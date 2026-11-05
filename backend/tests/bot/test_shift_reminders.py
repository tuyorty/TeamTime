"""Первое начало дня: личная доставка, тихое время и отсутствие повторов после сбоев."""

import asyncio
from datetime import date

import pytest
from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from aiogram.methods import SendMessage
from sqlalchemy import select

from teamtime.bot.shift_reminders import send_shift_reminders
from teamtime.calc import StatusKind
from teamtime.db.models import Employee, NotificationPreference, ShiftReminder, TelegramIdentity
from teamtime.parsing import PlanDayKind
from teamtime.services import manual
from teamtime.services.ingest import ingest
from teamtime.services.settings import load_settings, save_settings
from tests import factories as f
from tests.bot.fake_telegram import FakeSession
from tests.bot.test_reminders import WORK_DATE, at, setup_reminder

pytestmark = pytest.mark.db


def fake_bot():
    fake = FakeSession()
    return Bot("123456:TEST-TOKEN", session=fake), fake


async def test_boundary_and_concurrent_workers_send_once_per_person_day(maker):
    employee_id = await setup_reminder(maker, "10:00-13:00; 16:00-18:00")
    bot, fake = fake_bot()
    at("2026-10-26T08:59:59+05:00")
    assert await send_shift_reminders(bot, maker) == 0
    at("2026-10-26T09:00:00+05:00")
    assert (
        sum(
            await asyncio.gather(send_shift_reminders(bot, maker), send_shift_reminders(bot, maker))
        )
        == 1
    )
    assert await send_shift_reminders(bot, maker) == 0
    async with maker() as session:
        record = await session.get(ShiftReminder, (employee_id, WORK_DATE))
        assert record.sent_at is not None and record.attempts == 1
    at("2026-10-26T15:00:00+05:00")
    assert await send_shift_reminders(bot, maker) == 0
    message = fake.of(SendMessage)[0]
    assert message.chat_id == 501 and "10:00" in message.text and "В офисе" in message.text
    assert len(fake.of(SendMessage)) == 1


@pytest.mark.parametrize(
    "reason", ["no_dm", "removed", "inactive", "disabled", "personal", "arrival", "daily"]
)
async def test_ineligible_person_never_receives_a_message(maker, reason):
    employee_id = await setup_reminder(maker)
    async with maker() as session:
        identity = await session.scalar(select(TelegramIdentity))
        if reason == "no_dm":
            identity.dm_chat_id = None
        elif reason == "removed":
            identity.removed_at = identity.last_seen_at
        elif reason == "inactive":
            employee = await session.get(Employee, employee_id)
            employee.is_active = False
        elif reason == "disabled":
            settings = await load_settings(session)
            settings.bot.reminders_enabled = False
            await save_settings(session, settings)
        elif reason == "daily":
            await ingest(session, f.message(f.daily_text("26.10.2026")))
        else:
            session.add(
                NotificationPreference(
                    employee_id=employee_id,
                    enabled=reason != "personal",
                    arrival_enabled=reason != "arrival",
                )
            )
        await session.commit()
    at("2026-10-26T09:00:00+05:00")
    bot, fake = fake_bot()
    assert await send_shift_reminders(bot, maker) == 0
    assert fake.of(SendMessage) == []


@pytest.mark.parametrize(
    "kind", [StatusKind.VACATION, StatusKind.SICK, StatusKind.BUSINESS_TRIP, StatusKind.ABSENT]
)
async def test_absence_cancels_start_reminder(maker, kind):
    employee_id = await setup_reminder(maker)
    async with maker() as session:
        await manual.set_status(
            session, employee_id=employee_id, day=WORK_DATE, kind=kind, actor="test"
        )
        await session.commit()
    at("2026-10-26T09:00:00+05:00")
    bot, fake = fake_bot()
    assert await send_shift_reminders(bot, maker) == 0
    assert not fake.of(SendMessage)


@pytest.mark.parametrize("plan", ["выходной", "после обеда"])
async def test_no_exact_start_no_reminder(maker, plan):
    await setup_reminder(maker, plan)
    at("2026-10-26T09:00:00+05:00")
    bot, _ = fake_bot()
    assert await send_shift_reminders(bot, maker) == 0


async def test_night_start_is_reminded_on_previous_date(maker):
    await setup_reminder(maker, "00:30-04:00")
    at("2026-10-25T23:30:00+05:00")
    bot, fake = fake_bot()
    assert await send_shift_reminders(bot, maker) == 1
    assert "26.10 в 00:30" in fake.of(SendMessage)[0].text


async def test_no_backlog_after_long_outage_or_shift_start(maker):
    await setup_reminder(maker)
    bot, fake = fake_bot()
    for moment in ("09:10:00", "09:30:00", "10:00:00", "18:00:00"):
        at(f"2026-10-26T{moment}+05:00")
        assert await send_shift_reminders(bot, maker) == 0
    assert not fake.of(SendMessage)


@pytest.mark.parametrize(("quiet_end", "expected"), [(9 * 60 + 30, 1), (10 * 60, 0)])
async def test_quiet_time_only_defers_before_start(maker, quiet_end, expected):
    employee_id = await setup_reminder(maker)
    async with maker() as session:
        session.add(
            NotificationPreference(
                employee_id=employee_id, quiet_start=22 * 60, quiet_end=quiet_end
            )
        )
        await session.commit()
    bot, fake = fake_bot()
    at("2026-10-26T09:00:00+05:00")
    assert await send_shift_reminders(bot, maker) == 0
    at("2026-10-26T09:30:00+05:00")
    assert await send_shift_reminders(bot, maker) == expected
    at("2026-10-26T10:00:00+05:00")
    assert await send_shift_reminders(bot, maker) == 0
    assert len(fake.of(SendMessage)) == expected


async def test_remote_and_multiple_accounts_one_message(maker):
    employee_id = await setup_reminder(maker)
    async with maker() as session:
        session.add(
            TelegramIdentity(
                telegram_user_id=777,
                employee_id=employee_id,
                dm_chat_id=777,
                display_name="Другой аккаунт",
            )
        )
        await manual.set_status(
            session, employee_id=employee_id, day=WORK_DATE, kind=StatusKind.REMOTE, actor="test"
        )
        await session.commit()
    at("2026-10-26T09:00:00+05:00")
    bot, fake = fake_bot()
    assert await send_shift_reminders(bot, maker) == 1
    assert "Удалённо" in fake.of(SendMessage)[0].text
    assert len(fake.of(SendMessage)) == 1


@pytest.mark.parametrize("error", [TelegramNetworkError, TelegramForbiddenError])
async def test_ambiguous_failure_or_block_never_retries(maker, error):
    employee_id = await setup_reminder(maker)
    bot, fake = fake_bot()
    fake.send_failures = [error(method=SendMessage(chat_id=501, text=""), message="test failure")]
    at("2026-10-26T09:00:00+05:00")
    assert await send_shift_reminders(bot, maker) == 0
    assert await send_shift_reminders(bot, maker) == 0
    assert len(fake.of(SendMessage)) == 1
    async with maker() as session:
        record = await session.get(ShiftReminder, (employee_id, WORK_DATE))
        assert record.attempted_at and record.error_code == error.__name__


async def test_rate_limit_has_bounded_retries(maker):
    await setup_reminder(maker)
    bot, fake = fake_bot()
    fake.send_failures = [
        TelegramRetryAfter(method=SendMessage(chat_id=501, text=""), message="test", retry_after=60)
    ] * 4
    for moment in ("09:00:00", "09:01:00", "09:03:00", "09:07:00"):
        at(f"2026-10-26T{moment}+05:00")
        assert await send_shift_reminders(bot, maker) == 0
    assert len(fake.of(SendMessage)) == 3


async def test_persisted_attempt_from_crash_is_never_replayed(maker):
    from teamtime.core import clock

    employee_id = await setup_reminder(maker)
    at("2026-10-26T09:00:00+05:00")
    async with maker() as session:
        session.add(
            ShiftReminder(
                employee_id=employee_id,
                work_date=WORK_DATE,
                chat_id=501,
                shift_start=clock.now(),
                attempted_at=clock.now(),
                attempts=1,
            )
        )
        await session.commit()
    bot, fake = fake_bot()
    assert await send_shift_reminders(bot, maker) == 0
    assert not fake.of(SendMessage)


async def test_changed_schedule_does_not_send_second_reminder(maker):
    employee_id = await setup_reminder(maker)
    bot, fake = fake_bot()
    at("2026-10-26T09:00:00+05:00")
    assert await send_shift_reminders(bot, maker) == 1
    async with maker() as session:
        await manual.set_plan_day(
            session,
            employee_id=employee_id,
            day=date(2026, 10, 26),
            kind=PlanDayKind.WORK,
            intervals=[(12 * 3600, 18 * 3600)],
            actor="test",
        )
        await session.commit()
    at("2026-10-26T11:00:00+05:00")
    assert await send_shift_reminders(bot, maker) == 0
    assert len(fake.of(SendMessage)) == 1
