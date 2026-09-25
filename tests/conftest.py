from __future__ import annotations

from pathlib import Path

import pytest

from thesis_ci import engine, selftest


@pytest.fixture
def ws(tmp_path: Path) -> Path:
    """A fresh copy of the clean selftest workspace (public/ and private/)."""
    return selftest.materialize(tmp_path / "ws")


@pytest.fixture
def lint():
    """lint(ws, check_id, side="public", counterpart=True, today=..., **options) -> findings of that check only.

    ``options`` are passed to engine.run (base_ref, period).
    """

    def run(ws: Path, check_id: str, side: str = "public", counterpart: bool = True, today=selftest.TODAY, **options):
        other = "private" if side == "public" else "public"
        report = engine.run(ws / side, ws / other if counterpart else None, today, only=[check_id], **options)
        found = [f for f in report.findings if f.check == check_id]
        assert not any(f.message.startswith(engine.INTERNAL_ERROR) for f in found), found
        return found

    return run
