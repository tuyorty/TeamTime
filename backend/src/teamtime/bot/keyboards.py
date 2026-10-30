"""Клавиатуры и callback-данные бота."""

from __future__ import annotations

import calendar
from datetime import date

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

from teamtime.bot.dates import date_key, shift_period
from teamtime.services.reports import MONTHS

MENU = {
    "✍️ Дейлик": "daily",
    "🗓 Моя неделя": "week",
    "📊 Месяц": "month",
    "👥 Сегодня": "today",
    "📋 Итоги дня": "summary",
    "👤 Сотрудники": "people",
    "🙅 Не приду": "absent",
    "✏️ Исправить": "fix",
    "🔎 Мой день": "check",
    "🔔 Уведомления": "notifications",
}
"""Кнопки постоянного меню в личке: подпись → действие (те же, что у MenuCb)."""


class MenuCb(CallbackData, prefix="m"):
    action: str


class PersonalCb(CallbackData, prefix="ps"):
    action: str
    value: str = ""


class ReportCb(CallbackData, prefix="rp"):
    view: str
    day: str
    employee_id: int = 0
    page: int = 0


class PeopleCb(CallbackData, prefix="pe"):
    day: str
    view: str = "month"
    page: int = 0


class CalendarCb(CallbackData, prefix="cl"):
    view: str
    day: str
    month: str
    employee_id: int = 0


class FixCb(CallbackData, prefix="fx"):
    action: str
    parse_id: int
    value: int = 0


class StatusCb(CallbackData, prefix="st"):
    kind: str


class StatusRequestCb(CallbackData, prefix="sr"):
    action: str
    request_id: int


def status_request_menu(request_id: int, pending: bool = True) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text="Проверить решение",
        callback_data=StatusRequestCb(action="check", request_id=request_id),
    )
    if pending:
        kb.button(
            text="Отозвать заявку",
            callback_data=StatusRequestCb(action="withdraw", request_id=request_id),
        )
    kb.adjust(1)
    return kb.as_markup()


def reply_menu() -> ReplyKeyboardMarkup:
    """Постоянная панель под полем ввода в личке: всегда под рукой, ничего не нужно набирать."""
    labels = list(MENU)
    rows = [labels[index : index + 2] for index in range(0, len(labels), 2)]
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t) for t in row] for row in rows],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выберите действие или пришлите сообщение",
    )


def report_menu(
    view: str,
    day: date,
    today: date,
    *,
    employee_id: int = 0,
    page: int = 0,
    pages: int = 1,
) -> InlineKeyboardMarkup:
    """Период, дата и страницы отчёта хранятся в кнопках, независимо от других сообщений."""
    kb = InlineKeyboardBuilder()
    key = date_key(day)
    previous, following = shift_period(day, view, -1), shift_period(day, view, 1)
    arrows = []
    if previous:
        arrows.append(
            InlineKeyboardButton(
                text="‹ " + (previous.strftime("%d.%m") if view in {"day", "summary"} else "Назад"),
                callback_data=ReportCb(
                    view=view, day=date_key(previous), employee_id=employee_id
                ).pack(),
            )
        )
    arrows.append(
        InlineKeyboardButton(
            text=f"📅 {day:%d.%m.%Y}",
            callback_data=CalendarCb(
                view=view, day=key, month=date_key(day.replace(day=1)), employee_id=employee_id
            ).pack(),
        )
    )
    if following:
        arrows.append(
            InlineKeyboardButton(
                text=(following.strftime("%d.%m") if view in {"day", "summary"} else "Вперёд")
                + " ›",
                callback_data=ReportCb(
                    view=view, day=date_key(following), employee_id=employee_id
                ).pack(),
            )
        )
    kb.row(*arrows)
    tabs = (
        (("day", "День"), ("week", "Неделя"), ("month", "Месяц"))
        if employee_id
        else (("day", "Расписание"), ("summary", "📋 Итоги дня"), ("week", "Неделя"))
    )
    kb.row(
        *[
            InlineKeyboardButton(
                text=f"· {label} ·" if target == view else label,
                callback_data=ReportCb(view=target, day=key, employee_id=employee_id).pack(),
            )
            for target, label in tabs
        ]
    )
    if pages > 1:
        paging = []
        for target, label in (
            (page - 1, "‹ Страница"),
            (page, f"{page + 1}/{pages}"),
            (page + 1, "Страница ›"),
        ):
            if 0 <= target < pages:
                paging.append(
                    InlineKeyboardButton(
                        text=label,
                        callback_data=ReportCb(
                            view=view, day=key, employee_id=employee_id, page=target
                        ).pack(),
                    )
                )
        kb.row(*paging)
    kb.row(
        InlineKeyboardButton(
            text="Сегодня" if view in {"day", "summary"} else "Текущий период",
            callback_data=ReportCb(view=view, day=date_key(today), employee_id=employee_id).pack(),
        ),
        InlineKeyboardButton(
            text="👤 Сотрудники",
            callback_data=PeopleCb(day=key, view=view if employee_id else "month").pack(),
        ),
    )
    return kb.as_markup()


def people_menu(
    employees: list[tuple[int, str]], day: date, view: str, page: int, pages: int
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for employee_id, name in employees:
        kb.button(
            text=name[:50],
            callback_data=ReportCb(view=view, day=date_key(day), employee_id=employee_id),
        )
    kb.adjust(2)
    if pages > 1:
        paging = []
        for target, label in ((page - 1, "‹"), (page, f"{page + 1}/{pages}"), (page + 1, "›")):
            if 0 <= target < pages:
                paging.append(
                    InlineKeyboardButton(
                        text=label,
                        callback_data=PeopleCb(day=date_key(day), view=view, page=target).pack(),
                    )
                )
        kb.row(*paging)
    kb.row(
        InlineKeyboardButton(
            text="👥 День команды", callback_data=ReportCb(view="day", day=date_key(day)).pack()
        )
    )
    return kb.as_markup()


def calendar_menu(
    view: str, selected: date, month: date, today: date, employee_id: int = 0
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    key = date_key(selected)
    navigation = []
    for step, label in ((-1, "‹"), (0, f"{MONTHS[month.month - 1]} {month.year}"), (1, "›")):
        target = shift_period(month, "month", step)
        if target:
            navigation.append(
                InlineKeyboardButton(
                    text=label,
                    callback_data=CalendarCb(
                        view=view, day=key, month=date_key(target), employee_id=employee_id
                    ).pack(),
                )
            )
    kb.row(*navigation)
    kb.row(
        *[
            InlineKeyboardButton(text=label, callback_data="browse:noop")
            for label in ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")
        ]
    )
    for week in calendar.monthcalendar(month.year, month.month):
        buttons = []
        for number in week:
            day = month.replace(day=number) if number else None
            label = (
                f"[{number}]" if day == selected else f"{number}•" if day == today else str(number)
            )
            buttons.append(
                InlineKeyboardButton(
                    text=label if day else " ",
                    callback_data=ReportCb(
                        view=view, day=date_key(day), employee_id=employee_id
                    ).pack()
                    if day
                    else "browse:noop",
                )
            )
        kb.row(*buttons)
    kb.row(
        InlineKeyboardButton(
            text="Сегодня",
            callback_data=ReportCb(view=view, day=date_key(today), employee_id=employee_id).pack(),
        ),
        InlineKeyboardButton(
            text="‹ К отчёту",
            callback_data=ReportCb(view=view, day=key, employee_id=employee_id).pack(),
        ),
    )
    return kb.as_markup()


class ReminderCb(CallbackData, prefix="rm"):
    action: str
    day: str


def reminder_menu(
    topic_url: str | None, work_date: date | None = None, *, followup: bool = False
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if topic_url:
        kb.button(text="✍️ Открыть тему «Дейлики»", url=topic_url)
    kb.button(text="🔎 Проверить мои сообщения", callback_data=MenuCb(action="fix"))
    if work_date and not followup:
        kb.button(
            text="⏰ Напомнить через 30 минут · один раз",
            callback_data=ReminderCb(action="snooze", day=date_key(work_date)),
        )
    kb.adjust(1)
    return kb.as_markup()


def status_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for kind, text in (
        ("absent", "Не приду сегодня"),
        ("remote", "Удалёнка сегодня"),
        ("sick", "Больничный сегодня"),
        ("dayoff", "Отгул сегодня"),
        ("vacation", "Отпуск…"),
        ("clear", "Снять статус сегодня"),
    ):
        kb.button(text=text, callback_data=StatusCb(kind=kind))
    kb.adjust(2)
    return kb.as_markup()


def fix_menu(
    parse_id: int, *, kind: str, has_data: bool, note_days: list[tuple[int, str]]
) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if kind == "daily" and has_data:
        kb.button(text="Время", callback_data=FixCb(action="time", parse_id=parse_id))
        kb.button(text="Эффективность", callback_data=FixCb(action="eff", parse_id=parse_id))
    if kind == "daily" and not has_data:
        kb.button(
            text="Прислать дейлик заново", callback_data=FixCb(action="full", parse_id=parse_id)
        )
    for weekday, label in note_days:
        kb.button(
            text=f"Уточнить {label}",
            callback_data=FixCb(action="day", parse_id=parse_id, value=weekday),
        )
    if has_data:
        kb.button(text="Всё верно", callback_data=FixCb(action="accept", parse_id=parse_id))
    kb.adjust(2)
    return kb.as_markup()


def efficiency_menu(parse_id: int) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"{v}%",
                callback_data=FixCb(action="eff_set", parse_id=parse_id, value=v).pack(),
            )
            for v in values
        ]
        for values in ((50, 60, 70), (80, 90, 100))
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
