"""Agent 服务：把一次「Agent 优化简历」任务从建记录、执行、落库到流式输出串起来。

职责边界：

- ``agent/`` 目录里是通用 Agent 机制（循环、工具、记忆、轨迹），不依赖 HTTP
- 这个文件负责把机制接到本项目的业务上：注入简历与 JD、把轨迹写进数据库、
  产出给前端的 SSE 事件、把改写结果合并回简历
- ``app/api/agent.py`` 只做鉴权、参数校验和 SSE 编码

流式与回调的桥接方式：AgentRunner 通过 ``on_event`` 回调推事件，而回调里不能
``yield``，所以这里用 ``asyncio.Queue`` 把回调事件搬进生成器（见 ``_pump``）。
"""

import asyncio
import logging
import time
import uuid
from contextlib import suppress
from typing import Any, AsyncGenerator, Callable

from sqlalchemy import delete, func, select

from app.agent.loop import AgentRunner
from app.agent.memory import KNOWN_KEYS, MemoryStore
from app.agent.prompts import build_executor_system_prompt
from app.agent.tools import ToolContext, build_registry
from app.agent.utils import split_resume_sections
from app.config import get_settings
from app.database import async_session
from app.models.agent import AgentRun, AgentRunStatus, AgentStep
from app.models.resume import Resume
from app.services.llm_service import llm_service
from app.services.resume_service import merge_polish_structured, update_resume_parsed_data

settings = get_settings()
logger = logging.getLogger("uvicorn")

GOAL = "根据目标岗位 JD 优化这份简历，产出可执行的优化报告"
_CONTENT_CHUNK = 240


# ---------------------------------------------------------------- 运行一次任务


async def _create_run(
    *,
    user_id: uuid.UUID,
    resume_id: uuid.UUID,
    jd_text: str,
    model: str,
) -> uuid.UUID:
    async with async_session() as session:
        run = AgentRun(
            user_id=user_id,
            resume_id=resume_id,
            goal=GOAL,
            jd_text=jd_text,
            model=model,
            status=AgentRunStatus.RUNNING,
            plan=[],
        )
        session.add(run)
        await session.commit()
        await session.refresh(run)
        return run.id


async def _persist_step(run_id: uuid.UUID, step: dict) -> None:
    """把一条轨迹实时写库——任务中途失败也留得下已有过程。"""
    async with async_session() as session:
        session.add(
            AgentStep(
                run_id=run_id,
                step_index=int(step.get("index") or 0),
                kind=str(step.get("kind") or "tool"),
                tool_name=step.get("tool"),
                tool_input=step.get("input"),
                tool_output=(step.get("output") if isinstance(step.get("output"), dict) else None),
                status=str(step.get("status") or "ok"),
                error=step.get("error"),
                latency_ms=int(step.get("latency_ms") or 0),
            )
        )
        await session.commit()


async def _finish_run(run_id: uuid.UUID, **values: Any) -> None:
    async with async_session() as session:
        run = await session.get(AgentRun, run_id)
        if run is None:
            return
        for key, value in values.items():
            setattr(run, key, value)
        run.updated_at = func.now()
        await session.commit()


def build_rewritten_draft(resume_text: str, rewrites: dict[str, str]) -> str:
    """把「被改写的版块」替换回原文，拼出一份可直接解析的优化稿。

    只替换命中的版块，其余版块保持原文——这样重新结构化解析出来的简历仍然是
    候选人本人的经历，而不是模型的自由发挥。没有任何版块被改写时返回空串
    （此时不更新简历预览，避免像早期版本那样把「建议报告」当成简历解析）。
    """
    if not rewrites:
        return ""
    sections = split_resume_sections(resume_text)
    if not sections:
        return ""
    parts: list[str] = []
    hit = False
    for name, content in sections.items():
        replacement = rewrites.get(name)
        if replacement:
            hit = True
            parts.append(f"## {name}\n{replacement}")
        else:
            parts.append(f"## {name}\n{content}")
    return "\n\n".join(parts) if hit else ""


def collect_section_rewrites(steps: list[Any]) -> dict[str, str]:
    """从轨迹里收集 ``rewrite_resume_section`` 的产出：``{版块名: 改写稿}``。"""
    rewrites: dict[str, str] = {}
    for step in steps:
        if getattr(step, "kind", None) != "tool" or getattr(step, "tool_name", None) != "rewrite_resume_section":
            continue
        if getattr(step, "status", "") != "ok":
            continue
        output = getattr(step, "tool_output", None)
        if not isinstance(output, dict):
            continue
        section = str(output.get("section") or "").strip()
        rewritten = str(output.get("rewritten") or "").strip()
        if section and rewritten:
            rewrites[section] = rewritten
    return rewrites


async def _persist_artifacts(
    *,
    user_id: uuid.UUID,
    resume_id: uuid.UUID,
    resume_text: str,
    report: str,
    rewrites: dict[str, str],
    client: Any,
    is_premium: bool,
) -> dict | None:
    """把报告与改写稿写回简历，并在有改写稿时重新结构化解析。

    返回合并后的结构化简历（供 SSE 立刻刷新预览）；没有可写内容时返回 None。
    """
    structured: dict | None = None
    draft = build_rewritten_draft(resume_text, rewrites)
    if draft:
        try:
            parsed = await client.parse_resume(draft, is_premium)
        except Exception as exc:  # 解析失败不影响报告与改写稿的保存
            logger.error("agent: re-parse rewritten draft failed => %s: %s", type(exc).__name__, exc)
            parsed = None
        if isinstance(parsed, dict) and parsed:
            try:
                async with async_session() as session:
                    resume = await session.get(Resume, resume_id)
                    if resume is not None and resume.user_id == user_id:
                        old = (resume.parsed_data or {}).get("structured") or {}
                        structured = merge_polish_structured(old, parsed)
                        await update_resume_parsed_data(session, resume_id, user_id, structured)
                        await session.commit()
            except Exception as exc:
                logger.error("agent: persist structured failed => %s: %s", type(exc).__name__, exc)
                structured = None

    try:
        async with async_session() as session:
            resume = await session.get(Resume, resume_id)
            if resume is not None and resume.user_id == user_id:
                parsed_data = dict(resume.parsed_data or {})
                parsed_data["agent_report"] = report
                if rewrites:
                    parsed_data["agent_rewrites"] = rewrites
                resume.parsed_data = parsed_data
                await session.commit()
    except Exception as exc:
        logger.error("agent: persist artifacts failed => %s: %s", type(exc).__name__, exc)
    return structured


def _chunks(text: str, size: int = _CONTENT_CHUNK) -> list[str]:
    """把最终报告切成若干片下发。

    工具调用阶段的模型输出是整块返回的（function calling 与流式混用会显著增加
    出错面），所以报告的「流式」是在这里分片完成，而不是逐 token 从模型流出。
    """
    if not text:
        return []
    return [text[index : index + size] for index in range(0, len(text), size)]


def _degraded_report(result: Any, rewrites: dict[str, str]) -> str:
    """收尾报告没生成出来时的兜底正文。

    真实场景：工具全部跑成功，但最后一步生成长报告时模型超时/报错。这时如果只发一帧
    error，前端会直接弹失败提示、正文一片空白——用户会觉得「点了没反应」。改成给出一段
    结构化说明：失败原因 + 已经完成的步骤 + 已经拿到的改写稿（它们确实写回过简历预览）。
    """
    reason = result.error or "模型未返回报告正文"
    lines = [
        "## 报告正文生成失败",
        "",
        f"- 原因：{reason}",
        f"- 已完成的执行步骤：{len(result.steps)} 步，其中工具调用 {result.tool_calls} 次",
    ]
    if result.plan:
        lines.append("- 原定计划：" + "；".join(str(step.get("intent")) for step in result.plan))
    if rewrites:
        lines.append(f"- 已改写版块：{'、'.join(rewrites)}（已写回简历预览）")
        lines.append("")
        lines.append("### 已拿到的改写稿")
        for name, text in rewrites.items():
            lines.append("")
            lines.append(f"**{name}**")
            lines.append("")
            lines.append(text)
    lines.append("")
    lines.append("- 建议：稍后重试，或暂时关闭「Agent 模式」走快速改写。")
    return "\n".join(lines)


async def stream_optimize_agent(
    *,
    user_id: uuid.UUID,
    resume_id: uuid.UUID,
    resume_text: str,
    jd_text: str,
    is_premium: bool,
    match_report: dict | None = None,
    max_steps: int | None = None,
    llm: Any = None,
    session_factory: Callable = async_session,
) -> AsyncGenerator[dict, None]:
    """跑一次 Agent 任务，按顺序 yield SSE 事件字典。

    事件类型：``run`` / ``plan`` / ``step`` / ``tool_call`` / ``tool_result`` /
    ``replan`` / ``compaction`` / ``thinking`` / ``content`` / ``structured`` /
    ``fallback`` / ``error`` / ``done``。
    其中 ``content`` 与 ``structured`` 沿用旧「一键优化」接口的帧格式，前端可以无缝接。
    """
    client = llm or llm_service
    model = settings.AI_PREMIUM_MODEL if is_premium else settings.AI_FAST_MODEL
    run_id = await _create_run(
        user_id=user_id, resume_id=resume_id, jd_text=jd_text, model=model
    )
    yield {"type": "run", "run_id": str(run_id), "model": model, "goal": GOAL}

    if not settings.AGENT_ENABLED:
        async for event in _fallback_stream(
            run_id=run_id,
            user_id=user_id,
            resume_id=resume_id,
            resume_text=resume_text,
            jd_text=jd_text,
            is_premium=is_premium,
            match_report=match_report,
            client=client,
            reason="AGENT_ENABLED=false",
        ):
            yield event
        return

    registry = build_registry()
    memory = MemoryStore(session_factory)
    memory_text = await memory.render_for_prompt(user_id)
    system_prompt = build_executor_system_prompt(
        tool_menu=registry.menu(),
        resume_text=resume_text,
        jd_text=jd_text,
        match_report_text=(
            f"综合评分 {match_report.get('overall_score')}，"
            f"缺失关键词：{'、'.join(match_report.get('missing_keywords') or [])}"
            if isinstance(match_report, dict) and match_report
            else ""
        ),
        memory_text=memory_text,
    )
    context = ToolContext(
        user_id=user_id,
        llm=client,
        session_factory=session_factory,
        is_premium=is_premium,
        resume_id=resume_id,
        run_id=run_id,
        resume_text=resume_text,
        jd_text=jd_text,
        match_report=match_report,
    )

    queue: "asyncio.Queue[dict]" = asyncio.Queue()

    async def on_event(event: dict) -> None:
        if event.get("type") == "step" and isinstance(event.get("step"), dict):
            try:
                await _persist_step(run_id, event["step"])
            except Exception as exc:  # 落库失败不能中断任务本身
                logger.warning("agent: persist step failed => %s: %s", type(exc).__name__, exc)
        await queue.put(event)

    runner = AgentRunner(
        llm=client,
        registry=registry,
        max_steps=max_steps or settings.AGENT_MAX_STEPS,
        tool_timeout=settings.AGENT_TOOL_TIMEOUT_SECONDS,
        max_same_tool_calls=settings.AGENT_MAX_SAME_TOOL_CALLS,
        token_budget=settings.AGENT_CONTEXT_TOKEN_BUDGET,
        on_event=on_event,
        model_name=model,
    )
    started = time.perf_counter()
    task = asyncio.create_task(
        runner.run(system_prompt=system_prompt, task=GOAL, context=context)
    )

    try:
        async for event in _pump(queue, task):
            yield event
        result = await task
    except GeneratorExit:
        # 客户端断开（关标签页 / 取消请求）时生成器会被关闭：把后台任务一起取消，
        # 否则它会继续跑完剩下的模型调用——用户已经走了，token 还是要付的。
        task.cancel()
        raise
    except Exception as exc:  # noqa: BLE001
        task.cancel()
        logger.error("agent: task crashed => %s: %s", type(exc).__name__, exc)
        await _finish_run(
            run_id,
            status=AgentRunStatus.FAILED,
            stopped_reason="error",
            error=f"{type(exc).__name__}: {exc}",
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        yield {"type": "error", "message": f"{type(exc).__name__}: {exc}", "run_id": str(run_id)}
        return

    # 模型不支持 function calling：降级到旧的一次性改写链路
    if result.stopped_reason == "tool_unsupported":
        async for event in _fallback_stream(
            run_id=run_id,
            user_id=user_id,
            resume_id=resume_id,
            resume_text=resume_text,
            jd_text=jd_text,
            is_premium=is_premium,
            match_report=match_report,
            client=client,
            reason="当前模型不支持工具调用（function calling）",
            result=result,
        ):
            yield event
        return

    rewrites = collect_section_rewrites(result.steps)
    report = result.final_output or ""
    if not report:
        report = _degraded_report(result, rewrites)
    for chunk in _chunks(report):
        yield {"type": "content", "content": chunk}

    structured = await _persist_artifacts(
        user_id=user_id,
        resume_id=resume_id,
        resume_text=resume_text,
        report=report,
        rewrites=rewrites,
        client=client,
        is_premium=is_premium,
    )
    if structured:
        yield {"structured": structured}

    await _finish_run(
        run_id,
        status=(
            AgentRunStatus.SUCCEEDED
            if result.stopped_reason in ("completed", "max_steps")
            else AgentRunStatus.FAILED
        ),
        stopped_reason=result.stopped_reason,
        plan=result.plan,
        steps_count=len(result.steps),
        tool_calls=result.tool_calls,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        duration_ms=result.duration_ms,
        final_output=report,
        error=result.error,
    )
    yield {
        "type": "done",
        "run_id": str(run_id),
        "stopped_reason": result.stopped_reason,
        "steps": len(result.steps),
        "tool_calls": result.tool_calls,
        "duration_ms": result.duration_ms,
        "prompt_tokens": result.prompt_tokens,
        "completion_tokens": result.completion_tokens,
        "rewritten_sections": sorted(rewrites),
    }


async def _pump(queue: "asyncio.Queue[dict]", task: asyncio.Task) -> AsyncGenerator[dict, None]:
    """把回调塞进队列的事件转成生成器输出，直到任务结束且队列排空。"""
    while True:
        if task.done() and queue.empty():
            return
        getter = asyncio.ensure_future(queue.get())
        done, _ = await asyncio.wait({getter, task}, return_when=asyncio.FIRST_COMPLETED)
        if getter in done:
            yield getter.result()
            continue
        getter.cancel()
        with suppress(asyncio.CancelledError, Exception):
            await getter


async def _fallback_stream(
    *,
    run_id: uuid.UUID,
    user_id: uuid.UUID,
    resume_id: uuid.UUID,
    resume_text: str,
    jd_text: str,
    is_premium: bool,
    match_report: dict | None,
    client: Any,
    reason: str,
    result: Any = None,
) -> AsyncGenerator[dict, None]:
    """降级链路：模型不支持工具调用时，退回单次改写（功能降级但可用）。"""
    logger.warning("agent: falling back to single-shot polish (run=%s, reason=%s)", run_id, reason)
    started = time.perf_counter()
    yield {"type": "fallback", "reason": reason, "run_id": str(run_id)}
    try:
        await _persist_step(
            run_id,
            {
                "index": 0,
                "kind": "fallback",
                "status": "ok",
                "tool": None,
                "input": {"reason": reason},
                "latency_ms": 0,
            },
        )
    except Exception as exc:
        logger.warning("agent: persist fallback step failed => %s: %s", type(exc).__name__, exc)

    accumulated: list[str] = []
    try:
        async for chunk in client.polish_stream(
            resume_text, jd_text, match_report, is_premium
        ):
            accumulated.append(chunk)
            yield {"type": "content", "content": chunk}
    except Exception as exc:  # noqa: BLE001
        await _finish_run(
            run_id,
            status=AgentRunStatus.FAILED,
            stopped_reason="error",
            error=f"{type(exc).__name__}: {exc}",
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        yield {"type": "error", "message": f"AI service error: {exc}", "run_id": str(run_id)}
        return

    report = "".join(accumulated)
    structured = await _persist_artifacts(
        user_id=user_id,
        resume_id=resume_id,
        resume_text=resume_text,
        report=report,
        rewrites={},
        client=client,
        is_premium=is_premium,
    )
    if structured:
        yield {"structured": structured}
    await _finish_run(
        run_id,
        status=AgentRunStatus.SUCCEEDED,
        stopped_reason="tool_unsupported",
        steps_count=1,
        tool_calls=0,
        duration_ms=int((time.perf_counter() - started) * 1000),
        final_output=report,
    )
    yield {
        "type": "done",
        "run_id": str(run_id),
        "stopped_reason": "tool_unsupported",
        "fallback": True,
        "steps": 1,
        "tool_calls": 0,
    }


# ---------------------------------------------------------------- 查询与清理


async def list_runs(session: Any, user_id: uuid.UUID, limit: int = 20) -> list[AgentRun]:
    result = await session.execute(
        select(AgentRun)
        .where(AgentRun.user_id == user_id)
        .order_by(AgentRun.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def get_run(session: Any, run_id: uuid.UUID, user_id: uuid.UUID) -> AgentRun | None:
    """按 id + 归属用户取轨迹详情（含 steps）；越权一律当不存在。"""
    result = await session.execute(
        select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == user_id)
    )
    run = result.scalar_one_or_none()
    if run is None:
        return None
    await session.refresh(run, attribute_names=["steps"])
    return run


async def delete_run(session: Any, run_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    result = await session.execute(
        select(AgentRun.id).where(AgentRun.id == run_id, AgentRun.user_id == user_id)
    )
    if result.scalar_one_or_none() is None:
        return False
    # SQLite 默认不启用外键约束，子表要显式删。
    await session.execute(delete(AgentStep).where(AgentStep.run_id == run_id))
    await session.execute(delete(AgentRun).where(AgentRun.id == run_id))
    await session.flush()
    return True


async def delete_all_runs(session: Any, user_id: uuid.UUID) -> int:
    run_ids = select(AgentRun.id).where(AgentRun.user_id == user_id)
    await session.execute(delete(AgentStep).where(AgentStep.run_id.in_(run_ids)))
    result = await session.execute(delete(AgentRun).where(AgentRun.user_id == user_id))
    await session.flush()
    return result.rowcount or 0


__all__ = [
    "GOAL",
    "KNOWN_KEYS",
    "build_rewritten_draft",
    "collect_section_rewrites",
    "delete_all_runs",
    "delete_run",
    "get_run",
    "list_runs",
    "stream_optimize_agent",
]
