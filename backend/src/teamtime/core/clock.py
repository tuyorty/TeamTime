"""Единственное место, где код спрашивает текущее время.

Всё остальное принимает время аргументом или спрашивает здесь, поэтому тесты и демо
управляют «сейчас» без патчей: ``freeze`` фиксирует момент, ``set_offset`` сдвигает часы.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

_offset = timedelta(0)
_frozen: datetime | None = None


def now() -> datetime:
    """Текущий момент в UTC."""
    if _frozen is not None:
        return _frozen
    return datetime.now(UTC) + _offset


def set_offset(delta: timedelta) -> None:
    global _offset
    _offset = delta


def freeze(moment: datetime | None) -> None:
    """Зафиксировать «сейчас» (``None`` — отпустить)."""
    global _frozen
    if moment is not None and moment.tzinfo is None:
        raise ValueError("нужно время с часовым поясом")
    _frozen = moment
