"""Вход в режим админа по паролю из .env (ADR 0006)."""

from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel

from teamtime.api.deps import SESSION_COOKIE, ConfigDep, IsAdminDep, serializer

router = APIRouter(prefix="/auth", tags=["режим админа"])

MAX_ATTEMPTS = 5
WINDOW_SECONDS = 60


def _attempts(request: Request) -> dict[str, deque[float]]:
    """Неудачные попытки входа по адресу; живут в состоянии приложения."""
    state = request.app.state
    if not hasattr(state, "login_attempts"):
        state.login_attempts = defaultdict(deque)
    attempts: dict[str, deque[float]] = state.login_attempts
    return attempts


class LoginIn(BaseModel):
    password: str


class AuthState(BaseModel):
    is_admin: bool
    admin_enabled: bool
    demo_password_hint: bool


def _throttle(attempts: dict[str, deque[float]], key: str) -> None:
    now = time.monotonic()
    window = attempts[key]
    while window and now - window[0] > WINDOW_SECONDS:
        window.popleft()
    if len(window) >= MAX_ATTEMPTS:
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS, "Слишком много попыток, подождите минуту"
        )


@router.get("/me", summary="Включён ли режим админа")
async def me(admin: IsAdminDep, config: ConfigDep) -> AuthState:
    return AuthState(
        is_admin=admin,
        admin_enabled=config.admin_enabled,
        demo_password_hint=config.demo and config.admin_password is None,
    )


@router.post("/login", summary="Войти в режим админа")
async def login(
    body: LoginIn, request: Request, response: Response, config: ConfigDep
) -> AuthState:
    if not config.admin_enabled:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Режим админа выключен: задайте ADMIN_PASSWORD"
        )
    key = request.client.host if request.client else "?"
    attempts = _attempts(request)
    _throttle(attempts, key)
    if not config.check_admin_password(body.password):
        attempts[key].append(time.monotonic())
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный пароль")
    attempts.pop(key, None)
    response.set_cookie(
        SESSION_COOKIE,
        serializer(config).dumps({"admin": True}),
        max_age=config.session_max_age_hours * 3600,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
        path="/",
    )
    return AuthState(is_admin=True, admin_enabled=True, demo_password_hint=False)


@router.post("/logout", summary="Выйти из режима админа")
async def logout(response: Response, config: ConfigDep) -> AuthState:
    response.delete_cookie(SESSION_COOKIE, path="/")
    return AuthState(is_admin=False, admin_enabled=config.admin_enabled, demo_password_hint=False)
