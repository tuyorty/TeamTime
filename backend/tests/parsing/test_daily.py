"""Разбор дейликов: образцы из задания и табличные кейсы на устойчивость."""

from __future__ import annotations

from datetime import UTC, date, datetime
from textwrap import dedent

import pytest

from teamtime.parsing import MessageKind, ParseStatus, parse_daily, parse_message
from teamtime.parsing.text import format_seconds
from tests.parsing.conftest import SENT, TZ, codes

SAMPLE_23 = dedent("""\
    23.10.2026
    15:40 - 20:00
    Эффективность:  70%

    - сделал то-то
    - разбирался с тем-то

    #дейли
""")

SAMPLE_22 = dedent("""\
    22.10.2026
    13:30 - 15:30; 17:30 - 18:40
    Эффективность: 100%

    - фиксы безопасности
    - документация

    #дейли
""")


def daily(text: str, sent: datetime = SENT):
    return parse_daily(text, sent, TZ)


def spans(result) -> list[str]:
    assert result.daily is not None
    return [f"{format_seconds(i.start)}-{format_seconds(i.end)}" for i in result.daily.intervals]


class TestSamplesFromBrief:
    def test_single_interval(self) -> None:
        r = daily(SAMPLE_23)
        assert r.kind is MessageKind.DAILY
        assert r.status is ParseStatus.OK, r.issues
        d = r.daily
        assert d is not None
        assert d.work_date == date(2026, 10, 23)
        assert spans(r) == ["15:40-20:00"]
        assert format_seconds(d.worked_seconds) == "4:20"
        assert d.efficiency == 70
        assert d.tasks == ("сделал то-то", "разбирался с тем-то")

    def test_two_intervals_sum_hours_and_span_first_to_last(self) -> None:
        r = daily(SAMPLE_22)
        assert r.status is ParseStatus.OK, r.issues
        d = r.daily
        assert d is not None
        assert spans(r) == ["13:30-15:30", "17:30-18:40"]
        assert format_seconds(d.start) == "13:30"  # Пришёл
        assert format_seconds(d.end) == "18:40"  # Ушёл
        assert format_seconds(d.worked_seconds) == "3:10"  # Часы = сумма интервалов
        assert d.efficiency == 100

    def test_work_date_is_from_text_not_sending(self) -> None:
        sent = datetime(2026, 10, 24, 18, 0, tzinfo=UTC)
        r = daily(SAMPLE_22, sent)
        assert r.daily is not None and r.daily.work_date == date(2026, 10, 22)


class TestEfficiency:
    @pytest.mark.parametrize(
        ("line", "value"),
        [
            ("Эффективность: 70%", 70),
            ("Эффективность:  70%", 70),
            ("эффективность: 70%", 70),
            ("ЭФФЕКТИВНОСТЬ: 70%", 70),
            ("Эффективность 70%", 70),
            ("Эффективность: 70", 70),
            ("Эффективность:70 %", 70),
            ("Эффективность - 70%", 70),
            ("Эфективность: 70%", 70),
            ("Эфф: 70%", 70),
            ("Эфф. 70", 70),
            ("e% 80", 80),
            ("Эффективность: 0%", 0),
            ("Эффективность: 100%", 100),
            ("Эффективность: 72,5%", 72),
            # из реальных дейликов: комментарий в скобках и опечатки в слове
            ("Эффективность: 90% (сидел с кнопкой какое-то время)", 90),
            ("Эффективность: 65%(вычел за 40 минут)", 65),
            ("Эффеткивность: 100%", 100),
            ("Эффективонсть: 100%", 100),
        ],
    )
    def test_variants(self, line: str, value: int) -> None:
        r = daily(f"23.10.2026\n10:00 - 18:00\n{line}")
        assert r.daily is not None and r.daily.efficiency == value, r.issues

    def test_missing_efficiency_is_partial(self) -> None:
        r = daily("23.10.2026\n10:00 - 18:00\n- задача")
        assert r.status is ParseStatus.PARTIAL
        assert "no_efficiency" in codes(r)
        assert r.daily is not None and r.daily.efficiency is None

    @pytest.mark.parametrize(
        "line",
        ["Эффективность: 150%", "Эффективность: много", "Эфф: ?", "Эффективность: 1488%"],
    )
    def test_bad_values(self, line: str) -> None:
        r = daily(f"23.10.2026\n10:00 - 18:00\n{line}")
        assert "bad_efficiency" in codes(r)
        assert r.status is ParseStatus.PARTIAL
        assert r.daily is not None and r.daily.efficiency is None

    def test_comment_is_noted(self) -> None:
        r = daily("23.10.2026\n10:00 - 18:00\nЭффективность: 85% (кс)")
        assert r.status is ParseStatus.OK
        assert "comment_ignored" in codes(r)

    def test_word_that_only_looks_similar_is_not_efficiency(self) -> None:
        r = daily("23.10.2026\n10:00 - 18:00\nЭфф: 80%\n\nЭфир 30 минут")
        assert r.daily is not None and r.daily.efficiency == 80
        assert codes(r).isdisjoint({"duplicate_efficiency", "bad_efficiency"})

    def test_duplicate_takes_first(self) -> None:
        r = daily("23.10.2026\n10:00 - 18:00\nЭфф: 60%\nЭфф: 90%")
        assert r.daily is not None and r.daily.efficiency == 60
        assert "duplicate_efficiency" in codes(r)


class TestIntervals:
    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            ("15:40 - 20:00", ["15:40-20:00"]),
            ("15:40-20:00", ["15:40-20:00"]),
            ("15:40 – 20:00", ["15:40-20:00"]),
            ("15:40 — 20:00", ["15:40-20:00"]),
            ("6:00 - 9:00", ["6:00-9:00"]),
            ("06:00 - 09:00", ["6:00-9:00"]),
            ("13:30 - 15:30; 17:30 - 18:40", ["13:30-15:30", "17:30-18:40"]),
            ("13:30 - 15:30;17:30 - 18:40", ["13:30-15:30", "17:30-18:40"]),
            ("13:30 - 15:30, 17:30 - 18:40", ["13:30-15:30", "17:30-18:40"]),
            ("9:00-10:00; 11:00-12:00; 13:00-14:00", ["9:00-10:00", "11:00-12:00", "13:00-14:00"]),
            ("15.40 - 20.00", ["15:40-20:00"]),
            ("10 - 18", ["10:00-18:00"]),
            ("с 10:00 до 18:00", ["10:00-18:00"]),
            ("18:00 - 00:00", ["18:00-24:00"]),
        ],
    )
    def test_variants(self, line: str, expected: list[str]) -> None:
        r = daily(f"23.10.2026\n{line}\nЭффективность: 80%")
        assert spans(r) == expected, r.issues

    @pytest.mark.parametrize(
        ("line", "expected", "code"),
        [
            ("10:50 - 19:20 (час добавил за воскресенье)", ["10:50-19:20"], "comment_ignored"),
            ("9:00 - 15:30 (раньше уехал из-за митапа)", ["9:00-15:30"], "comment_ignored"),
            ("14:00 - 24:00(00:00)", ["14:00-24:00"], "comment_ignored"),
            ("15;00 - 18:00", ["15:00-18:00"], "time_typo"),
            ("09:35 - 18: 30", ["9:35-18:30"], "time_typo"),
            ("11:30 - 19 00", ["11:30-19:00"], "time_typo"),
            ("10;00 - 13;00; 14;00 - 18;00", ["10:00-13:00", "14:00-18:00"], "time_typo"),
        ],
    )
    def test_real_life_comments_and_typos(self, line: str, expected: list[str], code: str) -> None:
        """Строки из реальных дейликов: раньше часы за такой день терялись целиком."""
        r = daily(f"23.10.2026\n{line}\nЭффективность: 80%")
        assert spans(r) == expected, r.issues
        assert code in codes(r)
        assert r.status is ParseStatus.OK

    def test_comment_without_time_is_still_not_an_interval(self) -> None:
        r = daily("23.10.2026\n(забыл время)\nЭфф: 80%")
        assert "no_intervals" in codes(r)

    def test_intervals_on_several_lines_are_merged(self) -> None:
        r = daily("23.10.2026\n10:00 - 12:00\n13:00 - 18:00\nЭфф: 80%")
        assert spans(r) == ["10:00-12:00", "13:00-18:00"]
        assert "intervals_multiline" in codes(r)
        assert r.status is ParseStatus.OK

    def test_overnight_interval_counts_into_work_date_with_warning(self) -> None:
        r = daily("23.10.2026\n22:00 - 02:00\nЭфф: 80%")
        assert r.daily is not None
        assert r.daily.worked_seconds == 4 * 3600
        assert r.daily.work_date == date(2026, 10, 23)
        assert "overnight" in codes(r)
        assert r.status is ParseStatus.PARTIAL

    def test_overlap_warns(self) -> None:
        r = daily("23.10.2026\n10:00 - 13:00; 12:00 - 14:00\nЭфф: 80%")
        assert "overlap" in codes(r)

    def test_zero_length_warns(self) -> None:
        r = daily("23.10.2026\n10:00 - 10:00\nЭфф: 80%")
        assert "empty_interval" in codes(r)

    def test_impossible_time_fails(self) -> None:
        r = daily("23.10.2026\n10:00 - 25:00\nЭфф: 80%")
        assert r.status is ParseStatus.FAILED
        assert "bad_time" in codes(r)

    def test_interval_on_date_line(self) -> None:
        r = daily("23.10.2026 15:40 - 20:00\nЭфф: 70%")
        assert spans(r) == ["15:40-20:00"]

    def test_no_intervals_fails(self) -> None:
        r = daily("23.10.2026\nЭффективность: 80%\n- что-то")
        assert r.status is ParseStatus.FAILED
        assert "no_intervals" in codes(r)


class TestDate:
    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            ("23.10.2026", date(2026, 10, 23)),
            ("23.10.26", date(2026, 10, 23)),
            ("23/10/2026", date(2026, 10, 23)),
            ("3.10.2026", date(2026, 10, 3)),
            ("23.10.2026 (пт)", date(2026, 10, 23)),
            ("Дата: 23.10.2026", date(2026, 10, 23)),
        ],
    )
    def test_variants(self, line: str, expected: date) -> None:
        r = daily(f"{line}\n10:00 - 18:00\nЭфф: 80%")
        assert r.daily is not None and r.daily.work_date == expected

    def test_without_year_uses_sending_date(self) -> None:
        r = daily("23.10\n10:00 - 18:00\nЭфф: 80%")
        assert r.daily is not None and r.daily.work_date == date(2026, 10, 23)
        assert "year_inferred" in codes(r)
        assert r.status is ParseStatus.OK

    def test_without_year_across_new_year(self) -> None:
        sent = datetime(2027, 1, 2, 8, 0, tzinfo=UTC)
        r = daily("31.12\n10:00 - 18:00\nЭфф: 80%", sent)
        assert r.daily is not None and r.daily.work_date == date(2026, 12, 31)

    def test_missing_date_fails(self) -> None:
        r = daily("10:00 - 18:00\nЭфф: 80%")
        assert r.status is ParseStatus.FAILED
        assert "no_date" in codes(r)

    def test_dotted_time_first_line_is_not_a_date(self) -> None:
        r = daily("15.40 - 20.00\nЭфф: 80%")
        assert "no_date" in codes(r)
        assert "bad_date" not in codes(r)

    def test_impossible_date_fails(self) -> None:
        r = daily("31.02.2026\n10:00 - 18:00\nЭфф: 80%")
        assert r.status is ParseStatus.FAILED
        assert "bad_date" in codes(r)

    def test_future_date_warns(self) -> None:
        r = daily("30.10.2026\n10:00 - 18:00\nЭфф: 80%")
        assert "future_date" in codes(r)

    @pytest.mark.parametrize("line", ["22.10.2025", "22.10.2020", "22.10.25"])
    def test_year_typo_is_fixed_with_warning(self, line: str) -> None:
        """«22.10.2025», присланный 24.10.2026, — опечатка в годе: часы идут на 22.10.2026."""
        r = daily(f"{line}\n10:00 - 18:00\nЭфф: 80%")
        assert r.daily is not None and r.daily.work_date == date(2026, 10, 22)
        assert "year_fixed" in codes(r)
        assert "old_date" not in codes(r)
        assert r.status is ParseStatus.OK  # тот же день и месяц в пределах месяца — не гадание

    def test_wrong_month_is_not_guessed(self) -> None:
        r = daily("22.08.2025\n10:00 - 18:00\nЭфф: 80%")
        assert r.daily is not None and r.daily.work_date == date(2025, 8, 22)
        assert "old_date" in codes(r)

    def test_very_old_date_warns(self) -> None:
        r = daily("01.08.2026\n10:00 - 18:00\nЭфф: 80%")
        assert "old_date" in codes(r)


class TestTasksAndNoise:
    def test_no_tasks_is_fine(self) -> None:
        r = daily("23.10.2026\n10:00 - 18:00\nЭфф: 80%")
        assert r.status is ParseStatus.OK
        assert r.daily is not None and r.daily.tasks == ()

    def test_unknown_line_is_warning(self) -> None:
        r = daily("23.10.2026\n10:00 - 18:00\nнормально поработал\nЭфф: 80%")
        assert "unknown_line" in codes(r)
        assert r.status is ParseStatus.PARTIAL

    def test_task_with_times_is_a_task_not_interval(self) -> None:
        r = daily("23.10.2026\n10:00 - 18:00\nЭфф: 80%\n- созвон 12:00 - 13:00")
        assert spans(r) == ["10:00-18:00"]
        assert r.daily is not None and r.daily.tasks == ("созвон 12:00 - 13:00",)

    def test_free_text_after_header_is_a_task(self) -> None:
        r = daily(
            dedent("""\
            21.10.2026
            09:20 - 19:50
            Эффективность: 100%

            Разбирался с картой отклонений
            -Добавил проверку слоёв
            -Починил регистрацию моделей

            #дейли
        """)
        )
        assert r.status is ParseStatus.OK, codes(r)
        assert r.daily is not None
        assert r.daily.tasks == (
            "Разбирался с картой отклонений",
            "Добавил проверку слоёв",
            "Починил регистрацию моделей",
        )

    def test_blank_line_starts_new_task(self) -> None:
        r = daily(
            dedent("""\
            21.10.2026
            10:00 - 18:00
            Эффективность: 90%

            - первый пункт
            продолжение первого

            Upd: вернулся вечером
            - второй пункт
        """)
        )
        assert r.daily is not None
        assert r.daily.tasks == (
            "первый пункт продолжение первого",
            "Upd: вернулся вечером",
            "второй пункт",
        )

    def test_text_after_tag_is_ignored(self) -> None:
        r = daily("21.10.2026\n10:00 - 18:00\nЭфф: 80%\n\n- пункт\n\n#дейли\n\nвечером ещё заеду")
        assert r.status is ParseStatus.OK
        assert r.daily is not None and r.daily.tasks == ("пункт",)
        assert "text_after_tag" in codes(r)

    @pytest.mark.parametrize(
        "text",
        ["", "\n\n", "ок", "23.10.2026", "#дейли", "Эффективность: 80%", "🚀", "- - -"],
    )
    def test_garbage_never_raises(self, text: str) -> None:
        assert daily(text).status is ParseStatus.FAILED


class TestEdits:
    """Правка сообщения — это новый текст той же сущности. Парсер разбирает каждую версию
    независимо, а сервис сравнивает результаты. Здесь проверяем, что изменения видны."""

    def test_edit_changes_efficiency(self) -> None:
        before = daily(SAMPLE_23)
        after = daily(SAMPLE_23.replace("70%", "85%"))
        assert before.daily is not None and after.daily is not None
        assert (before.daily.efficiency, after.daily.efficiency) == (70, 85)

    def test_edit_changes_date(self) -> None:
        after = daily(SAMPLE_23.replace("23.10.2026", "22.10.2026"))
        assert after.daily is not None and after.daily.work_date == date(2026, 10, 22)


def test_parse_message_detects_daily_without_hashtag() -> None:
    text = SAMPLE_22.replace("#дейли", "")
    r = parse_message(text, SENT, TZ)
    assert r.kind is MessageKind.DAILY
    assert r.status is ParseStatus.OK
