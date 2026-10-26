"""Зависимости FastAPI: сессия БД, настройки, режим админа."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.core.config import Settings, get_settings
from teamtime.services.settings import AppSettings, load_settings

SESSION_COOKIE = "tt_session"


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    maker = request.app.state.sessionmaker
    async with maker() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            await session.rollback()
            raise


SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_app_settings(session: SessionDep) -> AppSettings:
    return await load_settings(session)


AppSettingsDep = Annotated[AppSettings, Depends(get_app_settings)]


def get_config(request: Request) -> Settings:
    """Настройки процесса, с которыми создано приложение (в тестах — свои)."""
    config: Settings = getattr(request.app.state, "settings", None) or get_settings()
    return config


ConfigDep = Annotated[Settings, Depends(get_config)]


def serializer(config: Settings) -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(config.session_secret.get_secret_value(), salt="teamtime-admin")


def is_admin(request: Request, config: ConfigDep) -> bool:
    if not config.admin_enabled:
        return False
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return False
    try:
        data = serializer(config).loads(token, max_age=config.session_max_age_hours * 3600)
    except (BadSignature, SignatureExpired):
        return False
    return bool(isinstance(data, dict) and data.get("admin"))


IsAdminDep = Annotated[bool, Depends(is_admin)]


def require_admin(
    admin: IsAdminDep,
    x_requested_with: Annotated[str | None, Header()] = None,
) -> str:
    """Изменяющие запросы: нужна сессия админа и заголовок X-Requested-With (защита от CSRF)."""
    if not admin:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Нужен режим админа")
    if x_requested_with != "teamtime":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет заголовка X-Requested-With")
    return "admin"


AdminDep = Annotated[str, Depends(require_admin)]
