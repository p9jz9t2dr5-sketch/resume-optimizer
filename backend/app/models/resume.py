"""resumes 表：一份上传的简历。

- content：含真实 PII 的原文（预览、导出、重新优化用）
- anonymized_text：脱敏副本（隐私安全兜底）
- parsed_data.structured：结构化简历（教育/工作/项目/技能），前端据它显示摘要
- avatar_url：图片简历里裁剪出的证件照
"""

import uuid
from datetime import datetime
from sqlalchemy import String, Text, DateTime, ForeignKey, func, Uuid, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    version_name: Mapped[str] = mapped_column(String(255), default="v1")
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    original_file_url: Mapped[str] = mapped_column(String(1000), nullable=True)
    # Cropped person photo/avatar extracted from an uploaded image resume via
    # Qwen-VL bbox + Pillow. Null for non-image resumes or when detection fails.
    avatar_url: Mapped[str] = mapped_column(String(1000), nullable=True)
    # Raw, un-masked resume text WITH real PII (name/phone/email). This is the
    # source of truth used for preview, AI polish, parse, match and export so the
    # optimized deliverable keeps the user's real contact info.
    content: Mapped[str] = mapped_column(Text, nullable=True)
    # Masked copy kept only as a privacy-safe fallback (e.g. old records / redacted view).
    anonymized_text: Mapped[str] = mapped_column(Text, nullable=True)
    parsed_data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=func.now())

    user = relationship("User", back_populates="resumes")
    chat_sessions = relationship("ChatSession", back_populates="resume")
