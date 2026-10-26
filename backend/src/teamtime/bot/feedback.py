"""Что бот делает в теме после разбора: реакция и, при проблемах, одна короткая строка.

Отдельно от aiogram, чтобы эмулятор и тесты использовали ту же логику.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

from teamtime.parsing import MessageKind
from teamtime.services.ingest import IngestOutcome
from teamtime.services.settings import AppSettings


@dataclass(frozen=True, slots=True)
class GroupFeedback:
    reaction: str | None
    reply: str | None
    """Текст ответа в теме (HTML). None — ничего не писать."""


def fix_link(bot_username: str | None, parse_result_id: int | None) -> str | None:
    if not bot_username or parse_result_id is None:
        return None
    return f"https://t.me/{bot_username}?start=fix_{parse_result_id}"


def group_feedback(
    outcome: IngestOutcome, settings: AppSettings, *, bot_username: str | None
) -> GroupFeedback:
    if outcome.skipped or outcome.kind is MessageKind.UNKNOWN:
        return GroupFeedback(None, None)
    if not outcome.changed:
        return GroupFeedback(None, None)
    cfg = settings.bot
    if not outcome.needs_attention:
        reaction = cfg.reaction_edit if outcome.is_edit else cfg.reaction_ok
        reply = None if cfg.feedback == "reaction" else "Принято"
        return GroupFeedback(reaction, reply)

    problem = outcome.problems[0].message if outcome.problems else "нужна проверка"
    # В тексте проблемы бывает имя из Telegram или строка из сообщения — только как текст.
    problem = escape(f"{problem[0].upper()}{problem[1:]}")
    link = fix_link(bot_username, outcome.parse_result_id)
    tail = f' <a href="{link}">Исправить в боте</a>' if link else ""
    return GroupFeedback(cfg.reaction_warn, f"{problem}.{tail}")
