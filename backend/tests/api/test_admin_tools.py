"""Реальные импорты, отделы и массовое закрытие не должны менять исходные часы."""

from dataclasses import replace
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from teamtime.db.models import (
    BotChat,
    Daily,
    Employee,
    EmployeeTerms,
    ParseResultRow,
    RawMessage,
    Resolution,
    Source,
)
from teamtime.services import manual
from teamtime.services.ingest import ingest
from tests import factories as f
from tests.api.conftest import ADMIN_HEADERS

pytestmark = pytest.mark.db


def imported(text, **kwargs):
    chat_id = kwargs.pop("chat_id", f.CHAT)
    return replace(f.message(text, **kwargs), source=Source.IMPORT, chat_id=chat_id)


async def test_bulk_keeps_unknown_efficiency_and_rejects_other_errors(admin, maker):
    async with maker() as session:
        await f.forum(session)
        employee = await f.employee(session, tg_id=501)
        valid = await ingest(session, imported("#дейлик\n25.10.2026\n10:00-18:00\n- работал"))
        no_time = await ingest(session, imported("#дейлик\n22.06.2026\nБез науки"))
        await ingest(session, imported("#дейлик\n24.10.2026\n10:00-18:00\nЭффективность: 150%"))
        await ingest(session, imported("#дейлик\n23.10.2026\n10:00-18:00", author=999))
        await ingest(session, f.message("#дейлик\n22.10.2026\n10:00-18:00"))
        await session.commit()
    before = (await admin.get("/months/2026/10?history=1")).json()["rows"][0]["summary"]
    preview = (
        await admin.post(
            "/admin/inbox/bulk/preview",
            headers=ADMIN_HEADERS,
            json={"target": "missing_efficiency", "employee_id": employee.id},
        )
    ).json()
    assert preview["parse_ids"] == [valid.parse_result_id]
    response = await admin.post(
        "/admin/inbox/bulk/apply",
        headers=ADMIN_HEADERS,
        json={"target": "missing_efficiency", "parse_ids": preview["parse_ids"]},
    )
    assert response.status_code == 200, response.text
    after = (await admin.get("/months/2026/10?history=1")).json()["rows"][0]["summary"]
    assert before == after
    async with maker() as session:
        daily = await session.scalar(select(Daily).where(Daily.work_date == date(2026, 10, 25)))
        assert daily.efficiency is None
        assert (
            await session.get(ParseResultRow, valid.parse_result_id)
        ).resolution is Resolution.ACCEPTED
    retry = await admin.post(
        "/admin/inbox/bulk/apply",
        headers=ADMIN_HEADERS,
        json={"target": "missing_efficiency", "parse_ids": preview["parse_ids"]},
    )
    assert retry.status_code == 409
    preview = (
        await admin.post(
            "/admin/inbox/bulk/preview",
            headers=ADMIN_HEADERS,
            json={"target": "no_time", "start": "2026-10-26", "end": "2026-10-26"},
        )
    ).json()
    assert preview["parse_ids"] == [no_time.parse_result_id]
    response = await admin.post(
        "/admin/inbox/bulk/apply",
        headers=ADMIN_HEADERS,
        json={"target": "no_time", "parse_ids": preview["parse_ids"]},
    )
    assert response.status_code == 200
    async with maker() as session:
        row = await session.get(ParseResultRow, no_time.parse_result_id)
        assert row.resolution is Resolution.IGNORED and row.data is None


async def test_bulk_covers_all_pages_and_stale_selection_is_atomic(admin, maker):
    async with maker() as session:
        await f.forum(session)
        await f.employee(session, tg_id=501)
        for n in range(31):
            await ingest(session, imported(f"#дейлик\n25.10.2026\n10:00-18:00\n- задача {n}"))
        await session.commit()
    preview = (
        await admin.post(
            "/admin/inbox/bulk/preview",
            json={"target": "missing_efficiency"},
            headers=ADMIN_HEADERS,
        )
    ).json()
    assert preview["count"] == 31
    assert len(preview["samples"]) == 8
    async with maker() as session:
        await manual.resolve_parse(
            session, preview["parse_ids"][0], Resolution.ACCEPTED, actor="test"
        )
        await session.commit()
    response = await admin.post(
        "/admin/inbox/bulk/apply",
        json={"target": "missing_efficiency", "parse_ids": preview["parse_ids"]},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 409
    async with maker() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(ParseResultRow)
                .where(ParseResultRow.resolution == Resolution.PENDING)
            )
            == 30
        )
    preview = (
        await admin.post(
            "/admin/inbox/bulk/preview",
            json={"target": "missing_efficiency"},
            headers=ADMIN_HEADERS,
        )
    ).json()
    response = await admin.post(
        "/admin/inbox/bulk/apply",
        json={"target": "missing_efficiency", "parse_ids": preview["parse_ids"]},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 200
    assert (await admin.get("/inbox?limit=1")).json()["total"] == 0


async def test_remove_unknown_account_is_reversible_and_import_does_not_restore_it(admin, maker):
    async with maker() as session:
        await f.forum(session)
        employee = await f.employee(session, tg_id=501)
        message = imported("#дейлик\n25.10.2026\n10:00-18:00", author=777, name="Неизвестный")
        await ingest(session, message)
        await session.commit()
    identities = (await admin.get("/identities")).json()
    unknown = next(i for i in identities if i["telegram_user_id"] == 777)
    linked = next(i for i in identities if i["telegram_user_id"] == 501)
    assert (
        await admin.delete(f"/admin/identities/{linked['id']}", headers=ADMIN_HEADERS)
    ).status_code == 409
    response = await admin.delete(f"/admin/identities/{unknown['id']}", headers=ADMIN_HEADERS)
    assert response.status_code == 200
    assert all(i["id"] != unknown["id"] for i in (await admin.get("/identities")).json())
    assert (await admin.get("/admin/identities/removed")).json()[0]["id"] == unknown["id"]
    async with maker() as session:
        outcome = await ingest(session, message)
        assert outcome.skipped == "author_removed"
        assert await session.scalar(select(func.count()).select_from(RawMessage)) == 1
        assert await session.get(Employee, employee.id) is not None
        await session.commit()
    assert (
        await admin.post(f"/admin/identities/{unknown['id']}/restore", headers=ADMIN_HEADERS)
    ).status_code == 200
    async with maker() as session:
        assert not (
            await ingest(session, imported("#дейлик\n24.10.2026\n11:00-17:00", author=777))
        ).skipped


async def test_chat_department_assigns_imported_and_new_employees_and_keeps_manual_choice(
    admin, maker
):
    lab_chat = -100777000111
    async with maker() as session:
        original = await f.employee(session, "Яковлев Я.Я.", tg_id=501)
        lab = await f.employee(session, "Баранов К.А.", tg_id=502)
        session.add(BotChat(chat_id=lab_chat, title="Лаборатория", approved=True))
        await session.flush()
        await ingest(
            session, imported("#дейлик\n25.10.2026\n10:00-18:00", author=502, chat_id=lab_chat)
        )
        await session.commit()
    response = await admin.put(
        f"/admin/chats/{lab_chat}/department",
        json={"department": "laboratory"},
        headers=ADMIN_HEADERS,
    )
    assert response.status_code == 200, response.text
    rows = {e["id"]: e for e in (await admin.get("/employees")).json()}
    assert rows[lab.id]["department"] == "laboratory"
    assert rows[original.id]["department"] == "software"
    old_client_body = {key: value for key, value in rows[lab.id].items() if key != "department"}
    response = await admin.put(
        f"/admin/employees/{lab.id}", json=old_client_body, headers=ADMIN_HEADERS
    )
    assert response.status_code == 200
    assert response.json()["department"] == "laboratory"
    async with maker() as session:
        newcomer = await f.employee(session, "Андреев А.А.", tg_id=503)
        await ingest(
            session, imported("#дейлик\n25.10.2026\n10:00-18:00", author=503, chat_id=lab_chat)
        )
        assert newcomer.department == "laboratory"
        newcomer.department = "software"
        await session.flush()
        await ingest(
            session, imported("#дейлик\n24.10.2026\n10:00-18:00", author=503, chat_id=lab_chat)
        )
        assert newcomer.department == "software"


async def test_employee_past_month_uses_past_norm_rate_and_facts(client, maker):
    async with maker() as session:
        employee = await f.employee(session, norm_hours=160, rate=900)
        session.add_all(
            [
                EmployeeTerms(
                    employee_id=employee.id,
                    effective_from=date(2000, 1, 1),
                    monthly_norm_minutes=40 * 60,
                    hourly_rate=Decimal(500),
                ),
                EmployeeTerms(
                    employee_id=employee.id,
                    effective_from=date(2026, 10, 1),
                    monthly_norm_minutes=160 * 60,
                    hourly_rate=Decimal(900),
                ),
            ]
        )
        await manual.set_daily(
            session,
            employee_id=employee.id,
            work_date=date(2026, 9, 15),
            intervals=[(36000, 64800)],
            efficiency=50,
            actor="test",
        )
        await session.commit()
    profile = (await client.get(f"/employees/{employee.id}?start=2026-09-01&end=2026-09-30")).json()
    report = (await client.get("/months/2026/9?history=1")).json()
    assert profile["month"] == report["rows"][0]["summary"]
    assert profile["month"]["norm_sec"] == 40 * 3600
    assert profile["month"]["worked_sec"] == 8 * 3600
    assert profile["employee"]["hourly_rate"] == "500.00"


async def test_admin_tools_require_session_and_csrf(client):
    for path, body in [
        ("/admin/inbox/bulk/preview", {"target": "no_time"}),
        ("/admin/inbox/bulk/apply", {"target": "no_time", "parse_ids": [1]}),
    ]:
        assert (await client.post(path, json=body, headers=ADMIN_HEADERS)).status_code == 401
    assert (await client.delete("/admin/identities/1", headers=ADMIN_HEADERS)).status_code == 401
    assert (await client.get("/admin/identities/removed")).status_code == 401
    await client.post("/auth/login", json={"password": "secret"})
    assert (await client.delete("/admin/identities/1")).status_code == 403
    assert (
        await client.post("/admin/inbox/bulk/preview", json={"target": "no_time"})
    ).status_code == 403
