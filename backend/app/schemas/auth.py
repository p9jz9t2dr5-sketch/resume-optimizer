from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
import uuid


# --- Auth Schemas ---
class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    is_premium: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserStatsResponse(BaseModel):
    resume_count: int
    session_count: int
    messages_today: int
    daily_limit: int
    is_premium: bool
