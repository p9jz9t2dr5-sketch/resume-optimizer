"""Deleting an account must remove every trace of it.

Checks the rows, the uploaded files on disk, and that nothing leaks into (or out
of) another account. Orphan rows are verified with a fresh engine bound to the
test's own event loop, because SQLite does not enforce foreign keys by default —
which is exactly the failure mode the explicit delete order guards against.
"""

import asyncio
import os
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.chat import ChatSession, Message
from app.models.agent import AgentRun, AgentStep, UserPreference
from app.models.job_description import JobDescription
from app.models.resume import Resume
from app.models.user import User


def _signup(client) -> tuple[str, dict[str, str]]:
    email = f"delete-{uuid.uuid4().hex[:12]}@example.com"
    password = "Passw0rd!123"
    assert client.post("/auth/register", json={"email": email, "password": password}).status_code == 201
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    return email, {"Authorization": f"Bearer {r.json()['access_token']}"}


def _upload_resume(client, headers, name: str = "resume.txt") -> dict:
    r = client.post(
        "/resumes/upload",
        files={"file": (name, b"# Zhang San\nBackend engineer\n", "text/plain")},
        data={"version_name": "v1"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


def _row_counts() -> dict[str, int]:
    """Count rows with a dedicated engine so no loop/pool state is shared."""

    async def run() -> dict[str, int]:
        engine = create_async_engine(os.environ["DATABASE_URL"])
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as s:
                return {
                    "users": await s.scalar(select(func.count()).select_from(User)),
                    "resumes": await s.scalar(select(func.count()).select_from(Resume)),
                    "job_descriptions": await s.scalar(
                        select(func.count()).select_from(JobDescription)
                    ),
                    "sessions": await s.scalar(select(func.count()).select_from(ChatSession)),
                    "messages": await s.scalar(select(func.count()).select_from(Message)),
                    "agent_runs": await s.scalar(select(func.count()).select_from(AgentRun)),
                    "agent_steps": await s.scalar(select(func.count()).select_from(AgentStep)),
                    "preferences": await s.scalar(select(func.count()).select_from(UserPreference)),
                }
        finally:
            await engine.dispose()

    return asyncio.run(run())


def _seed_agent_data(user_id: str, resume_id: str) -> None:
    """直接写入一条 Agent 轨迹与一条长期记忆（不经过模型，保持这个用例离线）。"""

    async def run() -> None:
        engine = create_async_engine(os.environ["DATABASE_URL"])
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with session_factory() as s:
                agent_run = AgentRun(
                    user_id=uuid.UUID(user_id),
                    resume_id=uuid.UUID(resume_id),
                    goal="优化简历",
                    status="succeeded",
                    stopped_reason="completed",
                    plan=[{"intent": "读结构", "tool": "list_resume_sections"}],
                )
                s.add(agent_run)
                await s.flush()
                s.add(
                    AgentStep(
                        run_id=agent_run.id,
                        step_index=0,
                        kind="tool",
                        tool_name="list_resume_sections",
                        status="ok",
                    )
                )
                s.add(
                    UserPreference(
                        user_id=uuid.UUID(user_id), key="target_role", value="AI 应用开发"
                    )
                )
                await s.commit()
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_deleting_an_account_removes_all_of_its_data(client, upload_dir):
    email, headers = _signup(client)
    resume = _upload_resume(client, headers, "doomed.txt")
    stored_file = os.path.join(str(upload_dir), os.path.basename(resume["original_file_url"]))
    assert os.path.isfile(stored_file)

    # A finished interview, so messages and sessions exist as well.
    session_id = client.post(
        "/chat/start",
        json={"resume_id": resume["id"], "jd_text": "后端工程师", "title": "面试"},
        headers=headers,
    ).json()["session_id"]

    # Agent 轨迹与长期记忆同样属于用户数据，注销后不能残留。
    user_id = client.get("/auth/me", headers=headers).json()["id"]
    _seed_agent_data(user_id, resume["id"])

    before = _row_counts()

    r = client.delete("/auth/me", headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["deleted"] is True
    assert r.json()["files_removed"] >= 1

    after = _row_counts()
    assert after["users"] == before["users"] - 1
    assert after["resumes"] == before["resumes"] - 1
    assert after["sessions"] == before["sessions"] - 1
    assert after["messages"] <= before["messages"]
    assert after["job_descriptions"] <= before["job_descriptions"]
    assert after["agent_runs"] == before["agent_runs"] - 1
    assert after["agent_steps"] == before["agent_steps"] - 1
    assert after["preferences"] == before["preferences"] - 1

    # The uploaded file is gone from disk...
    assert not os.path.exists(stored_file)
    # ...and the account is really gone: no token, no login.
    assert client.get("/auth/me", headers=headers).status_code in (401, 403)
    assert client.post("/auth/login", json={"email": email, "password": "Passw0rd!123"}).status_code == 401
    # The interview session is gone with it.
    assert client.get(f"/chat/{session_id}/messages", headers=headers).status_code in (401, 403)


def test_deleting_one_account_leaves_others_untouched(client, upload_dir):
    _, doomed = _signup(client)
    other_email, other = _signup(client)

    _upload_resume(client, doomed, "doomed.txt")
    kept = _upload_resume(client, other, "kept.txt")
    kept_file = os.path.join(str(upload_dir), os.path.basename(kept["original_file_url"]))

    assert client.delete("/auth/me", headers=doomed).status_code == 200

    assert client.get("/auth/me", headers=other).status_code == 200
    assert client.get("/resumes", headers=other).json()["total"] == 1
    assert os.path.isfile(kept_file)
    assert client.post("/auth/login", json={"email": other_email, "password": "Passw0rd!123"}).status_code == 200


def test_account_deletion_requires_auth(client):
    assert client.delete("/auth/me").status_code in (401, 403)
