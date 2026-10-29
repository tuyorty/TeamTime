"""Отчёты из базы: сквозной золотой месяц (сообщения → итог), неделя, сегодня, правки."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.calc import DayState, StatusKind, format_hm
from teamtime.db.models import AuditLog
from teamtime.parsing import PlanDayKind
from teamtime.services import manual, reports
from teamtime.services.ingest import ingest
from teamtime.services.settings import AppSettings
from tests import factories as f

pytestmark = pytest.mark.db
SETTINGS = AppSettings()


def sent(day: int, month: int = 10, hour: int = 15) -> datetime:
    return datetime(2026, month, day, hour, 0, tzinfo=UTC)


async def golden_october(session: AsyncSession) -> int:
    """Тот же месяц, что в tests/calc/test_month.py, но через сообщения в Telegram."""
    await f.forum(session)
    e = await f.employee(session, "Орлова О.О.", norm_hours=20, rate=500, tg_id=900)
    # 40 неделя: 28.09–04.10, 41 неделя: 05.10–11.10.
    await ingest(
        session,
        f.message(
            f.schedule_text(
                "Орлова О.О.",
                "28.09 - 03.10",
                Чт="10:00 - 18:00",
                Пт="10:00 - 18:00",
                Сб="по вайбу",
            ),
            author=900,
            thread=f.SCHEDULE_THREAD,
            sent_at=sent(27, 9),
        ),
    )
    await ingest(
        session,
        f.message(
            f.schedule_text(
                "Орлова О.О.",
                "05.10 - 10.10",
                Пн="9:00 - 17:00",
                Вт="10:00 - 18:00",
                Ср="10:00 - 18:00",
                Чт="10:00 - 18:00",
            ),
            author=900,
            thread=f.SCHEDULE_THREAD,
            sent_at=sent(4),
        ),
    )
    for day, spans, eff in [
        ("01.10.2026", "10:20 - 18:00", 80),
        ("02.10.2026", "9:55 - 18:05", 100),
        ("03.10.2026", "12:00 - 17:00", 60),
        ("05.10.2026", "11:00 - 13:00; 14:00 - 17:30", 70),
        ("08.10.2026", "13:20 - 19:00", 90),
    ]:
        d = int(day[:2])
        await ingest(session, f.message(f.daily_text(day, spans, eff), author=900, sent_at=sent(d)))
    await manual.set_status(
        session, employee_id=e.id, day=date(2026, 10, 6), kind=StatusKind.VACATION, actor="admin"
    )
    return e.id


async def test_golden_month_from_messages(session: AsyncSession) -> None:
    emp_id = await golden_october(session)
    month = await reports.month_report(session, SETTINGS, 2026, 10, history=2)
    row = next(r for r in month.rows if r.employee.id == emp_id)
    s = row.summary
    assert format_hm(s.worked_sec) == "32:00"
    assert format_hm(s.result_sec) == "26:15"
    assert format_hm(s.late_total_sec) == "5:40"
    assert s.late_count == 3
    assert format_hm(s.penalty_sec) == "5:45"
    assert format_hm(s.total_sec) == "20:29"
    assert format_hm(s.overtime_sec) == "0:29"
    assert s.bonus == Decimal("244.05")
    assert s.days_missing == 1  # 07.10: план был, дейлика нет
    assert s.days_no_plan == 1  # 03.10: «по вайбу»
    assert s.statuses == {"vacation": 1}
    assert [(d.date.day, format_hm(d.late_sec)) for d in row.late_days] == [
        (1, "0:20"),
        (5, "2:00"),
        (8, "3:20"),
    ]
    assert month.scale.problems == []
    assert [h.month for h in month.history] == [10]  # сентябрь пустой — в историю не попадает
    kinds = {(d.date.day, d.kind) for d in month.deviations}
    assert (8, "late") in kinds and (7, "missing_daily") in kinds


async def test_week_report_cells_and_totals(session: AsyncSession) -> None:
    emp_id = await golden_october(session)
    week = await reports.week_report(session, SETTINGS, 2026, 41)
    assert week.label == "41 неделя"
    assert week.days[0] == date(2026, 10, 5)
    row = next(r for r in week.rows if r.employee.id == emp_id)
    states = [c.state for c in row.cells]
    assert states == [
        DayState.WORKED,
        DayState.ABSENCE,
        DayState.MISSING,
        DayState.WORKED,
        DayState.UNPLANNED,
        DayState.UNPLANNED,
        DayState.OFF,
    ]
    monday = row.cells[0]
    assert monday.plan is not None and monday.plan.start == 9 * 3600
    assert monday.fact is not None and monday.fact.intervals == [(39600, 46800), (50400, 63000)]
    assert format_hm(monday.fact.result_sec) == "3:51"
    assert format_hm(monday.late_sec) == "2:00"
    assert monday.source.daily_raw_message_id is not None
    assert row.plan is not None and row.plan.tasks == ["задача один", "задача два"]
    assert format_hm(row.totals.worked_sec) == "11:10"
    assert row.totals.late_count == 2


async def test_manual_fact_edit_is_versioned_and_audited(session: AsyncSession) -> None:
    emp_id = await golden_october(session)
    await manual.set_daily(
        session,
        employee_id=emp_id,
        work_date=date(2026, 10, 8),
        intervals=[(10 * 3600, 19 * 3600)],
        efficiency=manual.KEEP,
        actor="admin",
        reason="опоздание по согласованию",
    )
    week = await reports.week_report(session, SETTINGS, 2026, 41)
    thursday = next(r for r in week.rows if r.employee.id == emp_id).cells[3]
    assert thursday.late_sec == 0
    assert thursday.fact is not None and thursday.fact.efficiency == 90
    assert thursday.fact.source.value == "manual"
    entry = await session.scalar(select(AuditLog).where(AuditLog.action == "daily.set"))
    assert entry is not None
    assert entry.before is not None and entry.before["intervals"] == [[48000, 68400]]
    assert entry.after is not None and entry.after["intervals"] == [[36000, 68400]]
    assert entry.reason == "опоздание по согласованию"


async def test_manual_plan_day_edit_makes_new_plan_version(session: AsyncSession) -> None:
    emp_id = await golden_october(session)
    await manual.set_plan_day(
        session, employee_id=emp_id, day=date(2026, 10, 7), kind=PlanDayKind.OFF, actor="admin"
    )
    plans = await reports.plans_report(session, SETTINGS, 2026, 41)
    row = next(r for r in plans.rows if r.employee.id == emp_id)
    assert [v.version for v in row.versions] == [1, 2]
    assert row.current is not None and row.current.source.value == "manual"
    week = await reports.week_report(session, SETTINGS, 2026, 41)
    assert next(r for r in week.rows if r.employee.id == emp_id).cells[2].state is DayState.OFF


async def test_status_range_and_clear(session: AsyncSession) -> None:
    emp_id = await golden_october(session)
    n = await manual.set_status_range(
        session,
        employee_id=emp_id,
        start=date(2026, 10, 12),
        end=date(2026, 10, 16),
        kind=StatusKind.SICK,
        actor="admin",
    )
    assert n == 5
    await manual.set_status(
        session, employee_id=emp_id, day=date(2026, 10, 14), kind=None, actor="admin"
    )
    week = await reports.week_report(session, SETTINGS, 2026, 42)
    statuses = [c.status for c in next(r for r in week.rows if r.employee.id == emp_id).cells]
    assert statuses[:5] == [
        StatusKind.SICK,
        StatusKind.SICK,
        None,
        StatusKind.SICK,
        StatusKind.SICK,
    ]


async def test_today_report(session: AsyncSession) -> None:
    await f.forum(session)
    await f.employee(session, "Иванов И.И.", tg_id=501)
    await f.employee(session, "Петров П.П.", tg_id=502)
    await ingest(
        session,
        f.message(
            f.schedule_text("Иванов И.И.", Пн="10:00 - 18:00"),
            thread=f.SCHEDULE_THREAD,
            sent_at=sent(25),
        ),
    )
    await ingest(
        session,
        f.message(
            f.schedule_text("Петров П.П.", Пн="14:00 - 20:00"),
            thread=f.SCHEDULE_THREAD,
            sent_at=sent(25),
        ),
    )
    today = await reports.today_report(session, SETTINGS)  # 26.10, 12:00
    presence = {r.employee.short_name: r.presence for r in today.rows}
    assert presence == {"Иванов И.И.": "on_site", "Петров П.П.": "expected_later"}
    assert today.counts["planned"] == 2
    assert today.counts["awaiting_daily"] == 2
    assert len(today.feed) == 2
    assert today.feed[0].summary.startswith("Расписание на 44 неделю")


async def test_today_accounts_for_every_employee_and_returns_schedule_tasks(
    session: AsyncSession,
) -> None:
    """Выходные и отсутствие расписания не теряются в сумме категорий."""
    await f.forum(session)
    entries = [
        ("Иванов И.И.", "10:00 - 18:00", None, "on_site"),
        ("Петров П.П.", "14:00 - 20:00", None, "expected_later"),
        ("Сидоров С.С.", "08:00 - 10:00", None, "left"),
        ("Орлов О.О.", "выходной", None, "off"),
        ("Кузнецов К.К.", None, None, "no_plan"),
        ("Смирнов С.С.", "10:00 - 18:00", StatusKind.REMOTE, "remote"),
        ("Лебедев Л.Л.", "10:00 - 18:00", StatusKind.SICK, "absent"),
        ("Волков В.В.", None, StatusKind.OFF, "off"),
        ("Зайцев З.З.", "14:00 - 20:00", StatusKind.REMOTE, "expected_later"),
    ]
    for index, (name, plan, status, _) in enumerate(entries, 501):
        employee = await f.employee(session, name, tg_id=index)
        if plan:
            await ingest(
                session,
                f.message(
                    f.schedule_text(name, Пн=plan),
                    author=index,
                    thread=f.SCHEDULE_THREAD,
                    sent_at=sent(25),
                ),
            )
        if status:
            await manual.set_status(
                session,
                employee_id=employee.id,
                day=date(2026, 10, 26),
                kind=status,
                actor="test",
            )
    inactive = await f.employee(session, "Захаров З.З.")
    inactive.is_active = False
    await ingest(session, f.message(f.daily_text("26.10.2026")))
    today = await reports.today_report(session, SETTINGS)
    assert {row.employee.short_name: row.presence for row in today.rows} == {
        name: presence for name, _, _, presence in entries
    }
    categories = ("on_site", "remote", "expected_later", "left", "off", "absent", "no_plan")
    assert sum(today.counts.get(key, 0) for key in categories) == today.counts["total"] == 9
    assert today.counts["off"] == 2
    first = next(row for row in today.rows if row.employee.short_name == "Иванов И.И.")
    assert first.tasks == ["задача один", "задача два"]
    assert first.cell.fact is not None
    assert all(item.kind.value == "schedule" for item in today.feed)


async def test_employee_notes_include_workday_remarks_and_manual_status(
    session: AsyncSession,
) -> None:
    employee = await f.employee(session)
    await manual.set_plan_day(
        session,
        employee_id=employee.id,
        day=date(2026, 10, 20),
        kind=PlanDayKind.WORK,
        intervals=[(9 * 3600, 18 * 3600)],
        note="Встреча в мастерской",
        actor="admin",
    )
    await manual.set_status(
        session,
        employee_id=employee.id,
        day=date(2026, 10, 21),
        kind=StatusKind.REMOTE,
        note="Работаю из дома",
        actor="admin",
    )
    report = await reports.employee_report(
        session, SETTINGS, employee, date(2026, 10, 19), date(2026, 10, 25)
    )
    assert [(item.date.day, item.kind, item.text) for item in report.notes] == [
        (21, "status", "Работаю из дома"),
        (20, "plan_note", "Встреча в мастерской"),
    ]
    outside = await reports.employee_report(
        session, SETTINGS, employee, date(2026, 10, 22), date(2026, 10, 25)
    )
    assert outside.notes == []
