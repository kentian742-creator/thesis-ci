"""Fiscal periods (FY<year>, FY<year>H<half>, FY<year>Q<quarter>) and whether a thesis test is in force (SPEC 4.1).

Periods follow the company's own fiscal year. ``FY<year>`` is the fiscal year that ends in calendar year ``<year>``
(Microsoft's FY2027 ends on 2027-06-30, so its FY2027Q1 is the quarter to 2026-09-30); this is the SEC's ``fy``
convention for most filers and the one the archives use. A fiscal year end ``MM-DD`` (``filer.fiscal_year_end``) that
is the last day of its month puts every quarter end on the last day of a month.
"""

from __future__ import annotations

import calendar
import datetime as dt
import re
from dataclasses import dataclass
from typing import Any

PERIOD_RE = re.compile(r"^FY(\d{4})Q([1-4])$")
FISCAL_RE = re.compile(r"^FY(\d{4})(?:Q([1-4])|H([12]))?$")
FYE_RE = re.compile(r"^(\d{2})-(\d{2})$")
QUARTERS_PER = {"quarter": 1, "half": 2, "year": 4}


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


def quarter_index(key: tuple[int, int]) -> int:
    """A running count of fiscal quarters, so that quarters can be compared and stepped through."""
    return key[0] * 4 + key[1] - 1


def from_quarter_index(index: int) -> tuple[int, int]:
    return index // 4, index % 4 + 1


@dataclass(frozen=True)
class Fiscal:
    """One fiscal period: a year (``FY2026``), a half (``FY2026H1``) or a quarter (``FY2026Q3``)."""

    year: int
    unit: str  # "year" | "half" | "quarter"
    n: int = 0  # the quarter (1-4) or the half (1-2); 0 for a year

    @property
    def label(self) -> str:
        if self.unit == "quarter":
            return f"FY{self.year}Q{self.n}"
        if self.unit == "half":
            return f"FY{self.year}H{self.n}"
        return f"FY{self.year}"

    def __str__(self) -> str:
        return self.label

    @property
    def end_quarter(self) -> tuple[int, int]:
        """(year, quarter) of the last fiscal quarter in the period."""
        if self.unit == "quarter":
            return self.year, self.n
        if self.unit == "half":
            return self.year, 2 * self.n
        return self.year, 4

    @property
    def start_quarter(self) -> tuple[int, int]:
        """(year, quarter) of the first fiscal quarter in the period."""
        return from_quarter_index(quarter_index(self.end_quarter) - QUARTERS_PER[self.unit] + 1)

    def shift(self, steps: int) -> Fiscal:
        """The period ``steps`` periods of the same kind later (earlier when negative)."""
        end = quarter_index(self.end_quarter) + steps * QUARTERS_PER[self.unit]
        found = period_at(self.unit, from_quarter_index(end))
        assert found is not None  # whole steps keep a half or a year aligned
        return found

    def year_ago(self) -> Fiscal:
        """The same period one fiscal year earlier (FY2026Q3 -> FY2025Q3, FY2026 -> FY2025)."""
        return Fiscal(self.year - 1, self.unit, self.n)


def parse_fiscal(value: Any) -> Fiscal | None:
    """``FY2026`` / ``FY2026H1`` / ``FY2026Q3`` as a Fiscal; None for anything else."""
    m = FISCAL_RE.match(value.strip()) if isinstance(value, str) else None
    if not m:
        return None
    year = int(m.group(1))
    if m.group(2):
        return Fiscal(year, "quarter", int(m.group(2)))
    if m.group(3):
        return Fiscal(year, "half", int(m.group(3)))
    return Fiscal(year, "year")


def period_at(unit: str, end_quarter: tuple[int, int]) -> Fiscal | None:
    """The period of ``unit`` (quarter, half or year) that ends with fiscal quarter ``end_quarter``.

    None when no period of that kind ends there: a year ends only with Q4, a half only with Q2 or Q4.
    """
    year, quarter = end_quarter
    if unit == "quarter":
        return Fiscal(year, "quarter", quarter)
    if unit == "half":
        return Fiscal(year, "half", quarter // 2) if quarter in (2, 4) else None
    if unit == "year":
        return Fiscal(year, "year") if quarter == 4 else None
    raise ValueError(f"unknown period unit {unit!r}")


def fiscal_year_end(value: Any) -> tuple[int, int]:
    """(month, day) of ``filer.fiscal_year_end`` (``MM-DD``); December 31 when it is missing or malformed."""
    m = FYE_RE.match(value.strip()) if isinstance(value, str) else None
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        if 1 <= month <= 12 and 1 <= day <= (29 if month == 2 else calendar.monthrange(2001, month)[1]):
            return month, day
    return 12, 31


def _month_shift(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + month - 1 + delta
    return index // 12, index % 12 + 1


def quarter_end_date(year: int, quarter: int, fye: tuple[int, int]) -> dt.date:
    """The last day of fiscal quarter (year, quarter) for a fiscal year ending on ``fye`` = (month, day)."""
    month, day = fye
    month_end = day >= calendar.monthrange(year, month)[1]
    y, m = _month_shift(year, month, -3 * (4 - quarter))
    last = calendar.monthrange(y, m)[1]
    return dt.date(y, m, last if month_end else min(day, last))


def period_dates(period: Fiscal, fye: tuple[int, int]) -> tuple[dt.date, dt.date]:
    """(first day, last day) of a fiscal period."""
    before = from_quarter_index(quarter_index(period.start_quarter) - 1)
    start = quarter_end_date(*before, fye) + dt.timedelta(days=1)
    return start, quarter_end_date(*period.end_quarter, fye)
