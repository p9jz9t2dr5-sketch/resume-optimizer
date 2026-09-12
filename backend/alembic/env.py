"""Alembic environment.

The database URL is taken from the application settings (``app.config``), so a
single ``alembic upgrade head`` works in every environment — local SQLite
(``APP_ENV=local`` -> ``.env.local``), CI, and the Postgres container
(``backend/.env``) — without configuring the URL twice.

The engine is async because the application uses asyncpg/aiosqlite; Alembic
drives it through ``connection.run_sync``.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from app.config import get_settings
from app.database import Base

# Importing the models registers them on Base.metadata (autogenerate needs this).
from app.models import (  # noqa: F401
    ChatSession,
    Company,
    JobDescription,
    Message,
    Resume,
    User,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ConfigParser treats "%" as interpolation, so escape it in the URL.
config.set_main_option("sqlalchemy.url", get_settings().DATABASE_URL.replace("%", "%%"))

target_metadata = Base.metadata


def _configure(connection: Connection | None = None, url: str | None = None) -> None:
    context.configure(
        connection=connection,
        url=url,
        target_metadata=target_metadata,
        compare_type=True,
        literal_binds=connection is None,
        dialect_opts={"paramstyle": "named"},
    )


def run_migrations_offline() -> None:
    _configure(url=config.get_main_option("sqlalchemy.url"))
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    _configure(connection=connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_async_migrations())
