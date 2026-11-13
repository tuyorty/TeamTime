"""Подтверждённый невыход не превращается в ожидание дейлика или вымышленный приход."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from teamtime.bot.handlers import personal
from teamtime.bot.reminders import _deadline
from teamtime.calc import DayRules, compute_day
from teamtime.services.facts import DayCell
from teamtime.services.reports import _presence
from teamtime.services.settings import AppSettings
from tests.calc.helpers import work

DAY = date(2026, 10, 26)


def test_confirmed_no_show_has_no_reminder_deadline_and_is_absent():
    result = compute_day(
        DAY,
        work("10:00-18:00"),
        None,
        None,
        DayRules(),
        DAY,
        confirmed_no_show_seconds=8 * 3600,
    )
    cell = DayCell(1, DAY, result, None, None, None, None)
    assert _deadline(cell, AppSettings()) is None
    assert _presence(cell, 19 * 3600) == "absent"


@pytest.mark.parametrize("confirmed", [True, False])
async def test_check_does_not_ask_confirmed_no_show_to_fill_daily(monkeypatch, confirmed):
    flags = ["no_show_confirmed"] if confirmed else []
    cell = SimpleNamespace(result=SimpleNamespace(flags=flags))
    monkeypatch.setattr(personal, "own_employee", AsyncMock(return_value=SimpleNamespace(id=1)))
    monkeypatch.setattr(personal, "report_text", AsyncMock(return_value="Итоги дня"))
    monkeypatch.setattr(personal, "today_local", lambda _: DAY)
    monkeypatch.setattr(personal, "load_cells", AsyncMock(return_value={(1, DAY): cell}))
    display = AsyncMock()
    monkeypatch.setattr(personal, "display_report", display)
    session = AsyncMock()
    session.scalar.return_value = None
    await personal.send_check(SimpleNamespace(), session, AppSettings(), SimpleNamespace(id=501))
    text = display.await_args.args[1]
    assert ("Заполнить дейлик: /daily" in text) is not confirmed
