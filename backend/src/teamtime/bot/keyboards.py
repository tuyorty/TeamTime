"""Клавиатуры и callback-данные бота."""

from __future__ import annotations

from datetime import date
from urllib.parse import urlsplit

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

MENU = {
    "🗓 Моя неделя": "week",
    "📊 Месяц": "month",
    "👥 Сегодня": "today",
    "📋 Итоги дня": "summary",
    "🙅 Не приду": "absent",
    "✏️ Исправить": "fix",
}
"""Кнопки постоянного меню в личке: подпись → действие (те же, что у MenuCb)."""


class MenuCb(CallbackData, prefix="m"):
    action: str


class FixCb(CallbackData, prefix="fx"):
    action: str
    parse_id: int
    value: int = 0


class StatusCb(CallbackData, prefix="st"):
    kind: str


def reply_menu() -> ReplyKeyboardMarkup:
    """Постоянная панель под полем ввода в личке: всегда под рукой, ничего не нужно набирать."""
    labels = list(MENU)
    rows = [labels[0:2], labels[2:4], labels[4:]]
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t) for t in row] for row in rows],
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выберите действие или пришлите сообщение",
    )


def dashboard_menu(
    public_url: str, path: str, label: str, *, summary: bool = False
) -> InlineKeyboardMarkup | None:
    """Ссылка на соответствующий экран; итоги открываются внутри «Сегодня»."""
    kb = InlineKeyboardBuilder()
    if summary:
        kb.button(text="📋 Итоги дня", callback_data=MenuCb(action="summary"))
    if urlsplit(public_url).scheme in {"http", "https"} and urlsplit(public_url).netloc:
        kb.button(text=label, url=public_url.rstrip("/") + path)
    kb.adjust(1)
    markup = kb.as_markup()
    return markup if markup.inline_keyboard else None


def reminder_menu(public_url: str, day: date, topic_url: str | None) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    if topic_url:
        kb.button(text="✍️ Открыть тему «Дейлики»", url=topic_url)
    kb.button(text="🔎 Проверить мои сообщения", callback_data=MenuCb(action="fix"))
    dashboard = dashboard_menu(public_url, f"/?view=summary&date={day}", "📊 Итоги этого дня")
    if dashboard:
        kb.attach(InlineKeyboardBuilder.from_markup(dashboard))
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
