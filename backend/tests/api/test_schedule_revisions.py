"""Правки сохраняют неделю, обновляют задачи и не отменяют спорный рабочий день молча."""

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from teamtime.core import clock
from teamtime.db.models import Resolution
from teamtime.parsing import ParseStatus
from teamtime.services import manual, reports
from teamtime.services.facts import load_cells
from teamtime.services.ingest import ingest
from teamtime.services.settings import AppSettings
from tests import factories as f

pytestmark = pytest.mark.db
SENT = datetime(2026, 11, 8, 8, tzinfo=UTC)
EDITED = datetime(2026, 11, 11, 8, tzinfo=UTC)
START, END = date(2026, 11, 9), date(2026, 11, 15)
SETTINGS = AppSettings()


def schedule(tuesday="17:00 - 20:00", task="Исходная задача"):
    return f"""#расписание
Спринт 09.11 - 15.11
Иванов И.И.
ПН: —————
ВТ: {tuesday}
Задачи перенесены на среду.
СР: 10:00 - 18:00
- {task}
ЧТ: 17:00 - 20:00
- Подготовить отчёт
ПТ: —————
Резерв на правки.
СБ: 09:30 - 20:00
- Проверить результаты
ВС: —————
"""


async def setup(session):
    clock.freeze(EDITED)
    await f.forum(session)
    employee = await f.employee(session, tg_id=501)
    message = f.message(schedule(), thread=f.SCHEDULE_THREAD, sent_at=SENT)
    first = await ingest(session, message)
    return employee, message, first


async def edit(session, message, text):
    return await ingest(
        session,
        replace(
            f.message(
                text,
                thread=f.SCHEDULE_THREAD,
                sent_at=SENT,
                message_id=message.message_id,
                edited=True,
            ),
            edited_at=EDITED,
        ),
    )


async def test_late_one_day_keeps_week_but_uses_latest_tasks(session):
    employee, message, _ = await setup(session)
    result = await edit(session, message, schedule("—————", "Новая задача"))
    assert result.status == ParseStatus.PARTIAL
    assert any(i.code == "late_change" for i in result.issues)
    for _ in range(2):
        cells = await load_cells(session, SETTINGS, START, END, [employee.id])
        assert cells[(employee.id, date(2026, 11, 10))].result.planned == 3 * 3600
        assert cells[(employee.id, date(2026, 11, 11))].result.planned == 8 * 3600
        week = await reports.week_report(session, SETTINGS, 2026, 46)
        assert "Новая задача" in week.rows[0].plan.tasks
        assert "Исходная задача" not in week.rows[0].plan.tasks
        today = await reports.today_report(session, SETTINGS, date(2026, 11, 10))
        assert "Новая задача" in today.rows[0].tasks
        result = await manual.reparse(session, result.parse_result_id, SETTINGS, actor="admin")
        assert any(i.code == "late_change" for i in result.issues)


async def test_ignore_edit_keeps_previous_and_accept_restores_selected_revision(session):
    employee, message, _ = await setup(session)
    edited = await edit(session, message, schedule("—————", "Новая задача"))
    await manual.resolve_parse(session, edited.parse_result_id, Resolution.IGNORED, actor="admin")
    week = await reports.week_report(session, SETTINGS, 2026, 46)
    assert week.rows[0].cells[1].plan.planned_sec == 3 * 3600
    assert "Исходная задача" in week.rows[0].plan.tasks
    await manual.resolve_parse(session, edited.parse_result_id, Resolution.ACCEPTED, actor="admin")
    week = await reports.week_report(session, SETTINGS, 2026, 46)
    assert week.rows[0].cells[1].plan.kind.value == "off"
    assert "Новая задача" in week.rows[0].plan.tasks
    await manual.reparse(session, edited.parse_result_id, SETTINGS, actor="admin")
    cells = await load_cells(session, SETTINGS, START, END, [employee.id])
    assert cells[(employee.id, date(2026, 11, 10))].plan_day.kind.value == "off"


async def test_broken_edit_preserves_valid_schedule_and_new_text_recovers(session):
    _, message, _ = await setup(session)
    failed = await edit(
        session, message, "#расписание\nСпринт 99.99 - 99.99\nИванов И.И.\nСР: 10:00 - 18:00"
    )
    assert failed.status == ParseStatus.FAILED
    week = await reports.week_report(session, SETTINGS, 2026, 46)
    assert week.rows[0].cells[2].plan.planned_sec == 8 * 3600
    await edit(session, message, schedule(task="Исправленная задача"))
    week = await reports.week_report(session, SETTINGS, 2026, 46)
    assert "Исправленная задача" in week.rows[0].plan.tasks


async def test_task_only_followup_does_not_approve_pending_day(session):
    employee, message, _ = await setup(session)
    await edit(session, message, schedule("—————", "Новая задача"))
    result = await edit(session, message, schedule("—————", "Уточнённая задача"))
    assert any(i.code == "late_change" for i in result.issues)
    cells = await load_cells(session, SETTINGS, START, END, [employee.id])
    assert cells[(employee.id, date(2026, 11, 10))].result.planned == 3 * 3600
    plans = await reports.plans_report(session, SETTINGS, 2026, 46)
    assert plans.rows[0].versions[0].stated_at == SENT
    assert plans.rows[0].versions[-1].stated_at == EDITED


async def test_preview_of_retracted_plan_matches_accepting_it(session):
    """Прежняя ошибка могла отозвать всю неделю; предпросмотр показывает восстановление."""
    from sqlalchemy import select

    from teamtime.db.models import ParseResultRow, SchedulePlan
    from teamtime.services.schedule_changes import schedule_change_preview

    employee, message, _ = await setup(session)
    result = await edit(session, message, schedule("—————", "Новая задача"))
    for plan in await session.scalars(select(SchedulePlan)):
        plan.retracted_at = EDITED
    await session.flush()
    row = await session.get(ParseResultRow, result.parse_result_id)
    preview = await schedule_change_preview(session, row, SETTINGS)
    wednesday = next(day for day in preview.days if day.date == date(2026, 11, 11))
    assert wednesday.current.plan is None
    assert wednesday.if_accepted.plan.planned_sec == 8 * 3600
    assert wednesday.affects_calculation
    await manual.resolve_parse(session, row.id, Resolution.ACCEPTED, actor="admin")
    cells = await load_cells(session, SETTINGS, START, END, [employee.id])
    assert cells[(employee.id, date(2026, 11, 11))].result.planned == 8 * 3600


async def test_first_seen_edit_preserves_telegram_edit_time(session):
    """Если исходный текст не был получен, не выдаём правку за исходное расписание."""
    clock.freeze(EDITED)
    await f.forum(session)
    await f.employee(session, tg_id=501)
    message = replace(
        f.message(schedule(), thread=f.SCHEDULE_THREAD, sent_at=SENT), edited_at=EDITED
    )
    outcome = await ingest(session, message)
    assert outcome.is_edit
    report = await reports.plans_report(session, SETTINGS, 2026, 46)
    version = report.rows[0].versions[0]
    assert version.edited
    assert version.stated_at == EDITED
