"""Движок и фабрика сессий. Один движок на процесс."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from teamtime.core.config import get_settings


@lru_cache
def get_engine(url: str | None = None) -> AsyncEngine:
    return create_async_engine(
        url or get_settings().database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=5,
    )


def get_sessionmaker(engine: AsyncEngine | None = None) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine or get_engine(), expire_on_commit=False)


@asynccontextmanager
async def session_scope(
    maker: async_sessionmaker[AsyncSession] | None = None,
) -> AsyncIterator[AsyncSession]:
    """Сессия с транзакцией: commit при успехе, rollback при исключении."""
    async with (maker or get_sessionmaker())() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise
