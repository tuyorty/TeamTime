"""Незавершённый модуль не рекламируется в обычном меню Telegram."""

from teamtime.bot.app import menu_commands
from teamtime.bot.keyboards import reply_menu
from teamtime.services import fund_config


def test_release_has_no_fund_commands_or_keyboard_button():
    assert not fund_config.FUND_AVAILABLE
    assert "fund" not in {command.command for command in menu_commands(fund_enabled=True)}
    assert not any(button.text == "💼 Финансы" for row in reply_menu().keyboard for button in row)


def test_development_command_requires_explicit_module_activation(monkeypatch):
    monkeypatch.setattr(fund_config, "FUND_AVAILABLE", True)
    assert "fund" not in {command.command for command in menu_commands()}
    assert "fund" in {command.command for command in menu_commands(fund_enabled=True)}
