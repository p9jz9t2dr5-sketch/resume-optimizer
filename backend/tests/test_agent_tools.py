"""Agent 工具层测试：参数校验、超时兜底、确定性工具的正确性、模型工具的结构校验。

用 ``asyncio.run`` 直接跑协程而不是引入 pytest-asyncio：这些工具不碰数据库，
每次开一个独立事件循环即可，测试依赖越少越好。
"""

import asyncio
import uuid

from agent_fakes import JD_TEXT, SAMPLE_RESUME, FakeLLM
from app.agent.tools import ToolContext, ToolRegistry, ToolSpec, bm25_search, build_registry, load_knowledge_base
from app.agent.types import ToolResult
from app.database import async_session


def run(coro):
    return asyncio.run(coro)


def make_context(llm=None, **overrides) -> ToolContext:
    values = {
        "user_id": uuid.uuid4(),
        "llm": llm or FakeLLM(),
        "session_factory": async_session,
        "resume_text": SAMPLE_RESUME,
        "jd_text": JD_TEXT,
    }
    values.update(overrides)
    return ToolContext(**values)


def test_registry_schemas_are_openai_compatible():
    registry = build_registry()
    schemas = registry.schemas()
    assert {schema["type"] for schema in schemas} == {"function"}
    names = {schema["function"]["name"] for schema in schemas}
    assert {"list_resume_sections", "check_keywords", "search_knowledge", "score_resume_match"} <= names
    for schema in schemas:
        assert schema["function"]["description"]
        assert schema["function"]["parameters"]["type"] == "object"


def test_unknown_tool_returns_error_instead_of_raising():
    result = run(build_registry().execute("no_such_tool", {}, make_context()))
    assert result.ok is False
    assert "未知工具" in result.summary
    assert "list_resume_sections" in (result.error or "")


def test_missing_required_argument_is_reported_to_model():
    result = run(build_registry().execute("check_keywords", {"text": "Python"}, make_context()))
    assert result.ok is False
    assert "缺少必填参数" in result.summary


def test_arguments_are_coerced_from_model_friendly_forms():
    registry = build_registry()
    spec = registry.get("check_keywords")
    coerced, error = registry.coerce_args(spec, {"text": "a", "keywords": "Python, Go、Rust"})
    assert error is None
    assert coerced["keywords"] == ["Python", "Go", "Rust"]

    spec = registry.get("search_knowledge")
    coerced, error = registry.coerce_args(spec, {"query": "量化", "top_k": "3"})
    assert error is None and coerced["top_k"] == 3

    coerced, error = registry.coerce_args(spec, {"query": "量化", "top_k": "abc"})
    assert error is not None and "整数" in error


def test_handler_exception_becomes_a_result_not_a_crash():
    async def boom(ctx, **kwargs):
        raise ValueError("内部炸了")

    registry = ToolRegistry([
        ToolSpec(name="boom", description="总是失败", parameters={"type": "object", "properties": {}}, handler=boom)
    ])
    result = run(registry.execute("boom", {}, make_context()))
    assert result.ok is False
    assert "执行失败" in result.summary and "ValueError" in result.summary


def test_slow_tool_is_cut_off_by_timeout():
    async def slow(ctx, **kwargs):
        await asyncio.sleep(0.5)
        return ToolResult(ok=True, summary="其实跑完了")

    registry = ToolRegistry([
        ToolSpec(
            name="slow",
            description="很慢",
            parameters={"type": "object", "properties": {}},
            handler=slow,
            timeout=0.05,
        )
    ])
    result = run(registry.execute("slow", {}, make_context()))
    assert result.ok is False
    assert "超时" in result.summary


def test_list_resume_sections_tool():
    result = run(build_registry().execute("list_resume_sections", {}, make_context()))
    assert result.ok is True
    sections = result.data["sections"]
    assert "工作经历" in sections
    assert sections["工作经历"]["chars"] > 0


def test_list_resume_sections_without_text_reports_clearly():
    result = run(build_registry().execute("list_resume_sections", {}, make_context(resume_text="")))
    assert result.ok is False
    assert "没有可用的简历正文" in result.summary


def test_check_keywords_tool_computes_coverage():
    result = run(
        build_registry().execute(
            "check_keywords",
            {"text": SAMPLE_RESUME, "keywords": ["Python", "FastAPI", "Kubernetes", "RAG"]},
            make_context(),
        )
    )
    assert result.ok is True
    assert result.data["present"] == ["Python", "FastAPI"]
    assert result.data["missing"] == ["Kubernetes", "RAG"]
    assert result.data["coverage"] == 0.5


def test_search_knowledge_returns_ranked_entries():
    result = run(
        build_registry().execute("search_knowledge", {"query": "没有数字怎么量化成果", "top_k": 3}, make_context())
    )
    assert result.ok is True
    results = result.data["results"]
    assert results and len(results) <= 3
    assert "quantify" in [item["id"] for item in results]
    assert results[0]["score"] > 0


def test_search_knowledge_rejects_empty_query():
    result = run(build_registry().execute("search_knowledge", {"query": "   "}, make_context()))
    assert result.ok is False


def test_bm25_search_ranks_relevant_entry_first():
    entries = load_knowledge_base()
    hits = bm25_search(entries, "Agent 任务规划 工具调用 失败重试", top_k=2)
    assert hits, "知识库检索不应为空"
    assert hits[0][1].id == "agent-project-story"


def test_score_resume_match_tool_returns_validated_report():
    result = run(build_registry().execute("score_resume_match", {}, make_context()))
    assert result.ok is True
    assert result.data["overall_score"] == 72
    assert result.data["missing_keywords"] == ["Kubernetes", "RAG"]
    assert "72/100" in result.summary


def test_score_resume_match_survives_model_returning_garbage():
    class GarbageLLM(FakeLLM):
        async def complete(self, messages, **kwargs):
            from app.services.llm_service import LLMReply

            return LLMReply(content="我不知道该怎么打分", finish_reason="stop")

    result = run(
        build_registry().execute("score_resume_match", {}, make_context(llm=GarbageLLM()))
    )
    assert result.ok is False
    assert "JSON" in result.summary


def test_rewrite_section_locates_block_and_flags_fabricated_numbers():
    llm = FakeLLM(
        rewrite={
            "rewritten": "主导订单中心微服务拆分，接口 P99 从 800ms 降到 120ms",
            "changes": ["补强动词"],
            "keywords_used": ["微服务"],
            "risk_notes": [],
        }
    )
    result = run(
        build_registry().execute(
            "rewrite_resume_section", {"section_name": "工作经历"}, make_context(llm=llm)
        )
    )
    assert result.ok is True
    assert result.data["section"] == "工作经历"
    # 120ms 原文里没有（原文是 210ms），必须被标出来
    assert result.data["unsupported_numbers"] == ["120"]
    assert "原文没有的数字" in result.summary


def test_rewrite_section_for_unknown_block_lists_available_ones():
    result = run(
        build_registry().execute(
            "rewrite_resume_section", {"section_name": "获奖情况"}, make_context()
        )
    )
    assert result.ok is False
    assert "工作经历" in result.summary


def test_rewrite_section_keeps_no_fabrication_warning_when_numbers_match():
    llm = FakeLLM(
        rewrite={
            "rewritten": "负责订单中心微服务拆分，接口 P99 从 800ms 降到 210ms",
            "changes": [],
            "keywords_used": [],
            "risk_notes": [],
        }
    )
    result = run(
        build_registry().execute(
            "rewrite_resume_section",
            {"section_name": "工作经历", "target_keywords": ["微服务", "Redis"]},
            make_context(llm=llm),
        )
    )
    assert result.ok is True
    assert result.data["unsupported_numbers"] == []
    assert "⚠️" not in result.summary


def test_observation_is_capped():
    result = ToolResult(ok=True, summary="大结果", data={"blob": "x" * 20000})
    observation = result.to_observation(limit=500)
    assert len(observation) < 800
    assert "已截断" in observation
    assert observation.startswith("{")
