"""Один расчёт нормы и командировок на экранах, в финансах и выгрузке."""

import csv
import io
from datetime import date

import pytest
from sqlalchemy import select

from teamtime.calc import StatusKind
from teamtime.db.models import AppSetting, DayStatus
from teamtime.services import manual
from tests import factories as f
from tests.api.conftest import ADMIN_HEADERS

pytestmark = pytest.mark.db


async def test_admin_trip_range_excludes_fact_and_restores_on_clear(admin, maker):
    async with maker() as session:
        employee = await f.employee(session, norm_hours=80, rate=500)
        session.add(AppSetting(key="app", value={"weekly_off": [5, 6]}))
        await manual.set_daily(
            session,
            employee_id=employee.id,
            work_date=date(2026, 2, 2),
            intervals=[(10 * 3600, 18 * 3600)],
            efficiency=85,
            actor="test",
        )
        await session.commit()
    path = f"/admin/days/{employee.id}/2026-02-02/status"
    # Сам статус, а не повтор запроса, определяет количество исключённых дней.
    for _ in range(2):
        response = await admin.put(
            path,
            json={
                "kind": "business_trip",
                "end": "2026-02-15",
                "reason": "Поездка",
            },
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200, response.text
    month = (await admin.get("/months/2026/2?history=1")).json()
    finance = (await admin.get("/finances/2026/2")).json()
    row = finance["rows"][0]
    summary = row["summary"]
    assert summary == month["rows"][0]["summary"]
    assert summary["contract_norm_sec"] == 80 * 3600
    assert summary["norm_sec"] == summary["norm_reduction_sec"] == 40 * 3600
    assert (summary["norm_working_days"], summary["norm_excluded_days"]) == (20, 10)
    assert summary["worked_sec"] == summary["result_sec"] == summary["total_sec"] == 0
    assert row["amounts"]["salary"] == "40000.00"
    week = (await admin.get("/weeks/2026/6")).json()
    assert week["totals"]["worked_sec"] == week["totals"]["result_sec"] == 0
    cell = week["rows"][0]["cells"][0]
    assert cell["status"] == "business_trip" and cell["state"] == "absence"
    assert cell["fact"]["worked_sec"] == 8 * 3600  # Исходный дейлик не потерян.
    assert cell["fact"]["result_sec"] == 0
    response = await admin.get("/export/finances/2026/2.csv")
    exported = next(
        csv.DictReader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";")
    )
    assert exported["Норма"] == "40:00"
    assert exported["Договорная норма"] == "80:00"
    assert exported["Снижение нормы"] == "40:00"
    response = await admin.put(
        path, json={"kind": None, "end": "2026-02-15"}, headers=ADMIN_HEADERS
    )
    assert response.status_code == 200
    restored = (await admin.get("/finances/2026/2")).json()["rows"][0]
    assert restored["summary"]["norm_sec"] == 80 * 3600
    assert restored["summary"]["norm_reduction_sec"] == 0
    assert restored["summary"]["worked_sec"] == 8 * 3600
    assert restored["summary"]["result_sec"] == 24480
    assert restored["amounts"]["salary"] == "40000.00"
    async with maker() as session:
        history = list(
            await session.scalars(
                select(DayStatus).where(
                    DayStatus.employee_id == employee.id,
                    DayStatus.kind == StatusKind.BUSINESS_TRIP,
                )
            )
        )
        assert len(history) == 28  # Две версии статуса на каждый из 14 дней.
