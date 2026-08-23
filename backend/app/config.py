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
