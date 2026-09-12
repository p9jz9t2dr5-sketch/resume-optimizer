import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, func, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    # Display name the user can edit from the header avatar menu. NULL means the
    # UI falls back to the local part of the email.
    display_name: Mapped[str] = mapped_column(String(100), nullable=True)
    # Stored as a path under UPLOAD_DIR (e.g. './uploads/avatar_<uuid>.png'), the
    # same shape the resume avatar extraction produces.
    avatar_url: Mapped[str] = mapped_column(String(1000), nullable=True)
    is_premium: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())

    resumes = relationship("Resume", back_populates="user", cascade="all, delete-orphan")
    job_descriptions = relationship("JobDescription", back_populates="user", cascade="all, delete-orphan")
    chat_sessions = relationship("ChatSession", back_populates="user", cascade="all, delete-orphan")
