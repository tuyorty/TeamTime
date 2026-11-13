"""Скрытый фонд не блокирует обычные отчёты для подтверждённой команды."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import Chat, User

from teamtime.bot.identity import team_access
from teamtime.db.fund import FundMember
from teamtime.db.models import Employee, TelegramIdentity
from teamtime.services import fund_config


@pytest.mark.parametrize(
    ("linked", "removed", "active_member", "expected"),
    [(True, False, True, True), (False, False, True, False),
     (True, True, True, False), (True, False, False, False)],
)  # fmt: skip
async def test_protected_team_access_does_not_depend_on_fund_availability(
    monkeypatch, linked, removed, active_member, expected
):
    monkeypatch.setattr(fund_config, "FUND_AVAILABLE", False)
    monkeypatch.setattr(
        fund_config,
        "load",
        AsyncMock(return_value=fund_config.FundConfig(enabled=True, module_enabled=True)),
    )
    identity = SimpleNamespace(
        id=11,
        employee_id=7,
        linked_at=datetime(2026, 11, 1) if linked else None,
        removed_at=datetime(2026, 11, 2) if removed else None,
    )
    employee = SimpleNamespace(id=7, is_active=True, full_name="Вымышленный сотрудник")
    participant = SimpleNamespace(active=active_member, leader=False)
    rows = {(Employee, 7): employee, (TelegramIdentity, 11): identity, (FundMember, 7): participant}
    session = AsyncMock()
    session.scalar.return_value = identity
    session.get.side_effect = lambda model, key: rows.get((model, key))

    assert (
        await team_access(
            session, Chat(id=99, type="private"), User(id=99, is_bot=False, first_name="Сотрудник")
        )
        is expected
    )


async def test_protected_team_report_stays_unavailable_in_group_when_fund_is_hidden(monkeypatch):
    monkeypatch.setattr(fund_config, "FUND_AVAILABLE", False)
    monkeypatch.setattr(
        fund_config, "load", AsyncMock(return_value=fund_config.FundConfig(enabled=True))
    )
    session = AsyncMock()
    assert not await team_access(
        session, Chat(id=-99, type="group"), User(id=99, is_bot=False, first_name="Сотрудник")
    )
    session.get.assert_not_awaited()
