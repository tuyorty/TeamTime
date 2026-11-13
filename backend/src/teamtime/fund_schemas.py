"""Публичные поля фонда. Личные исходники и реквизиты в эти схемы не входят."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Amount = Annotated[
    Decimal, Field(ge=0, le=Decimal("999999999999.99"), max_digits=14, decimal_places=2)
]
SignedAmount = Annotated[
    Decimal,
    Field(
        ge=Decimal("-999999999999.99"),
        le=Decimal("999999999999.99"),
        max_digits=14,
        decimal_places=2,
    ),
]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ReceiptInput(Input):
    request_id: UUID
    source: str = Field(min_length=1, max_length=100)
    origin_month: date
    received_on: date
    amount: Amount = Field(gt=0)


class SourceInput(Input):
    month: date
    source: str = Field(min_length=1, max_length=100)
    complete: bool
    expected_total: SignedAmount
    expected_version: int = Field(ge=0)


class TermsInput(Input):
    effective_from: date
    target: Amount
    share: Decimal = Field(gt=0, le=10, decimal_places=4)
    sources: list[str] = Field(max_length=20)
    no_other_income: bool = False
    reason: str = Field(min_length=1, max_length=1000)


class CalendarInput(Input):
    month: date
    version: str = Field(min_length=1, max_length=100)
    source: str = Field(min_length=1, max_length=2000)
    days: dict[date, int]
    holidays: set[date] = Field(default_factory=set)
    reason: str = Field(min_length=1, max_length=1000)


class Allocation(Input):
    obligation_id: int = Field(gt=0)
    amount: Amount = Field(gt=0)


class OperationInput(Input):
    request_id: UUID
    kind: Literal[
        "contribution",
        "interest",
        "expense",
        "refund",
        "payment",
        "transfer",
        "loan_issue",
        "loan_repayment",
        "loan_offset",
        "overpayment_return",
        "allocate",
        "cash_correction",
        "compensation_return",
    ]
    occurred_on: date
    amount: Amount = Field(gt=0)
    basket_id: int | None = Field(None, gt=0)
    target_basket_id: int | None = Field(None, gt=0)
    employee_id: int | None = Field(None, gt=0)
    allocations: list[Allocation] = Field(default_factory=list, max_length=100)
    loan_id: int | None = Field(None, gt=0)
    original_id: int | None = Field(None, gt=0)
    correction_direction: Literal[-1, 1] = 1
    reason: str = Field(min_length=1, max_length=1000)


class ClaimInput(Input):
    request_id: UUID
    month: date
    spent_on: date
    amount: Amount = Field(gt=0)
    title: str = Field(min_length=1, max_length=200)


class DecisionInput(Input):
    approve: bool
    reason: str = Field(min_length=1, max_length=1000)


class TimeRequestInput(Input):
    request_id: UUID
    kind: Literal["vacation", "sick", "trip", "missed", "waiver", "no_work"]
    days: list[date] = Field(min_length=1, max_length=366)
    seconds: int = Field(0, ge=0, le=86400)
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("days")
    @classmethod
    def unique_days(cls, value: list[date]) -> list[date]:
        if len(value) != len(set(value)):
            raise ValueError("Дата повторяется")
        return sorted(value)


class LoanInput(Input):
    request_id: UUID
    employee_id: int = Field(gt=0)
    amount: Amount = Field(gt=0)
    issued_on: date
    due_on: date
    reason: str = Field(min_length=1, max_length=1000)


class ReconciliationInput(Input):
    request_id: UUID
    basket_id: int = Field(gt=0)
    as_of: date
    actual: Amount
    reason: str = Field(min_length=1, max_length=1000)


class VacationYearInput(Input):
    employee_id: int = Field(gt=0)
    start: date
    end: date
    as_of: date
    annual_days: int = Field(28, ge=0, le=366)
    opening_days: int = Field(ge=0, le=1000)
    adjustment_days: int = Field(0, ge=-1000, le=1000)
    reason: str = Field(min_length=1, max_length=1000)


class MemberInput(Input):
    employee_id: int = Field(gt=0)
    active: bool = True
    leader: bool = False
    joined_on: date
    left_on: date | None = None
    reason: str = Field(min_length=1, max_length=1000)


class BasketInput(Input):
    name: str = Field(min_length=1, max_length=100)
    owner_id: int = Field(gt=0)


class OpeningInput(Input):
    month: date
    amount: Amount
    reason: str = Field(min_length=1, max_length=1000)


class CloseInput(Input):
    fingerprint: str = Field(min_length=64, max_length=64)
    reason: str = Field(min_length=1, max_length=1000)


class BonusInput(Input):
    request_id: UUID
    employee_id: int = Field(gt=0)
    month: date
    amount: Amount = Field(gt=0)
    reason: str = Field(min_length=1, max_length=1000)


class CorrectedCondition(Input):
    key: str = Field(min_length=1, max_length=100)
    start: date
    end: date
    target: Amount
    share: Decimal = Field(gt=0, le=10, decimal_places=4)


class CorrectionInput(Input):
    request_id: UUID
    employee_id: int = Field(gt=0)
    origin_month: date
    kind: Literal["salary", "compensation", "source"]
    corrected_inputs: dict[str, object] = Field(default_factory=dict)
    corrected_conditions: list[CorrectedCondition] | None = Field(None, max_length=31)
    corrected_amount: SignedAmount | None = None
    reference_id: int | None = Field(None, gt=0)
    reason: str = Field(min_length=1, max_length=1000)
