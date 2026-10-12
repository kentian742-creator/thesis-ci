"""XBRL readings from real SEC companyfacts, against figures recomputed from the filings (metrics.py, SPEC 4.5, 9.1).

Each fixture in tests/fixtures/companyfacts is the document the SEC served on 2026-10-11 at
data.sec.gov/api/xbrl/companyfacts/CIK##########.json, trimmed to the concepts these tests read and to the facts that
end on or after a cutoff (AppLovin and American Express 2022-01-01, Costco 2022-08-01, Walmart 2024-01-01). The rows
themselves are unchanged; concept descriptions are left out. The trimmed documents give the same fiscal calendar and
the same readings as the full ones for every period these tests use.

The metric definitions are those published in the Owner's Office archive
(github.com/kentian742-creator/owners-office, companies/<TICKER>/thesis.yml), under the test ids named.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from thesis_ci.evaluate import evaluate_company
from thesis_ci.metrics import Facts, computable, readings_from_companyfacts
from thesis_ci.periods import Fiscal, fiscal_year_end, quarter_end_date

FIXTURES = Path(__file__).parent / "fixtures" / "companyfacts"
FISCAL_YEAR_END = {"APP": "12-31", "AXP": "12-31", "COST": "08-30", "WMT": "01-31"}

APP_Q3 = {"id": "net_debt_to_fcf_ttm", "unit": "x", "frequency": "quarter", "data": "xbrl",
          "formula": "(debt - cash - short_term_investments) / sum_4q(operating_cash_flow - capex)",
          "xbrl": ["us-gaap:LongTermDebt", "us-gaap:LongTermDebtNoncurrent",
                   "us-gaap:CashAndCashEquivalentsAtCarryingValue", "us-gaap:ShortTermInvestments",
                   "us-gaap:NetCashProvidedByUsedInOperatingActivities",
                   "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment"]}
APP_Q6 = {"id": "owner_fcf_margin_ttm", "unit": "%", "frequency": "quarter", "data": "xbrl",  # and APP-Q11
          "formula": "sum_4q(operating_cash_flow - capex - stock_based_compensation) / sum_4q(revenue)",
          "xbrl": ["us-gaap:NetCashProvidedByUsedInOperatingActivities",
                   "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment", "us-gaap:ShareBasedCompensation",
                   "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", "us-gaap:Revenues"]}
AXP_Q1 = {"id": "revenue_net_of_interest_expense_yoy", "unit": "%", "frequency": "quarter", "data": "xbrl",
          "formula": "revenue_t / revenue_{t-4q} - 1",
          "xbrl": ["us-gaap:RevenuesNetOfInterestExpense", "us-gaap:Revenues"]}
AXP_Q4 = {"id": "capital_return_to_common_ni_3y", "unit": "%", "frequency": "year", "data": "xbrl",
          "formula": "sum_3y(buybacks + common_dividends) / sum_3y(net_income_to_common)",
          "xbrl": ["us-gaap:PaymentsForRepurchaseOfCommonStock", "us-gaap:PaymentsOfDividendsCommonStock",
                   "us-gaap:NetIncomeLossAvailableToCommonStockholdersBasic"]}
AXP_Q14 = {"id": "pre_provision_pretax_income_yoy", "unit": "%", "frequency": "quarter", "data": "xbrl",
           "formula": "(pretax_income + provisions)_t / (pretax_income + provisions)_{t-4q} - 1",
           "xbrl": [
               "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
               "us-gaap:ProvisionForLoanLeaseAndOtherLosses", "us-gaap:ProvisionForLoanAndLeaseLosses"]}
AXP_Q15 = {"id": "diluted_eps_yoy", "unit": "%", "frequency": "year", "data": "xbrl",
           "formula": "eps_diluted_t / eps_diluted_{t-1y} - 1", "xbrl": ["us-gaap:EarningsPerShareDiluted"]}
COST_Q8 = {"id": "operating_margin_total_revenue", "unit": "%", "frequency": "year", "data": "xbrl",  # and COST-Q15
           "formula": "operating_income / total_revenue", "xbrl": ["us-gaap:OperatingIncomeLoss", "us-gaap:Revenues"]}
COST_Q13 = {"id": "pretax_return_on_capital", "unit": "%", "frequency": "year", "data": "xbrl",
            "formula": "operating_income / (total_equity + long_term_debt_noncurrent + long_term_debt_current - cash)",
            "xbrl": ["us-gaap:OperatingIncomeLoss",
                     "us-gaap:StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
                     "us-gaap:LongTermDebtNoncurrent", "us-gaap:LongTermDebtCurrent",
                     "us-gaap:CashAndCashEquivalentsAtCarryingValue"]}
COST_Q14 = {"id": "fcf_conversion_3y", "unit": "%", "frequency": "year", "data": "xbrl",
            "formula": "sum_3y(operating_cash_flow - capex) / sum_3y(net_income)",
            "xbrl": ["us-gaap:NetCashProvidedByUsedInOperatingActivities",
                     "us-gaap:PaymentsToAcquirePropertyPlantAndEquipment", "us-gaap:ProfitLoss",
                     "us-gaap:NetIncomeLoss"]}


def companyfacts(ticker):
    return json.loads((FIXTURES / f"{ticker}.json").read_text(encoding="utf-8"))


def read(ticker, definitions, periods, metrics=None):
    """{(metric, period): reading} for metric definitions (by id) and registry metrics."""
    ids = list(metrics or []) + [d["id"] for d in definitions]
    out = readings_from_companyfacts(companyfacts(ticker), ids, periods, FISCAL_YEAR_END[ticker], ticker=ticker,
                                     definitions={d["id"]: d for d in definitions})
    return {(r["metric"], r["period"]): r for r in out}


def amount(formula, unit="USD", frequency="quarter"):
    return {"id": "amount", "unit": unit, "frequency": frequency, "data": "xbrl", "formula": formula}


def near(value):
    return pytest.approx(value, abs=1e-4)


@pytest.mark.parametrize("definition", [APP_Q3, APP_Q6, AXP_Q1, AXP_Q4, AXP_Q14, AXP_Q15, COST_Q8, COST_Q13, COST_Q14])
def test_the_published_definitions_are_computable(definition):
    ok, notes = computable(definition)
    assert ok
    assert notes == ("us-gaap:LongTermDebtNoncurrent in xbrl is a candidate of long_term_debt_noncurrent, which the "
                     "formula does not read" if definition is APP_Q3 else "")


# ---------------------------------------------------------------------------------------------------- Costco


def test_costco_operating_margin_on_total_revenue():
    """COST-Q8 and COST-Q15: Costco tags no us-gaap:Revenues in its FY2026 10-K, so total revenue falls back to the
    undimensioned revenue from contracts with customers: 11,685 / 303,154 = 3.85%."""
    got = read("COST", [COST_Q8], ["FY2026", "FY2025", "FY2026Q4"])
    assert set(got) == {("operating_margin_total_revenue", "FY2026"), ("operating_margin_total_revenue", "FY2025")}
    fy26 = got[("operating_margin_total_revenue", "FY2026")]
    assert fy26["value"] == near(11685 / 303154 * 100) and fy26["value"] == 3.8545 and fy26["unit"] == "%"
    assert fy26["basis"] == (
        "operating_income / total_revenue = 11,685,000,000 / 303,154,000,000; operating_income: "
        "us-gaap:OperatingIncomeLoss: FY2026 as reported (10-K 0000909832-26-000093); total_revenue: "
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax: FY2026 as reported (10-K 0000909832-26-000093)")
    assert fy26["source"] == ("COST-XBRL#us-gaap:OperatingIncomeLoss:0000909832-26-000093+"
                              "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax:0000909832-26-000093")
    fy25 = got[("operating_margin_total_revenue", "FY2025")]  # the FY2025 10-K did tag Revenues, listed first
    assert fy25["value"] == near(10383 / 275235 * 100) and "total_revenue: us-gaap:Revenues:" in fy25["basis"]


def test_costco_pretax_return_on_capital_at_year_end_balances():
    """COST-Q13: 11,685 / (35,803 + 3,914 + 2,248 - 20,207) = 53.7%; equity falls back to stockholders' equity, since
    Costco reports no noncontrolling interests at 2026-08-30."""
    got = read("COST", [COST_Q13], ["FY2026", "FY2026Q4"])
    assert list(got) == [("pretax_return_on_capital", "FY2026")]  # an annual definition has no quarterly reading
    reading = got[("pretax_return_on_capital", "FY2026")]
    assert reading["value"] == near(11685 / 21758 * 100) == 53.7044
    assert ("= 11,685,000,000 / (35,803,000,000 + 3,914,000,000 + 2,248,000,000 - 20,207,000,000); "
            in reading["basis"])
    assert "total_equity: us-gaap:StockholdersEquity: at 2026-08-30 (10-K 0000909832-26-000093)" in reading["basis"]


def test_costco_three_year_free_cash_flow_conversion():
    """COST-Q14: (40,491 - 16,643) / 24,692 = 96.6% over FY2024-FY2026; ProfitLoss, listed first, lacks FY2026, so
    net income is NetIncomeLoss for all three years."""
    got = read("COST", [COST_Q14], ["FY2026"])
    reading = got[("fcf_conversion_3y", "FY2026")]
    assert reading["value"] == near(23848 / 24692 * 100) == 96.5819
    assert reading["basis"].startswith(
        "sum_3y(operating_cash_flow - capex) / sum_3y(net_income) = ((11,339,000,000 - 4,710,000,000) + "
        "(13,335,000,000 - 5,498,000,000) + (15,817,000,000 - 6,435,000,000)) / (7,367,000,000 + 8,099,000,000 + "
        "9,226,000,000); ")
    assert "net_income: us-gaap:NetIncomeLoss: FY2024 as reported" in reading["basis"]


def test_costco_quarters_end_where_its_filings_say():
    """Costco's quarters run 12, 12, 12 and 16 weeks, and its year ends on the Sunday nearest August 31: FY2026's
    quarters ended 2025-11-23, 2026-02-15, 2026-05-10 and 2026-08-30, 7, 13 and 20 days before the month ends that
    fiscal_year_end implies for the first three."""
    facts = Facts(companyfacts("COST"), fiscal_year_end("08-30"))
    assert [facts.dates(Fiscal(2026, "quarter", q)) for q in (1, 2, 3, 4)] == [
        (dt.date(2025, 9, 1), dt.date(2025, 11, 23)), (dt.date(2025, 11, 24), dt.date(2026, 2, 15)),
        (dt.date(2026, 2, 16), dt.date(2026, 5, 10)), (dt.date(2026, 5, 11), dt.date(2026, 8, 30))]
    assert facts.dates(Fiscal(2026, "year")) == (dt.date(2025, 9, 1), dt.date(2026, 8, 30))
    assert quarter_end_date(2026, 3, fiscal_year_end("08-30")) == dt.date(2026, 5, 30)  # what 0.5 matched against


def test_costco_quarters_from_year_to_date_figures():
    """Revenue for the 16-week fourth quarter is the year less the first 36 weeks (303,154 - 207,431 = 95,723); the
    cash flow statement is year to date only, so each quarter of operating cash flow is derived."""
    got = read("COST", [amount("revenue")], ["FY2026Q1", "FY2026Q2", "FY2026Q3", "FY2026Q4"])
    assert {p: r["value"] for (_, p), r in got.items()} == {
        "FY2026Q1": 67_307_000_000, "FY2026Q2": 69_597_000_000, "FY2026Q3": 70_527_000_000, "FY2026Q4": 95_723_000_000}
    assert got[("amount", "FY2026Q4")]["basis"] == (
        "revenue = 95,723,000,000; revenue: us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax: FY2026Q4 = "
        "FY - 9M (303,154,000,000 10-K 0000909832-26-000093 - 207,431,000,000 10-Q 0000909832-26-000051)")
    cash = read("COST", [amount("operating_cash_flow")], ["FY2026Q1", "FY2026Q2", "FY2026Q3", "FY2026Q4"])
    assert [r["value"] for r in cash.values()] == [4_688_000_000, 2_996_000_000, 3_449_000_000, 4_684_000_000]
    assert sum(r["value"] for r in cash.values()) == 15_817_000_000  # the year as reported
    growth = read("COST", [], ["FY2026Q2", "FY2026Q3"], metrics=["revenue_yoy"])  # missing in thesis-ci 0.5
    assert growth[("revenue_yoy", "FY2026Q2")]["value"] == near((69597 / 63723 - 1) * 100)
    assert set(growth) == {("revenue_yoy", "FY2026Q2"), ("revenue_yoy", "FY2026Q3")}


def test_costco_tests_judged_end_to_end():
    """The readings judge COST-Q8 and COST-Q13 as published, with effective_from moved to FY2026Q4 for the test."""
    readings = list(read("COST", [COST_Q8, COST_Q13], ["FY2025", "FY2026"]).values())
    thesis = {"company": "COST", "filer": {"fiscal_year_end": "08-30"}, "tests": [
        {"id": "COST-Q8", "type": "quantitative", "metric_def": COST_Q8, "effective_from": "FY2026Q4",
         "rule": {"op": "<", "threshold": 3.0, "unit": "%", "consecutive": 2, "period": "year"}},
        {"id": "COST-Q13", "type": "quantitative", "metric_def": COST_Q13, "effective_from": "FY2026Q4",
         "rule": {"op": "<", "threshold": 35, "unit": "%", "consecutive": 1, "period": "year"},
         "warn_rule": {"op": "<", "threshold": 40, "unit": "%", "consecutive": 1, "period": "year"}}]}
    results = {t["id"]: t for t in evaluate_company(thesis, readings, "FY2026Q4", dt.date(2026, 10, 11))["results"]}
    assert results["COST-Q8"]["result"] == "pass" and results["COST-Q8"]["reading"]["value"] == 3.8545
    assert results["COST-Q13"]["result"] == "pass" and results["COST-Q13"]["reading"]["value"] == 53.7044


# ---------------------------------------------------------------------------------------------------- AppLovin


def test_applovin_owner_free_cash_flow_margin_at_fy2026q2():
    """APP-Q6 and APP-Q11 have no reading: AppLovin's cash flow statements have shown no purchases of property and
    equipment since FY2025 (they sit in "other investing activities", $7.7 million in the first half of 2026), so
    capex has no fact for any quarter in the window, and a missing fact is never taken as zero.

    The thesis baseline's 61.9% is (free cash flow $4,508 million, company definition, less stock-based compensation
    $284 million) / revenue $6,829 million. From XBRL over FY2025Q3-FY2026Q2: revenue 6,829,124 thousand (the same),
    operating cash flow 4,527,589 thousand, stock-based compensation in the cash flow statement 282,376 thousand;
    without capex the margin is 62.16%. The 0.3-point gap is what the company's free cash flow deducts beyond
    operating cash flow (capital expenditure and finance-lease principal, about $19.6 million) and the expense measure
    of stock-based compensation ($283.5 million)."""
    periods = ["FY2026Q2", "FY2026Q1", "FY2025Q4", "FY2025"]
    assert read("APP", [APP_Q6], periods) == {}
    parts = read("APP", [amount("sum_4q(operating_cash_flow)")], ["FY2026Q2"])
    assert parts[("amount", "FY2026Q2")]["value"] == 4_527_589_000  # 1,053,422 + 1,313,734 + 1,291,393 + 869,040
    assert read("APP", [amount("sum_4q(stock_based_compensation)")], ["FY2026Q2"])[
        ("amount", "FY2026Q2")]["value"] == 282_376_000
    assert read("APP", [amount("sum_4q(revenue)")], ["FY2026Q2"])[("amount", "FY2026Q2")]["value"] == 6_829_124_000
    without_capex = {**APP_Q6, "formula": "sum_4q(operating_cash_flow - stock_based_compensation) / sum_4q(revenue)"}
    reading = read("APP", [without_capex], ["FY2026Q2"])[("owner_fcf_margin_ttm", "FY2026Q2")]
    assert reading["value"] == near((4527589 - 282376) / 6829124 * 100) == 62.1634
    assert reading["basis"].startswith(
        "sum_4q(operating_cash_flow - stock_based_compensation) / sum_4q(revenue) = ((1,053,422,000 - 33,141,000) + "
        "(1,313,734,000 - 80,254,000) + (1,291,393,000 - 83,372,000) + (869,040,000 - 85,609,000)) / "
        "(1,405,045,000 + 1,657,944,000 + 1,842,449,000 + 1,923,686,000); ")
    assert abs(reading["value"] - 61.9) < 0.3


def test_applovin_net_debt_to_free_cash_flow_has_no_reading():
    """APP-Q3: AppLovin reports no short-term investments, and no capex since FY2025; LongTermDebt is tagged at
    fiscal year ends only (quarter ends carry LongTermDebtNoncurrent, which the formula's debt does not read)."""
    assert read("APP", [APP_Q3], ["FY2026Q2", "FY2025Q4", "FY2025", "FY2024"]) == {}
    debt = read("APP", [amount("debt")], ["FY2026Q2", "FY2025"])
    assert list(debt) == [("amount", "FY2025")] and debt[("amount", "FY2025")]["value"] == 3_512_987_000


# ---------------------------------------------------------------------------------------------------- American Express


def test_american_express_pre_provision_pretax_income_growth():
    """AXP-Q14: (4,071 + 1,084) / (3,550 + 1,405) - 1 = 4.0% for Q2 2026, and (7,849 + 2,336) / (6,880 + 2,555) - 1 =
    7.9% for the first half, as in the thesis baseline. American Express tags its provisions for credit losses as
    ProvisionForLoanLossesExpensed, a fallback after the two concepts the definition lists."""
    got = read("AXP", [AXP_Q14], ["FY2026Q2", "FY2026H1"])
    q2 = got[("pre_provision_pretax_income_yoy", "FY2026Q2")]
    assert q2["value"] == near((5155 / 4955 - 1) * 100) == 4.0363
    assert q2["basis"] == (
        "(pretax_income + provisions)_t / (pretax_income + provisions)_{t-4q} - 1 = (4,071,000,000 + 1,084,000,000) / "
        "(3,550,000,000 + 1,405,000,000) - 1; pretax_income: "
        "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest: "
        "FY2025Q2 as reported (10-Q 0000004962-26-000322); FY2026Q2 as reported (10-Q 0000004962-26-000322); "
        "provisions: us-gaap:ProvisionForLoanLossesExpensed: FY2025Q2 as reported (10-Q 0000004962-26-000322); "
        "FY2026Q2 as reported (10-Q 0000004962-26-000322)")
    assert got[("pre_provision_pretax_income_yoy", "FY2026H1")]["value"] == near((10185 / 9435 - 1) * 100) == 7.9491


def test_american_express_three_year_capital_return():
    """AXP-Q4 over FY2023-FY2025: (3,650 + 1,770 + 6,020 + 1,999 + 5,814 + 2,286) / (8,316 + 10,071 + 10,775) = 73.9%.
    American Express tags no common dividends paid, so common_dividends falls back to common cash dividends declared;
    its cash flow line for buybacks is "repurchase of American Express common shares and other". The thesis baseline,
    71.3%, uses the capital-return amounts of the 10-K text instead."""
    got = read("AXP", [AXP_Q4], ["FY2025", "FY2025Q4", "FY2024"])
    assert list(got) == [("capital_return_to_common_ni_3y", "FY2025")]  # FY2024 needs 2022, before the fixture
    reading = got[("capital_return_to_common_ni_3y", "FY2025")]
    assert reading["value"] == near(21539 / 29162 * 100) == 73.8598
    assert "common_dividends: us-gaap:DividendsCommonStockCash: FY2023 as reported" in reading["basis"]


def test_american_express_single_quantity_growth_is_read_as_before():
    """AXP-Q1 and AXP-Q15 keep the 0.4 computation over their own xbrl lists, for every period asked for."""
    got = read("AXP", [AXP_Q1, AXP_Q15], ["FY2026Q2", "FY2025"])
    assert got[("revenue_net_of_interest_expense_yoy", "FY2026Q2")]["value"] == near((19637 / 17856 - 1) * 100)
    assert got[("revenue_net_of_interest_expense_yoy", "FY2026Q2")]["source"] == (
        "AXP-XBRL#us-gaap:RevenuesNetOfInterestExpense:0000004962-26-000322")
    assert got[("diluted_eps_yoy", "FY2025")]["value"] == near((15.38 / 14.01 - 1) * 100)
    assert ("diluted_eps_yoy", "FY2026Q2") in got  # frequency: year, yet quarters are read, as in 0.4


# ---------------------------------------------------------------------------------------------------- the calendar


def test_walmart_quarters_end_at_month_ends_in_a_january_year():
    """Walmart's fiscal year ends on January 31 (FY2027 ends 2027-01-31) and its quarters at month ends."""
    facts = Facts(companyfacts("WMT"), fiscal_year_end("01-31"))
    assert facts.dates(Fiscal(2027, "quarter", 1)) == (dt.date(2026, 2, 1), dt.date(2026, 4, 30))
    assert facts.dates(Fiscal(2027, "quarter", 2)) == (dt.date(2026, 5, 1), dt.date(2026, 7, 31))
    assert facts.dates(Fiscal(2026, "quarter", 4)) == (dt.date(2025, 11, 1), dt.date(2026, 1, 31))
    assert all(end == quarter_end_date(y, q, (1, 31)) for (y, q), end in facts.ends.items())
    growth = {"id": "total_revenue_yoy", "unit": "%", "frequency": "quarter", "data": "xbrl",
              "formula": "total_revenue_t / total_revenue_{t-4q} - 1"}
    got = read("WMT", [growth, amount("operating_cash_flow")], ["FY2027Q2", "FY2026Q4"])
    assert got[("total_revenue_yoy", "FY2027Q2")]["value"] == near((187937 / 177402 - 1) * 100)
    # the fourth quarter is the year less nine months: (713,163 - 522,507) / (680,985 - 500,431) - 1
    assert got[("total_revenue_yoy", "FY2026Q4")]["value"] == near((190656 / 180554 - 1) * 100)
    assert got[("amount", "FY2027Q2")]["value"] == 14_972_000_000  # 19,710 for six months less 4,738 for three


@pytest.mark.parametrize("ticker", ["APP", "AXP"])
def test_december_year_ends_are_unchanged(ticker):
    facts = Facts(companyfacts(ticker), fiscal_year_end("12-31"))
    assert len(facts.ends) >= 16
    assert all(end == quarter_end_date(y, q, (12, 31)) for (y, q), end in facts.ends.items())
