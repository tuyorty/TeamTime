"""Приём сообщений: исходники, версии, сопоставление, правки, идемпотентность."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.db.models import (
    Daily,
    ParseResultRow,
    RawMessage,
    RawMessageVersion,
    Resolution,
    SchedulePlan,
    TelegramIdentity,
)
from teamtime.parsing import MessageKind, ParseStatus
from teamtime.services.facts import current_dailies, current_plans
from teamtime.services.ingest import ingest
from teamtime.services.manual import link_identity
from teamtime.services.settings import AppSettings
from tests import factories as f

pytestmark = pytest.mark.db
SETTINGS = AppSettings()


async def count(session: AsyncSession, model: type) -> int:
    return await session.scalar(select(func.count()).select_from(model)) or 0


async def test_schedule_matched_by_name_line_not_by_sender(session: AsyncSession) -> None:
    await f.forum(session)
    ivanov = await f.employee(session, "Иванов И.И.")
    out = await ingest(session, f.message(f.schedule_text(), thread=f.SCHEDULE_THREAD, name="😎"))
    assert out.kind is MessageKind.SCHEDULE
    assert out.status is ParseStatus.OK
    assert out.employee_id == ivanov.id
    assert not out.needs_attention
    plans = await current_plans(session, date(2026, 10, 26), date(2026, 11, 1))
    assert len(plans) == 1
    assert (plans[0].iso_week, plans[0].version) == (44, 1)
    assert [d.date for d in plans[0].days] == [date(2026, 10, 26), date(2026, 10, 27)]
    assert [t.text for t in plans[0].tasks] == ["задача один", "задача два"]
    # Отправитель не был привязан — бот предложил кандидата, но не привязал сам.
    identity = await session.scalar(select(TelegramIdentity))
    assert identity is not None
    assert identity.employee_id is None
    assert identity.suggested_employee_id == ivanov.id


async def test_daily_requires_linked_identity_then_reprocesses(session: AsyncSession) -> None:
    await f.forum(session)
    ivanov = await f.employee(session, "Иванов И.И.")
    out = await ingest(session, f.message(f.daily_text(), author=777))
    assert out.employee_unresolved
    assert out.needs_attention
    assert "identity_not_linked" in {i.code for i in out.issues}
    assert await count(session, Daily) == 0
    row = await session.get(ParseResultRow, out.parse_result_id)
    assert row is not None and row.resolution is Resolution.PENDING

    identity = await session.scalar(
        select(TelegramIdentity).where(TelegramIdentity.telegram_user_id == 777)
    )
    assert identity is not None
    report = await link_identity(session, identity.id, ivanov.id, SETTINGS, actor="admin")
    assert report.reprocessed == 1
    dailies = await current_dailies(session, date(2026, 10, 23), date(2026, 10, 23))
    assert len(dailies) == 1
    assert dailies[0].employee_id == ivanov.id
    assert dailies[0].efficiency == 80


async def test_resend_same_text_is_idempotent(session: AsyncSession) -> None:
    await f.forum(session)
    await f.employee(session, tg_id=501)
    msg = f.message(f.daily_text())
    first = await ingest(session, msg)
    again = await ingest(session, msg)
    assert again.changed is False
    assert again.parse_result_id == first.parse_result_id
    assert await count(session, RawMessage) == 1
    assert await count(session, RawMessageVersion) == 1
    assert await count(session, Daily) == 1


async def test_edit_creates_new_versions_and_keeps_history(session: AsyncSession) -> None:
    await f.forum(session)
    await f.employee(session, tg_id=501)
    msg = f.message(f.daily_text(e=70), message_id=42)
    await ingest(session, msg)
    edited = f.message(f.daily_text(e=90), message_id=42, edited=True)
    out = await ingest(session, edited)
    assert out.is_edit
    assert out.status is ParseStatus.OK
    versions = list(
        await session.scalars(select(RawMessageVersion).order_by(RawMessageVersion.version))
    )
    assert [v.version for v in versions] == [1, 2]
    assert "Эффективность: 70%" in versions[0].text  # исходник не перезаписан
    dailies = list(await session.scalars(select(Daily).order_by(Daily.version)))
    assert [(d.version, d.efficiency, d.retracted_at is None, d.edited) for d in dailies] == [
        (1, 70, False, False),
        (2, 90, True, True),
    ]
    current = await current_dailies(session, date(2026, 10, 23), date(2026, 10, 23))
    assert current[0].efficiency == 90


async def test_edit_moving_date_restores_previous_version_on_old_date(
    session: AsyncSession,
) -> None:
    await f.forum(session)
    await f.employee(session, tg_id=501)
    await ingest(session, f.message(f.daily_text("22.10.2026", e=60), message_id=1))
    await ingest(
        session, f.message(f.daily_text("22.10.2026", e=75), message_id=2)
    )  # второй за ту же дату
    await ingest(session, f.message(f.daily_text("21.10.2026", e=75), message_id=2, edited=True))
    current = {
        d.work_date: d.efficiency
        for d in await current_dailies(session, date(2026, 10, 20), date(2026, 10, 25))
    }
    assert current == {date(2026, 10, 21): 75, date(2026, 10, 22): 60}


async def test_second_daily_same_date_replaces(session: AsyncSession) -> None:
    await f.forum(session)
    await f.employee(session, tg_id=501)
    await ingest(session, f.message(f.daily_text(e=60)))
    await ingest(session, f.message(f.daily_text(spans="11:00 - 19:00", e=60)))
    current = await current_dailies(session, date(2026, 10, 23), date(2026, 10, 23))
    assert len(current) == 1
    assert current[0].version == 2
    assert current[0].intervals[0].start_sec == 11 * 3600


async def test_new_schedule_same_week_is_new_plan_version(session: AsyncSession) -> None:
    await f.forum(session)
    await f.employee(session)
    await ingest(session, f.message(f.schedule_text(), thread=f.SCHEDULE_THREAD))
    await ingest(session, f.message(f.schedule_text(Пн="12:00 - 18:00"), thread=f.SCHEDULE_THREAD))
    plans = list(await session.scalars(select(SchedulePlan).order_by(SchedulePlan.version)))
    assert [p.version for p in plans] == [1, 2]
    current = await current_plans(session, date(2026, 10, 26), date(2026, 11, 1))
    assert current[0].version == 2
    assert current[0].days[0].start_sec == 12 * 3600


async def test_unknown_employee_suggests_candidates(session: AsyncSession) -> None:
    await f.forum(session)
    await f.employee(session, "Иванов И.И.")
    await f.employee(session, "Иванов А.П.")
    out = await ingest(session, f.message(f.schedule_text("Иванов Б.Б."), thread=f.SCHEDULE_THREAD))
    assert out.employee_unresolved
    assert out.status is ParseStatus.PARTIAL
    assert sorted(out.candidates) == ["Иванов А.П.", "Иванов И.И."]
    assert await count(session, SchedulePlan) == 0


async def test_chatter_in_bound_topic_is_stored_but_ignored(session: AsyncSession) -> None:
    await f.forum(session)
    out = await ingest(session, f.message("всем привет, кто сегодня в офисе?"))
    assert out.kind is MessageKind.UNKNOWN
    assert not out.needs_attention
    row = await session.get(ParseResultRow, out.parse_result_id)
    assert row is not None and row.resolution is Resolution.IGNORED


async def test_unrelated_chat_message_is_not_stored(session: AsyncSession) -> None:
    out = await ingest(session, f.message("просто болтовня", thread=999))
    assert out.skipped == "not_relevant"
    assert await count(session, RawMessage) == 0


async def test_hashtag_works_without_topic_binding(session: AsyncSession) -> None:
    await f.employee(session, tg_id=501)
    out = await ingest(session, f.message(f.daily_text(), thread=None))
    assert out.kind is MessageKind.DAILY
    assert out.status is ParseStatus.OK


async def test_failed_message_creates_nothing_but_is_in_inbox(session: AsyncSession) -> None:
    await f.forum(session)
    await f.employee(session, tg_id=501)
    out = await ingest(session, f.message("23.10.2026\nработал весь день\n#дейли"))
    assert out.status is ParseStatus.FAILED
    assert out.needs_attention
    assert await count(session, Daily) == 0
