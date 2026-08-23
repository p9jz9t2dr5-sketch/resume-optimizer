"""
Seed script: populate the companies table with 50+ tech companies.
Run: python -m scripts.seed_companies

The app also auto-seeds on startup, so this is mainly for manual re-seeding.
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from app.config import get_settings
from app.seed_data import seed_companies

settings = get_settings()


async def main():
    engine = create_async_engine(settings.DATABASE_URL)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    inserted = await seed_companies(session_factory)
    print(f"Seeded {inserted} companies." if inserted else "Companies already present — nothing to seed.")

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
