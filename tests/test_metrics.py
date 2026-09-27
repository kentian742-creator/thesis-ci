"""XBRL metrics from an SEC companyfacts document (metrics.py): fiscal periods, YTD derivation, fact selection."""

from __future__ import annotations

import pytest

from thesis_ci import contract, readings
from thesis_ci.metrics import NOT_COMPUTED, REGISTRY_FORMULAS, metric_definitions, readings_from_companyfacts


def fact(val, start, end, accn, form="10-Q", filed="2025-01-01"):
    row = {"end": end, "val": val, "accn": accn, "form": form, "filed": filed, "fy": 2099, "fp": "FY"}
    if start:
        row["start"] = start
    return row


# Calendar-year company. Filings: A25Q1..A25Q3 (10-Q), A25K (10-K), A26Q1 (10-Q), and an 8-K that must be ignored.
Q1, Q2, Q3, K, Q1N = ("A25Q1", "2025-05-01"), ("A25Q2", "2025-08-01"), ("A25Q3", "2025-11-01"), ("A25K", "2026-02-15"), \
    ("A26Q1", "2026-05-01")


def f(val, start, end, filing, form=None):
    accn, filed = filing
    return fact(val, start, end, accn, form or ("10-K" if accn.endswith("K") else "10-Q"), filed)


FACTS = {
    "cik": 1,
    "entityName": "ACME CORP",
    "facts": {
        "us-gaap": {
            "Revenues": {"units": {"USD": [
                f(100, "2025-01-01", "2025-03-31", Q1), f(90, "2024-01-01", "2024-03-31", Q1),
                f(110, "2025-04-01", "2025-06-30", Q2), f(95, "2024-04-01", "2024-06-30", Q2),
                f(210, "2025-01-01", "2025-06-30", Q2), f(185, "2024-01-01", "2024-06-30", Q2),
                f(120, "2025-07-01", "2025-09-30", Q3), f(100, "2024-07-01", "2024-09-30", Q3),
                f(330, "2025-01-01", "2025-09-30", Q3), f(285, "2024-01-01", "2024-09-30", Q3),
                f(460, "2025-01-01", "2025-12-31", K), f(390, "2024-01-01", "2024-12-31", K),
                f(115, "2026-01-01", "2026-03-31", Q1N), f(101, "2025-01-01", "2025-03-31", Q1N),  # restated comparative
                fact(999, "2025-01-01", "2025-12-31", "A8K", "8-K", "2026-01-20"),  # not a periodic report
            ]}},
            "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [  # year-to-date only, as in 10-Qs
                f(30, "2025-01-01", "2025-03-31", Q1), f(70, "2025-01-01", "2025-06-30", Q2),
                f(105, "2025-01-01", "2025-09-30", Q3), f(150, "2025-01-01", "2025-12-31", K),
                f(120, "2024-01-01", "2024-12-31", K),
            ]}},
            "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": [
                f(10, "2025-01-01", "2025-03-31", Q1), f(20, "2025-01-01", "2025-06-30", Q2),
                f(30, "2025-01-01", "2025-09-30", Q3), f(45, "2025-01-01", "2025-12-31", K),
                f(40, "2024-01-01", "2024-12-31", K),
            ]}},
            "WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": [
                f(1000, "2025-07-01", "2025-09-30", Q3), f(1050, "2024-07-01", "2024-09-30", Q3),
                f(1010, "2025-01-01", "2025-12-31", K), f(1060, "2024-01-01", "2024-12-31", K),
                f(1020, "2025-01-01", "2025-09-30", Q3), f(1070, "2024-01-01", "2024-09-30", Q3),
            ]}},
            "StockholdersEquity": {"units": {"USD": [
                f(400, None, "2024-12-31", K), f(500, None, "2025-12-31", K),
            ]}},
            "NetIncomeLoss": {"units": {"USD": [f(90, "2025-01-01", "2025-12-31", K)]}},
            "RevenuesNetOfInterestExpense": {"units": {"USD": [
                f(220, "2025-07-01", "2025-09-30", Q3), f(200, "2024-07-01", "2024-09-30", Q3),
            ]}},
        },
    },
}


def compute(metrics, periods, **kw):
    kw.setdefault("ticker", "ACME")
    return {(r["metric"], r["period"]): r for r in readings_from_companyfacts(FACTS, metrics, periods, "12-31", **kw)}


def test_quarter_reported_directly_and_year_on_year():
    got = compute(["revenue_yoy"], ["FY2025Q3"])[("revenue_yoy", "FY2025Q3")]
    assert got["value"] == pytest.approx(20.0) and got["unit"] == "%"
    assert got["source"] == "ACME-XBRL#us-gaap:Revenues:A25Q3"
    assert "120 / 100 - 1" in got["basis"]


def test_fourth_quarter_is_the_year_less_nine_months():
    got = compute(["revenue_yoy"], ["FY2025Q4"])[("revenue_yoy", "FY2025Q4")]
    assert got["value"] == pytest.approx((130 / 105 - 1) * 100, abs=1e-4)  # (460 - 330) / (390 - 285) - 1
    assert got["source"] == "ACME-XBRL#us-gaap:Revenues:A25K+us-gaap:Revenues:A25Q3"
    assert "FY2025Q4 = FY - 9M" in got["basis"]


def test_year_to_date_cash_flows_become_quarters():
    got = compute(["free_cash_flow"], ["FY2025Q1", "FY2025Q2", "FY2025Q3", "FY2025Q4", "FY2025", "FY2025H2"])
    assert {k[1]: v["value"] for k, v in got.items()} == {
        "FY2025Q1": 20, "FY2025Q2": 30, "FY2025Q3": 25, "FY2025Q4": 30, "FY2025": 105, "FY2025H2": 55}
    assert got[("free_cash_flow", "FY2025Q4")]["unit"] == "USD"


def test_the_latest_filed_value_wins_and_8k_facts_are_ignored():
    got = compute(["revenue_yoy"], ["FY2026Q1", "FY2025"])
    assert got[("revenue_yoy", "FY2026Q1")]["value"] == pytest.approx((115 / 101 - 1) * 100, abs=1e-4)
    assert got[("revenue_yoy", "FY2025")]["value"] == pytest.approx((460 / 390 - 1) * 100, abs=1e-4)
    assert "A8K" not in got[("revenue_yoy", "FY2025")]["source"]


def test_share_counts_are_never_derived_from_year_to_date_figures():
    got = compute(["diluted_shares_yoy"], ["FY2025Q3", "FY2025Q4", "FY2025"])
    assert set(got) == {("diluted_shares_yoy", "FY2025Q3"), ("diluted_shares_yoy", "FY2025")}
    assert got[("diluted_shares_yoy", "FY2025")]["value"] == pytest.approx((1010 / 1060 - 1) * 100, abs=1e-4)


def test_balances_and_annual_returns():
    got = compute(["roe"], ["FY2025", "FY2025Q4"])
    assert set(got) == {("roe", "FY2025")}  # a return on equity is annual only
    assert got[("roe", "FY2025")]["value"] == pytest.approx(20.0)  # 90 / avg(500, 400)


def test_what_cannot_be_computed_is_absent():
    got = compute(["revenue_yoy", "gross_margin", "net_write_off_rate", "book_value_per_share_yoy", "no_such_metric",
                   "fcf_conversion"], ["FY2024Q2", "FY2025Q2"])
    # FY2024Q2 has no year-earlier data; gross profit is not tagged; net_write_off_rate is filing_text;
    # book_value_per_share_yoy is not computed by design; fcf_conversion lacks quarterly net income.
    assert set(got) == {("revenue_yoy", "FY2025Q2")}


def test_every_registered_xbrl_metric_is_computed_or_explained():
    xbrl = {mid for mid, m in contract.metrics().items() if m["data"] == "xbrl"}
    assert xbrl == set(REGISTRY_FORMULAS) | set(NOT_COMPUTED)
    assert not set(REGISTRY_FORMULAS) & set(NOT_COMPUTED)


def test_metric_def_with_a_single_quantity_growth_formula():
    """AXP-Q1: revenue_t / revenue_{t-4q} - 1 over [RevenuesNetOfInterestExpense, Revenues]."""
    thesis = {"tests": [{"metric_def": {"id": "rev_net_yoy", "data": "xbrl", "formula": "revenue_t / revenue_{t-4q} - 1",
                                        "xbrl": ["us-gaap:RevenuesNetOfInterestExpense", "us-gaap:Revenues"]}},
                        {"metric_def": {"id": "text_metric", "data": "filing_text", "formula": "x_t / x_{t-4q} - 1"}},
                        {"metric_def": {"id": "two_things", "data": "xbrl", "formula": "a / b",
                                        "xbrl": ["us-gaap:Revenues"]}}]}
    defs = metric_definitions(thesis)
    got = compute(["rev_net_yoy", "text_metric", "two_things"], ["FY2025Q3", "FY2025Q2"], definitions=defs)
    assert set(got) == {("rev_net_yoy", "FY2025Q3"), ("rev_net_yoy", "FY2025Q2")}
    assert got[("rev_net_yoy", "FY2025Q3")]["value"] == pytest.approx(10.0)
    assert "RevenuesNetOfInterestExpense" in got[("rev_net_yoy", "FY2025Q3")]["source"]
    assert "us-gaap:Revenues:" in got[("rev_net_yoy", "FY2025Q2")]["source"]  # the first candidate lacks Q2


def test_reporting_currency_not_the_convenience_translation():
    cf = {"cik": 1737806, "facts": {"us-gaap": {"Revenues": {"units": {
        "CNY": [fact(400, "2025-01-01", "2025-12-31", "B1", "20-F", "2026-04-29"),
                fact(300, "2024-01-01", "2024-12-31", "B1", "20-F", "2026-04-29"),
                fact(200, "2023-01-01", "2023-12-31", "B0", "20-F", "2025-04-29")],
        "USD": [fact(56, "2025-01-01", "2025-12-31", "B1", "20-F", "2026-04-29")]}}}}}
    out = readings_from_companyfacts(cf, ["revenue_yoy"], ["FY2025"], "12-31")
    assert out[0]["value"] == pytest.approx(33.3333, abs=1e-4)
    assert out[0]["source"] == "CIK0001737806-XBRL#us-gaap:Revenues:B1"
    usd = readings_from_companyfacts(cf, ["revenue_yoy"], ["FY2025"], "12-31", currency="USD")
    assert usd == []  # no USD figure for FY2024: never mixed with CNY


def test_fiscal_year_ending_in_june_and_52_53_week_ends():
    cf = {"cik": 789019, "facts": {"us-gaap": {"Revenues": {"units": {"USD": [
        fact(77, "2025-06-29", "2025-09-27", "M1", "10-Q", "2025-10-29"),  # a 13-week quarter ending 3 days early
        fact(66, "2024-06-30", "2024-09-28", "M1", "10-Q", "2025-10-29"),
    ]}}}}}
    out = readings_from_companyfacts(cf, ["revenue_yoy"], ["FY2026Q1"], "06-30", ticker="MSFT")
    assert out[0]["period"] == "FY2026Q1" and out[0]["value"] == pytest.approx((77 / 66 - 1) * 100, abs=1e-4)


def test_readings_are_a_valid_readings_document():
    out = readings_from_companyfacts(FACTS, ["revenue_yoy", "free_cash_flow", "roe"], ["FY2025", "FY2025Q4"], "12-31",
                                     ticker="ACME")
    assert len(out) == 5  # revenue_yoy and free_cash_flow twice, roe for the year only
    assert readings.problems({"company": "ACME", "as_of": "2026-03-01", "readings": out}) == []


def test_malformed_period_is_an_error():
    with pytest.raises(ValueError):
        readings_from_companyfacts(FACTS, ["revenue_yoy"], ["2025Q3"], "12-31")
