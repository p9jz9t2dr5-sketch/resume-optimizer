"""汇总 agent_runs / agent_steps，产出可以写进简历的可靠性数字。

用法（在 backend 目录下执行）：

    python scripts/agent_stats.py                 # 打印表格
    python scripts/agent_stats.py --json          # 输出 JSON，便于接 CI 或存档
    python scripts/agent_stats.py --last 20       # 只看最近 20 次任务
    python scripts/agent_stats.py --user <uuid>   # 只看某个用户

注意：它读的是应用配置里的 DATABASE_URL，所以本地要带 ``APP_ENV=local``
（PowerShell：``$env:APP_ENV="local"; python scripts/agent_stats.py``）；
不带的话会去连 docker-compose 里的 Postgres 主机名 ``db``，报 DNS 解析失败。

指标口径（引用这些数字时请连口径一起写，否则会被追问）：

- 成功率 = ``status == succeeded`` 的任务数 / 全部任务数；``failed`` 与仍在
  ``running`` 的都算未成功。
- 工具成功率 = ``agent_steps`` 里 ``kind == "tool"`` 且 ``status == "ok"`` 的条数
  / ``kind == "tool"`` 的总条数。注意：模型调用参数非法、超限被拦下的调用同样计入
  分母（它们确实是失败的调用尝试）。
- 延迟/步数为分位数，样本不足 20 时分位数只能当粗略参考——简历上写数字时把样本量
  一起写上。
"""

import argparse
import asyncio
import json
import math
import os
import sys
import uuid
from collections import Counter, defaultdict

from sqlalchemy import select

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import async_session  # noqa: E402
from app.models.agent import AgentRun, AgentStep  # noqa: E402


def percentile(values: list[float], percent: float) -> float | None:
    """最近秩法（nearest-rank）分位数，样本少时可解释、不插值。"""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(percent / 100 * len(ordered)))
    return ordered[rank - 1]


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 1) if values else None


def _distribution(values: list[float]) -> dict:
    return {
        "mean": _mean(values),
        "p50": percentile(values, 50),
        "p95": percentile(values, 95),
        "max": max(values) if values else None,
        "samples": len(values),
    }


def _normalize_error(text: str | None) -> str:
    """把错误文案收敛成可聚合的类别（去掉具体 id、数字、路径）。"""
    if not text:
        return "未知错误"
    cleaned = " ".join(str(text).split())
    for token in (":", "（", "("):
        if token in cleaned:
            cleaned = cleaned.split(token)[0]
    return cleaned[:80] or "未知错误"


def summarize(runs: list[dict], steps: list[dict]) -> dict:
    """纯函数：把任务与步骤记录聚合成指标（可脱离数据库单测）。"""
    run_count = len(runs)
    by_status = Counter(run.get("status") or "unknown" for run in runs)
    succeeded = by_status.get("succeeded", 0)

    durations = [int(run.get("duration_ms") or 0) for run in runs if run.get("duration_ms")]
    steps_per_run = [int(run.get("steps_count") or 0) for run in runs]
    tools_per_run = [int(run.get("tool_calls") or 0) for run in runs]
    prompt_tokens = sum(int(run.get("prompt_tokens") or 0) for run in runs)
    completion_tokens = sum(int(run.get("completion_tokens") or 0) for run in runs)

    tool_steps = [step for step in steps if step.get("kind") == "tool"]
    tool_ok = [step for step in tool_steps if step.get("status") == "ok"]
    tool_errors = [step for step in tool_steps if step.get("status") != "ok"]

    by_tool: dict[str, dict] = {}
    for name in sorted({str(step.get("tool_name") or "-") for step in tool_steps}):
        calls = [step for step in tool_steps if str(step.get("tool_name") or "-") == name]
        oks = [step for step in calls if step.get("status") == "ok"]
        latencies = [int(step.get("latency_ms") or 0) for step in calls]
        by_tool[name] = {
            "calls": len(calls),
            "errors": len(calls) - len(oks),
            "success_rate": round(len(oks) / len(calls), 3) if calls else None,
            "latency_ms": {
                "mean": _mean(latencies),
                "p50": percentile(latencies, 50),
                "p95": percentile(latencies, 95),
            },
        }

    reason_counter = Counter(
        _normalize_error(step.get("error")) for step in tool_errors if step.get("error")
    )
    run_error_counter = Counter(
        _normalize_error(run.get("error")) for run in runs if run.get("error")
    )

    return {
        "runs": {
            "total": run_count,
            "succeeded": succeeded,
            "success_rate": round(succeeded / run_count, 3) if run_count else None,
            "by_status": dict(by_status),
            "by_stopped_reason": dict(
                Counter(str(run.get("stopped_reason") or "unknown") for run in runs)
            ),
            "duration_ms": _distribution(durations),
            "steps_per_run": _distribution(steps_per_run),
            "tool_calls_per_run": _distribution(tools_per_run),
            "tokens": {
                "prompt_total": prompt_tokens,
                "completion_total": completion_tokens,
                "total": prompt_tokens + completion_tokens,
                "mean_per_run": round((prompt_tokens + completion_tokens) / run_count, 1)
                if run_count
                else None,
            },
        },
        "tools": {
            "total_calls": len(tool_steps),
            "ok": len(tool_ok),
            "errors": len(tool_errors),
            "success_rate": round(len(tool_ok) / len(tool_steps), 3) if tool_steps else None,
            "by_tool": by_tool,
        },
        "errors": {
            "tool_reasons": [
                {"reason": reason, "count": count}
                for reason, count in reason_counter.most_common(10)
            ],
            "run_reasons": [
                {"reason": reason, "count": count}
                for reason, count in run_error_counter.most_common(10)
            ],
        },
    }


async def load(
    last: int | None = None, user_id: uuid.UUID | str | None = None
) -> tuple[list[dict], list[dict]]:
    """从库里读任务与步骤（按时间倒序取最近 last 条）。

    ``user_id`` 允许传字符串（命令行就是这么传的），但必须转成 UUID 再过滤：
    模型里的 id 列是 ``Uuid(as_uuid=True)``，直接拿字符串比较会在执行期抛
    ``StatementError: 'str' object has no attribute 'hex'``。
    """
    if isinstance(user_id, str) and user_id:
        try:
            user_id = uuid.UUID(user_id)
        except ValueError as exc:
            raise ValueError(f"--user 需要合法的 UUID，收到 {user_id!r}") from exc

    async with async_session() as session:
        query = select(AgentRun).order_by(AgentRun.created_at.desc())
        if last:
            query = query.limit(last)
        if user_id:
            query = query.where(AgentRun.user_id == user_id)
        run_rows = list((await session.execute(query)).scalars().all())
        run_ids = [row.id for row in run_rows]

        step_rows = []
        if run_ids:
            step_rows = list(
                (
                    await session.execute(
                        select(AgentStep)
                        .where(AgentStep.run_id.in_(run_ids))
                        .order_by(AgentStep.step_index.asc())
                    )
                ).scalars().all()
            )

    runs = [
        {
            "id": str(row.id),
            "status": row.status,
            "stopped_reason": row.stopped_reason,
            "steps_count": row.steps_count,
            "tool_calls": row.tool_calls,
            "prompt_tokens": row.prompt_tokens,
            "completion_tokens": row.completion_tokens,
            "duration_ms": row.duration_ms,
            "error": row.error,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in run_rows
    ]
    steps = [
        {
            "run_id": str(row.run_id),
            "step_index": row.step_index,
            "kind": row.kind,
            "tool_name": row.tool_name,
            "status": row.status,
            "error": row.error,
            "latency_ms": row.latency_ms,
        }
        for row in step_rows
    ]
    return runs, steps


def render(report: dict) -> str:
    """把指标渲染成便于贴进简历/周报的文本。"""
    runs = report["runs"]
    tools = report["tools"]
    if not runs["total"]:
        return "没有可统计的 Agent 任务记录。"

    lines = [
        f"任务总数：{runs['total']}（成功 {runs['succeeded']}，成功率 {runs['success_rate']:.1%}）",
        f"结束原因：{json.dumps(runs['by_stopped_reason'], ensure_ascii=False)}",
        f"耗时：P50 {runs['duration_ms']['p50']}ms / P95 {runs['duration_ms']['p95']}ms"
        f"（样本 {runs['duration_ms']['samples']}）",
        f"步数：平均 {runs['steps_per_run']['mean']}，工具调用：平均 {runs['tool_calls_per_run']['mean']}",
        f"token：合计 {runs['tokens']['total']}，平均每次 {runs['tokens']['mean_per_run']}",
        "",
        f"工具调用：{tools['total_calls']} 次，成功 {tools['ok']}，失败 {tools['errors']}"
        f"，成功率 {tools['success_rate']:.1%}",
    ]
    for name, stat in tools["by_tool"].items():
        lines.append(
            f"  - {name:<24} {stat['calls']:>3} 次  成功率 {stat['success_rate']:.0%}"
            f"  P50 {stat['latency_ms']['p50']}ms"
        )
    if report["errors"]["tool_reasons"]:
        lines.append("")
        lines.append("工具失败原因 TOP：")
        for item in report["errors"]["tool_reasons"]:
            lines.append(f"  - {item['count']} 次：{item['reason']}")
    if report["errors"]["run_reasons"]:
        lines.append("任务失败原因 TOP：")
        for item in report["errors"]["run_reasons"]:
            lines.append(f"  - {item['count']} 次：{item['reason']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agent 可靠性统计")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    parser.add_argument("--last", type=int, default=None, help="只看最近 N 次任务")
    parser.add_argument("--user", default=None, help="只看某个用户（uuid）")
    args = parser.parse_args(argv)

    runs, steps = asyncio.run(load(last=args.last, user_id=args.user))
    report = summarize(runs, steps)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
