"""Выдача кодов закрыта без именного входа и не обходит отдельный лимит запросов."""

from datetime import timedelta
from unittest.mock import AsyncMock

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from teamtime.api.routers import team
from teamtime.core import clock
from teamtime.db.fund_operations import TeamLogin
from teamtime.services import fund_config, team_auth
from tests.api.test_security import client

HEADERS = {"X-Requested-With": "teamtime"}


async def test_inactive_login_does_not_create_a_request(monkeypatch):
    monkeypatch.setattr(fund_config, "FUND_AVAILABLE", False)
    monkeypatch.setattr(
        fund_config, "load", AsyncMock(return_value=fund_config.FundConfig(module_enabled=True))
    )
    begin = AsyncMock(return_value={"code": "unused"})
    monkeypatch.setattr(team_auth, "begin_login", begin)
    async with client(admin_password=SecretStr("pw")) as browser:
        response = await browser.post("/team/login", headers=HEADERS)
    assert response.status_code == 409
    begin.assert_not_awaited()


async def test_named_login_throttle_is_independent_of_admin_password_and_expires(monkeypatch):
    monkeypatch.setattr(fund_config, "FUND_AVAILABLE", False)
    monkeypatch.setattr(
        fund_config, "load", AsyncMock(return_value=fund_config.FundConfig(enabled=True))
    )
    begin = AsyncMock(return_value={"code": "test-code", "secret": "test-secret"})
    monkeypatch.setattr(team_auth, "begin_login", begin)
    now = [100.0]
    monkeypatch.setattr(team, "monotonic", lambda: now[0])
    async with client(admin_password=SecretStr("pw")) as browser:
        assert (await browser.post("/team/login")).status_code == 403
        for _ in range(5):
            assert (
                await browser.post("/auth/login", json={"password": "wrong"})
            ).status_code == 401
        for _ in range(team.LOGIN_REQUEST_LIMIT):
            assert (await browser.post("/team/login", headers=HEADERS)).status_code == 200
        response = await browser.post("/team/login", headers=HEADERS)
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "60"
        assert begin.await_count == team.LOGIN_REQUEST_LIMIT
        now[0] += team.LOGIN_REQUEST_WINDOW
        assert (await browser.post("/team/login", headers=HEADERS)).status_code == 200


@pytest.mark.db
async def test_only_expired_unconfirmed_login_requests_are_cleaned(session):
    now = clock.now()
    session.add_all(
        [
            TeamLogin(id="expired", secret_hash="x" * 64, expires_at=now - timedelta(minutes=1)),
            TeamLogin(id="valid", secret_hash="x" * 64, expires_at=now + timedelta(minutes=1)),
            TeamLogin(
                id="confirmed",
                secret_hash="x" * 64,
                expires_at=now - timedelta(minutes=1),
                confirmed_at=now - timedelta(minutes=2),
            ),
            TeamLogin(
                id="consumed",
                secret_hash="x" * 64,
                expires_at=now - timedelta(minutes=1),
                confirmed_at=now - timedelta(minutes=2),
                consumed_at=now - timedelta(minutes=2),
            ),
        ]
    )
    await session.flush()
    request = await team_auth.begin_login(session)
    assert set(await session.scalars(select(TeamLogin.id))) == {
        "valid",
        "confirmed",
        "consumed",
        request["code"],
    }
