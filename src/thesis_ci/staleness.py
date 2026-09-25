"""Staleness tests (SPEC 4.1): a section fails when reviewed.<section> is older than max_age_quarters x 91 days.

Retired tests (retired_at set) are records only and are not evaluated.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .periods import retired
from .repo import Repo, is_number

QUARTER_DAYS = 91


@dataclass
class StalenessResult:
    company: str
    test: str
    section: str | None
    reviewed: str | None
    age_days: int | None
    limit_days: int | None
    result: str  # pass | fail | undetermined
    note: str = ""
    index: int = 0

    def as_dict(self) -> dict:
        out = asdict(self)
        out.pop("index")
        return out


def to_date(value: Any) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def evaluate(thesis: dict, today: dt.date) -> list[StalenessResult]:
    company = str(thesis.get("company") or "?")
    reviewed = thesis.get("reviewed") if isinstance(thesis.get("reviewed"), dict) else {}
    tests = thesis.get("tests") if isinstance(thesis.get("tests"), list) else []
    out = []
    for i, test in enumerate(tests):
        if not isinstance(test, dict) or test.get("type") != "staleness" or retired(test):
            continue
        section, quarters = test.get("section"), test.get("max_age_quarters")
        raw = reviewed.get(section) if isinstance(section, str) else None
        date = to_date(raw)
        res = StalenessResult(company, str(test.get("id")), section, date.isoformat() if date else None,
                              None, None, "undetermined", index=i)
        if not (is_number(quarters) and int(quarters) == quarters and quarters >= 1):
            res.note = "max_age_quarters must be a positive integer"
        elif date is None:
            res.note = f"reviewed.{section} has no valid date"
        else:
            res.age_days = (today - date).days
            res.limit_days = int(quarters) * QUARTER_DAYS
            if res.age_days < 0:
                res.note = f"reviewed.{section} is in the future"
            else:
                res.result = "fail" if res.age_days > res.limit_days else "pass"
        out.append(res)
    return out


def evaluate_repo(root: str | Path, today: dt.date) -> list[StalenessResult]:
    repo = Repo(root)
    results: list[StalenessResult] = []
    for path in repo.files("companies/*/thesis.yml"):
        data = repo.doc(path).mapping
        if data:
            results.extend(evaluate(data, today))
    return results
