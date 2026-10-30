"""Middleware: сессия БД и бизнес-настройки в каждом обработчике."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from teamtime.services.diagnostics import touch_update
from teamtime.services.settings import load_settings

from .identity import identity_for


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
                await touch_update(session)
                # Метаданные не держат общую строку заблокированной во время ответа Telegram.
                await session.commit()
                message = event.message if isinstance(event, CallbackQuery) else event
                user = event.from_user if isinstance(event, Message | CallbackQuery) else None
                if isinstance(message, Message) and message.chat.type == "private" and user:
                    await identity_for(session, user, message.chat.id)
                result = await handler(event, data)
                await session.commit()
                return result
            except BaseException:
                await session.rollback()
                raise
