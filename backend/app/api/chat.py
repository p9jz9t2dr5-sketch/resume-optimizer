import json
import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.user import User
from app.models.resume import Resume
from app.models.chat import Message
from app.schemas.chat import (
    ChatStartRequest,
    ChatStartResponse,
    ChatMessageRequest,
    MessageResponse,
    ChatSessionListResponse,
    ChatSessionResponse,
)
from app.services.chat_service import (
    create_session,
    get_user_sessions,
    get_session_messages,
    stream_chat_response,
    delete_session,
    delete_all_sessions,
)
from app.services.llm_service import llm_service

logger = logging.getLogger("uvicorn")

router = APIRouter()


@router.post("/start", response_model=ChatStartResponse, status_code=status.HTTP_201_CREATED)
async def start_chat(
    request: ChatStartRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        session = await create_session(
            db, current_user.id, request.resume_id, request.jd_text or "", request.title
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    # Generate the interviewer's opening line so the mock interview starts on its
    # own — the first message is an assistant greeting ("你好，同学……"), not the
    # user's. Best-effort: if the LLM call fails, the session still works and the
    # user can simply send the first message themselves.
    try:
        resume = await db.scalar(
            select(Resume).where(
                Resume.id == request.resume_id, Resume.user_id == current_user.id
            )
        )
        resume_text = (resume.content or resume.anonymized_text or "") if resume else ""
        opening = await llm_service.interview_opening(
            resume_text, request.jd_text or "", current_user.is_premium
        )
        if opening and opening.strip():
            db.add(Message(session_id=session.id, role="assistant", content=opening.strip()))
            await db.flush()
    except Exception as e:
        logger.error(
            "chat: failed to generate opening for session %s => %s: %s",
            session.id, type(e).__name__, e,
        )

    return ChatStartResponse(
        session_id=session.id,
        title=session.title,
        status=session.status.value,
        resume_id=session.resume_id,
        created_at=session.created_at,
    )


@router.get("/sessions", response_model=ChatSessionListResponse)
async def list_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sessions = await get_user_sessions(db, current_user.id)
    return ChatSessionListResponse(
        sessions=[ChatSessionResponse(**s) for s in sessions],
        total=len(sessions),
    )


@router.delete("/sessions")
async def clear_all_sessions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete all of the user's interview sessions (and their messages)."""
    deleted = await delete_all_sessions(db, current_user.id)
    return {"deleted": deleted}


@router.delete("/{session_id}")
async def delete_chat_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a single interview session (and its messages)."""
    ok = await delete_session(db, uuid.UUID(session_id), current_user.id)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
        )
    return {"deleted": True}


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
async def get_messages(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        messages = await get_session_messages(db, uuid.UUID(session_id), current_user.id)
        return [MessageResponse.model_validate(m) for m in messages]
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/{session_id}/message")
async def send_message(
    session_id: str,
    request: ChatMessageRequest,
    current_user: User = Depends(get_current_user),
):
    # NOTE: no `Depends(get_db)` here on purpose — this endpoint returns a
    # StreamingResponse, and the request-scoped session would be torn down before
    # the generator runs. stream_chat_response manages its own sessions.
    async def event_stream():
        try:
            async for chunk in stream_chat_response(
                uuid.UUID(session_id), current_user.id, request.content, current_user.is_premium
            ):
                yield f"data: {json.dumps({'content': chunk})}\n\n"

            yield "data: [DONE]\n\n"
        except ValueError as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': f'AI service error: {str(e)}'})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
