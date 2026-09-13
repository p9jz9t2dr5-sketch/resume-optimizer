"""账号服务：bcrypt 密码哈希与校验、JWT 的签发/刷新、注销账号时的数据清理。"""

from datetime import datetime, timedelta
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select
import uuid

from app.config import get_settings
from app.models.user import User
from app.models.resume import Resume
from app.models.chat import ChatSession, Message
from app.models.job_description import JobDescription

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """用 bcrypt 生成密码哈希（成本因子 12，刻意变慢以抵抗离线爆破）。"""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """校验明文密码与库里的哈希是否匹配。"""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(user_id: uuid.UUID) -> str:
    """签发短期 access token（有效期 ACCESS_TOKEN_EXPIRE_MINUTES，默认 30 分钟）。"""
    expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"sub": str(user_id), "exp": expire, "type": "access"}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")


def create_refresh_token(user_id: uuid.UUID) -> str:
    """签发长期 refresh token（默认 7 天），用于不重新登录就换取新的 access token。"""
    expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {"sub": str(user_id), "exp": expire, "type": "refresh"}
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm="HS256")


def refresh_access_token(refresh_token: str) -> str:
    """Validate a refresh token and issue a new short-lived access token."""
    try:
        payload = jwt.decode(refresh_token, settings.SECRET_KEY, algorithms=["HS256"])
    except JWTError:
        raise ValueError("Invalid refresh token")
    if payload.get("type") != "refresh":
        raise ValueError("Invalid token type")
    user_id = payload.get("sub")
    if not user_id:
        raise ValueError("Invalid refresh token")
    return create_access_token(uuid.UUID(user_id))


async def register_user(db: AsyncSession, email: str, password: str) -> User:
    """创建用户；邮箱已存在时抛 ValueError，由接口层转成 409。"""
    existing = await db.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none():
        raise ValueError("该邮箱已被注册，请直接登录")

    user = User(
        email=email,
        hashed_password=hash_password(password),
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, email: str, password: str) -> User | None:
    """校验邮箱 + 密码；不通过返回 None（接口统一回 401，不透露邮箱是否存在）。"""
    result = await db.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if not user or not verify_password(password, user.hashed_password):
        return None
    return user


async def delete_user_account(db: AsyncSession, user: User) -> list[str]:
    """Delete a user and every piece of data that belongs to them.

    Children are deleted explicitly, deepest first, instead of leaning on
    ``ON DELETE CASCADE``: SQLite only enforces foreign keys when
    ``PRAGMA foreign_keys=ON``, so the explicit order is what makes local
    development and the test suite behave the same as Postgres.

    Returns the stored file URLs that belonged to the account. The caller
    deletes them *after* committing, so a failed commit can never leave the
    database pointing at files that are already gone.
    """
    user_id = user.id

    resume_files = [
        url
        for row in (
            await db.execute(
                select(Resume.original_file_url, Resume.avatar_url).where(
                    Resume.user_id == user_id
                )
            )
        ).all()
        for url in row
        if url
    ]
    stored_files = list(resume_files)
    if user.avatar_url:
        stored_files.append(user.avatar_url)

    await db.execute(
        delete(Message).where(
            Message.session_id.in_(
                select(ChatSession.id).where(ChatSession.user_id == user_id)
            )
        )
    )
    await db.execute(delete(ChatSession).where(ChatSession.user_id == user_id))
    await db.execute(delete(JobDescription).where(JobDescription.user_id == user_id))
    await db.execute(delete(Resume).where(Resume.user_id == user_id))
    await db.execute(delete(User).where(User.id == user_id))
    await db.flush()

    return stored_files
