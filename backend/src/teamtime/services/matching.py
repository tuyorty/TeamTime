"""Сопоставление сообщений с сотрудниками.

Расписание: ключ — строка «Фамилия И.О.» (отправитель может быть подписан как угодно).
Дейлик: строки с ФИО нет, поэтому сотрудник берётся по привязке аккаунта Telegram.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.db.models import Employee, TelegramIdentity
from teamtime.parsing import PersonRef
from teamtime.parsing.text import fold


async def employee_by_person(session: AsyncSession, person: PersonRef) -> Employee | None:
    return await session.scalar(select(Employee).where(Employee.match_key == person.key))


async def candidates_by_surname(session: AsyncSession, surname: str) -> list[Employee]:
    key = fold(surname)
    rows = await session.scalars(
        select(Employee).where(Employee.match_key.like(f"{key} %")).order_by(Employee.short_name)
    )
    return list(rows)


async def suggest_by_display_name(
    session: AsyncSession, display_name: str, username: str | None
) -> Employee | None:
    """Кандидат по подписи в Telegram: фамилия встречается в имени. Только если он единственный."""
    haystack = fold(f"{display_name} {username or ''}")
    if not haystack.strip():
        return None
    employees = await session.scalars(select(Employee).where(Employee.is_active))
    found = [
        e for e in employees if (s := e.match_key.split(" ")[0]) and len(s) > 2 and s in haystack
    ]
    return found[0] if len(found) == 1 else None


async def upsert_identity(
    session: AsyncSession,
    telegram_user_id: int,
    display_name: str,
    username: str | None,
    seen_at: datetime,
) -> TelegramIdentity:
    identity = await session.scalar(
        select(TelegramIdentity).where(TelegramIdentity.telegram_user_id == telegram_user_id)
    )
    if identity is None:
        identity = TelegramIdentity(
            telegram_user_id=telegram_user_id,
            display_name=display_name,
            username=username,
            first_seen_at=seen_at,
            last_seen_at=seen_at,
        )
        session.add(identity)
        await session.flush()
        if suggestion := await suggest_by_display_name(session, display_name, username):
            identity.suggested_employee_id = suggestion.id
    else:
        identity.display_name = display_name or identity.display_name
        identity.username = username or identity.username
        identity.last_seen_at = max(identity.last_seen_at, seen_at)
    return identity
