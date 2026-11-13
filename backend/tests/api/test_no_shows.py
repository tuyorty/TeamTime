"""Подтверждение невыхода, защита от устаревшего плана и отмена с сохранением истории."""

import io
from datetime import UTC, date, datetime, time

import pytest
from openpyxl import load_workbook
from sqlalchemy import func, select

from teamtime.calc import StatusKind
from teamtime.calc.penalty import DEFAULT_SCALE
from teamtime.core import clock
from teamtime.db.models import AuditLog, DayNoShow
from teamtime.parsing import PlanDayKind
from teamtime.services import facts, manual
from teamtime.services.settings import AppSettings, load_settings, save_settings
from tests import factories as f
from tests.api.conftest import ADMIN_HEADERS

pytestmark = pytest.mark.db
DAY = date(2026, 10, 23)


async def test_archived_employee_keeps_confirmed_no_show_after_plan_retraction(admin, maker):
    """Архив и отзыв исходного плана не скрывают сохранённое решение из отчётов."""
    from teamtime.db.models import Employee, SchedulePlan

    employee, plan = await prepare(maker)
    response = await admin.post(
        f"/admin/days/{employee}/{DAY}/no-show", json=body(plan), headers=ADMIN_HEADERS
    )
    assert response.status_code == 200, response.text
    async with maker() as session:
        (await session.get(Employee, employee)).is_active = False
        (await session.get(SchedulePlan, plan)).retracted_at = clock.now()
        await session.flush()
        people = await facts.employees_for_period(session, DAY, DAY)
        assert [person.id for person in people] == [employee]
        cell = (await facts.load_cells(session, AppSettings(), DAY, DAY, [employee]))[employee, DAY]
        assert cell.result.late == 7 * 3600


async def prepare(maker, *, day=DAY, intervals=None):
    intervals = intervals or [(10 * 3600, 14 * 3600), (15 * 3600, 18 * 3600)]
    async with maker() as session:
        employee = await f.employee(session)
        plan = await manual.set_plan_day(
            session,
            employee_id=employee.id,
            day=day,
            kind=PlanDayKind.WORK,
            intervals=intervals,
            actor="admin",
            reason="Проверочный план",
        )
        await session.commit()
        return employee.id, plan.id


def body(plan_id, seconds=7 * 3600):
    return {"expected_plan_id": plan_id, "expected_seconds": seconds, "reason": "Невыход проверен"}


async def test_confirm_retry_and_cancel_preserve_snapshot_and_do_not_duplicate(admin, maker):
    employee, plan = await prepare(maker)
    path = f"/admin/days/{employee}/{DAY}/no-show"
    assert (await admin.post(path, json=body(plan))).status_code == 403
    response = await admin.post(path, json=body(plan), headers=ADMIN_HEADERS)
    assert response.status_code == 200, response.text
    saved = response.json()
    assert saved["seconds"] == 7 * 3600  # Часовой перерыв не входит в невыход.
    assert saved["intervals"] == [[36000, 50400], [54000, 64800]]
    retry = await admin.post(path, json=body(plan), headers=ADMIN_HEADERS)
    assert retry.status_code == 200
    assert retry.json()["id"] == saved["id"]
    async with maker() as session:
        assert await session.scalar(select(func.count()).select_from(DayNoShow)) == 1
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "no_show.confirmed")
            )
            == 1
        )
    response = await admin.post(
        path + "/cancel",
        headers=ADMIN_HEADERS,
        json={"expected_id": saved["id"], "reason": "Выяснили уважительную причину"},
    )
    assert response.status_code == 200
    assert response.json()["retracted_at"]
    async with maker() as session:
        assert await session.scalar(select(func.count()).select_from(DayNoShow)) == 1
        assert (await session.get(DayNoShow, saved["id"])).retracted_at is not None


async def test_employee_without_admin_cannot_confirm(client, maker):
    employee, plan = await prepare(maker)
    response = await client.post(
        f"/admin/days/{employee}/{DAY}/no-show", headers=ADMIN_HEADERS, json=body(plan)
    )
    assert response.status_code == 401


@pytest.mark.parametrize("change", ["plan", "hours", "daily", "status"])
async def test_stale_plan_daily_or_approved_status_prevents_confirmation(admin, maker, change):
    employee, plan = await prepare(maker)
    async with maker() as session:
        if change == "plan":
            await manual.set_plan_day(
                session,
                employee_id=employee,
                day=DAY,
                kind=PlanDayKind.WORK,
                intervals=[(11 * 3600, 18 * 3600)],
                actor="admin",
                reason="Изменили план",
            )
        elif change == "daily":
            await manual.set_daily(
                session,
                employee_id=employee,
                work_date=DAY,
                intervals=[(10 * 3600, 18 * 3600)],
                efficiency=100,
                actor="admin",
            )
        elif change == "status":
            await manual.set_status(
                session,
                employee_id=employee,
                day=DAY,
                kind=StatusKind.SICK,
                actor="admin",
                reason="Подтверждён больничный",
            )
        await session.commit()
    response = await admin.post(
        f"/admin/days/{employee}/{DAY}/no-show",
        headers=ADMIN_HEADERS,
        json=body(plan, 3600 if change == "hours" else 7 * 3600),
    )
    assert response.status_code == 409, response.text
    async with maker() as session:
        assert await session.scalar(select(func.count()).select_from(DayNoShow)) == 0


async def test_overnight_shift_must_finish_before_confirmation(admin, maker):
    day = date(2026, 10, 25)
    employee, plan = await prepare(maker, day=day, intervals=[(22 * 3600, 2 * 3600)])
    path = f"/admin/days/{employee}/{day}/no-show"
    clock.freeze(datetime(2026, 10, 25, 20, 0, tzinfo=UTC))  # 01:00 по времени команды.
    assert (
        await admin.post(path, json=body(plan, 4 * 3600), headers=ADMIN_HEADERS)
    ).status_code == 409
    clock.freeze(datetime(2026, 10, 25, 21, 0, tzinfo=UTC))
    response = await admin.post(path, json=body(plan, 4 * 3600), headers=ADMIN_HEADERS)
    assert response.status_code == 200, response.text


async def test_holiday_cannot_be_confirmed_and_has_no_action_in_day_cell(admin, maker):
    employee, plan = await prepare(maker)
    async with maker() as session:
        await save_settings(session, AppSettings(holidays=[DAY]), effective_from=DAY.replace(day=1))
        settings = await load_settings(session)
        cell = (await facts.load_cells(session, settings, DAY, DAY, [employee]))[employee, DAY]
        assert not cell.can_confirm_no_show
        await session.commit()
    response = await admin.post(
        f"/admin/days/{employee}/{DAY}/no-show", headers=ADMIN_HEADERS, json=body(plan)
    )
    assert response.status_code == 409, response.text
    assert "праздничный" in response.json()["detail"]
    async with maker() as session:
        assert await session.scalar(select(func.count()).select_from(DayNoShow)) == 0


async def test_snapshot_survives_plan_edit_but_later_daily_prevents_double_penalty(admin, maker):
    employee, plan = await prepare(maker)
    path = f"/admin/days/{employee}/{DAY}/no-show"
    response = await admin.post(path, json=body(plan), headers=ADMIN_HEADERS)
    assert response.status_code == 200, response.text
    async with maker() as session:
        await manual.set_plan_day(
            session,
            employee_id=employee,
            day=DAY,
            kind=PlanDayKind.OFF,
            intervals=[],
            actor="admin",
            reason="Исправили расписание",
        )
        settings = await load_settings(session)
        cell = (await facts.load_cells(session, settings, DAY, DAY, [employee]))[employee, DAY]
        assert cell.result.late == 7 * 3600
        assert cell.no_show is not None and cell.no_show.plan_id == plan
        assert cell.result.planned == 7 * 3600
        assert "no_show_confirmed" in cell.result.flags
        await manual.set_daily(
            session,
            employee_id=employee,
            work_date=DAY,
            intervals=[(10 * 3600, 18 * 3600)],
            efficiency=100,
            actor="admin",
        )
        cell = (await facts.load_cells(session, settings, DAY, DAY, [employee]))[employee, DAY]
        assert cell.result.late is None
        assert cell.result.worked == 8 * 3600
        assert "no_show_conflict" in cell.result.flags
        assert "no_show_confirmed" not in cell.result.flags


@pytest.mark.parametrize("remove_plan", [False, True])
async def test_no_show_reports_and_export_do_not_invent_midnight_arrival(admin, maker, remove_plan):
    employee, plan = await prepare(maker)
    response = await admin.post(
        f"/admin/days/{employee}/{DAY}/no-show", headers=ADMIN_HEADERS, json=body(plan)
    )
    assert response.status_code == 200, response.text
    if remove_plan:
        async with maker() as session:
            await manual.set_plan_day(
                session, employee_id=employee, day=DAY, kind=PlanDayKind.OFF, actor="admin"
            )
            await session.commit()
    month = (await admin.get("/months/2026/10?history=1")).json()
    row = next(row for row in month["rows"] if row["employee"]["id"] == employee)
    assert row["summary"]["late_total_sec"] == 7 * 3600
    assert row["summary"]["penalty_sec"] == int(DEFAULT_SCALE.penalty(7 * 3600))
    assert row["summary"]["days_missing"] == 0
    assert row["late_days"] == [
        {
            "date": str(DAY),
            "late_sec": 7 * 3600,
            "plan_start": 10 * 3600,
            "fact_start": None,
            "no_show": True,
        }
    ]
    today = (await admin.get("/today", params={"day": str(DAY)})).json()
    assert today["rows"][0]["presence"] == "absent"
    assert not today["rows"][0]["daily_overdue"]
    assert today["counts"]["awaiting_daily"] == 0
    assert today["counts"]["absent"] == 1
    response = await admin.get("/export/months/2026/10.xlsx")
    assert response.status_code == 200, response.text
    workbook = load_workbook(io.BytesIO(response.content))
    assert workbook["Опоздания"]["C2"].value == time(10)
    assert workbook["Опоздания"]["D2"].value == "Подтверждённый невыход"
    day_row = next(
        entry
        for entry in workbook["Дни"].iter_rows(min_row=2, values_only=True)
        if entry[2].date() == DAY
    )
    assert day_row[4] == "10:00–14:00; 15:00–18:00"
    assert day_row[5] is None
    assert day_row[12] == "Подтверждённый невыход"


@pytest.mark.parametrize(
    ("intervals", "hour", "hours"),
    [
        ([(15 * 3600, 18 * 3600), (9 * 3600, 12 * 3600)], 13, 6),
        ([(9 * 3600, 14 * 3600), (13 * 3600, 18 * 3600)], 19, 10),
    ],
)
async def test_ambiguous_or_overlapping_plan_cannot_confirm_no_show(
    admin, maker, intervals, hour, hours
):
    employee, plan = await prepare(maker, intervals=intervals)
    clock.freeze(datetime(2026, 10, 23, hour - 5, tzinfo=UTC))
    async with maker() as session:
        cell = (await facts.load_cells(session, AppSettings(), DAY, DAY, [employee]))[employee, DAY]
        assert not cell.can_confirm_no_show
    response = await admin.post(
        f"/admin/days/{employee}/{DAY}/no-show",
        headers=ADMIN_HEADERS,
        json=body(plan, hours * 3600),
    )
    assert response.status_code == 409, response.text
    assert "Сначала исправьте план дня" in response.json()["detail"]
    async with maker() as session:
        assert await session.scalar(select(func.count()).select_from(DayNoShow)) == 0


async def test_split_overnight_shift_waits_for_last_morning_interval(admin, maker):
    day = date(2026, 10, 25)
    employee, plan = await prepare(
        maker, day=day, intervals=[(22 * 3600, 2 * 3600), (3 * 3600, 5 * 3600)]
    )
    path = f"/admin/days/{employee}/{day}/no-show"
    clock.freeze(datetime(2026, 10, 25, 23, 59, tzinfo=UTC))  # Ещё 04:59 следующих суток.
    async with maker() as session:
        cell = (await facts.load_cells(session, AppSettings(), day, day, [employee]))[employee, day]
        assert not cell.can_confirm_no_show
    response = await admin.post(path, headers=ADMIN_HEADERS, json=body(plan, 6 * 3600))
    assert response.status_code == 409, response.text
    clock.freeze(datetime(2026, 10, 26, 0, 0, tzinfo=UTC))
    async with maker() as session:
        cell = (await facts.load_cells(session, AppSettings(), day, day, [employee]))[employee, day]
        assert cell.can_confirm_no_show
    response = await admin.post(path, headers=ADMIN_HEADERS, json=body(plan, 6 * 3600))
    assert response.status_code == 200, response.text
    assert response.json()["seconds"] == 6 * 3600
