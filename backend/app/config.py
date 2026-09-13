"""应用配置：所有可调项都来自环境变量或 .env 文件（见 app/config.py 顶部的 _ENV_FILE）。

读哪个文件由 APP_ENV 决定：

- APP_ENV=local → backend/.env.local（本地开发：SQLite，可不配 Redis）
- 其他         → backend/.env（docker-compose 使用：Postgres + Redis）

真实环境变量的优先级高于 .env 文件，所以测试可以直接覆盖 DATABASE_URL / UPLOAD_DIR
而不影响开发者的本地配置。
"""

import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache

# Local dev (SQLite + no Docker) reads .env.local; everything else (docker-compose)
# reads .env. Set APP_ENV=local when running `uvicorn app.main:app` without Docker.
_ENV_FILE = ".env.local" if os.getenv("APP_ENV") == "local" else ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, env_file_encoding="utf-8", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://resume_user:resume_pass@localhost:5432/resume_optimizer"
    REDIS_URL: str = "redis://localhost:6379/0"
    SECRET_KEY: str = "dev-secret-key-change-in-production"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.deepseek.com/v1"
    AI_FAST_MODEL: str = "deepseek-chat"
    AI_PREMIUM_MODEL: str = "deepseek-chat"
    CORS_ORIGINS: str = "http://localhost:3000"
    UPLOAD_DIR: str = "./uploads"
    FREE_DAILY_MESSAGE_LIMIT: int = 20

    # 阿里云百炼 DashScope（图片简历 OCR，Qwen-VL 视觉模型，OpenAI 兼容端点）
    DASHSCOPE_API_KEY: str = ""
    DASHSCOPE_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    QWEN_VL_MODEL: str = "qwen-vl-max"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
