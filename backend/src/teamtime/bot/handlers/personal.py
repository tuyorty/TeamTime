"""Личные действия: мастер дейлика, проверка дня и уведомления."""

from __future__ import annotations

import contextlib
import re
from datetime import date, timedelta
from html import escape
from uuid import uuid4

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, User
from aiogram.utils.keyboard import InlineKeyboardBuilder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.bot import texts
from teamtime.bot.dates import date_key, read_date
from teamtime.bot.handlers.browse import display_report, report_text
from teamtime.bot.identity import employee_for, not_linked_text
from teamtime.bot.keyboards import MENU, PersonalCb, ReminderCb
from teamtime.calc.duration import format_hm
from teamtime.core import clock
from teamtime.db.models import (
    BotDraft,
    Employee,
    NotificationPreference,
    ParseResultRow,
    RawMessage,
    RawMessageVersion,
    Resolution,
)
from teamtime.parsing.text import TimeFormatError, parse_interval_list
from teamtime.services import manual, notifications
from teamtime.services.facts import today_local
from teamtime.services.manual import current_daily
from teamtime.services.settings import AppSettings

router = Router(name="personal")
router.message.filter(F.chat.type == "private")
router.callback_query.filter(F.message.chat.type == "private")


class DailyDraft(StatesGroup):
    day = State()
    time = State()
    efficiency = State()
    preview = State()


class QuietTime(StatesGroup):
    value = State()


# Во время ввода команды и постоянное меню остаются доступны.
INPUT_TEXT = F.text & ~F.text.startswith("/") & ~F.text.in_(MENU)


async def own_employee(
    message: Message, session: AsyncSession, user: User | None
) -> Employee | None:
    if user is None:
        return None
    _, employee = await employee_for(session, user)
    if employee is None or not employee.is_active:
        await message.answer(not_linked_text(user) if employee is None else "Сотрудник неактивен.")
        return None
    return employee


async def cancel_draft(session: AsyncSession, state: FSMContext) -> None:
    draft_id = (await state.get_data()).get("draft_id")
    if draft_id:
        draft = await session.get(BotDraft, draft_id)
        if draft and draft.submitted_at is None:
            draft.payload = {**draft.payload, "cancelled": True}
    await state.clear()


@router.message(Command("daily"))
@router.message(F.text == "✍️ Дейлик")
async def start_daily(
    message: Message, session: AsyncSession, settings: AppSettings, state: FSMContext
) -> None:
    employee = await own_employee(message, session, message.from_user)
    if employee is None:
        return
    await cancel_draft(session, state)
    await state.set_state(DailyDraft.day)
    await state.update_data(
        user_id=message.from_user.id if message.from_user else None, employee_id=employee.id
    )
    kb = InlineKeyboardBuilder()
    today = today_local(settings)
    for day, label in ((today, "Сегодня"), (today - timedelta(days=1), "Вчера")):
        kb.button(
            text=f"{label} · {day:%d.%m}",
            callback_data=PersonalCb(action="draft_day", value=date_key(day)),
        )
    kb.adjust(2)
    await message.answer(
        "✍️ <b>Новый дейлик</b>\n\nЗа какой день? Выберите кнопку или пришлите дату, "
        "например <code>29.10.2026</code>.\nОтмена: /cancel.",
        reply_markup=kb.as_markup(),
    )


async def choose_day(
    message: Message, selected: date, settings: AppSettings, state: FSMContext
) -> None:
    if selected > today_local(settings) or selected.year < 2000:
        await message.answer("Укажите сегодняшний или прошедший день.")
        return
    await state.update_data(day=selected.isoformat())
    await state.set_state(DailyDraft.time)
    await message.answer(
        f"📅 <b>{selected:%d.%m.%Y}</b>\n\nПришлите фактические интервалы работы, например:\n"
        "<code>10:00–14:00; 15:00–18:00</code>"
    )


@router.message(DailyDraft.day, INPUT_TEXT)
async def draft_day_text(message: Message, settings: AppSettings, state: FSMContext) -> None:
    try:
        value = (message.text or "").strip()
        selected = date.fromisoformat("-".join(reversed(value.split("."))))
    except ValueError:
        await message.answer("Не понял дату. Пример: <code>29.10.2026</code>.")
        return
    await choose_day(message, selected, settings, state)


@router.message(DailyDraft.time, INPUT_TEXT)
async def draft_time(message: Message, session: AsyncSession, state: FSMContext) -> None:
    try:
        parsed = parse_interval_list(message.text or "")
    except TimeFormatError:
        parsed = None
    if not parsed:
        await message.answer("Не понял время. Пример: <code>10:00–14:00; 15:00–18:00</code>.")
        return
    if len(parsed) > 12:
        await message.answer("Для одного дня укажите не больше 12 интервалов.")
        return
    intervals = [(p.interval.start, p.interval.end) for p in parsed]
    try:
        manual._check_intervals(intervals)
    except manual.EditError as exc:
        await message.answer(escape(str(exc)))
        return
    await state.update_data(intervals=intervals)
    data = await state.get_data()
    if "efficiency" in data:
        await preview(message, session, state)
        return
    await state.set_state(DailyDraft.efficiency)
    kb = InlineKeyboardBuilder()
    for value in (50, 60, 70, 80, 90, 100):
        kb.button(text=f"{value}%", callback_data=PersonalCb(action="draft_eff", value=str(value)))
    kb.adjust(3)
    await message.answer(
        "📊 <b>Эффективность</b>\n\nВыберите кнопку или пришлите целое число от 0 до 100.",
        reply_markup=kb.as_markup(),
    )


async def choose_efficiency(
    message: Message, value: int, session: AsyncSession, state: FSMContext
) -> None:
    if not 0 <= value <= 100:
        await message.answer("Нужно целое число от 0 до 100.")
        return
    await state.update_data(efficiency=value)
    await preview(message, session, state)


@router.message(DailyDraft.efficiency, INPUT_TEXT)
async def draft_efficiency(message: Message, session: AsyncSession, state: FSMContext) -> None:
    try:
        value = int((message.text or "").strip().rstrip("%"))
    except ValueError:
        await message.answer("Нужно целое число от 0 до 100.")
        return
    await choose_efficiency(message, value, session, state)


async def preview(message: Message, session: AsyncSession, state: FSMContext) -> None:
    user = message.from_user
    # У callback-сообщения автор — бот; настоящий пользователь хранится при выборе кнопки.
    data = await state.get_data()
    user_id = data.get("user_id") or (user.id if user else None)
    if user_id is None:
        return
    employee_id = data.get("employee_id")
    if employee_id is None and user:
        _, employee = await employee_for(session, user)
        employee_id = employee.id if employee else None
    if employee_id is None:
        return
    selected = date.fromisoformat(data["day"])
    previous = await current_daily(session, employee_id, selected)
    payload = {key: data[key] for key in ("day", "intervals", "efficiency")}
    payload["previous_daily_id"] = previous.id if previous else None
    draft = await session.get(BotDraft, data["draft_id"]) if data.get("draft_id") else None
    if draft is None:
        draft = BotDraft(id=uuid4().hex, employee_id=employee_id, user_id=user_id, payload=payload)
        session.add(draft)
    else:
        draft.payload = payload
    await session.flush()
    await state.update_data(draft_id=draft.id, user_id=user_id, employee_id=employee_id)
    await state.set_state(DailyDraft.preview)
    intervals = payload["intervals"]
    total = sum((b - a) if b >= a else 86400 - a + b for a, b in intervals)
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ Сохранить дейлик", callback_data=PersonalCb(action="draft_save", value=draft.id)
    )
    for key, label in (("time", "Время"), ("efficiency", "Эффективность")):
        kb.button(text=label, callback_data=PersonalCb(action=f"draft_edit_{key}", value=draft.id))
    kb.adjust(1, 2)
    body = f"✍️ <b>Проверьте дейлик · {selected:%d.%m.%Y}</b>\n\n" + "; ".join(
        texts.span(a, b) for a, b in intervals
    )
    body += (
        f"\nОтработано: <b>{format_hm(total)}</b> · эффективность <b>{payload['efficiency']}%</b>"
    )
    if previous:
        body += (
            "\n\n⚠️ За этот день уже есть дейлик. После подтверждения будет сохранена новая версия."
        )
    await message.answer(body, reply_markup=kb.as_markup())


@router.message(Command("cancel"))
async def cancel(message: Message, session: AsyncSession, state: FSMContext) -> None:
    await cancel_draft(session, state)
    await message.answer("Действие отменено.")


async def send_check(
    message: Message, session: AsyncSession, settings: AppSettings, user: User
) -> None:
    employee = await own_employee(message, session, user)
    if employee is None:
        return
    today = today_local(settings)
    text = await report_text(session, settings, "day", today, employee.id)
    pending = await session.scalar(
        select(ParseResultRow.id)
        .join(RawMessageVersion)
        .join(RawMessage)
        .where(
            RawMessage.author_tg_id == user.id,
            ParseResultRow.is_latest,
            ParseResultRow.resolution == Resolution.PENDING,
        )
        .limit(1)
    )
    if pending:
        text += "\n\n⚠️ Есть сообщения с вопросами. Откройте /fix, чтобы проверить их."
    text += "\n\nЗаполнить дейлик: /daily"
    await display_report(message, text, settings, "day", today, employee.id)


@router.message(Command("check"))
@router.message(F.text == "🔎 Мой день")
async def check_day(
    message: Message, session: AsyncSession, settings: AppSettings, state: FSMContext
) -> None:
    await state.clear()
    if message.from_user:
        await send_check(message, session, settings, message.from_user)


def preferences_text(
    preference: NotificationPreference | None, settings: AppSettings
) -> tuple[str, InlineKeyboardBuilder]:
    enabled = preference.enabled if preference else True
    delay = (
        preference.delay_minutes if preference else None
    ) or settings.bot.reminder_delay_minutes
    quiet = "выключено"
    if preference and preference.quiet_start is not None and preference.quiet_end is not None:
        quiet = (
            f"{preference.quiet_start // 60:02}:{preference.quiet_start % 60:02}–"
            f"{preference.quiet_end // 60:02}:{preference.quiet_end % 60:02}"
        )
    text = (
        "🔔 <b>Личные уведомления</b>\n\n"
        f"Напоминания: <b>{'включены' if enabled else 'выключены'}</b>\n"
        f"Задержка после смены: <b>{delay} мин</b>\nТихое время: <b>{quiet}</b>\n"
        f"Часовой пояс: {escape(settings.timezone)}"
    )
    if not settings.bot.reminders_enabled:
        text += "\n\nОбщие напоминания сейчас выключены администратором."
    text += (
        "\n\nТихое время откладывает доставку. Кнопка в напоминании позволяет один раз "
        "запросить повтор через 30 минут."
    )
    kb = InlineKeyboardBuilder()
    kb.button(
        text="Выключить" if enabled else "Включить",
        callback_data=PersonalCb(action="notify_toggle"),
    )
    for value in (15, 30, 60):
        kb.button(
            text=f"{value} мин", callback_data=PersonalCb(action="notify_delay", value=str(value))
        )
    kb.button(text="Тихое время…", callback_data=PersonalCb(action="notify_quiet"))
    kb.button(text="Убрать тихое время", callback_data=PersonalCb(action="notify_quiet_off"))
    kb.adjust(1, 3, 2)
    return text, kb


@router.message(Command("notifications"))
@router.message(F.text == "🔔 Уведомления")
async def show_notifications(
    message: Message, session: AsyncSession, settings: AppSettings, state: FSMContext
) -> None:
    await state.clear()
    employee = await own_employee(message, session, message.from_user)
    if employee:
        preference = await session.get(NotificationPreference, employee.id)
        text, kb = preferences_text(preference, settings)
        await message.answer(text, reply_markup=kb.as_markup())


@router.message(QuietTime.value, INPUT_TEXT)
async def quiet_value(
    message: Message, session: AsyncSession, settings: AppSettings, state: FSMContext
) -> None:
    employee = await own_employee(message, session, message.from_user)
    if employee is None or message.from_user is None:
        return
    match = re.fullmatch(
        r"\s*([01]?\d|2[0-3]):([0-5]\d)\s*[-–—]\s*([01]?\d|2[0-3]):([0-5]\d)\s*", message.text or ""
    )
    if not match:
        await message.answer("Пример: <code>22:00–09:00</code>. Отмена: /cancel.")
        return
    start, end = int(match[1]) * 60 + int(match[2]), int(match[3]) * 60 + int(match[4])
    try:
        preference = await notifications.save_preferences(
            session,
            employee.id,
            {"quiet_start": start, "quiet_end": end},
            f"bot:{message.from_user.id}",
        )
    except manual.EditError as exc:
        await message.answer(escape(str(exc)))
        return
    await state.clear()
    text, kb = preferences_text(preference, settings)
    await message.answer(text, reply_markup=kb.as_markup())


@router.callback_query(PersonalCb.filter(), flags={"callback_answer": {"disabled": True}})
async def personal_action(
    query: CallbackQuery,
    callback_data: PersonalCb,
    session: AsyncSession,
    settings: AppSettings,
    state: FSMContext,
) -> None:
    if not isinstance(query.message, Message):
        await query.answer()
        return
    message = query.message
    employee = await own_employee(message, session, query.from_user)
    if employee is None:
        await query.answer("Нужен привязанный активный аккаунт", show_alert=True)
        return
    action, value = callback_data.action, callback_data.value
    if action == "draft_day":
        if await state.get_state() != DailyDraft.day.state:
            await query.answer("Откройте новый мастер: /daily", show_alert=True)
            return
        try:
            selected = read_date(value)
        except ValueError:
            await query.answer("Некорректная дата", show_alert=True)
            return
        await state.update_data(user_id=query.from_user.id, employee_id=employee.id)
        await query.answer()
        await choose_day(message, selected, settings, state)
        return
    if action == "draft_eff":
        if await state.get_state() != DailyDraft.efficiency.state or not value.isdigit():
            await query.answer("Откройте текущий шаг мастера", show_alert=True)
            return
        await state.update_data(user_id=query.from_user.id, employee_id=employee.id)
        await query.answer()
        await choose_efficiency(message, int(value), session, state)
        return
    if action == "draft_save" or action.startswith("draft_edit_"):
        draft = await session.scalar(select(BotDraft).where(BotDraft.id == value).with_for_update())
        if (
            draft is None
            or draft.user_id != query.from_user.id
            or draft.employee_id != employee.id
            or draft.payload.get("cancelled")
        ):
            await query.answer("Черновик недоступен. Откройте /daily", show_alert=True)
            return
        if draft.submitted_at:
            await query.answer("Этот дейлик уже сохранён", show_alert=True)
            return
        if action.startswith("draft_edit_"):
            field = action.removeprefix("draft_edit_")
            states = {
                "time": DailyDraft.time,
                "efficiency": DailyDraft.efficiency,
            }
            if field not in states:
                await query.answer()
                return
            await state.set_data(
                {
                    **draft.payload,
                    "draft_id": draft.id,
                    "user_id": query.from_user.id,
                    "employee_id": employee.id,
                }
            )
            await state.set_state(states[field])
            await query.answer()
            await message.answer(
                {
                    "time": "Пришлите фактические интервалы.",
                    "efficiency": "Пришлите эффективность от 0 до 100.",
                }[field]
            )
            return
        day = date.fromisoformat(draft.payload["day"])
        previous = await current_daily(session, employee.id, day)
        if (previous.id if previous else None) != draft.payload.get("previous_daily_id"):
            await query.answer(
                "Данные дня изменились. Проверьте их через /check и откройте /daily заново.",
                show_alert=True,
            )
            return
        daily = await manual.set_daily(
            session,
            employee_id=employee.id,
            work_date=day,
            intervals=[tuple(pair) for pair in draft.payload["intervals"]],
            efficiency=draft.payload["efficiency"],
            actor=f"bot:{query.from_user.id}",
            reason="Мастер дейлика",
        )
        await manual.resolve_daily_inbox(
            session, employee.id, day, actor=f"bot:{query.from_user.id}"
        )
        draft.submitted_at, draft.daily_id = clock.now(), daily.id
        await session.commit()
        await state.clear()
        await query.answer("Дейлик сохранён")
        await message.edit_text(
            f"✅ <b>Дейлик за {day:%d.%m.%Y} сохранён</b>\n\n"
            "Часы и эффективность сохранены. Проверить: /check."
        )
        return
    if action == "check":
        await query.answer()
        await send_check(message, session, settings, query.from_user)
        return
    preference = await session.get(NotificationPreference, employee.id)
    values: dict[str, object] = {}
    if action == "notify_toggle":
        values = {"enabled": not (preference.enabled if preference else True)}
    elif action == "notify_delay" and value in {"15", "30", "60"}:
        values = {"delay_minutes": int(value)}
    elif action == "notify_quiet_off":
        values = {"quiet_start": None, "quiet_end": None}
    elif action == "notify_quiet":
        await state.set_state(QuietTime.value)
        await query.answer()
        await message.answer(
            "Пришлите тихое время, например <code>22:00–09:00</code>. "
            "Используется часовой пояс команды."
        )
        return
    if not values:
        await query.answer()
        return
    preference = await notifications.save_preferences(
        session, employee.id, values, f"bot:{query.from_user.id}"
    )
    await query.answer("Сохранено")
    text, kb = preferences_text(preference, settings)
    with contextlib.suppress(TelegramBadRequest):
        await message.edit_text(text, reply_markup=kb.as_markup())


@router.callback_query(ReminderCb.filter(), flags={"callback_answer": {"disabled": True}})
async def snooze_reminder(
    query: CallbackQuery, callback_data: ReminderCb, session: AsyncSession
) -> None:
    _, employee = await employee_for(session, query.from_user)
    if employee is None or not employee.is_active or not isinstance(query.message, Message):
        await query.answer("Недоступно", show_alert=True)
        return
    try:
        day = read_date(callback_data.day)
        await notifications.snooze(session, employee.id, day, query.message.chat.id)
    except (ValueError, manual.EditError) as exc:
        await query.answer(str(exc), show_alert=True)
        return
    await session.commit()
    await query.answer("Один повтор запланирован через 30 минут", show_alert=True)
