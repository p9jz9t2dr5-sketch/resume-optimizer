"""End-to-end tests for the mock-interview session endpoints.

The interviewer's opening line is generated best-effort (``chat.py`` swallows a
failing LLM call), and tests run with ``OPENAI_API_KEY=""`` — so the whole
session lifecycle is exercised here without touching a paid model.
"""

import uuid

SAMPLE_RESUME = """# 张三
求职意向：后端开发工程师

## 工作经历
某互联网公司 — 后端开发工程师 | 2023.07 - 至今
- 负责订单中心微服务拆分，接口 P99 从 800ms 降到 210ms
"""

JD = "高级后端工程师：熟悉 Python、分布式系统与 Kubernetes。"


def _signup(client, email: str | None = None) -> dict[str, str]:
    email = email or f"interview-{uuid.uuid4().hex[:12]}@example.com"
    password = "Passw0rd!123"
    assert client.post("/auth/register", json={"email": email, "password": password}).status_code == 201
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _upload_resume(client, headers) -> str:
    r = client.post(
        "/resumes/upload",
        files={"file": ("interview.txt", SAMPLE_RESUME.encode("utf-8"), "text/plain")},
        data={"version_name": "面试用"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_interview_session_lifecycle(client):
    headers = _signup(client)
    resume_id = _upload_resume(client, headers)

    started = client.post(
        "/chat/start",
        json={"resume_id": resume_id, "jd_text": JD, "title": "模拟面试"},
        headers=headers,
    )
    assert started.status_code == 201, started.text
    session_id = started.json()["session_id"]
    assert started.json()["title"] == "模拟面试"

    listed = client.get("/chat/sessions", headers=headers).json()
    assert [s["id"] for s in listed["sessions"]] == [session_id]

    # The opening is best-effort: with no API key there is simply no message yet,
    # but the endpoint must still answer cleanly.
    messages = client.get(f"/chat/{session_id}/messages", headers=headers)
    assert messages.status_code == 200
    assert isinstance(messages.json(), list)

    assert client.delete(f"/chat/{session_id}", headers=headers).json()["deleted"] is True
    assert client.get("/chat/sessions", headers=headers).json()["total"] == 0
    assert client.get(f"/chat/{session_id}/messages", headers=headers).status_code == 404


def test_interview_sessions_are_scoped_to_their_owner(client):
    owner = _signup(client)
    intruder = _signup(client)
    resume_id = _upload_resume(client, owner)

    session_id = client.post(
        "/chat/start",
        json={"resume_id": resume_id, "jd_text": JD, "title": "私有面试"},
        headers=owner,
    ).json()["session_id"]

    assert client.get("/chat/sessions", headers=intruder).json()["total"] == 0
    assert client.get(f"/chat/{session_id}/messages", headers=intruder).status_code == 404
    assert client.delete(f"/chat/{session_id}", headers=intruder).status_code == 404
    # ...and the owner's session is untouched by those attempts.
    assert client.get(f"/chat/{session_id}/messages", headers=owner).status_code == 200


def test_starting_an_interview_needs_a_real_resume(client):
    headers = _signup(client)

    r = client.post(
        "/chat/start",
        json={"resume_id": str(uuid.uuid4()), "jd_text": JD, "title": "无简历"},
        headers=headers,
    )

    assert r.status_code == 404


def test_interview_endpoints_require_auth(client):
    assert client.get("/chat/sessions").status_code in (401, 403)
    assert client.post("/chat/start", json={"resume_id": str(uuid.uuid4())}).status_code in (401, 403)
