"""Agent 执行循环的测试：规划、工具调用、失败重试、重规划、步数上限、上下文压缩、降级。

全部对着 ``FakeLLM`` 跑，不联网、不花额度，但覆盖的正是线上最容易出问题的几条路径。
"""

import asyncio
import json
import uuid

from agent_fakes import SAMPLE_RESUME, FakeLLM, text_reply, tool_reply
from app.agent.loop import DEFAULT_PLAN, AgentRunner
from app.agent.tools import ToolContext, ToolRegistry, ToolSpec, build_registry
from app.agent.types import ToolResult
from app.database import async_session

SYSTEM_PROMPT = "你是一名简历优化 Agent（测试用）。"


def run(coro):
    return asyncio.run(coro)


def make_context(llm) -> ToolContext:
    return ToolContext(
        user_id=uuid.uuid4(),
        llm=llm,
        session_factory=async_session,
        resume_text=SAMPLE_RESUME,
        jd_text="AI 应用开发实习生：Python、Agent、RAG、Function Calling",
    )


def make_runner(llm, **overrides):
    options = {
        "llm": llm,
        "registry": build_registry(),
        "max_steps": 6,
        "tool_timeout": 30.0,
        "max_same_tool_calls": 3,
        "token_budget": 100000,
        "model_name": "fake-model",
    }
    options.update(overrides)
    return AgentRunner(**options)


def assert_tool_pairing(messages: list[dict]) -> None:
    """每条 tool 消息都必须能找到对应的 assistant tool_calls（否则接口会拒请求）。"""
    pending: set[str] = set()
    for message in messages:
        if message.get("role") == "assistant":
            for call in message.get("tool_calls") or []:
                pending.add(call["id"])
        elif message.get("role") == "tool":
            assert message["tool_call_id"] in pending, f"孤立 tool 消息: {message['tool_call_id']}"


def test_happy_path_plans_calls_tools_then_answers():
    llm = FakeLLM(
        replies=[
            tool_reply("list_resume_sections", {}),
            tool_reply("check_keywords", {"text": SAMPLE_RESUME, "keywords": ["Python", "Kubernetes"]}),
        ],
        final_text="## 报告\n\n匹配度一般。",
    )
    runner = make_runner(llm)
    result = run(runner.run(system_prompt=SYSTEM_PROMPT, task="优化简历", context=make_context(llm)))

    assert result.stopped_reason == "completed"
    assert result.final_output.startswith("## 报告")
    assert result.tool_calls == 2
    assert [step.kind for step in result.steps] == ["plan", "tool", "tool", "final"]
    assert [step.tool_name for step in result.steps if step.kind == "tool"] == [
        "list_resume_sections",
        "check_keywords",
    ]
    assert result.plan[0]["intent"] == "读简历结构"
    assert result.prompt_tokens > 0 and result.completion_tokens > 0
    assert result.model == "fake-model"
    # 工具结果确实以 tool 消息回灌给了模型（而不是只存在本地轨迹里）
    tool_messages = [m for m in llm.messages_seen[-1] if m.get("role") == "tool"]
    assert len(tool_messages) == 2
    assert "coverage" in tool_messages[-1]["content"]


def test_events_stream_in_expected_order():
    events: list[dict] = []

    async def collect(event: dict) -> None:
        events.append(event)

    llm = FakeLLM(replies=[tool_reply("list_resume_sections", {})], final_text="完成")
    runner = make_runner(llm, on_event=collect)
    run(runner.run(system_prompt=SYSTEM_PROMPT, task="优化", context=make_context(llm)))

    types = [event["type"] for event in events]
    assert types[0] == "plan"
    assert "tool_call" in types and "tool_result" in types
    assert types[-1] == "final"
    assert "step" in types
    # plan 事件必须带计划内容，前端才能立刻画出步骤条
    assert events[0]["plan"][0]["intent"] == "读简历结构"
    step_events = [event for event in events if event["type"] == "step"]
    assert [event["step"]["kind"] for event in step_events] == ["plan", "tool", "final"]


def test_unknown_tool_becomes_an_error_step_and_run_continues():
    llm = FakeLLM(
        replies=[
            tool_reply("does_not_exist", {"foo": "bar"}),
            tool_reply("list_resume_sections", {}),
        ],
        final_text="补救后的报告",
    )
    result = run(make_runner(llm).run(system_prompt=SYSTEM_PROMPT, task="优化", context=make_context(llm)))

    tool_steps = [step for step in result.steps if step.kind == "tool"]
    assert tool_steps[0].status == "error"
    assert "未知工具" in (tool_steps[0].error or "")
    assert tool_steps[1].status == "ok"
    assert result.stopped_reason == "completed"
    assert result.final_output == "补救后的报告"


def test_invalid_json_arguments_are_rejected_before_execution():
    bad = text_reply('{"tool_calls": []}')
    bad.tool_calls = [{"id": "call_1", "name": "check_keywords", "arguments": "{不是 JSON"}]
    llm = FakeLLM(replies=[bad], final_text="改用文字总结")
    result = run(make_runner(llm).run(system_prompt=SYSTEM_PROMPT, task="优化", context=make_context(llm)))

    tool_step = next(step for step in result.steps if step.kind == "tool")
    assert tool_step.status == "error"
    assert "合法 JSON" in (tool_step.error or "")


def test_repeated_tool_calls_are_capped():
    llm = FakeLLM(
        replies=[tool_reply("list_resume_sections", {}) for _ in range(5)],
        final_text="最后收尾",
    )
    events: list[dict] = []

    async def collect(event: dict) -> None:
        events.append(event)

    result = run(
        make_runner(llm, max_same_tool_calls=2, on_event=collect).run(
            system_prompt=SYSTEM_PROMPT, task="优化", context=make_context(llm)
        )
    )

    tool_outputs = [event["summary"] for event in events if event["type"] == "tool_result"]
    assert any("上限" in summary for summary in tool_outputs)
    # 被拦下来的调用不会真的执行工具，因此轨迹里只有前两次是 ok
    tool_steps = [step for step in result.steps if step.kind == "tool"]
    assert [step.status for step in tool_steps[:3]] == ["ok", "ok", "error"]


def test_two_consecutive_failures_trigger_a_replan_step():
    llm = FakeLLM(
        replies=[
            tool_reply("does_not_exist", {}),
            tool_reply("also_missing", {}),
            tool_reply("check_keywords", {"text": SAMPLE_RESUME, "keywords": ["Python"]}),
        ],
        final_text="重规划后的报告",
    )
    events: list[dict] = []

    async def collect(event: dict) -> None:
        events.append(event)

    result = run(
        make_runner(llm, on_event=collect).run(
            system_prompt=SYSTEM_PROMPT, task="优化", context=make_context(llm)
        )
    )
    assert any(step.kind == "replan" for step in result.steps)
    assert any(event["type"] == "replan" for event in events)
    assert result.final_output == "重规划后的报告"


def test_max_steps_forces_a_final_answer():
    llm = FakeLLM(
        replies=[tool_reply("list_resume_sections", {}) for _ in range(5)],
        final_text="步数用尽后的报告",
    )
    result = run(
        make_runner(llm, max_steps=2, max_same_tool_calls=5).run(
            system_prompt=SYSTEM_PROMPT, task="优化", context=make_context(llm)
        )
    )
    assert result.stopped_reason == "max_steps"
    assert result.final_output == "步数用尽后的报告"
    assert llm.force_final_calls == 1


def test_planner_failure_falls_back_to_default_plan():
    llm = FakeLLM(planner_raises=True, final_text="没有规划也要能跑完")
    result = run(make_runner(llm).run(system_prompt=SYSTEM_PROMPT, task="优化", context=make_context(llm)))

    assert result.plan == DEFAULT_PLAN
    assert result.final_output == "没有规划也要能跑完"


def test_planner_inventing_tool_names_is_normalized():
    llm = FakeLLM(
        plan={"steps": [{"intent": "用不存在的工具", "tool": "magic_tool"}, {"intent": "出结论"}]},
        final_text="ok",
    )
    result = run(make_runner(llm).run(system_prompt=SYSTEM_PROMPT, task="优化", context=make_context(llm)))
    assert result.plan[0]["tool"] is None
    assert result.plan[1]["tool"] is None


def test_tool_unsupported_is_reported_for_fallback():
    llm = FakeLLM(raise_tool_unsupported=True)
    result = run(make_runner(llm).run(system_prompt=SYSTEM_PROMPT, task="优化", context=make_context(llm)))
    assert result.stopped_reason == "tool_unsupported"
    assert "tools" in (result.error or "")
    assert result.final_output == ""


def test_context_compaction_keeps_tool_pairing_valid():
    # 让工具吐回一大段文本，把小预算的上下文顶爆
    big = "X" * 4000

    async def chatty(ctx, **kwargs):
        return ToolResult(ok=True, summary="一大堆内容", data={"blob": big})

    registry = ToolRegistry([
        ToolSpec(
            name="chatty",
            description="返回大段文本",
            parameters={"type": "object", "properties": {}},
            handler=chatty,
        )
    ])
    llm = FakeLLM(
        replies=[tool_reply("chatty", {}) for _ in range(3)],
        final_text="压缩之后的报告",
        compact_text="已完成 3 次检索，缺失关键词 Kubernetes。",
    )
    events: list[dict] = []

    async def collect(event: dict) -> None:
        events.append(event)

    runner = make_runner(llm, registry=registry, token_budget=2000, on_event=collect)
    result = run(runner.run(system_prompt=SYSTEM_PROMPT, task="优化", context=make_context(llm)))

    assert any(step.kind == "compaction" for step in result.steps)
    assert any(event["type"] == "compaction" for event in events)
    # 压缩插入的摘要必须是 assistant 消息，且不能破坏 tool 消息的配对
    assert_tool_pairing(llm.messages_seen[-1])
    assert any(
        "上下文已压缩" in str(message.get("content"))
        for message in llm.messages_seen[-1]
    )
    assert result.final_output == "压缩之后的报告"


def test_compaction_falls_back_to_truncation_when_summarizer_fails():
    async def chatty(ctx, **kwargs):
        return ToolResult(ok=True, summary="内容", data={"blob": "Y" * 4000})

    class NoSummarizer(FakeLLM):
        async def complete(self, messages, **kwargs):
            if "上下文压缩器" in str(messages[0].get("content", "")):
                raise RuntimeError("summarizer down")
            return await super().complete(messages, **kwargs)

    registry = ToolRegistry([
        ToolSpec(name="chatty", description="大", parameters={"type": "object", "properties": {}}, handler=chatty)
    ])
    llm = NoSummarizer(replies=[tool_reply("chatty", {}) for _ in range(3)], final_text="依然完成")
    runner = make_runner(llm, registry=registry, token_budget=2000)
    result = run(runner.run(system_prompt=SYSTEM_PROMPT, task="优化", context=make_context(llm)))

    assert result.stopped_reason == "completed"
    assert any(step.kind == "compaction" for step in result.steps)
    assert_tool_pairing(llm.messages_seen[-1])


def test_empty_model_answer_triggers_forced_final():
    llm = FakeLLM(replies=[], final_text="兜底正文")
    # 先让循环正常结束但正文为空，再验证 _force_final 会被调用
    llm.final_text = ""
    result = run(make_runner(llm).run(system_prompt=SYSTEM_PROMPT, task="优化", context=make_context(llm)))
    assert llm.force_final_calls == 1
    assert result.final_output == ""


def test_tool_arguments_are_visible_in_step_events():
    events: list[dict] = []

    async def collect(event: dict) -> None:
        events.append(event)

    llm = FakeLLM(
        replies=[tool_reply("check_keywords", {"text": "abc", "keywords": ["python", "go"]})],
        final_text="done",
    )
    run(
        make_runner(llm, on_event=collect).run(
            system_prompt=SYSTEM_PROMPT, task="优化", context=make_context(llm)
        )
    )
    call_event = next(event for event in events if event["type"] == "tool_call")
    assert call_event["tool"] == "check_keywords"
    assert call_event["input"]["keywords"] == "['python', 'go']"
    assert json.loads(json.dumps(call_event["input"], ensure_ascii=False))
