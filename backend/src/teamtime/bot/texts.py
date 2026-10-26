"""Тексты бота (HTML-разметка Telegram). Чистые функции от DTO отчётов — легко тестировать."""

from __future__ import annotations

from datetime import date
from html import escape

from teamtime.calc import DayState
from teamtime.calc.duration import format_hm
from teamtime.schemas import (
    DayCellOut,
    EmployeeBrief,
    MonthSummaryOut,
    TodayOut,
    WeekOut,
    WeekRow,
)
from teamtime.services.reports import MONTHS_GENITIVE

WEEKDAYS = ("пн", "вт", "ср", "чт", "пт", "сб", "вс")
WEEKDAYS_CAP = ("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")


def plural(n: int, one: str, few: str, many: str) -> str:
    """Русская плюрализация: 1 день, 2 дня, 5 дней."""
    n = abs(n)
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def human_date(d: date) -> str:
    return f"{WEEKDAYS[d.weekday()]}, {d.day} {MONTHS_GENITIVE[d.month - 1]}"


def span(a: int | None, b: int | None) -> str:
    return f"{format_hm(a)}–{format_hm(b)}"


def plan_text(cell: DayCellOut) -> str:
    p = cell.plan
    if p is None:
        return "без плана"
    if p.kind.value == "off":
        return "выходной"
    if p.kind.value == "note":
        return f"«{escape(p.note or '')}»"
    return span(p.start, p.end)


def fact_text(cell: DayCellOut) -> str:
    f = cell.fact
    if f is None:
        if cell.status_label:
            return cell.status_label.lower()
        return {
            DayState.MISSING: "нет дейлика",
            DayState.PENDING: "ждём дейлик",
            DayState.OFF: "выходной",
        }.get(cell.state, "—")
    spans = "; ".join(span(a, b) for a, b in f.intervals)
    parts = [spans, format_hm(f.worked_sec)]
    if f.efficiency is not None:
        parts.append(f"{f.efficiency}% → {format_hm(f.result_sec)}")
    return ", ".join(parts)


def _name(e: EmployeeBrief) -> str:
    return escape(e.short_name)


def format_today(t: TodayOut) -> str:
    lines = [f"<b>Сегодня, {human_date(t.date)}</b>, {format_hm(t.now_sec)}"]
    groups: dict[str, list[str]] = {
        "on_site": [],
        "expected_later": [],
        "left": [],
        "remote": [],
        "absent": [],
    }
    late: list[str] = []
    no_daily: list[str] = []
    no_plan: list[str] = []
    for r in t.rows:
        c = r.cell
        name = _name(r.employee)
        if r.presence == "absent":
            groups["absent"].append(f"{name} — {escape((c.status_label or '').lower())}")
        elif r.presence == "no_plan":
            no_plan.append(name)
        elif r.presence == "expected_later" and c.plan:
            groups["expected_later"].append(f"{name} — с {format_hm(c.plan.start)}")
        elif r.presence in groups and c.plan:
            groups[r.presence].append(f"{name} — {span(c.plan.start, c.plan.end)}")
        if c.late_sec:
            late.append(f"{name} +{format_hm(c.late_sec)}")
        if r.daily_overdue:
            no_daily.append(name)

    titles = {
        "on_site": "На месте по плану",
        "expected_later": "Придут позже",
        "left": "Уже ушли по плану",
        "remote": "На удалёнке",
        "absent": "Отсутствуют",
    }
    for key, title in titles.items():
        if groups[key]:
            lines += ["", f"<b>{title}</b> ({len(groups[key])})", *(f"• {x}" for x in groups[key])]
    if late:
        lines += ["", "<b>Опоздали</b> (по дейликам)", *(f"• {x}" for x in late)]
    if no_daily:
        lines += ["", "<b>Не прислали дейлик</b>", *(f"• {x}" for x in no_daily)]
    if no_plan:
        lines += ["", f"Без плана на сегодня: {', '.join(no_plan)}"]
    dailies = t.counts.get("dailies", 0)
    lines += ["", f"Дейликов за сегодня: {dailies}, часов: {format_hm(t.worked_sec)}"]
    return "\n".join(lines)


def format_my_week(week: WeekOut, row: WeekRow) -> str:
    lines = [f"<b>{week.label}</b>, {_name(row.employee)}", ""]
    for c in row.cells:
        if c.plan is None and c.fact is None and c.status is None:
            continue
        head = f"<b>{WEEKDAYS_CAP[c.date.weekday()]} {c.date:%d.%m}</b>"
        line = f"{head}  план {plan_text(c)}\n      факт {fact_text(c)}"
        marks = []
        if c.late_sec:
            marks.append(f"опоздание {format_hm(c.late_sec)}")
        if c.early_leave_sec:
            marks.append(f"ранний уход {format_hm(c.early_leave_sec)}")
        if c.undertime_sec:
            marks.append(f"недоработка {format_hm(c.undertime_sec)}")
        if marks:
            line += f"\n      ⚠ {', '.join(marks)}"
        lines.append(line)
    t = row.totals
    lines += [
        "",
        f"Часы: <b>{format_hm(t.worked_sec)}</b> из плана {format_hm(t.planned_sec)}",
        f"Итог (с e%): {format_hm(t.result_sec)}",
        f"Опозданий: {t.late_count}" + (f", всего {format_hm(t.late_sec)}" if t.late_sec else ""),
    ]
    if row.plan and row.plan.tasks:
        lines += ["", "<b>Задачи спринта</b>", *(f"• {escape(x)}" for x in row.plan.tasks)]
    return "\n".join(lines)


def format_who(week: WeekOut) -> str:
    lines = [f"<b>{week.label}</b>: команда", ""]
    for r in week.rows:
        t = r.totals
        bits = [f"{format_hm(t.worked_sec)} из {format_hm(t.planned_sec)}"]
        if t.late_count:
            bits.append(f"опозданий {t.late_count}")
        if t.days_missing:
            bits.append(
                f"{t.days_missing} {plural(t.days_missing, 'день', 'дня', 'дней')} без дейлика"
            )
        absent = sum(1 for c in r.cells if c.state is DayState.ABSENCE)
        if absent:
            bits.append(f"отсутствие {absent} {plural(absent, 'день', 'дня', 'дней')}")
        lines.append(f"• <b>{_name(r.employee)}</b>: {', '.join(bits)}")
    lines += ["", "Часы — сумма интервалов из дейликов, план — по расписанию."]
    return "\n".join(lines)


def format_month(name: str, label: str, s: MonthSummaryOut) -> str:
    progress = round(s.norm_progress * 100)
    lines = [
        f"<b>{escape(label)}</b>, {escape(name)}",
        "",
        f"Часы(+): <b>{format_hm(s.worked_sec)}</b>",
        f"Часы(e%): {format_hm(s.result_sec)}",
        f"Опоздания: {s.late_count} {plural(s.late_count, 'раз', 'раза', 'раз')}, "
        f"всего {format_hm(s.late_total_sec)}",
        f"Опоздания(−), штраф: {format_hm(s.penalty_sec)}",
        f"Итого: <b>{format_hm(s.total_sec)}</b> из нормы {format_hm(s.norm_sec)} ({progress}%)",
    ]
    if s.overtime_sec:
        bonus = f"{s.bonus:,.2f}".replace(",", " ").replace(".", ",")
        lines.append(f"Переработка: {format_hm(s.overtime_sec)}, премия {bonus} ₽")
    if s.days_missing:
        lines.append(
            f"Без дейлика: {s.days_missing} {plural(s.days_missing, 'день', 'дня', 'дней')}"
        )
    lines += ["", "<i>Значения усечены до минут.</i>"]
    return "\n".join(lines)


HELP = (
    "Я веду табель команды по сообщениям в темах «расписание» и «дейлики».\n\n"
    "<b>Команды</b>\n"
    "/today — кто сегодня на работе, кто опоздал, кто не прислал дейлик\n"
    "/week — моя неделя: план, факт, итог\n"
    "/who — общая картина по команде за неделю\n"
    "/me — моя статистика за месяц\n"
    "/absent — не приду сегодня, удалёнка, больничный, отпуск\n"
    "/fix — что я не смог разобрать в ваших сообщениях\n\n"
    "Если в сообщении ошибка, проще всего отредактировать его в теме: я разберу заново."
)
