"""The check registry, the spec files and the selftest agree with each other."""

from __future__ import annotations

import ast
from pathlib import Path

import jsonschema
import pytest

from thesis_ci import contract, engine, selftest
from thesis_ci.checks.thesis_tests import rule_problems
from thesis_ci.evaluate import shape_problems

TESTS_DIR = Path(__file__).parent


def test_registry_ids_equal_checks_yml_ids():
    """Every id in spec/checks.yml is implemented, and nothing else is registered."""
    registered = set(engine.load_checks())
    listed = [m["id"] for m in contract.registered_checks()]
    assert len(listed) == len(set(listed)), "duplicate ids in checks.yml"
    assert registered == set(listed)


def test_checks_yml_entries_are_well_formed():
    for meta in contract.registered_checks():
        assert meta["scope"] in {"public", "private", "both", "workspace"}, meta
        assert meta["level"] in {"error", "warning"}, meta
        assert meta["title"] and meta["description"], meta


def test_every_check_has_violating_fixtures():
    with_cases = {c.check for c in selftest.CASES}
    assert with_cases == {m["id"] for m in contract.registered_checks()}


def test_every_check_has_a_unit_test_naming_it():
    """SPEC section 8: a unit test whose name or docstring contains the check id exists for every check."""
    texts = []
    for path in TESTS_DIR.glob("test_*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                texts.append(node.name.upper().replace("_", "-") + " " + (ast.get_docstring(node) or ""))
    for meta in contract.registered_checks():
        assert any(meta["id"] in t for t in texts), f"no unit test mentions {meta['id']}"


@pytest.mark.parametrize("name", contract.schema_names())
def test_schemas_are_valid_draft_2020_12(name):
    jsonschema.Draft202012Validator.check_schema(contract.schema(name))


def test_spec_directory_found():
    spec = contract.spec_dir()
    assert (spec / "checks.yml").is_file()
    assert (spec / "schemas" / "thesis.schema.json").is_file()
    assert (spec / "templates" / "lynch" / "stalwart.yml").is_file()


def test_metrics_registry_is_well_formed():
    for mid, metric in contract.metrics().items():
        assert metric["data"] in {"xbrl", "filing_text"}, mid
        if metric["data"] == "xbrl":
            assert metric.get("xbrl"), f"{mid}: xbrl metric without concepts"


@pytest.mark.parametrize("category", ["slow_grower", "stalwart", "fast_grower", "cyclical", "turnaround", "asset_play"])
def test_lynch_templates_are_executable(category):
    """Template quantitative tests use registered metrics and machine-readable rules (C-TEST-METRIC)."""
    template = contract.template(category)
    assert template["category"] == category
    for test in template["tests"]:
        if test["type"] == "quantitative":
            metric = contract.metrics()[test["metric"]]
            assert test["data"] == metric["data"], test["key"]
            assert rule_problems(test["rule"]) == [], test["key"]
            if "warn_rule" in test:
                assert rule_problems(test["warn_rule"]) == [], test["key"]
            assert shape_problems({**test, "id": "X-Q1"}) == [], test["key"]  # the evaluation engine can judge it
        elif test["type"] == "qualitative":
            assert test["question"] and test["fail_if"], test["key"]
            assert test["where"] and isinstance(test["lookback"], int) and test["lookback"] >= 1, test["key"]


def test_common_template_staleness_sections():
    """C-STALENESS: the shared staleness tests watch moat and management (4 quarters) and bear_case (2 quarters)."""
    common = {t["key"]: t for t in contract.template("_common")["tests"]}
    assert {k: (t["section"], t["max_age_quarters"]) for k, t in common.items()} == {
        "S-moat": ("moat", 4), "S-management": ("management", 4), "S-bear_case": ("bear_case", 2)}
    sections = contract.schema("thesis")["properties"]["reviewed"]["properties"]
    assert all(t["section"] in sections for t in common.values())


def test_selftest_all_pass():
    results = selftest.run_all()
    assert [r.check for r in results if not r.passed] == []
    assert all(r.cases >= 1 or r.skipped for r in results)  # C-TEST-FROZEN's cases need git
