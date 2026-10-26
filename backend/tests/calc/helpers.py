from __future__ import annotations

from teamtime.calc import FactInput, PlanInput
from teamtime.calc.duration import parse_hm
from teamtime.parsing import Interval, PlanDayKind


def iv(span: str) -> Interval:
    a, b = span.split("-")
    return Interval(int(parse_hm(a)), int(parse_hm(b)))


def work(*spans: str) -> PlanInput:
    return PlanInput(PlanDayKind.WORK, tuple(iv(s) for s in spans))


def note(text: str = "по вайбу") -> PlanInput:
    return PlanInput(PlanDayKind.NOTE, (), text)


def off() -> PlanInput:
    return PlanInput(PlanDayKind.OFF)


def fact(*spans: str, e: int | None = 100) -> FactInput:
    return FactInput(tuple(iv(s) for s in spans), e)
