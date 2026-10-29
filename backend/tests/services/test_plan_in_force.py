"""Правка расписания: за 12 ч до начала — сама, позже — после подтверждения админа."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, time

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.db.models import Resolution, TelegramIdentity
from teamtime.parsing import PlanDayKind
from teamtime.schemas import DayCellOut
from teamtime.services import manual, messages, reports
from teamtime.services.ingest import ingest
from teamtime.services.settings import AppSettings
from tests import factories as f

pytestmark = pytest.mark.db
SETTINGS = AppSettings(timezone="Asia/Yekaterinburg")
MONDAY = date(2026, 10, 19)
SCHEDULE_ID = 7001


def local(day: date, hh: int, mm: int = 0) -> datetime:
    return datetime.combine(day, time(hh, mm), SETTINGS.tz)


async def setup(session: AsyncSession) -> int:
    """План на пн 10:00–18:00, прислан накануне; дейлик за пн с 11:00."""
    await f.forum(session)
    e = await f.employee(session, "Иванов И.И.", tg_id=501)
    await ingest(
        session,
        f.message(
            f.schedule_text(sprint="19.10 - 24.10", Пн="10:00 - 18:00"),
            thread=f.SCHEDULE_THREAD,
            message_id=SCHEDULE_ID,
            sent_at=local(date(2026, 10, 18), 20),
        ),
        SETTINGS,
    )
    await ingest(
        session,
        f.message(f.daily_text("19.10.2026", "11:00 - 19:00"), sent_at=local(MONDAY, 19, 30)),
        SETTINGS,
    )
    return e.id


async def edit_schedule(session: AsyncSession, at: datetime) -> None:
    msg = f.message(
        f.schedule_text(sprint="19.10 - 24.10", Пн="11:00 - 19:00"),
        thread=f.SCHEDULE_THREAD,
        message_id=SCHEDULE_ID,
        sent_at=local(date(2026, 10, 18), 20),
    )
    await ingest(session, replace(msg, edited_at=at), SETTINGS)


async def monday(session: AsyncSession, emp: int) -> DayCellOut:
    week = await reports.week_report(session, SETTINGS, 2026, 43)
    return next(r for r in week.rows if r.employee.id == emp).cells[0]


async def inbox_items(session: AsyncSession) -> list[str]:
    inbox = await messages.inbox(session)
    return [i.code for item in inbox.items for i in item.parse.issues]


async def test_no_edit_is_late(session: AsyncSession) -> None:
    emp = await setup(session)
    assert (await monday(session, emp)).late_sec == 3600


async def test_edit_12h_ahead_applies_by_itself(session: AsyncSession) -> None:
    emp = await setup(session)
    await edit_schedule(session, local(date(2026, 10, 18), 21, 30))  # пн с 10:00 → срок до 22:00
    cell = await monday(session, emp)
    assert cell.late_sec == 0
    assert cell.plan is not None and cell.plan.start == 11 * 3600
    assert "plan_late_edit" not in cell.flags
    assert "late_change" not in await inbox_items(session)


@pytest.mark.parametrize("at", [local(date(2026, 10, 18), 23), local(MONDAY, 10, 30)])
async def test_late_edit_waits_for_admin(session: AsyncSession, at: datetime) -> None:
    emp = await setup(session)
    await edit_schedule(session, at)
    cell = await monday(session, emp)
    assert cell.late_sec == 3600
    assert cell.plan is not None and cell.plan.start == 10 * 3600
    assert "plan_late_edit" in cell.flags

    inbox = await messages.inbox(session)
    late = [item for item in inbox.items if any(i.code == "late_change" for i in item.parse.issues)]
    assert len(late) == 1
    await manual.resolve_parse(session, late[0].parse.id, Resolution.ACCEPTED, actor="admin")
    cell = await monday(session, emp)
    assert cell.late_sec == 0
    assert "plan_late_edit" not in cell.flags


async def test_notice_hours_setting(session: AsyncSession) -> None:
    emp = await setup(session)
    await edit_schedule(session, local(MONDAY, 9, 30))
    relaxed = SETTINGS.model_copy(update={"plan_notice_hours": 0})
    week = await reports.week_report(session, relaxed, 2026, 43)
    assert next(r for r in week.rows if r.employee.id == emp).cells[0].late_sec == 0


async def test_approval_does_not_approve_another_edit_with_same_timestamp(
    session: AsyncSession,
) -> None:
    emp = await setup(session)
    at = local(MONDAY, 10, 30)
    await edit_schedule(session, at)
    pending = await messages.inbox(session)
    target = next(
        item for item in pending.items if item.plan_change and item.plan_change.late_change
    )
    await manual.resolve_parse(session, target.parse.id, Resolution.ACCEPTED, actor="admin")
    assert (await monday(session, emp)).plan.start == 11 * 3600
    msg = f.message(
        f.schedule_text(sprint="19.10 - 24.10", Пн="12:00 - 20:00"),
        thread=f.SCHEDULE_THREAD,
        message_id=SCHEDULE_ID,
        sent_at=local(date(2026, 10, 18), 20),
    )
    await ingest(session, replace(msg, edited_at=at), SETTINGS)
    cell = await monday(session, emp)
    assert cell.plan is not None and cell.plan.start == 11 * 3600
    pending = await messages.inbox(session)
    target = next(
        item for item in pending.items if item.plan_change and item.plan_change.late_change
    )
    change = next(day for day in target.plan_change.days if day.date == MONDAY)
    assert change.affects_calculation is True
    assert change.if_accepted.plan and change.if_accepted.plan.start == 12 * 3600


async def test_admin_edit_always_applies(session: AsyncSession) -> None:
    emp = await setup(session)
    await edit_schedule(session, local(MONDAY, 10, 30))
    await manual.set_plan_day(
        session,
        employee_id=emp,
        day=MONDAY,
        kind=PlanDayKind.WORK,
        intervals=[(11 * 3600, 19 * 3600)],
        actor="admin",
    )
    assert (await monday(session, emp)).late_sec == 0


async def test_reparse_pending_clears_fixed_items(session: AsyncSession) -> None:
    await f.forum(session)
    e = await f.employee(session, "Петров П.П.")
    await ingest(session, f.message(f.daily_text(), author=777), SETTINGS)
    inbox = await messages.inbox(session)
    assert inbox.counts["pending"] == 1
    # Аккаунт связали в обход привязки — переразбор подхватывает это сам.
    identity = await session.scalar(
        select(TelegramIdentity).where(TelegramIdentity.telegram_user_id == 777)
    )
    assert identity is not None
    identity.employee_id = e.id
    assert await manual.reparse_pending(session, SETTINGS, actor="admin") == 1
    assert (await messages.inbox(session)).counts["pending"] == 0
