"""Ограниченные повторы реакций при временных ошибках Telegram и SOCKS-прокси."""

from __future__ import annotations

from asyncio import sleep
from collections.abc import Awaitable, Callable

from aiogram import Bot
from aiogram.exceptions import TelegramNetworkError, TelegramRetryAfter, TelegramServerError
from aiogram.types import ReactionTypeEmoji
from aiohttp_socks import ProxyConnectionError, ProxyError, ProxyTimeoutError

from teamtime.core.logging import get_logger

log = get_logger(__name__)
MAX_ATTEMPTS = 3
REQUEST_TIMEOUT_SECONDS = 15
MAX_RETRY_DELAY_SECONDS = 30


async def set_reaction(
    bot: Bot,
    chat_id: int,
    message_id: int,
    emoji: str,
    attempted: Callable[[int], Awaitable[None]] | None = None,
) -> bool:
    """Повторяем только выставление той же реакции: новых сообщений оно не создаёт.

    Долгую блокировку Telegram не сокращаем: если ждать нужно больше 30 секунд,
    прекращаем попытки. Постоянные ошибки остаются на обработку вызывающему коду.
    """
    for attempt in range(1, MAX_ATTEMPTS + 1):
        if attempted:
            await attempted(attempt)
        try:
            await bot.set_message_reaction(
                chat_id,
                message_id,
                reaction=[ReactionTypeEmoji(emoji=emoji)],
                request_timeout=REQUEST_TIMEOUT_SECONDS,
            )
        except TelegramRetryAfter as exc:
            delay = max(2**attempt, exc.retry_after)
            error = type(exc).__name__
        except (
            TelegramNetworkError,
            TelegramServerError,
            ProxyConnectionError,
            ProxyError,
            ProxyTimeoutError,
        ) as exc:
            # aiohttp-socks выбрасывает ошибки, не унаследованные от TelegramAPIError.
            delay = 2**attempt
            error = type(exc).__name__
        else:
            if attempt > 1:
                log.info(
                    "bot.reaction_recovered",
                    chat_id=chat_id,
                    message_id=message_id,
                    attempts=attempt,
                )
            return True

        if attempt == MAX_ATTEMPTS or delay > MAX_RETRY_DELAY_SECONDS:
            log.warning(
                "bot.reaction_abandoned",
                chat_id=chat_id,
                message_id=message_id,
                attempts=attempt,
                error=error,
            )
            return False
        log.warning(
            "bot.reaction_retry",
            chat_id=chat_id,
            message_id=message_id,
            attempt=attempt,
            retry_in_seconds=delay,
            error=error,
        )
        await sleep(delay)
    return False
