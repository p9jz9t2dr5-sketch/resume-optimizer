"""Agent 层：规划（planner）+ 带工具调用的执行循环（executor）+ 记忆 + 执行轨迹。

对外只暴露两样东西：``AgentRunner``（跑一次任务）与 ``ToolRegistry``（模型能用的工具集）。
具体的一次「简历优化」任务怎么组装、怎么落库、怎么推给前端，在
``app/services/agent_service.py`` 里。
"""

from app.agent.loop import AgentRunner
from app.agent.tools import ToolContext, ToolRegistry, build_registry
from app.agent.types import AgentResult, StepRecord, ToolResult

__all__ = [
    "AgentRunner",
    "ToolContext",
    "ToolRegistry",
    "build_registry",
    "AgentResult",
    "StepRecord",
    "ToolResult",
]
