"""Команды данных: работают в личке и в группе — способ посмотреть таблицу вне локальной сети."""

from __future__ import annotations

from datetime import date

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, User
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.bot import texts
from teamtime.bot.dates import date_key, read_date
from teamtime.bot.handlers.browse import send_people, send_report
from teamtime.bot.identity import employee_for, not_linked_text
from teamtime.bot.keyboards import reply_menu
from teamtime.services.settings import AppSettings

router = Router(name="commands")


@router.message(Command("help"))
async def help_(message: Message) -> None:
    await message.answer(
        texts.HELP, reply_markup=reply_menu() if message.chat.type == "private" else None
    )


async def send_today(
    message: Message,
    session: AsyncSession,
    settings: AppSettings,
    user: User | None,
) -> None:
    await send_report(message, session, settings, user, "day")


async def send_day_summary(
    message: Message,
    session: AsyncSession,
    settings: AppSettings,
    user: User | None,
) -> None:
    await send_report(message, session, settings, user, "summary")


@router.message(Command("today"))
async def today(message: Message, session: AsyncSession, settings: AppSettings) -> None:
    await send_today(message, session, settings, message.from_user)


@router.message(Command("who"))
async def who(message: Message, session: AsyncSession, settings: AppSettings) -> None:
    await send_report(message, session, settings, message.from_user, "week")


@router.message(Command("people"))
async def people(message: Message, session: AsyncSession, settings: AppSettings) -> None:
    await send_people(message, session, settings, message.from_user)


@router.message(Command("day"))
async def day(
    message: Message, command: CommandObject, session: AsyncSession, settings: AppSettings
) -> None:
    selected = None
    if command.args:
        try:
            selected = date.fromisoformat("-".join(reversed(command.args.strip().split("."))))
            selected = read_date(date_key(selected))
        except ValueError:
            await message.answer(
                "Не понял дату. Пример: <code>/day 29.10.2026</code>. "
                "Или откройте /day и выберите дату в календаре."
            )
            return
    await send_report(message, session, settings, message.from_user, "day", day=selected)


async def send_mine(
    message: Message, session: AsyncSession, settings: AppSettings, user: User, view: str
) -> None:
    _, employee = await employee_for(session, user)
    if employee is None:
        await message.answer(not_linked_text(user))
        return
    if not employee.is_active:
        await message.answer("Вы не отмечены как активный сотрудник.")
        return
    await send_report(message, session, settings, user, view, employee_id=employee.id)


async def send_my_week(
    message: Message, session: AsyncSession, settings: AppSettings, user: User
) -> None:
    await send_mine(message, session, settings, user, "week")


async def send_my_month(
    message: Message, session: AsyncSession, settings: AppSettings, user: User
) -> None:
    await send_mine(message, session, settings, user, "month")


@router.message(Command("week"))
async def week(message: Message, session: AsyncSession, settings: AppSettings) -> None:
    if message.from_user:
        await send_my_week(message, session, settings, message.from_user)


@router.message(Command("me"))
async def me(message: Message, session: AsyncSession, settings: AppSettings) -> None:
    if message.from_user:
        await send_my_month(message, session, settings, message.from_user)
