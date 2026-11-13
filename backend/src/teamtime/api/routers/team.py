"""Вход, выход и режим телевизора. Финансовые роли выдаются отдельно от технического входа."""

from collections import deque
from contextlib import suppress
from dataclasses import asdict
from time import monotonic
from typing import Annotated, Any

from fastapi import APIRouter, Header, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from teamtime.api.deps import ConfigDep, SessionDep
from teamtime.api.fund_deps import LeaderDep
from teamtime.core import clock
from teamtime.db.fund_operations import TeamSession
from teamtime.db.models import Employee
from teamtime.services import fund_config, team_auth
from teamtime.services.fund import FundError

router = APIRouter(prefix="/team", tags=["именной вход"])
LOGIN_REQUEST_LIMIT = 5
LOGIN_REQUEST_WINDOW = 60


def limit_login_requests(request: Request) -> None:
    """Ограничить выдачу одноразовых кодов независимо от парольного входа админа."""
    state = request.app.state
    if not hasattr(state, "team_login_requests"):
        state.team_login_requests = {}
    requests: dict[str, deque[float]] = state.team_login_requests
    now = monotonic()
    for address, recent in list(requests.items()):
        while recent and now - recent[0] >= LOGIN_REQUEST_WINDOW:
            recent.popleft()
        if not recent:
            del requests[address]
    address = request.client.host if request.client else "?"
    recent = requests.setdefault(address, deque())
    if len(recent) >= LOGIN_REQUEST_LIMIT:
        raise HTTPException(
            429,
            "Слишком много запросов входа, подождите минуту",
            headers={"Retry-After": str(LOGIN_REQUEST_WINDOW)},
        )
    recent.append(now)


def csrf(header: str | None) -> None:
    if header != "teamtime":
        raise HTTPException(403, "Нет заголовка X-Requested-With")


class LoginPoll(BaseModel):
    code: str = Field(min_length=16, max_length=64)
    secret: str = Field(min_length=40, max_length=100)


def set_cookie(response: Response, request: Request, token: str, *, display: bool = False) -> None:
    response.set_cookie(
        team_auth.DISPLAY_COOKIE if display else team_auth.COOKIE,
        token,
        httponly=True,
        samesite="strict",
        secure=request.url.scheme == "https",
        max_age=365 * 86400 if display else 12 * 3600,
    )
    response.headers["Cache-Control"] = "no-store"


@router.get("/session")
async def session_info(
    request: Request, session: SessionDep, config: ConfigDep, response: Response
) -> dict[str, Any]:
    setup = await fund_config.load(session)
    actor = None
    with suppress(FundError):
        actor = asdict(
            await team_auth.authenticate(
                session, request.cookies.get(team_auth.COOKIE), demo=config.demo
            )
        )
    response.headers["Cache-Control"] = "no-store"
    return {
        "enabled": setup.enabled,
        "module_enabled": setup.module_active,
        "module_available": fund_config.FUND_AVAILABLE,
        "demo": config.demo,
        "actor": actor,
    }


@router.post("/login")
async def login(
    request: Request,
    session: SessionDep,
    x_requested_with: Annotated[str | None, Header()] = None,
) -> dict[str, str]:
    csrf(x_requested_with)
    setup = await fund_config.load(session)
    if not setup.enabled and not setup.module_active:
        raise HTTPException(409, "Именной вход не включён; используйте обычный режим xTime")
    limit_login_requests(request)
    return await team_auth.begin_login(session)


@router.post("/login/poll")
async def poll(
    body: LoginPoll,
    request: Request,
    response: Response,
    session: SessionDep,
    x_requested_with: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    csrf(x_requested_with)
    token, actor = await team_auth.finish_login(session, body.code, body.secret)
    if token:
        set_cookie(response, request, token)
    return {"ready": actor is not None, "actor": asdict(actor) if actor else None}


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    session: SessionDep,
    x_requested_with: Annotated[str | None, Header()] = None,
) -> dict[str, bool]:
    csrf(x_requested_with)
    token = request.cookies.get(team_auth.COOKIE)
    if token:
        row = await session.get(TeamSession, team_auth.token_hash(token))
        if row:
            row.revoked_at = clock.now()
    response.delete_cookie(team_auth.COOKIE)
    return {"ok": True}


@router.get("/demo-users")
async def demo_users(config: ConfigDep, session: SessionDep) -> list[dict[str, Any]]:
    if not config.demo:
        raise HTTPException(404)
    return [
        {"id": e.id, "name": e.full_name}
        for e in await session.scalars(
            select(Employee).where(Employee.is_active).order_by(Employee.id)
        )
    ]


class DemoLogin(BaseModel):
    employee_id: int = Field(gt=0)


@router.post("/demo-login")
async def demo_login(
    body: DemoLogin,
    config: ConfigDep,
    request: Request,
    response: Response,
    session: SessionDep,
    x_requested_with: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    csrf(x_requested_with)
    if not config.demo:
        raise HTTPException(404)
    actor = await team_auth.account(session, body.employee_id, None, demo=True)
    set_cookie(response, request, await team_auth.issue_session(session, actor.employee_id, None))
    return asdict(actor)


@router.post("/display-token")
async def display_token(actor: LeaderDep, session: SessionDep) -> dict[str, str]:
    token = await team_auth.issue_session(session, None, None, display=True)
    return {"token": token}


class DisplayToken(BaseModel):
    token: str = Field(min_length=40, max_length=100)


@router.post("/display-login")
async def display_login(
    body: DisplayToken,
    request: Request,
    response: Response,
    session: SessionDep,
    x_requested_with: Annotated[str | None, Header()] = None,
) -> dict[str, bool]:
    csrf(x_requested_with)
    if not await team_auth.display_access(session, body.token):
        raise HTTPException(401, "Ссылка для экрана недействительна")
    set_cookie(response, request, body.token, display=True)
    return {"ok": True}


@router.post("/revoke-sessions/{employee_id}")
async def revoke(employee_id: int, actor: LeaderDep, session: SessionDep) -> dict[str, bool]:
    for row in await session.scalars(
        select(TeamSession).where(TeamSession.employee_id == employee_id)
    ):
        row.revoked_at = clock.now()
    return {"ok": True}
