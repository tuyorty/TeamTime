from __future__ import annotations

from collections.abc import AsyncIterator

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from teamtime.api.app import create_app
from teamtime.core.config import Settings
from tests.conftest import TEST_DB

ADMIN_HEADERS = {"X-Requested-With": "teamtime"}


@pytest.fixture
async def client(maker: async_sessionmaker[AsyncSession]) -> AsyncIterator[httpx.AsyncClient]:
    assert TEST_DB
    settings = Settings(
        database_url=TEST_DB,
        admin_password=SecretStr("secret"),
        session_secret=SecretStr("test-secret"),
        log_level="WARNING",
        demo=True,
    )
    app = create_app(settings, realtime=False)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test/api/v1") as c:
            yield c


@pytest.fixture
async def admin(client: httpx.AsyncClient) -> httpx.AsyncClient:
    r = await client.post("/auth/login", json={"password": "secret"})
    assert r.status_code == 200, r.text
    return client
