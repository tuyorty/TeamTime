"""Просмотр команды и сотрудников: выбор даты, периода и страниц без новых сообщений."""

from __future__ import annotations

from datetime import date
from html import escape

from aiogram import F, Router
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, LinkPreviewOptions, Message, User
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.bot import texts
from teamtime.bot.dates import read_date
from teamtime.bot.identity import not_linked_text, team_access
from teamtime.bot.keyboards import (
    CalendarCb,
    PeopleCb,
    ReportCb,
    calendar_menu,
    people_menu,
    report_menu,
)
from teamtime.bot.replies import report_parts
from teamtime.db.models import Employee
from teamtime.services import reports
from teamtime.services.facts import active_employees, today_local
from teamtime.services.settings import AppSettings

router = Router(name="browse")
PEOPLE_PER_PAGE = 10


def valid_view(view: str, employee_id: int) -> bool:
    return employee_id >= 0 and view in (
        {"day", "week", "month"} if employee_id else {"day", "summary", "week"}
    )


async def may_view(message: Message, session: AsyncSession, user: User | None) -> bool:
    if await team_access(session, message.chat, user):
        return True
    if message.chat.type == "private" and user:
        await message.answer(not_linked_text(user))
    return False


async def allowed_query(query: CallbackQuery, session: AsyncSession) -> Message | None:
    if not isinstance(query.message, Message):
        await query.answer("Откройте новый отчёт через меню бота", show_alert=True)
        return None
    if not await team_access(session, query.message.chat, query.from_user):
        await query.answer("Просмотр доступен только сотрудникам команды", show_alert=True)
        return None
    return query.message


async def deliver(
    message: Message, text: str, keyboard: InlineKeyboardMarkup, *, edit: bool
) -> None:
    if edit:
        try:
            await message.edit_text(
                text,
                parse_mode=ParseMode.HTML,
                link_preview_options=LinkPreviewOptions(is_disabled=True),
                reply_markup=keyboard,
            )
        except TelegramBadRequest as exc:
            if "message is not modified" not in exc.message.lower():
                raise
    else:
        await message.answer(
            text,
            parse_mode=ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
            reply_markup=keyboard,
        )


async def report_text(
    session: AsyncSession, settings: AppSettings, view: str, day: date, employee_id: int
) -> str:
    if not valid_view(view, employee_id):
        raise ValueError("Неизвестный отчёт. Откройте его через меню бота.")
    if employee_id:
        employee = await session.get(Employee, employee_id)
        if employee is None or not employee.is_active:
            raise ValueError("Сотрудник больше не активен. Выберите другого в меню «Сотрудники».")
    if view in {"day", "summary"}:
        report = await reports.today_report(session, settings, day)
        if employee_id:
            person = next(row for row in report.rows if row.employee.id == employee_id)
            return texts.format_employee_day(person, today_local(settings))
        return (
            texts.format_day_summary(report)
            if view == "summary"
            else texts.format_day(report, today_local(settings))
        )
    if view == "week":
        iso = day.isocalendar()
        week = await reports.week_report(session, settings, iso.year, iso.week)
        if employee_id:
            row = next(row for row in week.rows if row.employee.id == employee_id)
            return texts.format_my_week(week, row)
        return texts.format_who(week)
    month = await reports.month_report(session, settings, day.year, day.month, history=1)
    month_row = next(row for row in month.rows if row.employee.id == employee_id)
    return texts.format_month(month_row.employee.short_name, month.label, month_row.summary)


async def display_report(
    message: Message,
    text: str,
    settings: AppSettings,
    view: str,
    day: date,
    employee_id: int,
    *,
    edit: bool = False,
    page: int = 0,
) -> None:
    # Оставляем место для имени и периода в заголовке каждой следующей страницы.
    parts = report_parts(text, limit=3200)
    page = max(0, min(page, len(parts) - 1))
    context = "\n".join(text.splitlines()[:2])
    heading = f"{context}\n<i>Страница {page + 1}/{len(parts)}</i>\n\n" if page else ""
    await deliver(
        message,
        heading + parts[page],
        report_menu(
            view, day, today_local(settings), employee_id=employee_id, page=page, pages=len(parts)
        ),
        edit=edit,
    )


async def send_report(
    message: Message,
    session: AsyncSession,
    settings: AppSettings,
    user: User | None,
    view: str,
    *,
    day: date | None = None,
    employee_id: int = 0,
) -> None:
    if not await may_view(message, session, user):
        return
    day = day or today_local(settings)
    try:
        text = await report_text(session, settings, view, day, employee_id)
    except ValueError as exc:
        await message.answer(escape(str(exc)))
        return
    await display_report(message, text, settings, view, day, employee_id)


async def display_people(
    message: Message,
    session: AsyncSession,
    day: date,
    view: str,
    page: int = 0,
    *,
    edit: bool = False,
) -> None:
    employees = await active_employees(session)
    pages = max(1, (len(employees) + PEOPLE_PER_PAGE - 1) // PEOPLE_PER_PAGE)
    page = max(0, min(page, pages - 1))
    selected = employees[page * PEOPLE_PER_PAGE : (page + 1) * PEOPLE_PER_PAGE]
    label = {"day": "день", "week": "неделя", "month": "месяц"}[view]
    text = (
        f"👤 <b>Сотрудники · {len(employees)}</b>\n\n"
        "Выберите сотрудника: покажу часы, эффективность и опоздания.\n\n"
        f"Дата: <b>{day:%d.%m.%Y}</b> · откроется {label}.\n"
        "День, неделю и месяц можно переключать в отчёте."
        if employees
        else "👤 <b>Сотрудники</b>\n\nАктивных сотрудников пока нет."
    )
    await deliver(
        message,
        text,
        people_menu([(e.id, e.short_name) for e in selected], day, view, page, pages),
        edit=edit,
    )


async def send_people(
    message: Message, session: AsyncSession, settings: AppSettings, user: User | None
) -> None:
    if await may_view(message, session, user):
        await display_people(message, session, today_local(settings), "month")


@router.callback_query(ReportCb.filter(), flags={"callback_answer": {"disabled": True}})
async def open_report(
    query: CallbackQuery,
    callback_data: ReportCb,
    session: AsyncSession,
    settings: AppSettings,
    state: FSMContext,
) -> None:
    message = await allowed_query(query, session)
    if message is None:
        return
    data = callback_data
    try:
        day = read_date(data.day)
        text = await report_text(session, settings, data.view, day, data.employee_id)
    except ValueError as exc:
        await query.answer(str(exc), show_alert=True)
        return
    await state.clear()
    await query.answer()
    await display_report(
        message, text, settings, data.view, day, data.employee_id, edit=True, page=data.page
    )


@router.callback_query(PeopleCb.filter(), flags={"callback_answer": {"disabled": True}})
async def open_people(
    query: CallbackQuery,
    callback_data: PeopleCb,
    session: AsyncSession,
    state: FSMContext,
) -> None:
    message = await allowed_query(query, session)
    if message is None:
        return
    try:
        day = read_date(callback_data.day)
        if not valid_view(callback_data.view, 1):
            raise ValueError("Неизвестный период")
    except ValueError as exc:
        await query.answer(str(exc), show_alert=True)
        return
    await state.clear()
    await query.answer()
    await display_people(message, session, day, callback_data.view, callback_data.page, edit=True)


@router.callback_query(CalendarCb.filter(), flags={"callback_answer": {"disabled": True}})
async def open_calendar(
    query: CallbackQuery,
    callback_data: CalendarCb,
    session: AsyncSession,
    settings: AppSettings,
    state: FSMContext,
) -> None:
    message = await allowed_query(query, session)
    if message is None:
        return
    data = callback_data
    try:
        day, month = read_date(data.day), read_date(data.month).replace(day=1)
        if not valid_view(data.view, data.employee_id):
            raise ValueError("Неизвестный отчёт")
    except ValueError as exc:
        await query.answer(str(exc), show_alert=True)
        return
    await state.clear()
    await query.answer()
    await deliver(
        message,
        "📅 <b>Выберите дату</b>\n\n"
        "Стрелки переключают месяцы. Нажмите на число, чтобы открыть отчёт.\n"
        f"Выбрано: <b>{day:%d.%m.%Y}</b>. Точка • отмечает сегодня.",
        calendar_menu(data.view, day, month, today_local(settings), data.employee_id),
        edit=True,
    )


@router.callback_query(F.data == "browse:noop", flags={"callback_answer": {"disabled": True}})
async def calendar_heading(query: CallbackQuery) -> None:
    await query.answer()
