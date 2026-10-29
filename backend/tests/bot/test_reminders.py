"""Напоминания после смены: граница 15 минут, ночные смены, повторы и ошибки Telegram."""

from __future__ import annotations

import asyncio
from datetime import date, datetime

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from aiogram.methods import SendMessage
from aiogram.types import User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.bot.identity import identity_for
from teamtime.bot.reminders import due_reminders, send_due_reminders
from teamtime.calc import StatusKind
from teamtime.core import clock
from teamtime.db.models import DailyReminder, Employee, TelegramIdentity
from teamtime.services import manual
from teamtime.services.ingest import ingest
from teamtime.services.settings import AppSettings, load_settings, save_settings
from tests import factories as f
from tests.bot.fake_telegram import FakeSession

pytestmark = pytest.mark.db
WORK_DATE = date(2026, 10, 26)


async def setup_reminder(maker, schedule: str = "10:00 - 18:00") -> int:
    async with maker() as session:
        await f.forum(session)
        employee = await f.employee(session, tg_id=501)
        await identity_for(session, User(id=501, is_bot=False, first_name="Вымышленный"), 501)
        await save_settings(session, AppSettings())
        await ingest(
            session,
            f.message(
                f.schedule_text(Пн=schedule, Вт="выходной"),
                thread=f.SCHEDULE_THREAD,
            ),
        )
        await session.commit()
        return employee.id


def at(value: str = "2026-10-26T18:15:00+05:00") -> None:
    clock.freeze(datetime.fromisoformat(value))


@pytest.mark.parametrize(
    ("now", "expected"),
    [
        ("2026-10-26T12:15:00+05:00", 0),
        ("2026-10-26T18:14:59+05:00", 0),
        ("2026-10-26T18:15:00+05:00", 1),
    ],
)
async def test_exact_deadline_uses_last_interval(maker, now: str, expected: int) -> None:
    await setup_reminder(maker, "09:00 - 12:00; 15:00 - 18:00")
    at(now)
    async with maker() as session:
        assert len(await due_reminders(session)) == expected


@pytest.mark.parametrize(
    ("schedule", "now", "expected"),
    [
        ("22:00 - 02:00", "2026-10-27T02:14:59+05:00", 0),
        ("22:00 - 02:00", "2026-10-27T02:15:00+05:00", 1),
        ("10:00 - 23:55", "2026-10-27T00:10:00+05:00", 1),
    ],
)
async def test_midnight_keeps_original_work_date(maker, schedule, now, expected) -> None:
    await setup_reminder(maker, schedule)
    at(now)
    async with maker() as session:
        reminders = await due_reminders(session)
    assert len(reminders) == expected
    if reminders:
        assert reminders[0].work_date == WORK_DATE


@pytest.mark.parametrize(
    "kind",
    [
        StatusKind.VACATION,
        StatusKind.SICK,
        StatusKind.OFF,
        StatusKind.DAYOFF,
        StatusKind.ABSENT,
    ],
)
async def test_cancelled_shifts_are_not_reminded(maker, kind) -> None:
    employee_id = await setup_reminder(maker)
    async with maker() as session:
        await manual.set_status(
            session,
            employee_id=employee_id,
            day=WORK_DATE,
            kind=kind,
            actor="test",
        )
        await session.commit()
    at()
    async with maker() as session:
        assert await due_reminders(session) == []


@pytest.mark.parametrize("schedule", ["выходной", "по ситуации"])
async def test_no_timed_shift_means_no_reminder(maker, schedule) -> None:
    await setup_reminder(maker, schedule)
    at()
    async with maker() as session:
        assert await due_reminders(session) == []


@pytest.mark.parametrize("reason", ["daily", "inactive", "disabled", "no_dm", "holiday"])
async def test_ineligible_employee_is_skipped(maker, reason) -> None:
    employee_id = await setup_reminder(maker)
    async with maker() as session:
        if reason == "daily":
            await ingest(session, f.message(f.daily_text("26.10.2026")))
        elif reason == "inactive":
            employee = await session.get(Employee, employee_id)
            employee.is_active = False
        elif reason == "no_dm":
            identity = await session.scalar(select(TelegramIdentity))
            identity.dm_chat_id = None
        else:
            settings = await load_settings(session)
            if reason == "disabled":
                settings.bot.reminders_enabled = False
            else:
                settings.holidays = [WORK_DATE]
            await save_settings(session, settings)
        await session.commit()
    at()
    async with maker() as session:
        assert await due_reminders(session) == []


async def test_remote_employee_is_reminded(maker) -> None:
    employee_id = await setup_reminder(maker)
    async with maker() as session:
        await manual.set_status(
            session,
            employee_id=employee_id,
            day=WORK_DATE,
            kind=StatusKind.REMOTE,
            actor="test",
        )
        await session.commit()
    at()
    async with maker() as session:
        assert len(await due_reminders(session)) == 1


async def test_success_is_persistent_and_contains_useful_buttons(maker) -> None:
    employee_id = await setup_reminder(maker)
    at()
    fake = FakeSession()
    bot = Bot("123456:TEST-TOKEN", session=fake)
    assert await send_due_reminders(bot, maker) == 1
    # Новая сессия и новый экземпляр бота моделируют перезапуск процесса.
    assert await send_due_reminders(Bot("123456:TEST-TOKEN", session=fake), maker) == 0
    messages = fake.of(SendMessage)
    assert len(messages) == 1
    assert messages[0].parse_mode == "HTML"
    assert "26.10.2026" in messages[0].text and "15 минут" in messages[0].text
    buttons = [button for row in messages[0].reply_markup.inline_keyboard for button in row]
    assert any(button.url == "https://t.me/c/1234567890/22" for button in buttons)
    assert all(button.url is None or button.url.startswith("https://t.me/") for button in buttons)
    assert any(button.callback_data == "m:fix" for button in buttons)
    async with maker() as session:
        record = await session.get(DailyReminder, (employee_id, WORK_DATE, 501))
        assert record.sent_at is not None


async def test_concurrent_workers_do_not_send_twice(maker) -> None:
    await setup_reminder(maker)
    at()
    fake = FakeSession()
    bot = Bot("123456:TEST-TOKEN", session=fake)
    results = await asyncio.gather(
        send_due_reminders(bot, maker),
        send_due_reminders(bot, maker),
    )
    assert sum(results) == 1
    assert len(fake.of(SendMessage)) == 1


async def test_rate_limit_is_retried_after_requested_delay(maker) -> None:
    employee_id = await setup_reminder(maker)
    at()
    fake = FakeSession()
    method = SendMessage(chat_id=501, text="тест")
    fake.send_failures.append(TelegramRetryAfter(method=method, message="Retry", retry_after=120))
    bot = Bot("123456:TEST-TOKEN", session=fake)
    assert await send_due_reminders(bot, maker) == 0
    assert await send_due_reminders(bot, maker) == 0
    async with maker() as session:
        record = await session.get(DailyReminder, (employee_id, WORK_DATE, 501))
        assert record.sent_at is None
    at("2026-10-26T18:16:00+05:00")
    assert await send_due_reminders(bot, maker) == 0
    at("2026-10-26T18:17:00+05:00")
    assert await send_due_reminders(bot, maker) == 1


async def test_network_error_is_not_retried_after_restart(maker) -> None:
    employee_id = await setup_reminder(maker)
    at()
    fake = FakeSession()
    fake.send_failures.append(
        TelegramNetworkError(method=SendMessage(chat_id=501, text="тест"), message="Timeout")
    )
    assert await send_due_reminders(Bot("123456:TEST-TOKEN", session=fake), maker) == 0
    at("2026-10-26T19:00:00+05:00")
    assert await send_due_reminders(Bot("123456:TEST-TOKEN", session=fake), maker) == 0
    assert len(fake.of(SendMessage)) == 1
    async with maker() as session:
        record = await session.get(DailyReminder, (employee_id, WORK_DATE, 501))
        assert record.attempted_at is not None and record.sent_at is None


async def test_crash_after_telegram_accepted_message_does_not_repeat_it(maker) -> None:
    await setup_reminder(maker)
    at()

    class CrashAfterDelivery(FakeSession):
        async def make_request(self, bot, method, timeout=None):  # noqa: ASYNC109 — сигнатура BaseSession
            result = await super().make_request(bot, method, timeout)
            if isinstance(method, SendMessage):
                raise asyncio.CancelledError
            return result

    fake = CrashAfterDelivery()
    with pytest.raises(asyncio.CancelledError):
        await send_due_reminders(Bot("123456:TEST-TOKEN", session=fake), maker)
    at("2026-10-26T19:00:00+05:00")
    assert await send_due_reminders(Bot("123456:TEST-TOKEN", session=fake), maker) == 0
    assert len(fake.of(SendMessage)) == 1


async def test_failed_database_write_after_delivery_does_not_repeat_it(maker, monkeypatch) -> None:
    await setup_reminder(maker)
    at()
    fake = FakeSession()
    original_commit = AsyncSession.commit
    failed = False

    async def commit(session):
        nonlocal failed
        if fake.of(SendMessage) and not failed:
            failed = True
            raise RuntimeError("Имитируем сбой БД после отправки")
        await original_commit(session)

    monkeypatch.setattr(AsyncSession, "commit", commit)
    with pytest.raises(RuntimeError, match="сбой БД"):
        await send_due_reminders(Bot("123456:TEST-TOKEN", session=fake), maker)
    assert await send_due_reminders(Bot("123456:TEST-TOKEN", session=fake), maker) == 0
    assert len(fake.of(SendMessage)) == 1


async def test_rate_limit_attempts_are_bounded(maker) -> None:
    await setup_reminder(maker)
    fake = FakeSession()
    fake.send_failures = [
        TelegramRetryAfter(
            method=SendMessage(chat_id=501, text="тест"), message="Retry", retry_after=60
        )
        for _ in range(4)
    ]
    for minute in (15, 16, 18, 22):
        at(f"2026-10-26T18:{minute}:00+05:00")
        assert await send_due_reminders(Bot("123456:TEST-TOKEN", session=fake), maker) == 0
    assert len(fake.of(SendMessage)) == 3


async def test_failed_claim_does_not_send_until_database_recovers(maker, monkeypatch) -> None:
    await setup_reminder(maker)
    at()
    fake = FakeSession()

    async def failed_commit(session):
        raise RuntimeError("Имитируем недоступную БД")

    with monkeypatch.context() as patch:
        patch.setattr(AsyncSession, "commit", failed_commit)
        with pytest.raises(RuntimeError, match="недоступную БД"):
            await send_due_reminders(Bot("123456:TEST-TOKEN", session=fake), maker)
    assert fake.of(SendMessage) == []
    assert await send_due_reminders(Bot("123456:TEST-TOKEN", session=fake), maker) == 1


async def test_long_outage_does_not_send_old_reminders(maker) -> None:
    await setup_reminder(maker)
    at("2026-10-26T19:15:00+05:00")
    fake = FakeSession()
    assert await send_due_reminders(Bot("123456:TEST-TOKEN", session=fake), maker) == 0
    at("2026-10-27T09:00:00+05:00")
    assert await send_due_reminders(Bot("123456:TEST-TOKEN", session=fake), maker) == 0
    assert fake.of(SendMessage) == []


async def test_blocked_bot_waits_for_new_private_message(maker) -> None:
    await setup_reminder(maker)
    at()
    fake = FakeSession()
    fake.send_failures.append(
        TelegramForbiddenError(
            method=SendMessage(chat_id=501, text="тест"),
            message="Blocked",
        )
    )
    bot = Bot("123456:TEST-TOKEN", session=fake)
    assert await send_due_reminders(bot, maker) == 0
    async with maker() as session:
        assert await due_reminders(session) == []
        await identity_for(session, User(id=501, is_bot=False, first_name="Вымышленный"), 501)
        await session.commit()
    assert await send_due_reminders(bot, maker) == 1


async def test_old_history_is_not_spammed_after_restart(maker) -> None:
    await setup_reminder(maker)
    at("2026-10-27T18:15:00+05:00")
    async with maker() as session:
        assert await due_reminders(session) == []


async def test_delay_is_configurable_and_hour_setting_is_not_used(maker) -> None:
    await setup_reminder(maker)
    async with maker() as session:
        settings = await load_settings(session)
        settings.bot.reminder_delay_minutes = 30
        await save_settings(session, settings)
        await session.commit()
    at()
    async with maker() as session:
        assert await due_reminders(session) == []
    at("2026-10-26T18:30:00+05:00")
    async with maker() as session:
        assert len(await due_reminders(session)) == 1
