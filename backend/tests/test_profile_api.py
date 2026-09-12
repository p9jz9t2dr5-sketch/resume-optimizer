"""End-to-end tests for the account profile endpoints.

These go through the real ASGI app — routing, JWT middleware, SQLAlchemy session
and the static upload mount — against an isolated SQLite database, so they cover
the wiring that unit tests miss.
"""

import io
import os
import uuid

from PIL import Image, ImageDraw


def _png_bytes(size=(600, 400)) -> bytes:
    """A deliberately non-square image: the server must centre-crop it."""
    img = Image.new("RGB", size, (13, 148, 136))
    draw = ImageDraw.Draw(img)
    for x in range(0, size[0], 60):
        draw.rectangle([x, 0, x + 30, size[1]], fill=(255, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _signup(client, email: str | None = None) -> tuple[str, dict[str, str]]:
    email = email or f"user-{uuid.uuid4().hex[:12]}@example.com"
    password = "Passw0rd!123"

    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text

    r = client.post("/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return email, {"Authorization": f"Bearer {r.json()['access_token']}"}


def _upload_avatar(client, headers, image: bytes | None = None, name: str = "me.png"):
    return client.post(
        "/auth/me/avatar",
        files={"file": (name, image or _png_bytes(), "image/png")},
        headers=headers,
    )


def _stored_name(avatar_url: str) -> str:
    return os.path.basename(avatar_url.replace("\\", "/"))


# --------------------------------------------------------------------------- #
# health / auth basics
# --------------------------------------------------------------------------- #


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_register_login_and_me(client):
    email, headers = _signup(client)

    r = client.get("/auth/me", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == email
    assert body["display_name"] is None
    assert body["avatar_url"] is None
    assert body["is_premium"] is False


def test_register_rejects_duplicate_email(client):
    email, _ = _signup(client)
    r = client.post("/auth/register", json={"email": email, "password": "Passw0rd!123"})
    assert r.status_code == 409


def test_login_rejects_wrong_password(client):
    email, _ = _signup(client)
    r = client.post("/auth/login", json={"email": email, "password": "wrong-password"})
    assert r.status_code == 401


def test_profile_endpoints_require_auth(client):
    assert client.get("/auth/me").status_code in (401, 403)
    assert client.patch("/auth/me", json={"display_name": "x"}).status_code in (401, 403)
    assert client.delete("/auth/me/avatar").status_code in (401, 403)


# --------------------------------------------------------------------------- #
# display name
# --------------------------------------------------------------------------- #


def test_display_name_is_trimmed_and_persisted(client):
    _, headers = _signup(client)

    r = client.patch("/auth/me", json={"display_name": "  小张  "}, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["display_name"] == "小张"

    assert client.get("/auth/me", headers=headers).json()["display_name"] == "小张"


def test_display_name_length_boundary(client):
    _, headers = _signup(client)

    ok = client.patch("/auth/me", json={"display_name": "一二三四五六七八"}, headers=headers)
    assert ok.status_code == 200, ok.text

    too_long = client.patch("/auth/me", json={"display_name": "一二三四五六七八九"}, headers=headers)
    assert too_long.status_code == 422


def test_display_name_rejects_blank(client):
    _, headers = _signup(client)

    for value in ("", "   ", "\t"):
        r = client.patch("/auth/me", json={"display_name": value}, headers=headers)
        assert r.status_code == 422, f"{value!r} should be rejected"


# --------------------------------------------------------------------------- #
# avatar
# --------------------------------------------------------------------------- #


def test_avatar_is_centre_cropped_square_png(client, upload_dir):
    _, headers = _signup(client)

    r = _upload_avatar(client, headers, _png_bytes((600, 400)))
    assert r.status_code == 200, r.text
    avatar_url = r.json()["avatar_url"]
    assert avatar_url

    # The browser reaches it through the static mount.
    served = client.get("/" + avatar_url.replace("\\", "/").lstrip("./"))
    assert served.status_code == 200
    assert served.headers["content-type"] == "image/png"
    assert Image.open(io.BytesIO(served.content)).size == (256, 256)

    # ...and the bytes really landed in the configured upload dir.
    assert (upload_dir / _stored_name(avatar_url)).is_file()


def test_avatar_rejects_non_image(client):
    _, headers = _signup(client)
    r = _upload_avatar(client, headers, b"definitely not an image", name="notes.txt")
    assert r.status_code == 400


def test_avatar_rejects_oversize_file(client):
    _, headers = _signup(client)
    oversize = b"\x89PNG\r\n\x1a\n" + b"0" * (5 * 1024 * 1024)
    r = _upload_avatar(client, headers, oversize, name="big.png")
    assert r.status_code == 400
    assert "5MB" in r.json()["detail"]


def test_replacing_avatar_removes_the_previous_file(client, upload_dir):
    _, headers = _signup(client)

    first = _upload_avatar(client, headers).json()["avatar_url"]
    second = _upload_avatar(client, headers, _png_bytes((300, 300))).json()["avatar_url"]

    assert first != second
    assert not (upload_dir / _stored_name(first)).exists(), "old avatar should be cleaned up"
    assert (upload_dir / _stored_name(second)).is_file()


def test_delete_avatar_clears_column_and_file(client, upload_dir):
    _, headers = _signup(client)
    avatar_url = _upload_avatar(client, headers).json()["avatar_url"]

    r = client.delete("/auth/me/avatar", headers=headers)
    assert r.status_code == 200
    assert r.json()["avatar_url"] is None
    assert client.get("/auth/me", headers=headers).json()["avatar_url"] is None
    assert not (upload_dir / _stored_name(avatar_url)).exists()


def test_avatar_survives_a_fresh_read(client):
    _, headers = _signup(client)
    avatar_url = _upload_avatar(client, headers).json()["avatar_url"]

    assert client.get("/auth/me", headers=headers).json()["avatar_url"] == avatar_url
