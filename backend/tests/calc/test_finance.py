"""Оклад сохраняется при недоработке, точность переработки не теряется."""

from decimal import Decimal

from teamtime.calc import summarize_month
from teamtime.services.finance import amounts
from tests.calc.test_month import golden_month


def test_salary_is_full_even_with_missing_days_or_no_facts():
    for days in [[], golden_month()]:
        summary = summarize_month(days, norm=160 * 3600, hourly_rate=Decimal(500))
        result = amounts(summary, Decimal("1234.56"))
        assert result.salary == Decimal("80000.00")
        assert result.overtime_pay == 0
        assert result.total == Decimal("81234.56")


def test_overtime_uses_exact_fraction_after_efficiency_and_penalty():
    summary = summarize_month(golden_month(), norm=20 * 3600, hourly_rate=Decimal(500))
    result = amounts(summary, Decimal("1000.05"))
    assert result.salary == Decimal("10000.00")
    assert result.overtime_pay == Decimal("244.05")
    assert result.total == Decimal("11244.10")
