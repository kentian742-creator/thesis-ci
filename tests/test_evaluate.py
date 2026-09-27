"""The evaluation engine (SPEC 4.5): quantitative thesis tests + readings -> ci_results."""

from __future__ import annotations

import datetime as dt

import pytest

from thesis_ci import contract, evaluate
from thesis_ci.evaluate import evaluate_company, needed_readings, shape_problems

TODAY = dt.date(2026, 12, 1)
AFTER_FY2026 = dt.date(2027, 3, 1)


def quant(tid: str = "ACME-Q1", **fields) -> dict:
    """A quantitative test; the defaults are a registry metric and a two-quarter rule."""
    test = {"id": tid, "type": "quantitative", "claim": "a claim", "origin": "manual", "severity": "breaker",
            "covers": ["growth"], "metric": "revenue_yoy", "fail_if": "below 5% for 2 consecutive quarters",
            "rule": {"op": "<", "threshold": 5, "unit": "%", "consecutive": 2, "period": "quarter"},
            "data": "xbrl", "effective_from": "FY2026Q1"}
    test.update(fields)
    return test


def thesis(*tests: dict, fye: str = "12-31") -> dict:
    return {"company": "ACME", "filer": {"cik": "0000000001", "type": "domestic", "fiscal_year_end": fye},
            "tests": list(tests)}


def R(metric: str, period: str, value, unit: str = "%", **extra) -> dict:
    return {"metric": metric, "period": period, "value": value, "unit": unit, "source": f"ACME-XBRL#{metric}", **extra}


def run(tests, readings, period="FY2026Q3", today=TODAY, fye="12-31") -> dict:
    tests = tests if isinstance(tests, list) else [tests]
    return evaluate_company(thesis(*tests, fye=fye), readings, period, today)


def one(tests, readings, period="FY2026Q3", **kw) -> dict:
    doc = run(tests, readings, period, **kw)
    assert len(doc["results"]) == 1, doc
    return doc["results"][0]


def schema_errors(doc: dict) -> list[str]:
    return [e.message for e in contract.validator("ci-results").iter_errors(doc)]


# --- comparisons and consecutive windows


def test_consecutive_window_fails_only_when_every_period_holds():
    result = one(quant(), [R("revenue_yoy", "FY2026Q3", 3.0), R("revenue_yoy", "FY2026Q2", 4.9)])
    assert result["result"] == "fail"
    assert result["consecutive_count"] == 2 and result["consecutive"] == 2
    assert result["reading"] == R("revenue_yoy", "FY2026Q3", 3.0)
    assert [r["period"] for r in result["readings"]] == ["FY2026Q2", "FY2026Q3"]
    assert result["threshold"] == 5 and result["op"] == "<" and result["unit"] == "%"
    assert result["fail_if"] == "below 5% for 2 consecutive quarters"
    assert "fail rule triggered" in result["reason"]


def test_broken_streak_passes_and_counts_the_run():
    result = one(quant(), [R("revenue_yoy", "FY2026Q3", 3.0), R("revenue_yoy", "FY2026Q2", 6.0)])
    assert result["result"] == "pass"
    assert result["consecutive_count"] == 1
    assert result["missing"] == []


def test_current_period_not_holding_decides_without_older_readings():
    """Three-valued logic: a window with one period that does not hold is not triggered, whatever is missing."""
    result = one(quant(), [R("revenue_yoy", "FY2026Q3", 8.0)])
    assert result["result"] == "pass" and result["missing"] == []


def test_a_run_whose_latest_period_is_unread_is_undetermined():
    """An earlier period that breaks the run does not stand in for this period's missing reading."""
    result = one(quant(), [R("revenue_yoy", "FY2026Q2", 9.0)])
    assert result["result"] == "undetermined"
    assert result["missing"] == [{"metric": "revenue_yoy", "period": "FY2026Q3", "rule": "rule"}]


def test_missing_reading_is_undetermined_and_named():
    result = one(quant(), [R("revenue_yoy", "FY2026Q3", 3.0)])
    assert result["result"] == "undetermined"
    assert result["missing"] == [{"metric": "revenue_yoy", "period": "FY2026Q2", "rule": "rule"}]
    assert "missing readings: revenue_yoy FY2026Q2" in result["reason"]


def test_no_readings_at_all_is_undetermined_never_guessed():
    result = one(quant(), [])
    assert result["result"] == "undetermined" and result["reading"] is None and result["readings"] == []
    assert {m["period"] for m in result["missing"]} == {"FY2026Q3", "FY2026Q2"}


@pytest.mark.parametrize("op,threshold,value,expected", [
    ("<", 5, 5, "pass"), ("<=", 5, 5, "fail"), (">", 5, 5, "pass"), (">=", 5, 5, "fail"),
    ("==", 0, 0, "fail"), ("!=", 0, 0, "pass"),
    ("between", [0, 10], 10, "fail"), ("between", [0, 10], 10.5, "pass"),
    ("outside", [-10, 15], -10, "pass"), ("outside", [-10, 15], 16, "fail"),
])
def test_comparison_ops(op, threshold, value, expected):
    test = quant(rule={"op": op, "threshold": threshold, "unit": "%", "consecutive": 1, "period": "quarter"})
    assert one(test, [R("revenue_yoy", "FY2026Q3", value)])["result"] == expected


# --- warn_rule


def test_warn_is_judged_only_when_fail_is_not_triggered():
    test = quant(warn_if="below 8%", warn_rule={"op": "<", "threshold": 8, "unit": "%", "consecutive": 1, "period": "quarter"})
    failed = one(test, [R("revenue_yoy", "FY2026Q3", 3.0), R("revenue_yoy", "FY2026Q2", 4.0)])
    assert failed["result"] == "fail" and failed["evaluation"]["warn"] is None
    warned = one(test, [R("revenue_yoy", "FY2026Q3", 7.0), R("revenue_yoy", "FY2026Q2", 4.0)])
    assert warned["result"] == "warn" and warned["warn_if"] == "below 8%"
    assert warned["evaluation"]["warn"]["state"] == "triggered"
    passed = one(test, [R("revenue_yoy", "FY2026Q3", 9.0)])
    assert passed["result"] == "pass"


def test_undetermined_warn_rule_makes_the_test_undetermined():
    test = quant(rule={"op": "<", "threshold": 5, "unit": "%", "consecutive": 1, "period": "quarter"},
                 warn_rule={"op": "<", "threshold": 8, "unit": "%", "consecutive": 2, "period": "quarter"})
    result = one(test, [R("revenue_yoy", "FY2026Q3", 7.0)])
    assert result["result"] == "undetermined"
    assert result["missing"] == [{"metric": "revenue_yoy", "period": "FY2026Q2", "rule": "warn_rule"}]
    assert result["reason"].startswith("warn_rule undetermined")


# --- increase / decrease


def test_decrease_in_pp_compares_with_the_same_quarter_a_year_earlier():
    """APP-Q2 / the fast_grower template: "down more than 5 percentage points year on year"."""
    test = quant(metric="operating_margin", rule={"op": "decrease", "threshold": 5, "unit": "pp", "consecutive": 1,
                                                  "period": "quarter"})
    readings = [R("operating_margin", "FY2026Q3", 70.0), R("operating_margin", "FY2026Q2", 50.0),
                R("operating_margin", "FY2025Q3", 76.0)]
    result = one(test, readings)
    assert result["result"] == "fail"  # 76 -> 70 year on year; the rise from Q2 is irrelevant
    window = result["evaluation"]["fail"]["window"][0]
    assert window["base"]["period"] == "FY2025Q3" and window["change"] == pytest.approx(-6.0)
    assert one(test, readings[:2] + [R("operating_margin", "FY2025Q3", 74.0)])["result"] == "pass"  # -4 pp


def test_decrease_needs_more_than_the_threshold():
    test = quant(metric="operating_margin", rule={"op": "decrease", "threshold": 0, "unit": "pp", "consecutive": 1,
                                                  "period": "quarter"})
    assert one(test, [R("operating_margin", "FY2026Q3", 40), R("operating_margin", "FY2025Q3", 40)])["result"] == "pass"


def test_decrease_in_percent_of_an_amount_is_relative():
    """PDD-Q7: merchant float (RMB 100 million) down year on year, threshold 0 in %."""
    md = {"id": "merchant_float", "description": "x", "unit": "RMB 100 million", "frequency": "quarter", "data": "filing_text"}
    test = quant(metric=None, metric_def=md, data="filing_text",
                 rule={"op": "decrease", "threshold": 10, "unit": "%", "consecutive": 1, "period": "quarter"})
    del test["metric"]
    fall = [R("merchant_float", "FY2026Q3", 880, "RMB 100 million"), R("merchant_float", "FY2025Q3", 1000, "RMB 100 million")]
    result = one(test, fall)
    assert result["result"] == "fail" and result["evaluation"]["fail"]["window"][0]["change"] == pytest.approx(-12.0)
    mixed_units = [R("merchant_float", "FY2026Q3", 95_000_000_000, "CNY"), R("merchant_float", "FY2025Q3", 1000, "RMB 100 million")]
    assert one(test, mixed_units)["result"] == "pass"  # -5% after converting to one unit


def test_increase_by_year_for_a_year_rule():
    test = quant(metric="provision_for_credit_losses",
                 rule={"op": "increase", "threshold": 50, "unit": "%", "consecutive": 1, "period": "year"})
    readings = [R("provision_for_credit_losses", "FY2026", 160, "USD"), R("provision_for_credit_losses", "FY2025", 100, "USD")]
    assert one(test, readings, period="FY2026Q4", today=AFTER_FY2026)["result"] == "fail"


def test_decrease_without_the_year_earlier_reading_is_undetermined():
    test = quant(metric="operating_margin", rule={"op": "decrease", "threshold": 0, "unit": "pp", "consecutive": 1,
                                                  "period": "quarter"})
    result = one(test, [R("operating_margin", "FY2026Q3", 40), R("operating_margin", "FY2026Q2", 45)])
    assert result["result"] == "undetermined"
    assert result["missing"] == [{"metric": "operating_margin", "period": "FY2025Q3", "rule": "rule"}]


# --- components, all_of / any_of


COMPONENTS = {"id": "drivers", "description": "x", "unit": "%", "frequency": "quarter", "data": "filing_text",
              "components": {"installs": {"description": "x", "unit": "%"},
                             "price": {"description": "x", "unit": "%"}}}


def drivers_test(rule: dict) -> dict:
    test = quant(metric_def=COMPONENTS, data="filing_text", rule=rule)
    del test["metric"]
    return test


def test_components_by_full_and_bare_name():
    rule = {"all_of": [{"metric": "drivers.installs", "op": "<", "threshold": 0, "unit": "%", "period": "quarter"},
                       {"metric": "price", "op": "<", "threshold": 30, "unit": "%", "period": "quarter"}]}
    readings = [R("drivers.installs", "FY2026Q3", -2), R("drivers.price", "FY2026Q3", 20)]
    result = one(drivers_test(rule), readings)
    assert result["result"] == "fail"
    assert result["op"] is None if "op" in result else True
    assert result["consecutive"] is None and result["consecutive_count"] is None
    assert [c["metric"] for c in result["evaluation"]["fail"]["children"]] == ["drivers.installs", "drivers.price"]


def test_all_of_is_not_triggered_by_one_known_false_whatever_is_missing():
    rule = {"all_of": [{"metric": "drivers.installs", "op": "<", "threshold": 0, "unit": "%", "period": "quarter"},
                       {"metric": "drivers.price", "op": "<", "threshold": 30, "unit": "%", "period": "quarter"}]}
    assert one(drivers_test(rule), [R("drivers.installs", "FY2026Q3", 5)])["result"] == "pass"
    assert one(drivers_test(rule), [R("drivers.installs", "FY2026Q3", -5)])["result"] == "undetermined"


def test_any_of_is_triggered_by_one_known_true_whatever_is_missing():
    rule = {"any_of": [{"metric": "drivers.installs", "op": "<", "threshold": 0, "unit": "%", "period": "quarter"},
                       {"metric": "drivers.price", "op": "<", "threshold": 30, "unit": "%", "period": "quarter"}]}
    assert one(drivers_test(rule), [R("drivers.installs", "FY2026Q3", -5)])["result"] == "fail"
    assert one(drivers_test(rule), [R("drivers.installs", "FY2026Q3", 5)])["result"] == "undetermined"


def test_shared_consecutive_asks_the_combination_to_hold_in_the_same_periods():
    """AXP-Q13 / MSFT-Q5: consecutive on all_of = both hold in the same quarter, N quarters running."""
    rule = {"all_of": [{"metric": "drivers.installs", "op": "<", "threshold": 0, "unit": "%"},
                       {"metric": "drivers.price", "op": ">", "threshold": 0, "unit": "%"}],
            "consecutive": 2, "period": "quarter"}
    both = [R("drivers.installs", "FY2026Q3", -1), R("drivers.price", "FY2026Q3", 1),
            R("drivers.installs", "FY2026Q2", -1), R("drivers.price", "FY2026Q2", 1)]
    result = one(drivers_test(rule), both)
    assert result["result"] == "fail" and result["consecutive"] == 2 and result["consecutive_count"] == 2
    assert [w["period"] for w in result["evaluation"]["fail"]["window"]] == ["FY2026Q3", "FY2026Q2"]
    broken = both[:3] + [R("drivers.price", "FY2026Q2", -1)]
    assert one(drivers_test(rule), broken)["result"] == "pass"


def test_shared_consecutive_on_any_of_differs_from_consecutive_on_each_branch():
    shared = {"any_of": [{"metric": "drivers.installs", "op": "<", "threshold": 0, "unit": "%"},
                         {"metric": "drivers.price", "op": "<", "threshold": 0, "unit": "%"}],
              "consecutive": 2, "period": "quarter"}
    per_branch = {"any_of": [{"metric": "drivers.installs", "op": "<", "threshold": 0, "unit": "%", "consecutive": 2},
                             {"metric": "drivers.price", "op": "<", "threshold": 0, "unit": "%", "consecutive": 2}],
                  "period": "quarter"}
    alternating = [R("drivers.installs", "FY2026Q3", -1), R("drivers.price", "FY2026Q3", 1),
                   R("drivers.installs", "FY2026Q2", 1), R("drivers.price", "FY2026Q2", -1)]
    assert one(drivers_test(shared), alternating)["result"] == "fail"
    assert one(drivers_test(per_branch), alternating)["result"] == "pass"


def test_nested_any_of_inside_all_of():
    """AXP-Q8: all_of[any_of[decrease, below], component > 0], judged by year."""
    rule = {"all_of": [{"any_of": [{"metric": "drivers", "op": "decrease", "threshold": 0.05, "unit": "pp",
                                    "consecutive": 2, "period": "year"},
                                   {"metric": "drivers", "op": "<", "threshold": 2.15, "unit": "%", "period": "year"}]},
                       {"metric": "drivers.installs", "op": ">", "threshold": 0, "unit": "%", "period": "year"}]}
    readings = [R("drivers", "FY2026", 2.10), R("drivers.installs", "FY2026", 3)]
    assert one(drivers_test(rule), readings, period="FY2026Q4", today=AFTER_FY2026)["result"] == "fail"
    assert one(drivers_test(rule), readings, period="FY2026Q3")["result"] == "not_due"


# --- periods: not_due, evaluate_on, evaluate_from


def test_annual_test_is_not_due_outside_the_fiscal_fourth_quarter():
    test = quant(metric="roe", rule={"op": "<", "threshold": 12, "unit": "%", "consecutive": 2, "period": "year"})
    result = one(test, [R("roe", "FY2025", 10)])
    assert result["result"] == "not_due"
    assert "judged by year, only when a fiscal year ends (Q4)" in result["reason"]
    assert result["evaluation"]["fail"]["state"] == "not_due"
    annual = one(test, [R("roe", "FY2026", 10), R("roe", "FY2025", 11)], period="FY2026Q4", today=AFTER_FY2026)
    assert annual["result"] == "fail" and annual["reading"]["period"] == "FY2026"


def test_half_rule_reads_the_half_ending_with_the_quarter():
    """AXP-Q14: period half, judged in FY2027Q2 on the first half of 2027."""
    test = quant(rule={"op": "<", "threshold": 8.5, "unit": "%", "consecutive": 1, "period": "half",
                       "evaluate_on": ["FY2027Q2"]})
    assert one(test, [R("revenue_yoy", "FY2027H1", 7.9)], period="FY2027Q2", today=dt.date(2027, 8, 1))["result"] == "fail"
    assert one(test, [], period="FY2026Q4")["result"] == "not_due"
    assert one(test, [], period="FY2027Q1", today=dt.date(2027, 8, 1))["result"] == "not_due"


def test_evaluate_on_a_year_matches_every_quarter_of_that_year():
    test = quant(rule={"op": "<", "threshold": 5, "unit": "%", "period": "quarter", "evaluate_on": ["FY2026"]})
    assert one(test, [R("revenue_yoy", "FY2026Q3", 1)])["result"] == "fail"
    assert one(test, [R("revenue_yoy", "FY2027Q1", 1)], period="FY2027Q1", today=dt.date(2027, 6, 1))["result"] == "not_due"


def test_evaluate_from_starts_the_consecutive_count():
    """MSFT-Q4: from FY2027, two consecutive years not above 52%; FY2026 does not count toward the run."""
    test = quant(metric="fcf_to_non_gaap_net_income", data="filing_text",
                 rule={"op": "<=", "threshold": 52, "unit": "%", "consecutive": 2, "period": "year",
                       "evaluate_from": "FY2027"},
                 warn_rule={"op": "<=", "threshold": 52, "unit": "%", "consecutive": 1, "period": "year",
                            "evaluate_from": "FY2027"})
    readings = [R("fcf_to_non_gaap_net_income", "FY2027", 50), R("fcf_to_non_gaap_net_income", "FY2026", 51)]
    first = one(test, readings, period="FY2027Q4", today=dt.date(2028, 8, 1))
    assert first["result"] == "warn"
    assert first["evaluation"]["fail"]["window"][1]["note"].startswith("before evaluate_from FY2027")
    second = one(test, readings + [R("fcf_to_non_gaap_net_income", "FY2028", 49)], period="FY2028Q4",
                 today=dt.date(2029, 8, 1))
    assert second["result"] == "fail"
    assert one(test, readings, period="FY2026Q4")["result"] == "not_due"


def test_any_of_judges_only_its_due_branches():
    """APP-Q9's warn_rule: a quarterly branch and a year branch read in Q4 only."""
    rule = {"any_of": [{"metric": "drivers.installs", "op": "<", "threshold": 0, "unit": "%", "period": "quarter"},
                       {"metric": "drivers.price", "op": "<=", "threshold": 0, "unit": "%", "period": "year"}]}
    q3 = one(drivers_test(rule), [R("drivers.installs", "FY2026Q3", 1)])
    assert q3["result"] == "pass"
    assert [c["state"] for c in q3["evaluation"]["fail"]["children"]] == ["not_triggered", "not_due"]
    q4 = one(drivers_test(rule), [R("drivers.installs", "FY2026Q4", 1), R("drivers.price", "FY2026", -1)],
             period="FY2026Q4", today=AFTER_FY2026)
    assert q4["result"] == "fail"


def test_all_of_with_a_branch_not_due_is_not_due():
    rule = {"all_of": [{"metric": "drivers.installs", "op": "<", "threshold": 0, "unit": "%", "period": "quarter"},
                       {"metric": "drivers.price", "op": "<=", "threshold": 0, "unit": "%", "period": "year"}]}
    result = one(drivers_test(rule), [R("drivers.installs", "FY2026Q3", -1)])
    assert result["result"] == "not_due" and "rule.all_of[1]" in result["reason"]


def test_evaluate_on_a_nested_branch():
    """APP-Q13: the all_of branch is read only in FY2026Q3, the whole rule in Q3 and Q4."""
    rule = {"any_of": [{"metric": "drivers.installs", "op": "<", "threshold": 0, "unit": "%", "period": "quarter"},
                       {"all_of": [{"metric": "drivers.price", "op": "<", "threshold": 30, "unit": "%", "period": "quarter"}],
                        "evaluate_on": ["FY2026Q3"]}],
            "evaluate_on": ["FY2026Q3", "FY2026Q4"]}
    assert one(drivers_test(rule), [R("drivers.installs", "FY2026Q3", 1), R("drivers.price", "FY2026Q3", 10)])["result"] == "fail"
    q4 = one(drivers_test(rule), [R("drivers.installs", "FY2026Q4", 1), R("drivers.price", "FY2026Q4", 10)],
             period="FY2026Q4", today=AFTER_FY2026)
    assert q4["result"] == "pass"
    assert one(drivers_test(rule), [], period="FY2027Q1", today=dt.date(2027, 6, 1))["result"] == "not_due"


# --- lifecycle


def test_retired_and_superseded_tests_are_not_judged():
    old = quant("ACME-Q4", retired_at="FY2026Q3")
    new = quant("ACME-Q5", supersedes="ACME-Q4", effective_from="FY2026Q3")
    later = quant("ACME-Q6", effective_from="FY2027Q1")
    readings = [R("revenue_yoy", "FY2026Q3", 3), R("revenue_yoy", "FY2026Q2", 3)]
    doc = run([old, new, later], readings)
    assert [r["id"] for r in doc["results"]] == ["ACME-Q5"]
    assert doc["results"][0]["supersedes"] == "ACME-Q4" and doc["results"][0]["result"] == "fail"
    assert doc["not_in_force"] == [{"id": "ACME-Q4", "reason": "retired at FY2026Q3; superseded by ACME-Q5"},
                                   {"id": "ACME-Q6", "reason": "effective from FY2027Q1"}]
    before = run([old, new, later], readings, period="FY2026Q2", today=TODAY)
    assert [r["id"] for r in before["results"]] == ["ACME-Q4"]


def test_only_quantitative_tests_are_evaluated():
    staleness = {"id": "ACME-S1", "type": "staleness", "section": "moat", "max_age_quarters": 4}
    doc = run([quant(), staleness], [])
    assert [r["id"] for r in doc["results"]] == ["ACME-Q1"] and doc["not_in_force"] == []


# --- events, null readings, segments, series


def test_event_readings_and_the_metric_less_event_keyed_by_test_id():
    """MSFT-Q9: the second branch is an event judged by a model, with no metric: its reading is keyed by the test id."""
    rule = {"all_of": [{"metric": "m365_seats_yoy", "op": "<", "threshold": 0, "unit": "%", "period": "quarter"},
                       {"op": "event", "threshold": "no separately disclosed growing usage revenue", "period": "quarter"}]}
    md = {"id": "m365_seats_yoy", "description": "x", "unit": "%", "frequency": "quarter", "data": "filing_text"}
    test = quant("ACME-Q9", metric_def=md, data="filing_text", rule=rule)
    del test["metric"]
    seats = R("m365_seats_yoy", "FY2026Q3", -1)
    assert one(test, [seats, R("ACME-Q9", "FY2026Q3", True, "event")])["result"] == "fail"
    assert one(test, [seats, R("ACME-Q9", "FY2026Q3", False, "event")])["result"] == "pass"
    undecided = one(test, [seats])
    assert undecided["result"] == "undetermined" and undecided["missing"][0]["metric"] == "ACME-Q9"
    assert one(test, [seats, R("ACME-Q9", "FY2026Q3", 1, "event")])["result"] == "undetermined"  # not a boolean
    assert needed_readings(thesis(test), "FY2026Q3")[0]["metric"] == "ACME-Q9"


def test_null_reading_means_nothing_to_measure():
    """BRK-Q11: no qualifying acquisition in the period -> the metric is not computed -> the rule does not hold."""
    test = quant(metric="buyback_amount", rule={"op": ">", "threshold": 0, "unit": "USD", "period": "event"})
    reading = R("buyback_amount", "FY2026Q3", None, "USD", note="no qualifying event in the quarter")
    result = one(test, [reading])
    assert result["result"] == "pass" and result["reading"]["value"] is None
    assert "nothing to measure" in result["evaluation"]["fail"]["window"][0]["note"]


def test_segment_readings_match_params_segment():
    test = quant(metric="combined_ratio", data="filing_text", params={"segment": "GEICO"},
                 rule={"op": ">", "threshold": 100, "unit": "%", "consecutive": 1, "period": "quarter"})
    group = R("combined_ratio", "FY2026Q3", 104)  # the group's ratio: not GEICO's
    assert one(test, [group])["result"] == "undetermined"
    result = one(test, [group, R("combined_ratio", "FY2026Q3", 92, segment="GEICO")])
    assert result["result"] == "pass" and result["segment"] == "GEICO"
    assert result["missing"] == [] and result["reading"]["segment"] == "GEICO"
    assert needed_readings(thesis(test), "FY2026Q3") == [
        {"metric": "combined_ratio", "segment": "GEICO", "periods": ["FY2026Q3"], "unit": "%", "data": "filing_text",
         "where": contract.metrics()["combined_ratio"]["where"], "tests": ["ACME-Q1"]}]


def test_series_trigger_when_any_series_holds():
    """PDD-Q15: holdings of either holder group down more than 20% in a year."""
    md = {"id": "holder_shares", "description": "x", "unit": "shares", "frequency": "year", "data": "filing_text"}
    test = quant(metric_def=md, data="filing_text", params={"holders": ["A", "B"]},
                 rule={"op": "decrease", "threshold": 20, "unit": "%", "consecutive": 1, "period": "year"})
    del test["metric"]
    readings = [R("holder_shares", "FY2026", 100, "shares", series="A"), R("holder_shares", "FY2025", 100, "shares", series="A"),
                R("holder_shares", "FY2026", 70, "shares", series="B"), R("holder_shares", "FY2025", 100, "shares", series="B")]
    result = one(test, readings, period="FY2026Q4", today=dt.date(2027, 5, 1))
    assert result["result"] == "fail"
    assert [s["state"] for s in result["evaluation"]["fail"]["series"]] == ["not_triggered", "triggered"]
    mixed = readings + [R("holder_shares", "FY2026", 1, "shares")]
    assert one(test, mixed, period="FY2026Q4", today=dt.date(2027, 5, 1))["result"] == "undetermined"


# --- units, conflicting readings, dates


def test_units_are_converted_within_a_kind_and_otherwise_undetermined():
    md = {"id": "deal", "description": "x", "unit": "USD 100 million", "frequency": "event", "data": "filing_text"}
    test = quant(metric_def=md, data="filing_text", rule={"op": ">", "threshold": 100, "unit": "USD 100 million",
                                                         "period": "event"})
    del test["metric"]
    assert one(test, [R("deal", "FY2026Q3", 12_000_000_000, "USD")])["result"] == "fail"  # $12 bn > 100 x $100 m
    assert one(test, [R("deal", "FY2026Q3", 9.5, "USD billion")])["result"] == "pass"
    wrong = one(test, [R("deal", "FY2026Q3", 12, "%")])
    assert wrong["result"] == "undetermined" and "reading in '%', rule in 'USD 100 million'" in wrong["reason"]


def test_conflicting_readings_are_undetermined():
    test = quant(rule={"op": "<", "threshold": 5, "unit": "%", "period": "quarter"})
    same = [R("revenue_yoy", "FY2026Q3", 3), R("revenue_yoy", "FY2026Q3", 3)]
    assert one(test, same)["result"] == "fail"
    clash = [R("revenue_yoy", "FY2026Q3", 3), R("revenue_yoy", "FY2026Q3", 6)]
    result = one(test, clash)
    assert result["result"] == "undetermined" and "conflicting readings" in result["reason"]


def test_readings_of_periods_not_yet_ended_are_ignored():
    """MSFT's FY2027Q1 ends on 2026-09-30 (fiscal year ending June 30)."""
    test = quant(rule={"op": "<", "threshold": 5, "unit": "%", "period": "quarter"})
    doc = run(test, [R("revenue_yoy", "FY2027Q1", 3)], period="FY2027Q1", today=dt.date(2026, 9, 15), fye="06-30")
    assert doc["results"][0]["result"] == "undetermined"
    assert doc["ignored_readings"] == [{"metric": "revenue_yoy", "period": "FY2027Q1",
                                        "reason": "FY2027Q1 ends on 2026-09-30, after 2026-09-15"}]
    assert doc["warnings"] == ["FY2027Q1 ends on 2026-09-30, after the evaluation date 2026-09-15"]
    later = run(test, [R("revenue_yoy", "FY2027Q1", 3)], period="FY2027Q1", today=dt.date(2026, 10, 30), fye="06-30")
    assert later["results"][0]["result"] == "fail" and later["ignored_readings"] == []


# --- rules the engine does not understand


@pytest.mark.parametrize("rule,why", [
    ({"op": "<", "threshold": 5, "all_of": [{"op": "<", "threshold": 1}]}, "exactly one of op, all_of, any_of"),
    ({"op": "decrease", "threshold": 1, "unit": "%", "period": "quarter"}, "ambiguous"),
    ({"op": "<", "threshold": 5, "unit": "USD", "period": "quarter"}, "does not fit the metric's unit"),
    ({"op": "increase", "threshold": 1, "unit": "pp", "period": "event"}, "event period"),
    ({"op": "<", "threshold": "5%", "unit": "%"}, "numeric threshold"),
    ({"op": "outside", "threshold": [15, -10], "unit": "%"}, "low <= high"),
    ({"op": "near", "threshold": 1}, "unknown op"),
    ({"op": "<", "threshold": 1, "unit": "%", "period": "month"}, "period"),
    ({"op": "<", "threshold": 1, "unit": "%", "evaluate_from": "2027"}, "evaluate_from"),
    ({"all_of": [{"op": "<", "threshold": 1, "unit": "%", "period": "year"}], "consecutive": 2, "period": "quarter"},
     "counts quarters"),
    ({"metric": "not_a_metric", "op": "<", "threshold": 1}, "not in spec/metrics.yml"),
    ({"op": "<", "threshold": 1, "unit": "%", "period": "year", "evaluate_on": ["FY2026Q3"]}, "never be judged"),
])
def test_rules_the_engine_does_not_understand_are_undetermined(rule, why):
    test = quant(rule=rule)
    problems = shape_problems(test)
    assert problems and why in problems[0], problems
    result = one(test, [R("revenue_yoy", "FY2026Q3", 1)])
    assert result["result"] == "undetermined" and result["reason"].startswith("rule not understood by the engine")
    assert schema_errors(run(test, [])) == []


def test_two_metric_less_events_cannot_be_told_apart():
    rule = {"any_of": [{"op": "event", "threshold": "one thing"}, {"op": "event", "threshold": "another"}]}
    assert "could not be told apart" in shape_problems(quant(rule=rule))[0]


# --- output


def test_output_document_validates_against_the_schema():
    tests = [quant("ACME-Q1"),
             quant("ACME-Q2", metric="roe", rule={"op": "<", "threshold": 12, "unit": "%", "consecutive": 2, "period": "year"}),
             quant("ACME-Q3", rule={"op": "decrease", "unit": "%"}),
             quant("ACME-Q4", retired_at="FY2026Q2"),
             drivers_test({"all_of": [{"metric": "drivers.installs", "op": "<", "threshold": 0, "unit": "%"}],
                           "consecutive": 2, "period": "quarter"}) | {"id": "ACME-Q5"}]
    readings = [R("revenue_yoy", "FY2026Q3", 3), R("drivers.installs", "FY2026Q3", -1), R("drivers.installs", "FY2026Q2", 2),
                R("revenue_yoy", "FY2027Q1", 1)]
    doc = run(tests, readings)
    assert schema_errors(doc) == []
    assert doc["summary"] == {"pass": 1, "warn": 0, "fail": 0, "undetermined": 2, "not_due": 1}
    assert doc["company"] == "ACME" and doc["period"] == "FY2026Q3" and doc["evaluated_on"] == TODAY.isoformat()
    assert doc["engine"].startswith("thesis-ci ")


def test_evaluation_period_must_be_a_quarter():
    with pytest.raises(ValueError):
        evaluate_company(thesis(quant()), [], "FY2026", TODAY)
    with pytest.raises(ValueError):
        needed_readings(thesis(quant()), "2026Q3")


def test_needed_readings_lists_windows_bases_and_skips_what_is_not_due():
    tests = [quant("ACME-Q1", warn_rule={"op": "<", "threshold": 8, "unit": "%", "consecutive": 4, "period": "quarter"}),
             quant("ACME-Q2", metric="operating_margin",
                   rule={"op": "decrease", "threshold": 5, "unit": "pp", "consecutive": 2, "period": "quarter"}),
             quant("ACME-Q3", metric="roe", rule={"op": "<", "threshold": 12, "unit": "%", "consecutive": 2, "period": "year"})]
    needs = {n["metric"]: n for n in needed_readings(thesis(*tests), "FY2026Q3")}
    assert set(needs) == {"revenue_yoy", "operating_margin"}
    assert needs["revenue_yoy"]["periods"] == ["FY2025Q4", "FY2026Q1", "FY2026Q2", "FY2026Q3"]
    assert needs["operating_margin"]["periods"] == ["FY2025Q2", "FY2025Q3", "FY2026Q2", "FY2026Q3"]
    assert needs["revenue_yoy"]["xbrl"] == contract.metrics()["revenue_yoy"]["xbrl"]
    q4 = {n["metric"]: n for n in needed_readings(thesis(*tests), "FY2026Q4")}
    assert q4["roe"]["periods"] == ["FY2025", "FY2026"]


def test_kleene_logic():
    t, f, u = evaluate.TRIGGERED, evaluate.NOT_TRIGGERED, evaluate.UNDETERMINED
    assert evaluate.kleene_and([t, u]) == u and evaluate.kleene_and([f, u]) == f and evaluate.kleene_and([t, t]) == t
    assert evaluate.kleene_or([f, u]) == u and evaluate.kleene_or([t, u]) == t and evaluate.kleene_or([f, f]) == f


def test_c_test_metric_flags_rules_the_evaluation_engine_cannot_judge(ws, lint):
    """C-TEST-METRIC: a rule that parses and resolves but that the engine cannot judge is an error at lint time."""
    from thesis_ci import selftest

    assert lint(ws, "C-TEST-METRIC") == []
    selftest.apply(ws, (selftest.replace(selftest.THESIS, 'warn_rule: {op: "<", threshold: 58, unit: "%"',
                                         'warn_rule: {op: decrease, threshold: 3, unit: "%"'),))
    found = lint(ws, "C-TEST-METRIC")
    assert len(found) == 1 and "the evaluation engine cannot judge it" in found[0].message
    assert "ambiguous" in found[0].message and found[0].line is not None
