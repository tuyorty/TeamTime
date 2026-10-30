"""Успешный long polling и его ошибки видны в админке независимо от SSE сайта."""

from __future__ import annotations

from aiogram import Bot
from aiogram.client.session.middlewares.base import BaseRequestMiddleware, NextRequestMiddlewareType
from aiogram.methods import GetMe, GetUpdates, Response, TelegramMethod
from aiogram.methods.base import TelegramType
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from teamtime.core.logging import get_logger
from teamtime.services.diagnostics import set_service

log = get_logger(__name__)


class TelemetryMiddleware(BaseRequestMiddleware):
    def __init__(self, maker: async_sessionmaker[AsyncSession]) -> None:
        self.maker = maker

    async def record(self, state: str, error_code: str | None = None) -> None:
        try:
            async with self.maker() as session:
                await set_service(
                    session, "bot", state, success=state == "running", error_code=error_code
                )
                await session.commit()
        except Exception as exc:
            log.warning("bot.telemetry_unavailable", error=type(exc).__name__)

    async def __call__(
        self,
        make_request: NextRequestMiddlewareType[TelegramType],
        bot: Bot,
        method: TelegramMethod[TelegramType],
    ) -> Response[TelegramType]:
        observed = isinstance(method, GetMe | GetUpdates)
        if not observed:
            return await make_request(bot, method)
        try:
            response = await make_request(bot, method)
        except Exception as exc:
            await self.record("error", type(exc).__name__)
            raise
        await self.record("running")
        return response
