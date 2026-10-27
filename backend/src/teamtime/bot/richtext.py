"""Текст из «богатого» сообщения Telegram (rich_message): списки, заголовки, таблицы.

У такого сообщения нет ``text``: содержимое лежит деревом блоков. Парсеру нужен обычный текст,
поэтому дерево разворачивается в строки, как их видит человек: пункт списка — строка с меткой
(«•», «1.»), абзац — строка, ячейки таблицы — через « | ». Обход идёт по полям, а не по типам:
новый вид блока с полем ``text`` или ``blocks`` разберётся без правки кода.
"""

from __future__ import annotations

from typing import Any


def rich_plain_text(rich: Any) -> str:
    """Обычный текст из ``Message.rich_message``."""
    return "\n".join(_blocks(getattr(rich, "blocks", None) or [])).strip()


def _blocks(blocks: list[Any]) -> list[str]:
    lines: list[str] = []
    for block in blocks:
        lines.extend(_block(block))
    return lines


def _block(block: Any) -> list[str]:
    items = getattr(block, "items", None)
    if items is not None:  # список
        lines: list[str] = []
        for item in items:
            inner = _blocks(getattr(item, "blocks", None) or []) or [""]
            label = getattr(item, "label", "") or ""
            lines.append(f"{label} {inner[0]}".strip())
            lines.extend(inner[1:])
        return lines
    cells = getattr(block, "cells", None)
    if cells is not None:  # таблица
        return [" | ".join(_text(getattr(c, "text", None)) for c in row) for row in cells]

    lines = []
    for field in ("summary", "text", "expression"):
        if (value := getattr(block, field, None)) is not None:
            lines.extend(_text(value).split("\n"))
    lines.extend(_blocks(getattr(block, "blocks", None) or []))
    caption = getattr(block, "caption", None)
    if caption is not None:
        lines.extend(_text(getattr(caption, "text", caption)).split("\n"))
    return lines


def _text(value: Any) -> str:
    """RichText: строка, список кусков или обёртка (жирный, ссылка, хештег…) с полем text."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(_text(v) for v in value)
    for field in ("text", "alternative_text", "expression"):
        if (inner := getattr(value, field, None)) is not None:
            return _text(inner)
    button = getattr(value, "button", None)
    return _text(getattr(button, "text", None)) if button is not None else ""
