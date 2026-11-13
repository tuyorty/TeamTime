"""Именной вход через подтверждённый Telegram; роли никогда не берутся из браузера."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.core import clock
from teamtime.db.fund import FundMember
from teamtime.db.fund_operations import TeamLogin, TeamSession
from teamtime.db.models import Employee, TelegramIdentity
from teamtime.services import fund_config
from teamtime.services.fund import FundError, lock

COOKIE = "xtime_member"
DISPLAY_COOKIE = "xtime_display"


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass(frozen=True)
class Identity:
    employee_id: int
    identity_id: int | None
    name: str
    leader: bool
    technical: bool


async def account(
    session: AsyncSession, employee_id: int, identity_id: int | None, *, demo: bool = False
) -> Identity:
    employee = await session.get(Employee, employee_id)
    if employee is None or not employee.is_active:
        raise FundError("Учётная запись недоступна", 401)
    if not demo:
        identity = await session.get(TelegramIdentity, identity_id) if identity_id else None
        if (
            identity is None
            or identity.employee_id != employee_id
            or not identity.linked_at
            or identity.removed_at
        ):
            raise FundError("Привязка Telegram изменилась; войдите заново", 401)
    config = await fund_config.load(session)
    person = await session.get(FundMember, employee_id)
    if config.enabled and (person is None or not person.active):
        raise FundError("Доступ участника не подтверждён", 403)
    return Identity(
        employee_id,
        identity_id,
        employee.full_name,
        bool(person and person.active and person.leader),
        employee_id in config.technical_employee_ids,
    )


async def authenticate(session: AsyncSession, token: str | None, *, demo: bool = False) -> Identity:
    row = await session.get(TeamSession, token_hash(token)) if token else None
    if (
        row is None
        or row.revoked_at
        or row.expires_at <= clock.now()
        or row.scope != "member"
        or row.employee_id is None
    ):
        raise FundError("Войдите через личный Telegram-аккаунт", 401)
    return await account(session, row.employee_id, row.identity_id, demo=demo)


async def issue_session(
    session: AsyncSession,
    employee_id: int | None,
    identity_id: int | None,
    *,
    display: bool = False,
) -> str:
    token = secrets.token_urlsafe(32)
    session.add(
        TeamSession(
            token_hash=token_hash(token),
            employee_id=employee_id,
            identity_id=identity_id,
            scope="display" if display else "member",
            expires_at=clock.now() + (timedelta(days=365) if display else timedelta(hours=12)),
        )
    )
    await session.flush()
    return token


async def display_access(session: AsyncSession, token: str | None) -> bool:
    row = await session.get(TeamSession, token_hash(token)) if token else None
    return bool(
        row and row.scope == "display" and row.expires_at > clock.now() and not row.revoked_at
    )


async def begin_login(session: AsyncSession) -> dict[str, str]:
    # Удаляем только просроченные неподтверждённые запросы: действующие коды,
    # подтверждения входа и выпущенные сессии остаются нетронутыми.
    await session.execute(
        delete(TeamLogin).where(
            TeamLogin.expires_at <= clock.now(),
            TeamLogin.confirmed_at.is_(None),
            TeamLogin.consumed_at.is_(None),
        )
    )
    code, secret = secrets.token_urlsafe(12), secrets.token_urlsafe(32)
    session.add(
        TeamLogin(
            id=code, secret_hash=token_hash(secret), expires_at=clock.now() + timedelta(minutes=5)
        )
    )
    await session.flush()
    return {"code": code, "secret": secret, "command": f"/login {code}"}


async def confirm_login(session: AsyncSession, code: str, telegram_id: int) -> str:
    await lock(session)
    row = await session.get(TeamLogin, code, populate_existing=True)
    if row is None or row.expires_at <= clock.now() or row.consumed_at:
        raise FundError("Код истёк или уже использован; запросите новый на сайте")
    identity = await session.scalar(
        select(TelegramIdentity).where(TelegramIdentity.telegram_user_id == telegram_id)
    )
    if identity is None or identity.employee_id is None:
        raise FundError("Аккаунт не привязан к сотруднику", 403)
    actor = await account(session, identity.employee_id, identity.id)
    if row.telegram_id and row.telegram_id != telegram_id:
        raise FundError("Этот запрос уже подтверждён другим аккаунтом", 403)
    row.telegram_id, row.employee_id, row.confirmed_at = telegram_id, actor.employee_id, clock.now()
    return actor.name


async def finish_login(
    session: AsyncSession, code: str, secret: str
) -> tuple[str | None, Identity | None]:
    await lock(session)
    row = await session.get(TeamLogin, code, populate_existing=True)
    if row is None or not hmac.compare_digest(row.secret_hash, token_hash(secret)):
        raise FundError("Запрос входа не найден", 401)
    if row.expires_at <= clock.now() or row.consumed_at:
        raise FundError("Запрос входа истёк или уже использован", 401)
    if row.confirmed_at is None or row.employee_id is None:
        return None, None
    identity = await session.scalar(
        select(TelegramIdentity).where(TelegramIdentity.telegram_user_id == row.telegram_id)
    )
    if identity is None:
        raise FundError("Привязка не найдена", 401)
    actor = await account(session, row.employee_id, identity.id)
    token = await issue_session(session, actor.employee_id, identity.id)
    row.consumed_at = clock.now()
    return token, actor
