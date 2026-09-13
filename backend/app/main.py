"""应用入口：创建 FastAPI 实例、挂载路由与静态目录、启动时连接 Redis 并写入种子数据。

路由前缀一览（公网访问时 nginx 会把 /api 前缀剥掉再转给后端）：

| 前缀 | 来源文件 | 负责什么 |
|------|----------|----------|
| /auth | app/api/auth.py | 账号、资料（头像/昵称）、注销 |
| /resumes | app/api/resumes.py | 简历上传解析、优化建议（SSE） |
| /jd | app/api/jd.py | JD 解析与匹配度分析 |
| /chat | app/api/chat.py | 模拟面试（SSE） |
| /companies | app/api/companies.py | 公司库 |
| /uploads | StaticFiles | 上传的简历原文件与头像 |
| /health | 本文件 | 健康检查（容器 healthcheck 探的就是它） |

数据库结构由 Alembic 迁移负责（compose 启动前执行 alembic upgrade head），
本文件不再建表。
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from app.config import get_settings
from app.database import async_session, engine
from app.api import auth, resumes, companies, jd, chat
from app.models import user, resume, company, job_description, chat as chat_model
from app.services.quota_service import quota_service
from app.services.login_throttle import login_throttle
from app.seed_data import seed_companies


@asynccontextmanager
async def lifespan(app: FastAPI):
    # The schema is owned by Alembic (`alembic upgrade head`, run by compose
    # before the API starts); startup only does data work.
    # Redis quota (no-op locally when REDIS_URL is empty)
    await quota_service.connect()
    # Login failure throttling shares the same Redis instance when configured.
    await login_throttle.connect()

    # Auto-seed companies on first run
    try:
        inserted = await seed_companies(async_session)
        if inserted:
            print(f"Seeded {inserted} companies.")
    except Exception as e:
        print(f"Company seeding skipped: {e}")

    yield

    await quota_service.disconnect()
    await login_throttle.disconnect()
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
