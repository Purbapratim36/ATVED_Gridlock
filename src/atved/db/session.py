from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from atved.config import get_settings
from atved.db.models import Base

# Global engine and session factory
_engine = None
_async_session_factory = None

def _get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        # asyncpg tries SSL by default; Docker Postgres doesn't support it,
        # which causes a misleading "password auth failed" error.
        ssl_mode = settings.database.ssl_mode
        if ssl_mode in ("disable", "prefer", ""):
            connect_args = {"ssl": False}
        else:
            connect_args = {"ssl": ssl_mode}
        _engine = create_async_engine(
            settings.database.async_url,
            pool_size=settings.database.pool_size,
            max_overflow=settings.database.max_overflow,
            echo=settings.database.echo,
            connect_args=connect_args,
        )
    return _engine

def AsyncSessionFactory() -> async_sessionmaker[AsyncSession]:
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            bind=_get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autocommit=False,
            autoflush=False,
        )
    return _async_session_factory

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for providing a database session to FastAPI endpoints."""
    factory = AsyncSessionFactory()
    async with factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

async def init_db() -> None:
    """Initialize the database by creating all tables. (For dev/testing only)"""
    engine = _get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def dispose_engine() -> None:
    """Dispose of the database engine (useful for clean teardown)."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
