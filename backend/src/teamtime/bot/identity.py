"""Кто пишет боту: аккаунт Telegram → сотрудник."""

from __future__ import annotations

from aiogram.types import Chat, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.core import clock
from teamtime.db.models import BotChat, Employee, TelegramIdentity
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


async def team_access(session: AsyncSession, chat: Chat, user: User | None) -> bool:
    """Сводку по всей команде видят только свои: привязанный активный сотрудник в личке
    или участники разрешённого админом чата. Бота может найти любой человек в Telegram."""
    if chat.type != "private":
        bot_chat = await session.get(BotChat, chat.id)
        return bool(bot_chat and bot_chat.approved)
    if user is None:
        return False
    identity = await session.scalar(
        select(TelegramIdentity).where(TelegramIdentity.telegram_user_id == user.id)
    )
    if identity is None or identity.employee_id is None:
        return False
    employee = await session.get(Employee, identity.employee_id)
    return bool(employee and employee.is_active)
