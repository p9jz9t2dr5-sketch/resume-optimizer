"""Agent 路由（挂载前缀 /agent，最终路径 /api/agent/*）。

| 方法 | 路径 | 说明 | 需要登录 |
|------|------|------|----------|
| POST | /optimize | 跑一次 Agent 简历优化任务，SSE 流式返回「计划 → 工具调用 → 报告」 | 是 |
| GET | /runs | 我的 Agent 执行记录（不含轨迹明细） | 是 |
| DELETE | /runs | 清空我的执行记录 | 是 |
| GET | /runs/{run_id} | 一次任务的完整执行轨迹（规划 / 工具 / 压缩 / 收尾） | 是 |
| DELETE | /runs/{run_id} | 删除一次执行记录 | 是 |
| GET | /preferences | 我的长期记忆（跨任务偏好） | 是 |
| PUT | /preferences/{key} | 写入/覆盖一条偏好（source=user，Agent 不能覆盖） | 是 |
| DELETE | /preferences/{key} | 删除一条偏好 | 是 |

SSE 事件格式（每帧 ``data: {json}``，以 ``data: [DONE]`` 结束）：

| 帧 | 含义 |
|----|------|
| ``{"type":"run","run_id":...}`` | 任务已建记录，可据此查轨迹 |
| ``{"type":"plan","plan":[...]}`` | 规划器产出的执行计划 |
| ``{"type":"step",...}`` | 一条轨迹（已落库） |
| ``{"type":"tool_call","tool":...,"input":{...}}`` | 即将调用某工具 |
| ``{"type":"tool_result","tool":...,"ok":bool,"summary":...}`` | 工具执行结果 |
| ``{"type":"replan" / "compaction" / "thinking"}`` | 重规划 / 上下文压缩 / 模型中间说明 |
| ``{"content":"..."}`` | 最终报告分片（沿用旧「一键优化」帧格式） |
| ``{"structured":{...}}`` | 优化后的结构化简历（有版块被改写时才有） |
| ``{"type":"fallback","reason":...}`` | 模型不支持工具调用，已降级为单次改写 |
| ``{"type":"done",...}`` / ``{"error":"..."}`` | 结束 / 出错 |

注意 ``thinking`` 与 ``final`` 两帧也带 ``content`` 字段：前者是模型的中间说明、后者是
整篇报告（与上面的分片帧内容相同）。**正文只应累加 ``type == "content"`` 的帧**，
否则会把报告拼两遍、并把过程说明混进正文——这一条是踩过坑之后补上的约定。

与 ``/resumes/{id}/polish`` 的区别：那个接口是「一次 prompt 出建议」，这个接口是
「先规划、再调工具查证据、改写后检查数字幻觉、最后汇总」，并且全过程留痕可复盘。
"""

import json
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.memory import KNOWN_KEYS, MemoryStore
from app.config import get_settings
from app.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.models.agent import UserPreference
from app.models.user import User
from app.schemas.agent import (
    AgentOptimizeRequest,
    AgentRunDetailResponse,
    AgentRunListResponse,
    AgentRunResponse,
    PreferenceListResponse,
    PreferenceResponse,
    PreferenceUpsertRequest,
)
from app.services.agent_service import (
    delete_all_runs,
    delete_run,
    get_run,
    list_runs,
    stream_optimize_agent,
)
from app.services.resume_service import get_resume_by_id

logger = logging.getLogger("uvicorn")
router = APIRouter()
settings = get_settings()


@router.post("/optimize")
async def optimize_resume(
    request: AgentOptimizeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """跑一次 Agent 优化任务（SSE 流式）。

    入参：resume_id（必填且属于当前用户）、jd_text（目标岗位）、match_report（可选，
          来自 /jd/parse）、max_steps（可选，覆盖默认步数上限）
    返回：text/event-stream，事件类型见模块文档
    异常：简历不存在 → 404；简历无正文 → 400；未配置模型 Key → 503

    注意：这里刻意不注入 request 级别的会话到流式生成器里（FastAPI 会在生成器
    开始迭代前关掉它），所有落库动作都由 agent_service 用短生命周期会话完成。
    """
    try:
        resume_id = uuid.UUID(request.resume_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")

    resume = await get_resume_by_id(db, resume_id, current_user.id)
    if resume is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resume not found")
    resume_text = resume.content or resume.anonymized_text
    if not resume_text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Resume has no parsed text")
    if not settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="AI service not configured"
        )

    # 先把值取出来：生成器开始迭代时请求级会话可能已经被回收。
    user_id = current_user.id
    is_premium = current_user.is_premium
    jd_text = request.jd_text
    match_report = request.match_report
    max_steps = request.max_steps

    async def event_stream():
        try:
            async for event in stream_optimize_agent(
                user_id=user_id,
                resume_id=resume_id,
                resume_text=resume_text,
                jd_text=jd_text,
                is_premium=is_premium,
                match_report=match_report,
                max_steps=max_steps,
            ):
                yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
        except Exception as exc:  # noqa: BLE001 — 生成器内异常必须变成一帧错误，否则前端只看到断流
            logger.error("agent: optimize stream failed => %s: %s", type(exc).__name__, exc)
            yield f"data: {json.dumps({'error': str(exc)}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/runs", response_model=AgentRunListResponse)
async def get_runs(
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """我的 Agent 执行记录（按时间倒序，不含轨迹明细，明细走 /runs/{id}）。"""
    runs = await list_runs(db, current_user.id, limit=max(1, min(limit, 100)))
    return AgentRunListResponse(
        runs=[AgentRunResponse.model_validate(run) for run in runs], total=len(runs)
    )


@router.delete("/runs")
async def clear_runs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """清空我的全部 Agent 执行记录（连同轨迹）。"""
    return {"deleted": await delete_all_runs(db, current_user.id)}


@router.get("/runs/{run_id}", response_model=AgentRunDetailResponse)
async def get_run_detail(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """一次任务的完整执行轨迹；记录不属于当前用户时返回 404。"""
    try:
        parsed_id = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    run = await get_run(db, parsed_id, current_user.id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return AgentRunDetailResponse.model_validate(run)


@router.delete("/runs/{run_id}")
async def delete_run_endpoint(
    run_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除一次执行记录；不属于当前用户时返回 404。"""
    try:
        parsed_id = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    if not await delete_run(db, parsed_id, current_user.id):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return {"deleted": True}


@router.get("/preferences", response_model=PreferenceListResponse)
async def list_preferences(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """我的长期记忆（跨任务偏好）；``known_keys`` 给出约定键的中文含义供前端渲染。"""
    rows = (
        await db.execute(
            select(UserPreference)
            .where(UserPreference.user_id == current_user.id)
            .order_by(UserPreference.updated_at.desc())
        )
    ).scalars().all()
    return PreferenceListResponse(
        preferences=[PreferenceResponse.model_validate(row) for row in rows],
        total=len(rows),
        known_keys=KNOWN_KEYS,
    )


@router.put("/preferences/{key}", response_model=PreferenceResponse)
async def upsert_preference(
    key: str,
    request: PreferenceUpsertRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """写入一条偏好。用户手设的偏好优先级最高，Agent 之后的自动写入不会覆盖它。"""
    store = MemoryStore(lambda: _noop_session(db))
    ok, message = await store.set(current_user.id, key, request.value, source="user")
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)
    await db.commit()
    row = (
        await db.execute(
            select(UserPreference).where(
                UserPreference.user_id == current_user.id, UserPreference.key == key
            )
        )
    ).scalar_one()
    return PreferenceResponse.model_validate(row)


@router.delete("/preferences/{key}")
async def delete_preference(
    key: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除一条偏好；不存在时返回 404。"""
    deleted = (
        await db.execute(
            select(UserPreference).where(
                UserPreference.user_id == current_user.id, UserPreference.key == key
            )
        )
    ).scalar_one_or_none()
    if deleted is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preference not found")
    await db.delete(deleted)
    await db.flush()
    return {"deleted": True}


class _NoopSessionContext:
    """把请求级会话包成 async context manager，好让 MemoryStore 复用同一会话。

    接口层已经有事务上下文（``get_db`` 负责 commit/rollback），如果 MemoryStore
    再开一个会话，同一次请求里就会出现两个事务，容易写出互相看不见的更新。
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def __aenter__(self) -> AsyncSession:
        return self.session

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


def _noop_session(session: AsyncSession) -> _NoopSessionContext:
    return _NoopSessionContext(session)
