"""Shared pytest fixtures.

Everything here runs *before* the application is imported, because
``app.config`` / ``app.database`` build the engine at import time. Pointing the
environment at a throwaway SQLite file and a temp upload dir keeps the suite
from touching the developer's ``.env.local``, ``local_dev.db`` or the real
``backend/uploads`` folder — and it works unchanged in CI where those files
don't exist at all.
"""

import os
import pathlib
import sys
import tempfile

_BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND_DIR))

_TMP_ROOT = pathlib.Path(tempfile.mkdtemp(prefix="resume-optimizer-tests-"))
_UPLOAD_DIR = _TMP_ROOT / "uploads"
_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

os.environ["APP_ENV"] = "local"
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(_TMP_ROOT / 'test.db').as_posix()}"
os.environ["REDIS_URL"] = ""  # quota service no-ops when Redis is not configured
os.environ["UPLOAD_DIR"] = str(_UPLOAD_DIR)
os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["OPENAI_API_KEY"] = ""  # tests must never hit a paid model endpoint
os.environ["CORS_ORIGINS"] = "http://localhost:3000"

import pytest  # noqa: E402  (import order is deliberate)
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def alembic_config() -> Config:
    """Alembic config pointing at this repo's migration scripts and the test DB."""
    config = Config(str(_BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND_DIR / "alembic"))
    return config


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    """Build the schema the way production does — through Alembic, not create_all.

    This keeps the migration scripts on the tested path: if a revision drifts
    from the models, the whole suite fails at setup instead of in production.
    """
    command.upgrade(alembic_config(), "head")


@pytest.fixture(scope="session")
def alembic_cfg() -> Config:
    """The Alembic config the suite migrated with (pointing at the test DB)."""
    return alembic_config()


@pytest.fixture(scope="session")
def client():
    """A TestClient whose context manager runs the app lifespan (creates tables
    and seeds the company list) exactly like a real server boot would."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="session")
def upload_dir() -> pathlib.Path:
    """The temp UPLOAD_DIR the app under test writes resume/avatar files into."""
    return _UPLOAD_DIR
