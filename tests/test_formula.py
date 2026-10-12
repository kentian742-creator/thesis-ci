"""The formulas of data: xbrl metric definitions (formula.py, metrics.py, SPEC 9.1), on small synthetic companyfacts."""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import pytest

from thesis_ci import readings
from thesis_ci.formula import At, Avg, Binary, FormulaError, Name, Number, Sum, ascii_signs, names, parse, text
from thesis_ci.metrics import SYNONYMS, VOCABULARY, Facts, computable, formula_plan, readings_from_companyfacts
from thesis_ci.periods import Fiscal, fiscal_year_end, quarter_end_date

# ---------------------------------------------------------------------------------------------------- the parser


def test_published_formulas_parse():
    tree = parse("(debt - cash - short_term_investments) / sum_4q(operating_cash_flow - capex)")
    assert isinstance(tree, Binary) and tree.op == "/" and isinstance(tree.right, Sum)
    assert (tree.right.count, tree.right.unit) == (4, "quarter")
    assert names(tree) == ["debt", "cash", "short_term_investments", "operating_cash_flow", "capex"]
    years = parse("sum_3y(buybacks + common_dividends) / sum_3y(net_income_to_common)")
    assert (years.left.function, years.left.count, years.left.unit) == ("sum_3y", 3, "year")
    growth = parse("(pretax_income + provisions)_t / (pretax_income + provisions)_{t-4q} - 1")
    assert isinstance(growth, Binary) and growth.op == "-" and growth.right == Number(1.0, "1")
    ratio = growth.left
    assert isinstance(ratio.left, At) and ratio.left.years_back == 0
    assert isinstance(ratio.right, At) and ratio.right.years_back == 1
    assert ratio.left.body == ratio.right.body


def test_names_with_time_subscripts_and_precedence():
    assert parse("revenue_t / revenue_{t-1y} - 1") == parse("(revenue)_t / (revenue)_{ t - 1y } - 1")
    assert parse("net_income_to_common") == Name("net_income_to_common")  # ends in _common, not in _t
    assert parse("a - b - c") == Binary("-", Binary("-", Name("a"), Name("b")), Name("c"))
    assert parse("a - b * c") == Binary("-", Name("a"), Binary("*", Name("b"), Name("c")))
    assert text(parse("a - (b - c) / (d * e)")) == "a - (b - c) / (d * e)"
    assert text(parse("sum_4q(x)_{t-4q}")) == "sum_4q(x)_{t-4q}"


@pytest.mark.parametrize("formula,message", [
    ("", "the formula is empty"),
    ("revenue +", "the formula ends too early"),
    ("revenue capex", "unexpected 'capex' at character 9"),
    ("(revenue", "expected ')' to close the '(' at character 1"),
    ("median(equity)", "unknown function median() at character 1: the functions are sum_4q(), sum_<n>y() and avg()"),
    ("sum_8q(revenue)", "unknown function sum_8q()"),
    ("max(revenue, capex)", "unknown function max()"),
    ("revenue_{t-1q}", "time subscript _{t-1q} at character 8 is not one of _t, _{t-4q}, _{t-1y}"),
    ("revenue = capex", "unexpected '=' at character 9"),
    ("revenue ** 2", "unexpected '*' at character 10"),
])
def test_syntax_errors_say_where(formula, message):
    with pytest.raises(FormulaError) as err:
        parse(formula)
    assert message in str(err.value)


def test_typographic_signs_are_read_as_ascii_operators():
    assert parse("a × (1 − b ÷ c)") == parse("a * (1 - b / c)")
    assert parse("a · b") == parse("a ⋅ b") == parse("a * b") == Binary("*", Name("a"), Name("b"))
    assert parse("−revenue") == parse("-revenue")
    assert parse("x_t ÷ x_{t−4q} − 1") == parse("x_t / x_{t-4q} - 1")  # a minus sign in a time subscript too
    assert text(parse("sum_3y(dividends_paid + repurchases) ÷ sum_3y(operating_cash_flow − capex)")) == (
        "sum_3y(dividends_paid + repurchases) / sum_3y(operating_cash_flow - capex)")
    assert parse("2 · 5") == Binary("*", Number(2.0, "2"), Number(5.0, "5"))  # spaced, it can only be a product
    assert ascii_signs("a×b÷c−d·e⋅f") == "a*b/c-d*e*f"
    assert ascii_signs("0·5 · x") == "0·5 * x"  # one character for one, so positions in messages stay right


@pytest.mark.parametrize("formula,message", [
    ("0·5 * revenue", "'·' between two digits at character 2 could be a decimal point or a multiplication sign: "
                      "write '.' or '*'"),
    ("revenue ×× capex", "unexpected '×' at character 10"),  # messages quote the sign as written
    ("revenue – capex", "unexpected '–' at character 9"),  # an en dash is not a minus sign
    ("revenue_{t−1q}", "time subscript _{t−1q} at character 8 is not one of _t, _{t-4q}, _{t-1y}"),
])
def test_typographic_mistakes_say_where(formula, message):
    with pytest.raises(FormulaError) as err:
        parse(formula)
    assert message in str(err.value)


def test_avg_parses_and_takes_subscripts():
    tree = parse("operating_income / avg(total_equity + debt - cash)")
    assert tree == Binary("/", Name("operating_income"),
                          Avg(Binary("-", Binary("+", Name("total_equity"), Name("debt")), Name("cash"))))
    assert names(tree) == ["operating_income", "total_equity", "debt", "cash"]
    assert text(parse("avg(cash)_t / avg(cash)_{t-4q} - 1")) == "avg(cash)_t / avg(cash)_{t-4q} - 1"
    assert isinstance(parse("avg (cash)"), Avg)
    with pytest.raises(FormulaError, match="nests more than 50 levels deep"):
        parse("avg(" * 51 + "cash" + ")" * 51)


def test_the_parser_never_evaluates_text():
    with pytest.raises(FormulaError):
        parse("__import__('os').system('true')")
    with pytest.raises(FormulaError):
        parse("revenue; capex")


def test_long_or_deeply_nested_formulas_are_refused():
    assert parse("(" * 50 + "revenue" + ")" * 50) == Name("revenue")
    with pytest.raises(FormulaError, match="nests more than 50 levels deep at character 51"):
        parse("(" * 51 + "revenue" + ")" * 51)
    with pytest.raises(FormulaError, match="nests more than 50 levels deep"):
        parse("-" * 60 + "revenue")
    with pytest.raises(FormulaError, match="longer than 1,000 characters"):
        parse(" + ".join(["revenue"] * 120))
    assert computable(definition("(" * 400 + "revenue" + ")" * 400, unit="USD"))[0] is False


# ---------------------------------------------------------------------------------------------------- the vocabulary


def test_vocabulary_has_the_names_formulas_need():
    for name in ("revenue", "total_revenue", "gross_profit", "operating_income", "pretax_income", "net_income",
                 "net_income_to_common", "operating_cash_flow", "capex", "stock_based_compensation", "buybacks",
                 "dividends", "common_dividends", "provisions", "cash", "short_term_investments", "total_assets",
                 "total_equity", "debt", "long_term_debt_noncurrent", "long_term_debt_current", "diluted_shares"):
        assert name in VOCABULARY, name
    assert all(target in VOCABULARY and alias not in VOCABULARY for alias, target in SYNONYMS.items())
    assert VOCABULARY["total_revenue"].concepts[:2] == ("us-gaap:Revenues",
                                                        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax")
    balances = {n for n, q in VOCABULARY.items() if q.instant}
    assert {"cash", "short_term_investments", "total_assets", "total_equity", "debt", "long_term_debt_noncurrent",
            "long_term_debt_current"} <= balances
    assert not balances & {"revenue", "operating_cash_flow", "capex", "net_income", "provisions"}
    assert all(q.instant in (True, False) for q in VOCABULARY.values())  # every vocabulary name has its kind


def test_vocabulary_names_added_in_0_6_1():
    flows = {n for n, q in VOCABULARY.items() if q.instant is False}
    balances = {n for n, q in VOCABULARY.items() if q.instant is True}
    assert "net_sales" in flows
    assert {"accounts_payable", "inventories", "short_term_borrowings", "finance_lease_obligations",
            "operating_lease_obligations"} <= balances
    assert {SYNONYMS[n] for n in ("income_tax_provision", "dividends_paid", "repurchases")} == {
        "income_tax", "dividends", "buybacks"}
    assert "pretax_income" in VOCABULARY
    # net_sales reads revenue from contracts with customers only as a part of a larger us-gaap:Revenues
    assert VOCABULARY["net_sales"].parts == (("us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
                                              "us-gaap:Revenues"),)
    assert "us-gaap:Revenues" not in VOCABULARY["net_sales"].concepts
    # concepts that hold more than the quantity are not candidates
    assert "us-gaap:AccountsPayableAndAccruedLiabilitiesCurrent" not in VOCABULARY["accounts_payable"].concepts
    assert not {"us-gaap:DebtCurrent", "us-gaap:CommercialPaper"} & set(VOCABULARY["short_term_borrowings"].concepts)
    assert all(q.parts == () for name, q in VOCABULARY.items() if name != "net_sales")


KINDS = {"spec/SPEC.md": {"flow": ("money", False), "balance": ("money", True),
                          "flow, share count": ("shares", False), "flow, per share": ("per_share", False)},
         "zh-CN/spec/SPEC.md": {"流量": ("money", False), "余额": ("money", True),
                                "流量，股数": ("shares", False), "流量，每股": ("per_share", False)}}


@pytest.mark.parametrize("spec", list(KINDS))
def test_the_spec_lists_the_vocabulary(spec):
    """SPEC 9.1 (and its Chinese version) lists every name, its synonyms, kind and candidates as the code has them."""
    document = (Path(__file__).resolve().parents[1] / spec).read_text(encoding="utf-8")
    section = document[document.index("### 9.1"):]
    section = section[:section.index("\n## ")]
    table = {}
    for line in section.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 4 and cells[0].startswith("`"):
            table[cells[0].strip("`")] = (set(re.findall(r"`([^`]+)`", cells[1])), cells[2],
                                          tuple(re.findall(r"`([^`]+)`", cells[3])))
    assert set(table) == set(VOCABULARY)
    for name, quantity in VOCABULARY.items():
        synonyms, kind, concepts = table[name]
        assert synonyms == {alias for alias, target in SYNONYMS.items() if target == name}, name
        assert KINDS[spec][kind] == (quantity.kind, quantity.instant), name
        assert concepts == quantity.concepts, name


# ---------------------------------------------------------------------------------------------------- computable()


def definition(formula, unit="%", frequency="quarter", xbrl=None, data="xbrl"):
    out = {"id": "m", "description": "test", "unit": unit, "data": data, "formula": formula}
    if frequency:
        out["frequency"] = frequency
    if xbrl is not None:
        out["xbrl"] = xbrl
    return out


@pytest.mark.parametrize("formula,unit,frequency", [
    ("(debt - cash - short_term_investments) / sum_4q(operating_cash_flow - capex)", "x", "quarter"),
    ("sum_4q(operating_cash_flow - capex - stock_based_compensation) / sum_4q(revenue)", "%", "quarter"),
    ("sum_3y(buybacks + common_dividends) / sum_3y(net_income_to_common)", "%", "year"),
    ("(pretax_income + provisions)_t / (pretax_income + provisions)_{t-4q} - 1", "%", "quarter"),
    ("operating_income / total_revenue", "%", "year"),
    ("operating_income / (total_equity + long_term_debt_noncurrent + long_term_debt_current - cash)", "%", "year"),
    ("sum_3y(operating_cash_flow - capex) / sum_3y(net_income)", "%", "year"),
    ("operating_cash_flow - capex", "USD million", "quarter"),
    ("net_income / diluted_shares", "USD/shares", "year"),
    ("diluted_shares_t - diluted_shares_{t-1y}", "shares", "year"),
    ("revenues_t / revenues_{t-4q} - 1", "%", None),  # a synonym, no frequency
    ("revenues_t ÷ revenues_{t−4q} − 1", "%", None),  # typographic signs
    ("net_income / avg(equity)", "%", "year"),
    ("operating_income × (1 − income_tax_provision ÷ pretax_income) ÷ avg(total_equity + short_term_borrowings + "
     "long_term_debt + finance_lease_obligations + operating_lease_obligations − cash)", "%", "year"),
    ("avg(cash)_t / avg(cash)_{t-4q} - 1", "%", "quarter"),
    ("accounts_payable ÷ inventories", "%", "year"),
    ("capex ÷ net_sales", "%", "year"),
])
def test_computable_formulas(formula, unit, frequency):
    assert computable(definition(formula, unit, frequency)) == (True, "")


@pytest.mark.parametrize("formula,unit,frequency,reason", [
    ("net_incom / revenue", "%", "year", "unknown quantity name 'net_incom' (did you mean net_income?)"),
    ("fcf / revenue", "%", "year", "unknown quantity name 'fcf'"),
    ("sum_4q(cash) / sum_4q(revenue)", "%", "quarter",
     "sum_4q() adds up flows over periods, but cash is a balance at a date"),
    ("sum_4q(diluted_shares)", "shares", "quarter",
     "sum_4q() adds up amounts of money, but diluted_shares is a share count"),
    ("sum_3y(operating_cash_flow) / sum_3y(net_income)", "%", "quarter",
     "sum_3y() is read for fiscal years only, but frequency is quarter: write frequency: year"),
    ("sum_3y(operating_cash_flow) / sum_3y(net_income)", "%", None,
     "sum_3y() is read for fiscal years only, but frequency is not given"),
    ("operating_income / revenue", "USD", "year", "the formula gives a ratio, but unit is 'USD': write %, pp or x"),
    ("operating_cash_flow - capex", "%", "year",
     "the formula gives an amount of money, but unit '%' is not a currency"),
    ("revenue - 1", "USD", "year", "revenue - 1 subtracts a number or a ratio from an amount of money"),
    ("revenue * revenue", "USD", "year", "the formula's result is not a ratio"),
    ("operating_income / revenue * 100", "%", "year", "the formula multiplies by 100, and unit % does so again"),
    ("1 + 2", "x", "year", "the formula reads no quantity"),
    ("operating_income / revenue", "%", "year", None),
    ("avg(revenue)", "USD", "year",
     "avg() averages a balance at the start and at the end of a period, but revenue is a flow over a period"),
    ("avg(sum_4q(revenue))", "USD", "year", "avg() averages a balance at the start and at the end of a period, but "
                                            "revenue is a flow over a period"),
    ("sum_4q(avg(cash))", "USD", "quarter", "sum_4q() adds up flows over periods, but cash is a balance at a date"),
    ("avg(cash) ÷ avg(cash) * 100", "%", "year", "the formula multiplies by 100"),
    ("0·5 * revenue", "USD", "year", "'·' between two digits at character 2 could be a decimal point"),
])
def test_what_cannot_be_computed_and_why(formula, unit, frequency, reason):
    ok, why = computable(definition(formula, unit, frequency))
    if reason is None:
        assert ok and why == ""
    else:
        assert not ok and reason in why, why


def test_definitions_that_are_not_xbrl_formulas_are_not_computable():
    assert computable(definition("recurring / revenue", data="mixed")) == (
        False, "data is 'mixed': thesis-ci computes only data: xbrl definitions")
    assert computable({**definition("x"), "formula": None})[1] == "the definition has no formula"
    assert computable("revenue")[0] is False
    assert computable(definition("revenue_t / revenue_{t-4q} - 1", unit="x", xbrl=["us-gaap:Revenues"])) == (
        False, "a growth formula gives a percentage, but unit is 'x': write %")


def test_listed_concepts_go_first_and_unused_ones_are_noted():
    plan = formula_plan(definition("(debt - cash) / sum_4q(operating_cash_flow - capex)", "x", xbrl=[
        "us-gaap:LongTermDebtNoncurrent", "us-gaap:CashAndCashEquivalentsAtCarryingValue", "us-gaap:Foo"]))
    assert plan.quantities["debt"].concepts == ("us-gaap:LongTermDebt",)
    assert plan.notes == [
        "us-gaap:LongTermDebtNoncurrent in xbrl is a candidate of long_term_debt_noncurrent, which the formula does "
        "not read", "us-gaap:Foo in xbrl is a candidate of no quantity in the vocabulary, so it is not read"]
    ordered = formula_plan(definition("operating_income / total_revenue", xbrl=[
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"])).quantities["total_revenue"].concepts
    assert ordered == ("us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", "us-gaap:Revenues",
                       "ifrs-full:Revenue")
    ok, notes = computable(definition("(debt - cash) / sum_4q(operating_cash_flow)", "x",
                                      xbrl=["us-gaap:LongTermDebtNoncurrent"]))
    assert ok and "us-gaap:LongTermDebtNoncurrent in xbrl is a candidate of long_term_debt_noncurrent" in notes


def with_components(formula, unit="%", frequency="year", xbrl=None, **components):
    """A definition whose components are given as name=(unit, [concepts]) or name=(unit, None) for no xbrl."""
    out = definition(formula, unit, frequency, xbrl)
    out["components"] = {name: {"description": name, "unit": u, **({"xbrl": c} if c is not None else {})}
                         for name, (u, c) in components.items()}
    return out


def test_a_component_lists_concepts_first_for_a_vocabulary_name():
    """A vocabulary name keeps its meaning: its component's xbrl goes first, then the definition's xbrl, as far as
    they are candidates of the name; a concept that is not a candidate is noted and not read."""
    plan = formula_plan(with_components(
        "sum_3y(dividends_paid) / sum_3y(operating_cash_flow - capex)", xbrl=["us-gaap:PaymentsOfDividends"],
        dividends_paid=("USD", ["us-gaap:PaymentsOfDividendsCommonStock"]),
        capex=("USD", ["us-gaap:PaymentsToAcquireProductiveAssets"])))
    assert plan.quantities["dividends_paid"].concepts == ("us-gaap:PaymentsOfDividendsCommonStock",
                                                          "us-gaap:PaymentsOfDividends")
    assert plan.quantities["capex"] == VOCABULARY["capex"]
    assert plan.notes == ["us-gaap:PaymentsToAcquireProductiveAssets in components.capex.xbrl is not a candidate of "
                          "capex in the vocabulary, so it is not read"]
    # the component's unit does not change what a vocabulary name is
    capex = ("%", ["us-gaap:PaymentsToAcquirePropertyPlantAndEquipment"])
    assert computable(with_components("capex / revenue", capex=capex)) == (True, "")


def test_a_component_name_is_read_from_its_own_concepts():
    ok, notes = computable(with_components("membership_income / total_revenue", unit="%", frequency="quarter",
                                           membership_income=("USD", ["us-gaap:OtherIncome"])))
    assert ok and notes == ("membership_income is read from components.membership_income.xbrl (us-gaap:OtherIncome); "
                            "whether it is a flow or a balance is decided from the facts when it is read")
    shares = ("shares", ["us-gaap:WeightedAverageNumberOfSharesOutstandingBasic"])
    plan = formula_plan(with_components("net_income / weighted_shares", unit="USD/shares", weighted_shares=shares))
    assert plan.quantities["weighted_shares"].kind == "shares" and plan.quantities["weighted_shares"].instant is None
    assert plan.result == "per_share"


@pytest.mark.parametrize("formula,components,reason", [
    ("recurring / revenue", {"recurring": ("USD", None)},
     "unknown quantity name 'recurring' (components.recurring lists no xbrl concepts): a name is in the vocabulary of "
     "SPEC 9.1, or is a component of the definition that lists xbrl concepts"),
    ("membership_incom / revenue", {"membership_income": ("USD", ["us-gaap:OtherIncome"])},
     "unknown quantity name 'membership_incom' (did you mean membership_income?)"),
    ("churn / revenue", {"churn": ("%", ["us-gaap:Foo"])},
     "components.churn has unit '%': a name read from its component is an amount of money (a currency), a share count "
     "(shares) or a per-share amount (<currency>/shares)"),
    ("store_count", {"store_count": ("stores", ["us-gaap:NumberOfStores"])},
     "components.store_count has unit 'stores'"),
    ("sum_3y(weighted_shares)",
     {"weighted_shares": ("shares", ["us-gaap:WeightedAverageNumberOfSharesOutstandingBasic"])},
     "sum_3y() adds up amounts of money, but weighted_shares is a share count"),
    ("membership_income", {"membership_income": ("USD", ["us-gaap:OtherIncome"])},
     "the formula gives an amount of money, but unit '%' is not a currency"),
])
def test_components_that_cannot_be_read(formula, components, reason):
    ok, why = computable(with_components(formula, **components))
    assert not ok and reason in why, why


# ---------------------------------------------------------------------------------------------------- the engine

# A calendar-year company. Each filing reports its own period: a 10-Q reports year-to-date flows (and the quarter
# itself for income statement lines) and quarter-end balances; a 10-K reports the year. A23K has the year 2023 only.
FILINGS = {(2023, 4): ("A23K", "10-K", "FY", "2024-02-15"), (2024, 1): ("A24Q1", "10-Q", "Q1", "2024-05-01"),
           (2024, 2): ("A24Q2", "10-Q", "Q2", "2024-08-01"), (2024, 3): ("A24Q3", "10-Q", "Q3", "2024-11-01"),
           (2024, 4): ("A24K", "10-K", "FY", "2025-02-15"), (2025, 1): ("A25Q1", "10-Q", "Q1", "2025-05-01"),
           (2025, 2): ("A25Q2", "10-Q", "Q2", "2025-08-01"), (2025, 3): ("A25Q3", "10-Q", "Q3", "2025-11-01"),
           (2025, 4): ("A25K", "10-K", "FY", "2026-02-15"), (2026, 1): ("A26Q1", "10-Q", "Q1", "2026-05-01"),
           (2026, 2): ("A26Q2", "10-Q", "Q2", "2026-08-01")}
QUARTER_END = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}
QUARTER_START = {1: "01-01", 2: "04-01", 3: "07-01", 4: "10-01"}


def row(val, start, end, period):
    accn, form, fp, filed = FILINGS[period]
    out = {"end": end, "val": val, "accn": accn, "form": form, "fy": period[0], "fp": fp, "filed": filed}
    if start:
        out["start"] = start
    return out


def flow(quarters, *, quarterly=False, skip=()):
    """Rows of a flow given by quarter: year-to-date figures in 10-Qs (and the quarter itself when ``quarterly``),
    the year in 10-Ks; a (year, quarter) in ``skip`` was not tagged in its filing."""
    rows = []
    for (year, q), _ in sorted(quarters.items()):
        if (year, q) in skip:
            continue
        ytd = sum(quarters[(year, k)] for k in range(1, q + 1))
        rows.append(row(ytd, f"{year}-01-01", f"{year}-{QUARTER_END[q]}", (year, q)))
        if quarterly and q < 4:
            rows.append(row(quarters[(year, q)], f"{year}-{QUARTER_START[q]}", f"{year}-{QUARTER_END[q]}", (year, q)))
    return rows


def annual(years):
    return [row(v, f"{y}-01-01", f"{y}-12-31", (y, 4)) for y, v in years.items()]


def balance(values):
    return [row(v, None, f"{y}-{QUARTER_END[q]}", (y, q)) for (y, q), v in values.items()]


def by_quarter(values_by_year):
    return {(y, q + 1): v for y, values in values_by_year.items() for q, v in enumerate(values)}


REVENUE = by_quarter({2024: [100, 110, 120, 130], 2025: [120, 130, 140, 150], 2026: [150, 160]})
OCF = by_quarter({2024: [30, 40, 35, 45], 2025: [32, 42, 38, 50], 2026: [40, 44]})
CAPEX = by_quarter({2024: [10, 10, 12, 13], 2025: [11, 12, 13, 14], 2026: [15, 15]})
COMPANY = {"cik": 1, "entityName": "ACME CORP", "facts": {"dei": {
    "EntityCommonStockSharesOutstanding": {"units": {"shares": [  # cover-page facts are dated after the period
        {"end": "2026-07-25", "val": 1000, "accn": "A26Q2", "form": "10-Q", "fy": 2026, "fp": "Q2",
         "filed": "2026-08-01"},
    ]}}}, "us-gaap": {
    "Revenues": {"units": {"USD": flow(REVENUE, quarterly=True) + annual({2023: 400})}},
    "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": flow(OCF) + annual({2023: 140})}},
    "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": flow(CAPEX, skip={(2025, 3)})
                                                                     + annual({2023: 40})}},
    "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": balance({p: 500 + 10 * i
                                                                        for i, p in enumerate(FILINGS)})}},
    "LongTermDebt": {"units": {"USD": balance({p: 800 for p in FILINGS})}},
    "NetIncomeLoss": {"units": {"USD": annual({2023: 80, 2024: 90, 2025: 100})}},
    "ProfitLoss": {"units": {"USD": annual({2024: 95, 2025: 105})}},
    "PaymentsForRepurchaseOfCommonStock": {"units": {"USD": annual({2023: 20, 2024: 30, 2025: 40})}},
    "DividendsCommonStockCash": {"units": {"USD": annual({2023: 10, 2024: 11, 2025: 12})}},
    "NetIncomeLossAvailableToCommonStockholdersBasic": {"units": {"USD": annual({2023: 75, 2024: 85, 2025: 95})}},
    "WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": annual({2024: 50, 2025: 40})}},
    "StockholdersEquity": {"units": {"USD": balance({(2024, 4): 300, (2025, 4): 330})}},
}}}


def near(value):
    """Readings carry four decimals."""
    return pytest.approx(value, abs=1e-4)


def compute(formula, periods, unit="%", frequency="quarter", xbrl=None, facts=COMPANY):
    defs = {"m": definition(formula, unit, frequency, xbrl)}
    return {r["period"]: r for r in readings_from_companyfacts(facts, ["m"], periods, "12-31", ticker="ACME",
                                                               definitions=defs)}


def test_quarters_are_derived_from_year_to_date_figures_and_summed():
    got = compute("sum_4q(operating_cash_flow - capex) / sum_4q(revenue)", ["FY2025Q2", "FY2024Q4", "FY2024"])
    # FY2025Q2: OCF 35 + 45 + 32 + 42 = 154, capex 12 + 13 + 11 + 12 = 48, revenue 120 + 130 + 120 + 130 = 500
    assert got["FY2025Q2"]["value"] == near((154 - 48) / 500 * 100)
    assert got["FY2025Q2"]["unit"] == "%"
    basis = got["FY2025Q2"]["basis"]
    assert basis.startswith("sum_4q(operating_cash_flow - capex) / sum_4q(revenue) = ((35 - 12) + (45 - 13) + "
                            "(32 - 11) + (42 - 12)) / (120 + 130 + 120 + 130); operating_cash_flow: "
                            "us-gaap:NetCashProvidedByUsedInOperatingActivities: FY2024Q3 = 9M - 6M (105 10-Q A24Q3 - "
                            "70 10-Q A24Q2); FY2024Q4 = FY - 9M (150 10-K A24K - 105 10-Q A24Q3)")
    assert "revenue: us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax" not in basis  # not reported
    assert "revenue: us-gaap:Revenues: FY2024Q3 as reported (10-Q A24Q3)" in basis
    # a fiscal year's trailing four quarters are its own four quarters
    assert got["FY2024"]["value"] == near(got["FY2024Q4"]["value"]) == near((150 - 45) / 460 * 100)
    assert got["FY2025Q2"]["source"].startswith("ACME-XBRL#us-gaap:NetCashProvidedByUsedInOperatingActivities:A24Q3+")


def test_a_missing_quarter_means_no_reading_for_every_period_that_needs_it():
    # capex for the nine months of 2025 was not tagged: Q3 2025 cannot be derived, and neither can Q4 (FY - 9M);
    # every trailing four quarters that includes either has no reading, and nothing is interpolated
    got = compute("sum_4q(operating_cash_flow - capex) / sum_4q(revenue)",
                  ["FY2025Q2", "FY2025Q3", "FY2025Q4", "FY2026Q1", "FY2026Q2", "FY2025"])
    assert set(got) == {"FY2025Q2"}
    year = compute("capex / revenue", ["FY2025"], frequency="year")  # the year itself was reported
    assert year["FY2025"]["value"] == near(50 / 540 * 100)


def test_sums_over_fiscal_years_are_read_for_years_only():
    got = compute("sum_3y(buybacks + common_dividends) / sum_3y(net_income_to_common)",
                  ["FY2025", "FY2025Q4", "FY2024"], frequency="year")
    assert set(got) == {"FY2025"}  # FY2024 would need 2022
    assert got["FY2025"]["value"] == near((20 + 10 + 30 + 11 + 40 + 12) / (75 + 85 + 95) * 100)
    assert "common_dividends: us-gaap:DividendsCommonStockCash" in got["FY2025"]["basis"]  # paid is not tagged


def test_balances_are_read_at_the_period_end():
    got = compute("(debt - cash) / sum_4q(operating_cash_flow)", ["FY2025Q2", "FY2024"], unit="x")
    # cash is 560 at 2025-06-30 and 540 at 2024-12-31; debt is 800 throughout
    assert got["FY2025Q2"]["value"] == near((800 - 560) / (35 + 45 + 32 + 42))
    assert got["FY2024"]["value"] == near((800 - 540) / 150)
    assert "cash: us-gaap:CashAndCashEquivalentsAtCarryingValue: at 2025-06-30 (10-Q A25Q2)" in got["FY2025Q2"]["basis"]
    assert got["FY2025Q2"]["unit"] == "x"


def test_growth_of_an_expression_and_of_one_name():
    got = compute("(operating_cash_flow - capex)_t / (operating_cash_flow - capex)_{t-4q} - 1", ["FY2025Q2", "FY2025"])
    assert got["FY2025Q2"]["value"] == near(((42 - 12) / (40 - 10) - 1) * 100)
    assert got["FY2025"]["value"] == near(((162 - 50) / (150 - 45) - 1) * 100)
    single = compute("revenue_t / revenue_{t-1y} - 1", ["FY2026Q2"])  # no xbrl list: read through the vocabulary
    assert single["FY2026Q2"]["value"] == near((160 / 130 - 1) * 100)


def test_no_reading_on_a_zero_or_negative_base():
    formula = "(operating_cash_flow - capex - revenue)_t / (operating_cash_flow - capex - revenue)_{t-4q} - 1"
    assert computable(definition(formula)) == (True, "")
    assert compute(formula, ["FY2025Q2"]) == {}  # the base, 40 - 10 - 110, is negative


def test_one_concept_per_quantity_within_a_reading():
    # ProfitLoss is listed first but lacks 2023, so a sum over 2023-2025 reads NetIncomeLoss for all three years
    got = compute("sum_3y(operating_cash_flow - capex) / sum_3y(net_income)", ["FY2025"], frequency="year",
                  xbrl=["us-gaap:ProfitLoss", "us-gaap:NetIncomeLoss"])
    assert got["FY2025"]["value"] == near((140 - 40 + 150 - 45 + 162 - 50) / (80 + 90 + 100) * 100)
    assert "net_income: us-gaap:NetIncomeLoss" in got["FY2025"]["basis"]
    one_year = compute("sum_1y(operating_cash_flow) / sum_1y(net_income)", ["FY2025"], frequency="year",
                       xbrl=["us-gaap:ProfitLoss"])
    assert one_year["FY2025"]["value"] == near(162 / 105 * 100)
    assert "net_income: us-gaap:ProfitLoss" in one_year["FY2025"]["basis"]  # listed, and it has 2025


def test_a_definition_is_read_for_its_frequency_and_longer_periods():
    yearly = compute("operating_cash_flow / revenue", ["FY2025Q2", "FY2025H1", "FY2025"], frequency="year")
    assert set(yearly) == {"FY2025"}
    quarterly = compute("operating_cash_flow / revenue", ["FY2025Q2", "FY2025H1", "FY2025"])
    assert set(quarterly) == {"FY2025Q2", "FY2025H1", "FY2025"}
    assert quarterly["FY2025H1"]["value"] == near((32 + 42) / (120 + 130) * 100)


def test_amounts_and_units():
    got = compute("operating_cash_flow - capex", ["FY2025Q1"], unit="USD million")
    assert got["FY2025Q1"]["value"] == 21 and got["FY2025Q1"]["unit"] == "USD"  # in the reporting currency
    per_share = compute("net_income / diluted_shares", ["FY2025"], unit="USD/shares", frequency="year")
    assert per_share["FY2025"]["value"] == near(2.5) and per_share["FY2025"]["unit"] == "USD/shares"
    times = compute("revenue / operating_cash_flow", ["FY2025Q1"], unit="×")
    assert times["FY2025Q1"]["unit"] == "x" and times["FY2025Q1"]["value"] == near(120 / 32)


def test_unknown_names_and_bad_definitions_give_no_reading():
    assert compute("net_incom / revenue", ["FY2025"], frequency="year") == {}
    assert compute("sum_4q(cash)", ["FY2025"], unit="USD") == {}


def test_readings_are_a_valid_readings_document():
    out = readings_from_companyfacts(COMPANY, ["a", "b"], ["FY2025Q2", "FY2024"], "12-31", ticker="ACME", definitions={
        "a": definition("sum_4q(operating_cash_flow - capex) / sum_4q(revenue)"),
        "b": definition("(debt - cash) / sum_4q(operating_cash_flow)", "x")})
    assert len(out) == 4
    assert readings.problems({"company": "ACME", "as_of": "2026-09-01", "readings": out}) == []


def test_typographic_formulas_read_as_their_ascii_twins():
    plain = compute("sum_4q(operating_cash_flow - capex) / sum_4q(revenue)", ["FY2025Q2"])["FY2025Q2"]
    typographic = compute("sum_4q(operating_cash_flow − capex) ÷ sum_4q(revenue)", ["FY2025Q2"])["FY2025Q2"]
    assert typographic["value"] == plain["value"] and typographic["source"] == plain["source"]
    # the basis opens with the formula as written; the values follow in ASCII
    assert typographic["basis"] == plain["basis"].replace(
        "sum_4q(operating_cash_flow - capex) / sum_4q(revenue) = ",
        "sum_4q(operating_cash_flow − capex) ÷ sum_4q(revenue) = ", 1)
    # the growth of one quantity over the definition's own xbrl list keeps its 0.4.0 reading
    legacy = compute("revenue_t ÷ revenue_{t−4q} − 1", ["FY2025Q2"], xbrl=["us-gaap:Revenues"])["FY2025Q2"]
    assert legacy == compute("revenue_t / revenue_{t-4q} - 1", ["FY2025Q2"], xbrl=["us-gaap:Revenues"])["FY2025Q2"]
    assert computable(definition("revenue_t ÷ revenue_{t−4q} − 1", xbrl=["us-gaap:Revenues"])) == (True, "")


# ---------------------------------------------------------------------------------------------------- avg()


def test_avg_reads_a_balance_at_the_start_and_at_the_end_of_the_period():
    # cash is 500 at 2023-12-31, 510 at 2024-03-31, 540 at 2024-12-31, 550 at 2025-03-31, 560 at 2025-06-30 and 580
    # at 2025-12-31; no filing reports it at 2023-09-30
    got = compute("avg(cash)", ["FY2025Q2", "FY2025H1", "FY2025", "FY2024Q1", "FY2023Q4"], unit="USD")
    assert {p: r["value"] for p, r in got.items()} == {"FY2025Q2": 555, "FY2025H1": 550, "FY2025": 560,
                                                      "FY2024Q1": 505}  # FY2023Q4 lacks its opening balance
    assert got["FY2025Q2"]["basis"] == ("avg(cash) = (550 + 560) / 2; cash: "
                                        "us-gaap:CashAndCashEquivalentsAtCarryingValue: at 2025-03-31 (10-Q A25Q1); "
                                        "at 2025-06-30 (10-Q A25Q2)")
    assert got["FY2025"]["basis"].startswith("avg(cash) = (540 + 580) / 2; ")


def test_avg_in_a_return_on_average_equity_and_in_a_growth_form():
    # equity is 300 at the end of 2024 and 330 at the end of 2025; none is reported at the end of 2023
    got = compute("net_income / avg(equity)", ["FY2025", "FY2024"], frequency="year")
    assert set(got) == {"FY2025"}
    assert got["FY2025"]["value"] == near(100 / 315 * 100)
    assert got["FY2025"]["basis"].startswith("net_income / avg(equity) = 100 / ((300 + 330) / 2); ")
    growth = compute("avg(cash)_t / avg(cash)_{t-4q} - 1", ["FY2025Q2"])
    assert growth["FY2025Q2"]["value"] == near((555 / 515 - 1) * 100)  # 515 = (510 + 520) / 2, a year earlier
    sums = compute("avg(debt - cash) / sum_4q(operating_cash_flow)", ["FY2025Q2"], unit="x")
    assert sums["FY2025Q2"]["basis"].startswith(
        "avg(debt - cash) / sum_4q(operating_cash_flow) = ((800 - 550) + (800 - 560)) / 2 / (35 + 45 + 32 + 42); ")


# ---------------------------------------------------------------------------------------------------- components


def read_definition(defn, periods, facts=COMPANY):
    return {r["period"]: r for r in readings_from_companyfacts(facts, ["m"], periods, "12-31", ticker="ACME",
                                                               definitions={"m": defn})}


def test_a_component_name_is_a_flow_or_a_balance_as_its_facts_show():
    repurchased = {"repurchased": ("USD", ["us-gaap:PaymentsForRepurchaseOfCommonStock"])}
    defn = with_components("sum_3y(repurchased) / sum_3y(net_income)", **repurchased)
    assert computable(defn, COMPANY)[0]
    got = read_definition(defn, ["FY2025"])
    assert got["FY2025"]["value"] == near((20 + 30 + 40) / (80 + 90 + 100) * 100)
    assert ("repurchased: us-gaap:PaymentsForRepurchaseOfCommonStock: FY2023 as reported (10-K A23K)"
            in got["FY2025"]["basis"])
    borrowings = {"borrowings": ("USD", ["us-gaap:Foo", "us-gaap:LongTermDebt"])}  # a concept without facts is passed
    got = read_definition(with_components("avg(borrowings) / avg(cash)", unit="x", frequency="quarter", **borrowings),
                          ["FY2025Q2"])
    assert got["FY2025Q2"]["value"] == near(800 / 555)
    assert "borrowings: us-gaap:LongTermDebt: at 2025-03-31 (10-Q A25Q1)" in got["FY2025Q2"]["basis"]


@pytest.mark.parametrize("formula,unit,components,reason", [
    ("sum_4q(borrowings)", "USD", {"borrowings": ("USD", ["us-gaap:LongTermDebt"])},
     "sum_4q() adds up flows over periods, but borrowings is a balance at a date"),
    ("avg(repurchased)", "USD", {"repurchased": ("USD", ["us-gaap:PaymentsForRepurchaseOfCommonStock"])},
     "avg() averages a balance at the start and at the end of a period, but repurchased is a flow over a period"),
    ("mixed", "USD", {"mixed": ("USD", ["us-gaap:LongTermDebt", "us-gaap:PaymentsForRepurchaseOfCommonStock"])},
     "mixed: its concepts disagree: us-gaap:PaymentsForRepurchaseOfCommonStock is reported over periods, as a flow, "
     "and us-gaap:LongTermDebt at dates, as a balance"),
    ("ghost", "USD", {"ghost": ("USD", ["us-gaap:Nothing", "us-gaap:NothingElse"])},
     "ghost: no periodic report has a fact of us-gaap:Nothing or us-gaap:NothingElse in USD"),
    ("counted", "shares", {"counted": ("shares", ["us-gaap:LongTermDebt"])},  # its facts are in USD
     "counted: no periodic report has a fact of us-gaap:LongTermDebt in shares"),
])
def test_a_component_name_the_facts_cannot_settle(formula, unit, components, reason):
    """computable() accepts each of these on its own, since a component's kind is decided only from the facts. This
    company's facts make the name a balance summed or a flow averaged, or decide nothing, so for it the definition is
    not computable, with the reason, and has no reading."""
    defn = with_components(formula, unit=unit, frequency="quarter", **components)
    ok, notes = computable(defn)
    assert ok and "is decided from the facts when it is read" in notes
    assert computable(defn, COMPANY) == (False, reason)
    assert read_definition(defn, ["FY2025Q2", "FY2025"]) == {}


# ---------------------------------------------------------------------------------------------------- net sales

# A retailer whose net sales sit beside membership income. Revenue from contracts with customers carries its net
# sales; us-gaap:Revenues, when tagged, carries net sales plus membership income, or the same figure.
NET_SALES = by_quarter({2024: [100, 110, 120, 130], 2025: [120, 130, 140, 150]})
MEMBERSHIP = by_quarter({2024: [5, 5, 5, 5], 2025: [6, 6, 6, 6]})


def club(total):
    tags = {"RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": flow(NET_SALES, quarterly=True)}}}
    if total == "net sales plus membership":
        tags["Revenues"] = {"units": {"USD": flow({p: v + MEMBERSHIP[p] for p, v in NET_SALES.items()},
                                                  quarterly=True)}}
    elif total == "the same figure":
        tags["Revenues"] = {"units": {"USD": flow(NET_SALES, quarterly=True)}}
    return {"cik": 3, "entityName": "CLUB", "facts": {"us-gaap": tags}}


def test_net_sales_are_read_where_the_facts_show_them_beside_a_larger_total():
    got = compute("net_sales", ["FY2025", "FY2025Q2", "FY2025Q4"], unit="USD", facts=club("net sales plus membership"))
    assert {p: r["value"] for p, r in got.items()} == {"FY2025": 540, "FY2025Q2": 130, "FY2025Q4": 150}
    assert got["FY2025Q2"]["basis"] == (
        "net_sales = 130; net_sales: us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax: FY2025Q2 as "
        "reported (10-Q A25Q2), below us-gaap:Revenues 136")
    assert got["FY2025Q4"]["basis"].endswith(  # each fact the fourth quarter is derived from is checked
        "FY2025Q4 = FY - 9M (540 10-K A25K - 390 10-Q A25Q3), below us-gaap:Revenues 564 and 408")
    assert got["FY2025"]["source"] == "ACME-XBRL#us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax:A25K"


@pytest.mark.parametrize("total", ["the same figure", None])
def test_net_sales_never_fall_back_to_total_revenue(total):
    """Where revenue from contracts with customers equals the total, or is the only revenue tagged, the facts cannot
    tell it from total revenue, so net_sales has no reading; revenue and total_revenue still read it."""
    facts = club(total)
    assert compute("net_sales", ["FY2025", "FY2025Q2", "FY2025Q4"], unit="USD", facts=facts) == {}
    for name in ("revenue", "total_revenue"):
        assert compute(name, ["FY2025"], unit="USD", facts=facts)["FY2025"]["value"] == 540
    assert computable(definition("capex / net_sales", frequency="year"), facts) == (True, "")


def test_net_sales_named_as_such_are_read_as_they_are():
    legacy = {"cik": 4, "facts": {"us-gaap": {
        "SalesRevenueNet": {"units": {"USD": annual({2024: 460})}},
        "Revenues": {"units": {"USD": annual({2024: 460})}}}}}  # a single revenue line, tagged twice
    got = compute("net_sales", ["FY2024"], unit="USD", facts=legacy)
    assert got["FY2024"]["value"] == 460
    assert got["FY2024"]["basis"].endswith("net_sales: us-gaap:SalesRevenueNet: FY2024 as reported (10-K A24K)")


# ---------------------------------------------------------------------------------------------------- the calendar


def test_a_december_year_end_is_unchanged():
    facts = Facts(COMPANY, (12, 31))
    assert facts.ends and all(end == quarter_end_date(y, q, (12, 31)) for (y, q), end in facts.ends.items())
    assert facts.dates(Fiscal(2025, "quarter", 3)) == (dt.date(2025, 7, 1), dt.date(2025, 9, 30))


def week_company():
    """A retailer whose quarters are 12, 12, 12 and 16 weeks long, its year ending on the Sunday nearest August 31.

    The second filing's fy names the wrong year and a third filing's fp the wrong quarter: neither is used.
    """
    def r(val, start, end, accn, form, fp, filed, fy=2026):
        out = {"end": end, "val": val, "accn": accn, "form": form, "fy": fy, "fp": fp, "filed": filed}
        if start:
            out["start"] = start
        return out

    revenue = [
        r(50, "2024-09-02", "2025-08-31", "K25", "10-K", "FY", "2025-10-08", 2025),
        r(10, "2025-09-01", "2025-11-23", "Q1", "10-Q", "Q1", "2025-12-17"),
        r(11, "2025-11-24", "2026-02-15", "Q2", "10-Q", "Q2", "2026-03-11", 2025),  # fy names the wrong year
        r(21, "2025-09-01", "2026-02-15", "Q2", "10-Q", "Q2", "2026-03-11", 2025),
        r(12, "2026-02-16", "2026-05-10", "Q3", "10-Q", "Q3", "2026-06-03"),
        r(33, "2025-09-01", "2026-05-10", "Q3", "10-Q", "Q3", "2026-06-03"),
        r(52, "2025-09-01", "2026-08-30", "K26", "10-K", "FY", "2026-10-07"),
        r(99, "2026-08-31", "2026-11-22", "BAD", "10-Q", "Q2", "2026-12-16", 2027),  # Q1 2027 labelled Q2
    ]
    cash = [r(5, None, "2026-02-15", "Q2", "10-Q", "Q2", "2026-03-11"),
            r(6, None, "2026-05-10", "Q3", "10-Q", "Q3", "2026-06-03")]
    return {"cik": 2, "facts": {"us-gaap": {"Revenues": {"units": {"USD": revenue}},
                                            "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": cash}}}}}


def test_quarters_end_where_the_filings_say():
    facts = Facts(week_company(), fiscal_year_end("08-30"))
    assert facts.ends == {(2025, 4): dt.date(2025, 8, 31), (2026, 1): dt.date(2025, 11, 23),
                          (2026, 2): dt.date(2026, 2, 15), (2026, 3): dt.date(2026, 5, 10),
                          (2026, 4): dt.date(2026, 8, 30)}  # BAD lies 98 days from any second quarter's end
    assert facts.dates(Fiscal(2026, "quarter", 3)) == (dt.date(2026, 2, 16), dt.date(2026, 5, 10))
    assert facts.dates(Fiscal(2026, "quarter", 4)) == (dt.date(2026, 5, 11), dt.date(2026, 8, 30))
    assert facts.dates(Fiscal(2027, "quarter", 1)) == (dt.date(2026, 8, 31), dt.date(2026, 11, 30))  # implied


def test_twelve_and_sixteen_week_quarters_are_read_and_derived():
    got = {(r["metric"], r["period"]): r for r in readings_from_companyfacts(
        week_company(), ["q"], ["FY2026Q1", "FY2026Q2", "FY2026Q3", "FY2026Q4", "FY2026H2"], "08-30", ticker="W",
        definitions={"q": definition("revenue", unit="USD")})}
    assert {k[1]: v["value"] for k, v in got.items()} == {"FY2026Q1": 10, "FY2026Q2": 11, "FY2026Q3": 12,
                                                          "FY2026Q4": 19, "FY2026H2": 31}
    assert got[("q", "FY2026Q4")]["basis"] == (
        "revenue = 19; revenue: us-gaap:Revenues: FY2026Q4 = FY - 9M (52 10-K K26 - 33 10-Q Q3)")
    ratio = readings_from_companyfacts(week_company(), ["c"], ["FY2026Q3"], "08-30", ticker="W", definitions={
        "c": definition("cash / revenue", unit="x")})
    assert ratio[0]["value"] == near(6 / 12)
