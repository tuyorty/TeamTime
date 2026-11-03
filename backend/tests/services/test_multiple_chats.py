from dataclasses import replace
from datetime import date

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.db.models import BotChat, DayStatus, RawMessage, TopicBinding, TopicKind
from teamtime.services.ingest import ingest
from teamtime.services.reports import today_report
from teamtime.services.settings import AppSettings
from tests import factories as f

pytestmark = pytest.mark.db


async def test_two_departments_share_board_without_chat_or_topic_id_collisions(
    session: AsyncSession,
):
    await f.forum(session)
    office = await f.employee(session, "Иванов И.И.", tg_id=501)
    lab = await f.employee(session, "Петров П.П.", tg_id=777)
    lab_chat = -1009999999999
    session.add(BotChat(chat_id=lab_chat, title="Лаборатория", is_forum=True, approved=True))
    await session.flush()
    session.add_all(
        [
            TopicBinding(chat_id=lab_chat, thread_id=f.SCHEDULE_THREAD, kind=TopicKind.SCHEDULE),
            TopicBinding(chat_id=lab_chat, thread_id=f.DAILY_THREAD, kind=TopicKind.DAILY),
        ]
    )
    await session.flush()
    for employee, chat_id, author in [(office, f.CHAT, 501), (lab, lab_chat, 777)]:
        schedule = replace(
            f.message(
                f.schedule_text(
                    employee.short_name, Пн="10:00 - 12:00; 13:00 - 17:00; 20:00 - 23:00"
                ),
                thread=f.SCHEDULE_THREAD,
                message_id=42,
                author=author,
            ),
            chat_id=chat_id,
        )
        daily = replace(
            f.message(
                f.daily_text("26.10.2026", "10:00 - 12:00; 13:00 - 17:00; 20:00 - 23:00", 85),
                message_id=43,
                author=author,
            ),
            chat_id=chat_id,
        )
        assert (await ingest(session, schedule)).employee_id == employee.id
        assert (await ingest(session, daily)).employee_id == employee.id
    report = await today_report(session, AppSettings(), date(2026, 10, 26))
    assert {row.employee.id for row in report.rows} == {office.id, lab.id}
    assert await session.scalar(select(func.count()).select_from(RawMessage)) == 4
    for row in report.rows:
        assert row.cell.plan is not None and row.cell.fact is not None
        assert len(row.cell.plan.intervals) == len(row.cell.fact.intervals) == 3
        assert row.cell.plan.planned_sec == row.cell.fact.worked_sec == 9 * 3600


async def test_weekly_vacation_is_visible_on_board_without_creating_manual_statuses(
    session: AsyncSession,
):
    await f.forum(session)
    employee = await f.employee(session, tg_id=501)
    await ingest(
        session,
        f.message(
            "#расписание\nСпринт 26.10 - 01.11\nИванов И.И.\nПН - ВС: отпуск",
            thread=f.SCHEDULE_THREAD,
        ),
    )
    report = await today_report(session, AppSettings(), date(2026, 10, 26))
    row = next(row for row in report.rows if row.employee.id == employee.id)
    assert row.presence == "absent"
    assert row.cell.status == "vacation"
    assert row.cell.status_label == "Отпуск"
    assert row.cell.state == "absence"
    assert await session.scalar(select(func.count()).select_from(DayStatus)) == 0
