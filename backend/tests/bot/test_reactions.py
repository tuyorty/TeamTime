"""Реакции переживают краткий сбой сети и прекращают попытки при длительном отказе."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, call

import pytest
from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
    TelegramServerError,
)
from aiogram.methods import SendMessage, SetMessageReaction
from aiohttp_socks import ProxyConnectionError, ProxyError, ProxyTimeoutError

from teamtime.bot.reactions import set_reaction
from tests.bot.fake_telegram import GROUP, FakeSession

REACTION = SetMessageReaction(chat_id=GROUP.id, message_id=7)


@pytest.fixture
def wait(monkeypatch) -> AsyncMock:
    mocked = AsyncMock()
    monkeypatch.setattr("teamtime.bot.reactions.sleep", mocked)
    return mocked


@pytest.mark.parametrize(
    "error",
    [
        ProxyTimeoutError("Proxy timed out"),
        ProxyConnectionError("Proxy disconnected"),
        ProxyError("Proxy failed"),
        TelegramNetworkError(method=REACTION, message="Request timeout"),
        TelegramServerError(method=REACTION, message="Internal server error"),
    ],
    ids=["proxy-timeout", "proxy-connection", "proxy-error", "network", "server"],
)
async def test_transient_failure_retries_same_reaction(error: Exception, wait: AsyncMock) -> None:
    fake = FakeSession()
    fake.reaction_failures.append(error)
    await set_reaction(Bot("123456:TEST-TOKEN", session=fake), GROUP.id, 7, "👌")
    requests = fake.of(SetMessageReaction)
    assert len(requests) == 2
    assert requests[0] == requests[1]
    assert fake.of(SendMessage) == []
    wait.assert_awaited_once_with(2)


async def test_persistent_failure_stops_after_three_attempts(wait: AsyncMock) -> None:
    fake = FakeSession()
    fake.reaction_failures = [ProxyTimeoutError("Proxy timed out") for _ in range(4)]
    await set_reaction(Bot("123456:TEST-TOKEN", session=fake), GROUP.id, 7, "👌")
    assert len(fake.of(SetMessageReaction)) == 3
    assert len(fake.reaction_failures) == 1
    assert fake.of(SendMessage) == []
    assert wait.await_args_list == [call(2), call(4)]


async def test_rate_limit_waits_for_telegram(wait: AsyncMock) -> None:
    fake = FakeSession()
    fake.reaction_failures.append(
        TelegramRetryAfter(method=REACTION, message="Retry", retry_after=9)
    )
    await set_reaction(Bot("123456:TEST-TOKEN", session=fake), GROUP.id, 7, "👌")
    assert len(fake.of(SetMessageReaction)) == 2
    wait.assert_awaited_once_with(9)


async def test_long_rate_limit_does_not_retry_early(wait: AsyncMock) -> None:
    fake = FakeSession()
    fake.reaction_failures.append(
        TelegramRetryAfter(method=REACTION, message="Retry", retry_after=120)
    )
    await set_reaction(Bot("123456:TEST-TOKEN", session=fake), GROUP.id, 7, "👌")
    assert len(fake.of(SetMessageReaction)) == 1
    wait.assert_not_awaited()


@pytest.mark.parametrize("error_type", [TelegramBadRequest, TelegramForbiddenError])
async def test_permanent_failure_is_not_retried(error_type, wait: AsyncMock) -> None:
    fake = FakeSession()
    fake.reaction_failures.append(error_type(method=REACTION, message="Rejected"))
    with pytest.raises(error_type):
        await set_reaction(Bot("123456:TEST-TOKEN", session=fake), GROUP.id, 7, "👌")
    assert len(fake.of(SetMessageReaction)) == 1
    wait.assert_not_awaited()


async def test_shutdown_cancels_delivery_without_retry(wait: AsyncMock) -> None:
    fake = FakeSession()
    fake.reaction_failures.append(asyncio.CancelledError())
    with pytest.raises(asyncio.CancelledError):
        await set_reaction(Bot("123456:TEST-TOKEN", session=fake), GROUP.id, 7, "👌")
    assert len(fake.of(SetMessageReaction)) == 1
    wait.assert_not_awaited()
