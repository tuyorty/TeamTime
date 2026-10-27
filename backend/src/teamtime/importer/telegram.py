"""Импорт истории из экспорта Telegram Desktop (``result.json``).

Тот же ``ingest``, что у бота, поэтому импорт идемпотентен: повторная загрузка того же файла
ничего не меняет, а сообщения, уже полученные ботом, не дублируются — ключ ``(chat_id,
message_id)`` совпадает (``chat_id`` приводится к виду Bot API: ``-100…``).

Формат экспорта:
- ``text`` — строка или список фрагментов (строки и объекты ``{"type", "text"}``);
- время — ``date_unixtime`` / ``edited_unixtime`` (UTC), поле ``date`` без часового пояса не берём;
- ``since`` — импортировать только сообщения с этой даты (по часовому поясу команды), старые
  считаются в ``older`` и не трогаются;
- темы форума — служебные сообщения ``action: "topic_created"``; сообщение в теме ссылается на
  корень темы или на другое сообщение этой темы через ``reply_to_message_id``.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.core.logging import get_logger
from teamtime.db.models import Source
from teamtime.parsing import MessageKind
from teamtime.parsing.text import fold
from teamtime.services.ingest import IncomingMessage, ingest
from teamtime.services.settings import AppSettings, load_settings

log = get_logger(__name__)


class ExportFormatError(ValueError):
    """Файл не похож на экспорт Telegram. Текст показывается пользователю."""


@dataclass
class ImportReport:
    chat_title: str = ""
    chat_id: int = 0
    total: int = 0
    imported: int = 0
    unchanged: int = 0
    skipped: int = 0
    older: int = 0
    statuses: Counter[str] = field(default_factory=Counter)
    topics: dict[int, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "chat_title": self.chat_title,
            "chat_id": self.chat_id,
            "total": self.total,
            "imported": self.imported,
            "unchanged": self.unchanged,
            "skipped": self.skipped,
            "older": self.older,
            "statuses": dict(self.statuses),
            "topics": {str(k): v for k, v in self.topics.items()},
            "errors": self.errors[:20],
        }


def flatten_text(text: Any) -> str:
    """``text`` экспорта → строка. Фрагменты бывают строками и объектами с полем ``text``."""
    if isinstance(text, str):
        return text
    if isinstance(text, list):
        return "".join(p if isinstance(p, str) else str(p.get("text", "")) for p in text)
    return ""


def bot_api_chat_id(export_id: int, chat_type: str) -> int:
    """В экспорте id супергруппы «голый»; Bot API видит его как -100<id>."""
    if export_id < 0:
        return export_id
    if chat_type in {
        "private_supergroup",
        "public_supergroup",
        "private_channel",
        "public_channel",
    }:
        return int(f"-100{export_id}")
    return -export_id


def author_id(raw: str | None) -> int | None:
    if not raw or not raw.startswith("user"):
        return None
    try:
        return int(raw.removeprefix("user"))
    except ValueError:
        return None


def topic_kind(title: str) -> MessageKind | None:
    """Подсказка по названию темы. Общая тема («Расписание и дейлики») подсказки не даёт."""
    t = fold(title)
    schedule = "распис" in t or "спринт" in t or "schedule" in t
    daily = "дейл" in t or "daily" in t or "отчет" in t
    if schedule == daily:
        return None
    return MessageKind.SCHEDULE if schedule else MessageKind.DAILY


def _ts(value: str | int | None) -> datetime | None:
    if value is None or value == "":
        return None
    return datetime.fromtimestamp(int(value), UTC)


def load_export(data: bytes | str) -> dict[str, Any]:
    try:
        parsed = json.loads(data)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ExportFormatError(
            "Файл не читается как JSON. Нужен result.json из Telegram Desktop."
        ) from exc
    if not isinstance(parsed, dict) or not isinstance(parsed.get("messages"), list):
        raise ExportFormatError(
            "В файле нет списка messages. Экспортируйте чат в Telegram Desktop в формате JSON."
        )
    return parsed


async def import_export(
    session: AsyncSession,
    export: dict[str, Any],
    *,
    settings: AppSettings | None = None,
    chat_id: int | None = None,
    since: date | None = None,
) -> ImportReport:
    settings = settings or await load_settings(session)
    report = ImportReport(chat_title=str(export.get("name", "")))
    report.chat_id = chat_id or bot_api_chat_id(
        int(export.get("id", 0)), str(export.get("type", ""))
    )
    is_forum = False

    messages: list[dict[str, Any]] = export["messages"]
    thread_of: dict[int, int] = {}
    for m in messages:
        if m.get("type") == "service" and m.get("action") == "topic_created":
            report.topics[int(m["id"])] = str(m.get("title", ""))
            thread_of[int(m["id"])] = int(m["id"])
            is_forum = True

    for m in messages:
        if m.get("type") != "message":
            continue
        report.total += 1
        mid = int(m["id"])
        reply = m.get("reply_to_message_id")
        thread = thread_of.get(int(reply)) if reply is not None else None
        if thread is not None:
            thread_of[mid] = thread
        text = flatten_text(m.get("text"))
        sent = _ts(m.get("date_unixtime"))
        if not text.strip() or sent is None:
            report.skipped += 1
            continue
        if since is not None and sent.astimezone(settings.tz).date() < since:
            report.older += 1
            continue
        try:
            outcome = await ingest(
                session,
                IncomingMessage(
                    chat_id=report.chat_id,
                    message_id=mid,
                    thread_id=thread,
                    text=text,
                    sent_at=sent,
                    edited_at=_ts(m.get("edited_unixtime")),
                    author_id=author_id(m.get("from_id")),
                    author_name=str(m.get("from") or ""),
                    source=Source.IMPORT,
                    chat_title=report.chat_title,
                    is_forum=is_forum,
                    topic_hint=topic_kind(report.topics.get(thread, "")) if thread else None,
                ),
                settings,
            )
        except Exception as exc:  # одно битое сообщение не должно сорвать импорт
            log.warning("import.message_failed", message_id=mid, error=str(exc))
            report.errors.append(f"Сообщение {mid}: {exc}")
            continue
        if outcome.skipped:
            report.skipped += 1
        elif not outcome.changed:
            report.unchanged += 1
        else:
            report.imported += 1
            report.statuses[outcome.status.value if outcome.status else "unknown"] += 1
    log.info("import.done", **{k: v for k, v in report.as_dict().items() if k != "errors"})
    return report
