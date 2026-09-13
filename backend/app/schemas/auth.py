"""账号相关的请求/响应模型：注册、登录、改昵称、用户信息、用量统计。"""

from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional
from datetime import datetime
import uuid


# --- Auth Schemas ---
class RegisterRequest(BaseModel):
    email: EmailStr
    # 8 characters minimum, and capped at 72 because bcrypt silently ignores
    # everything past 72 bytes — rejecting is friendlier than truncating.
    password: str = Field(min_length=8, max_length=72)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class UpdateProfileRequest(BaseModel):
    """Only the display name is editable; email is the login identity."""

    display_name: str = Field(min_length=1, max_length=8)

    @field_validator("display_name")
    @classmethod
    def _strip_and_check(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("昵称不能为空")
        return value


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None
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
