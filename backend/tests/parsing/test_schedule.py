"""Разбор расписания: образцы из задания и табличные кейсы на устойчивость."""

from __future__ import annotations

from datetime import UTC, date, datetime
from textwrap import dedent

import pytest

from teamtime.parsing import (
    MessageKind,
    ParseStatus,
    PlanDayKind,
    Severity,
    parse_message,
    parse_schedule,
)
from teamtime.parsing.text import format_seconds
from tests.parsing.conftest import SENT, TZ, codes

SAMPLE_IVANOV = dedent("""\
    Спринт 26.10 - 31.10
    Иванов И.И.

    Пн: 12:00 - 18:00
    Вт: 10:00 - 18:00
    Ср: 14:00 - 18:00
    Чт: по вайбу с 16:30 до вечера
    Пт: 10:00 - 18:00
    Сб: по вайбику(хз поеду ли)

    - задача один
    - задача два

    #расписание
""")

SAMPLE_PETROV = dedent("""\
    Спринт 26.10 - 31.10
    Петров П.П.

    ПН: 6:00 - 14:00
    ВТ: 10:00 - 20:00
    СБ: ——————

    - задача один
    - задача два

    #расписание
""")


def plan(text: str, sent: datetime = SENT):
    return parse_schedule(text, sent, TZ)


def day_map(result) -> dict[int, tuple[str, str | None, str | None, str | None]]:
    assert result.schedule is not None
    return {
        d.weekday: (
            d.kind.value,
            format_seconds(d.start) if d.start is not None else None,
            format_seconds(d.end) if d.end is not None else None,
            d.note,
        )
        for d in result.schedule.days
    }


class TestSamplesFromBrief:
    def test_ivanov(self) -> None:
        r = plan(SAMPLE_IVANOV)
        assert r.kind is MessageKind.SCHEDULE
        assert r.status is ParseStatus.OK
        s = r.schedule
        assert s is not None
        assert (s.sprint_start, s.sprint_end) == (date(2026, 10, 26), date(2026, 10, 31))
        assert (s.iso_year, s.iso_week) == (2026, 44)
        assert s.person is not None
        assert (s.person.surname, s.person.initials, s.person.key) == ("Иванов", "ИИ", "иванов ии")
        assert day_map(r) == {
            0: ("work", "12:00", "18:00", None),
            1: ("work", "10:00", "18:00", None),
            2: ("work", "14:00", "18:00", None),
            3: ("note", None, None, "по вайбу с 16:30 до вечера"),
            4: ("work", "10:00", "18:00", None),
            5: ("note", None, None, "по вайбику(хз поеду ли)"),
        }
        assert s.tasks == ("задача один", "задача два")

    def test_ivanov_note_with_time_is_flagged_but_not_guessed(self) -> None:
        r = plan(SAMPLE_IVANOV)
        assert r.schedule is not None
        thursday = next(d for d in r.schedule.days if d.weekday == 3)
        assert thursday.note_has_time is True
        assert thursday.intervals == ()
        info = [i for i in r.issues if i.code == "note_has_time"]
        assert len(info) == 1
        assert info[0].severity is Severity.INFO
        assert info[0].line_no == 7

    def test_petrov_uppercase_days_short_hours_and_dash_off(self) -> None:
        r = plan(SAMPLE_PETROV)
        assert r.status is ParseStatus.OK
        assert day_map(r) == {
            0: ("work", "6:00", "14:00", None),
            1: ("work", "10:00", "20:00", None),
            5: ("off", None, None, None),
        }
        assert r.schedule is not None
        assert r.schedule.days[0].date == date(2026, 10, 26)
        assert r.schedule.days[-1].date == date(2026, 10, 31)

    def test_hashtag_detected(self) -> None:
        assert plan(SAMPLE_IVANOV).hashtags == ("расписание",)


class TestDayLines:
    @pytest.mark.parametrize(
        ("line", "expected"),
        [
            ("Пн: 12:00 - 18:00", ("work", "12:00", "18:00", None)),
            ("пн: 12:00 - 18:00", ("work", "12:00", "18:00", None)),
            ("ПН: 12:00 - 18:00", ("work", "12:00", "18:00", None)),
            ("Пн 12:00-18:00", ("work", "12:00", "18:00", None)),
            ("Пн. 12:00 – 18:00", ("work", "12:00", "18:00", None)),
            ("Пн: 12:00 — 18:00", ("work", "12:00", "18:00", None)),
            ("Пн: 12:00 ― 18:00", ("work", "12:00", "18:00", None)),
            ("Пн: 12:00 − 18:00", ("work", "12:00", "18:00", None)),
            ("Пн - 12:00 - 18:00", ("work", "12:00", "18:00", None)),
            ("Пн:12:00-18:00", ("work", "12:00", "18:00", None)),
            ("Пн: 12:00 - 18:00", ("work", "12:00", "18:00", None)),
            ("Понедельник: 9:00 - 17:00", ("work", "9:00", "17:00", None)),
            ("Пн: 06:00 - 14:00", ("work", "6:00", "14:00", None)),
            ("Пн: с 10:00 до 18:00", ("work", "10:00", "18:00", None)),
            ("Пн: 10 - 18", ("work", "10:00", "18:00", None)),
            ("Пн: 18:00 - 00:00", ("work", "18:00", "24:00", None)),
            ("Пн: 10:00 - 18:00 (созвон в 12)", ("work", "10:00", "18:00", "созвон в 12")),
            ("Пн: ——————", ("off", None, None, None)),
            ("Пн: ---", ("off", None, None, None)),
            ("Пн: -", ("off", None, None, None)),
            ("Пн: выходной", ("off", None, None, None)),
            ("Пн: Выходной!", ("off", None, None, None)),
            ("Пн: вых", ("off", None, None, None)),
            ("Пн: по вайбу", ("note", None, None, "по вайбу")),
            ("Пн: как пойдёт", ("note", None, None, "как пойдёт")),
        ],
    )
    def test_monday_line(self, line: str, expected: tuple) -> None:
        r = plan(f"Спринт 26.10 - 31.10\nИванов И.И.\n{line}")
        assert r.status is not ParseStatus.FAILED, r.issues
        assert day_map(r)[0] == expected

    @pytest.mark.parametrize(
        ("abbr", "weekday"),
        [("Пн", 0), ("Вт", 1), ("Ср", 2), ("Чт", 3), ("Пт", 4), ("Сб", 5), ("Вс", 6),
         ("вс", 6), ("ВС", 6), ("Вторник", 1), ("СРЕДА", 2), ("пятница", 4)],
    )  # fmt: skip
    def test_all_weekdays(self, abbr: str, weekday: int) -> None:
        r = plan(f"Спринт 26.10 - 01.11\nИванов И.И.\n{abbr}: 10:00 - 12:00")
        assert list(day_map(r)) == [weekday]

    def test_multiple_plan_intervals_span_first_to_last(self) -> None:
        r = plan("Спринт 26.10 - 31.10\nИванов И.И.\nПн: 10:00 - 13:00; 15:00 - 19:00")
        assert r.schedule is not None
        d = r.schedule.days[0]
        assert (format_seconds(d.start), format_seconds(d.end)) == ("10:00", "19:00")
        assert d.planned_seconds == 7 * 3600
        assert "plan_split" in codes(r)
        assert r.status is ParseStatus.OK

    def test_overnight_plan_warns(self) -> None:
        r = plan("Спринт 26.10 - 31.10\nИванов И.И.\nПн: 22:00 - 02:00")
        assert "overnight" in codes(r)
        assert r.status is ParseStatus.PARTIAL
        assert r.schedule is not None
        assert r.schedule.days[0].planned_seconds == 4 * 3600

    def test_impossible_time_becomes_note_with_warning(self) -> None:
        r = plan("Спринт 26.10 - 31.10\nИванов И.И.\nПн: 25:00 - 26:00")
        assert "bad_time" in codes(r)
        assert day_map(r)[0][0] == "note"

    def test_empty_day_is_skipped_with_warning(self) -> None:
        r = plan("Спринт 26.10 - 31.10\nИванов И.И.\nПн:\nВт: 10:00 - 18:00")
        assert list(day_map(r)) == [1]
        assert "empty_day" in codes(r)
        assert r.status is ParseStatus.PARTIAL

    def test_duplicate_day_keeps_first(self) -> None:
        r = plan("Спринт 26.10 - 31.10\nИванов И.И.\nПн: 10:00 - 12:00\nпн: 14:00 - 18:00")
        assert day_map(r)[0][1] == "10:00"
        assert "duplicate_day" in codes(r)
        assert r.status is ParseStatus.PARTIAL

    def test_surname_starting_like_weekday_is_not_a_day(self) -> None:
        r = plan("Спринт 26.10 - 31.10\nСредин С.С.\nПн: 10:00 - 12:00")
        assert r.schedule is not None and r.schedule.person is not None
        assert r.schedule.person.surname == "Средин"
        assert list(day_map(r)) == [0]


class TestHeader:
    @pytest.mark.parametrize(
        "header",
        [
            "Спринт 26.10 - 31.10",
            "спринт 26.10 - 31.10",
            "СПРИНТ 26.10-31.10",
            "Спринт: 26.10 – 31.10",
            "Спринт 26/10 - 31/10",
            "Спринт 26.10.2026 - 31.10.2026",
            "Спринт 26.10.26 - 31.10.26",
            "Спринт №44 26.10 - 31.10",
        ],
    )
    def test_header_variants(self, header: str) -> None:
        r = plan(f"{header}\nИванов И.И.\nПн: 10:00 - 18:00")
        if "№44" in header:
            # «№44» — не дата; такой заголовок не распознаётся, и это честный failed.
            assert r.status is ParseStatus.FAILED
            return
        assert r.schedule is not None, r.issues
        assert r.schedule.sprint_start == date(2026, 10, 26)
        assert r.schedule.sprint_end == date(2026, 10, 31)

    def test_missing_header_fails(self) -> None:
        r = plan("Иванов И.И.\nПн: 10:00 - 18:00")
        assert r.status is ParseStatus.FAILED
        assert "no_header" in codes(r)

    def test_no_days_fails(self) -> None:
        r = plan("Спринт 26.10 - 31.10\nИванов И.И.\n- задача")
        assert r.status is ParseStatus.FAILED
        assert "no_days" in codes(r)

    def test_invalid_date_fails(self) -> None:
        r = plan("Спринт 31.02 - 05.03\nИванов И.И.\nПн: 10:00 - 18:00")
        assert r.status is ParseStatus.FAILED
        assert "bad_sprint_dates" in codes(r)

    def test_year_rolls_over_new_year(self) -> None:
        sent = datetime(2026, 12, 27, 8, 0, tzinfo=UTC)
        r = plan("Спринт 28.12 - 02.01\nИванов И.И.\nПн: 10:00 - 18:00\nПт: 10:00 - 18:00", sent)
        assert r.schedule is not None
        assert r.schedule.sprint_start == date(2026, 12, 28)
        assert r.schedule.sprint_end == date(2027, 1, 2)
        assert (r.schedule.iso_year, r.schedule.iso_week) == (2026, 53)
        assert r.schedule.days[-1].date == date(2027, 1, 1)

    def test_sprint_sent_in_january_for_previous_december(self) -> None:
        sent = datetime(2027, 1, 2, 8, 0, tzinfo=UTC)
        r = plan("Спринт 28.12 - 02.01\nИванов И.И.\nПн: 10:00 - 18:00", sent)
        assert r.schedule is not None
        assert r.schedule.sprint_start == date(2026, 12, 28)

    def test_year_uses_team_timezone(self) -> None:
        # 31.12 21:00 UTC — это уже 1 января в Екатеринбурге (+5).
        sent = datetime(2026, 12, 31, 21, 0, tzinfo=UTC)
        r = plan("Спринт 04.01 - 09.01\nИванов И.И.\nПн: 10:00 - 18:00", sent)
        assert r.schedule is not None
        assert r.schedule.sprint_start == date(2027, 1, 4)

    def test_long_sprint_warns(self) -> None:
        r = plan("Спринт 26.10 - 08.11\nИванов И.И.\nПн: 10:00 - 18:00")
        assert "long_sprint" in codes(r)

    def test_day_outside_sprint_is_info(self) -> None:
        r = plan("Спринт 27.10 - 31.10\nИванов И.И.\nПн: 10:00 - 18:00")
        assert "day_outside_sprint" in codes(r)
        assert r.status is ParseStatus.OK


class TestPerson:
    @pytest.mark.parametrize(
        ("line", "surname", "initials"),
        [
            ("Иванов И.И.", "Иванов", "ИИ"),
            ("Иванов И. И.", "Иванов", "ИИ"),
            ("Иванов ИИ", "Иванов", "ИИ"),
            ("иванов и.и.", "Иванов", "ИИ"),
            ("Иванов И.", "Иванов", "И"),
            ("Ёлкина Е.Е.", "Ёлкина", "ЕЕ"),
            ("Петрова-Водкина А.С.", "Петрова-водкина", "АС"),
            ("Иванов Иван Иванович", "Иванов", "ИИ"),
            ("Иванов Иван", "Иванов", "И"),
        ],
    )
    def test_name_variants(self, line: str, surname: str, initials: str) -> None:
        r = plan(f"Спринт 26.10 - 31.10\n{line}\nПн: 10:00 - 18:00")
        assert r.schedule is not None and r.schedule.person is not None
        assert r.schedule.person.surname == surname
        assert r.schedule.person.initials == initials

    def test_key_folds_yo_and_case(self) -> None:
        a = plan("Спринт 26.10 - 31.10\nЁлкина Е.Е.\nПн: 10:00 - 18:00").schedule
        b = plan("Спринт 26.10 - 31.10\nелкина е е\nПн: 10:00 - 18:00").schedule
        assert a is not None and b is not None and a.person and b.person
        assert a.person.key == b.person.key == "елкина ее"

    def test_missing_person_is_warning(self) -> None:
        r = plan("Спринт 26.10 - 31.10\nПн: 10:00 - 18:00")
        assert r.status is ParseStatus.PARTIAL
        assert "no_person" in codes(r)


class TestTasksAndNoise:
    def test_bullet_styles(self) -> None:
        r = plan(
            "Спринт 26.10 - 31.10\nИванов И.И.\nПн: 10:00 - 18:00\n\n"
            "- раз\n— два\n• три\n* четыре\n1. пять\n2) шесть"
        )
        assert r.schedule is not None
        assert r.schedule.tasks == ("раз", "два", "три", "четыре", "пять", "шесть")

    def test_wrapped_task_line_is_joined(self) -> None:
        r = plan(
            "Спринт 26.10 - 31.10\nИванов И.И.\nПн: 10:00 - 18:00\n"
            "- длинная задача,\nпродолжение\n- вторая"
        )
        assert r.schedule is not None
        assert r.schedule.tasks == ("длинная задача, продолжение", "вторая")

    def test_text_under_day_becomes_task(self) -> None:
        """Описание под строкой дня — задача, а не ошибка: так пишут расписание по дням."""
        r = plan("Спринт 26.10 - 31.10\nИванов И.И.\nПн: 10:00 - 18:00\nкакой-то текст\n- задача")
        assert "text_as_task" in codes(r)
        assert r.status is ParseStatus.OK
        assert r.schedule is not None and r.schedule.tasks == ("какой-то текст", "задача")

    def test_garbage_with_time_is_still_warning(self) -> None:
        r = plan("Спринт 26.10 - 31.10\nИванов И.И.\nПн: 10:00 - 18:00\nуйду в 15:30\n")
        assert "unknown_line" in codes(r)
        assert r.status is ParseStatus.PARTIAL

    def test_tasks_header_and_plain_tasks(self) -> None:
        r = plan(
            "Спринт 26.10 - 31.10\nИванов И.И.\nПн: 10:00 - 18:00\n\nЗадачи:\n"
            "первая задача\nвторая задача\n- третья\nпродолжение третьей"
        )
        assert "unknown_line" not in codes(r)
        assert r.schedule is not None
        assert r.schedule.tasks == (
            "первая задача",
            "вторая задача",
            "третья продолжение третьей",
        )

    def test_invisible_chars_and_crlf(self) -> None:
        text = "Спринт 26.10​ - 31.10\r\nИванов И.И.\r\n﻿Пн: 10:00 - 18:00\r\n"
        r = plan(text)
        assert r.status is ParseStatus.OK
        assert day_map(r)[0][1] == "10:00"

    def test_hashtag_inline_with_content(self) -> None:
        r = plan("Спринт 26.10 - 31.10 #расписание\nИванов И.И.\nПн: 10:00 - 18:00")
        assert r.status is ParseStatus.OK
        assert r.hashtags == ("расписание",)

    def test_day_after_tasks_is_still_a_day(self) -> None:
        r = plan("Спринт 26.10 - 31.10\nИванов И.И.\n- задача\nПн: 10:00 - 18:00")
        assert 0 in day_map(r)
        assert "day_after_tasks" in codes(r)

    @pytest.mark.parametrize(
        "text",
        ["", "   ", "привет всем", "Спринт", "🔥🔥🔥", "Спринт 26.10 - 31.10", "#расписание"],
    )
    def test_garbage_never_raises(self, text: str) -> None:
        r = plan(text)
        assert r.status is ParseStatus.FAILED


def test_parse_message_routes_schedule_and_reports_topic_mismatch() -> None:
    r = parse_message(SAMPLE_IVANOV, SENT, TZ, topic_hint=MessageKind.DAILY)
    assert r.kind is MessageKind.SCHEDULE
    assert "topic_mismatch" in codes(r)
    assert r.status is ParseStatus.OK


def test_plan_day_kinds_cover_brief() -> None:
    assert {d.kind for d in plan(SAMPLE_IVANOV).schedule.days} == {  # type: ignore[union-attr]
        PlanDayKind.WORK,
        PlanDayKind.NOTE,
    }
