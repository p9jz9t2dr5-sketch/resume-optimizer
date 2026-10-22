"""隐私边界回归：发给模型的只能是脱敏文本，交付物仍保留真实联系方式。

这一组用例锁住的是「代码行为」而不是「文档承诺」——之前 README 写「只有脱敏
文本会发给模型」，但主链路实际用的是 content（含真实姓名/手机/邮箱）。
"""

import uuid

import pytest

from app.config import get_settings
from app.schemas.jd import MatchReport
from app.services.llm_service import LLMReply, llm_service

SAMPLE = """张三
手机：13800000000  邮箱：zhangsan@example.com
身份证：110101199001011234
求职意向：后端开发工程师
现居地：深圳市南山区

教育背景
某某大学 计算机科学与技术 本科 | 2019.09 - 2023.06

项目经历
AI 简历优化平台 — 独立开发
- 用 FastAPI + PostgreSQL 实现简历解析与 SSE 流式改写

专业技能
Python、FastAPI、PostgreSQL
"""

PII = ("张三", "13800000000", "zhangsan@example.com", "110101199001011234")
JD = "AI 应用开发实习生：熟悉 Python、FastAPI，了解 Agent 与 Function Calling。"


def _signup(client) -> dict[str, str]:
    email = f"privacy-{uuid.uuid4().hex[:10]}@example.com"
    password = "Passw0rd!123"
    assert client.post("/auth/register", json={"email": email, "password": password}).status_code == 201
    token = client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _upload(client, headers) -> str:
    response = client.post(
        "/resumes/upload",
        files={"file": ("privacy.txt", SAMPLE.encode("utf-8"), "text/plain")},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _assert_masked(text: str) -> None:
    for secret in PII:
        assert secret not in text, f"模型收到了未脱敏的 {secret!r}"
    assert "[已隐藏]" in text


@pytest.fixture
def api_key(monkeypatch):
    """端点的 Key 检查读的是同一个 Settings 单例，改一次全局生效。"""
    monkeypatch.setattr(get_settings(), "OPENAI_API_KEY", "test-key")


def test_upload_sends_masked_text_and_restores_identity(client, monkeypatch, api_key):
    captured: list[str] = []

    async def fake_parse_resume(text, is_premium=False):
        captured.append(text)
        # 故意不返回任何身份字段：真实身份必须由本地回填
        return {"summary": "后端开发", "skills": ["Python"], "basic_info": {}}

    monkeypatch.setattr(llm_service, "parse_resume", fake_parse_resume)
    headers = _signup(client)
    resume_id = _upload(client, headers)

    assert captured, "上传时应调用一次结构化解析"
    _assert_masked(captured[0])

    resume = client.get(f"/resumes/{resume_id}", headers=headers).json()
    # 原文仍在本地，供预览/导出使用
    assert "13800000000" in resume["content"]
    # 结构化数据里的身份由本地回填，不依赖模型
    basic = resume["parsed_data"]["structured"]["basic_info"]
    assert basic["name"] == "张三"
    assert basic["phone"] == "13800000000"
    assert basic["email"] == "zhangsan@example.com"
    assert basic["job_title"] == "后端开发工程师"


def test_polish_sends_masked_text_and_export_keeps_real_contact(client, monkeypatch, api_key):
    captured_polish: list[str] = []
    captured_parse: list[str] = []

    async def fake_parse_resume(text, is_premium=False):
        captured_parse.append(text)
        return {"summary": "优化后的简介", "skills": ["Python"], "basic_info": {}}

    async def fake_polish_stream(resume_text, jd_text, match_report=None, is_premium=False):
        captured_polish.append(resume_text)
        yield "## 优化建议\n"
        yield "保留 [已隐藏] 占位符。"

    monkeypatch.setattr(llm_service, "parse_resume", fake_parse_resume)
    monkeypatch.setattr(llm_service, "polish_stream", fake_polish_stream)

    headers = _signup(client)
    resume_id = _upload(client, headers)
    response = client.post(
        f"/resumes/{resume_id}/polish", json={"jd_text": JD}, headers=headers
    )
    assert response.status_code == 200, response.text
    _assert_masked(captured_polish[0])

    # 导出是本地交付物，必须仍有真实联系方式
    exported = client.get(f"/resumes/{resume_id}/export", headers=headers).text
    assert "13800000000" in exported
    assert "zhangsan@example.com" in exported
    assert "张三" in exported


def test_jd_match_and_interview_send_masked_text(client, monkeypatch, api_key):
    captured: list[str] = []

    async def fake_parse_jd(raw_text, is_premium=False):
        return {
            "company_name": "示例公司",
            "title": "AI 应用开发实习生",
            "parsed_requirements": {"skills": ["Python"], "keywords": ["Python"]},
        }

    async def fake_analyze_match(resume_text, parsed_requirements, is_premium=False):
        captured.append(resume_text)
        return MatchReport(overall_score=70, matched_keywords=["Python"])

    async def fake_interview_opening(resume_text, jd_text, is_premium=False):
        captured.append(resume_text)
        return "你好，我们先聊聊你的项目。"

    monkeypatch.setattr(llm_service, "parse_jd", fake_parse_jd)
    monkeypatch.setattr(llm_service, "analyze_match", fake_analyze_match)
    monkeypatch.setattr(llm_service, "interview_opening", fake_interview_opening)

    headers = _signup(client)
    resume_id = _upload(client, headers)

    parsed = client.post("/jd/parse", json={"raw_text": JD, "resume_id": resume_id}, headers=headers)
    assert parsed.status_code == 200, parsed.text

    started = client.post(
        "/chat/start",
        json={"resume_id": resume_id, "jd_text": JD, "title": "隐私边界"},
        headers=headers,
    )
    assert started.status_code == 201, started.text

    assert len(captured) == 2
    for text in captured:
        _assert_masked(text)


def test_agent_sends_masked_text(client, monkeypatch, api_key):
    captured: list[str] = []

    async def fake_parse_resume(text, is_premium=False):
        return {"summary": "agent 报告解析", "skills": ["Python"], "basic_info": {}}

    async def fake_complete(messages, **kwargs):
        # 规划器收到的是任务描述，不含简历；但统一收集以便断言
        captured.append(str(messages))
        raise RuntimeError("planner down")  # 触发 DEFAULT_PLAN 兜底

    async def fake_complete_with_tools(messages, tools, **kwargs):
        captured.append(str(messages))
        return LLMReply(content="## 报告\n完成。", finish_reason="stop")

    monkeypatch.setattr(llm_service, "complete", fake_complete)
    monkeypatch.setattr(llm_service, "complete_with_tools", fake_complete_with_tools)
    monkeypatch.setattr(llm_service, "parse_resume", fake_parse_resume)

    headers = _signup(client)
    resume_id = _upload(client, headers)
    response = client.post(
        "/agent/optimize",
        json={"resume_id": resume_id, "jd_text": JD, "max_steps": 2},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert captured
    for text in captured:
        for secret in PII:
            assert secret not in text, f"Agent 模型收到了未脱敏的 {secret!r}"
