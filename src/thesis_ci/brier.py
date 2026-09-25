"""Brier score and calibration for forecasts/<YYYY>.yml.

BS = mean((p - o)^2) over resolved forecasts only (outcome happened -> o = 1, not_happened -> o = 0);
pending and undetermined forecasts are not scored. 0 is perfect; always saying 50% scores 0.25.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Iterable

import yaml

from .repo import is_number

OUTCOMES = {"happened": 1, "not_happened": 0}
BIN_LABELS = [f"{10 * i}-{10 * (i + 1)}%" for i in range(10)]


def brier_score(pairs: Iterable[tuple[float, int]]) -> float | None:
    pairs = list(pairs)
    if not pairs:
        return None
    return sum((p - o) ** 2 for p, o in pairs) / len(pairs)


def bin_index(p: float) -> int:
    return min(9, max(0, math.floor(p * 10 + 1e-9)))


def calibration(pairs: Iterable[tuple[float, int]]) -> list[dict]:
    """Ten bins (0-10%, ..., 90-100%): count, mean forecast probability, observed frequency."""
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(10)]
    for p, o in pairs:
        buckets[bin_index(p)].append((p, o))
    out = []
    for label, items in zip(BIN_LABELS, buckets):
        n = len(items)
        out.append({
            "bin": label,
            "n": n,
            "mean_p": sum(p for p, _ in items) / n if n else None,
            "observed": sum(o for _, o in items) / n if n else None,
        })
    return out


def _block(pairs: list[tuple[float, int]]) -> dict:
    return {"n": len(pairs), "brier": brier_score(pairs), "calibration": calibration(pairs)}


def summarize(records: Iterable[dict]) -> dict:
    records = list(records)
    resolved = []
    for rec in records:
        p, outcome = rec.get("probability"), rec.get("outcome")
        if is_number(p) and 0 <= p <= 1 and isinstance(outcome, str) and outcome in OUTCOMES:
            resolved.append((float(p), OUTCOMES[outcome], str(rec.get("domain") or "other"), str(rec.get("book") or "system")))
    by_domain: dict[str, list] = {}
    by_book: dict[str, list] = {}
    for p, o, domain, book in resolved:
        by_domain.setdefault(domain, []).append((p, o))
        by_book.setdefault(book, []).append((p, o))
    return {
        "n_forecasts": len(records),
        "n_resolved": len(resolved),
        "overall": _block([(p, o) for p, o, _d, _b in resolved]),
        "by_domain": {k: _block(v) for k, v in sorted(by_domain.items())},
        "by_book": {k: _block(v) for k, v in sorted(by_book.items())},
    }


def load_records(paths: Iterable[str | Path]) -> list[dict]:
    records: list[dict] = []
    for path in paths:
        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        items = data.get("forecasts") if isinstance(data, dict) else None
        if not isinstance(items, list):
            raise ValueError(f"{path}: expected a forecasts file with a 'forecasts' list")
        records.extend(r for r in items if isinstance(r, dict))
    return records


def _fmt(x: float | None, pct: bool = False) -> str:
    if x is None:
        return "-"
    return f"{x:.0%}" if pct else f"{x:.4f}"


def format_text(summary: dict) -> str:
    lines = [f"forecasts: {summary['n_forecasts']}, resolved: {summary['n_resolved']}"]
    groups = [("overall", {"all": summary["overall"]})]
    groups += [("domain", summary["by_domain"]), ("book", summary["by_book"])]
    for kind, blocks in groups:
        for name, block in blocks.items():
            label = "overall" if kind == "overall" else f"{kind} {name}"
            lines.append(f"\n{label}: n={block['n']} brier={_fmt(block['brier'])}")
            for b in block["calibration"]:
                if b["n"]:
                    lines.append(f"  {b['bin']:>8}  n={b['n']:<4} said {_fmt(b['mean_p'], True):>4}  happened {_fmt(b['observed'], True):>4}")
    if not summary["n_resolved"]:
        lines.append("\nno resolved forecasts yet: nothing to score")
    return "\n".join(lines)
