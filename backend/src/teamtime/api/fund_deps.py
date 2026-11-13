"""Именные права нового учёта: общий пароль админа не используется."""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request

from teamtime.api.deps import ConfigDep, SessionDep
from teamtime.services.fund import FundError, member
from teamtime.services.team_auth import COOKIE, Identity, authenticate


async def require_module(request: Request, session: SessionDep) -> None:
    from teamtime.services import fund, fund_config

    # Переключение режима и финансовые записи не обгоняют друг друга.
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        await fund.lock(session)
    await fund_config.require_module(session)


async def authenticated(request: Request, session: SessionDep, config: ConfigDep) -> Identity:
    try:
        return await authenticate(session, request.cookies.get(COOKIE), demo=config.demo)
    except FundError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


IdentityDep = Annotated[Identity, Depends(authenticated)]


async def participant(actor: IdentityDep, session: SessionDep) -> Identity:
    try:
        await member(session, actor.employee_id)
        return actor
    except FundError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


MemberDep = Annotated[Identity, Depends(participant)]


def write_access(
    actor: MemberDep, x_requested_with: Annotated[str | None, Header()] = None
) -> Identity:
    if x_requested_with != "teamtime":
        raise HTTPException(403, "Нет заголовка X-Requested-With")
    return actor


WriterDep = Annotated[Identity, Depends(write_access)]


def lead_access(actor: WriterDep) -> Identity:
    if not actor.leader:
        raise HTTPException(403, "Действие доступно только руководителю")
    return actor


LeaderDep = Annotated[Identity, Depends(lead_access)]
