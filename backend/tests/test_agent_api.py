"""Agent 接口的端到端测试：SSE 事件流、轨迹落库、降级路径、长期记忆、越权隔离。

模型一律替换成 ``FakeLLM``（``monkeypatch`` 掉 ``app.services.agent_service.llm_service``），
所以整套用例不联网、不花额度，但走的是真实的 HTTP 路由、真实的数据库与真实的 SSE 编码。
"""

import json
import uuid

import pytest
from agent_fakes import JD_TEXT, SAMPLE_RESUME, FakeLLM, tool_reply

import app.services.agent_service as agent_service
from app.api import agent as agent_api


def parse_sse(body: str) -> list[dict]:
    """把 SSE 响应体解析成事件列表（``[DONE]`` 帧丢弃）。"""
    events: list[dict] = []
    for block in body.split("\n\n"):
        block = block.strip()
        if not block.startswith("data:"):
            continue
        payload = block[len("data:") :].strip()
        if payload == "[DONE]":
            continue
        events.append(json.loads(payload))
    return events


def signup(client, email: str | None = None) -> dict[str, str]:
    email = email or f"agent-{uuid.uuid4().hex[:12]}@example.com"
    password = "Passw0rd!123"
    assert client.post("/auth/register", json={"email": email, "password": password}).status_code == 201
    response = client.post("/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def upload_resume(client, headers, text: str = SAMPLE_RESUME, name: str = "agent-resume.txt") -> str:
    response = client.post(
        "/resumes/upload",
        files={"file": (name, text.encode("utf-8"), "text/plain")},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.fixture
def with_api_key(monkeypatch):
    """接口会检查模型 Key 是否配置；测试环境默认清空，这里临时补上。"""
    monkeypatch.setattr(agent_api.settings, "OPENAI_API_KEY", "test-key")


@pytest.fixture
def fake_llm(monkeypatch):
    def _install(llm: FakeLLM) -> FakeLLM:
        monkeypatch.setattr(agent_service, "llm_service", llm)
        return llm

    return _install


def test_agent_optimize_streams_plan_tools_report_and_trace(client, with_api_key, fake_llm):
    headers = signup(client)
    resume_id = upload_resume(client, headers)
    fake_llm(
        FakeLLM(
            replies=[
                tool_reply("list_resume_sections", {}),
                tool_reply("check_keywords", {"text": SAMPLE_RESUME, "keywords": ["Python", "Kubernetes"]}),
                tool_reply("search_knowledge", {"query": "没有数字怎么量化成果"}),
            ],
            final_text="## 匹配度结论\n\n整体匹配一般。\n\n## 下一步\n\n1. 补 RAG 经历。",
        )
    )

    response = client.post(
        "/agent/optimize",
        json={"resume_id": resume_id, "jd_text": JD_TEXT},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)

    run_event = next(event for event in events if event["type"] == "run")
    assert run_event["run_id"]
    assert run_event["model"]

    plan_event = next(event for event in events if event["type"] == "plan")
    assert plan_event["plan"][0]["intent"] == "读简历结构"

    called_tools = [event["tool"] for event in events if event["type"] == "tool_call"]
    assert called_tools == ["list_resume_sections", "check_keywords", "search_knowledge"]
    assert all(
        event["ok"] is True for event in events if event["type"] == "tool_result"
    )

    # 最终报告沿用旧接口的 content 帧格式（前端不用改渲染逻辑）
    content = "".join(
        event["content"] for event in events if event.get("type") == "content"
    )
    assert "匹配度结论" in content

    done = next(event for event in events if event["type"] == "done")
    assert done["stopped_reason"] == "completed"
    assert done["tool_calls"] == 3
    assert done["steps"] >= 5
    assert response.text.rstrip().endswith("[DONE]")

    # 轨迹已落库，可以事后复盘
    runs = client.get("/agent/runs", headers=headers).json()
    assert runs["total"] == 1
    run = runs["runs"][0]
    assert run["status"] == "succeeded"
    assert run["steps_count"] >= 5
    assert run["tool_calls"] == 3
    assert run["prompt_tokens"] > 0

    detail = client.get(f"/agent/runs/{run['id']}", headers=headers).json()
    kinds = [step["kind"] for step in detail["steps"]]
    assert kinds[0] == "plan" and kinds[-1] == "final"
    assert [step["tool_name"] for step in detail["steps"] if step["kind"] == "tool"] == [
        "list_resume_sections",
        "check_keywords",
        "search_knowledge",
    ]
    keyword_step = next(
        step for step in detail["steps"] if step["tool_name"] == "check_keywords"
    )
    assert keyword_step["tool_output"]["missing"] == ["Kubernetes"]
    assert keyword_step["latency_ms"] >= 0


def test_agent_optimize_needs_a_real_resume(client, with_api_key, fake_llm):
    headers = signup(client)
    fake_llm(FakeLLM())

    missing = client.post(
        "/agent/optimize",
        json={"resume_id": str(uuid.uuid4()), "jd_text": JD_TEXT},
        headers=headers,
    )
    assert missing.status_code == 404

    malformed = client.post(
        "/agent/optimize",
        json={"resume_id": "not-a-uuid", "jd_text": JD_TEXT},
        headers=headers,
    )
    assert malformed.status_code == 404


def test_agent_optimize_without_model_key_returns_503(client, fake_llm):
    headers = signup(client)
    resume_id = upload_resume(client, headers)
    fake_llm(FakeLLM())

    response = client.post(
        "/agent/optimize",
        json={"resume_id": resume_id, "jd_text": JD_TEXT},
        headers=headers,
    )
    assert response.status_code == 503


def test_runs_and_preferences_are_scoped_to_their_owner(client, with_api_key, fake_llm):
    owner = signup(client)
    intruder = signup(client)
    resume_id = upload_resume(client, owner)
    fake_llm(FakeLLM(final_text="## 报告\n内容"))

    body = client.post(
        "/agent/optimize",
        json={"resume_id": resume_id, "jd_text": JD_TEXT},
        headers=owner,
    ).text
    run_id = next(event["run_id"] for event in parse_sse(body) if event["type"] == "run")

    assert client.get("/agent/runs", headers=intruder).json()["total"] == 0
    assert client.get(f"/agent/runs/{run_id}", headers=intruder).status_code == 404
    assert client.delete(f"/agent/runs/{run_id}", headers=intruder).status_code == 404
    assert client.get(f"/agent/runs/{run_id}", headers=owner).status_code == 200

    client.put("/agent/preferences/style", json={"value": "量化优先"}, headers=owner)
    assert client.get("/agent/preferences", headers=intruder).json()["total"] == 0


def test_agent_falls_back_when_model_cannot_call_tools(client, with_api_key, fake_llm):
    headers = signup(client)
    resume_id = upload_resume(client, headers)
    llm = fake_llm(FakeLLM(raise_tool_unsupported=True))

    response = client.post(
        "/agent/optimize",
        json={"resume_id": resume_id, "jd_text": JD_TEXT},
        headers=headers,
    )
    events = parse_sse(response.text)

    fallback = next(event for event in events if event["type"] == "fallback")
    assert "工具调用" in fallback["reason"]
    assert llm.polish_calls == 1
    assert any("降级报告" in event.get("content", "") for event in events)

    done = next(event for event in events if event["type"] == "done")
    assert done["stopped_reason"] == "tool_unsupported"
    assert done["fallback"] is True

    run = client.get("/agent/runs", headers=headers).json()["runs"][0]
    assert run["stopped_reason"] == "tool_unsupported"
    assert run["status"] == "succeeded"


def test_section_rewrites_update_the_resume_preview(client, with_api_key, fake_llm):
    headers = signup(client)
    resume_id = upload_resume(client, headers)
    llm = fake_llm(
        FakeLLM(
            replies=[tool_reply("rewrite_resume_section", {"section_name": "工作经历"})],
            rewrite={
                "rewritten": "搭建订单中心微服务，接口 P99 从 800ms 降到 210ms",
                "changes": ["量化结果前置"],
                "keywords_used": ["微服务"],
                "risk_notes": [],
            },
            final_text="## 报告\n已改写工作经历。",
        )
    )

    response = client.post(
        "/agent/optimize",
        json={"resume_id": resume_id, "jd_text": JD_TEXT},
        headers=headers,
    )
    events = parse_sse(response.text)

    structured_event = next(event for event in events if "structured" in event)
    assert structured_event["structured"]["work_experience"][0]["company"] == "某互联网公司"
    # 重新结构化解析用的是「改写稿 + 原文其余版块」，而不是把建议报告当简历解析
    assert "## 工作经历" in llm.parse_calls[-1]
    assert "搭建订单中心微服务" in llm.parse_calls[-1]

    resume = client.get(f"/resumes/{resume_id}", headers=headers).json()
    assert resume["parsed_data"]["structured"] == structured_event["structured"]
    assert "已改写工作经历" in resume["parsed_data"]["agent_report"]
    assert "工作经历" in resume["parsed_data"]["agent_rewrites"]
    # 身份字段仍然来自原简历：模型看到的是 [已隐藏]，但本地回填必须还原真实姓名，
    # 不能让占位符覆盖交付物里的身份字段。
    assert resume["parsed_data"]["structured"]["basic_info"]["name"] == "张三"
    assert "[已隐藏]" not in str(resume["parsed_data"]["structured"]["basic_info"].values())


def test_agent_cannot_overwrite_a_user_set_preference(client, with_api_key, fake_llm):
    headers = signup(client)
    resume_id = upload_resume(client, headers)
    fake_llm(
        FakeLLM(
            replies=[tool_reply("remember_preference", {"key": "target_role", "value": "算法工程师"})],
            final_text="## 报告\n已记录偏好。",
        )
    )

    created = client.put(
        "/agent/preferences/target_role", json={"value": "AI 应用开发"}, headers=headers
    )
    assert created.status_code == 200
    assert created.json()["source"] == "user"

    response = client.post(
        "/agent/optimize",
        json={"resume_id": resume_id, "jd_text": JD_TEXT},
        headers=headers,
    )
    events = parse_sse(response.text)
    result = next(
        event for event in events if event["type"] == "tool_result" and event["tool"] == "remember_preference"
    )
    assert result["ok"] is False
    assert "不能覆盖" in result["summary"]

    preferences = client.get("/agent/preferences", headers=headers).json()
    stored = {item["key"]: item for item in preferences["preferences"]}
    assert stored["target_role"]["value"] == "AI 应用开发"
    assert preferences["known_keys"]["target_role"] == "目标岗位"


def test_preference_validation_and_deletion(client, with_api_key):
    headers = signup(client)

    bad_key = client.put("/agent/preferences/BAD_KEY", json={"value": "x"}, headers=headers)
    assert bad_key.status_code == 400
    assert "键名" in bad_key.json()["detail"]

    empty_value = client.put("/agent/preferences/style", json={"value": ""}, headers=headers)
    assert empty_value.status_code == 422  # pydantic 拦在最外层

    assert client.put("/agent/preferences/style", json={"value": "STAR 优先"}, headers=headers).status_code == 200
    assert client.delete("/agent/preferences/style", headers=headers).json()["deleted"] is True
    assert client.delete("/agent/preferences/style", headers=headers).status_code == 404
    assert client.get("/agent/preferences", headers=headers).json()["total"] == 0


def test_runs_can_be_deleted_one_by_one_or_all_at_once(client, with_api_key, fake_llm):
    headers = signup(client)
    resume_id = upload_resume(client, headers)
    fake_llm(FakeLLM(final_text="## 报告\n内容"))

    run_ids = []
    for _ in range(2):
        body = client.post(
            "/agent/optimize",
            json={"resume_id": resume_id, "jd_text": JD_TEXT},
            headers=headers,
        ).text
        run_ids.append(next(event["run_id"] for event in parse_sse(body) if event["type"] == "run"))

    assert client.delete(f"/agent/runs/{run_ids[0]}", headers=headers).json()["deleted"] is True
    assert client.get("/agent/runs", headers=headers).json()["total"] == 1
    assert client.delete("/agent/runs", headers=headers).json()["deleted"] == 1
    assert client.get("/agent/runs", headers=headers).json()["total"] == 0


def test_agent_run_is_linked_to_resume_and_survives_resume_deletion(client, with_api_key, fake_llm):
    headers = signup(client)
    resume_id = upload_resume(client, headers)
    fake_llm(FakeLLM(final_text="## 报告\n内容"))
    body = client.post(
        "/agent/optimize",
        json={"resume_id": resume_id, "jd_text": JD_TEXT},
        headers=headers,
    ).text
    run_id = next(event["run_id"] for event in parse_sse(body) if event["type"] == "run")

    assert client.delete(f"/resumes/{resume_id}", headers=headers).json()["deleted"] is True
    detail = client.get(f"/agent/runs/{run_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["resume_id"] is None  # 只断开引用，执行记录保留
