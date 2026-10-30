"""Просмотр чужой статистики, истории дней и календаря через настоящий диспетчер."""

from __future__ import annotations

from datetime import date, datetime

import pytest
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import AnswerCallbackQuery, EditMessageText, SendMessage

from teamtime.bot.keyboards import CalendarCb, PeopleCb, ReportCb
from teamtime.core import clock
from teamtime.db.models import Employee
from teamtime.services import manual
from tests import factories as f
from tests.bot.fake_telegram import GROUP, STRANGERS, Telegram
from tests.bot.test_bot import tg as tg

pytestmark = pytest.mark.db


def response(tg: Telegram):
    return [call for call in tg.session.calls if isinstance(call, SendMessage | EditMessageText)][
        -1
    ]


def button(tg: Telegram, label: str) -> str:
    found = next(
        button
        for row in response(tg).reply_markup.inline_keyboard
        for button in row
        if button.text == label
    )
    assert found.callback_data
    return found.callback_data


async def daily(maker, employee_id: int, day: date = date(2026, 10, 25)) -> None:
    async with maker() as session:
        await manual.set_daily(
            session,
            employee_id=employee_id,
            work_date=day,
            intervals=[(9 * 3600, 17 * 3600)],
            efficiency=75,
            tasks=["Проверил тестовый стенд"],
            actor="test",
        )
        await session.commit()


async def test_choose_colleague_and_switch_between_day_week_and_month(tg: Telegram, maker) -> None:
    await daily(maker, 2)
    await tg.private(501, "/people")
    await tg.press(501, button(tg, "Петров П.П."))
    month = response(tg).text
    assert "Петров П.П." in month and "Иванов И.И." not in month
    assert "По дейликам: <b>8:00</b>" in month
    assert "С учётом эффективности: <b>6:00</b>" in month
    await tg.press(501, button(tg, "День"))
    await tg.press(501, button(tg, "‹ 25.10"))
    day = response(tg).text
    assert "Петров П.П." in day and "25 октября 2026" in day
    assert "9:00–17:00" in day and "75%" in day
    assert "Проверил тестовый стенд" in day
    await tg.press(501, button(tg, "Неделя"))
    assert "19.10.2026–25.10.2026" in response(tg).text
    assert "Отработано: <b>8:00</b>" in response(tg).text
    await tg.press(501, button(tg, "Месяц"))
    assert "Петров П.П." in response(tg).text
    assert len(tg.session.of(SendMessage)) == 1


async def test_yesterday_and_its_summary_keep_selected_day(tg: Telegram, maker) -> None:
    await daily(maker, 1)
    await tg.private(501, "/today")
    await tg.press(501, button(tg, "‹ 25.10"))
    text = response(tg).text
    assert "День команды" in text and "25 октября 2026" in text
    assert "Сегодня" not in text and "Сейчас" not in text
    assert "9:00–17:00" in text
    await tg.press(501, button(tg, "📋 Итоги дня"))
    assert "Итоги дня · вс, 25 октября 2026" in response(tg).text
    assert "Прислали дейлик: <b>1</b>" in response(tg).text
    assert "Отработано командой: <b>8:00</b>" in response(tg).text
    await tg.press(501, button(tg, "26.10 ›"))
    assert "Итоги дня · пн, 26 октября 2026" in response(tg).text
    assert "Прислали дейлик: <b>0</b>" in response(tg).text
    assert len(tg.session.of(SendMessage)) == 1


async def test_calendar_switches_month_and_opens_selected_date(tg: Telegram) -> None:
    await tg.private(501, "/day")
    await tg.press(501, button(tg, "📅 26.10.2026"))
    assert "Выберите дату" in response(tg).text
    calendar = response(tg)
    assert any(
        button.text == "[26]" for row in calendar.reply_markup.inline_keyboard for button in row
    )
    await tg.press(501, button(tg, "‹"))
    assert button(tg, "Сентябрь 2026")
    await tg.press(501, button(tg, "30"))
    assert "30 сентября 2026" in response(tg).text
    assert button(tg, "📅 30.09.2026")
    await tg.press(501, button(tg, "Сегодня"))
    assert "Сегодня, пн, 26 октября" in response(tg).text
    assert len(tg.session.of(SendMessage)) == 1


async def test_employee_calendar_keeps_employee_and_report_type(tg: Telegram, maker) -> None:
    await daily(maker, 2, date(2026, 9, 30))
    await tg.private(501, "/people")
    await tg.press(501, button(tg, "Петров П.П."))
    await tg.press(501, button(tg, "📅 26.10.2026"))
    await tg.press(501, button(tg, "‹"))
    selection = ReportCb.unpack(button(tg, "30"))
    assert selection.employee_id == 2 and selection.view == "month"
    await tg.press(501, selection.pack())
    text = response(tg).text
    assert "Сентябрь 2026" in text and "Петров П.П." in text
    assert "По дейликам: <b>8:00</b>" in text


@pytest.mark.parametrize("command", ["/day 25.10.2026", "/day 2026-10-25"])
async def test_day_command_accepts_explicit_date(tg: Telegram, command: str) -> None:
    await tg.private(501, command)
    assert "25 октября 2026" in response(tg).text


async def test_future_day_shows_plan_without_missing_daily(tg: Telegram) -> None:
    await tg.private(501, "/day 28.10.2026")
    text = response(tg).text
    assert "28 октября 2026" in text and "будущую дату" in text
    assert "Сейчас" not in text and "дейлик не прислан" not in text


async def test_navigation_uses_team_timezone(tg: Telegram) -> None:
    clock.freeze(datetime.fromisoformat("2026-10-26T20:30:00+00:00"))
    await tg.private(501, "/today")
    assert "Сегодня, вт, 27 октября" in response(tg).text
    previous = ReportCb.unpack(button(tg, "‹ 26.10"))
    assert previous.day == "20261026"


async def test_people_list_is_paginated_and_excludes_inactive(tg: Telegram, maker) -> None:
    async with maker() as session:
        for initial in "АБВГДЕЖЗИКЛ":
            await f.employee(session, f"Выдуманный {initial}.{initial}.")
        inactive = await f.employee(session, "Неактивный Н.Н.")
        inactive.is_active = False
        await session.commit()
    await tg.private(501, "👤 Сотрудники")
    first = response(tg)
    first_ids = {
        ReportCb.unpack(button.callback_data).employee_id
        for row in first.reply_markup.inline_keyboard
        for button in row
        if button.callback_data.startswith("rp:")
    } - {0}
    assert len(first_ids) == 10
    await tg.press(501, button(tg, "›"))
    second = response(tg)
    second_ids = {
        ReportCb.unpack(button.callback_data).employee_id
        for row in second.reply_markup.inline_keyboard
        for button in row
        if button.callback_data.startswith("rp:")
    } - {0}
    assert len(second_ids) == 3
    assert first_ids.isdisjoint(second_ids)
    assert "Неактивный" not in str(second.reply_markup)
    assert len(tg.session.of(SendMessage)) == 1


@pytest.mark.parametrize(
    "data",
    [
        ReportCb(view="month", day="20261026", employee_id=2).pack(),
        PeopleCb(day="20261026").pack(),
        CalendarCb(view="day", day="20261026", month="20261001").pack(),
    ],
)
async def test_unlinked_user_cannot_browse_team_data(tg: Telegram, data: str) -> None:
    await tg.press(999, data)
    assert tg.session.of(EditMessageText) == []
    assert tg.session.of(SendMessage) == []
    answer = tg.session.of(AnswerCallbackQuery)[-1]
    assert answer.show_alert and "только сотрудникам" in answer.text


@pytest.mark.parametrize("command", ["/people", "/day"])
async def test_unknown_group_cannot_request_reports(tg: Telegram, command: str) -> None:
    await tg.group(501, command, chat=STRANGERS)
    assert tg.session.of(SendMessage) == []
    await tg.press(501, ReportCb(view="day", day="20261025").pack(), chat=STRANGERS)
    assert tg.session.of(EditMessageText) == []


async def test_approved_group_can_browse_colleague(tg: Telegram) -> None:
    await tg.group(777, "/people")
    await tg.press(777, button(tg, "Петров П.П."), chat=GROUP)
    assert "Петров П.П." in response(tg).text
    assert response(tg).chat_id == GROUP.id


async def test_inactive_viewer_and_inactive_employee_are_rejected(tg: Telegram, maker) -> None:
    async with maker() as session:
        employee = await session.get(Employee, 2)
        employee.is_active = False
        await session.commit()
    await tg.press(501, ReportCb(view="month", day="20261026", employee_id=2).pack())
    assert "больше не активен" in tg.session.of(AnswerCallbackQuery)[-1].text
    async with maker() as session:
        employee = await session.get(Employee, 1)
        employee.is_active = False
        await session.commit()
    await tg.press(501, ReportCb(view="day", day="20261026").pack())
    assert "только сотрудникам" in tg.session.of(AnswerCallbackQuery)[-1].text
    assert tg.session.of(EditMessageText) == []


@pytest.mark.parametrize(
    "data",
    [
        ReportCb(view="day", day="20260230").pack(),
        ReportCb(view="day", day="99991231").pack(),
        ReportCb(view="unknown", day="20261026").pack(),
        ReportCb(view="month", day="20261026", employee_id=999).pack(),
        CalendarCb(view="day", day="20261026", month="bad-date").pack(),
        PeopleCb(day="20261026", view="unknown").pack(),
    ],
)
async def test_invalid_or_stale_buttons_show_alert(tg: Telegram, data: str) -> None:
    await tg.press(501, data)
    assert tg.session.of(AnswerCallbackQuery)[-1].show_alert
    assert tg.session.of(EditMessageText) == []


async def test_selecting_same_report_ignores_not_modified_error(tg: Telegram) -> None:
    tg.session.edit_failures.append(
        TelegramBadRequest(
            method=EditMessageText(chat_id=501, message_id=1, text="тест"),
            message="Bad Request: message is not modified",
        )
    )
    await tg.press(501, ReportCb(view="day", day="20261026").pack())
    assert len(tg.session.of(EditMessageText)) == 1


async def test_invalid_command_date_explains_how_to_choose_day(tg: Telegram) -> None:
    await tg.private(501, "/day 31.02.2026")
    assert "Не понял дату" in response(tg).text
    assert "/day 29.10.2026" in response(tg).text
