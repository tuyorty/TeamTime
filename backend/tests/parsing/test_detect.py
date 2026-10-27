from __future__ import annotations

import pytest

from teamtime.parsing import MessageKind, detect_kind, parse_message
from tests.parsing.conftest import SENT, TZ


@pytest.mark.parametrize(
    ("text", "hint", "expected"),
    [
        ("Спринт 26.10 - 31.10\nИванов И.И.\nПн: 10:00 - 18:00", None, MessageKind.SCHEDULE),
        ("23.10.2026\n10:00 - 18:00\nЭфф: 80%", None, MessageKind.DAILY),
        ("23.10.2026\n10:00 - 18:00", MessageKind.SCHEDULE, MessageKind.DAILY),
        ("что-то #расписание", None, MessageKind.SCHEDULE),
        ("что-то #дейли", None, MessageKind.DAILY),
        ("что-то #Дейлики", None, MessageKind.DAILY),
        ("23.10.2026 не работал", MessageKind.DAILY, MessageKind.DAILY),
        ("всем привет!", MessageKind.DAILY, MessageKind.UNKNOWN),
        ("всем привет!", MessageKind.SCHEDULE, MessageKind.UNKNOWN),
        ("кто сегодня в офисе?", None, MessageKind.UNKNOWN),
        ("", None, MessageKind.UNKNOWN),
        (
            "03.03.2026\n\n- разобраться с потоками\n\n#дейлиплан",
            MessageKind.DAILY,
            MessageKind.UNKNOWN,
        ),
        ("Иванов И.И.\n18.02.2026\n10:00 - 18:00\n#ДейлиПлан", None, MessageKind.UNKNOWN),
    ],
)
def test_detect_kind(text: str, hint: MessageKind | None, expected: MessageKind) -> None:
    assert detect_kind(text, hint) is expected


def test_unknown_message_has_no_issues() -> None:
    r = parse_message("всем привет", SENT, TZ, topic_hint=MessageKind.DAILY)
    assert r.kind is MessageKind.UNKNOWN
    assert r.issues == ()
