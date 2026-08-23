from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from sqlalchemy import text

from app.config import get_settings
from app.database import engine, Base, async_session
from app.api import auth, resumes, companies, jd, chat
from app.models import user, resume, company, job_description, chat as chat_model
from app.services.quota_service import quota_service
from app.seed_data import seed_companies


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Idempotent schema migration for local SQLite (create_all won't add new columns
    # to an existing table). Safe to run every boot; ignores "column already exists".
    try:
        async with engine.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: sync_conn.execute(
                    text("ALTER TABLE resumes ADD COLUMN content TEXT")
                )
            )
    except Exception:
        pass

    # Same idempotent migration for the cropped-avatar column added later.
    try:
        async with engine.begin() as conn:
            await conn.run_sync(
                lambda sync_conn: sync_conn.execute(
                    text("ALTER TABLE resumes ADD COLUMN avatar_url VARCHAR(1000)")
                )
            )
    except Exception:
        pass

    # Redis quota (no-op locally when REDIS_URL is empty)
    await quota_service.connect()

    # Auto-seed companies on first run
    try:
        inserted = await seed_companies(async_session)
        if inserted:
            print(f"Seeded {inserted} companies.")
    except Exception as e:
        print(f"Company seeding skipped: {e}")

    yield

    await quota_service.disconnect()
    await engine.dispose()


settings = get_settings()

app = FastAPI(
    title="AI Resume Optimizer",
    description="AI-powered resume optimization platform API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(resumes.router, prefix="/resumes", tags=["Resumes"])
app.include_router(companies.router, prefix="/companies", tags=["Companies"])
app.include_router(jd.router, prefix="/jd", tags=["Job Descriptions"])
app.include_router(chat.router, prefix="/chat", tags=["Chat"])

# Static file serving for uploaded resume files (used as avatar / preview thumbnails)
import os as _os
_os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "AI Resume Optimizer"}
