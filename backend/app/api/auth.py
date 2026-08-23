from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.auth import (
    RegisterRequest,
    LoginRequest,
    TokenResponse,
    UserResponse,
    UserStatsResponse,
)
from app.services.auth_service import register_user, authenticate_user, create_access_token, create_refresh_token, refresh_access_token
from app.middleware.auth_middleware import get_current_user
from app.models.user import User
from app.services.quota_service import quota_service

router = APIRouter()


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
