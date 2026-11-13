"""Настройки фонда; незавершённый модуль закрыт отдельным флагом выпуска."""

from datetime import date

from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.db.models import AppSetting

KEY = "fund"
# До приёмки фонда включение доступно только в отдельной сборке для разработки и тестов.
FUND_AVAILABLE = False


class FundConfig(BaseModel):
    module_enabled: bool = False
    enabled: bool = False
    first_month: date = date(2026, 11, 1)
    notification_hour: int = Field(12, ge=0, le=23)
    notification_minute: int = Field(0, ge=0, le=59)
    reminders_enabled: bool = True
    technical_employee_ids: list[int] = Field(default_factory=list)

    @property
    def module_active(self) -> bool:
        return FUND_AVAILABLE and self.module_enabled


async def load(session: AsyncSession) -> FundConfig:
    row = await session.get(AppSetting, KEY, populate_existing=True)
    return FundConfig.model_validate(row.value if row else {})


async def require_module(session: AsyncSession) -> None:
    from teamtime.services.fund import FundError

    if not FUND_AVAILABLE:
        raise FundError("Модуль фонда находится в разработке и пока недоступен", 409)
    if not (await load(session)).module_active:
        raise FundError("Модуль фонда отключён администратором", 409)


async def save(session: AsyncSession, config: FundConfig) -> None:
    row = await session.get(AppSetting, KEY)
    if row is None:
        row = AppSetting(key=KEY, value=config.model_dump(mode="json"))
        session.add(row)
    else:
        row.value = config.model_dump(mode="json")
    await session.flush()
