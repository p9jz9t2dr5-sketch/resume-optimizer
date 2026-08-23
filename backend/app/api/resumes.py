import json
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db, async_session
from app.middleware.auth_middleware import get_current_user
from app.models.user import User
from app.schemas.resume import (
    ResumeUploadResponse,
    ResumeResponse,
    ResumeListResponse,
    PolishRequest,
    ResumeStructured,
)
from app.services.resume_service import (
    upload_and_parse_resume,
    get_user_resumes,
    get_resume_by_id,
    update_resume_parsed_data,
    merge_polish_structured,
    delete_resume,
    delete_all_resumes,
)
from app.services.llm_service import llm_service
from app.services.avatar_service import _resolve_avatar_url

settings = get_settings()
router = APIRouter()


@router.post("/upload", response_model=ResumeUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_resume(
    file: UploadFile = File(...),
    version_name: str = Form(default="v1"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        resume = await upload_and_parse_resume(db, current_user.id, file, version_name)
        resume.avatar_url = _resolve_avatar_url(resume.avatar_url)
        return resume
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process file: {str(e)}",
        )


@router.get("", response_model=ResumeListResponse)
async def list_resumes(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    resumes = await get_user_resumes(db, current_user.id)
    for r in resumes:
        r.avatar_url = _resolve_avatar_url(r.avatar_url)
    return ResumeListResponse(
        resumes=[ResumeResponse.model_validate(r) for r in resumes],
        total=len(resumes),
    )


@router.delete("")
async def clear_all_resumes(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete all of the user's resumes (and their upload files)."""
    deleted = await delete_all_resumes(db, current_user.id)
    return {"deleted": deleted}


@router.delete("/{resume_id}")
async def delete_resume_endpoint(
    resume_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single resume (and its upload file)."""
    ok = await delete_resume(db, uuid.UUID(resume_id), current_user.id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    return {"deleted": True}


@router.get("/{resume_id}", response_model=ResumeResponse)
async def get_resume(
    resume_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    import uuid
    resume = await get_resume_by_id(db, uuid.UUID(resume_id), current_user.id)
    if not resume:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    resume.avatar_url = _resolve_avatar_url(resume.avatar_url)
    return resume


def _structured_to_text(st: dict) -> str:
    """Render the optimized structured resume into a readable plain-text file."""
    lines: list[str] = []
    basic = st.get("basic_info") or {}
    if basic.get("name"):
        lines.append(str(basic["name"]))
    if basic.get("job_title"):
        lines.append(f"应聘岗位：{basic['job_title']}")
    contact = []
    for k in ("phone", "email", "location"):
        if basic.get(k):
            contact.append(f"{ '手机' if k == 'phone' else ('邮箱' if k == 'email' else '现居地') }：{basic[k]}")
    if contact:
        lines.append("  ".join(contact))
    if lines:
        lines.append("")

    if st.get("summary"):
        lines.append("个人简介")
        lines.append(str(st["summary"]))
        lines.append("")

    sections = [
        ("education", "教育背景", lambda it: (it.get("school") or "", it.get("major") or "", it.get("degree"))),
        ("work_experience", "工作经历", lambda it: (it.get("company") or "", it.get("title") or "", None)),
        ("projects", "项目经历", lambda it: (it.get("name") or "", it.get("role") or "", None)),
    ]
    for key, label, head_fn in sections:
        items = st.get(key) or []
        if not items:
            continue
        lines.append(label)
        for it in items:
            title, sub, extra = head_fn(it)
            head = " · ".join([x for x in (title, sub) if x])
            meta = " — ".join([x for x in (it.get("start"), it.get("end")) if x])
            line = f"- {head}" + (f" ({meta})" if meta else "")
            if extra:
                line += f"  {extra}"
            lines.append(line)
            desc = it.get("description")
            if desc:
                for d in str(desc).split("\n"):
                    if d.strip():
                        lines.append(f"    {d.strip()}")
            if it.get("tech_stack"):
                lines.append(f"    技术栈：{'、'.join(it['tech_stack'])}")
        lines.append("")

    for key, label in (("skills", "专业技能"), ("certificates", "证书荣誉"), ("languages", "语言能力")):
        items = st.get(key) or []
        if items:
            lines.append(label)
            lines.append("、".join(str(x) for x in items))
            lines.append("")

    return "\n".join(lines).strip() + "\n"


@router.get("/{resume_id}/export")
async def export_resume(
    resume_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Download the resume as a .txt file.

    Prefers the optimized structured data (reflects AI polish) when present,
    falling back to the raw parsed text.
    """
    import uuid
    from fastapi.responses import StreamingResponse
    import io
    resume = await get_resume_by_id(db, uuid.UUID(resume_id), current_user.id)
    if not resume:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    parsed_data = resume.parsed_data if isinstance(resume.parsed_data, dict) else {}
    structured = parsed_data.get("structured")
    safe_name = resume.original_filename.rsplit(".", 1)[0] if "." in (resume.original_filename or "") else (resume.original_filename or "resume")
    if structured:
        # Export the optimized, structured resume (reflects AI polish).
        resume_text = _structured_to_text(structured)
        filename = f"{safe_name}_optimized.txt"
    else:
        resume_text = resume.content or resume.anonymized_text
        if not resume_text:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No resume text available")
        filename = f"{safe_name}.txt"
    return StreamingResponse(
        io.BytesIO(resume_text.encode("utf-8")),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{resume_id}/polish")
async def polish_resume(
    resume_id: str,
    request: PolishRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stream an AI-polished resume tailored to a job description (SSE)."""
    resume = await get_resume_by_id(db, uuid.UUID(resume_id), current_user.id)
    if not resume:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    resume_text = resume.content or resume.anonymized_text
    if not resume_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Resume has no parsed text")

    if not settings.OPENAI_API_KEY:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI service not configured")

    rid = uuid.UUID(resume_id)

    async def event_stream():
        # Accumulate the full polished resume so we can re-parse it into structured
        # fields and persist them — this is what makes the visual preview after a
        # one-click polish actually reflect the optimizations (instead of looking
        # identical to the pre-optimization resume).
        accumulated: list[str] = []
        try:
            async for chunk in llm_service.polish_stream(
                resume_text, request.jd_text, request.match_report, current_user.is_premium
            ):
                accumulated.append(chunk)
                yield f"data: {json.dumps({'content': chunk})}\n\n"

            polished_text = "".join(accumulated)
            if polished_text and settings.OPENAI_API_KEY:
                try:
                    new_structured = await llm_service.parse_resume(polished_text, current_user.is_premium)
                    old_structured = (resume.parsed_data or {}).get("structured", {})
                    merged = merge_polish_structured(old_structured, new_structured)
                    # NOTE: the request-scoped `db` session may already be closed by
                    # the time this streaming generator runs its post-yield code, so
                    # persist inside a fresh session to avoid a silent "session closed"
                    # failure that leaves parsed_data.structured unchanged (preview == original).
                    import logging as _logging
                    try:
                        async with async_session() as s:
                            await update_resume_parsed_data(s, rid, current_user.id, merged)
                            await s.commit()
                        # Surface the optimized structured to the client so the
                        # visual preview/export can render it directly, without a
                        # second GET round-trip that might silently fail and leave
                        # the preview showing the *original* resume.
                        yield f"data: {json.dumps({'structured': merged}, ensure_ascii=False)}\n\n"
                    except Exception as persist_err:
                        _logging.getLogger("uvicorn").error(
                            "polish: failed to persist structured => %s: %s",
                            type(persist_err).__name__, persist_err,
                        )
                        raise
                except Exception as outer_err:
                    # Best-effort: the streamed polish text is still delivered to the client.
                    import logging as _logging2
                    _logging2.getLogger("uvicorn").error(
                        "polish: re-parse/persist skipped => %s: %s",
                        type(outer_err).__name__, outer_err,
                    )

            yield "data: [DONE]\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.post("/{resume_id}/parse", response_model=ResumeResponse)
async def parse_resume_endpoint(
    resume_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Parse resume into structured fields (education/work/projects/skills) via LLM and persist."""
    resume = await get_resume_by_id(db, uuid.UUID(resume_id), current_user.id)
    if not resume:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    resume_text = resume.content or resume.anonymized_text
    if not resume_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Resume has no parsed text")
    if not settings.OPENAI_API_KEY:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI service not configured")

    try:
        data = await llm_service.parse_resume(resume_text, current_user.is_premium)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"AI service error: {str(e)}")

    # Normalize via schema; fall back to raw dict on validation failure (best-effort, don't 500)
    try:
        structured = ResumeStructured(**data).model_dump()
    except Exception:
        structured = data if isinstance(data, dict) else {}

    return await update_resume_parsed_data(db, uuid.UUID(resume_id), current_user.id, structured)
