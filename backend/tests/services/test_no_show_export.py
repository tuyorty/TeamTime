"""Экспорт различает невыход, неизвестный приход и настоящий приход в полночь."""

import csv
import io
from datetime import date
from types import SimpleNamespace

import pytest

from teamtime.schemas import LateDay
from teamtime.services import export


@pytest.mark.parametrize(
    ("no_show", "fact_start", "expected"),
    [(True, None, "Подтверждённый невыход"), (False, 0, "0:00"), (False, None, "")],
)
def test_lateness_csv_preserves_absent_and_midnight_meanings(no_show, fact_start, expected):
    day = LateDay(
        date=date(2026, 10, 26),
        late_sec=3600,
        plan_start=23 * 3600,
        fact_start=fact_start,
        no_show=no_show,
    )
    month = SimpleNamespace(
        rows=[
            SimpleNamespace(
                employee=SimpleNamespace(short_name="Вымышленный сотрудник"), late_days=[day]
            )
        ]
    )
    header, rows = export.month_late_rows(month)
    csv_rows = list(
        csv.reader(io.StringIO(export.to_csv(header, rows).decode("utf-8-sig")), delimiter=";")
    )
    assert csv_rows[1][3] == expected
