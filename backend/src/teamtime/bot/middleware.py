"""Middleware: сессия БД и бизнес-настройки в каждом обработчике."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from teamtime.services.settings import load_settings


class DbSessionMiddleware(BaseMiddleware):
    def __init__(self, maker: async_sessionmaker[AsyncSession]) -> None:
        self.maker = maker

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with self.maker() as session:
            data["session"] = session
            data["settings"] = await load_settings(session)
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except BaseException:
                await session.rollback()
                raise
