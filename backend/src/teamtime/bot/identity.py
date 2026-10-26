"""Кто пишет боту: аккаунт Telegram → сотрудник."""

from __future__ import annotations

from aiogram.types import User
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.core import clock
from teamtime.db.models import Employee, TelegramIdentity
from teamtime.services.matching import upsert_identity


async def identity_for(
    session: AsyncSession, user: User, dm_chat_id: int | None = None
) -> TelegramIdentity:
    identity = await upsert_identity(session, user.id, user.full_name, user.username, clock.now())
    if dm_chat_id is not None:
        identity.dm_chat_id = dm_chat_id
    return identity


async def employee_for(
    session: AsyncSession, user: User, dm_chat_id: int | None = None
) -> tuple[TelegramIdentity, Employee | None]:
    identity = await identity_for(session, user, dm_chat_id)
    employee = await session.get(Employee, identity.employee_id) if identity.employee_id else None
    return identity, employee


def not_linked_text(user: User) -> str:
    return (
        "Ваш аккаунт ещё не привязан к сотруднику. Попросите админа привязать его на сайте "
        f"(раздел «Админка → Telegram»). Ваш ID: <code>{user.id}</code>."
    )
