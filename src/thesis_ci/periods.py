"""Fiscal periods (FY<year>Q<quarter>) and whether a thesis test is in force (SPEC 4.1)."""

from __future__ import annotations

import re
from typing import Any

PERIOD_RE = re.compile(r"^FY(\d{4})Q([1-4])$")


def period_key(value: Any) -> tuple[int, int] | None:
    """(year, quarter) of a period such as FY2027Q1; None when the value is not a period."""
    m = PERIOD_RE.match(value.strip()) if isinstance(value, str) else None
    return (int(m.group(1)), int(m.group(2))) if m else None


def is_period(value: Any) -> bool:
    return period_key(value) is not None


def retired(test: dict, period: str | None = None) -> bool:
    """A test with retired_at is retired; with a current period, only once that period reaches retired_at."""
    end = test.get("retired_at")
    if end is None:
        return False
    now, stop = period_key(period), period_key(end)
    if now is not None and stop is not None:
        return stop <= now
    return True


def in_force_for(test: dict, period: str) -> bool:
    """True when the test is judged in ``period``: effective_from <= period < retired_at.

    A test without effective_from (written before the field existed) counts as in force from the start.
    """
    now = period_key(period)
    if now is None:
        return False
    start = period_key(test.get("effective_from"))
    if start is not None and start > now:
        return False
    return not retired(test, period)
