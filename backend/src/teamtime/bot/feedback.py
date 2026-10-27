"""Что бот делает в теме после разбора: реакция и, при проблемах, короткий список «что не так
и как написать правильно».

Отдельно от aiogram, чтобы эмулятор и тесты использовали ту же логику.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

from teamtime.parsing import Issue, MessageKind
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


MAX_PROBLEMS = 3
QUOTE_LEN = 40

HOW_TO_FIX = {
    # дейлик
    "no_date": "первой строкой нужна дата, например «23.10.2026»",
    "bad_date": "проверьте дату в первой строке, например «23.10.2026»",
    "no_intervals": "добавьте строку со временем, например «10:00 - 18:00»",
    "no_efficiency": "добавьте строку «Эффективность: 80%»",
    "bad_efficiency": "нужно целое число от 0 до 100: «Эффективность: 80%»",
    "duplicate_efficiency": "оставьте одну строку «Эффективность»",
    "old_date": "проверьте дату в первой строке",
    "future_date": "проверьте дату в первой строке",
    "overnight": "если работали после полуночи, ничего делать не нужно",
    "overlap": "проверьте время: интервалы не должны пересекаться",
    "empty_interval": "проверьте время: начало и конец совпадают",
    # расписание
    "no_header": "первой строкой нужен заголовок «Спринт 26.10 - 31.10»",
    "bad_sprint_dates": "заголовок пишите как «Спринт 26.10 - 31.10»",
    "no_days": "нужны строки с днями, например «Пн: 10:00 - 18:00»",
    "empty_day": "укажите время или «выходной»",
    "duplicate_day": "оставьте одну строку на день",
    "no_person": "второй строкой укажите ФИО, как «Иванов И.И.»",
    "long_sprint": "спринт — не длиннее недели",
}
"""Подсказка «как исправить» к коду проблемы. Нет подсказки — хватает текста проблемы."""

NOT_YOUR_FAULT = {
    "identity_not_linked",
    "employee_not_found",
    "person_not_found_used_sender",
    "late_change",
}
"""Решает админ (справочник, поздняя правка расписания): переписывать сообщение не нужно."""


def _quote(line: str) -> str:
    line = line.strip()
    return line if len(line) <= QUOTE_LEN else f"{line[: QUOTE_LEN - 1]}…"


def issue_text(issue: Issue) -> str:
    """Одна проблема для человека (HTML): где, что не так и как написать правильно."""
    what = issue.message[0].lower() + issue.message[1:]
    if issue.line and issue.line.strip():
        where = f"строка «{_quote(issue.line)}»"
        what = (
            f"{where} — не понял, что это" if issue.code == "unknown_line" else f"{where}: {what}"
        )
    hint = HOW_TO_FIX.get(issue.code)
    return escape(f"{what}. {hint[0].upper()}{hint[1:]}." if hint else f"{what}.")


def problems_text(issues: list[Issue], kind: MessageKind) -> str:
    """Список проблем сообщения для темы или лички (HTML, без ссылок)."""
    own = [i for i in issues if i.code not in NOT_YOUR_FAULT]
    admin = [i for i in issues if i.code in NOT_YOUR_FAULT]
    what = "дейлике" if kind is MessageKind.DAILY else "расписании"
    lines: list[str] = []
    if own:
        lines.append(f"Не всё понял в {what}:")
        lines += [f"• {issue_text(i)}" for i in own[:MAX_PROBLEMS]]
        if len(own) > MAX_PROBLEMS:
            lines.append(f"• и ещё {len(own) - MAX_PROBLEMS}")
    if admin:
        note = escape(admin[0].message)
        lines.append(f"{note} Сообщение сохранено, админ разберётся — переписывать не нужно.")
    return "\n".join(lines)


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

    # В тексте проблемы бывает имя из Telegram или строка из сообщения — escape внутри.
    body = problems_text(outcome.problems, outcome.kind) or "Нужна проверка."
    if any(i.code not in NOT_YOUR_FAULT for i in outcome.problems):
        link = fix_link(bot_username, outcome.parse_result_id)
        tail = f' Или <a href="{link}">исправить в боте</a>.' if link else ""
        body += f"\nОтредактируйте сообщение — я разберу заново.{tail}"
    return GroupFeedback(cfg.reaction_warn, body)
