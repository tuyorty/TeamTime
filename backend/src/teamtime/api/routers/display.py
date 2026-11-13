"""Ограниченный доступ телевизора: только план команды на текущий день."""

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from teamtime import __version__
from teamtime.api.deps import AppSettingsDep, ConfigDep, SessionDep
from teamtime.core import clock
from teamtime.services import fund_config, reports, team_auth
from teamtime.services.facts import today_local
from teamtime.services.fund import FundError

router = APIRouter(prefix="/display", tags=["экран офиса"])


async def access(request: Request, session: SessionDep, config: ConfigDep) -> None:
    if not (await fund_config.load(session)).enabled:
        return
    if await team_auth.display_access(session, request.cookies.get(team_auth.DISPLAY_COOKIE)):
        return
    try:
        await team_auth.authenticate(
            session, request.cookies.get(team_auth.COOKIE), demo=config.demo
        )
    except FundError as exc:
        raise HTTPException(401, "Нужна отдельная ссылка доступа для телевизора") from exc


@router.get("/meta")
async def meta(
    request: Request, session: SessionDep, config: ConfigDep, settings: AppSettingsDep
) -> dict[str, Any]:
    await access(request, session, config)
    return {
        "version": __version__,
        "demo": config.demo,
        "admin_enabled": False,
        "is_admin": False,
        "timezone": settings.timezone,
        "today": today_local(settings),
        "now": clock.now(),
        "bot_username": None,
        "late_tolerance_min": settings.late_tolerance_min,
        "weekly_off": settings.weekly_off,
    }


@router.get("/today")
async def today(
    request: Request, session: SessionDep, config: ConfigDep, settings: AppSettingsDep
) -> dict[str, Any]:
    await access(request, session, config)
    result = (await reports.today_report(session, settings)).model_dump(mode="json")
    # TodayOut хранит краткого сотрудника; удаляем ленту исходных сообщений и результаты дня.
    result["feed"] = []
    result["week_pulse"] = []
    result["worked_sec"] = 0
    for row in result.get("rows", []):
        row["employee"] = {
            k: v
            for k, v in row["employee"].items()
            if k
            in {
                "id",
                "full_name",
                "short_name",
                "department",
                "avatar_url",
                "position",
                "color",
            }
        }
        row["daily_overdue"] = False
        row["tasks"] = []
        cell = row["cell"]
        row["cell"] = {
            k: v
            for k, v in cell.items()
            if k
            in {
                "date",
                "plan",
                "status",
                "status_note",
                "day_off",
            }
        }
        row["cell"]["status_note"] = ""
    return result
