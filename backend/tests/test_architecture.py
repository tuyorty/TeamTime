"""Границы слоёв (ADR 0001): parsing и calc — чистые, без базы, сети и фреймворков."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src" / "teamtime"
FORBIDDEN = ("sqlalchemy", "fastapi", "aiogram", "httpx", "asyncpg", "teamtime.db",
             "teamtime.services", "teamtime.api", "teamtime.bot")  # fmt: skip


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.mark.parametrize("package", ["parsing", "calc"])
def test_pure_packages_do_not_import_infrastructure(package: str) -> None:
    for path in (SRC / package).rglob("*.py"):
        bad = {n for n in _imports(path) if n.startswith(FORBIDDEN)}
        assert not bad, f"{path.relative_to(SRC)} импортирует {bad}"
