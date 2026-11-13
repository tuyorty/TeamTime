"""Месяц и профиль используют то же учётное время, что новый расчёт фонда."""

from datetime import date
from decimal import Decimal
from fractions import Fraction
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.calc.fund import START, FundCalculationError, next_month, split_interval
from teamtime.db.fund import FundMember, FundPeriod
from teamtime.schemas import MonthSummaryOut
from teamtime.services import fund_config, fund_report


async def adapt(
    session: AsyncSession, employee: int, month: date, summary: MonthSummaryOut
) -> MonthSummaryOut:
    if month < START or not (await fund_config.load(session)).module_active:
        return summary
    person = await session.get(FundMember, employee)
    if person is None:
        return summary
    out = summary.model_copy(
        update={"fund_model": True, "bonus": Decimal(0), "hourly_rate": Decimal(0)}
    )
    stored = await session.get(FundPeriod, month)
    saved = (
        next(
            (r for r in (stored.snapshot or {}).get("rows", []) if r["employee"]["id"] == employee),
            None,
        )
        if stored and stored.closed_at
        else None
    )
    if saved is not None:
        data = saved.get("inputs")
        norm, effective, penalty, total = (
            saved[k] for k in ("norm_sec", "effective_sec", "penalty_sec", "credited_sec")
        )
        wage = Decimal(saved["amounts"]["salary"])
        problems: list[dict[str, Any]] = []
    else:
        data, problems, _ = await fund_report.collect_inputs(session, month, person)
        try:
            if data is None:
                raise FundCalculationError("Не заданы условия или календарь")
            parts, wage = fund_report.calculate_inputs(data)
            norm, effective, penalty, total = (
                int(sum((Fraction(p[k]) for p in parts), Fraction(0)))
                for k in ("norm", "effective", "penalty", "credited")
            )
        except FundCalculationError as exc:
            return out.model_copy(
                update={
                    "calculation_ready": False,
                    "calculation_issues": [p["message"] for p in problems] + [str(exc)],
                    "norm_sec": 0,
                    "penalty_sec": 0,
                    "total_sec": 0,
                    "norm_progress": 0,
                    "overtime_sec": 0,
                }
            )
    contract = Fraction(0)
    raw_worked = 0
    late = 0
    working_days = summary.norm_working_days
    excluded_days = summary.norm_excluded_days
    if data:
        participating = {
            d
            for d, n in data["calendar"]["days"].items()
            if n and d >= data["joined_on"] and (not data["left_on"] or d <= data["left_on"])
        }
        working_days = len(participating)
        excluded_days = len(
            {d["day"] for d in data["decisions"] if d["kind"] in {"vacation", "sick"}}
            & participating
        )
        for condition in data["conditions"]:
            contract += Fraction(condition["share"]) * sum(
                n
                for d, n in data["calendar"]["days"].items()
                if condition["start"] <= d <= condition["end"]
                and d >= data["joined_on"]
                and (not data["left_on"] or d <= data["left_on"])
            )
        for work in data["work"]:
            for day, start, end in split_interval(
                date.fromisoformat(work["day"]), work["start"], work["end"]
            ):
                if (
                    month <= day < next_month(month)
                    and str(day) >= data["joined_on"]
                    and (not data["left_on"] or str(day) <= data["left_on"])
                ):
                    raw_worked += end - start
        late = max(
            0,
            sum(data["lateness"].values())
            + sum(d["seconds"] for d in data["decisions"] if d["kind"] == "missed")
            - sum(d["seconds"] for d in data["decisions"] if d["kind"] == "waiver"),
        )
    return out.model_copy(
        update={
            "worked_sec": raw_worked if data else out.worked_sec,
            "result_sec": effective,
            "penalty_sec": penalty,
            "late_total_sec": late,
            "total_sec": total,
            "norm_sec": norm,
            "norm_working_days": working_days,
            "norm_excluded_days": excluded_days,
            "contract_norm_sec": int(contract),
            "norm_reduction_sec": max(0, int(contract) - norm),
            "norm_progress": total / norm if norm else 0,
            "overtime_sec": max(0, total - norm),
            "fund_salary": wage,
            "calculation_issues": [p["message"] for p in problems],
        }
    )
