"""模拟面试服务：会话增删查、组装上下文、流式调用模型并把问答写入数据库。"""

import logging
import uuid
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete

from app.database import async_session
from app.models.chat import ChatSession, Message, SessionStatus
from app.models.resume import Resume
from app.services.llm_service import llm_service

logger = logging.getLogger("uvicorn")


async def create_session(
    db: AsyncSession,
    user_id: uuid.UUID,
    resume_id: uuid.UUID,
    jd_text: str,
    title: str = "Resume Optimization",
) -> ChatSession:
    """新建一场面试会话；简历不存在或不属于该用户时抛 ValueError（接口转 404）。"""
    # Verify resume belongs to user
    result = await db.execute(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == user_id)
    )
    resume = result.scalar_one_or_none()
    if not resume:
        raise ValueError("Resume not found")

    session = ChatSession(
        user_id=user_id,
        resume_id=resume_id,
        jd_text=jd_text,
        title=title,
    )
    db.add(session)
    await db.flush()
    await db.refresh(session)
    return session


async def get_user_sessions(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    """取某个用户的面试记录（按更新时间倒序，含消息条数）。"""
    result = await db.execute(
        select(ChatSession)
        .where(ChatSession.user_id == user_id)
        .order_by(ChatSession.updated_at.desc())
    )
    sessions = result.scalars().all()

    session_list = []
    for s in sessions:
        msg_count = await db.execute(
            select(func.count()).where(Message.session_id == s.id)
        )
        count = msg_count.scalar()
        session_list.append({
            "id": s.id,
            "title": s.title,
            "status": s.status.value if isinstance(s.status, SessionStatus) else s.status,
            "resume_id": s.resume_id,
            "jd_text": s.jd_text,
            "message_count": count or 0,
            "created_at": s.created_at,
            "updated_at": s.updated_at,
        })
    return session_list


async def get_session_messages(db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID) -> list[Message]:
    """取某场面试的全部消息（按时间正序）；会话不存在或不属于该用户时抛 ValueError。"""
    # Verify ownership
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id)
    )
    session = result.scalar_one_or_none()
    if not session:
        raise ValueError("Session not found")

    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
    )
    return list(result.scalars().all())


async def stream_chat_response(
    session_id: uuid.UUID,
    user_id: uuid.UUID,
    user_message: str,
    is_premium: bool,
) -> AsyncGenerator[str, None]:
    """Stream an AI chat reply, persisting both sides of the exchange.

    This deliberately does NOT take the request-scoped `db` session. FastAPI tears
    down `Depends(get_db)` as soon as the endpoint returns the StreamingResponse,
    which happens *before* this generator is iterated. Touching that session here
    fails ("session closed" / greenlet errors), which previously made every chat
    message abort with "AI service error" before a single token reached the client.
    Instead each DB phase runs in its own short-lived session.
    """
    # --- Phase 1: load context + persist the user message (own session) ---
    async with async_session() as s:
        result = await s.execute(
            select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id)
        )
        session = result.scalar_one_or_none()
        if not session:
            raise ValueError("Session not found")

        resume = None
        if session.resume_id:
            result = await s.execute(select(Resume).where(Resume.id == session.resume_id))
            resume = result.scalar_one_or_none()

        resume_text = (resume.content or resume.anonymized_text or "") if resume else ""
        jd_text = session.jd_text or ""

        if not resume_text and session.resume_id:
            logger.warning(
                "chat: resume %s is bound but resume_text is EMPTY "
                "(both content and anonymized_text are null/empty) — model gets no resume.",
                session.resume_id,
            )

        s.add(Message(session_id=session_id, role="user", content=user_message))
        # Flush explicitly so the message just added is included in the history
        # query below (which is what the model needs to see as the latest turn).
        await s.flush()

        result = await s.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.asc())
        )
        messages_for_ai = [{"role": m.role, "content": m.content} for m in result.scalars().all()]

        # Diagnostics: surface exactly what context the model receives. The chat
        # reply is the model's own text (not a code string), so when something
        # looks wrong (e.g. a confusing answer) these lines in the backend
        # terminal tell us whether the resume/JD actually reached the model.
        logger.info(
            "chat: ctx session=%s resume_id=%s resume_text_len=%d jd_len=%d history=%d",
            session_id, session.resume_id, len(resume_text), len(jd_text), len(messages_for_ai),
        )

        await s.commit()

    # --- Phase 2: stream from the LLM (no DB session held open across the stream) ---
    full_response = ""
    async for chunk in llm_service.chat_stream(
        messages=messages_for_ai,
        anonymized_resume=resume_text,
        jd_text=jd_text,
        is_premium=is_premium,
    ):
        full_response += chunk
        yield chunk

    logger.info(
        "chat: model_response session=%s len=%d first200=%r",
        session_id, len(full_response), full_response[:200],
    )
    if not full_response.strip():
        # Model returned nothing — don't leave the user with an empty bubble.
        logger.warning("chat: model returned EMPTY response for session=%s", session_id)
        full_response = "⚠️ 模型未返回任何内容，请稍后重试，或换一个问题。"

    # --- Phase 3: persist the assistant reply (own session) ---
    # Best-effort: the user already received the full answer, so a persistence
    # failure must not surface as a chat error.
    try:
        async with async_session() as s:
            s.add(
                Message(
                    session_id=session_id,
                    role="assistant",
                    content=full_response,
                    tokens_used=len(full_response.split()),  # rough estimate
                )
            )
            await s.execute(
                ChatSession.__table__.update()
                .where(ChatSession.id == session_id)
                .values(updated_at=func.now())
            )
            await s.commit()
    except Exception as e:
        logger.error(
            "chat: failed to persist assistant message for session %s => %s: %s",
            session_id, type(e).__name__, e,
        )


async def delete_session(db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Delete one chat session (and its messages) if it belongs to the user.

    Returns True if deleted, False if not found / not owned.
    """
    result = await db.execute(
        select(ChatSession.id).where(
            ChatSession.id == session_id, ChatSession.user_id == user_id
        )
    )
    if not result.scalar_one_or_none():
        return False
    # 先删消息再删会话（SQLite 默认不启用 foreign_keys，ondelete 不生效，需手动）。
    await db.execute(delete(Message).where(Message.session_id == session_id))
    await db.execute(
        delete(ChatSession).where(
            ChatSession.id == session_id, ChatSession.user_id == user_id
        )
    )
    await db.flush()
    return True


async def delete_all_sessions(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Delete all chat sessions (and their messages) for the user. Returns count deleted."""
    session_ids = select(ChatSession.id).where(ChatSession.user_id == user_id)
    await db.execute(delete(Message).where(Message.session_id.in_(session_ids)))
    result = await db.execute(delete(ChatSession).where(ChatSession.user_id == user_id))
    await db.flush()
    return result.rowcount or 0
