from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from teamtime.parsing import ParseStatus, PlanDayKind, parse_daily, parse_schedule

TZ = ZoneInfo("Asia/Yekaterinburg")
SENT = datetime(2026, 11, 1, 14, tzinfo=UTC)


@pytest.mark.parametrize(
    ("spans", "efficiency", "seconds"),
    [
        ("9:15 - 18:10", "Эффективность 85% (обед вычитаем)", 8 * 3600 + 55 * 60),
        ("11:30 - 22:00", "Эффективность: 85%", 10 * 3600 + 30 * 60),
        ("13:00 - 18:00", "Эффективность: 95%", 5 * 3600),
        ("13:30 - 24:00", "Эффективность 95%", 10 * 3600 + 30 * 60),
    ],
)
def test_lab_daily_after_midnight_uses_written_work_date(spans, efficiency, seconds):
    result = parse_daily(
        f"#дейлик\n02.11.2026\n{spans}\n{efficiency}\n- документы\n- расчёты",
        datetime(2026, 11, 2, 22, tzinfo=UTC),
        TZ,
    )
    assert result.status is ParseStatus.OK
    assert result.daily is not None
    assert result.daily.work_date == date(2026, 11, 2)
    assert result.daily.worked_seconds == seconds
    assert result.daily.tasks == ("документы", "расчёты")


def test_lab_schedule_with_daily_tasks_bold_days_and_different_dashes():
    result = parse_schedule(
        "#расписание\nСпринт 02.11 - 08.11\nИванов И.И.\n"
        "**ПН: 15:30 - 20:30**\n- Добавление экспорта\n"
        "**ВТ: 15:30 - 20:30**\n- Тестирование\n"
        "**СР: 10:30 - 20:30**\n- Изучение статей\n"
        "**ЧТ: —————**\nПТ: 9:00 - 18:00\nСБ: 12:00 - 16:00\nВС: **—————**",
        SENT,
        TZ,
    )
    assert result.status is ParseStatus.OK
    assert result.schedule is not None
    assert len(result.schedule.days) == 7
    assert [d.kind for d in result.schedule.days] == [
        PlanDayKind.WORK,
        PlanDayKind.WORK,
        PlanDayKind.WORK,
        PlanDayKind.OFF,
        PlanDayKind.WORK,
        PlanDayKind.WORK,
        PlanDayKind.OFF,
    ]
    assert result.schedule.days[0].planned_seconds == 5 * 3600
    assert result.schedule.tasks == ("Добавление экспорта", "Тестирование", "Изучение статей")


def test_whole_week_vacation_expands_to_seven_dates():
    result = parse_schedule(
        "#расписание\nСпринт 02.11 - 08.11\nИванов И.И.\nПН — ВС: отпуск",
        SENT,
        TZ,
    )
    assert result.status is ParseStatus.OK
    assert result.schedule is not None
    assert [d.date for d in result.schedule.days] == [date(2026, 11, d) for d in range(2, 9)]
    assert all(d.kind is PlanDayKind.NOTE and d.note == "отпуск" for d in result.schedule.days)


@pytest.mark.parametrize(
    "spans",
    [
        "10:00 - 12:00; 13:00 - 17:00; 20:00 - 23:00",
        "10:00 - 11:00; 11:00 - 12:00; 13:00 - 15:00; 15:00 - 17:00; 20:00 - 23:00",
    ],
)
def test_three_or_more_intervals_keep_breaks_out_of_both_totals(spans):
    schedule = parse_schedule(f"Спринт 02.11 - 08.11\nИванов И.И.\nПН: {spans}", SENT, TZ)
    daily = parse_daily(f"#дейлик\n02.11.2026\n{spans}\nЭффективность: 85%", SENT, TZ)
    assert schedule.status is ParseStatus.OK
    assert schedule.schedule is not None
    assert daily.daily is not None
    assert schedule.schedule.days[0].planned_seconds == daily.daily.worked_seconds == 9 * 3600
    assert len(schedule.schedule.days[0].intervals) == len(daily.daily.intervals) >= 3


def test_day_range_does_not_overwrite_an_explicit_day():
    result = parse_schedule(
        "Спринт 02.11 - 08.11\nИванов И.И.\nПН: 10:00 - 18:00\nПН - ВС: отпуск",
        SENT,
        TZ,
    )
    assert result.schedule is not None
    assert result.schedule.days[0].kind is PlanDayKind.WORK
    assert all(d.note == "отпуск" for d in result.schedule.days[1:])
    assert "duplicate_day" in {issue.code for issue in result.issues}
