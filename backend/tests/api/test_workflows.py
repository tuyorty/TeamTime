"""Заявки, задачи и расчёты по действовавшим условиям на вымышленных данных."""

from __future__ import annotations

import io
from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from openpyxl import load_workbook
from sqlalchemy import func, select

from teamtime.calc import StatusKind
from teamtime.core import clock
from teamtime.db.models import DayStatus
from teamtime.services import diagnostics, manual, status_requests
from teamtime.services.ingest import ingest
from teamtime.services.reports import month_report, today_report, week_report
from teamtime.services.settings import AppSettings, load_settings, save_settings
from tests import factories as f
from tests.api.conftest import ADMIN_HEADERS
from tests.conftest import NOW

pytestmark = pytest.mark.db
MONDAY = date(2026, 10, 26)


async def test_demo_status_request_waits_for_approval_and_changes_day_after_accept(admin, maker):
    async with maker() as session:
        await f.forum(session)
        employee = await f.employee(session, tg_id=501)
        await ingest(session, f.message(f.schedule_text(), thread=f.SCHEDULE_THREAD))
        await session.commit()
    created = await admin.post(
        "/demo/status-requests",
        json={
            "employee_id": employee.id,
            "start": str(MONDAY),
            "end": str(MONDAY),
            "kind": "remote",
        },
        headers=ADMIN_HEADERS,
    )
    assert created.status_code == 200, created.text
    before = (await admin.get("/today")).json()["rows"][0]["cell"]
    assert before["status"] is None
    request_id = created.json()["request_id"]
    accepted = await admin.post(
        f"/admin/status-requests/{request_id}/decision",
        json={"accepted": True},
        headers=ADMIN_HEADERS,
    )
    assert accepted.status_code == 200
    after = (await admin.get("/today")).json()["rows"][0]["cell"]
    assert after["status"] == "remote"


async def test_employee_default_month_and_selected_period_change_all_statistics(client, maker):
    async with maker() as session:
        await f.forum(session)
        employee = await f.employee(session, tg_id=501)
        await ingest(
            session, f.message(f.schedule_text(sprint="14.09 - 19.09"), thread=f.SCHEDULE_THREAD)
        )
        await ingest(session, f.message(f.daily_text("14.09.2026", "10:00 - 18:00")))
        await ingest(session, f.message(f.schedule_text(), thread=f.SCHEDULE_THREAD))
        await ingest(session, f.message(f.daily_text("26.10.2026", "11:00 - 19:00")))
        await session.commit()
    current = (await client.get(f"/employees/{employee.id}")).json()
    assert current["start"] == "2026-10-01"
    assert current["totals"]["worked_sec"] == 8 * 3600
    assert current["late_minutes"] == [60] and current["avg_start_sec"] == 11 * 3600
    period = (
        await client.get(
            f"/employees/{employee.id}", params={"start": "2026-09-01", "end": "2026-10-26"}
        )
    ).json()
    assert period["totals"]["worked_sec"] == 16 * 3600
    assert period["late_minutes"] == [0, 60] and period["avg_start_sec"] == int(10.5 * 3600)
    assert period["days"][0]["date"] == "2026-09-01" and period["days"][-1]["date"] == "2026-10-26"


async def test_removed_task_tracker_has_no_public_or_admin_routes(client):
    assert (await client.get("/tasks?start=2026-10-01&end=2026-10-31")).status_code == 404
    assert (await client.post("/admin/tasks", json={})).status_code == 404


async def test_status_request_approval_is_atomic_idempotent_and_admin_only(client, admin, maker):
    async with maker() as session:
        employee = await f.employee(session)
        request = await status_requests.request_status(
            session, employee, MONDAY, MONDAY, StatusKind.REMOTE, "bot:501"
        )
        duplicate = await status_requests.request_status(
            session, employee, MONDAY, MONDAY, StatusKind.REMOTE, "bot:501"
        )
        assert request.id == duplicate.id
        assert await session.scalar(select(func.count()).select_from(DayStatus)) == 0
        with pytest.raises(manual.EditError, match="уже есть заявка"):
            await status_requests.request_status(
                session, employee, MONDAY, MONDAY, StatusKind.SICK, "bot:501"
            )
        await session.commit()
    url = f"/admin/status-requests/{request.id}/decision"
    assert (await client.post(url, json={"accepted": True})).status_code == 403
    result = await admin.post(
        url, json={"accepted": True, "note": "Согласовано"}, headers=ADMIN_HEADERS
    )
    assert result.status_code == 200, result.text
    assert result.json()["state"] == "accepted"
    assert (
        await admin.post(url, json={"accepted": True}, headers=ADMIN_HEADERS)
    ).status_code == 200
    assert (
        await admin.post(url, json={"accepted": False}, headers=ADMIN_HEADERS)
    ).status_code == 409
    async with maker() as session:
        assert await session.scalar(select(func.count()).select_from(DayStatus)) == 1
        row = await session.scalar(select(DayStatus))
        assert row.kind is StatusKind.REMOTE
    assert (await admin.get("/admin/status-requests?state=accepted")).json()["total"] == 1


async def test_withdraw_and_rejection_preserve_existing_status(maker):
    async with maker() as session:
        employee = await f.employee(session)
        await manual.set_status(
            session, employee_id=employee.id, day=MONDAY, kind=StatusKind.REMOTE, actor="admin"
        )
        request = await status_requests.request_status(
            session, employee, MONDAY, MONDAY, None, "bot:501"
        )
        with pytest.raises(manual.EditError, match="не найдена"):
            await status_requests.withdraw(session, request.id, employee.id + 1, "bot:502")
        await status_requests.withdraw(session, request.id, employee.id, "bot:501")
        assert request.state == "rejected"
        report = await today_report(session, AppSettings(), MONDAY)
        assert report.rows[0].cell.status is StatusKind.REMOTE


async def test_future_terms_and_rules_do_not_change_past_reports(maker):
    async with maker() as session:
        await f.forum(session)
        employee = await f.employee(session, tg_id=501)
        await save_settings(session, AppSettings())
        await ingest(session, f.message(f.schedule_text(), thread=f.SCHEDULE_THREAD))
        await ingest(session, f.message(f.daily_text("26.10.2026", "10:20 - 18:00")))
        baseline = await month_report(session, await load_settings(session), 2026, 10)
        new_settings = AppSettings(late_tolerance_min=30)
        await save_settings(session, new_settings, effective_from=date(2026, 11, 1), actor="admin")
        await manual.save_employee(
            session,
            {
                "short_name": employee.short_name,
                "monthly_norm_minutes": 120 * 60,
                "hourly_rate": Decimal(900),
                "terms_effective_from": date(2026, 11, 1),
            },
            employee=employee,
            actor="admin",
        )
        current = await month_report(session, await load_settings(session), 2026, 10)
        assert current.rows[0].summary == baseline.rows[0].summary
        future = await month_report(session, await load_settings(session), 2026, 11)
        assert future.rows[0].summary.norm_sec == 120 * 3600
        assert future.rows[0].employee.hourly_rate == Decimal(900)
        assert (await load_settings(session)).late_tolerance_min == 0
        clock.freeze(datetime.fromisoformat("2026-11-02T12:00:00+05:00"))
        assert (await load_settings(session)).late_tolerance_min == 30
        # Будущую версию можно явно вернуть к прежним правилам.
        await save_settings(session, AppSettings(), effective_from=date(2026, 11, 1), actor="admin")
        assert (await load_settings(session)).late_tolerance_min == 0


async def test_inactive_employee_stays_in_historical_report(maker):
    async with maker() as session:
        await f.forum(session)
        employee = await f.employee(session, tg_id=501)
        await ingest(session, f.message(f.daily_text("23.10.2026")))
        employee.is_active = False
        await session.flush()
        month = await month_report(session, AppSettings(), 2026, 10)
        assert [row.employee.id for row in month.rows] == [employee.id]
        assert (await today_report(session, AppSettings())).rows == []


async def test_future_timezone_does_not_activate_rules_before_old_month_boundary(maker):
    async with maker() as session:
        await save_settings(session, AppSettings())
        await save_settings(
            session,
            AppSettings(timezone="Asia/Vladivostok", late_tolerance_min=30),
            effective_from=date(2026, 11, 1),
        )
        clock.freeze(datetime.fromisoformat("2026-10-31T22:00:00+05:00"))
        settings = await load_settings(session)
        assert settings.timezone == "Asia/Yekaterinburg" and settings.late_tolerance_min == 0
        clock.freeze(datetime.fromisoformat("2026-11-01T00:01:00+05:00"))
        settings = await load_settings(session)
        assert settings.timezone == "Asia/Vladivostok" and settings.late_tolerance_min == 30


async def test_inbox_date_filter_and_stable_pages(client, maker):
    async with maker() as session:
        await f.forum(session)
        await f.employee(session, tg_id=501)
        for day in (23, 24, 25):
            await ingest(
                session,
                f.message(
                    f.daily_text(f"{day}.10.2026", e=None), sent_at=NOW - timedelta(days=26 - day)
                ),
            )
        await session.commit()
    params = {"limit": 1, "oldest": "true"}
    first = (await client.get("/inbox", params=params)).json()
    second = (await client.get("/inbox", params={**params, "offset": 1})).json()
    assert first["total"] == second["total"] == 3
    assert first["items"][0]["message"]["id"] != second["items"][0]["message"]["id"]
    filtered = (
        await client.get("/inbox", params={"start": "2026-10-24", "end": "2026-10-24"})
    ).json()
    assert filtered["total"] == 1


async def test_export_filters_all_sheets_and_totals(client, maker):
    async with maker() as session:
        await f.forum(session)
        first = await f.employee(session, tg_id=501)
        second = await f.employee(session, "Петров П.П.", tg_id=502)
        for employee in (first, second):
            await ingest(
                session,
                f.message(f.daily_text("26.10.2026"), author=501 if employee == first else 502),
            )
        await session.commit()
    for path in ("/export/months/2026/10", "/export/weeks/2026/44"):
        csv = await client.get(f"{path}.csv", params={"employee_id": first.id})
        assert csv.status_code == 200
        assert first.short_name in csv.text and second.short_name not in csv.text
        xlsx = await client.get(f"{path}.xlsx", params={"employee_id": first.id})
        book = load_workbook(io.BytesIO(xlsx.content))
        values = str([list(sheet.values) for sheet in book])
        assert first.short_name in values and second.short_name not in values


async def test_system_reports_unknown_stale_and_delivery_results(client, maker):
    assert (await client.get("/admin/system")).status_code == 401
    await client.post("/auth/login", json={"password": "secret"})
    initial = (await client.get("/admin/system")).json()
    assert all(service["state"] == "unknown" for service in initial["services"])
    async with maker() as session:
        await diagnostics.set_service(session, "bot", "ok", success=True)
        await session.commit()
        delivery = await diagnostics.begin_delivery(session, "reaction")
        await diagnostics.finish_delivery(session, delivery, "failed", "ProxyTimeoutError")
    clock.freeze(NOW + timedelta(minutes=5))
    result = (await client.get("/admin/system")).json()
    assert (
        next(service for service in result["services"] if service["service"] == "bot")["state"]
        == "stale"
    )
    assert result["deliveries"][0]["error_code"] == "ProxyTimeoutError"


async def test_period_facts_count_night_hours_weekends_and_work_series(maker):
    async with maker() as session:
        employee = await f.employee(session)
        for day, intervals in (
            (date(2026, 10, 24), [(22 * 3600, 2 * 3600)]),
            (date(2026, 10, 25), [(21 * 3600, 23 * 3600)]),
        ):
            await manual.set_daily(
                session,
                employee_id=employee.id,
                work_date=day,
                intervals=intervals,
                efficiency=80,
                actor="admin",
            )
        week = await week_report(session, AppSettings(), 2026, 43)
        assert week.highlights.calendar_off_sec == 4 * 3600
        assert week.highlights.evening_night_sec == 6 * 3600
        assert week.highlights.longest_daily_series == 2


async def test_upgrade_preserves_conditions_and_pending_late_edit(maker, engine):
    from alembic import command
    from alembic.config import Config

    from teamtime.db.models import CalculationVersion, EmployeeTerms
    from tests.conftest import BACKEND

    async with maker() as session:
        await f.forum(session)
        employee = await f.employee(session, tg_id=501)
        await save_settings(session, AppSettings(late_tolerance_min=5))
        text = f.schedule_text()
        await ingest(session, f.message(text, thread=f.SCHEDULE_THREAD, message_id=810))
        changed = text.replace("задача один", "Неподтверждённая задача").replace(
            "Пн: 10:00", "Пн: 12:00"
        )
        edited = await ingest(
            session, f.message(changed, thread=f.SCHEDULE_THREAD, message_id=810, edited=True)
        )
        assert any(issue.code == "late_change" for issue in edited.issues)
        await session.commit()

    def upgrade(connection):
        cfg = Config(str(BACKEND / "alembic.ini"))
        cfg.attributes["connection"] = connection
        cfg.attributes["skip_logging"] = True
        command.downgrade(cfg, "e1f4a5b6c7d8")
        command.upgrade(cfg, "head")

    async with engine.begin() as connection:
        await connection.run_sync(upgrade)
    async with maker() as session:
        terms = await session.scalar(select(EmployeeTerms))
        assert terms.monthly_norm_minutes == employee.monthly_norm_minutes
        assert terms.hourly_rate == employee.hourly_rate
        version = await session.scalar(select(CalculationVersion))
        assert version.effective_from == date(2000, 1, 1)
        assert version.value["late_tolerance_min"] == 5
        report = await today_report(session, await load_settings(session), MONDAY)
        assert report.rows[0].cell.plan.start == 10 * 3600
