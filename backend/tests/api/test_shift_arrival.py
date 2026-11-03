"""Ночная подработка не подменяет приход к смене в расчёте, профиле и Excel."""

import io
from datetime import UTC, datetime, time

import pytest
from openpyxl import load_workbook

from teamtime.services.ingest import ingest
from tests import factories as f

pytestmark = pytest.mark.db


async def test_shift_arrival_matches_lateness_profile_and_both_export_sheets(client, maker):
    async with maker() as session:
        await f.forum(session)
        employee = await f.employee(session, "Рябинин Р.Р.", tg_id=501)
        other = await f.employee(session, "Тихонов Т.Т.", tg_id=502)
        for who in (employee, other):
            await ingest(session, f.message(
                f.schedule_text(who.short_name, "28.09 - 03.10", Чт="11:00 - 18:00"),
                author=501 if who is employee else 502, thread=f.SCHEDULE_THREAD,
                sent_at=datetime(2026, 9, 27, 15, tzinfo=UTC),
            ))
        await ingest(session, f.message(
            f.schedule_text(employee.short_name, "05.10 - 10.10", Пн="14:00 - 17:00"),
            thread=f.SCHEDULE_THREAD, sent_at=datetime(2026, 10, 4, 15, tzinfo=UTC),
        ))
        await ingest(session, f.message(
            f.daily_text("01.10.2026", "22:00 - 00:00\n11:40 - 16:40", 60), author=501,
            sent_at=datetime(2026, 10, 2, 15, tzinfo=UTC),
        ))
        await ingest(session, f.message(
            f.daily_text("05.10.2026", "03:00 - 05:30\n14:05 - 18:00", 60), author=501,
            sent_at=datetime(2026, 10, 6, 15, tzinfo=UTC),
        ))
        await ingest(session, f.message(
            f.daily_text("01.10.2026", "10:00 - 18:00", 100), author=502,
            sent_at=datetime(2026, 10, 2, 15, tzinfo=UTC),
        ))
        await session.commit()

    month = (await client.get("/months/2026/10")).json()
    row = next(r for r in month["rows"] if r["employee"]["id"] == employee.id)
    summary = row["summary"]
    assert summary["worked_sec"] == (13 * 60 + 25) * 60
    assert summary["result_sec"] == (8 * 60 + 3) * 60
    assert summary["late_total_sec"] == summary["penalty_sec"] == 45 * 60
    assert [r["fact_start"] for r in row["late_days"]] == [11 * 3600 + 40 * 60, 14 * 3600 + 5 * 60]
    other_row = next(r for r in month["rows"] if r["employee"]["id"] == other.id)
    assert other_row["summary"]["late_total_sec"] == 0
    assert other_row["summary"]["worked_sec"] == 8 * 3600

    profile = (await client.get(f"/employees/{employee.id}")).json()
    assert profile["late_minutes"] == [40, 5]
    assert profile["arrivals"] == [11 * 3600 + 40 * 60, 14 * 3600 + 5 * 60]
    first = next(d for d in profile["days"] if d["date"] == "2026-10-01")
    assert first["fact"]["start"] == 11 * 3600 + 40 * 60
    assert first["fact"]["intervals"] == [
        [22 * 3600, 86400], [11 * 3600 + 40 * 60, 16 * 3600 + 40 * 60]
    ]

    response = await client.get(f"/export/months/2026/10.xlsx?employee_id={employee.id}")
    assert response.status_code == 200
    workbook = load_workbook(io.BytesIO(response.content))
    assert workbook["Опоздания"]["D2"].value == time(11, 40)
    assert workbook["Опоздания"]["D3"].value == time(14, 5)
    assert workbook["Дни"]["F2"].value == time(11, 40)
    assert workbook["Дни"]["F6"].value == time(14, 5)
    assert workbook["Дни"]["I2"].value.total_seconds() == 7 * 3600
