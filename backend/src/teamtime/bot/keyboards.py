"""Клавиатуры и callback-данные бота."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


class MenuCb(CallbackData, prefix="m"):
    action: str


class FixCb(CallbackData, prefix="fx"):
    action: str
    parse_id: int
    value: int = 0


class StatusCb(CallbackData, prefix="st"):
    kind: str


def main_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="Моя неделя", callback_data=MenuCb(action="week"))
    kb.button(text="Месяц", callback_data=MenuCb(action="month"))
    kb.button(text="Сегодня", callback_data=MenuCb(action="today"))
    kb.button(text="Не приду / статус", callback_data=MenuCb(action="absent"))
    kb.button(text="Исправить", callback_data=MenuCb(action="fix"))
    kb.adjust(3, 2)
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
