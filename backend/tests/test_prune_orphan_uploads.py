"""The orphan-upload pruner must only ever touch unreferenced files."""

import asyncio
import os
import uuid

from scripts.prune_orphan_uploads import collect_orphans, prune


def _signup(client) -> dict[str, str]:
    email = f"prune-{uuid.uuid4().hex[:12]}@example.com"
    password = "Passw0rd!123"
    assert client.post("/auth/register", json={"email": email, "password": password}).status_code == 201
    token = client.post("/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _upload_resume(client, headers) -> str:
    r = client.post(
        "/resumes/upload",
        files={"file": ("kept.txt", b"# Zhang San\nBackend engineer\n", "text/plain")},
        data={"version_name": "v1"},
        headers=headers,
    )
    assert r.status_code == 201, r.text
    return os.path.basename(r.json()["original_file_url"].replace("\\", "/"))


def test_dry_run_lists_orphans_without_deleting(client, upload_dir):
    headers = _signup(client)
    referenced_name = _upload_resume(client, headers)

    orphan_path = os.path.join(str(upload_dir), "orphan-from-old-run.txt")
    with open(orphan_path, "w", encoding="utf-8") as fh:
        fh.write("legacy test artifact")

    _, orphans = asyncio.run(collect_orphans())

    assert "orphan-from-old-run.txt" in orphans
    assert referenced_name not in orphans
    assert os.path.isfile(orphan_path), "collecting must not delete anything"


def test_prune_removes_only_unreferenced_files(client, upload_dir):
    headers = _signup(client)
    referenced_name = _upload_resume(client, headers)
    referenced_path = os.path.join(str(upload_dir), referenced_name)

    orphan_path = os.path.join(str(upload_dir), "another-orphan.txt")
    with open(orphan_path, "w", encoding="utf-8") as fh:
        fh.write("legacy test artifact")

    _, orphans = asyncio.run(collect_orphans())
    removed = prune(orphans)

    assert removed >= 1
    assert not os.path.exists(orphan_path)
    assert os.path.isfile(referenced_path), "a referenced file must never be pruned"
