"""账号相关路由（在 app/main.py 里以 /auth 前缀挂载，最终路径 = /api/auth/*）。

| 方法 | 路径 | 说明 | 需要登录 |
|------|------|------|----------|
| POST | /register | 注册新账号（密码 8–72 位） | 否 |
| POST | /login | 登录，返回 access + refresh token；失败按 IP+邮箱限流 | 否 |
| POST | /refresh | 用 refresh token 换一个新的 access token | 否 |
| GET | /me | 当前登录用户信息 | 是 |
| PATCH | /me | 修改昵称（1–8 字） | 是 |
| POST | /me/avatar | 上传头像（服务端居中裁剪为 256×256 PNG） | 是 |
| DELETE | /me/avatar | 删除头像 | 是 |
| DELETE | /me | 注销账号：清空该用户全部数据与上传文件 | 是 |
| GET | /me/stats | 简历数 / 面试会话数 / 今日消息用量与上限 | 是 |
"""

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    UpdateProfileRequest,
    UserResponse,
    UserStatsResponse,
)
from app.services.auth_service import (
    register_user,
    authenticate_user,
    create_access_token,
    create_refresh_token,
    refresh_access_token,
    delete_user_account,
)
from app.services.avatar_service import delete_stored_file, store_user_avatar
from app.services.login_throttle import WINDOW_SECONDS, login_throttle
from app.middleware.auth_middleware import get_current_user
from app.models.user import User
from app.services.quota_service import quota_service
from app.config import get_settings

router = APIRouter()
settings = get_settings()

# Profile picture upload limits.
MAX_AVATAR_BYTES = 5 * 1024 * 1024
ALLOWED_AVATAR_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}


class RefreshRequest(BaseModel):
    refresh_token: str


def _client_key(http_request: Request) -> str:
    """Best-effort client identity for throttling.

    Behind nginx the socket address is the proxy, so prefer the first hop of
    X-Forwarded-For (nginx sets it in nginx/nginx.conf).
    """
    forwarded = http_request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return http_request.client.host if http_request.client else "unknown"


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)):
    """注册新账号。

    入参：email + password（8–72 位，越界由 RegisterRequest 直接返回 422）
    返回：201 + 用户信息（id / email / 昵称 / 头像，不含密码哈希）
    异常：邮箱已注册 → 409
    """
    try:
        user = await register_user(db, request.email, request.password)
        return user
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    http_request: Request,
    db: AsyncSession = Depends(get_db),
):
    """登录并签发 JWT。

    入参：email + password
    返回：access token + refresh token（后续请求用 `Authorization: Bearer <access>`）
    异常：账号或密码错误统一返回 401（不透露邮箱是否存在）；
          同一「客户端 IP + 邮箱」15 分钟内失败 5 次后返回 429，登录成功即清零。
    """
    identifier = f"{_client_key(http_request)}:{request.email.lower()}"

    if await login_throttle.is_blocked(identifier):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"该账号登录失败次数过多，请 {WINDOW_SECONDS // 60} 分钟后再试",
        )

    user = await authenticate_user(db, request.email, request.password)
    if not user:
        await login_throttle.register_failure(identifier)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="邮箱或密码错误",
        )

    await login_throttle.clear(identifier)
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    """返回当前登录用户的信息（前端启动时调用它判断登录状态）。"""
    return current_user


@router.delete("/me")
async def delete_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete the account together with all of its data.

    Removes the user's resumes, job descriptions, interview sessions and
    messages, plus every file they uploaded (original resume files, extracted
    avatars and the profile picture). The upload files are only unlinked after
    the transaction commits, so a failed commit cannot leave the database
    pointing at deleted files.
    """
    user_id = str(current_user.id)
    stored_files = await delete_user_account(db, current_user)
    await db.commit()

    removed = sum(1 for url in stored_files if delete_stored_file(url))
    await quota_service.clear_daily(user_id)

    return {
        "deleted": True,
        "files_removed": removed,
        "files_tracked": len(stored_files),
    }


@router.patch("/me", response_model=UserResponse)
async def update_me(
    request: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """修改昵称。

    入参：display_name（1–8 字，前后空格会被去掉）
    返回：更新后的用户信息
    异常：空字符串或超过 8 字 → 422
    """
    current_user.display_name = request.display_name
    await db.commit()
    await db.refresh(current_user)
    return current_user


@router.post("/me/avatar", response_model=UserResponse)
async def upload_my_avatar(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """上传 / 替换头像。

    入参：multipart 文件（仅 PNG / JPG / WebP，≤5MB）
    处理：用 Pillow 居中裁剪成 256×256 并统一存为 PNG；旧头像文件在新头像
          写库成功之后才删除，避免事务失败导致图片先没了
    返回：更新后的用户信息（含新的 avatar_url）
    异常：类型不支持 / 文件为空 / 超过 5MB / 不是合法图片 → 400
    """
    if file.content_type not in ALLOWED_AVATAR_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅支持 PNG / JPG / WebP 格式的图片",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="上传的文件为空")
    if len(data) > MAX_AVATAR_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="图片过大，请上传 5MB 以内的图片",
        )

    try:
        stored_path = store_user_avatar(data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    previous = current_user.avatar_url
    current_user.avatar_url = stored_path
    await db.commit()
    await db.refresh(current_user)

    # Only drop the old file once the new one is safely committed.
    delete_stored_file(previous)
    return current_user


@router.delete("/me/avatar", response_model=UserResponse)
async def delete_my_avatar(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除头像：清空字段并删除磁盘文件，前端会退回显示「昵称首字」的圆形头像。"""
    previous = current_user.avatar_url
    current_user.avatar_url = None
    await db.commit()
    await db.refresh(current_user)
    delete_stored_file(previous)
    return current_user


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: RefreshRequest):
    """用 refresh token 换一个新的 access token。

    入参：refresh_token
    返回：新的 access_token（refresh_token 原样返回，不做轮换）
    异常：token 过期 / 伪造 / 类型不对 → 401
    """
    try:
        access_token = refresh_access_token(request.refresh_token)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(access_token=access_token, refresh_token=request.refresh_token)


@router.get("/me/stats", response_model=UserStatsResponse)
async def get_user_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """控制面板顶部三张统计卡的数据来源。

    返回：简历数、面试会话数、今日已用消息数与上限（会员上限为 999999）
    说明：今日用量来自 quota_service（Redis 计数；未配置 Redis 时退化为进程内计数）。
    """
    from sqlalchemy import select, func
    from app.models.resume import Resume
    from app.models.chat import ChatSession, Message

    resume_count = await db.scalar(
        select(func.count()).where(Resume.user_id == current_user.id)
    )
    session_count = await db.scalar(
        select(func.count()).where(ChatSession.user_id == current_user.id)
    )
    messages_today = await quota_service.get_daily_count(str(current_user.id))
    daily_limit = (
        999999 if current_user.is_premium else settings.FREE_DAILY_MESSAGE_LIMIT
    )

    return UserStatsResponse(
        resume_count=resume_count or 0,
        session_count=session_count or 0,
        messages_today=messages_today,
        daily_limit=daily_limit,
        is_premium=current_user.is_premium,
    )
