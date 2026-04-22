"""
Creates all database tables directly from SQLAlchemy models.
Use this instead of alembic migrations for fresh deployments.

Usage: python create_tables.py
"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine
from app.core.config import settings
from app.core.db import Base
from app.models import *  # noqa: F401,F403 — load all models so metadata is populated


async def create_all_tables():
    engine = create_async_engine(settings.DATABASE_URL, echo=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    print("All tables created successfully.")


if __name__ == "__main__":
    asyncio.run(create_all_tables())
