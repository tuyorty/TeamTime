"""Экспорт недели и месяца в CSV и XLSX."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Path
from fastapi.responses import Response

from teamtime.api.deps import AppSettingsDep, SessionDep
from teamtime.services import export, reports
from teamtime.services.facts import date_range, load_cells

router = APIRouter(prefix="/export", tags=["экспорт"])

Fmt = Literal["csv", "xlsx"]
MEDIA = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def _file(content: bytes, fmt: str, filename: str) -> Response:
    return Response(
        content,
        media_type=MEDIA[fmt],
        headers={"Content-Disposition": f'attachment; filename="{filename}.{fmt}"'},
    )


@router.get("/weeks/{iso_year}/{iso_week}.{fmt}", summary="Неделя в CSV или XLSX")
async def week(
    session: SessionDep,
    settings: AppSettingsDep,
    iso_year: int,
    iso_week: Annotated[int, Path(ge=1, le=53)],
    fmt: Fmt,
) -> Response:
    data = await reports.week_report(session, settings, iso_year, iso_week)
    name = f"teamtime-{iso_year}-w{iso_week:02d}"
    if fmt == "csv":
        return _file(export.to_csv(export.DAY_HEADER, export.week_day_rows(data)), fmt, name)
    grid_header, grid_rows = export.week_grid_rows(data)
    return _file(
        export.to_xlsx([
            (data.label, grid_header, grid_rows),
            ("Дни", export.DAY_HEADER, export.week_day_rows(data)),
        ]),
        fmt,
        name,
    )  # fmt: skip


@router.get("/months/{year}/{month}.{fmt}", summary="Месяц в CSV или XLSX")
async def month(
    session: SessionDep,
    settings: AppSettingsDep,
    year: Annotated[int, Path(ge=2000, le=2100)],
    month: Annotated[int, Path(ge=1, le=12)],
    fmt: Fmt,
) -> Response:
    data = await reports.month_report(session, settings, year, month, history=1)
    name = f"teamtime-{year}-{month:02d}"
    summary_header, summary_rows = export.month_summary_rows(data)
    if fmt == "csv":
        return _file(export.to_csv(summary_header, summary_rows), fmt, name)
    late_header, late_rows = export.month_late_rows(data)
    first, last = reports.month_bounds(year, month)
    cells = await load_cells(session, settings, first, last, [r.employee.id for r in data.rows])
    days = [
        row
        for r in data.rows
        for row in export.day_rows(
            r.employee.short_name,
            r.employee.position,
            [reports.cell_out(cells[(r.employee.id, d)]) for d in date_range(first, last)],
        )
    ]
    return _file(
        export.to_xlsx([
            ("Итог за месяц", summary_header, summary_rows),
            ("Опоздания", late_header, late_rows),
            ("Дни", export.DAY_HEADER, days),
        ]),
        fmt,
        name,
    )  # fmt: skip
