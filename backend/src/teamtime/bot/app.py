"""Сборка и запуск бота: long polling, ретраи, graceful shutdown (aiogram ловит SIGINT/SIGTERM)."""

from __future__ import annotations

import asyncio
import contextlib

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats
from aiogram.utils.callback_answer import CallbackAnswerMiddleware
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from teamtime.core.config import Settings
from teamtime.core.logging import configure_logging, get_logger
from teamtime.db.session import get_sessionmaker

from .handlers import commands, group, private
from .middleware import DbSessionMiddleware
from .reminders import reminder_loop

log = get_logger(__name__)

COMMANDS = [
    BotCommand(command="today", description="Кто сегодня на работе"),
    BotCommand(command="week", description="Моя неделя"),
    BotCommand(command="who", description="Команда за неделю"),
    BotCommand(command="me", description="Моя статистика за месяц"),
    BotCommand(command="absent", description="Не приду, удалёнка, отпуск"),
    BotCommand(command="fix", description="Исправить распознанное"),
    BotCommand(command="help", description="Что умеет бот"),
]


def build_dispatcher(maker: async_sessionmaker[AsyncSession], config: Settings) -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage(), config=config)
    middleware = DbSessionMiddleware(maker)
    for observer in (dp.message, dp.edited_message, dp.callback_query):
        observer.middleware(middleware)
    dp.callback_query.middleware(CallbackAnswerMiddleware())
    # Порядок важен: в группе «любой текст» не ловит команды, а в личке запасной обработчик
    # стоит последним, после команд.
    dp.include_routers(group.router, commands.router, private.router)
    return dp


async def run(config: Settings) -> None:
    configure_logging(config.log_level, config.log_format)
    if config.bot_token is None:
        log.warning("bot.disabled", reason="BOT_TOKEN не задан — бот не запущен")
        return
    engine = create_async_engine(config.database_url, pool_pre_ping=True)
    maker = get_sessionmaker(engine)
    bot = Bot(
        config.bot_token.get_secret_value(),
        session=AiohttpSession(timeout=60),
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )
    dp = build_dispatcher(maker, config)
    me = await bot.get_me()
    log.info("bot.started", username=me.username)
    if config.bot_username is None:
        config.bot_username = me.username
    await bot.set_my_commands(COMMANDS, scope=BotCommandScopeAllPrivateChats())
    reminders = asyncio.create_task(reminder_loop(bot, maker), name="reminders")
    try:
        await dp.start_polling(
            bot,
            allowed_updates=["message", "edited_message", "callback_query"],
            polling_timeout=30,
        )  # при сетевых ошибках aiogram сам повторяет запросы с экспоненциальной паузой
    finally:
        reminders.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await reminders
        await bot.session.close()
        await engine.dispose()
        log.info("bot.stopped")
