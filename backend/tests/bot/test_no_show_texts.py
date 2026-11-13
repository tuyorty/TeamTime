"""Невыход в отчётах не изображает вымышленный приход и не требует дейлик."""

from datetime import date, datetime

from teamtime.bot import texts
from teamtime.schemas import DayCellOut, EmployeeBrief, TodayOut, TodayRow, WeekOut, WeekRow


def confirmed_cell() -> DayCellOut:
    return DayCellOut.model_validate(
        {
            "date": "2026-11-10",
            "state": "absence",
            "status": "remote",
            "status_label": "Удалёнка",
            "status_note": None,
            "plan": None,
            "fact": None,
            "late_sec": 28800,
            "early_leave_sec": None,
            "undertime_sec": None,
            "no_plan": False,
            "flags": ["no_show_confirmed"],
            "source": {},
            "no_show": {
                "id": 1,
                "plan_id": 2,
                "seconds": 28800,
                "intervals": [[36000, 64800]],
                "reason": "Проверено с сотрудником",
                "created_by": "admin",
                "created_at": datetime(2026, 11, 10, 19),
            },
        }
    )


def person(cell: DayCellOut) -> TodayRow:
    return TodayRow(
        employee=EmployeeBrief(
            id=7,
            short_name="Сотрудник 7",
            full_name="Вымышленный сотрудник",
            position="",
            color="",
            is_active=True,
        ),
        cell=cell,
        presence="absent",
        daily_overdue=False,
    )


def report(row: TodayRow) -> TodayOut:
    return TodayOut(
        date=row.cell.date,
        now_sec=19 * 3600,
        rows=[row],
        counts={"absent": 1},
        worked_sec=0,
        feed=[],
        week_pulse=[],
    )


def test_employee_day_reports_confirmed_no_show_instead_of_missing_daily():
    cell = confirmed_cell()
    text = texts.format_employee_day(person(cell), cell.date)
    assert "Факт: невыход подтверждён администратором" in text
    assert "Время невыхода, в опоздания: <b>8:00</b>" in text
    assert "дейлик не прислан" not in text
    assert "00:00" not in text
    assert "10:00–18:00 (план при подтверждении невыхода)" in text


def test_day_summary_separates_confirmed_no_show_from_waiting_and_reported_lateness():
    data = report(person(confirmed_cell()))
    text = texts.format_day_summary(data)
    assert "Пока без дейлика: <b>0</b>" in text
    assert "Опоздания по дейликам: <b>0</b>" in text
    assert "Невыходы подтверждены · 1" in text
    assert "Сотрудник 7 — 8:00 в опоздания" in text
    assert "Невыход подтверждён" in texts.format_today(data)


def test_week_reports_no_show_explicitly():
    row = person(confirmed_cell())
    week_row = WeekRow(employee=row.employee, cells=[row.cell], totals={}, plan=None)
    week = WeekOut(
        iso_year=2026,
        iso_week=46,
        label="46 неделя",
        week_start=date(2026, 11, 9),
        days=[row.cell.date],
        rows=[week_row],
        day_totals=[],
        totals={},
        today=row.cell.date,
    )
    text = texts.format_my_week(week, week_row)
    assert "Факт: невыход подтверждён администратором" in text
    assert "невыход, в опоздания 8:00" in text
    assert "дейлик не прислан" not in text


def test_conflict_keeps_new_actual_hours_and_explains_no_double_penalty():
    cell = confirmed_cell().model_copy(
        update={"flags": ["no_show_conflict"], "status": None, "status_label": None}
    )
    cell = DayCellOut.model_validate(
        {
            **cell.model_dump(),
            "state": "worked",
            "late_sec": None,
            "fact": {
                "start": 36000,
                "end": 64800,
                "intervals": [[36000, 64800]],
                "worked_sec": 28800,
                "efficiency": 80,
                "result_sec": 23040,
                "tasks": [],
                "edited": False,
                "sent_at": None,
                "source": "telegram",
            },
        }
    )
    text = texts.format_employee_day(person(cell), cell.date)
    assert "Факт: 10:00–18:00 · <b>8:00</b>" in text
    assert "Подтверждение невыхода требует пересмотра" in text
    assert "Время невыхода в опоздания не добавлено" in text
    assert "невыход подтверждён администратором" not in text
