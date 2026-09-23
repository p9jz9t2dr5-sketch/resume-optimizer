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

    # —— Agent（规划 + 工具调用 + 记忆 + 轨迹）——
    # 单次任务最多执行多少步（一步 = 一轮模型调用）。步数上限是防止
    # 「工具调用死循环」把 token 烧穿的最后一道闸门。
    AGENT_MAX_STEPS: int = 8
    # 单个工具调用的超时（秒）。LLM 类工具内部还有自己的模型超时。
    AGENT_TOOL_TIMEOUT_SECONDS: float = 60.0
    # 同一个工具在一次任务里最多被调用几次，超过就回一条错误观察值让它换方案。
    AGENT_MAX_SAME_TOOL_CALLS: int = 3
    # 执行上下文超过这个估算 token 数就触发压缩（把早期观察值摘要成一段）。
    AGENT_CONTEXT_TOKEN_BUDGET: int = 8000
    # 长期记忆最多存多少条键值，防止 Agent 无限写入把记忆变成垃圾场。
    AGENT_MAX_PREFERENCES: int = 20
    # 关掉后 /agent/optimize 直接回退到旧的单次改写链路。
    AGENT_ENABLED: bool = True
    # 单次模型请求的超时（秒）。客户端默认的 10 秒读超时对 Agent 的收尾报告太短：
    # 收尾要生成整篇 Markdown 报告，实测会超过 10 秒拿不到首字节，于是 3 次重试
    # 全部超时、任务以「工具都跑成功了但报告是空的」结束。这里单独放开。
    AI_REQUEST_TIMEOUT_SECONDS: float = 120.0


@lru_cache()
def get_settings() -> Settings:
    return Settings()
