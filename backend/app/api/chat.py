"""模拟面试（对话）路由（挂载前缀 /chat，最终路径 /api/chat/*）。

这一组接口支撑的是「AI 模拟面试」：面试官围绕简历里的项目经历逐轮追问，
而不是简历改写（改写见 /resumes/{id}/polish）。

| 方法 | 路径 | 说明 | 需要登录 |
|------|------|------|----------|
| POST | /start | 新建面试会话，并让模型生成面试官开场白（失败不影响会话创建） | 是 |
| GET | /sessions | 我的面试记录列表 | 是 |
| DELETE | /sessions | 清空全部面试记录 | 是 |
| DELETE | /{session_id} | 删除单场面试（连同消息） | 是 |
| GET | /{session_id}/messages | 某场面试的消息列表 | 是 |
| POST | /{session_id}/message | 发送回答，SSE 流式返回面试官的下一句；先预占免费额度 | 是 |

注意：/message 走 StreamingResponse，所以它刻意不注入请求级 db 会话
（FastAPI 会在生成器开始迭代前就关掉它），入库由 chat_service 自己开短会话完成。
"""

import json
import logging
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.config import get_settings
from app.middleware.auth_middleware import get_current_user
from app.services.quota_service import quota_service
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
settings = get_settings()


@router.post("/start", response_model=ChatStartResponse, status_code=status.HTTP_201_CREATED)
async def start_chat(
    request: ChatStartRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """新建一场模拟面试。

    入参：resume_id（必填且必须属于当前用户）、jd_text（可空）、title
    返回：201 + 会话信息（session_id / title / status）
    说明：建完会话会调模型生成「面试官开场白」并作为第一条 assistant 消息落库；
          这一步是 best-effort——模型不可用时照样返回会话，用户可以直接先开口。
    异常：简历不存在或不属于当前用户 → 404
    """
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
    """我的面试记录列表（按更新时间倒序，只返回当前用户的会话）。"""
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
    """清空我的全部面试记录（连同消息），返回删除的条数。"""
    deleted = await delete_all_sessions(db, current_user.id)
    return {"deleted": deleted}


@router.delete("/{session_id}")
async def delete_chat_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除单场面试（连同消息）；会话不属于当前用户时返回 404。"""
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
    """某场面试的消息列表（按时间正序）；会话不属于当前用户时返回 404。"""
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
    """发送一条回答，SSE 流式返回面试官的下一句。

    入参：content（用户这次说的话）
    返回：text/event-stream；正文帧 `data: {"content": "..."}`，结束帧 `data: [DONE]`，
          出错帧 `data: {"error": "..."}`
    说明：开始流式之前先原子预占一个免费额度（超额直接 429），模型报错则把额度退回。
    """
    # NOTE: no `Depends(get_db)` here on purpose — this endpoint returns a
    # StreamingResponse, and the request-scoped session would be torn down before
    # the generator runs. stream_chat_response manages its own sessions.

    # Reserve the message *before* calling the model: the counter must be shared
    # when concurrent requests arrive, otherwise a free account could fire many
    # parallel messages and slip past the daily limit together.
    if not await quota_service.consume_message(str(current_user.id), current_user.is_premium):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"今日免费额度已用完（{settings.FREE_DAILY_MESSAGE_LIMIT} 条/天），"
                "明天再来，或升级会员后不限量"
            ),
        )

    async def event_stream():
        failed = False
        try:
            async for chunk in stream_chat_response(
                uuid.UUID(session_id), current_user.id, request.content, current_user.is_premium
            ):
                yield f"data: {json.dumps({'content': chunk})}\n\n"

            yield "data: [DONE]\n\n"
        except ValueError as e:
            failed = True
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        except Exception as e:
            failed = True
            yield f"data: {json.dumps({'error': f'AI service error: {str(e)}'})}\n\n"
        finally:
            # A request that never produced an answer should not cost a message.
            if failed:
                await quota_service.release_message(str(current_user.id))

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
