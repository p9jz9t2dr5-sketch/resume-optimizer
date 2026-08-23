from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import event
from app.config import get_settings

settings = get_settings()

if settings.DATABASE_URL.startswith("sqlite"):
    engine = create_async_engine(
        settings.DATABASE_URL, echo=False, connect_args={"timeout": 30}
    )

    # Do NOT force journal_mode=WAL here. WAL keeps all writes in a sibling
    # `<db>-wal` file plus a `<db>-shm` shared-memory file; on directories that
    # disallow creating/writing those sidecars (OneDrive-style sync folders,
    # network shares, some AV/controlled-folder policies) every write then fails
    # with the very misleading "attempt to write a readonly database" even though
    # the .db file itself is perfectly writable.
    # The default DELETE journal is portable and plenty for local dev; a
    # busy_timeout is what actually prevents spurious "database is locked" errors.
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _record):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()
else:
    engine = create_async_engine(
        settings.DATABASE_URL, echo=False, pool_size=20, max_overflow=10
    )

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
