"""Команды данных: работают в личке и в группе — способ посмотреть табель вне локальной сети."""

from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, User
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.bot import texts
from teamtime.bot.identity import employee_for, not_linked_text, team_access
from teamtime.bot.keyboards import reply_menu
from teamtime.services import reports
from teamtime.services.facts import today_local
from teamtime.services.settings import AppSettings

router = Router(name="commands")


@router.message(Command("help"))
async def help_(message: Message) -> None:
    await message.answer(
        texts.HELP, reply_markup=reply_menu() if message.chat.type == "private" else None
    )


async def deny_team(message: Message, session: AsyncSession, user: User | None) -> bool:
    """Ответить отказом, если спрашивающему не положена сводка по команде."""
    if await team_access(session, message.chat, user):
        return False
    if message.chat.type == "private" and user is not None:
        await message.answer(not_linked_text(user))
    return True  # в чужой группе молчим


async def send_today(
    message: Message, session: AsyncSession, settings: AppSettings, user: User | None
) -> None:
    if await deny_team(message, session, user):
        return
    report = await reports.today_report(session, settings)
    await message.answer(texts.format_today(report))


@router.message(Command("today"))
async def today(message: Message, session: AsyncSession, settings: AppSettings) -> None:
    await send_today(message, session, settings, message.from_user)


@router.message(Command("who"))
async def who(message: Message, session: AsyncSession, settings: AppSettings) -> None:
    if await deny_team(message, session, message.from_user):
        return
    iso = today_local(settings).isocalendar()
    week = await reports.week_report(session, settings, iso.year, iso.week)
    await message.answer(texts.format_who(week))


async def send_my_week(
    message: Message, session: AsyncSession, settings: AppSettings, user: User
) -> None:
    _, employee = await employee_for(session, user)
    if employee is None:
        await message.answer(not_linked_text(user))
        return
    iso = today_local(settings).isocalendar()
    week = await reports.week_report(session, settings, iso.year, iso.week)
    row = next((r for r in week.rows if r.employee.id == employee.id), None)
    if row is None:
        await message.answer("Вы не отмечены как активный сотрудник.")
        return
    await message.answer(texts.format_my_week(week, row))


async def send_my_month(
    message: Message, session: AsyncSession, settings: AppSettings, user: User
) -> None:
    _, employee = await employee_for(session, user)
    if employee is None:
        await message.answer(not_linked_text(user))
        return
    today = today_local(settings)
    month = await reports.month_report(session, settings, today.year, today.month, history=1)
    row = next((r for r in month.rows if r.employee.id == employee.id), None)
    if row is None:
        await message.answer("Вы не отмечены как активный сотрудник.")
        return
    await message.answer(texts.format_month(employee.short_name, month.label, row.summary))


@router.message(Command("week"))
async def week(message: Message, session: AsyncSession, settings: AppSettings) -> None:
    if message.from_user:
        await send_my_week(message, session, settings, message.from_user)


@router.message(Command("me"))
async def me(message: Message, session: AsyncSession, settings: AppSettings) -> None:
    if message.from_user:
        await send_my_month(message, session, settings, message.from_user)
