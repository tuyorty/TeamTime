"""Режим финансов: права, прежний расчёт, сохранность закрытого фонда и остановка бота."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import func, select

from teamtime.bot import fund_notifications
from teamtime.bot.handlers.fund import entry
from teamtime.bot.keyboards import reply_menu
from teamtime.core import clock
from teamtime.db.fund import FundPeriod, FundReceipt
from teamtime.db.fund_operations import FundNotification
from teamtime.db.models import AppSetting, AuditLog
from teamtime.services import fund, fund_bot, fund_config, fund_report
from tests.api.conftest import ADMIN_HEADERS
from tests.api.test_fund_acceptance import login
from tests.api.test_fund_more import link
from tests.api.test_fund_workflows import MONTH, prepare_month

pytest_plugins = ["tests.api.test_fund_workflows"]
pytestmark = pytest.mark.db


async def switch(client, enabled, expected):
    return await client.put(
        "/admin/finance-module",
        json={"module_enabled": enabled, "expected_enabled": expected},
        headers=ADMIN_HEADERS,
    )


async def test_development_build_only_admin_can_switch(client, admin, monkeypatch):
    monkeypatch.setattr(fund_config, "FUND_AVAILABLE", True)
    client.cookies.clear()
    assert not (await client.get("/team/session")).json()["module_enabled"]
    assert (await client.get("/finances/2026/11")).status_code == 200
    assert (await client.get("/fund/overview")).status_code == 409
    assert (await switch(client, True, False)).status_code == 401
    await client.post("/auth/login", json={"password": "secret"})
    body = {"module_enabled": True, "expected_enabled": False}
    assert (await client.put("/admin/finance-module", json=body)).status_code == 403
    assert (await switch(client, True, False)).status_code == 200
    assert (await switch(client, False, False)).status_code == 409
    assert (await client.get("/team/session")).json()["module_enabled"]


async def test_switch_restores_ordinary_reports_and_preserves_closed_fund(admin, maker, team):
    lead, owner, employee, _, _ = team
    async with maker() as session:
        await prepare_month(session, lead, (lead, owner, employee))
        report = await fund_report.report(session, lead, MONTH)
        closed = await fund_report.close_month(
            session, lead, MONTH, report["fingerprint"], "Сверено"
        )
        await session.commit()
    await login(admin, lead)
    assert (await admin.get("/finances/2026/11")).status_code == 409
    assert (await switch(admin, False, True)).status_code == 200
    for path in ("/fund/overview", f"/fund/months/{MONTH}", f"/fund/export/{MONTH}.xlsx"):
        assert (await admin.get(path)).status_code == 409
    assert (
        await admin.post("/fund/preferences", json={}, headers=ADMIN_HEADERS)
    ).status_code == 409
    ordinary = await admin.get("/finances/2026/11")
    assert ordinary.status_code == 200, ordinary.text
    month = (await admin.get("/months/2026/11")).json()
    assert all(not row["summary"]["fund_model"] for row in month["rows"])
    assert (await admin.get("/export/finances/2026/11.xlsx")).status_code == 200
    async with maker() as session:
        assert (await session.get(FundPeriod, MONTH)).snapshot["fingerprint"] == closed[
            "fingerprint"
        ]
    assert (await switch(admin, True, False)).status_code == 200
    restored = (await admin.get(f"/fund/months/{MONTH}")).json()
    assert restored == closed
    month = (await admin.get("/months/2026/11")).json()
    assert all(row["summary"]["fund_model"] for row in month["rows"])
    async with maker() as session:
        assert (
            await session.scalar(
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == "finance.module.changed")
            )
            == 2
        )


async def test_named_access_remains_and_technical_admin_can_restore_module(client, maker, team):
    _lead, technical, employee, _, _ = team
    async with maker() as session:
        await fund_config.save(
            session,
            fund_config.FundConfig(
                module_enabled=True, enabled=True, technical_employee_ids=[technical]
            ),
        )
        await session.commit()
    await login(client, employee)
    assert (await switch(client, False, True)).status_code == 403
    await login(client, technical)
    assert (await switch(client, False, True)).status_code == 200
    assert (await client.get("/team/session")).json()["enabled"]
    await client.post("/team/logout", headers=ADMIN_HEADERS)
    assert (await client.get("/today")).status_code == 401
    await login(client, technical)
    assert (await switch(client, True, False)).status_code == 200


async def test_stale_bot_confirmation_cannot_write_and_notifications_stop(session, maker, team):
    lead, _, employee, _, _ = team
    await link(session, lead, 901)
    await link(session, employee, 903)
    row = await fund_bot.create_draft(session, 903, "receipt", MONTH)
    for i, value in enumerate(("Источник", "1234,56", "2026-11-20")):
        await fund_bot.answer(session, 903, row.id, value, f"step:{i}")
    await fund_config.save(session, fund_config.FundConfig(module_enabled=False, enabled=True))
    await session.commit()
    with pytest.raises(fund.FundError, match="отключён"):
        await fund_bot.submit(session, 903, row.id)
    assert await session.scalar(select(func.count()).select_from(FundReceipt)) == 0
    clock.freeze(datetime(2026, 11, 18, 7, 1, tzinfo=UTC))
    bot = AsyncMock()
    assert await fund_notifications.send_fund_notifications(bot, maker) == 0
    bot.send_message.assert_not_called()
    assert await session.scalar(select(func.count()).select_from(FundNotification)) == 0
    assert not any(button.text == "💼 Финансы" for line in reply_menu().keyboard for button in line)


async def test_upgrade_does_not_enable_module_implicitly(session):
    session.add(AppSetting(key="fund", value={"enabled": True}))
    await session.flush()
    assert not (await fund_config.load(session)).module_enabled


async def test_release_gate_blocks_existing_fund_and_admin_activation(
    admin, maker, team, monkeypatch
):
    monkeypatch.setattr(fund_config, "FUND_AVAILABLE", False)
    setup = (await admin.get("/team/session")).json()
    assert not setup["module_enabled"]
    assert not setup["module_available"]
    assert (await admin.get("/finances/2026/11")).status_code == 200
    assert (await admin.get("/export/finances/2026/11.xlsx")).status_code == 200
    month = (await admin.get("/months/2026/11")).json()
    assert all(not row["summary"]["fund_model"] for row in month["rows"])
    for path in ("/fund/overview", f"/fund/months/{MONTH}", f"/fund/export/{MONTH}.xlsx"):
        response = await admin.get(path)
        assert response.status_code == 409
        assert "разработке" in response.json()["detail"]
    assert (await switch(admin, True, False)).status_code == 409
    async with maker() as session:
        stored = await session.get(AppSetting, "fund")
        assert stored.value["module_enabled"]  # Старые данные сохранены, но не активны.
        with pytest.raises(fund.FundError, match="разработке"):
            await fund.telegram_member(session, 903)
        assert await fund_notifications.candidates(session) == []
    assert (await switch(admin, False, False)).status_code == 200


async def test_release_gate_keeps_previously_enabled_access_protection(
    client, maker, team, monkeypatch
):
    monkeypatch.setattr(fund_config, "FUND_AVAILABLE", False)
    async with maker() as session:
        await fund_config.save(session, fund_config.FundConfig(module_enabled=True, enabled=True))
        await session.commit()
    assert not (await client.get("/team/session")).json()["module_enabled"]
    assert (await client.get("/today")).status_code == 401
    await login(client, team[0])
    assert (await client.get("/today")).status_code == 200


async def test_disabled_wizard_releases_regular_bot_menu(session):
    message = SimpleNamespace(from_user=SimpleNamespace(id=903), text="Ответ", answer=AsyncMock())
    state = AsyncMock()
    await entry(message, session, state)
    state.clear.assert_awaited_once()
    assert "Ввод остановлен" in message.answer.call_args.args[0]
