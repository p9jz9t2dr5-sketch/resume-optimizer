"""The free-tier daily message quota must be enforced, not just displayed.

The service is exercised directly in one async test and through the HTTP layer in
another, so both the counting logic and the 429 the client actually sees are
covered. Tests run without Redis, i.e. against the in-process fallback counter.
"""

import asyncio
import uuid

import pytest

from app.config import get_settings
from app.services.quota_service import quota_service

settings = get_settings()
LIMIT = settings.FREE_DAILY_MESSAGE_LIMIT


@pytest.fixture(autouse=True)
def _clean_quota():
    quota_service.reset_all()
    yield
    quota_service.reset_all()


def _signup(client) -> dict[str, str]:
    email = f"quota-{uuid.uuid4().hex[:12]}@example.com"
    password = "Passw0rd!123"
    assert client.post("/auth/register", json={"email": email, "password": password}).status_code == 201
    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _fill_quota(user_id: str, count: int) -> None:
    """Drive the counter through the service API (no private state poking)."""

    async def run() -> None:
        for _ in range(count):
            await quota_service.increment_daily(user_id)

    asyncio.run(run())


@pytest.mark.anyio
async def test_quota_counts_and_blocks_free_accounts():
    user_id = str(uuid.uuid4())

    for _ in range(LIMIT):
        assert await quota_service.consume_message(user_id, is_premium=False) is True

    assert await quota_service.consume_message(user_id, is_premium=False) is False
    assert await quota_service.get_daily_count(user_id) == LIMIT + 1


@pytest.mark.anyio
async def test_premium_accounts_are_not_blocked():
    user_id = str(uuid.uuid4())
    _ = [await quota_service.consume_message(user_id, is_premium=True) for _ in range(LIMIT + 5)]

    assert await quota_service.consume_message(user_id, is_premium=True) is True
    assert await quota_service.remaining_messages(user_id, is_premium=True) == 999999


@pytest.mark.anyio
async def test_release_gives_a_failed_message_back():
    """A model call that errored must not burn one of the free messages."""
    user_id = str(uuid.uuid4())
    await quota_service.consume_message(user_id, is_premium=False)
    assert await quota_service.get_daily_count(user_id) == 1

    await quota_service.release_message(user_id)

    assert await quota_service.get_daily_count(user_id) == 0
    assert await quota_service.remaining_messages(user_id, is_premium=False) == LIMIT


def test_message_endpoint_returns_429_when_quota_is_used_up(client):
    headers = _signup(client)

    uploaded = client.post(
        "/resumes/upload",
        files={"file": ("quota.txt", b"# Zhang San\nBackend engineer\n", "text/plain")},
        data={"version_name": "v1"},
        headers=headers,
    )
    assert uploaded.status_code == 201, uploaded.text
    resume_id = uploaded.json()["id"]

    session_id = client.post(
        "/chat/start",
        json={"resume_id": resume_id, "jd_text": "后端工程师", "title": "额度测试"},
        headers=headers,
    ).json()["session_id"]

    user_id = client.get("/auth/me", headers=headers).json()["id"]
    _fill_quota(user_id, LIMIT)

    # The dashboard counter and the enforcement share the same number.
    stats = client.get("/auth/me/stats", headers=headers).json()
    assert stats["messages_today"] == LIMIT
    assert stats["daily_limit"] == LIMIT

    blocked = client.post(
        f"/chat/{session_id}/message", json={"content": "你好"}, headers=headers
    )
    assert blocked.status_code == 429
    assert "今日免费额度已用完" in blocked.json()["detail"]


def test_stats_report_the_configured_limit(client):
    headers = _signup(client)

    stats = client.get("/auth/me/stats", headers=headers).json()

    assert stats["messages_today"] == 0
    assert stats["daily_limit"] == LIMIT
    assert stats["is_premium"] is False
