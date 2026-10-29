"""Личка: меню, исправление распознанного (FSM), статусы дня."""

from __future__ import annotations

from datetime import date, timedelta
from html import escape
from typing import Any
from zoneinfo import ZoneInfo

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from teamtime.bot import texts
from teamtime.bot.feedback import issue_text
from teamtime.bot.handlers.commands import send_day_summary, send_my_month, send_my_week, send_today
from teamtime.bot.identity import employee_for, not_linked_text
from teamtime.bot.keyboards import (
    MENU,
    FixCb,
    MenuCb,
    StatusCb,
    efficiency_menu,
    fix_menu,
    reply_menu,
    status_menu,
)
from teamtime.calc import STATUS_LABELS, StatusKind
from teamtime.core import clock
from teamtime.core.config import Settings
from teamtime.db.models import (
    Employee,
    ParseResultRow,
    RawMessage,
    RawMessageVersion,
    Resolution,
)
from teamtime.parsing import Issue, MessageKind, PlanDayKind, Severity, parse_daily
from teamtime.parsing.text import DATE_RE, closest_year, format_seconds, parse_interval_list
from teamtime.services import manual
from teamtime.services.facts import today_local
from teamtime.services.settings import AppSettings

router = Router(name="private")
router.message.filter(F.chat.type == "private")

WEEKDAYS = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")


class Fix(StatesGroup):
    time = State()
    full_daily = State()
    plan_day = State()


class Vacation(StatesGroup):
    range = State()


def actor(user: User) -> str:
    return f"bot:{user.id}"


@router.message(CommandStart(deep_link=True))
async def start_deep(
    message: Message, command: CommandObject, session: AsyncSession, state: FSMContext
) -> None:
    await state.clear()
    args = command.args or ""
    if args.startswith("fix_") and args[4:].isdigit() and message.from_user:
        await show_fix(message, session, message.from_user, int(args[4:]))
        return
    await start(message, session, state)


@router.message(CommandStart())
async def start(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    if message.from_user is None:
        return
    _, employee = await employee_for(session, message.from_user, message.chat.id)
    parts = employee.full_name.split() if employee else []
    first = parts[1] if len(parts) > 1 else message.from_user.first_name
    hello = f"👋 <b>Здравствуйте, {escape(first)}!</b>"
    if employee is None:
        await message.answer(f"{hello}\n\n{not_linked_text(message.from_user)}\n\n{texts.HELP}")
        return
    await message.answer(f"{hello}\n\n{texts.HELP}", reply_markup=reply_menu())


async def run_menu(
    action: str,
    msg: Message,
    session: AsyncSession,
    settings: AppSettings,
    user: User,
    config: Settings,
) -> None:
    if action == "week":
        await send_my_week(msg, session, settings, user, config)
    elif action == "month":
        await send_my_month(msg, session, settings, user, config)
    elif action == "today":
        await send_today(msg, session, settings, user, config)
    elif action == "summary":
        await send_day_summary(msg, session, settings, user, config)
    elif action == "absent":
        await msg.answer(texts.STATUS_PROMPT, reply_markup=status_menu())
    elif action == "fix":
        await list_fixes(msg, session, user)


@router.message(F.text.in_(MENU))
async def menu_button(
    message: Message,
    session: AsyncSession,
    settings: AppSettings,
    state: FSMContext,
    config: Settings,
) -> None:
    """Кнопка постоянного меню. Прерывает начатое исправление: человек передумал."""
    await state.clear()
    if message.from_user and message.text:
        await run_menu(MENU[message.text], message, session, settings, message.from_user, config)


@router.callback_query(MenuCb.filter())
async def menu(
    query: CallbackQuery,
    callback_data: MenuCb,
    session: AsyncSession,
    settings: AppSettings,
    state: FSMContext,
    config: Settings,
) -> None:
    await query.answer()
    if isinstance(query.message, Message):
        await run_menu(
            callback_data.action, query.message, session, settings, query.from_user, config
        )


# --- статусы -------------------------------------------------------------------------------


@router.message(Command("absent"))
async def absent(message: Message) -> None:
    await message.answer(texts.STATUS_PROMPT, reply_markup=status_menu())


@router.callback_query(StatusCb.filter())
async def set_status(
    query: CallbackQuery,
    callback_data: StatusCb,
    session: AsyncSession,
    settings: AppSettings,
    state: FSMContext,
) -> None:
    msg = query.message
    _, employee = await employee_for(session, query.from_user)
    if employee is None or not isinstance(msg, Message):
        await query.answer("Аккаунт не привязан к сотруднику", show_alert=True)
        return
    today = today_local(settings)
    if callback_data.kind == "vacation":
        await state.set_state(Vacation.range)
        await query.answer()
        await msg.answer(
            "🌴 <b>Даты отпуска</b>\n\nПришлите начало и конец одним сообщением.\n"
            "Пример: <code>02.11 - 13.11</code>"
        )
        return
    kind = None if callback_data.kind == "clear" else StatusKind(callback_data.kind)
    await manual.set_status(
        session,
        employee_id=employee.id,
        day=today,
        kind=kind,
        actor=actor(query.from_user),
        reason="через бота",
    )
    label = STATUS_LABELS[kind] if kind else "Статус снят"
    await query.answer(label)
    await msg.edit_text(
        f"✅ <b>{label}</b>\n{texts.human_date(today)}\n\nСтатус обновлён в таблице."
    )


def parse_range(text: str, today: date) -> tuple[date, date] | None:
    found = DATE_RE.findall(text)
    if not 1 <= len(found) <= 2:
        return None
    days = []
    for d, m, y in found:
        if y:
            try:
                days.append(date(int(y) + (2000 if len(y) == 2 else 0), int(m), int(d)))
            except ValueError:
                return None
        else:
            day = closest_year(int(d), int(m), today)
            if day is None:
                return None
            days.append(day)
    start, end = days[0], days[-1]
    if end < start:
        end = end.replace(year=end.year + 1)
    return start, end


@router.message(Vacation.range, F.text)
async def vacation_range(
    message: Message, session: AsyncSession, settings: AppSettings, state: FSMContext
) -> None:
    assert message.from_user
    assert message.text
    _, employee = await employee_for(session, message.from_user)
    if employee is None:
        await state.clear()
        return
    found = parse_range(message.text, today_local(settings))
    if found is None:
        await message.answer("Не понял даты. Пример: <code>02.11 - 13.11</code>")
        return
    start, end = found
    try:
        n = await manual.set_status_range(
            session,
            employee_id=employee.id,
            start=start,
            end=end,
            kind=StatusKind.VACATION,
            actor=actor(message.from_user),
            reason="через бота",
        )
    except manual.EditError as exc:
        await message.answer(f"⚠️ <b>Не удалось сохранить</b>\n\n{escape(str(exc))}")
        return
    await state.clear()
    await message.answer(
        f"🌴 <b>Отпуск отмечен</b>\n\nС <b>{start:%d.%m}</b> по <b>{end:%d.%m}</b> включительно.\n"
        f"Всего: {n} {texts.plural(n, 'день', 'дня', 'дней')}. Статус обновлён в таблице."
    )


# --- исправления ---------------------------------------------------------------------------


async def _own_parse(
    session: AsyncSession, user: User, parse_id: int
) -> tuple[ParseResultRow, RawMessage, Employee | None] | None:
    row = await session.get(
        ParseResultRow, parse_id, options=[selectinload(ParseResultRow.version)]
    )
    if row is None:
        return None
    raw = await session.get(RawMessage, row.version.raw_message_id)
    if raw is None or raw.author_tg_id != user.id:
        return None
    employee = await session.get(Employee, row.employee_id) if row.employee_id else None
    return row, raw, employee


async def _owned_with_data(
    session: AsyncSession, user: User, state: FSMContext
) -> tuple[ParseResultRow, Employee, dict[str, Any]] | None:
    """Запись из состояния FSM, если она принадлежит пользователю и уже привязана к сотруднику."""
    data = await state.get_data()
    found = await _own_parse(session, user, int(data["parse_id"]))
    if found is None:
        return None
    row, _raw, employee = found
    if employee is None or row.data is None:
        return None
    return row, employee, row.data


@router.message(Command("fix"))
async def fix_cmd(message: Message, session: AsyncSession) -> None:
    if message.from_user:
        await list_fixes(message, session, message.from_user)


async def list_fixes(message: Message, session: AsyncSession, user: User) -> None:
    rows = await session.execute(
        select(ParseResultRow.id)
        .join(RawMessageVersion, ParseResultRow.message_version_id == RawMessageVersion.id)
        .join(RawMessage, RawMessageVersion.raw_message_id == RawMessage.id)
        .where(
            RawMessage.author_tg_id == user.id,
            ParseResultRow.is_latest,
            ParseResultRow.resolution == Resolution.PENDING,
        )
        .order_by(RawMessage.sent_at.desc())
        .limit(5)
    )
    ids = [r[0] for r in rows]
    if not ids:
        await message.answer(
            "✅ <b>Всё разобрано</b>\n\nИсправлять нечего: сообщений, требующих вашей помощи, нет."
        )
        return
    for parse_id in ids:
        await show_fix(message, session, user, parse_id)


def describe(row: ParseResultRow, tz: ZoneInfo) -> str:
    data = row.data or {}
    if row.kind is MessageKind.DAILY and data:
        spans = "; ".join(f"{format_seconds(a)}–{format_seconds(b)}" for a, b in data["intervals"])
        eff = f"{data['efficiency']}%" if data.get("efficiency") is not None else "не указана"
        return (
            f"<b>Дейлик за {date.fromisoformat(data['work_date']):%d.%m.%Y}</b>\n"
            f"Время: {spans}\nЭффективность: {eff}"
        )
    if row.kind is MessageKind.SCHEDULE and data:
        days = []
        for d in data["days"]:
            label = WEEKDAYS[d["weekday"]]
            if d["kind"] == "work":
                a, b = d["intervals"][0][0], d["intervals"][-1][1]
                days.append(f"{label} {format_seconds(a)}–{format_seconds(b)}")
            elif d["kind"] == "off":
                days.append(f"{label} выходной")
            else:
                days.append(f"{label} «{escape(d['note'] or '')}»")
        return f"<b>Расписание на {data['iso_week']} неделю</b>\n" + "\n".join(days)
    return "<b>Сообщение не разобрано</b>"


async def show_fix(message: Message, session: AsyncSession, user: User, parse_id: int) -> None:
    found = await _own_parse(session, user, parse_id)
    if found is None:
        await message.answer("Это сообщение не найдено или прислано не вами.")
        return
    row, _raw, _employee = found
    issues = [
        Issue(i["code"], Severity(i["severity"]), i["message"], i.get("line_no"), i.get("line"))
        for i in row.issues
        if i["severity"] != "info" or i["code"] == "note_has_time"
    ]
    text = describe(row, ZoneInfo("UTC"))
    if issues:
        text += "\n\n" + "\n".join(f"• {issue_text(i)}" for i in issues)
    if row.employee_unresolved:
        text += f"\n\n{not_linked_text(user)}"
        await message.answer(text)
        return
    note_days = [
        (d["weekday"], WEEKDAYS[d["weekday"]])
        for d in (row.data or {}).get("days", [])
        if d["kind"] == "note"
    ]
    await message.answer(
        text,
        reply_markup=fix_menu(
            row.id, kind=row.kind.value, has_data=row.data is not None, note_days=note_days
        ),
    )


@router.callback_query(FixCb.filter())
async def fix_action(
    query: CallbackQuery,
    callback_data: FixCb,
    session: AsyncSession,
    settings: AppSettings,
    state: FSMContext,
) -> None:
    msg = query.message
    found = await _own_parse(session, query.from_user, callback_data.parse_id)
    if found is None or not isinstance(msg, Message):
        await query.answer("Нет доступа", show_alert=True)
        return
    row, _raw, employee = found
    await state.update_data(parse_id=row.id, weekday=callback_data.value)
    match callback_data.action:
        case "accept":
            await manual.resolve_parse(
                session, row.id, Resolution.ACCEPTED, actor=actor(query.from_user)
            )
            await query.answer("Принято")
            await msg.edit_reply_markup(reply_markup=None)
        case "time":
            await state.set_state(Fix.time)
            await query.answer()
            await msg.answer(
                "⏱ <b>Исправить время</b>\n\nПришлите фактические интервалы одним сообщением.\n"
                "Пример: <code>10:00 - 13:00; 14:00 - 18:30</code>"
            )
        case "eff":
            await query.answer()
            await msg.answer(
                "🎯 <b>Эффективность дня</b>\n\nВыберите значение для этого дейлика:",
                reply_markup=efficiency_menu(row.id),
            )
        case "eff_set":
            assert employee is not None
            assert row.data is not None
            await manual.set_daily(
                session,
                employee_id=employee.id,
                work_date=date.fromisoformat(row.data["work_date"]),
                efficiency=callback_data.value,
                actor=actor(query.from_user),
                reason="через бота",
                parse_result_id=row.id,
            )
            await manual.resolve_parse(
                session, row.id, Resolution.FIXED, actor=actor(query.from_user)
            )
            await query.answer(f"Эффективность {callback_data.value}%")
            await msg.edit_text(
                f"✅ <b>Готово: эффективность {callback_data.value}%</b>\n\n"
                "Изменение сохранено в таблице."
            )
        case "full":
            await state.set_state(Fix.full_daily)
            await query.answer()
            await msg.answer(
                "Пришлите дейлик целиком, как в теме. Или отредактируйте сообщение там."
            )
        case "day":
            await state.set_state(Fix.plan_day)
            await query.answer()
            await msg.answer(
                f"Время на {WEEKDAYS[callback_data.value]}: например <code>16:30 - 20:00</code>. "
                "Или «выходной»."
            )
        case _:
            await query.answer()


@router.message(Fix.time, F.text)
async def fix_time(message: Message, session: AsyncSession, state: FSMContext) -> None:
    assert message.text
    assert message.from_user
    try:
        parsed = parse_interval_list(message.text)
    except ValueError:
        parsed = None
    if not parsed:
        await message.answer("Не понял время. Пример: <code>10:00 - 18:00</code>")
        return
    owned = await _owned_with_data(session, message.from_user, state)
    if owned is None:
        await state.clear()
        return
    row, employee, data = owned
    try:
        await manual.set_daily(
            session,
            employee_id=employee.id,
            work_date=date.fromisoformat(data["work_date"]),
            intervals=[(p.interval.start, p.interval.end) for p in parsed],
            efficiency=manual.KEEP,
            actor=actor(message.from_user),
            reason="через бота",
            parse_result_id=row.id,
        )
    except manual.EditError as exc:
        await message.answer(f"⚠️ <b>Не удалось сохранить</b>\n\n{escape(str(exc))}")
        return
    await manual.resolve_parse(session, row.id, Resolution.FIXED, actor=actor(message.from_user))
    await state.clear()
    await message.answer(
        "✅ <b>Готово, время обновлено</b>\n\nНовые интервалы сохранены в таблице."
    )


@router.message(Fix.full_daily, F.text)
async def fix_full(
    message: Message, session: AsyncSession, settings: AppSettings, state: FSMContext
) -> None:
    assert message.text
    assert message.from_user
    data = await state.get_data()
    found = await _own_parse(session, message.from_user, int(data["parse_id"]))
    if found is None or found[2] is None:
        await state.clear()
        await message.answer(not_linked_text(message.from_user))
        return
    row, _raw, employee = found[0], found[1], found[2]
    result = parse_daily(message.text, clock.now(), settings.tz)
    if result.daily is None:
        problems = "\n".join(f"• {escape(i.message)}" for i in result.warnings)
        await message.answer(f"⚠️ <b>Всё ещё не получается разобрать</b>\n\n{problems}")
        return
    d = result.daily
    await manual.set_daily(
        session,
        employee_id=employee.id,
        work_date=d.work_date,
        intervals=[(i.start, i.end) for i in d.intervals],
        efficiency=d.efficiency,
        tasks=list(d.tasks),
        actor=actor(message.from_user),
        reason="дейлик прислан в личку",
        parse_result_id=row.id,
    )
    await manual.resolve_parse(session, row.id, Resolution.FIXED, actor=actor(message.from_user))
    await state.clear()
    await message.answer(
        f"✅ <b>Готово: дейлик за {d.work_date:%d.%m.%Y} сохранён</b>\n\n"
        "Часы, эффективность и задачи обновлены в таблице."
    )


@router.message(Fix.plan_day, F.text)
async def fix_plan_day(message: Message, session: AsyncSession, state: FSMContext) -> None:
    assert message.text
    assert message.from_user
    weekday = int((await state.get_data())["weekday"])
    owned = await _owned_with_data(session, message.from_user, state)
    if owned is None:
        await state.clear()
        return
    row, employee, data = owned
    week_start = date.fromisoformat(data["sprint_start"])
    day = week_start - timedelta(days=week_start.weekday()) + timedelta(days=weekday)
    text = message.text.strip().lower()
    try:
        if text in {"выходной", "вых", "-", "—"}:
            await manual.set_plan_day(
                session,
                employee_id=employee.id,
                day=day,
                kind=PlanDayKind.OFF,
                actor=actor(message.from_user),
                reason="через бота",
            )
        else:
            parsed = parse_interval_list(message.text)
            if not parsed:
                await message.answer("Не понял время. Пример: <code>16:30 - 20:00</code>")
                return
            await manual.set_plan_day(
                session,
                employee_id=employee.id,
                day=day,
                kind=PlanDayKind.WORK,
                intervals=[(p.interval.start, p.interval.end) for p in parsed],
                actor=actor(message.from_user),
                reason="через бота",
            )
    except (manual.EditError, ValueError) as exc:
        await message.answer(f"⚠️ <b>Не удалось сохранить</b>\n\n{escape(str(exc))}")
        return
    await manual.resolve_parse(session, row.id, Resolution.FIXED, actor=actor(message.from_user))
    await state.clear()
    await message.answer(
        f"✅ <b>Готово: план на {WEEKDAYS[weekday]} {day:%d.%m} обновлён</b>\n\n"
        "Расписание сохранено в таблице."
    )


@router.message(F.text)
async def fallback(message: Message) -> None:
    await message.answer("Не понял. Вот что я умею:\n\n" + texts.HELP, reply_markup=reply_menu())
