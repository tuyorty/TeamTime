"""Единственное место, где код спрашивает текущее время.

Всё остальное принимает время аргументом, поэтому тесты и демо управляют «сейчас»
без патчей. В демо-режиме время можно сдвинуть через ``set_offset``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

_offset = timedelta(0)


def now() -> datetime:
    """Текущий момент в UTC (с учётом демо-сдвига)."""
    return datetime.now(UTC) + _offset


def set_offset(delta: timedelta) -> None:
    global _offset
    _offset = delta
