from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
import uuid


class ChatStartRequest(BaseModel):
    resume_id: uuid.UUID
    jd_text: Optional[str] = ""
    title: Optional[str] = "Mock Interview"


class ChatStartResponse(BaseModel):
    session_id: uuid.UUID
    title: str
    status: str
    resume_id: Optional[uuid.UUID]
    created_at: datetime

    class Config:
        from_attributes = True


class ChatMessageRequest(BaseModel):
    content: str


class MessageResponse(BaseModel):
    id: uuid.UUID
    session_id: uuid.UUID
    role: str
    content: str
    tokens_used: int
    created_at: datetime

    class Config:
        from_attributes = True


class ChatSessionResponse(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    resume_id: Optional[uuid.UUID]
    jd_text: Optional[str]
    message_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ChatSessionListResponse(BaseModel):
    sessions: list[ChatSessionResponse]
    total: int
