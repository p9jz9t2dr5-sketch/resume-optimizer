"""Agent 层的内部数据结构（与 HTTP / ORM 解耦，方便单测直接构造）。"""

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


@dataclass
class ToolResult:
    """一次工具调用的结果。

    ``data`` 是给模型看的结构化结果，``summary`` 是给人看的短句（前端轨迹面板、
    日志、SSE 事件都用它，不必把整块 JSON 塞进 UI）。
    """

    ok: bool
    summary: str
    data: dict | None = None
    error: str | None = None
    tokens: int = 0

    def to_observation(self, limit: int = 6000) -> str:
        """转成回灌给模型的 observation 文本（超长则截断，避免把上下文撑爆）。"""
        import json

        payload: dict[str, Any] = {"ok": self.ok, "summary": self.summary}
        if self.data:
            payload["data"] = self.data
        if self.error:
            payload["error"] = self.error
        text = json.dumps(payload, ensure_ascii=False, default=str)
        if len(text) <= limit:
            return text
        return text[:limit] + f'...（结果过长已截断，原长度 {len(text)} 字符）'


@dataclass
class StepRecord:
    """落库到 agent_steps 的一条轨迹。"""

    step_index: int
    kind: str  # plan / tool / replan / compaction / final / error
    tool_name: str | None = None
    tool_input: dict | None = None
    tool_output: dict | None = None
    status: str = "ok"  # ok / error
    error: str | None = None
    latency_ms: int = 0
    tokens: int = 0


@dataclass
class AgentResult:
    """跑完一次 Agent 任务的全部产出。"""

    final_output: str = ""
    plan: list[dict] = field(default_factory=list)
    steps: list[StepRecord] = field(default_factory=list)
    tool_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    duration_ms: int = 0
    # completed（模型自己收尾）/ max_steps（用尽步数后强制收尾）/
    # tool_unsupported（模型不支持工具，需降级）/ error（异常终止）
    stopped_reason: str = "completed"
    model: str = ""
    error: str | None = None


# SSE / 落库事件回调（由 agent_service 提供，实现「边跑边推」）
EventCallback = Callable[[dict], Awaitable[None]]
