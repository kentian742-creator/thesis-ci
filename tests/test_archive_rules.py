"""Every rule shape used by the real archives is understood by the evaluation engine (SPEC 4.5).

Two sources, so that the check runs everywhere:

- the live archives, when a checkout of owners-office sits next to thesis-ci (or ``THESIS_CI_ARCHIVE`` points at one);
- ``fixtures/archive_rules.yml``, a snapshot of the quantitative tests of those archives (only the fields the engine
  reads), which always runs. Refresh it with ``python tests/test_archive_rules.py <path to owners-office>``.

An unsupported shape fails the test; it is never skipped.
"""

from __future__ import annotations

import datetime as dt
import os
import sys
from pathlib import Path

import pytest
import yaml

from thesis_ci import contract, evaluate

HERE = Path(__file__).resolve().parent
SNAPSHOT = HERE / "fixtures" / "archive_rules.yml"
LIVE = Path(os.environ.get("THESIS_CI_ARCHIVE") or HERE.parent.parent / "owners-office")
KEEP = ("id", "type", "metric", "params", "rule", "warn_rule", "data", "effective_from", "retired_at", "supersedes")
KEEP_DEF = ("id", "unit", "frequency", "data", "xbrl", "formula")
PERIODS = ["FY2026Q3", "FY2026Q4", "FY2027Q1", "FY2027Q2", "FY2028Q4"]


def _strip_notes(rule):
    if isinstance(rule, dict):
        return {k: _strip_notes(v) for k, v in rule.items() if k != "note"}
    if isinstance(rule, list):
        return [_strip_notes(v) for v in rule]
    return rule


def snapshot(archive: Path) -> dict:
    """The quantitative tests of every companies/*/thesis.yml, reduced to the fields the engine reads."""
    companies = {}
    for path in sorted(archive.glob("companies/*/thesis.yml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        tests = []
        for test in data.get("tests") or []:
            if test.get("type") != "quantitative":
                continue
            slim = {k: _strip_notes(test[k]) for k in KEEP if k in test}
            if isinstance(test.get("metric_def"), dict):
                md = test["metric_def"]
                slim["metric_def"] = {k: md[k] for k in KEEP_DEF if k in md}
                if isinstance(md.get("components"), dict):
                    slim["metric_def"]["components"] = {
                        name: {k: v for k, v in comp.items() if k in ("unit", "xbrl")}
                        for name, comp in md["components"].items()}
                slim["metric_def"].setdefault("description", "(omitted)")
            tests.append(slim)
        companies[data["company"]] = {"company": data["company"], "filer": data.get("filer"), "tests": tests}
    return companies


def _cases(companies: dict) -> list:
    return [pytest.param(c, t, id=t["id"]) for c in companies.values() for t in c["tests"]]


def _check(company: dict, test: dict) -> None:
    assert evaluate.shape_problems(test) == [], f"{test['id']}: the engine does not understand this rule"
    for period in PERIODS:
        doc = evaluate.evaluate_company({**company, "tests": [test]}, [], period, dt.date(2030, 1, 1))
        results = doc["results"]
        if results:
            assert results[0]["result"] in ("undetermined", "not_due", "pass"), results[0]
            assert not results[0]["reason"].startswith("rule not understood"), results[0]["reason"]
        assert [e.message for e in contract.validator("ci-results").iter_errors(doc)] == []
        evaluate.needed_readings({**company, "tests": [test]}, period)


SNAPSHOT_COMPANIES = yaml.safe_load(SNAPSHOT.read_text(encoding="utf-8")) if SNAPSHOT.is_file() else {}


def test_snapshot_covers_the_six_archives():
    assert set(SNAPSHOT_COMPANIES) == {"APP", "AXP", "BRK", "MSFT", "PDD", "SPGI"}
    assert sum(len(c["tests"]) for c in SNAPSHOT_COMPANIES.values()) >= 90


@pytest.mark.parametrize("company,test", _cases(SNAPSHOT_COMPANIES))
def test_snapshot_rules_are_understood(company, test):
    _check(company, test)


def _live() -> dict:
    return snapshot(LIVE) if (LIVE / "companies").is_dir() else {}


LIVE_COMPANIES = _live()


@pytest.mark.skipif(not LIVE_COMPANIES, reason="no owners-office checkout next to thesis-ci (the snapshot still runs)")
@pytest.mark.parametrize("company,test", _cases(LIVE_COMPANIES))
def test_live_archive_rules_are_understood(company, test):
    _check(company, test)


def test_the_shapes_the_archives_use_are_all_present_in_the_snapshot():
    """Guards the snapshot itself: it must keep the rule shapes that made the engine's semantics necessary."""
    tests = {t["id"]: t for c in SNAPSHOT_COMPANIES.values() for t in c["tests"]}
    ops = set()

    def walk(rule):
        if "op" in rule:
            ops.add(rule["op"])
        for key in ("all_of", "any_of"):
            for sub in rule.get(key, []):
                walk(sub)

    for t in tests.values():
        for key in ("rule", "warn_rule"):
            if key in t:
                walk(t[key])
    assert ops == {"<", "<=", ">", ">=", "==", "decrease", "increase", "event", "outside"}
    assert tests["AXP-Q13"]["rule"]["consecutive"] == 3 and "all_of" in tests["AXP-Q13"]["rule"]  # shared consecutive
    assert tests["AXP-Q14"]["rule"]["period"] == "half"
    assert "evaluate_from" in tests["MSFT-Q4"]["rule"] and "evaluate_on" in tests["APP-Q13"]["rule"]
    assert tests["PDD-Q15"]["params"]["holders"]  # series
    assert tests["BRK-Q10"]["params"]["segment"] == "GEICO"  # segment


if __name__ == "__main__":
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else LIVE
    header = ("# Snapshot of the quantitative tests of the owners-office archives (companies/*/thesis.yml), reduced to\n"
              "# the fields the evaluation engine reads. Regenerate: python tests/test_archive_rules.py <owners-office>\n")
    SNAPSHOT.parent.mkdir(exist_ok=True)
    SNAPSHOT.write_text(header + yaml.safe_dump(snapshot(root), sort_keys=False, allow_unicode=True, width=120),
                        encoding="utf-8")
    print(f"wrote {SNAPSHOT}")
