"""Проверяемый перенос финансового архива. Снимки остатков не повторяют движения денег."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import Field, model_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from teamtime.calc.fund import START, ZERO, money
from teamtime.core import clock
from teamtime.db.fund import FundMember, FundPeriod
from teamtime.db.fund_operations import FundBasket, FundImport, FundObligation
from teamtime.db.models import Employee
from teamtime.fund_schemas import Amount, Input, OpeningInput, SignedAmount, VacationYearInput
from teamtime.services import fund, fund_requests, fund_setup
from teamtime.services.fund_ledger import audit, digest, internal_operation


class Provenance(Input):
    book: str = Field(min_length=1, max_length=500)
    sheet: str = Field(min_length=1, max_length=200)
    cells: list[str] = Field(min_length=1, max_length=100)
    note: str = Field(min_length=1, max_length=2000)


class HistoricalRow(Input):
    month: date
    employee_id: int = Field(gt=0)
    norm_sec: int = Field(ge=0)
    effective_sec: int
    penalty_sec: int = Field(ge=0)
    credited_sec: int
    amounts: dict[str, SignedAmount]
    source: Provenance


class CashOpening(Input):
    basket_id: int = Field(gt=0)
    amount: Amount
    source: Provenance


class OverpaymentOpening(Input):
    employee_id: int = Field(gt=0)
    amount: Amount
    source: Provenance


class HistoricalObligation(Input):
    key: str = Field(min_length=1, max_length=100)
    employee_id: int = Field(gt=0)
    month: date
    kind: Literal["salary", "compensation"]
    amount: Amount
    paid: Amount
    title: str = Field(min_length=1, max_length=200)
    source: Provenance


class VacationOpening(Input):
    year: VacationYearInput
    historical_days: list[date] = Field(default_factory=list)
    source: Provenance


class Package(Input):
    package_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    as_of: date
    source: str = Field(min_length=1, max_length=2000)
    approved_by_leader: bool
    history: list[HistoricalRow] = Field(default_factory=list)
    cash: list[CashOpening] = Field(default_factory=list)
    overpayments: list[OverpaymentOpening] = Field(default_factory=list)
    obligations: list[HistoricalObligation] = Field(default_factory=list)
    vacations: list[VacationOpening] = Field(default_factory=list)
    included_cash_operations: list[Provenance] = Field(default_factory=list)
    expected_cash: Amount
    expected_overpayments: Amount
    expected_due: SignedAmount

    @model_validator(mode="after")
    def valid(self) -> Package:
        keys: list[Any] = [(r.employee_id, r.month) for r in self.history]
        groups = [
            keys,
            [c.basket_id for c in self.cash],
            [o.employee_id for o in self.overpayments],
            [o.key for o in self.obligations],
        ]
        if any(len(set(group)) != len(group) for group in groups):
            raise ValueError("В пакете повторяются строки или ключи операций")
        if any(r.month not in {date(2026, 9, 1), date(2026, 10, 1)} for r in self.history):
            raise ValueError("Исторический снимок допустим только за сентябрь и октябрь 2026")
        if any(o.month.day != 1 or o.month >= START for o in self.obligations):
            raise ValueError("Начальные обязательства относятся к историческим месяцам")
        if self.as_of < date(2026, 10, 31):
            raise ValueError("Начальный снимок должен завершать исторический период")
        return self


AMOUNT_KEYS = {
    "salary",
    "bonus",
    "correction",
    "received",
    "overpayment_in",
    "difference",
    "offset",
    "overpayment_new",
    "overpayment_out",
    "supplement_before_rounding",
    "supplement",
    "rounding",
    "compensation",
    "accrued",
    "paid",
    "due",
}


async def inspect(session: AsyncSession, actor: int, package: Package) -> dict[str, Any]:
    await fund.member(session, actor, leader=True)
    fingerprint = digest(package.model_dump(mode="json"))
    previous = await session.get(FundImport, package.package_id)
    if previous:
        if previous.digest != fingerprint:
            raise fund.FundError("Пакет уже импортирован с другим содержимым")
        return {"digest": fingerprint, "already_applied": True, "problems": [], "ready": True}
    problems: list[str] = []
    cash = sum((c.amount for c in package.cash), ZERO)
    overpayment = sum((o.amount for o in package.overpayments), ZERO)
    due = sum((o.amount - o.paid for o in package.obligations), ZERO)
    if (cash, overpayment, due) != (
        package.expected_cash,
        package.expected_overpayments,
        package.expected_due,
    ):
        problems.append("Контрольные суммы денег, переплат или обязательств не совпали")
    if not package.approved_by_leader:
        problems.append("Нет подтверждения исходного пакета руководителем")
    members = {m.employee_id for m in await session.scalars(select(FundMember))}
    employees = (
        {r.employee_id for r in package.history}
        | {o.employee_id for o in package.overpayments}
        | {o.employee_id for o in package.obligations}
        | {v.year.employee_id for v in package.vacations}
    )
    if employees - members:
        problems.append(
            "Не все внутренние ID сопоставлены с участниками; автоматического поиска по фамилии нет"
        )
    for c in package.cash:
        basket = await session.get(FundBasket, c.basket_id)
        if basket is None:
            problems.append(f"Корзина #{c.basket_id} не настроена")
        # Владелец подтверждает свою корзину, даже если пакет переносит руководитель.
        elif basket.owner_id != actor:
            from teamtime.db.fund_operations import FundReconciliation

            approval = await session.scalar(
                select(FundReconciliation.id).where(
                    FundReconciliation.basket_id == basket.id,
                    FundReconciliation.as_of == package.as_of,
                    FundReconciliation.actual == c.amount,
                    FundReconciliation.confirmed_by == basket.owner_id,
                )
            )
            if approval is None:
                problems.append(f"Корзина #{basket.id}: нужен ответ владельца на дату снимка")
    for row in package.history:
        if set(row.amounts) != AMOUNT_KEYS:
            problems.append(
                f"Строка {row.employee_id}/{row.month}: неполная расшифровка исторических сумм"
            )
        elif row.amounts["due"] != money(row.amounts["accrued"] - row.amounts["paid"]):
            problems.append(
                f"Строка {row.employee_id}/{row.month}: остаток не равен начислению минус выплаты"
            )
        obligations = [
            o
            for o in package.obligations
            if o.employee_id == row.employee_id and o.month == row.month
        ]
        if set(row.amounts) == AMOUNT_KEYS and (
            sum((o.amount for o in obligations), ZERO) != row.amounts["accrued"]
            or sum((o.paid for o in obligations), ZERO) != row.amounts["paid"]
        ):
            problems.append(
                f"Строка {row.employee_id}/{row.month}: обязательства "
                f"и выплаты не совпали с архивом"
            )
        existing = await session.get(FundPeriod, row.month)
        if existing and existing.closed_at:
            problems.append(f"Исторический месяц {row.month} уже перенесён другим пакетом")
    for v in package.vacations:
        if any(d >= v.year.as_of or not v.year.start <= d <= v.year.end for d in v.historical_days):
            problems.append(
                f"Отпуск #{v.year.employee_id}: история должна предшествовать "
                f"снимку и входить в рабочий год"
            )
    return {
        "digest": fingerprint,
        "already_applied": False,
        "ready": not problems,
        "problems": problems,
        "cash": str(cash),
        "overpayments": str(overpayment),
        "due": str(due),
        "history_rows": len(package.history),
        "vacation_days": {
            str(v.year.employee_id): len(set(v.historical_days)) for v in package.vacations
        },
        "included_operations": len(package.included_cash_operations),
    }


async def apply(
    session: AsyncSession, actor: int, package: Package, expected_digest: str
) -> dict[str, Any]:
    await fund.lock(session)
    result = await inspect(session, actor, package)
    if result["digest"] != expected_digest:
        raise fund.FundError("После проверки содержимое пакета изменилось")
    if not result["ready"]:
        raise fund.FundError("Импорт заблокирован: " + "; ".join(result["problems"]))
    if result["already_applied"]:
        return result
    # Только начальные значения. Перечень операций до снимка остаётся происхождением, не проводками.
    for c in package.cash:
        basket = await session.get(FundBasket, c.basket_id)
        assert basket is not None
        await fund_setup.basket_opening(
            session, basket.owner_id, basket.id, package.as_of, c.amount, c.source.note
        )
    for opening in package.overpayments:
        await fund_setup.overpayment_opening(
            session,
            actor,
            opening.employee_id,
            OpeningInput(month=START, amount=opening.amount, reason=opening.source.note),
        )
    for vacation in package.vacations:
        await fund_requests.set_vacation_year(session, actor, vacation.year)
    for entry in package.obligations:
        obligation = FundObligation(
            employee_id=entry.employee_id,
            month=entry.month,
            kind=entry.kind,
            amount=entry.amount,
            origin=f"import:{package.package_id}:{entry.key}",
            title=entry.title,
        )
        session.add(obligation)
        await session.flush()
        await internal_operation(
            session,
            actor,
            key=f"{obligation.origin}:accrual",
            kind="obligation",
            day=entry.month,
            reason=entry.source.note,
            details={"import": package.package_id, "source": entry.source.model_dump(mode="json")},
            entries=[("obligation", obligation.id, entry.amount)],
        )
        if entry.paid:
            await internal_operation(
                session,
                actor,
                key=f"{obligation.origin}:payment",
                kind="import_payment",
                day=package.as_of,
                reason=entry.source.note,
                details={"import": package.package_id, "cash_included_in_snapshot": True},
                entries=[("obligation", obligation.id, -entry.paid)],
            )
    for month in sorted({r.month for r in package.history}):
        rows = []
        for historical in package.history:
            if historical.month != month:
                continue
            employee = await session.get(Employee, historical.employee_id)
            assert employee is not None
            rows.append(
                {
                    "employee": {
                        "id": employee.id,
                        "name": employee.full_name,
                        "short_name": employee.short_name,
                        "department": employee.department,
                        "avatar_url": employee.avatar_url,
                    },
                    "no_other_income": False,
                    "norm_sec": historical.norm_sec,
                    "effective_sec": historical.effective_sec,
                    "penalty_sec": historical.penalty_sec,
                    "credited_sec": historical.credited_sec,
                    "parts": [],
                    "sources": [],
                    "receipts": [],
                    "blockers": [],
                    "inputs": None,
                    "amounts": {k: str(v) for k, v in historical.amounts.items()},
                    "source": historical.source.model_dump(mode="json"),
                    "unallocated": "0.00",
                }
            )
        snapshot = {
            "month": str(month),
            "ruleset": "historical-confirmed",
            "closed": True,
            "closed_at": clock.now().isoformat(),
            "can_close": False,
            "rows": rows,
            "blockers": [],
            "import": package.package_id,
        }
        snapshot["fingerprint"] = digest(snapshot)
        stored = await session.get(FundPeriod, month)
        if stored is None:
            stored = FundPeriod(month=month)
            session.add(stored)
        stored.closed_at, stored.closed_by, stored.snapshot = clock.now(), actor, snapshot
    session.add(
        FundImport(
            package_id=package.package_id,
            digest=result["digest"],
            as_of=package.as_of,
            source=package.source,
            manifest=package.model_dump(mode="json"),
            applied_by=actor,
        )
    )
    audit(
        session,
        actor,
        "import.applied",
        package_id=package.package_id,
        digest=result["digest"],
        totals={k: result[k] for k in ("cash", "overpayments", "due")},
    )
    await session.flush()
    return {**result, "applied": True}
