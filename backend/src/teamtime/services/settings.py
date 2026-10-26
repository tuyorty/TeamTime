"""Бизнес-настройки: допуски, шкала штрафа, часовой пояс, рабочая неделя, праздники, бот.

Хранятся одной JSON-записью в ``app_settings`` и меняются в админке. Отсутствующие поля
берутся из значений по умолчанию, поэтому новые настройки не требуют миграций.
"""

from __future__ import annotations

from datetime import date
from fractions import Fraction
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.calc import DayRules, PenaltyScale
from teamtime.core.config import get_settings
from teamtime.db.models import AppSetting

SETTINGS_KEY = "app"


def _fraction(value: str) -> Fraction:
    return Fraction(value.replace(",", ".").strip())


class PenaltySettings(BaseModel):
    """Параметры шкалы штрафа. Дроби строками, чтобы 3/14 хранилось точно."""

    soft_limit_h: str = Field("5", description="Первый порог, часы")
    hard_limit_h: str = Field("12", description="Второй порог, часы")
    quad_coef: str = Field("3/14", description="Коэффициент квадратичной части")
    hard_value_h: str = Field("22.5", description="Штраф на втором пороге, часы")
    tail_slope: str = Field("4", description="Наклон после второго порога")

    @field_validator("*")
    @classmethod
    def _check_number(cls, v: str) -> str:
        try:
            _fraction(v)
        except (ValueError, ZeroDivisionError) as exc:
            raise ValueError(f"не число: {v!r}") from exc
        return v

    def scale(self) -> PenaltyScale:
        return PenaltyScale(
            soft_limit_h=_fraction(self.soft_limit_h),
            hard_limit_h=_fraction(self.hard_limit_h),
            quad_coef=_fraction(self.quad_coef),
            hard_value_h=_fraction(self.hard_value_h),
            tail_slope=_fraction(self.tail_slope),
        )


# Bot API разрешает только эти эмодзи в ReactionTypeEmoji (сверено с документацией 2026-10-26).
ALLOWED_REACTIONS = frozenset(
    "❤ 👍 👎 🔥 🥰 👏 😁 🤔 🤯 😱 🤬 😢 🎉 🤩 🤮 💩 🙏 👌 🕊 🤡 🥱 🥴 😍 🐳 ❤‍🔥 🌚 🌭 💯 🤣 ⚡ 🍌 "  # noqa: SIM905 — строкой проще сверять со списком в документации
    "🏆 💔 🤨 😐 🍓 🍾 💋 🖕 😈 😴 😭 🤓 👻 👨‍💻 👀 🎃 🙈 😇 😨 🤝 ✍ 🤗 🫡 🎅 🎄 ☃ 💅 🤪 🗿 🆒 💘 "
    "🙉 🦄 😘 💊 🙊 😎 👾 🤷‍♂ 🤷 🤷‍♀ 😡".split()
)


class BotSettings(BaseModel):
    feedback: Literal["reaction", "reply"] = Field(
        "reaction", description="Как отмечать разобранные сообщения в теме"
    )
    reaction_ok: str = "👌"
    reaction_warn: str = "🤔"
    reaction_edit: str = "✍"
    reminders_enabled: bool = False
    reminder_hour: int = Field(21, ge=0, le=23, description="Во сколько напоминать о дейлике")

    @field_validator("reaction_ok", "reaction_warn", "reaction_edit")
    @classmethod
    def _check_reaction(cls, v: str) -> str:
        if v not in ALLOWED_REACTIONS:
            raise ValueError(f"Telegram не разрешает реакцию {v!r}: выберите из списка Bot API")
        return v


class AppSettings(BaseModel):
    timezone: str = Field(default_factory=lambda: get_settings().default_timezone)
    late_tolerance_min: int = Field(0, ge=0, le=180, description="Допуск опоздания, минуты")
    early_tolerance_min: int = Field(0, ge=0, le=180)
    undertime_tolerance_min: int = Field(0, ge=0, le=600)
    weekly_off: list[int] = Field(default_factory=lambda: [6], description="0 — пн, 6 — вс")
    holidays: list[date] = Field(default_factory=list)
    default_norm_hours: int = Field(160, ge=0, le=400)
    penalty: PenaltySettings = Field(default_factory=PenaltySettings)
    bot: BotSettings = Field(default_factory=BotSettings)

    @field_validator("timezone")
    @classmethod
    def _check_tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"неизвестный часовой пояс {v!r}") from exc
        return v

    @field_validator("weekly_off")
    @classmethod
    def _check_weekdays(cls, v: list[int]) -> list[int]:
        if any(not 0 <= d <= 6 for d in v):
            raise ValueError("дни недели — числа от 0 до 6")
        return sorted(set(v))

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def day_rules(self) -> DayRules:
        return DayRules(
            late_tolerance=self.late_tolerance_min * 60,
            early_tolerance=self.early_tolerance_min * 60,
            undertime_tolerance=self.undertime_tolerance_min * 60,
            weekly_off=frozenset(self.weekly_off),
            holidays=frozenset(self.holidays),
        )


async def load_settings(session: AsyncSession) -> AppSettings:
    row = await session.get(AppSetting, SETTINGS_KEY)
    return AppSettings.model_validate(row.value) if row else AppSettings()


async def save_settings(session: AsyncSession, value: AppSettings) -> None:
    row = await session.get(AppSetting, SETTINGS_KEY)
    payload = value.model_dump(mode="json")
    if row is None:
        session.add(AppSetting(key=SETTINGS_KEY, value=payload))
    else:
        row.value = payload
