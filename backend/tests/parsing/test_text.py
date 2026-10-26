from __future__ import annotations

import pytest

from teamtime.parsing.text import (
    TimeFormatError,
    bullet_text,
    format_seconds,
    hashtags,
    normalize_line,
    parse_interval,
    parse_interval_list,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("12:00 – 18:00", "12:00 - 18:00"),
        ("12:00 — 18:00", "12:00 - 18:00"),
        ("12:00 - 18:00", "12:00 - 18:00"),
        ("  много   пробелов  ", "много пробелов"),
        ("​невидимый", "невидимый"),
        ("ＦＵＬＬ", "FULL"),
    ],
)
def test_normalize_line(raw: str, expected: str) -> None:
    assert normalize_line(raw) == expected


@pytest.mark.parametrize(
    ("token", "start", "end"),
    [
        ("6:00 - 14:00", "6:00", "14:00"),
        ("06:00-14:00", "6:00", "14:00"),
        ("0:00 - 24:00", "0:00", "24:00"),
        ("23:30 - 0:30", "23:30", "0:30"),
    ],
)
def test_parse_interval(token: str, start: str, end: str) -> None:
    p = parse_interval(token)
    assert p is not None
    assert (format_seconds(p.interval.start), format_seconds(p.interval.end)) == (start, end)


@pytest.mark.parametrize("token", ["24:00 - 25:00", "10:60 - 11:00", "24:30 - 1:00"])
def test_parse_interval_rejects_impossible(token: str) -> None:
    with pytest.raises(TimeFormatError):
        parse_interval(token)


@pytest.mark.parametrize("token", ["", "10:00", "по вайбу", "10:00 18:00", "10:00 - "])
def test_parse_interval_ignores_non_intervals(token: str) -> None:
    assert parse_interval(token) is None


@pytest.mark.parametrize(
    ("line", "expected"),
    [("- раз", "раз"), ("-раз", "раз"), ("------", None), ("-", None), ("1) два", "два"),
     ("текст", None)],
)  # fmt: skip
def test_bullet_text(line: str, expected: str | None) -> None:
    assert bullet_text(line) == expected


def test_hashtags_are_folded_and_unique() -> None:
    assert hashtags("#Дейли и снова #дейли, #расписание") == ("дейли", "расписание")


@pytest.mark.parametrize(
    "text",
    [
        "09:00 - 14:00 и 15:30 - 16:00",
        "09:00 - 14:00 + 15:30 - 16:00",
        "09:00-14:00+15:30-16:00",
        "09:00 - 14:00 & 15:30 - 16:00",
        "09:00 - 14:00 И 15:30 - 16:00",
    ],
)
def test_interval_list_word_and_plus_separators(text: str) -> None:
    parsed = parse_interval_list(text)
    assert parsed is not None
    assert [(p.interval.start, p.interval.end) for p in parsed] == [(32400, 50400), (55800, 57600)]
