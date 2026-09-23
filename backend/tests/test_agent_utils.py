"""Agent 纯函数的单元测试：版块切分、关键词匹配、数字幻觉检查、JSON 容错、检索分词。

这一层不碰模型也不碰数据库，是 Agent 里最该被钉死的部分（``evals/`` 的离线
评测也建立在这些函数之上）。
"""

from agent_fakes import SAMPLE_RESUME
from app.agent.utils import (
    estimate_tokens,
    keyword_hits,
    loads_json_loose,
    split_resume_sections,
    tokenize_for_search,
    truncate,
    unsupported_numbers,
)


def test_split_markdown_resume_into_sections():
    sections = split_resume_sections(SAMPLE_RESUME)
    assert set(sections) >= {"教育背景", "工作经历", "项目经历", "专业技能"}
    assert "某某大学" in sections["教育背景"]
    assert "P99 从 800ms 降到 210ms" in sections["工作经历"]
    # 版块标题之前的姓名/联系方式不能被丢掉
    assert "张三" in sections["头部信息"]
    # Markdown 的 "#" 装饰不应该留在正文里
    assert not sections["工作经历"].startswith("#")


def test_split_plain_text_resume_with_inline_heading():
    text = """个人信息
姓名：李四  电话：13900000000
求职意向：AI 应用开发实习生
专业技能：Python、FastAPI、PostgreSQL
工作经历
某公司 数据开发实习生 2024.06-2024.09
参与离线数仓建设，任务失败率下降
"""
    sections = split_resume_sections(text)
    assert "求职意向" in sections
    assert sections["求职意向"].strip() == "AI 应用开发实习生"
    assert "专业技能" in sections and "Python" in sections["专业技能"]
    assert "某公司 数据开发实习生" in sections["工作经历"]


def test_split_keeps_duplicate_sections():
    text = """工作经历
第一段
工作经历
第二段
"""
    sections = split_resume_sections(text)
    assert "工作经历" in sections and "第一段" in sections["工作经历"]
    assert any(name.startswith("工作经历(") for name in sections)
    assert any("第二段" in value for value in sections.values())


def test_split_returns_empty_for_empty_text():
    assert split_resume_sections("") == {}


def test_keyword_hits_use_word_boundaries_for_ascii():
    present, missing = keyword_hits("熟悉 Go 语言与 Google Cloud", ["Go", "Google", "Rust"])
    assert "Go" in present and "Google" in present
    assert missing == ["Rust"]


def test_keyword_hits_do_not_match_ascii_inside_longer_word():
    present, missing = keyword_hits("只用过 Google Cloud", ["Go"])
    assert present == []
    assert missing == ["Go"]


def test_keyword_hits_match_chinese_by_substring_and_dedupe():
    present, missing = keyword_hits("负责大模型应用开发与 Prompt 调优", ["大模型", "大模型", "RAG"])
    assert present == ["大模型"]
    assert missing == ["RAG"]


def test_unsupported_numbers_flags_invented_metrics():
    original = "负责订单中心拆分，接口 P99 从 800ms 降到 210ms"
    rewritten = "主导订单中心拆分，接口 P99 从 800ms 降到 210ms，性能提升 40%"
    assert unsupported_numbers(original, rewritten) == ["40"]


def test_unsupported_numbers_ignores_reused_numbers_and_percent_forms():
    original = "覆盖 30% 的核心链路"
    rewritten = "覆盖 30% 的核心链路，新增 2 个接口"
    # 30% 与 30 视为同一个数字；2 是新增数字，会被标出
    assert unsupported_numbers(original, rewritten) == ["2"]


def test_loads_json_loose_handles_fences_prose_and_trailing_comma():
    assert loads_json_loose('```json\n{"a": 1}\n```') == {"a": 1}
    assert loads_json_loose('好的，结果如下：{"a": 2} 希望有帮助') == {"a": 2}
    assert loads_json_loose('{"a": 3,}') == {"a": 3}
    assert loads_json_loose("这不是 JSON") is None
    assert loads_json_loose("[1, 2]") is None  # 只接受对象


def test_estimate_and_truncate():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 2
    assert truncate("abcdef", 3).startswith("abc…")
    assert truncate("abc", 10) == "abc"
    assert truncate(None, 10) == ""


def test_tokenize_splits_cjk_into_bigrams():
    tokens = tokenize_for_search("FastAPI 简历优化")
    assert "fastapi" in tokens
    assert "简历" in tokens and "历优" in tokens
