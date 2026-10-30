"""Ответы бота: короткие блоки с заголовками, понятными показателями и HTML-разметкой."""

from __future__ import annotations

from datetime import date, datetime
from html import escape
from textwrap import wrap

from teamtime.calc import DayState
from teamtime.calc.duration import format_hm
from teamtime.schemas import (
    DayCellOut,
    EmployeeBrief,
    MonthSummaryOut,
    TodayOut,
    TodayRow,
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


def short_text(value: str, limit: int = 200) -> str:
    """Одна безопасная строка для заголовков и кратких подписей."""
    value = " ".join(value.split())
    return escape(value if len(value) <= limit else value[: limit - 1] + "…")


def human_date(day: date) -> str:
    return f"{WEEKDAYS[day.weekday()]}, {day.day} {MONTHS_GENITIVE[day.month - 1]}"


def span(start: int | None, end: int | None) -> str:
    return f"{format_hm(start)}–{format_hm(end)}"


def plan_text(cell: DayCellOut) -> str:
    if cell.status_label and cell.status != "remote":
        return short_text(cell.status_label)
    plan = cell.plan
    if plan is None:
        return "выходной" if cell.state is DayState.OFF else "расписание не указано"
    if plan.kind.value == "off":
        return "выходной"
    if plan.kind.value == "note":
        return f"«{short_text(plan.note or '')}»"
    return short_text("; ".join(span(start, end) for start, end in plan.intervals), 240)


def fact_text(cell: DayCellOut) -> str:
    fact = cell.fact
    if fact is None:
        if cell.status_label:
            return short_text(cell.status_label.lower())
        return {
            DayState.MISSING: "дейлик не прислан",
            DayState.PENDING: "дейлика пока нет",
            DayState.OFF: "выходной",
        }.get(cell.state, "—")
    intervals = "; ".join(span(start, end) for start, end in fact.intervals)
    return f"{intervals} · <b>{format_hm(fact.worked_sec)}</b>"


def _name(employee: EmployeeBrief) -> str:
    return short_text(employee.short_name, 100)


def _tasks(tasks: list[str]) -> list[str]:
    """Все задачи доступны в Telegram; длинные строки делим до экранирования HTML."""
    lines: list[str] = []
    for task in tasks:
        chunks = wrap(" ".join(task.split()), width=500, break_on_hyphens=False) or ["—"]
        lines.extend(
            f"{'• ' if index == 0 else '  '}{escape(chunk)}" for index, chunk in enumerate(chunks)
        )
    return lines


def format_today(report: TodayOut) -> str:
    groups: dict[str, list[str]] = {
        key: []
        for key in (
            "on_site",
            "remote",
            "expected_later",
            "left",
            "off",
            "absent",
            "no_plan",
        )
    }
    for row in report.rows:
        detail = plan_text(row.cell)
        if row.presence == "absent" and row.cell.status_note:
            detail += f" · {short_text(row.cell.status_note, 120)}"
        groups[row.presence].append(f"• <b>{_name(row.employee)}</b> — {detail}")
    lines = [
        f"👥 <b>Сегодня, {human_date(report.date)}</b>",
        f"Сейчас <code>{format_hm(report.now_sec)}</code> · в команде <b>{len(report.rows)}</b>",
    ]
    for key, title in (
        ("on_site", "🏢 В офисе"),
        ("remote", "💻 На удалёнке"),
        ("expected_later", "🕒 Начнут позже"),
        ("left", "🏁 Закончили по расписанию"),
        ("off", "🌿 Выходной"),
        ("absent", "🗓 Отсутствуют"),
        ("no_plan", "❔ Нет расписания"),
    ):
        if groups[key]:
            lines += ["", f"<b>{title} · {len(groups[key])}</b>", *groups[key]]
    if not report.rows:
        lines += ["", "Активных сотрудников пока нет."]
    lines += ["", "<i>Время и место работы — по расписанию. Отчёты доступны в итогах дня.</i>"]
    return "\n".join(lines)


def format_day_summary(report: TodayOut) -> str:
    waiting = [
        row
        for row in report.rows
        if row.cell.plan
        and row.cell.plan.kind.value == "work"
        and not row.cell.fact
        and row.presence not in {"absent", "off"}
    ]
    received = [row for row in report.rows if row.cell.fact]
    late = [row for row in received if row.cell.late_sec]
    lines = [
        f"📋 <b>Итоги дня · {human_date(report.date)} {report.date.year}</b>",
        "",
        f"Прислали дейлик: <b>{len(received)}</b>",
        f"Пока без дейлика: <b>{len(waiting)}</b>",
        f"Отработано командой: <b>{format_hm(report.worked_sec)}</b>",
        f"Опоздания по дейликам: <b>{len(late)}</b>",
    ]
    if waiting:
        lines += ["", "<b>⏳ Пока не прислали</b>"]
        lines += [
            f"• {_name(row.employee)} — расписание до {format_hm(row.cell.plan.end)}"
            for row in waiting
            if row.cell.plan
        ]
    if late:
        lines += [
            "",
            "<b>⚠️ Опоздания</b>",
            *(f"• {_name(row.employee)} — {format_hm(row.cell.late_sec)}" for row in late),
        ]
    if received:
        lines += ["", "<b>✅ Присланные дейлики</b>"]
        for row in received:
            fact = row.cell.fact
            assert fact
            efficiency = (
                f" · {fact.efficiency}%"
                if fact.efficiency is not None
                else " · эффективность не указана"
            )
            lines.append(
                f"• <b>{_name(row.employee)}</b> — {format_hm(fact.worked_sec)}{efficiency}"
            )
    return "\n".join(lines)


def format_day(report: TodayOut, today: date) -> str:
    """Прошлую и будущую дату показываем без текущего времени и присутствия «сейчас»."""
    if report.date == today:
        return format_today(report)
    lines = [
        f"👥 <b>День команды · {human_date(report.date)} {report.date.year}</b>",
        f"В команде: <b>{len(report.rows)}</b> · по расписанию работают: "
        f"<b>{report.counts.get('planned', 0)}</b>",
    ]
    for row in report.rows:
        lines += ["", f"<b>{_name(row.employee)}</b>", f"План: {plan_text(row.cell)}"]
        if report.date < today or row.cell.fact:
            lines.append(f"Факт: {fact_text(row.cell)}")
    if not report.rows:
        lines += ["", "Активных сотрудников пока нет."]
    if report.date > today:
        lines += ["", "<i>План на будущую дату. Рабочий день ещё не наступил.</i>"]
    return "\n".join(lines)


def format_employee_day(row: TodayRow, today: date) -> str:
    cell = row.cell
    lines = [
        f"👤 <b>{_name(row.employee)} · день</b>",
        f"{human_date(cell.date)} {cell.date.year}",
        "",
        f"План: <b>{plan_text(cell)}</b>",
    ]
    if cell.date <= today or cell.fact:
        lines.append(f"Факт: {fact_text(cell)}")
    else:
        lines.append("Рабочий день ещё не наступил.")
    if cell.fact:
        efficiency = cell.fact.efficiency
        lines.append(
            f"Эффективность: <b>{efficiency}%</b> · с её учётом "
            f"<b>{format_hm(cell.fact.result_sec)}</b>"
            if efficiency is not None
            else "Эффективность не указана."
        )
    for value, label in (
        (cell.late_sec, "Опоздание"),
        (cell.early_leave_sec, "Ранний уход"),
        (cell.undertime_sec, "Недоработка"),
    ):
        if value:
            lines.append(f"⚠️ {label}: <b>{format_hm(value)}</b>")
    if cell.status_note:
        lines += ["", f"Статус: {short_text(cell.status_note, 500)}"]
    if cell.plan and cell.plan.note:
        lines += ["", f"Заметка в расписании: {short_text(cell.plan.note, 500)}"]
    if row.tasks:
        lines += ["", "<b>🎯 Задачи из расписания на неделю</b>", *_tasks(row.tasks)]
    if cell.fact and cell.fact.tasks:
        lines += ["", "<b>✅ Выполнено за день</b>", *_tasks(cell.fact.tasks)]
    return "\n".join(lines)


def format_my_week(week: WeekOut, row: WeekRow) -> str:
    lines = [
        f"🗓 <b>{short_text(week.label)}</b>",
        f"{_name(row.employee)} · {week.days[0]:%d.%m.%Y}–{week.days[-1]:%d.%m.%Y}",
    ]
    for cell in row.cells:
        lines += [
            "",
            f"<b>{WEEKDAYS_CAP[cell.date.weekday()]} · {cell.date:%d.%m}</b>",
            f"План: {plan_text(cell)}",
        ]
        if cell.date <= week.today or cell.fact:
            lines.append(f"Факт: {fact_text(cell)}")
        if cell.fact and cell.fact.efficiency is not None:
            lines.append(
                f"Эффективность: <b>{cell.fact.efficiency}%</b> · "
                f"с её учётом {format_hm(cell.fact.result_sec)}"
            )
        marks = []
        if cell.late_sec:
            marks.append(f"опоздание {format_hm(cell.late_sec)}")
        if cell.early_leave_sec:
            marks.append(f"ранний уход {format_hm(cell.early_leave_sec)}")
        if cell.undertime_sec:
            marks.append(f"недоработка {format_hm(cell.undertime_sec)}")
        if marks:
            lines.append(f"⚠️ {', '.join(marks)}")
    totals = row.totals
    lines += [
        "",
        "<b>📊 За неделю</b>",
        f"Отработано: <b>{format_hm(totals.worked_sec)}</b> · "
        f"запланировано {format_hm(totals.planned_sec)}",
        f"С учётом эффективности: <b>{format_hm(totals.result_sec)}</b>",
        f"Опозданий: {totals.late_count}"
        + (f" · всего {format_hm(totals.late_sec)}" if totals.late_sec else ""),
    ]
    if row.plan and row.plan.tasks:
        lines += ["", "<b>🎯 Задачи из расписания</b>", *_tasks(row.plan.tasks)]
    return "\n".join(lines)


def format_who(week: WeekOut) -> str:
    lines = [
        f"👥 <b>{short_text(week.label)} · команда</b>",
        f"{week.days[0]:%d.%m}–{week.days[-1]:%d.%m}",
    ]
    for row in week.rows:
        totals = row.totals
        lines += [
            "",
            f"<b>{_name(row.employee)}</b>",
            f"Отработано <b>{format_hm(totals.worked_sec)}</b> · "
            f"план {format_hm(totals.planned_sec)}",
        ]
        if totals.late_count:
            lines.append(f"⚠️ Опозданий: {totals.late_count} · всего {format_hm(totals.late_sec)}")
        if totals.days_missing:
            lines.append(
                f"⏳ Без дейлика: {totals.days_missing} "
                f"{plural(totals.days_missing, 'день', 'дня', 'дней')}"
            )
    if not week.rows:
        lines += ["", "Активных сотрудников пока нет."]
    return "\n".join(lines)


def format_month(name: str, label: str, summary: MonthSummaryOut) -> str:
    progress = round(summary.norm_progress * 100)
    filled = max(0, min(10, round(summary.norm_progress * 10)))
    bar = "▰" * filled + "▱" * (10 - filled)
    lines = [
        f"📊 <b>{short_text(label)}</b>",
        short_text(name, 100),
        "",
        f"<b>Итого: {format_hm(summary.total_sec)} из {format_hm(summary.norm_sec)}</b>",
        f"{bar}  {progress}% нормы",
        "",
        "<b>⏱ Рабочее время</b>",
        f"По дейликам: <b>{format_hm(summary.worked_sec)}</b>",
        f"С учётом эффективности: <b>{format_hm(summary.result_sec)}</b>",
        "",
        "<b>⚠️ Опоздания и штраф</b>",
        f"Опозданий: {summary.late_count} · всего {format_hm(summary.late_total_sec)}",
        f"Штраф за месяц: <b>{format_hm(summary.penalty_sec)}</b>",
    ]
    if summary.overtime_sec:
        bonus = f"{summary.bonus:,.2f}".replace(",", " ").replace(".", ",")
        lines += [
            "",
            "<b>🎉 Сверх нормы</b>",
            f"Переработка: {format_hm(summary.overtime_sec)} · премия {bonus} ₽",
        ]
    if summary.days_missing:
        lines += [
            "",
            f"⏳ Без дейлика: {summary.days_missing} "
            f"{plural(summary.days_missing, 'день', 'дня', 'дней')}",
        ]
    lines += ["", "<i>Итого = время с учётом эффективности − штраф. Значения усечены до минут.</i>"]
    return "\n".join(lines)


def format_reminder(name: str, work_date: date, shift_end: datetime, delay_minutes: int) -> str:
    return "\n".join(
        [
            "⏰ <b>Не забудьте дейлик</b>",
            "",
            f"{short_text(name, 100)}, в таблице пока нет вашего дейлика "
            f"за <b>{work_date:%d.%m.%Y}</b>.",
            "",
            f"Смена по расписанию закончилась <b>{shift_end:%d.%m в %H:%M}</b>.",
            f"После её окончания прошло не меньше <b>{delay_minutes} "
            f"{plural(delay_minutes, 'минуты', 'минут', 'минут')}</b>.",
            "",
            "Пришлите дейлик в тему «Дейлики»: фактические интервалы работы, "
            "эффективность и выполненные задачи.",
            "Если уже отправили сообщение, проверьте в боте, удалось ли его разобрать: /fix.",
        ]
    )


HELP = (
    "⏱ <b>xTime · таблица команды</b>\n"
    "Расписание задаёт план, дейлик в конце дня — фактические часы и выполненные задачи.\n\n"
    "<b>👥 Рабочий день</b>\n"
    "/today — кто, где и во сколько работает сегодня\n"
    "/day — другой день: стрелки и календарь; можно /day 29.10.2026\n"
    "/absent — отсутствие, удалёнка, больничный или отпуск\n\n"
    "<b>📊 Мои отчёты</b>\n"
    "/week — расписание, часы и задачи на неделю\n"
    "/me — часы, норма и итоги месяца\n"
    "/who — итоги команды за неделю\n\n"
    "<b>👤 Сотрудники</b>\n"
    "/people — выбрать человека и посмотреть его день, неделю или месяц\n"
    "В отчётах можно менять дату и листать периоды стрелками.\n\n"
    "<b>✏️ Исправления</b>\n"
    "/fix — сообщения, в которых нужна ваша помощь\n"
    "Ошибку можно исправить прямо в исходном сообщении в теме — таблица обновится.\n\n"
    "Выбирайте действия кнопками под полем ввода."
)

STATUS_PROMPT = (
    "🗓 <b>Статус на сегодня</b>\n\n"
    "Выберите, где будете работать или почему отсутствуете. Статус появится в таблице.\n"
    "Для отпуска можно указать период."
)
