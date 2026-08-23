import os
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete
from fastapi import UploadFile

from app.config import get_settings
from app.models.resume import Resume
from app.models.chat import ChatSession
from app.services.file_parser import parse_file, allowed_file, ALLOWED_EXTENSIONS
from app.services.anonymizer import anonymize_text
from app.services.llm_service import llm_service
from app.services.avatar_service import extract_avatar

settings = get_settings()


# Contact/identity fields that must survive a polish re-parse: polish rewrites the
# descriptive content (experience/projects/skills) but never changes who the person is.
_IDENTITY_FIELDS = ("name", "phone", "email", "location", "job_title", "years_of_experience")


def merge_polish_structured(old: dict, new: dict) -> dict:
    """Merge a re-parsed (polished) structured resume over the previous one.

    Keeps descriptive arrays (education/work/projects/skills/certificates/languages)
    from the polished parse while preserving identity fields from the original when the
    new parse dropped them (common, since polish output often omits contact info).
    """
    merged = dict(new or {})
    old_basic = (old or {}).get("basic_info") or {}
    new_basic = merged.get("basic_info") or {}
    if not isinstance(new_basic, dict):
        new_basic = {}
    for field in _IDENTITY_FIELDS:
        if not new_basic.get(field) and old_basic.get(field):
            new_basic[field] = old_basic[field]
    merged["basic_info"] = new_basic
    return merged


async def upload_and_parse_resume(
    db: AsyncSession,
    user_id: uuid.UUID,
    file: UploadFile,
    version_name: str = "v1",
) -> Resume:
    if not allowed_file(file.filename):
        allowed = ", ".join(ext[1:] for ext in sorted(ALLOWED_EXTENSIONS))
        raise ValueError(f"Unsupported file type. Allowed: {allowed}")

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    # Save original file
    file_ext = os.path.splitext(file.filename)[1]
    saved_filename = f"{uuid.uuid4()}{file_ext}"
    saved_path = os.path.join(settings.UPLOAD_DIR, saved_filename)

    content = await file.read()
    with open(saved_path, "wb") as f:
        f.write(content)

    # Parse text
    raw_text = await parse_file(saved_path)

    # Extract the real person avatar from image resumes (best-effort; None on failure)
    avatar_url: str | None = None
    if os.path.splitext(file.filename)[1].lower() in (".png", ".jpg", ".jpeg", ".webp"):
        avatar_url = await extract_avatar(saved_path)

    # Anonymize (kept only as a privacy-safe fallback copy)
    anonymized_text, pii_found = anonymize_text(raw_text)

    # 结构化解析（用于视觉模板渲染；失败不阻塞上传）
    structured: dict = {}
    if raw_text and settings.OPENAI_API_KEY:
        try:
            structured = await llm_service.parse_resume(raw_text, is_premium=False)
        except Exception:
            structured = {}

    # Count existing resumes for version naming
    count_result = await db.execute(
        select(func.count()).where(Resume.user_id == user_id)
    )
    count = count_result.scalar()
    if version_name == "v1":
        version_name = f"v{count + 1}"

    resume = Resume(
        user_id=user_id,
        version_name=version_name,
        original_filename=file.filename,
        original_file_url=saved_path,
        avatar_url=avatar_url,
        content=raw_text,
        anonymized_text=anonymized_text,
        parsed_data={
            "pii_removed": pii_found,
            "word_count": len(raw_text.split()) if raw_text else 0,
            "structured": structured,
        },
    )
    db.add(resume)
    await db.flush()
    await db.refresh(resume)
    return resume


async def get_user_resumes(db: AsyncSession, user_id: uuid.UUID) -> list[Resume]:
    result = await db.execute(
        select(Resume).where(Resume.user_id == user_id).order_by(Resume.created_at.desc())
    )
    return list(result.scalars().all())


async def get_resume_by_id(db: AsyncSession, resume_id: uuid.UUID, user_id: uuid.UUID) -> Resume | None:
    result = await db.execute(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def update_resume_parsed_data(
    db: AsyncSession, resume_id: uuid.UUID, user_id: uuid.UUID, structured: dict
) -> Resume:
    """Merge structured parse output into parsed_data (preserving pii_removed / word_count)."""
    resume = await get_resume_by_id(db, resume_id, user_id)
    parsed = dict(resume.parsed_data or {})
    parsed["structured"] = structured
    resume.parsed_data = parsed
    await db.flush()
    await db.refresh(resume)
    return resume


def _remove_upload_files(urls: list[str]) -> list[str]:
    """Best-effort remove disk files (original + avatar) under UPLOAD_DIR."""
    removed: list[str] = []
    for url in urls:
        if not url:
            continue
        try:
            name = os.path.basename(url.replace("\\", "/"))
            if not name or name in (".", ".."):
                continue
            path = os.path.join(settings.UPLOAD_DIR, name)
            if os.path.exists(path):
                os.remove(path)
                removed.append(name)
        except Exception:
            pass
    return removed


async def delete_resume(db: AsyncSession, resume_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Delete one resume. Returns True if deleted, False if not found / not owned."""
    resume = await get_resume_by_id(db, resume_id, user_id)
    if not resume:
        return False
    files = [u for u in (resume.original_file_url, resume.avatar_url) if u]
    # 关联的面试会话 resume_id 置空（保留会话，仅失去简历预览）
    await db.execute(
        update(ChatSession).where(ChatSession.resume_id == resume_id).values(resume_id=None)
    )
    await db.delete(resume)
    await db.flush()
    _remove_upload_files(files)
    return True


async def delete_all_resumes(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Delete all of the user's resumes. Returns count deleted."""
    resumes = await get_user_resumes(db, user_id)
    if not resumes:
        return 0
    ids = [r.id for r in resumes]
    files = [u for r in resumes for u in (r.original_file_url, r.avatar_url) if u]
    await db.execute(
        update(ChatSession).where(ChatSession.resume_id.in_(ids)).values(resume_id=None)
    )
    result = await db.execute(delete(Resume).where(Resume.user_id == user_id))
    await db.flush()
    _remove_upload_files(files)
    return result.rowcount or 0
