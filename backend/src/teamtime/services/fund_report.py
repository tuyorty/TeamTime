"""Один расчёт для экрана, бота, экспорта и закрытого снимка фонда."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
from decimal import Decimal
from fractions import Fraction
from typing import Any, cast

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.calc.fund import (
    RULESET,
    ZERO,
    FundCalculationError,
    month_start,
    next_month,
    salary,
    settlement,
)
from teamtime.calc.fund_time import Calendar, Conditions, Decision, Work, segments
from teamtime.core import clock
from teamtime.db.fund import (
    FundCalendar,
    FundMember,
    FundPeriod,
    FundReceipt,
    FundSourceState,
    FundTerms,
)
from teamtime.db.fund_operations import (
    FundAdjustment,
    FundClaim,
    FundObligation,
    FundOpening,
    FundTimeRequest,
)
from teamtime.db.models import Employee, ParseResultRow, Resolution
from teamtime.services import facts, fund_config, history
from teamtime.services.fund import FundError, lock, member, period, source_total, valid_month
from teamtime.services.fund_ledger import (
    audit,
    balance,
    digest,
    internal_operation,
    obligation_paid,
)
from teamtime.services.fund_requests import evidence, raw_late
from teamtime.services.settings import PenaltySettings, load_settings


def calculate_inputs(data: dict[str, Any]) -> tuple[list[dict[str, Any]], Decimal]:
    """Воспроизводимый расчёт из снимка: только учётные поля, без ORM и текущих настроек."""
    try:
        cal = data["calendar"]
        calendar = Calendar(
            date.fromisoformat(cal["month"]),
            str(cal["version"]),
            cal["source"],
            {date.fromisoformat(d): n for d, n in cal["days"].items()},
            frozenset(date.fromisoformat(d) for d in cal["holidays"]),
        )
        conditions = [
            Conditions(
                c["key"],
                date.fromisoformat(c["start"]),
                date.fromisoformat(c["end"]),
                Decimal(c["target"]),
                Decimal(c["share"]),
            )
            for c in data["conditions"]
        ]
        work = [
            Work(date.fromisoformat(w["day"]), int(w["start"]), int(w["end"]), int(w["efficiency"]))
            for w in data["work"]
        ]
        decisions = [
            Decision(date.fromisoformat(d["day"]), d["kind"], int(d["seconds"]))
            for d in data["decisions"]
        ]
        inputs = segments(
            calendar,
            conditions,
            work,
            {date.fromisoformat(d): n for d, n in data["lateness"].items()},
            decisions,
            date.fromisoformat(data["joined_on"]),
            date.fromisoformat(data["left_on"]) if data["left_on"] else None,
        )
        output, amount = salary(inputs, PenaltySettings.model_validate(data["penalty"]).scale())
    except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
        if isinstance(exc, FundCalculationError):
            raise
        raise FundCalculationError("Неполные или неверные данные расчёта") from exc
    return [
        {k: str(v) if isinstance(v, Decimal | Fraction) else v for k, v in asdict(r).items()}
        for r in output
    ], amount


async def collect_inputs(
    session: AsyncSession, month: date, person: FundMember
) -> tuple[dict[str, Any] | None, list[dict[str, str]], list[str]]:
    settings = await history.settings_at(session, await load_settings(session), month)
    end = next_month(month) - timedelta(days=1)
    today = clock.now().astimezone(settings.tz).date()
    blockers: list[dict[str, str]] = []

    def problem(code: str, message: str, day: date | None = None) -> None:
        blockers.append({"code": code, "message": message, "day": str(day) if day else ""})

    calendar = await session.scalar(
        select(FundCalendar)
        .where(FundCalendar.month == month)
        .order_by(FundCalendar.version.desc())
        .limit(1)
    )
    if calendar is None:
        problem("calendar_missing", "Не утверждён производственный календарь")
    versions = list(
        await session.scalars(
            select(FundTerms)
            .where(FundTerms.employee_id == person.employee_id, FundTerms.effective_from <= end)
            .order_by(FundTerms.effective_from, FundTerms.revision)
        )
    )
    chosen = {r.effective_from: r for r in versions}
    rows = list(chosen.values())
    conditions = []
    sources: set[str] = set()
    term_refs = []
    for i, row in enumerate(rows):
        until = rows[i + 1].effective_from - timedelta(days=1) if i + 1 < len(rows) else end
        if until < month or until < person.joined_on:
            continue
        conditions.append(
            {
                "key": str(row.id),
                "start": str(row.effective_from),
                "end": str(until),
                "target": str(row.target),
                "share": str(row.share),
            }
        )
        sources.update(row.sources)
        term_refs.append(
            {"id": row.id, "revision": row.revision, "no_other_income": row.no_other_income}
        )
    if not conditions:
        problem("terms_missing", "Не заданы условия оплаты")
    if calendar is None or not conditions:
        return None, blockers, sorted(sources)
    cells = await facts.load_cells(
        session, settings, month - timedelta(days=1), end, [person.employee_id]
    )
    requests = list(
        await session.scalars(
            select(FundTimeRequest).where(
                FundTimeRequest.employee_id == person.employee_id,
                FundTimeRequest.state == "approved",
            )
        )
    )
    statuses: dict[date, list[FundTimeRequest]] = {}
    decisions = []
    for request in requests:
        for d in map(date.fromisoformat, request.days):
            if month <= d <= end:
                statuses.setdefault(d, []).append(request)
                if request.kind in {"waiver", "missed"} and request.evidence.get(
                    str(d)
                ) != evidence(cells[person.employee_id, d]):
                    problem(
                        "decision_stale",
                        "После согласования изменились план или дейлик; перепроверьте решение",
                        d,
                    )
                if request.kind != "no_work":
                    decisions.append(
                        {"day": str(d), "kind": request.kind, "seconds": request.seconds}
                    )
    work, proof = [], []
    late: dict[str, int] = {}
    for (_, d), cell in cells.items():
        proof.append(
            {"day": str(d), **evidence(cell), "status_id": cell.status.id if cell.status else None}
        )
        daily = cell.daily
        if daily:
            if daily.efficiency is None and any(
                getattr(i, "efficiency", None) is None for i in daily.intervals
            ):
                problem("efficiency_missing", "В дейлике не указана эффективность", d)
            else:
                for interval in daily.intervals:
                    efficiency = getattr(interval, "efficiency", None)
                    work.append(
                        {
                            "day": str(d),
                            "start": interval.start_sec,
                            "end": interval.end_sec,
                            "efficiency": efficiency
                            if efficiency is not None
                            else daily.efficiency,
                        }
                    )
            if daily.parse_result_id:
                parse = await session.get(ParseResultRow, daily.parse_result_id)
                if parse and parse.resolution == Resolution.PENDING:
                    problem("daily_pending", "Дейлик ожидает решения в инбоксе", d)
        if not month <= d <= end or d < person.joined_on or (person.left_on and d > person.left_on):
            continue
        state = statuses.get(d, [])
        if cell.late_edit:
            problem("plan_pending", "Изменение расписания ещё не согласовано", d)
        if (
            cell.result.status
            and cell.result.status.value in {"vacation", "sick", "business_trip"}
            and not state
        ):
            problem("status_unconfirmed", "Отсутствие требует именного согласования в фонде", d)
        if d < today and not daily and not state:
            if cell.plan_day and facts.plan_input(cell.plan_day).has_time:
                problem(
                    "daily_missing",
                    "Нет дейлика по запланированной смене; пропуск не подтверждён",
                    d,
                )
            elif (not cell.plan_day or cell.plan_day.kind.value == "note") and calendar.days.get(
                str(d), 0
            ):
                problem("day_unconfirmed", "Нет подтверждённого плана или статуса дня", d)
        if daily and not any(r.kind in {"vacation", "sick", "trip", "no_work"} for r in state):
            late[str(d)] = raw_late(cell, settings.late_tolerance_min * 60)
        if daily and any(r.kind == "no_work" for r in state):
            problem("status_conflict", "Подтверждение дня без работы противоречит дейлику", d)
    data = {
        "calendar": {
            "id": calendar.id,
            "month": str(month),
            "version": calendar.version,
            "source": calendar.source,
            "source_version": calendar.source_version,
            "days": calendar.days,
            "holidays": calendar.holidays,
        },
        "conditions": conditions,
        "term_refs": term_refs,
        "work": work,
        "lateness": late,
        "decisions": decisions,
        "joined_on": str(person.joined_on),
        "left_on": str(person.left_on) if person.left_on else None,
        "penalty": settings.penalty.model_dump(mode="json"),
        "proof": proof,
    }
    return data, blockers, sorted(sources)


async def report(
    session: AsyncSession, actor: int, month: date, *, live: bool = False
) -> dict[str, Any]:
    await member(session, actor)
    stored = await session.get(FundPeriod, month, populate_existing=True)
    if stored and stored.closed_at and not live:
        result = dict(cast(dict[str, Any], stored.snapshot))
        result["closed"] = True
        result["closed_at"] = stored.closed_at.isoformat()
        result["rows"] = [dict(row) for row in result["rows"]]
        for row in result["rows"]:
            await payment_status(session, row, month, closed=True)
        return result
    valid_month(month)
    config = await fund_config.load(session)
    end = next_month(month) - timedelta(days=1)
    members = list(
        await session.scalars(
            select(FundMember)
            .where(
                FundMember.joined_on <= end,
                (FundMember.left_on.is_(None) | (FundMember.left_on >= month)),
            )
            .order_by(FundMember.employee_id)
        )
    )
    rows = []
    global_blockers = []
    today = clock.now().astimezone((await load_settings(session)).tz).date()
    if today <= end:
        global_blockers.append({"code": "month_running", "message": "Месяц ещё не закончился"})
    previous = month - timedelta(days=1)
    if month > config.first_month:
        before = await session.get(FundPeriod, month_start(previous))
        if before is None or before.closed_at is None:
            global_blockers.append(
                {"code": "previous_open", "message": "Сначала закройте предыдущий месяц"}
            )
    if not members:
        global_blockers.append(
            {"code": "members_missing", "message": "Не настроены участники фонда"}
        )
    for person in members:
        employee = await session.get(Employee, person.employee_id)
        assert employee is not None
        data, blockers, source_names = await collect_inputs(session, month, person)
        parts: list[dict[str, Any]] = []
        wage = None
        if data:
            try:
                parts, wage = calculate_inputs(data)
            except FundCalculationError as exc:
                blockers.append({"code": exc.code, "message": str(exc), "day": ""})
        receipts = list(
            await session.scalars(
                select(FundReceipt)
                .where(
                    FundReceipt.employee_id == person.employee_id,
                    FundReceipt.applied_month == month,
                )
                .order_by(FundReceipt.received_on, FundReceipt.id)
            )
        )
        source_names = sorted(set(source_names) | {r.source for r in receipts})
        corrected_sources = await session.scalars(
            select(FundAdjustment.after["source"].as_string()).where(
                FundAdjustment.employee_id == person.employee_id,
                FundAdjustment.applied_month == month,
                FundAdjustment.kind == "source",
                FundAdjustment.state == "approved",
            )
        )
        source_names = sorted(set(source_names) | {s for s in corrected_sources if s})
        sources = []
        for source in source_names:
            state = await session.get(FundSourceState, (person.employee_id, month, source))
            amount = await source_total(session, person.employee_id, month, source)
            complete = bool(state and state.complete and state.confirmed_total == amount)
            sources.append(
                {
                    "name": source,
                    "amount": str(amount),
                    "state": "complete"
                    if complete
                    else "partial"
                    if state or amount
                    else "unknown",
                    "version": state.version if state else 0,
                }
            )
            if not complete:
                blockers.append(
                    {
                        "code": "source_incomplete",
                        "message": f"{source}: полнота поступлений не подтверждена",
                        "day": "",
                    }
                )
        opening = await session.get(FundOpening, person.employee_id)
        pending_claims = await session.scalars(
            select(FundClaim).where(
                FundClaim.employee_id == person.employee_id,
                FundClaim.month == month,
                FundClaim.state == "pending",
            )
        )
        for claim in pending_claims:
            blockers.append(
                {
                    "code": "claim_pending",
                    "message": f"Компенсация #{claim.id} ожидает решения",
                    "day": "",
                }
            )
        pending_time = await session.scalars(
            select(FundTimeRequest).where(
                FundTimeRequest.employee_id == person.employee_id,
                FundTimeRequest.state == "pending",
            )
        )
        for request in pending_time:
            if any(d.startswith(month.isoformat()[:7]) for d in request.days):
                blockers.append(
                    {
                        "code": "time_pending",
                        "message": f"Запрос по времени #{request.id} ожидает решения",
                        "day": "",
                    }
                )
        if opening is None or opening.month > month:
            blockers.append(
                {
                    "code": "opening_missing",
                    "message": "Не подтверждён начальный остаток переплаты, включая ноль",
                    "day": "",
                }
            )
        overpayment = await balance(session, "overpayment", person.employee_id, end)
        adjustments = list(
            await session.scalars(
                select(FundAdjustment).where(
                    FundAdjustment.employee_id == person.employee_id,
                    FundAdjustment.applied_month == month,
                )
            )
        )
        for adjustment in adjustments:
            if adjustment.state == "pending":
                blockers.append(
                    {
                        "code": "adjustment_pending",
                        "message": f"Корректировка #{adjustment.id} ожидает решения",
                        "day": "",
                    }
                )
        bonuses = sum(
            (a.amount for a in adjustments if a.kind == "bonus" and a.state == "approved"), ZERO
        )
        correction = sum(
            (a.amount for a in adjustments if a.kind == "salary" and a.state == "approved"), ZERO
        )
        source_correction = sum(
            (a.amount for a in adjustments if a.kind == "source" and a.state == "approved"), ZERO
        )
        received = sum((r.amount for r in receipts), ZERO) + source_correction
        comp = sum(
            (
                o.amount
                for o in await session.scalars(
                    select(FundObligation).where(
                        FundObligation.employee_id == person.employee_id,
                        FundObligation.month == month,
                        FundObligation.kind == "compensation",
                    )
                )
            ),
            ZERO,
        )
        amounts = None
        if wage is not None:
            amounts = {
                k: str(v)
                for k, v in asdict(
                    settlement(
                        salary_amount=wage,
                        received=received,
                        overpayment=overpayment,
                        bonus=bonuses,
                        correction=correction,
                        compensation=comp,
                    )
                ).items()
            }
        norm = sum((Fraction(p["norm"]) for p in parts), Fraction(0))
        effective = sum((Fraction(p["effective"]) for p in parts), Fraction(0))
        penalty = sum((Fraction(p["penalty"]) for p in parts), Fraction(0))
        credited = sum((Fraction(p["credited"]) for p in parts), Fraction(0))
        row = {
            "employee": {
                "id": employee.id,
                "name": employee.full_name,
                "short_name": employee.short_name,
                "department": employee.department,
                "avatar_url": employee.avatar_url,
            },
            "no_other_income": any(t["no_other_income"] for t in data["term_refs"])
            if data
            else False,
            "norm_sec": int(norm),
            "effective_sec": int(effective),
            "penalty_sec": int(penalty),
            "credited_sec": int(credited),
            "parts": parts,
            "amounts": amounts,
            "sources": sources,
            "receipts": [
                {
                    "id": r.id,
                    "source": r.source,
                    "origin_month": str(r.origin_month),
                    "received_on": str(r.received_on),
                    "amount": str(r.amount),
                }
                for r in receipts
            ],
            "blockers": blockers,
            "inputs": data,
            "input_digest": digest(data),
            "adjustment_ids": [a.id for a in adjustments if a.state == "approved"],
        }
        await payment_status(session, row, month)
        rows.append(row)
    base = {
        "month": str(month),
        "ruleset": RULESET,
        "closed": False,
        "closed_at": None,
        "rows": rows,
        "blockers": global_blockers,
        "can_close": not global_blockers and all(not r["blockers"] for r in rows),
    }
    base["fingerprint"] = digest(base)
    return base


async def payment_status(
    session: AsyncSession, row: dict[str, Any], month: date, *, closed: bool = False
) -> None:
    obligations = list(
        await session.scalars(
            select(FundObligation).where(
                FundObligation.employee_id == row["employee"]["id"], FundObligation.month == month
            )
        )
    )
    paid = ZERO
    due = ZERO
    for obligation in obligations:
        paid += await obligation_paid(session, obligation.id)
        due += await balance(session, "obligation", obligation.id)
    unallocated = await balance(session, "unallocated", row["employee"]["id"])
    row["unallocated"] = str(unallocated)
    if row.get("amounts"):
        row["amounts"] = {
            **row["amounts"],
            "paid": str(paid),
            "due": str(due if closed else Decimal(row["amounts"]["accrued"]) - paid),
        }


async def close_month(
    session: AsyncSession, actor: int, month: date, fingerprint: str, reason: str
) -> dict[str, Any]:
    await lock(session)
    await member(session, actor, leader=True)
    saved = await period(session, month)
    if saved.closed_at:
        if saved.snapshot and saved.snapshot.get("fingerprint") == fingerprint:
            return await report(session, actor, month)
        raise FundError("Месяц уже закрыт по другому снимку")
    # Снимок часов и условий берётся из одной согласованной версии и не обгоняет запись дейлика.
    await session.execute(
        text(
            "LOCK TABLE employees, dailies, daily_intervals, schedule_plans, plan_days, "
            "day_statuses, calculation_versions, parse_results IN SHARE MODE"
        )
    )
    result = await report(session, actor, month)
    if result["fingerprint"] != fingerprint:
        raise FundError("Исходные данные изменились; проверьте обновлённый расчёт")
    if not result["can_close"]:
        raise FundError("Месяц не готов к закрытию: есть незавершённые сведения")
    entries = []
    for row in result["rows"]:
        employee, amount = row["employee"]["id"], row["amounts"]
        supplement = Decimal(amount["supplement"])
        if supplement:
            obligation = FundObligation(
                employee_id=employee,
                month=month,
                kind="salary",
                amount=supplement,
                origin=f"salary:{month}:{employee}",
                title=f"Доплата за {month:%m.%Y}",
            )
            session.add(obligation)
            await session.flush()
            entries.append(("obligation", obligation.id, supplement))
        entries.append(
            (
                "overpayment",
                employee,
                Decimal(amount["overpayment_new"]) - Decimal(amount["offset"]),
            )
        )
    await internal_operation(
        session,
        actor,
        key=f"closure:{month}",
        kind="closure",
        day=next_month(month) - timedelta(days=1),
        reason=reason,
        details={"month": str(month), "fingerprint": fingerprint},
        entries=entries,
    )
    saved.snapshot = result
    saved.closed_at, saved.closed_by = clock.now(), actor
    audit(session, actor, "period.closed", month=str(month), fingerprint=fingerprint, reason=reason)
    await session.flush()
    return await report(session, actor, month)
