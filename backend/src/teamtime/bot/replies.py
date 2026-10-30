"""Длинные отчёты делим по завершённым HTML-строкам; кнопки остаются под последней частью."""

from __future__ import annotations

from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, LinkPreviewOptions, Message

REPORT_LIMIT = 3600


def _size(text: str) -> int:
    return len(text.encode("utf-16-le")) // 2


def report_parts(text: str, *, limit: int = REPORT_LIMIT) -> list[str]:
    """Форматтеры завершают HTML-теги внутри каждой строки и ограничивают длину полей."""
    parts: list[str] = []
    current = ""
    for line in text.splitlines():
        if _size(line) > limit:
            raise ValueError("Строка отчёта превышает допустимую длину")
        if current and _size(current) + _size(line) + 1 > limit:
            parts.append(current.rstrip())
            current = ""
        current += ("\n" if current else "") + line
    if current.strip():
        parts.append(current.rstrip())
    return parts


async def answer_report(
    message: Message, text: str, reply_markup: InlineKeyboardMarkup | None = None
) -> None:
    parts = report_parts(text)
    for index, part in enumerate(parts):
        heading = f"<i>Продолжение · {index + 1}/{len(parts)}</i>\n\n" if index else ""
        await message.answer(
            heading + part,
            parse_mode=ParseMode.HTML,
            link_preview_options=LinkPreviewOptions(is_disabled=True),
            reply_markup=reply_markup if index == len(parts) - 1 else None,
        )
