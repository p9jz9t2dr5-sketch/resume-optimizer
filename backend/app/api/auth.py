from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
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
from app.services.auth_service import register_user, authenticate_user, create_access_token, create_refresh_token, refresh_access_token
from app.services.avatar_service import delete_stored_file, store_user_avatar
from app.middleware.auth_middleware import get_current_user
from app.models.user import User
from app.services.quota_service import quota_service

router = APIRouter()

# Profile picture upload limits.
MAX_AVATAR_BYTES = 5 * 1024 * 1024
ALLOWED_AVATAR_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest, db: AsyncSession = Depends(get_db)):
    try:
        user = await register_user(db, request.email, request.password)
        return user
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    user = await authenticate_user(db, request.email, request.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )
    return TokenResponse(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.patch("/me", response_model=UserResponse)
async def update_me(
    request: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the editable part of the profile (display name)."""
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
    """Replace the user's avatar with an uploaded image (PNG / JPG / WebP)."""
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
    """Remove the avatar so the UI falls back to the initial letter."""
    previous = current_user.avatar_url
    current_user.avatar_url = None
    await db.commit()
    await db.refresh(current_user)
    delete_stored_file(previous)
    return current_user


@router.post("/refresh", response_model=TokenResponse)
async def refresh(request: RefreshRequest):
    """Exchange a valid refresh token for a new access token (refresh token reused)."""
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
    daily_limit = 999999 if current_user.is_premium else 20

    return UserStatsResponse(
        resume_count=resume_count or 0,
        session_count=session_count or 0,
        messages_today=messages_today,
        daily_limit=daily_limit,
        is_premium=current_user.is_premium,
    )
