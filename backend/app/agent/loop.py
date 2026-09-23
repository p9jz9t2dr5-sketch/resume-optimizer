"""Agent 执行循环：规划（plan）→ 带工具执行（execute）→ 压缩/重规划 → 收尾。

为什么不用「一次 prompt 加几个工具描述」而要写成循环？因为一次模型调用无法
处理「先看清现状、再决定改哪里、改完再验证」这类依赖链。循环带来的四件必须
自己兜住的事，也就是这个文件的主要内容：

1. **终止**：模型返回 tool_calls 就继续，返回纯文本就结束；另有步数上限兜底。
2. **失败**：单个工具失败变成一条错误观察值回灌给模型；连续失败则触发重规划。
3. **上下文**：消息数增长会烧钱也会撞上下文窗口，超预算就把早期步骤摘要掉。
4. **可观测**：每一步（规划/工具/压缩/重规划/收尾）都产出 StepRecord，
   由上层落库并在 SSE 里实时推给前端——出了问题能复现是 Agent 和玩具的分水岭。

模型不支持 function calling 时抛 ``ToolCallingUnsupported``，上层据此降级到
旧的单次改写链路，而不是把 500 甩给用户。
"""

import json
import logging
import time
from typing import Any

from app.agent.prompts import (
    COMPACTION_SYSTEM_PROMPT,
    FORCE_FINAL_HINT,
    PLANNER_SYSTEM_PROMPT,
    REPLAN_HINT,
)
from app.agent.tools import ToolContext, ToolRegistry
from app.agent.types import AgentResult, EventCallback, StepRecord
from app.agent.utils import estimate_tokens, loads_json_loose, truncate
from app.services.llm_service import ToolCallingUnsupported

logger = logging.getLogger("uvicorn")

# 规划失败时的兜底计划：保证「工具调用不灵」也不会让任务直接瘫掉。
DEFAULT_PLAN: list[dict] = [
    {"intent": "检查简历的版块结构与关键词覆盖情况", "tool": "list_resume_sections"},
    {"intent": "评估简历与目标岗位的匹配度，找出关键差距", "tool": "score_resume_match"},
    {"intent": "检索简历写法知识库，确定改写策略", "tool": "search_knowledge"},
    {"intent": "改写最需要改进的版块", "tool": "rewrite_resume_section"},
    {"intent": "汇总成最终优化报告", "tool": None},
]

_KEEP_LAST_MESSAGES = 4
_MAX_PLAN_STEPS = 6
# 单条轨迹输出在推给前端/落库前的上限。工具结果本身已经截断过一次，这里再兜一道，
# 避免某个工具输出把 SSE 帧撑到几百 KB。
_STEP_PAYLOAD_LIMIT = 4000


def _cap_payload(payload: Any) -> Any:
    """超长轨迹输出降级成「预览 + 长度」，保证轨迹可读但不撑爆传输。"""
    if payload is None:
        return None
    text = json.dumps(payload, ensure_ascii=False, default=str)
    if len(text) <= _STEP_PAYLOAD_LIMIT:
        return payload
    return {"truncated": True, "chars": len(text), "preview": text[:_STEP_PAYLOAD_LIMIT]}


class AgentRunner:
    """一次 Agent 任务的执行器（无状态，可复用；每次 run 自己开一份轨迹）。"""

    def __init__(
        self,
        *,
        llm: Any,
        registry: ToolRegistry,
        max_steps: int = 8,
        tool_timeout: float = 60.0,
        max_same_tool_calls: int = 3,
        token_budget: int = 8000,
        on_event: EventCallback | None = None,
        model_name: str = "",
    ):
        self.llm = llm
        self.registry = registry
        self.max_steps = max(1, int(max_steps))
        self.tool_timeout = float(tool_timeout)
        self.max_same_tool_calls = max(1, int(max_same_tool_calls))
        self.token_budget = max(1000, int(token_budget))
        self.on_event = on_event
        self.model_name = model_name

        # 每次 run 重置
        self._steps: list[StepRecord] = []
        self._cursor = 0
        self._tool_counts: dict[str, int] = {}
        self._consecutive_failures = 0
        self._failure_notes: list[str] = []
        self._prompt_tokens = 0
        self._completion_tokens = 0

    # ------------------------------------------------------------ 主流程

    async def run(self, *, system_prompt: str, task: str, context: ToolContext) -> AgentResult:
        started = time.perf_counter()
        self._steps = []
        self._cursor = 0
        self._tool_counts = {}
        self._consecutive_failures = 0
        self._failure_notes = []
        self._prompt_tokens = 0
        self._completion_tokens = 0

        result = AgentResult(model=self.model_name)
        stopped_reason = "completed"
        final_text = ""

        try:
            # ① 规划：先产出计划（也作为上下文的一部分回灌给执行阶段）
            plan = await self._make_plan(system_prompt=system_prompt, task=task)
            result.plan = plan
            await self._emit({
                "type": "plan",
                "plan": plan,
                "intents": [step.get("intent") for step in plan],
            })
            await self._record(
                kind="plan",
                tool_output={"plan": plan},
            )

            messages: list[dict] = [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": f"{task}\n\n=== 你的执行计划（来自规划器，可按实际情况调整）===\n{self._render_plan(plan)}",
                },
            ]

            # ② 执行：每一轮要么调工具，要么给最终答案
            for _ in range(self.max_steps):
                reply = await self.llm.complete_with_tools(
                    messages,
                    self.registry.schemas(),
                    is_premium=context.is_premium,
                    temperature=0.2,
                    max_tokens=3000,
                )
                self._add_usage(reply)

                if not reply.tool_calls:
                    final_text = (reply.content or "").strip()
                    stopped_reason = "completed"
                    break

                messages.append(self._assistant_message(reply))
                if reply.content and reply.content.strip():
                    await self._emit({"type": "thinking", "content": reply.content.strip()})

                for call in reply.tool_calls:
                    observation = await self._execute_tool(call, context)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": call.get("id") or call.get("name", ""),
                        "content": observation,
                    })

                if self._consecutive_failures >= 2:
                    hint = REPLAN_HINT.format(
                        failure_count=self._consecutive_failures,
                        failures="\n".join(f"- {note}" for note in self._failure_notes[-3:]),
                    )
                    messages.append({"role": "user", "content": hint})
                    await self._record(
                        kind="replan",
                        tool_output={"failures": self._failure_notes[-3:]},
                        status="error",
                        error="consecutive tool failures",
                    )
                    await self._emit({
                        "type": "replan",
                        "reason": f"连续 {self._consecutive_failures} 次工具调用失败，已要求模型调整方案",
                    })
                    self._consecutive_failures = 0
                    self._failure_notes = []

                messages = await self._maybe_compact(messages)
            else:
                stopped_reason = "max_steps"
                final_text = await self._force_final(messages, context)

            if not final_text:
                # 循环正常结束但模型没给正文（例如只回了空白），再要一次。
                final_text = await self._force_final(messages, context)

        except ToolCallingUnsupported as exc:
            logger.warning("agent: model does not support tool calling => %s", exc)
            result.stopped_reason = "tool_unsupported"
            result.error = str(exc)
            result.steps = list(self._steps)
            result.duration_ms = int((time.perf_counter() - started) * 1000)
            self._sync_usage(result)
            return result
        except Exception as exc:  # noqa: BLE001 — 任何异常都要变成可读结果
            logger.error("agent: run failed => %s: %s", type(exc).__name__, exc)
            result.stopped_reason = "error"
            result.error = f"{type(exc).__name__}: {exc}"
            await self._record(kind="error", status="error", error=result.error)
            await self._emit({"type": "error", "message": result.error})
            result.steps = list(self._steps)
            result.duration_ms = int((time.perf_counter() - started) * 1000)
            self._sync_usage(result)
            return result

        result.final_output = final_text
        result.stopped_reason = stopped_reason
        await self._record(
            kind="final",
            tool_output={
                "chars": len(final_text),
                "preview": truncate(final_text, 300),
                "stopped_reason": stopped_reason,
            },
        )
        result.steps = list(self._steps)
        result.duration_ms = int((time.perf_counter() - started) * 1000)
        self._sync_usage(result)
        await self._emit({
            "type": "final",
            "content": final_text,
            "stopped_reason": stopped_reason,
            "steps": len(self._steps),
            "duration_ms": result.duration_ms,
        })
        return result

    # ------------------------------------------------------------ 规划

    async def _make_plan(self, *, system_prompt: str, task: str) -> list[dict]:
        """让模型先出计划；失败就用兜底计划，绝不让规划拖垮执行。"""
        try:
            reply = await self.llm.complete(
                [
                    {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"目标：{truncate(task, 1500)}\n\n"
                            f"可用工具：\n{self.registry.menu()}\n\n请输出 JSON 计划。"
                        ),
                    },
                ],
                is_premium=False,
                temperature=0.2,
                max_tokens=800,
                response_format={"type": "json_object"},
            )
            self._add_usage(reply)
            data = loads_json_loose(reply.content) or {}
            plan = self._normalize_plan(data.get("steps"))
            if plan:
                return plan
        except Exception as exc:  # noqa: BLE001 — 规划是增强项，不是必需项
            logger.warning("agent: planner failed, falling back => %s: %s", type(exc).__name__, exc)
        return [dict(step) for step in DEFAULT_PLAN]

    def _normalize_plan(self, raw: Any) -> list[dict]:
        """收敛规划输出：只保留已知工具、限制步数、去掉空步骤。"""
        if not isinstance(raw, list):
            return []
        plan: list[dict] = []
        for item in raw[:_MAX_PLAN_STEPS]:
            if isinstance(item, str):
                intent, tool = item.strip(), None
            elif isinstance(item, dict):
                intent = str(item.get("intent") or item.get("step") or "").strip()
                tool = item.get("tool")
            else:
                continue
            if not intent:
                continue
            tool_name = str(tool).strip() if tool else None
            if tool_name not in self.registry:
                # 规划器偶尔会臆造工具名：直接降级为 null，而不是让它执行时报错。
                tool_name = None
            plan.append({"intent": intent[:200], "tool": tool_name})
        return plan

    @staticmethod
    def _render_plan(plan: list[dict]) -> str:
        lines = []
        for index, step in enumerate(plan, start=1):
            tool = step.get("tool")
            lines.append(f"{index}. {step.get('intent')}" + (f"（建议工具：{tool}）" if tool else ""))
        return "\n".join(lines) or "（无计划）"

    # ------------------------------------------------------------ 工具执行

    async def _execute_tool(self, call: dict, context: ToolContext) -> str:
        """执行一次工具调用，返回回灌给模型的 observation。"""
        name = str(call.get("name") or "").strip()
        raw_args = call.get("arguments")
        call_id = call.get("id") or name

        await self._emit({"type": "tool_call", "tool": name, "input": self._safe_args(raw_args)})

        args: dict | None = None
        if raw_args:
            parsed = loads_json_loose(raw_args) if isinstance(raw_args, str) else raw_args
            if not isinstance(parsed, dict):
                return await self._tool_failed(
                    name, call_id,
                    summary=f"工具 {name} 的参数不是合法 JSON 对象，请按 schema 重新调用",
                    error="invalid tool arguments",
                    args={"raw": truncate(str(raw_args), 300)},
                )
            args = parsed

        # 同一个工具被反复调用通常意味着模型在原地打转——超限就直接拦掉。
        self._tool_counts[name] = self._tool_counts.get(name, 0) + 1
        if self._tool_counts[name] > self.max_same_tool_calls:
            return await self._tool_failed(
                name, call_id,
                summary=(
                    f"工具 {name} 本次任务已调用 {self.max_same_tool_calls} 次（上限）。"
                    "请改用其它工具，或基于现有信息直接给出结论。"
                ),
                error="tool call limit reached",
                args=args,
            )

        started = time.perf_counter()
        result = await self.registry.execute(name, args, context, timeout=self.tool_timeout)
        latency_ms = int((time.perf_counter() - started) * 1000)

        await self._record(
            kind="tool",
            tool_name=name,
            tool_input=args or {},
            tool_output=(result.data if result.data is not None else {"summary": result.summary}),
            status="ok" if result.ok else "error",
            error=result.error,
            latency_ms=latency_ms,
            tokens=result.tokens,
        )
        await self._emit({
            "type": "tool_result",
            "tool": name,
            "ok": result.ok,
            "summary": result.summary,
            "latency_ms": latency_ms,
        })

        if result.ok:
            self._consecutive_failures = 0
        else:
            self._consecutive_failures += 1
            self._failure_notes.append(f"{name}: {result.summary}")

        return result.to_observation()

    async def _tool_failed(
        self, name: str, call_id: str, *, summary: str, error: str, args: dict | None
    ) -> str:
        """工具没真正执行就失败（参数非法、超出调用上限）时的统一处理。"""
        self._consecutive_failures += 1
        self._failure_notes.append(f"{name}: {summary}")
        await self._record(
            kind="tool",
            tool_name=name,
            tool_input=args or {},
            tool_output={"error_code": error, "summary": summary},
            status="error",
            # error 列给人和前端看，所以存中文说明；机器可读的错误码留在 tool_output 里。
            error=summary,
        )
        await self._emit({
            "type": "tool_result",
            "tool": name,
            "ok": False,
            "summary": summary,
            "latency_ms": 0,
        })
        return json.dumps({"ok": False, "error": error, "summary": summary}, ensure_ascii=False)

    @staticmethod
    def _safe_args(raw_args: Any) -> dict:
        """给 SSE 用的参数预览（解析失败就原样截断，避免把大 JSON 推给前端）。"""
        if isinstance(raw_args, dict):
            parsed = raw_args
        else:
            parsed = loads_json_loose(raw_args) if isinstance(raw_args, str) else None
        if isinstance(parsed, dict):
            return {key: truncate(str(value), 200) for key, value in list(parsed.items())[:8]}
        return {"raw": truncate(str(raw_args or ""), 200)}

    @staticmethod
    def _assistant_message(reply: Any) -> dict:
        """把模型回复拼回 OpenAI 的 assistant 消息格式（工具调用必须原样带回）。"""
        return {
            "role": "assistant",
            "content": reply.content or "",
            "tool_calls": [
                {
                    "id": call.get("id") or call.get("name", ""),
                    "type": "function",
                    "function": {
                        "name": call.get("name", ""),
                        "arguments": call.get("arguments") or "{}",
                    },
                }
                for call in (reply.tool_calls or [])
            ],
        }

    # ------------------------------------------------------------ 上下文压缩

    def _context_tokens(self, messages: list[dict]) -> int:
        return sum(
            estimate_tokens(json.dumps(message, ensure_ascii=False, default=str))
            for message in messages
        )

    async def _maybe_compact(self, messages: list[dict]) -> list[dict]:
        """上下文超预算时压缩：保留 system + 最近几轮，中间摘要成一段。"""
        if self._context_tokens(messages) <= self.token_budget:
            return messages

        # 切点只能落在 assistant 消息上：否则被保留的 tool 消息会失去它对应的
        # tool_calls 声明，下一次模型调用会被接口直接判为非法请求。
        candidates = [
            index
            for index, message in enumerate(messages)
            if index >= 1 and message.get("role") == "assistant"
        ]
        if not candidates:
            return messages

        # 优先保留最近 _KEEP_LAST_MESSAGES 条；如果这一段本身就把预算吃掉大半，
        # 就把切点继续往后挪，直到保留段装得下（实在装不下就保留最少的一段）。
        target = max(1, len(messages) - _KEEP_LAST_MESSAGES)
        tail_budget = max(400, int(self.token_budget * 0.7))
        start = candidates[-1]
        for candidate in candidates:
            if candidate < target:
                continue
            if self._context_tokens(messages[candidate:]) <= tail_budget:
                start = candidate
                break
        if start <= 1:
            return messages

        head, middle, tail = messages[:1], messages[1:start], messages[start:]
        if not middle:
            return messages
        summary = await self._summarize(middle)
        compacted = head + [
            {
                "role": "assistant",
                "content": f"[上下文已压缩] 前面 {len(middle)} 条步骤记录摘要如下：\n{summary}",
            }
        ] + tail

        await self._record(
            kind="compaction",
            tool_output={
                "messages_before": len(messages),
                "messages_after": len(compacted),
                "summary_chars": len(summary),
            },
        )
        await self._emit({
            "type": "compaction",
            "messages_before": len(messages),
            "messages_after": len(compacted),
        })
        return compacted

    async def _summarize(self, messages: list[dict]) -> str:
        """用模型摘要；模型不可用就退化成截断（宁可丢细节也不能丢流程）。"""
        transcript = "\n".join(
            f"{message.get('role')}: {truncate(str(message.get('content') or ''), 1200)}"
            for message in messages
        )
        try:
            reply = await self.llm.complete(
                [
                    {"role": "system", "content": COMPACTION_SYSTEM_PROMPT},
                    {"role": "user", "content": truncate(transcript, 12000)},
                ],
                is_premium=False,
                temperature=0.0,
                max_tokens=400,
            )
            self._add_usage(reply)
            if (reply.content or "").strip():
                return reply.content.strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("agent: compaction summarize failed => %s: %s", type(exc).__name__, exc)
        return "\n".join(
            f"{message.get('role')}: {truncate(str(message.get('content') or ''), 200)}"
            for message in messages
        )

    # ------------------------------------------------------------ 收尾

    async def _force_final(self, messages: list[dict], context: ToolContext) -> str:
        """步数用尽或模型没给正文时的兜底：禁止再调工具，只要报告正文。"""
        try:
            reply = await self.llm.complete(
                list(messages) + [{"role": "user", "content": FORCE_FINAL_HINT}],
                is_premium=context.is_premium,
                temperature=0.3,
                max_tokens=3000,
            )
            self._add_usage(reply)
            return (reply.content or "").strip()
        except Exception as exc:  # noqa: BLE001
            logger.error("agent: force final failed => %s: %s", type(exc).__name__, exc)
            return ""

    # ------------------------------------------------------------ 辅助

    async def _record(self, **kwargs: Any) -> None:
        """记一条轨迹，并把这条轨迹实时推给上层（用于落库 + SSE 展示）。"""
        kwargs.setdefault("kind", "tool")
        record = StepRecord(step_index=self._cursor, **kwargs)
        self._steps.append(record)
        self._cursor += 1
        await self._emit({
            "type": "step",
            "step": {
                "index": record.step_index,
                "kind": record.kind,
                "tool": record.tool_name,
                "input": record.tool_input,
                "output": _cap_payload(record.tool_output),
                "status": record.status,
                "error": record.error,
                "latency_ms": record.latency_ms,
            },
        })

    async def _emit(self, event: dict) -> None:
        if self.on_event is None:
            return
        try:
            await self.on_event(event)
        except Exception as exc:  # 前端/落库出问题不应该中断 Agent 本身
            logger.warning("agent: event callback failed => %s: %s", type(exc).__name__, exc)

    def _add_usage(self, reply: Any) -> None:
        self._prompt_tokens += int(getattr(reply, "prompt_tokens", 0) or 0)
        self._completion_tokens += int(getattr(reply, "completion_tokens", 0) or 0)

    def _sync_usage(self, result: AgentResult) -> None:
        result.prompt_tokens = self._prompt_tokens
        result.completion_tokens = self._completion_tokens
        result.tool_calls = sum(1 for step in self._steps if step.kind == "tool")
