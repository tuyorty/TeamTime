"""Ручная правка одного дня не одобряет спорные дни и не теряется при правке в Telegram."""

from dataclasses import replace
from datetime import UTC, date, datetime

import pytest

from teamtime.core import clock
from teamtime.db.models import ParseResultRow, Resolution
from teamtime.parsing import PlanDayKind
from teamtime.services import manual
from teamtime.services.facts import load_cells
from teamtime.services.ingest import ingest
from teamtime.services.schedule_changes import schedule_change_preview
from teamtime.services.settings import AppSettings
from tests import factories as f

pytestmark = pytest.mark.db
SENT = datetime(2026, 11, 8, 8, tzinfo=UTC)
EDITED = datetime(2026, 11, 11, 8, tzinfo=UTC)
ADMIN = datetime(2026, 11, 11, 9, tzinfo=UTC)
FOLLOWUP = datetime(2026, 11, 11, 10, tzinfo=UTC)
TUESDAY = date(2026, 11, 10)
THURSDAY = date(2026, 11, 12)
SETTINGS = AppSettings()


def schedule(tuesday="17:00 - 20:00", task="Исходная задача"):
    return f"""#расписание
Спринт 09.11 - 15.11
Иванов И.И.
ПН: —
ВТ: {tuesday}
СР: 10:00 - 18:00
ЧТ: 17:00 - 20:00
ПТ: —
СБ: —
ВС: —
Задачи:
- {task}
"""


async def setup(session):
    clock.freeze(SENT)
    await f.forum(session)
    employee = await f.employee(session, tg_id=501)
    message = f.message(schedule(), thread=f.SCHEDULE_THREAD, sent_at=SENT)
    await ingest(session, message, SETTINGS)
    return employee, message


async def edit(session, message, text, at):
    clock.freeze(at)
    return await ingest(session, replace(message, text=text, edited_at=at), SETTINGS)


async def planned_tuesday(session, employee):
    return (await load_cells(session, SETTINGS, TUESDAY, TUESDAY, [employee.id]))[
        employee.id, TUESDAY
    ]


async def test_editing_thursday_does_not_approve_pending_tuesday_or_later_task_edit(session):
    employee, message = await setup(session)
    await edit(session, message, schedule("—", "Новая задача"), EDITED)
    assert (await planned_tuesday(session, employee)).result.planned == 3 * 3600
    clock.freeze(ADMIN)
    changed = await manual.set_plan_day(
        session,
        employee_id=employee.id,
        day=THURSDAY,
        kind=PlanDayKind.WORK,
        intervals=[(18 * 3600, 20 * 3600)],
        actor="admin",
        reason="Уточнили только четверг",
    )
    # Воспроизводим хронологию событий независимо от текущего времени тестовой БД.
    changed.created_at = ADMIN
    await session.flush()
    cell = await planned_tuesday(session, employee)
    assert cell.result.planned == 3 * 3600
    assert [task.text for task in changed.tasks] == ["Новая задача"]
    result = await edit(session, message, schedule("—", "Ещё одна задача"), FOLLOWUP)
    assert any(issue.code == "late_change" for issue in result.issues)
    cell = await planned_tuesday(session, employee)
    assert cell.result.planned == 3 * 3600
    assert cell.late_edit is not None


@pytest.mark.parametrize("kind", [PlanDayKind.OFF, None])
async def test_later_telegram_edit_does_not_restore_manually_removed_past_day(session, kind):
    employee, message = await setup(session)
    clock.freeze(ADMIN)
    changed = await manual.set_plan_day(
        session,
        employee_id=employee.id,
        day=TUESDAY,
        kind=kind,
        intervals=[],
        actor="admin",
        reason="Отменили прошлую смену по согласованию",
    )
    changed.created_at = ADMIN
    await session.flush()
    await edit(session, message, schedule(task="Обновили только задачу"), FOLLOWUP)
    cell = await planned_tuesday(session, employee)
    assert cell.result.planned is None
    assert cell.plan_day is None if kind is None else cell.plan_day.kind is PlanDayKind.OFF
    assert cell.late_edit is not None


async def test_preview_keeps_submitted_version_and_approval_preserves_later_manual_plan(session):
    employee, message = await setup(session)
    submitted = await edit(session, message, schedule("—", "Новая задача"), EDITED)
    clock.freeze(ADMIN)
    changed = await manual.set_plan_day(
        session,
        employee_id=employee.id,
        day=THURSDAY,
        kind=PlanDayKind.WORK,
        intervals=[(18 * 3600, 20 * 3600)],
        actor="admin",
        reason="Уточнили только четверг",
    )
    changed.created_at = ADMIN
    await session.flush()
    parse = await session.get(ParseResultRow, submitted.parse_result_id)
    preview = await schedule_change_preview(session, parse, SETTINGS)
    assert preview is not None
    assert preview.version == 2 and preview.plan_id != changed.id
    assert preview.previous_version == 1
    assert preview.tasks_added == ["Новая задача"]
    assert preview.tasks_removed == ["Исходная задача"]
    tuesday = next(day for day in preview.days if day.date == TUESDAY)
    assert tuesday.previous.kind is PlanDayKind.WORK
    assert tuesday.submitted.kind is PlanDayKind.OFF
    assert tuesday.current.plan.planned_sec == tuesday.if_accepted.plan.planned_sec == 3 * 3600
    assert not tuesday.affects_calculation
    assert "не заменит ручной план" in tuesday.approval_note
    await manual.resolve_parse(session, parse.id, Resolution.ACCEPTED, actor="admin")
    cell = await planned_tuesday(session, employee)
    assert cell.plan.id == changed.id
    assert cell.result.planned == 3 * 3600
