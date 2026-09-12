"""Password policy and login throttling."""

import uuid

from app.services.login_throttle import MAX_FAILURES, login_throttle

GOOD_PASSWORD = "Passw0rd!123"


def _email() -> str:
    return f"hardening-{uuid.uuid4().hex[:12]}@example.com"


def test_password_must_be_at_least_eight_characters(client):
    for short in ("", "a", "1234567"):
        r = client.post("/auth/register", json={"email": _email(), "password": short})
        assert r.status_code == 422, f"{short!r} should be rejected"


def test_password_longer_than_bcrypt_limit_is_rejected(client):
    r = client.post("/auth/register", json={"email": _email(), "password": "a" * 73})
    assert r.status_code == 422


def test_eight_character_password_is_accepted(client):
    email = _email()
    assert client.post("/auth/register", json={"email": email, "password": "12345678"}).status_code == 201
    assert client.post("/auth/login", json={"email": email, "password": "12345678"}).status_code == 200


def test_repeated_failures_block_further_attempts(client):
    login_throttle.reset_all()
    email = _email()
    assert client.post("/auth/register", json={"email": email, "password": GOOD_PASSWORD}).status_code == 201

    for attempt in range(MAX_FAILURES):
        r = client.post("/auth/login", json={"email": email, "password": "wrong-password"})
        assert r.status_code == 401, f"attempt {attempt + 1} should be a plain 401"

    blocked = client.post("/auth/login", json={"email": email, "password": GOOD_PASSWORD})
    assert blocked.status_code == 429
    assert "登录失败次数过多" in blocked.json()["detail"]


def test_throttle_is_scoped_to_one_account(client):
    login_throttle.reset_all()
    victim = _email()
    bystander = _email()
    for email in (victim, bystander):
        assert client.post("/auth/register", json={"email": email, "password": GOOD_PASSWORD}).status_code == 201

    for _ in range(MAX_FAILURES):
        client.post("/auth/login", json={"email": victim, "password": "wrong-password"})

    assert client.post("/auth/login", json={"email": victim, "password": GOOD_PASSWORD}).status_code == 429
    # Someone else's account is unaffected by the failures above.
    assert client.post("/auth/login", json={"email": bystander, "password": GOOD_PASSWORD}).status_code == 200


def test_successful_login_clears_the_counter(client):
    login_throttle.reset_all()
    email = _email()
    assert client.post("/auth/register", json={"email": email, "password": GOOD_PASSWORD}).status_code == 201

    for _ in range(MAX_FAILURES - 1):
        client.post("/auth/login", json={"email": email, "password": "wrong-password"})

    assert client.post("/auth/login", json={"email": email, "password": GOOD_PASSWORD}).status_code == 200

    # Counter was reset, so the full budget is available again.
    for _ in range(MAX_FAILURES - 1):
        assert client.post("/auth/login", json={"email": email, "password": "wrong-password"}).status_code == 401
    assert client.post("/auth/login", json={"email": email, "password": GOOD_PASSWORD}).status_code == 200
