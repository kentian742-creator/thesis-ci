"""Readings: the measured values that quantitative thesis tests are judged on (SPEC 4.5).

A readings document belongs to one company::

    company: AXP
    as_of: 2026-10-17
    readings:
      - metric: revenue_yoy          # a registry id, a test's metric_def.id, <metric>.<component>,
        period: FY2026Q3             #   or the id of a test whose op: event sub-rule names no metric
        value: 9.8                   # number; true/false for an event; null = checked, nothing to measure
        unit: "%"
        source: AXP-XBRL#us-gaap:RevenuesNetOfInterestExpense:0000004962-26-000400
        basis: optional, how the value was measured
        note: optional (required when value is null)
        segment: optional, matches a test's params.segment
        series: optional, one of several parallel series (for example a holder group)

This module loads and validates such documents, indexes readings for lookup, and converts values between units
of the same kind (``USD`` and ``USD 100 million``, ``RMB`` and ``CNY``).
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from . import contract
from .periods import parse_fiscal
from .repo import is_number, jsonable

CURRENCY_RE = re.compile(r"^([A-Z]{3})(?: (thousand|million|100 million|billion|trillion))?$")
SPELLED_CURRENCY_RE = re.compile(r"^([A-Za-z]{3})(?: (thousand|million|100 million|billion|trillion))?$", re.I)
SCALES = {None: 1.0, "thousand": 1e3, "million": 1e6, "100 million": 1e8, "billion": 1e9, "trillion": 1e12}
CURRENCY_ALIASES = {"RMB": "CNY"}
UNIT_ALIASES = {"×": "x", "times": "x", "percent": "%", "percentage points": "pp", "ppt": "pp"}


def load(path: str | Path) -> dict:
    """Read a readings document from a YAML or JSON file (dates become ISO strings).

    Raises ValueError when the file cannot be read or parsed.
    """
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from None
    try:
        data = json.loads(text) if path.suffix.lower() == ".json" else yaml.safe_load(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise ValueError(f"{path} is not valid {'JSON' if path.suffix.lower() == '.json' else 'YAML'}: {exc}") from None
    return jsonable(data)


def problems(doc: Any) -> list[str]:
    """Why a readings document is not valid: schema violations and repeated readings (empty when valid)."""
    doc = jsonable(doc)
    out = []
    for err in sorted(contract.validator("readings").iter_errors(doc), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "(document)"
        out.append(f"{where}: {err.message}")
    if out:
        return out
    seen: dict[tuple, int] = {}
    for i, r in enumerate(doc["readings"]):
        key = reading_key(r) + (r["period"],)
        if key in seen:
            out.append(f"readings/{i}: repeats readings/{seen[key]} ({describe_key(r)} {r['period']})")
        else:
            seen[key] = i
    return out


def reading_key(reading: dict) -> tuple:
    """(metric, segment, series) of a reading; segment and series are None when absent."""
    return reading.get("metric"), reading.get("segment"), reading.get("series")


def describe_key(reading: dict) -> str:
    text = str(reading.get("metric"))
    if reading.get("segment"):
        text += f" [segment {reading['segment']}]"
    if reading.get("series"):
        text += f" [series {reading['series']}]"
    return text


class Index:
    """Readings grouped by (metric, segment) and period, for the evaluation engine.

    Readings whose period does not parse are ignored (the schema rejects them before this point).
    """

    def __init__(self, readings: list[dict]):
        self._by: dict[tuple, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
        for r in readings:
            if isinstance(r, dict) and isinstance(r.get("metric"), str) and parse_fiscal(r.get("period")):
                self._by[(r["metric"], r.get("segment"))][parse_fiscal(r["period"]).label].append(r)

    def get(self, metric: str, segment: str | None, period: str) -> list[dict]:
        """Every reading of ``metric`` for ``period`` (one per series; empty when there is none)."""
        return list(self._by.get((metric, segment), {}).get(period, []))

    def series(self, metric: str, segment: str | None) -> set[str | None]:
        """The series labels used by the readings of a metric (None stands for readings without one)."""
        return {r.get("series") for rows in self._by.get((metric, segment), {}).values() for r in rows}


def normalize_unit(unit: Any) -> str | None:
    """A canonical spelling of a unit: ``×`` -> ``x``, ``RMB 100 million`` -> ``CNY 100 million``."""
    if not isinstance(unit, str) or not unit.strip():
        return None
    text = " ".join(unit.split())
    text = UNIT_ALIASES.get(text.lower(), text)
    m = SPELLED_CURRENCY_RE.match(text)
    if m and (m.group(1).isupper() or m.group(1).upper() in CURRENCY_ALIASES):
        code = CURRENCY_ALIASES.get(m.group(1).upper(), m.group(1).upper())
        return f"{code} {m.group(2).lower()}" if m.group(2) else code
    return text


def currency(unit: Any) -> tuple[str, float] | None:
    """(ISO code, scale) of a currency unit such as ``USD`` or ``RMB 100 million``; None for other units."""
    norm = normalize_unit(unit)
    m = CURRENCY_RE.match(norm) if norm else None
    return (m.group(1), SCALES[m.group(2)]) if m else None


def compatible(a: Any, b: Any) -> bool:
    """True when a value in unit ``a`` can be expressed in unit ``b``."""
    if normalize_unit(a) is None or normalize_unit(b) is None:
        return False
    if normalize_unit(a) == normalize_unit(b):
        return True
    ca, cb = currency(a), currency(b)
    return ca is not None and cb is not None and ca[0] == cb[0]


def convert(value: float, from_unit: Any, to_unit: Any) -> float | None:
    """``value`` in ``from_unit`` expressed in ``to_unit``; None when the units are of different kinds."""
    if not is_number(value) or not compatible(from_unit, to_unit):
        return None
    if normalize_unit(from_unit) == normalize_unit(to_unit):
        return value
    (_, fa), (_, fb) = currency(from_unit), currency(to_unit)  # type: ignore[misc]
    return value * fa / fb
