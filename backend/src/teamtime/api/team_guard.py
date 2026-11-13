"""После включения фонда рабочие данные доступны только подтверждённой команде."""

from collections.abc import Awaitable, Callable

from fastapi import Request
from starlette.responses import JSONResponse, Response

from teamtime.services import fund_config, team_auth
from teamtime.services.fund import FundError


async def guard(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    path = request.url.path
    public = ("/api/v1/team/", "/api/v1/auth/", "/api/v1/display/")
    if (
        not path.startswith("/api/")
        or request.method == "OPTIONS"
        or path.startswith(public)
        or path in {"/api/v1/health", "/api/v1/docs", "/api/v1/openapi.json"}
    ):
        return await call_next(request)
    async with request.app.state.sessionmaker() as session:
        config = await fund_config.load(session)
        if config.enabled:
            try:
                actor = await team_auth.authenticate(
                    session,
                    request.cookies.get(team_auth.COOKIE),
                    demo=request.app.state.settings.demo,
                )
                if (
                    path.startswith(
                        ("/api/v1/inbox", "/api/v1/messages", "/api/v1/audit", "/api/v1/identities")
                    )
                    and not actor.leader
                ):
                    raise FundError("Исходные сообщения и привязки доступны руководителю", 403)
                if (
                    path.startswith("/api/v1/admin/")
                    and not actor.leader
                    and not (
                        actor.technical
                        and (
                            (path.startswith("/api/v1/admin/system") and request.method == "GET")
                            or path == "/api/v1/admin/finance-module"
                        )
                    )
                ):
                    raise FundError("Для изменений рабочих данных нужен руководитель", 403)
            except FundError as exc:
                return JSONResponse({"detail": str(exc)}, status_code=exc.status)
    response = await call_next(request)
    if config.enabled or path.startswith("/api/v1/fund/"):
        response.headers["Cache-Control"] = "no-store"
    return response
