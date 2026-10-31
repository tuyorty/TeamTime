"""Инбокс объясняет правку; предварительный расчёт совпадает с её одобрением."""

from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from teamtime.calc import StatusKind
from teamtime.services import manual
from teamtime.services.facts import current_plans
from teamtime.services.ingest import ingest
from teamtime.services.settings import AppSettings
from tests import factories as f
from tests.api.conftest import ADMIN_HEADERS
from tests.conftest import NOW

pytestmark = pytest.mark.db


@pytest.mark.parametrize("action", ["edit", "accept"])
async def test_suspicious_schedule_inbox_and_resolution(
    admin: httpx.AsyncClient, maker: async_sessionmaker[AsyncSession], action: str
) -> None:
    sent = datetime(2026, 10, 31, 8, 0, tzinfo=UTC)
    async with maker() as session:
        await f.forum(session)
        await f.employee(session)
        original = f.message(
            f.schedule_text(sprint="02.10 - 08.10"),
            thread=f.SCHEDULE_THREAD,
            sent_at=sent,
        )
        await ingest(session, original)
        await session.commit()

    inbox = (await admin.get("/inbox", params={"kind": "schedule"})).json()
    assert inbox["total"] == 1
    item = inbox["items"][0]
    assert item["parse"]["status"] == "partial"
    assert item["parse"]["resolution"] == "pending"
    issue = next(i for i in item["parse"]["issues"] if i["code"] == "suspicious_sprint_week")
    assert issue["severity"] == "warning"
    assert "31.10.2026" in issue["message"]
    assert "28.09.2026–04.10.2026" in issue["message"]

    if action == "accept":
        response = await admin.post(
            f"/admin/inbox/{item['parse']['id']}/resolve",
            json={"resolution": "accepted"},
            headers=ADMIN_HEADERS,
        )
        assert response.status_code == 200, response.text
    else:
        async with maker() as session:
            await ingest(
                session,
                f.message(
                    f.schedule_text(sprint="02.11 - 08.11"),
                    thread=f.SCHEDULE_THREAD,
                    sent_at=sent,
                    message_id=original.message_id,
                    edited=True,
                ),
            )
            await session.commit()

    assert (await admin.get("/inbox", params={"kind": "schedule"})).json()["total"] == 0
    async with maker() as session:
        old = await current_plans(session, date(2026, 9, 28), date(2026, 10, 4))
        new = await current_plans(session, date(2026, 11, 2), date(2026, 11, 8))
        assert len(old) == (1 if action == "accept" else 0)
        assert len(new) == (0 if action == "accept" else 1)


async def test_reparse_uses_original_send_date(admin: httpx.AsyncClient, maker) -> None:
    """Историческое расписание сверяется с датой сообщения, а не датой переразбора."""
    async with maker() as session:
        await f.forum(session)
        await f.employee(session)
        outcome = await ingest(
            session,
            f.message(
                f.schedule_text(sprint="28.09 - 04.10"),
                thread=f.SCHEDULE_THREAD,
                sent_at=datetime(2026, 9, 27, 8, 0, tzinfo=UTC),
            ),
        )
        assert not outcome.needs_attention and outcome.parse_result_id is not None
        reparsed = await manual.reparse(
            session, outcome.parse_result_id, AppSettings(), actor="admin"
        )
        assert not reparsed.needs_attention
        await session.commit()
    assert (await admin.get("/inbox")).json()["total"] == 0


@pytest.mark.parametrize("mode", ["daily", "no_daily", "sick", "new_message", "reparse"])
async def test_preview_and_approval(
    admin: httpx.AsyncClient, maker: async_sessionmaker[AsyncSession], mode: str
) -> None:
    async with maker() as session:
        await f.forum(session)
        employee = await f.employee(session, tg_id=501)
        employee_id = employee.id
        original = f.schedule_text(Пн="10:00 - 18:00", Вт="10:00 - 18:00")
        updated = f.schedule_text(Пн="11:00 - 19:00", Вт="10:00 - 18:00").replace(
            "задача два", "новая задача"
        )
        source = f.message(original, thread=f.SCHEDULE_THREAD, sent_at=NOW - timedelta(days=1))
        await ingest(session, source)
        if mode != "no_daily":
            await ingest(session, f.message(f.daily_text("26.10.2026", "10:30 - 18:00")))
        if mode == "sick":
            await manual.set_status(
                session,
                employee_id=employee_id,
                day=NOW.date(),
                kind=StatusKind.SICK,
                actor="admin",
            )
        edited = f.message(
            updated,
            thread=f.SCHEDULE_THREAD,
            message_id=None if mode == "new_message" else source.message_id,
            sent_at=NOW if mode == "new_message" else source.sent_at,
            edited=mode != "new_message",
        )
        result = await ingest(session, edited)
        if mode == "reparse":
            assert result.parse_result_id is not None
            await manual.reparse(session, result.parse_result_id, AppSettings(), actor="admin")
        await session.commit()

    payload = (await admin.get("/inbox")).json()
    item = next(item for item in payload["items"] if item["parse"]["kind"] == "schedule")
    preview = item["plan_change"]
    assert preview["late_change"] is True
    assert preview["previous_version"] == 1
    assert preview["tasks_added"] == ["новая задача"]
    assert preview["tasks_removed"] == ["задача два"]
    day = next(day for day in preview["days"] if day["date"] == "2026-10-26")
    assert day["affects_calculation"] is True
    assert day["current"]["plan"]["start"] == 10 * 3600
    assert day["if_accepted"]["plan"]["start"] == 11 * 3600
    expected_late = None if mode in {"no_daily", "sick"} else 1800
    assert day["current"]["late_sec"] == expected_late
    assert day["if_accepted"]["late_sec"] == (None if expected_late is None else 0)
    assert day["current"]["fact"] == day["if_accepted"]["fact"]

    # Сам просмотр ничего не одобряет и не меняет действующий план.
    week = (await admin.get("/weeks/2026/44")).json()
    before = next(row for row in week["rows"] if row["employee"]["id"] == employee_id)["cells"][0]
    assert before["plan"]["start"] == day["current"]["plan"]["start"]
    assert before["late_sec"] == expected_late
    response = await admin.post(
        f"/admin/inbox/{item['parse']['id']}/resolve",
        json={"resolution": "accepted"},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 200, response.text
    after_week = (await admin.get("/weeks/2026/44")).json()
    after = next(row for row in after_week["rows"] if row["employee"]["id"] == employee_id)[
        "cells"
    ][0]
    assert after["plan"] == day["if_accepted"]["plan"]
    assert after["late_sec"] == day["if_accepted"]["late_sec"]
    assert after["fact"] == before["fact"]
    assert not any(
        item["parse"]["kind"] == "schedule" for item in (await admin.get("/inbox")).json()["items"]
    )
