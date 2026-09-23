"""agent_stats 的聚合口径必须可回归：成功率先算对，简历上的数字才不会错。"""

import asyncio
import os
import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.agent import AgentRun, AgentStep
from app.models.user import User
from scripts.agent_stats import load, summarize


def _seed() -> uuid.UUID:
    """写入 3 次任务（2 成功 1 失败）+ 4 条工具轨迹，返回用户 id。"""

    async def run() -> uuid.UUID:
        engine = create_async_engine(os.environ["DATABASE_URL"])
        factory = async_sessionmaker(engine, expire_on_commit=False)
        user_id = uuid.uuid4()
        try:
            async with factory() as session:
                session.add(
                    User(
                        id=user_id,
                        email=f"stats-{uuid.uuid4().hex[:10]}@example.com",
                        hashed_password="x",
                    )
                )
                await session.flush()

                specs = [
                    ("succeeded", "completed", 3200, 12_000, 3_000),
                    ("succeeded", "completed", 4100, 13_000, 3_500),
                    ("failed", "error", 9_000, 11_000, 500),
                ]
                for status, reason, duration, prompt, completion in specs:
                    agent_run = AgentRun(
                        user_id=user_id,
                        status=status,
                        stopped_reason=reason,
                        steps_count=4,
                        tool_calls=3,
                        prompt_tokens=prompt,
                        completion_tokens=completion,
                        duration_ms=duration,
                        plan=[],
                        error="APITimeoutError: Request timed out" if status == "failed" else None,
                    )
                    session.add(agent_run)
                    await session.flush()
                    session.add_all(
                        [
                            AgentStep(
                                run_id=agent_run.id,
                                step_index=0,
                                kind="plan",
                                status="ok",
                            ),
                            AgentStep(
                                run_id=agent_run.id,
                                step_index=1,
                                kind="tool",
                                tool_name="check_keywords",
                                status="ok",
                                latency_ms=2,
                            ),
                            AgentStep(
                                run_id=agent_run.id,
                                step_index=2,
                                kind="tool",
                                tool_name="score_resume_match",
                                status="ok" if status == "succeeded" else "error",
                                error=None if status == "succeeded" else "工具 score_resume_match 超时",
                                latency_ms=3000,
                            ),
                        ]
                    )
                await session.commit()
        finally:
            await engine.dispose()
        return user_id

    return asyncio.run(run())


def test_stats_aggregate_a_known_batch():
    user_id = _seed()
    # 传字符串也要能用（命令行就是这么传的），脚本内部会转成 UUID
    runs, steps = asyncio.run(load(user_id=str(user_id)))
    report = summarize(runs, steps)

    assert report["runs"]["total"] == 3
    assert report["runs"]["succeeded"] == 2
    assert report["runs"]["success_rate"] == 0.667
    assert report["runs"]["by_stopped_reason"] == {"completed": 2, "error": 1}
    assert report["runs"]["duration_ms"]["p50"] == 4100  # 最近秩法：3200/4100/9000 → 第 2 个
    assert report["runs"]["duration_ms"]["p95"] == 9000
    assert report["runs"]["tokens"]["total"] == 12_000 + 3_000 + 13_000 + 3_500 + 11_000 + 500
    assert report["runs"]["steps_per_run"]["mean"] == 4.0

    tools = report["tools"]
    assert tools["total_calls"] == 6  # 3 次任务 × 2 条工具轨迹
    assert tools["ok"] == 5
    assert tools["errors"] == 1
    assert tools["success_rate"] == 0.833
    assert tools["by_tool"]["check_keywords"]["success_rate"] == 1.0
    assert tools["by_tool"]["score_resume_match"]["errors"] == 1
    assert tools["by_tool"]["score_resume_match"]["latency_ms"]["p50"] == 3000

    # 失败原因被归成一类，便于统计 TOP 原因
    assert report["errors"]["tool_reasons"] == [
        {"reason": "工具 score_resume_match 超时", "count": 1}
    ]
    assert report["errors"]["run_reasons"][0]["reason"].startswith("APITimeoutError")


def test_stats_handle_empty_database_shape():
    report = summarize([], [])
    assert report["runs"]["total"] == 0
    assert report["runs"]["success_rate"] is None
    assert report["tools"]["success_rate"] is None
    assert report["tools"]["by_tool"] == {}


def test_stats_reject_a_malformed_user_id():
    import pytest

    with pytest.raises(ValueError, match="合法的 UUID"):
        asyncio.run(load(user_id="not-a-uuid"))
