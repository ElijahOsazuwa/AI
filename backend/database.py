"""
Database session and connection setup using SQLAlchemy async engine.
All DB access goes through the async session factory defined here.
Uses SQLite for zero-dependency local development.
"""

import os
import pathlib

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

# SQLite database file lives next to the backend code
DB_DIR = pathlib.Path(__file__).parent
DB_PATH = DB_DIR / "codereviews.db"
DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{DB_PATH}")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    # SQLite needs this to allow async writes from multiple coroutines
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
)

# async_sessionmaker produces AsyncSession instances bound to our engine
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


async def get_db() -> AsyncSession:
    """FastAPI dependency that yields an async DB session and ensures cleanup."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Create all tables — used during app startup for dev convenience."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def check_db_health() -> bool:
    """Quick connectivity check for the /health endpoint."""
    try:
        async with async_session() as session:
            await session.execute(
                __import__("sqlalchemy").text("SELECT 1")
            )
        return True
    except Exception:
        return False
