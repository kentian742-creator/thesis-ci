"""Compute ``data: xbrl`` metrics from an SEC companyfacts document (SPEC 4.5, 9).

``readings_from_companyfacts(companyfacts, metric_ids, periods, fiscal_year_end)`` is a pure function: it reads the
JSON the SEC serves at ``api/xbrl/companyfacts/CIK##########.json`` (already downloaded) and returns readings
(``readings.py``) for the metrics and fiscal periods asked for: the metrics of ``spec/metrics.yml``, and the
formulas of tests' own ``metric_def`` (SPEC 9.1). A metric it cannot compute is left out; nothing is estimated.

How values are taken:

- Only facts from periodic reports count: 10-K, 10-Q, 20-F, 40-F (and their amendments and transition reports).
  Facts from 8-Ks and other forms are ignored.
- A fact's period comes from its start and end dates, matched within 10 days to the company's fiscal calendar, not
  from the filing's ``fy`` / ``fp`` fields, which describe the filing, not the fact.
- The fiscal calendar comes from the filings. A fiscal quarter ends on the date that the company's 10-Q or 10-K for
  it reports: the most common end date among that filing's facts. The filing is placed by its ``fp`` (Q1, Q2, Q3;
  FY for an annual report) and that date, never by its ``fy``, which can name the filing's year rather than the
  fact's. A quarter that no filing covers ends on the date ``fiscal_year_end`` implies, and so does one whose
  filing's date lies more than 46 days from it (a mislabelled ``fp``). So Costco's 12-week quarters (to 2026-02-15,
  say) are read as filed, not as quarters that end with a month.
- When several filings report the same span, the most recently filed value is used, so a restated comparative in a
  later filing wins over the original figure.
- Flows of a quarter or a half that no filing reports on their own (cash flow statements in 10-Qs are
  year-to-date; the fourth quarter is in no filing) are derived from year-to-date figures: Q2 = 6M - Q1,
  Q3 = 9M - 6M, Q4 = FY - 9M, H2 = FY - H1. Share counts and per-share amounts are never derived this way.
- Candidate concepts are tried in the registry's order; the first one that has every value a reading needs is
  used, so a reading never mixes two concepts for one quantity.
- Monetary facts are read in one currency: the ``currency`` argument, or else the currency with the most facts in
  the document (a foreign private issuer's reporting currency, not its convenience translation into USD).
- Growth and ratios are not computed on a zero or negative base (the result would carry no meaning).

A ``metric_def``'s formula is parsed by ``formula.py`` and read through a vocabulary of quantity names
(``VOCABULARY``, ``SYNONYMS``): each name has candidate concepts in order of preference, and is either a flow over a
period or a balance at its end. The concepts a definition lists in ``xbrl`` are tried first. ``computable(definition)``
says whether a definition can be computed at all, and why not.

Each reading's ``source`` is ``<TICKER>-XBRL#<concept>:<accession>``, with ``+`` joining further concept:accession
pairs when the value rests on several facts; ``basis`` spells out the formula with the values used.
"""

from __future__ import annotations

import datetime as dt
import difflib
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

from . import contract, formula
from .formula import FormulaError
from .periods import (QUARTERS_PER, Fiscal, fiscal_year_end as parse_fye, from_quarter_index, parse_fiscal,
                      quarter_end_date, quarter_index)
from .readings import currency as readings_currency, normalize_unit

PERIODIC_FORMS = {"10-K", "10-Q", "20-F", "40-F", "10-KT", "10-QT", "10-K/A", "10-Q/A", "20-F/A", "40-F/A",
                  "10-KT/A", "10-QT/A"}
QUARTERLY_FORMS = {"10-Q", "10-Q/A"}
ANNUAL_FORMS = {"10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A"}  # transition reports do not set the calendar
FILING_QUARTERS = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "FY": 4}  # a filing's fp; some 10-Ks write Q4
TOLERANCE = dt.timedelta(days=10)
CALENDAR_LIMIT = dt.timedelta(days=46)  # a filing's period end this far from the implied date is mislabelled
CURRENCY_UNIT = re.compile(r"^[A-Z]{3}$")
GROWTH_FORMULA = re.compile(r"^\s*([a-z][a-z0-9_]*)_t\s*/\s*\1_\{t-(4q|1y)\}\s*-\s*1\s*$")


@dataclass(frozen=True)
class Quantity:
    """One quantity a formula uses, with its candidate concepts in order of preference."""

    name: str
    concepts: tuple[str, ...]
    kind: str  # "money" | "shares" | "per_share"
    instant: bool = False  # a balance at a date; otherwise a flow over a period


REVENUE = Quantity("revenue", ("us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", "us-gaap:Revenues",
                               "ifrs-full:Revenue"), "money")
GROSS_PROFIT = Quantity("gross_profit", ("us-gaap:GrossProfit", "ifrs-full:GrossProfit"), "money")
OPERATING_INCOME = Quantity("operating_income", ("us-gaap:OperatingIncomeLoss",
                                                 "ifrs-full:ProfitLossFromOperatingActivities"), "money")
OCF = Quantity("operating_cash_flow", ("us-gaap:NetCashProvidedByUsedInOperatingActivities",
                                       "ifrs-full:CashFlowsFromUsedInOperatingActivities"), "money")
CAPEX = Quantity("capex", ("us-gaap:PaymentsToAcquirePropertyPlantAndEquipment",
                           "ifrs-full:PurchaseOfPropertyPlantAndEquipmentClassifiedAsInvestingActivities"), "money")
NET_INCOME = Quantity("net_income", ("us-gaap:NetIncomeLoss", "ifrs-full:ProfitLoss"), "money")
DILUTED_SHARES = Quantity("diluted_shares", ("us-gaap:WeightedAverageNumberOfDilutedSharesOutstanding",
                                             "ifrs-full:WeightedAverageNumberOfOrdinarySharesOutstandingDiluted"), "shares")
BUYBACKS = Quantity("buybacks", ("us-gaap:PaymentsForRepurchaseOfCommonStock",
                                 "ifrs-full:PaymentsToAcquireOrRedeemEntitysShares"), "money")
DIVIDENDS = Quantity("dividends", ("us-gaap:PaymentsOfDividends", "us-gaap:PaymentsOfDividendsCommonStock"), "money")
EQUITY = Quantity("equity", ("us-gaap:StockholdersEquity", "ifrs-full:Equity"), "money", instant=True)
DEBT = Quantity("debt", ("us-gaap:LongTermDebt",), "money", instant=True)
CASH = Quantity("cash", ("us-gaap:CashAndCashEquivalentsAtCarryingValue", "ifrs-full:CashAndCashEquivalents"), "money",
                instant=True)
SHORT_TERM_INVESTMENTS = Quantity("short_term_investments", ("us-gaap:ShortTermInvestments",), "money", instant=True)
INCOME_TAX = Quantity("income_tax", ("us-gaap:IncomeTaxExpenseBenefit",), "money")
PRETAX_INCOME = Quantity("pretax_income", (
    "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
), "money")
DEPRECIATION = Quantity("d_and_a", ("us-gaap:DepreciationDepletionAndAmortization",), "money")
RPO = Quantity("rpo", ("us-gaap:RevenueRemainingPerformanceObligation",), "money", instant=True)
PROVISION = Quantity("provision", ("us-gaap:ProvisionForLoanLeaseAndOtherLosses",
                                   "us-gaap:ProvisionForLoanAndLeaseLosses"), "money")
INTEREST_EXPENSE = Quantity("interest_expense", ("us-gaap:InterestExpense", "us-gaap:InterestExpenseOperating"), "money")
INTEREST_INCOME = Quantity("interest_income", ("us-gaap:InterestAndDividendIncomeOperating",), "money")
TOTAL_ASSETS = Quantity("total_assets", ("us-gaap:Assets",), "money", instant=True)

# The vocabulary of metric definitions' formulas (SPEC 9.1): every name a formula may use, with its candidate concepts
# in order of preference. It reuses the registry's quantities above; where a name needs more candidates than the
# registry formulas use, it has its own entry, so that the registry's readings do not change.
VOCABULARY: dict[str, Quantity] = {q.name: q for q in (
    REVENUE,
    Quantity("total_revenue", ("us-gaap:Revenues", "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
                               "ifrs-full:Revenue"), "money"),
    Quantity("revenue_net_of_interest_expense", ("us-gaap:RevenuesNetOfInterestExpense",), "money"),
    GROSS_PROFIT,
    OPERATING_INCOME,
    PRETAX_INCOME,
    INCOME_TAX,
    Quantity("net_income", ("us-gaap:NetIncomeLoss", "us-gaap:ProfitLoss", "ifrs-full:ProfitLoss"), "money"),
    Quantity("net_income_to_common", ("us-gaap:NetIncomeLossAvailableToCommonStockholdersBasic",), "money"),
    OCF,
    CAPEX,
    Quantity("stock_based_compensation", ("us-gaap:ShareBasedCompensation",
                                          "us-gaap:AllocatedShareBasedCompensationExpense"), "money"),
    DEPRECIATION,
    BUYBACKS,
    DIVIDENDS,
    Quantity("common_dividends", ("us-gaap:PaymentsOfDividendsCommonStock", "us-gaap:DividendsCommonStockCash"),
             "money"),
    Quantity("provisions", ("us-gaap:ProvisionForLoanLeaseAndOtherLosses", "us-gaap:ProvisionForLoanAndLeaseLosses",
                            "us-gaap:ProvisionForLoanLossesExpensed"), "money"),
    INTEREST_EXPENSE,
    INTEREST_INCOME,
    CASH,
    SHORT_TERM_INVESTMENTS,
    TOTAL_ASSETS,
    EQUITY,
    Quantity("total_equity", ("us-gaap:StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
                              "us-gaap:StockholdersEquity", "ifrs-full:Equity"), "money", instant=True),
    DEBT,
    Quantity("long_term_debt_noncurrent", ("us-gaap:LongTermDebtNoncurrent",), "money", instant=True),
    Quantity("long_term_debt_current", ("us-gaap:LongTermDebtCurrent",), "money", instant=True),
    RPO,
    DILUTED_SHARES,
    Quantity("eps_diluted", ("us-gaap:EarningsPerShareDiluted", "ifrs-full:DilutedEarningsLossPerShare"), "per_share"),
    Quantity("eps_basic", ("us-gaap:EarningsPerShareBasic", "ifrs-full:BasicEarningsLossPerShare"), "per_share"),
)}
SYNONYMS: dict[str, str] = {
    "revenues": "revenue",
    "total_revenues": "total_revenue",
    "revenues_net_of_interest_expense": "revenue_net_of_interest_expense",
    "operating_profit": "operating_income", "income_from_operations": "operating_income",
    "pretax_profit": "pretax_income", "income_before_taxes": "pretax_income",
    "income_before_income_taxes": "pretax_income",
    "income_taxes": "income_tax", "income_tax_expense": "income_tax",
    "net_profit": "net_income", "net_earnings": "net_income",
    "net_income_available_to_common": "net_income_to_common",
    "net_income_attributable_to_common": "net_income_to_common",
    "cash_from_operations": "operating_cash_flow", "ocf": "operating_cash_flow",
    "capital_expenditure": "capex", "capital_expenditures": "capex",
    "share_based_compensation": "stock_based_compensation", "sbc": "stock_based_compensation",
    "depreciation_and_amortization": "d_and_a",
    "share_repurchases": "buybacks", "repurchases": "buybacks",
    "dividends_paid": "dividends",
    "common_stock_dividends": "common_dividends",
    "provision": "provisions", "provision_for_credit_losses": "provisions",
    "provisions_for_credit_losses": "provisions",
    "cash_and_equivalents": "cash", "cash_and_cash_equivalents": "cash",
    "assets": "total_assets",
    "stockholders_equity": "equity", "shareholders_equity": "equity",
    "long_term_debt": "debt",
    "current_portion_of_long_term_debt": "long_term_debt_current",
    "remaining_performance_obligations": "rpo",
    "weighted_average_diluted_shares": "diluted_shares",
    "diluted_eps": "eps_diluted", "basic_eps": "eps_basic",
}


@dataclass(frozen=True)
class Fact:
    concept: str
    value: float
    start: dt.date | None
    end: dt.date
    accn: str
    form: str
    filed: dt.date


@dataclass
class Value:
    """A number taken from the facts, with the facts it rests on and how it was derived."""

    value: float
    facts: list[Fact]
    how: str  # e.g. "FY2026Q3 3M" or "FY2025Q4 = FY - 9M"


@dataclass
class Result:
    value: float
    unit: str
    basis: str
    facts: list[Fact] = field(default_factory=list)


def _date(value: Any) -> dt.date | None:
    try:
        return dt.date.fromisoformat(value) if isinstance(value, str) else None
    except ValueError:
        return None


def _near(a: dt.date | None, b: dt.date) -> bool:
    return a is not None and abs(a - b) <= TOLERANCE


def _fmt(value: float) -> str:
    return f"{value:,.0f}" if abs(value) >= 1000 else f"{value:.6g}"


@dataclass
class _Filing:
    """What one filing's facts say about the filing: its form, its fiscal period (fp) and their end dates."""

    forms: Counter = field(default_factory=Counter)
    fps: Counter = field(default_factory=Counter)
    ends: Counter = field(default_factory=Counter)
    filed: dt.date = dt.date.max

    def add(self, fact: Fact, fp: Any) -> None:
        self.forms[fact.form] += 1
        self.fps[str(fp)] += 1
        self.ends[fact.end] += 1
        self.filed = min(self.filed, fact.filed)


class Facts:
    """The periodic-report facts of one companyfacts document, indexed by concept and unit, and the company's own
    fiscal calendar, taken from its filings."""

    def __init__(self, companyfacts: dict, fye: tuple[int, int], currency: str | None = None):
        self.fye = fye
        self._rows: dict[tuple[str, str], list[Fact]] = defaultdict(list)
        counts: Counter = Counter()
        filings: dict[str, _Filing] = defaultdict(_Filing)
        taxonomies = companyfacts.get("facts") if isinstance(companyfacts, dict) else None
        for taxonomy, concepts in (taxonomies or {}).items():
            for name, body in (concepts or {}).items():
                units = body.get("units") if isinstance(body, dict) else None
                for unit, rows in (units or {}).items():
                    for row in rows or []:
                        fact = self._fact(f"{taxonomy}:{name}", row)
                        if fact is not None:
                            self._rows[(fact.concept, unit)].append(fact)
                            if CURRENCY_UNIT.match(unit):
                                counts[unit] += 1
                            if taxonomy != "dei":  # cover-page facts are dated after the period
                                filings[fact.accn].add(fact, row.get("fp"))
        self.currency = currency or (counts.most_common(1)[0][0] if counts else "USD")
        self.ends = self._calendar(filings)

    def _calendar(self, filings: dict[str, _Filing]) -> dict[tuple[int, int], dt.date]:
        """The last day of each fiscal (year, quarter) that a 10-Q or an annual report covers.

        A filing's own period ends on the most common end date of its facts (its comparatives are fewer), the later
        one on a tie. Its ``fp`` gives the quarter, and the fiscal year is the one whose implied quarter end is nearest
        that date. A filing whose ``fp`` does not fit its form, or whose date lies more than CALENDAR_LIMIT from the
        implied one (a mislabelled ``fp``), is not used; of two filings for one quarter, the first filed sets it.
        """
        ends: dict[tuple[int, int], dt.date] = {}
        for _, filing in sorted(filings.items(), key=lambda item: (item[1].filed, item[0])):
            form = filing.forms.most_common(1)[0][0]
            quarter = FILING_QUARTERS.get(filing.fps.most_common(1)[0][0])
            if quarter is None or (quarter < 4) != (form in QUARTERLY_FORMS) or (quarter == 4) != (form in ANNUAL_FORMS):
                continue  # an fp that does not fit the form, or a transition report
            end = max(filing.ends.items(), key=lambda item: (item[1], item[0]))[0]
            year = min(range(end.year - 1, end.year + 2),
                       key=lambda y: abs(quarter_end_date(y, quarter, self.fye) - end))
            if abs(quarter_end_date(year, quarter, self.fye) - end) <= CALENDAR_LIMIT:
                ends.setdefault((year, quarter), end)
        return ends

    def quarter_end(self, year: int, quarter: int) -> dt.date:
        """The last day of fiscal quarter (year, quarter): as the company's filing for it reports it, else implied by
        ``fiscal_year_end``."""
        return self.ends.get((year, quarter)) or quarter_end_date(year, quarter, self.fye)

    def dates(self, period: Fiscal) -> tuple[dt.date, dt.date]:
        """(first day, last day) of a fiscal period in the company's own calendar."""
        before = from_quarter_index(quarter_index(period.start_quarter) - 1)
        return self.quarter_end(*before) + dt.timedelta(days=1), self.quarter_end(*period.end_quarter)

    @staticmethod
    def _fact(concept: str, row: Any) -> Fact | None:
        if not isinstance(row, dict) or row.get("form") not in PERIODIC_FORMS:
            return None
        val, end, filed = row.get("val"), _date(row.get("end")), _date(row.get("filed"))
        if not isinstance(val, (int, float)) or isinstance(val, bool) or end is None or filed is None:
            return None
        start = _date(row.get("start")) if row.get("start") is not None else None
        return Fact(concept, float(val), start, end, str(row.get("accn") or "?"), str(row.get("form")), filed)

    def unit_for(self, kind: str) -> str:
        return {"money": self.currency, "shares": "shares", "per_share": f"{self.currency}/shares"}[kind]

    def _pick(self, concept: str, kind: str, start: dt.date | None, end: dt.date) -> Fact | None:
        """The most recently filed fact of ``concept`` for exactly this span (an instant when start is None)."""
        rows = [f for f in self._rows.get((concept, self.unit_for(kind)), [])
                if _near(f.end, end) and (f.start is None if start is None else _near(f.start, start))]
        return max(rows, key=lambda f: (f.filed, f.accn)) if rows else None

    def _ytd(self, year: int, quarter: int) -> tuple[dt.date, dt.date]:
        """First and last day of the fiscal year-to-date span ending with (year, quarter)."""
        return self.quarter_end(year - 1, 4) + dt.timedelta(days=1), self.quarter_end(year, quarter)

    def flow(self, concept: str, kind: str, period: Fiscal) -> Value | None:
        """A flow (income or cash flow statement line) over a fiscal period, reported or derived from YTD figures."""
        start, end = self.dates(period)
        fact = self._pick(concept, kind, start, end)
        if fact is not None:
            return Value(fact.value, [fact], f"{period.label} as reported ({fact.form} {fact.accn})")
        first_q = period.start_quarter[1]
        if kind != "money" or first_q == 1:
            return None  # share counts and per-share amounts do not add up; a span from Q1 is a YTD span itself
        year, last_q = period.end_quarter
        whole = self._pick(concept, kind, *self._ytd(year, last_q))
        before = self._pick(concept, kind, *self._ytd(year, first_q - 1))
        if whole is None or before is None:
            return None
        return Value(whole.value - before.value, [whole, before],
                     f"{period.label} = {_span(last_q)} - {_span(first_q - 1)} "
                     f"({_fmt(whole.value)} {whole.form} {whole.accn} - {_fmt(before.value)} {before.form} {before.accn})")

    def stock(self, concept: str, kind: str, period: Fiscal) -> Value | None:
        """A balance (an instant) at the end of a fiscal period."""
        end = self.dates(period)[1]
        fact = self._pick(concept, kind, None, end)
        if fact is None:
            return None
        return Value(fact.value, [fact], f"at {fact.end.isoformat()} ({fact.form} {fact.accn})")

    def first(self, quantity: Quantity, periods: list[Fiscal], stock: bool = False) -> tuple[str, list[Value]] | None:
        """(concept, values) from the first candidate concept that has a value for every period asked for."""
        read = self.stock if stock else self.flow
        for concept in quantity.concepts:
            values = [read(concept, quantity.kind, p) for p in periods]
            if all(v is not None for v in values):
                return concept, values  # type: ignore[return-value]
        return None


def _span(quarter: int) -> str:
    return {1: "3M", 2: "6M", 3: "9M", 4: "FY"}[quarter]


class _Calc:
    """Metric formulas over one Facts index. Each returns a Result, or None when it cannot be computed."""

    def __init__(self, facts: Facts):
        self.f = facts

    # -- building blocks

    def values(self, q: Quantity, periods: list[Fiscal], stock: bool = False) -> tuple[str, list[Value]] | None:
        return self.f.first(q, periods, stock)

    def one(self, q: Quantity, p: Fiscal, stock: bool = False) -> tuple[str, Value] | None:
        got = self.values(q, [p], stock)
        return (got[0], got[1][0]) if got else None

    @staticmethod
    def facts_of(*values: Value) -> list[Fact]:
        return [fact for v in values for fact in v.facts]

    def growth(self, q: Quantity, p: Fiscal, stock: bool = False) -> Result | None:
        """value_t / value_(same period a year earlier) - 1, in %."""
        got = self.values(q, [p, p.year_ago()], stock)
        if not got:
            return None
        concept, (cur, base) = got
        if base.value <= 0:
            return None
        return Result((cur.value / base.value - 1) * 100, "%",
                      f"{q.name}_t / {q.name}_(t-1y) - 1 = {_fmt(cur.value)} / {_fmt(base.value)} - 1; {concept}; "
                      f"{cur.how}; {base.how}", self.facts_of(cur, base))

    def ratio(self, num: Quantity, den: Quantity, p: Fiscal, label: str) -> Result | None:
        a, b = self.one(num, p), self.one(den, p)
        if not a or not b or b[1].value <= 0:
            return None
        return Result(a[1].value / b[1].value * 100, "%",
                      f"{label} = {_fmt(a[1].value)} / {_fmt(b[1].value)}; {a[0]}: {a[1].how}; {b[0]}: {b[1].how}",
                      self.facts_of(a[1], b[1]))

    def fcf(self, p: Fiscal) -> tuple[float, str, list[Fact]] | None:
        ocf, capex = self.one(OCF, p), self.one(CAPEX, p)
        if not ocf or not capex:
            return None
        text = (f"fcf {p.label} = {_fmt(ocf[1].value)} - {_fmt(capex[1].value)} ({ocf[0]}: {ocf[1].how}; "
                f"{capex[0]}: {capex[1].how})")
        return ocf[1].value - capex[1].value, text, self.facts_of(ocf[1], capex[1])

    def invested_capital(self, p: Fiscal) -> tuple[float, str, list[Fact]] | None:
        """Equity + interest-bearing debt - cash at the end of ``p`` (roic's definition in the registry)."""
        parts = [self.one(q, p, stock=True) for q in (EQUITY, DEBT, CASH)]
        if not all(parts):
            return None
        (ce, e), (cd, d), (cc, c) = parts  # type: ignore[misc]
        value = e.value + d.value - c.value
        text = f"ic {p.label} = {_fmt(e.value)} + {_fmt(d.value)} - {_fmt(c.value)} ({ce}, {cd}, {cc})"
        return value, text, self.facts_of(e, d, c)

    def nopat(self, p: Fiscal) -> tuple[float, str, list[Fact]] | None:
        """Operating income x (1 - income tax / pretax income) over ``p``."""
        oi, tax, pretax = self.one(OPERATING_INCOME, p), self.one(INCOME_TAX, p), self.one(PRETAX_INCOME, p)
        if not oi or not tax or not pretax or pretax[1].value <= 0:
            return None
        rate = tax[1].value / pretax[1].value
        text = (f"nopat {p.label} = {_fmt(oi[1].value)} x (1 - {_fmt(tax[1].value)} / {_fmt(pretax[1].value)}) "
                f"({oi[0]}, {tax[0]}, {pretax[0]})")
        return oi[1].value * (1 - rate), text, self.facts_of(oi[1], tax[1], pretax[1])

    # -- the registry's xbrl metrics

    def revenue_yoy(self, p: Fiscal) -> Result | None:
        return self.growth(REVENUE, p)

    def gross_margin(self, p: Fiscal) -> Result | None:
        return self.ratio(GROSS_PROFIT, REVENUE, p, "gross_profit / revenue")

    def operating_margin(self, p: Fiscal) -> Result | None:
        return self.ratio(OPERATING_INCOME, REVENUE, p, "operating_income / revenue")

    def capex_to_revenue(self, p: Fiscal) -> Result | None:
        return self.ratio(CAPEX, REVENUE, p, "capex / revenue")

    def free_cash_flow(self, p: Fiscal) -> Result | None:
        got = self.fcf(p)
        return Result(got[0], self.f.currency, got[1], got[2]) if got else None

    def free_cash_flow_yoy(self, p: Fiscal) -> Result | None:
        cur, base = self.fcf(p), self.fcf(p.year_ago())
        if not cur or not base or base[0] <= 0:
            return None
        return Result((cur[0] / base[0] - 1) * 100, "%", f"fcf_t / fcf_(t-1y) - 1; {cur[1]}; {base[1]}", cur[2] + base[2])

    def fcf_conversion(self, p: Fiscal) -> Result | None:
        cur, ni = self.fcf(p), self.one(NET_INCOME, p)
        if not cur or not ni or ni[1].value <= 0:
            return None
        return Result(cur[0] / ni[1].value * 100, "%",
                      f"free_cash_flow / net_income = {_fmt(cur[0])} / {_fmt(ni[1].value)}; {cur[1]}; {ni[0]}: {ni[1].how}",
                      cur[2] + ni[1].facts)

    def diluted_shares_yoy(self, p: Fiscal) -> Result | None:
        return self.growth(DILUTED_SHARES, p)

    def buyback_amount(self, p: Fiscal) -> Result | None:
        got = self.one(BUYBACKS, p)
        return Result(got[1].value, self.f.currency, f"{got[0]}: {got[1].how}", got[1].facts) if got else None

    def shareholder_return_to_fcf(self, p: Fiscal) -> Result | None:
        buy, div, cur = self.one(BUYBACKS, p), self.one(DIVIDENDS, p), self.fcf(p)
        if not buy or not div or not cur or cur[0] <= 0:
            return None
        return Result((buy[1].value + div[1].value) / cur[0] * 100, "%",
                      f"(buybacks + dividends) / free_cash_flow = ({_fmt(buy[1].value)} + {_fmt(div[1].value)}) / "
                      f"{_fmt(cur[0])}; {buy[0]}: {buy[1].how}; {div[0]}: {div[1].how}; {cur[1]}",
                      self.facts_of(buy[1], div[1]) + cur[2])

    def dividend_payout_ratio(self, p: Fiscal) -> Result | None:
        return self.ratio(DIVIDENDS, NET_INCOME, p, "dividends / net_income")

    def roe(self, p: Fiscal) -> Result | None:
        if p.unit != "year":
            return None  # a return on equity is an annual figure; the registry does not annualize quarters
        ni = self.one(NET_INCOME, p)
        eq = self.values(EQUITY, [p, p.year_ago()], stock=True)
        if not ni or not eq:
            return None
        concept, (end, begin) = eq
        avg = (end.value + begin.value) / 2
        if avg <= 0:
            return None
        return Result(ni[1].value / avg * 100, "%",
                      f"net_income / avg(equity) = {_fmt(ni[1].value)} / avg({_fmt(end.value)}, {_fmt(begin.value)}); "
                      f"{ni[0]}: {ni[1].how}; {concept}: {end.how}; {begin.how}", ni[1].facts + self.facts_of(end, begin))

    def roic(self, p: Fiscal) -> Result | None:
        if p.unit != "year":
            return None
        nopat, ic_end, ic_begin = self.nopat(p), self.invested_capital(p), self.invested_capital(p.year_ago())
        if not nopat or not ic_end or not ic_begin:
            return None
        avg = (ic_end[0] + ic_begin[0]) / 2
        if avg <= 0:
            return None
        return Result(nopat[0] / avg * 100, "%",
                      f"nopat / avg(invested capital); {nopat[1]}; {ic_end[1]}; {ic_begin[1]}",
                      nopat[2] + ic_end[2] + ic_begin[2])

    def incremental_roic_3y(self, p: Fiscal) -> Result | None:
        if p.unit != "year":
            return None
        old = Fiscal(p.year - 3, "year")
        n1, n0, i1, i0 = self.nopat(p), self.nopat(old), self.invested_capital(p), self.invested_capital(old)
        if not (n1 and n0 and i1 and i0) or i1[0] - i0[0] <= 0:
            return None
        return Result((n1[0] - n0[0]) / (i1[0] - i0[0]) * 100, "%",
                      f"(nopat_t - nopat_(t-3y)) / (ic_t - ic_(t-3y)); {n1[1]}; {n0[1]}; {i1[1]}; {i0[1]}",
                      n1[2] + n0[2] + i1[2] + i0[2])

    def net_cash(self, p: Fiscal) -> Result | None:
        parts = [self.one(q, p, stock=True) for q in (CASH, SHORT_TERM_INVESTMENTS, DEBT)]
        if not all(parts):
            return None
        (cc, c), (cs, s), (cd, d) = parts  # type: ignore[misc]
        return Result(c.value + s.value - d.value, self.f.currency,
                      f"cash + short_term_investments - debt = {_fmt(c.value)} + {_fmt(s.value)} - {_fmt(d.value)} "
                      f"at {p.label} end ({cc}, {cs}, {cd})", self.facts_of(c, s, d))

    def net_debt_to_ebitda(self, p: Fiscal) -> Result | None:
        if p.unit != "year":
            return None
        debt, cash = self.one(DEBT, p, stock=True), self.one(CASH, p, stock=True)
        oi, da = self.one(OPERATING_INCOME, p), self.one(DEPRECIATION, p)
        if not (debt and cash and oi and da) or oi[1].value + da[1].value <= 0:
            return None
        ebitda = oi[1].value + da[1].value
        return Result((debt[1].value - cash[1].value) / ebitda, "x",
                      f"(debt - cash) / (operating_income + d_and_a) = ({_fmt(debt[1].value)} - {_fmt(cash[1].value)}) / "
                      f"({_fmt(oi[1].value)} + {_fmt(da[1].value)}) ({debt[0]}, {cash[0]}, {oi[0]}, {da[0]})",
                      self.facts_of(debt[1], cash[1], oi[1], da[1]))

    def rpo_yoy(self, p: Fiscal) -> Result | None:
        return self.growth(RPO, p, stock=True)

    def provision_for_credit_losses(self, p: Fiscal) -> Result | None:
        got = self.one(PROVISION, p)
        return Result(got[1].value, self.f.currency, f"{got[0]}: {got[1].how}", got[1].facts) if got else None

    def interest_expense_minus_income_growth(self, p: Fiscal) -> Result | None:
        expense, income = self.growth(INTEREST_EXPENSE, p), self.growth(INTEREST_INCOME, p)
        if not expense or not income:
            return None
        return Result(expense.value - income.value, "pp",
                      f"yoy(interest_expense) - yoy(interest_income) = {expense.value:.4f} - {income.value:.4f}; "
                      f"{expense.basis}; {income.basis}", expense.facts + income.facts)

    def cash_and_tbills_to_total_assets(self, p: Fiscal) -> Result | None:
        parts = [self.one(q, p, stock=True) for q in (CASH, SHORT_TERM_INVESTMENTS, TOTAL_ASSETS)]
        if not all(parts) or parts[2][1].value <= 0:  # type: ignore[index]
            return None
        (cc, c), (cs, s), (ca, a) = parts  # type: ignore[misc]
        return Result((c.value + s.value) / a.value * 100, "%",
                      f"(cash + short_term_investments) / total_assets = ({_fmt(c.value)} + {_fmt(s.value)}) / "
                      f"{_fmt(a.value)} at {p.label} end ({cc}, {cs}, {ca})", self.facts_of(c, s, a))

    def defined_growth(self, definition: dict, p: Fiscal) -> Result | None:
        """A metric_def whose formula is the growth of one quantity (``x_t / x_{t-4q} - 1``) over its xbrl list."""
        m = GROWTH_FORMULA.match(str(definition.get("formula") or ""))
        concepts = tuple(c for c in definition.get("xbrl") or [] if isinstance(c, str) and ":" in c)
        if not m or not concepts:
            return None
        for kind in ("money", "per_share", "shares"):
            result = self.growth(Quantity(m.group(1), concepts, kind), p)
            if result is not None:
                return result
        return None

    def defined(self, plan: Plan, p: Fiscal) -> Result | None:
        """A metric_def's formula for period ``p`` (SPEC 9.1); None when ``p`` is shorter than the definition's
        frequency, when a sum over fiscal years is asked for a quarter or a half, when any fact the formula needs is
        missing, or when a denominator is zero or negative."""
        points: dict[str, list[Fiscal]] = defaultdict(list)
        if QUARTERS_PER[p.unit] < plan.shortest or not _collect(plan.tree, p, points):
            return None
        values: dict[str, tuple[str, dict[Fiscal, Value]]] = {}
        for name, wanted in points.items():
            quantity = plan.quantities[name]
            periods = sorted(set(wanted), key=_chronological)
            got = self.f.first(quantity, periods, stock=quantity.instant)
            if got is None:
                return None  # a reading never mixes two concepts for one quantity, and nothing is interpolated
            values[name] = (got[0], dict(zip(periods, got[1])))
        raw = _evaluate(plan.tree, p, values)
        if raw is None:
            return None
        parts = [f"{name}: {concept}: " + "; ".join(v.how for v in by_period.values())
                 for name, (concept, by_period) in values.items()]
        return Result(raw * plan.scale, plan.unit or self.f.unit_for(plan.result),
                      f"{plan.text} = {_render(plan.tree, p, values)[0]}; " + "; ".join(parts),
                      [fact for _, by_period in values.values() for v in by_period.values() for fact in v.facts])


# -- the formulas of metric definitions (SPEC 9.1)

DIMENSIONS = {"money": (1, 0), "shares": (0, 1), "per_share": (1, -1)}  # exponents of money and of shares
RESULTS = {(0, 0): "ratio", (1, 0): "money", (0, 1): "shares", (1, -1): "per_share"}
RESULT_WORDS = {"ratio": "a number or a ratio", "money": "an amount of money", "shares": "a share count",
                "per_share": "a per-share amount"}
RATIO_SCALES = {"%": 100.0, "pp": 100.0, "x": 1.0}
PER_SHARE_UNIT = re.compile(r"^[A-Z]{3}/shares$")


@dataclass
class Plan:
    """A metric_def's formula checked against the vocabulary: what to read, and in which unit to report it."""

    text: str  # the formula as written
    tree: formula.Node
    quantities: dict[str, Quantity]  # each name as written -> its quantity, with candidates in the order tried
    result: str  # "ratio" | "money" | "shares" | "per_share"
    unit: str | None  # a ratio's unit ("%", "pp" or "x"); the unit of the other results follows the currency
    scale: float  # 100 for % and pp, else 1
    shortest: int  # quarters in the shortest period read: 4 for frequency year, 2 for half, else 1
    notes: list[str] = field(default_factory=list)


def _legacy_growth(definition: dict) -> bool:
    """The single-quantity growth formula that 0.4.0 computes over the definition's own xbrl list (kept as it was)."""
    return bool(GROWTH_FORMULA.match(str(definition.get("formula") or ""))) and any(
        isinstance(c, str) and ":" in c for c in definition.get("xbrl") or [])


def _quantity(name: str, listed: list[str]) -> Quantity | None:
    """The vocabulary's quantity for a name or a synonym, with the definition's listed candidates tried first."""
    quantity = VOCABULARY.get(SYNONYMS.get(name, name))
    if quantity is None:
        return None
    first = [c for c in listed if c in quantity.concepts]
    return Quantity(quantity.name, tuple(dict.fromkeys(first + list(quantity.concepts))), quantity.kind,
                    quantity.instant)


def _unknown(name: str) -> str:
    near = difflib.get_close_matches(name, list(VOCABULARY) + list(SYNONYMS), n=1, cutoff=0.75)
    return f"{name!r}" + (f" (did you mean {near[0]}?)" if near else "")


def _dimension(node: formula.Node, quantities: dict[str, Quantity], problems: list[str],
               inside: formula.Sum | None = None) -> tuple[int, int]:
    """The exponents of money and of shares in a node's value; adds to ``problems`` what the formula gets wrong."""
    if isinstance(node, formula.Number):
        return 0, 0
    if isinstance(node, formula.Name):
        q = quantities.get(node.name)
        if q is None:
            return 0, 0  # an unknown name, reported apart
        if inside is not None and q.instant:
            problems.append(f"{inside.function}() adds up flows over periods, but {node.name} is a balance at a date")
        elif inside is not None and q.kind != "money":
            problems.append(f"{inside.function}() adds up amounts of money, but {node.name} is "
                            f"{RESULT_WORDS[q.kind]}, which does not add up over periods")
        return DIMENSIONS[q.kind]
    if isinstance(node, formula.Negate):
        return _dimension(node.operand, quantities, problems, inside)
    if isinstance(node, formula.At):
        return _dimension(node.body, quantities, problems, inside)
    if isinstance(node, formula.Sum):
        return _dimension(node.body, quantities, problems, node)
    a = _dimension(node.left, quantities, problems, inside)
    b = _dimension(node.right, quantities, problems, inside)
    if node.op in "+-":
        if a != b:
            problems.append(f"{formula.text(node)} {'adds' if node.op == '+' else 'subtracts'} "
                            f"{_words(b)} {'to' if node.op == '+' else 'from'} {_words(a)}")
        return a
    sign = 1 if node.op == "*" else -1
    return a[0] + sign * b[0], a[1] + sign * b[1]


def _words(dimension: tuple[int, int]) -> str:
    kind = RESULTS.get(dimension)
    return RESULT_WORDS[kind] if kind else "a product of amounts"


def formula_plan(definition: Any) -> Plan:
    """Check a ``data: xbrl`` metric_def's formula against the vocabulary (SPEC 9.1).

    Raises FormulaError with every reason the definition cannot be computed: no formula, a syntax error, a name the
    vocabulary does not know, a balance or a share count summed over periods, a sum over fiscal years in a definition
    whose frequency is not year, or a result that does not fit the definition's ``unit``.
    """
    if not isinstance(definition, dict):
        raise FormulaError("the metric definition is not a mapping")
    if definition.get("data") != "xbrl":
        raise FormulaError(f"data is {definition.get('data')!r}: thesis-ci computes only data: xbrl definitions")
    text = definition.get("formula")
    if not isinstance(text, str) or not text.strip():
        raise FormulaError("the definition has no formula")
    tree = formula.parse(text)
    listed = [c for c in definition.get("xbrl") or [] if isinstance(c, str)]
    names = formula.names(tree)
    if not names:
        raise FormulaError("the formula reads no quantity")
    quantities = {name: q for name in names if (q := _quantity(name, listed)) is not None}
    problems = []
    unknown = [name for name in names if name not in quantities]
    if unknown:
        problems.append(f"unknown quantity name{'s' if len(unknown) > 1 else ''} "
                        f"{', '.join(_unknown(n) for n in unknown)}: SPEC 9.1 lists the names thesis-ci knows")
    result = RESULTS.get(_dimension(tree, quantities, problems))
    frequency = definition.get("frequency")
    years = [s.function for s in formula.sums(tree) if s.unit == "year"]
    if years and frequency != "year":
        problems.append(f"{years[0]}() is read for fiscal years only, but frequency is "
                        f"{frequency if frequency is not None else 'not given'}: write frequency: year")
    raw_unit = definition.get("unit")
    unit = normalize_unit(raw_unit)
    if unknown:
        pass  # what the result is, and whether the unit fits it, is judged once every name is known
    elif result is None:
        problems.append("the formula's result is not a ratio, an amount of money, a share count or a per-share amount")
    elif result == "ratio" and unit not in RATIO_SCALES:
        problems.append(f"the formula gives a ratio, but unit is {raw_unit!r}: write %, pp or x")
    elif result == "money" and readings_currency(unit) is None:
        problems.append(f"the formula gives an amount of money, but unit {raw_unit!r} is not a currency")
    elif result == "shares" and unit != "shares":
        problems.append(f"the formula gives a share count, but unit is {raw_unit!r}: write shares")
    elif result == "per_share" and not (unit and PER_SHARE_UNIT.match(unit)):
        problems.append(f"the formula gives a per-share amount, but unit is {raw_unit!r}: write <currency>/shares, "
                        "for example USD/shares")
    if (result == "ratio" and unit in ("%", "pp") and isinstance(tree, formula.Binary) and tree.op == "*"
            and any(isinstance(n, formula.Number) and n.value == 100 for n in (tree.left, tree.right))):
        problems.append(f"the formula multiplies by 100, and unit {unit} does so again: write the plain ratio")
    if problems:
        raise FormulaError("; ".join(problems))
    used = {c for q in quantities.values() for c in q.concepts}
    notes = []
    for concept in dict.fromkeys(c for c in listed if c not in used):
        owners = [q.name for q in VOCABULARY.values() if concept in q.concepts]
        notes.append(f"{concept} in xbrl is a candidate of {' and '.join(owners)}, which the formula does not read"
                     if owners else
                     f"{concept} in xbrl is a candidate of no quantity in the vocabulary, so it is not read")
    return Plan(text.strip(), tree, quantities, result, unit if result == "ratio" else None,
                RATIO_SCALES.get(unit or "", 1.0) if result == "ratio" else 1.0,
                QUARTERS_PER.get(frequency, 1) if isinstance(frequency, str) else 1, notes)


def computable(definition: Any) -> tuple[bool, str]:
    """Whether thesis-ci can compute a ``data: xbrl`` metric_def from companyfacts, and why not (SPEC 9.1).

    It parses the formula and checks its names against the vocabulary, its functions, that no balance or share count
    is summed over periods, that a sum over fiscal years has ``frequency: year``, and that the result fits ``unit``.
    ``(False, reason)`` means no reading can ever be computed. ``(True, notes)`` promises no reading either: a period
    still has none when the filings lack a fact it needs. The notes name ``xbrl`` concepts that the formula does not
    read; they are empty when there is nothing to say. A single-quantity growth formula over the definition's own
    ``xbrl`` list, which 0.4.0 already computed, is computable when its unit is %.
    """
    if isinstance(definition, dict) and definition.get("data") == "xbrl" and _legacy_growth(definition):
        if normalize_unit(definition.get("unit")) != "%":
            return False, f"a growth formula gives a percentage, but unit is {definition.get('unit')!r}: write %"
        return True, ""
    try:
        plan = formula_plan(definition)
    except FormulaError as exc:
        return False, str(exc)
    return True, "; ".join(plan.notes)


def _chronological(period: Fiscal) -> tuple[int, int]:
    return quarter_index(period.end_quarter), QUARTERS_PER[period.unit]


def _earlier(period: Fiscal, years: int) -> Fiscal:
    return Fiscal(period.year - years, period.unit, period.n) if years else period


def _sum_periods(node: formula.Sum, period: Fiscal) -> list[Fiscal] | None:
    """The periods a sum adds up for ``period``, oldest first; None for a sum over years asked for a quarter or a
    half."""
    if node.unit == "quarter":
        last = Fiscal(period.end_quarter[0], "quarter", period.end_quarter[1])
        return [last.shift(k - node.count + 1) for k in range(node.count)]
    if period.unit != "year":
        return None
    return [Fiscal(period.year - node.count + 1 + k, "year") for k in range(node.count)]


def _collect(node: formula.Node, period: Fiscal, points: dict[str, list[Fiscal]]) -> bool:
    """Record, by name, the periods for which each quantity is read; False when the formula is undefined here."""
    if isinstance(node, formula.Name):
        points[node.name].append(period)
        return True
    if isinstance(node, formula.Number):
        return True
    if isinstance(node, formula.Negate):
        return _collect(node.operand, period, points)
    if isinstance(node, formula.At):
        return _collect(node.body, _earlier(period, node.years_back), points)
    if isinstance(node, formula.Sum):
        spans = _sum_periods(node, period)
        return spans is not None and all(_collect(node.body, s, points) for s in spans)
    return _collect(node.left, period, points) and _collect(node.right, period, points)


def _evaluate(node: formula.Node, period: Fiscal, values: dict[str, tuple[str, dict[Fiscal, Value]]]) -> float | None:
    """The value of a node for ``period``; None when a denominator is zero or negative."""
    if isinstance(node, formula.Number):
        return node.value
    if isinstance(node, formula.Name):
        return values[node.name][1][period].value
    if isinstance(node, formula.Negate):
        inner = _evaluate(node.operand, period, values)
        return None if inner is None else -inner
    if isinstance(node, formula.At):
        return _evaluate(node.body, _earlier(period, node.years_back), values)
    if isinstance(node, formula.Sum):
        terms = [_evaluate(node.body, s, values) for s in _sum_periods(node, period) or []]
        return None if any(t is None for t in terms) else sum(terms)  # type: ignore[arg-type]
    a, b = _evaluate(node.left, period, values), _evaluate(node.right, period, values)
    if a is None or b is None:
        return None
    if node.op == "/":
        return a / b if b > 0 else None  # no ratio or growth on a zero or negative base
    return a + b if node.op == "+" else a - b if node.op == "-" else a * b


def _render(node: formula.Node, period: Fiscal, values: dict[str, tuple[str, dict[Fiscal, Value]]]) -> tuple[str, int]:
    """The formula with every name replaced by the value used, and its precedence (1 for + -, 2 for * /, 3 for a
    sign, 4 for an atom)."""
    if isinstance(node, formula.Number):
        return node.text, 4
    if isinstance(node, formula.Name):
        value = values[node.name][1][period].value
        return (f"({_fmt(value)})" if value < 0 else _fmt(value)), 4
    if isinstance(node, formula.Negate):
        text, prec = _render(node.operand, period, values)
        return "-" + (f"({text})" if prec < 3 else text), 3
    if isinstance(node, formula.At):
        return _render(node.body, _earlier(period, node.years_back), values)
    if isinstance(node, formula.Sum):
        terms = [_render(node.body, s, values) for s in _sum_periods(node, period) or []]
        return "(" + " + ".join(f"({t})" if prec < 2 else t for t, prec in terms) + ")", 4
    prec = 1 if node.op in "+-" else 2
    (left, lp), (right, rp) = _render(node.left, period, values), _render(node.right, period, values)
    if lp < prec:
        left = f"({left})"
    if rp < prec or (rp == prec and node.op in "-/"):
        right = f"({right})"
    return f"{left} {node.op} {right}", prec


# Registry metrics this module computes, and why the others are not computed.
REGISTRY_FORMULAS: dict[str, Callable[[_Calc, Fiscal], Result | None]] = {
    name: getattr(_Calc, name) for name in (
        "revenue_yoy", "gross_margin", "operating_margin", "free_cash_flow", "free_cash_flow_yoy", "fcf_conversion",
        "capex_to_revenue", "diluted_shares_yoy", "buyback_amount", "shareholder_return_to_fcf",
        "dividend_payout_ratio", "roic", "incremental_roic_3y", "roe", "net_cash", "net_debt_to_ebitda", "rpo_yoy",
        "provision_for_credit_losses", "interest_expense_minus_income_growth", "cash_and_tbills_to_total_assets",
    )
}
NOT_COMPUTED = {
    "book_value_per_share_yoy": "the registry names no share-count concept, and multi-class issuers need a "
                                "conversion to one class that companyfacts does not carry",
}


def _source(ticker: str, facts: list[Fact]) -> str:
    pairs = list(dict.fromkeys(f"{f.concept}:{f.accn}" for f in facts))
    return f"{ticker}-XBRL#{'+'.join(pairs)}"


def _round(value: float, unit: str) -> float | int:
    if unit in ("%", "pp", "x"):
        return round(value, 4)
    return int(value) if float(value).is_integer() else round(value, 2)


def readings_from_companyfacts(companyfacts: dict, metric_ids: list[str], periods: list[str], fiscal_year_end: str,
                               *, ticker: str | None = None, definitions: dict[str, dict] | None = None,
                               currency: str | None = None) -> list[dict]:
    """Readings of the ``data: xbrl`` metrics ``metric_ids`` for ``periods``, computed from a companyfacts document.

    ``metric_ids`` are ids of ``spec/metrics.yml``, or ids of ``definitions`` (a test's ``metric_def`` by its id,
    see ``metric_definitions``), whose ``data: xbrl`` formulas are computed when ``computable`` accepts them (SPEC
    9.1). ``periods`` are fiscal periods (``FY2026Q3``, ``FY2026H1``, ``FY2026``); a definition's formula is read
    for the periods of its ``frequency`` or longer, except that the growth of one quantity over the definition's own
    ``xbrl`` list is read for every period, as in 0.4.0. ``fiscal_year_end`` is ``filer.fiscal_year_end``
    (``MM-DD``).
    ``ticker`` names the source tag (``<TICKER>-XBRL``); without it the companyfacts ``ticker`` field or the CIK is
    used. ``currency`` overrides the detected reporting currency.

    Returns one reading per metric and period that could be computed, in the order asked for; any other
    combination is simply absent. Raises ValueError for a period that is not a fiscal period.
    """
    parsed = []
    for label in periods:
        p = parse_fiscal(label)
        if p is None:
            raise ValueError(f"not a fiscal period FY<year>, FY<year>H<n> or FY<year>Q<n>: {label!r}")
        parsed.append(p)
    facts = Facts(companyfacts, parse_fye(fiscal_year_end), currency)
    calc = _Calc(facts)
    tag = ticker or (companyfacts.get("ticker") if isinstance(companyfacts.get("ticker"), str) else None) \
        or f"CIK{int(companyfacts.get('cik') or 0):010d}"
    registry = contract.metrics()
    definitions = definitions or {}
    out = []
    for metric in metric_ids:
        if metric in definitions:
            compute = _definition_formula(definitions[metric])
        elif metric in REGISTRY_FORMULAS and registry.get(metric, {}).get("data") == "xbrl":
            compute = REGISTRY_FORMULAS[metric]
        else:
            compute = None
        if compute is None:
            continue
        for p in parsed:
            result = compute(calc, p)
            if result is None:
                continue
            out.append({"metric": metric, "period": p.label, "value": _round(result.value, result.unit),
                        "unit": result.unit, "source": _source(tag, result.facts), "basis": result.basis})
    return out


def _definition_formula(definition: Any) -> Callable[[_Calc, Fiscal], Result | None] | None:
    """How a metric_def is computed: a single-quantity growth over its own xbrl list as in 0.4.0, else its formula
    through the vocabulary (SPEC 9.1); None when it is not a data: xbrl definition thesis-ci can compute."""
    if not isinstance(definition, dict) or definition.get("data") != "xbrl":
        return None
    if _legacy_growth(definition):
        return lambda calc, p: calc.defined_growth(definition, p)
    try:
        plan = formula_plan(definition)
    except FormulaError:
        return None
    return lambda calc, p: calc.defined(plan, p)


def metric_definitions(thesis: dict) -> dict[str, dict]:
    """The ``metric_def`` of every test in a thesis that has an id, keyed by that id (for ``definitions``)."""
    out = {}
    for test in thesis.get("tests") or []:
        md = test.get("metric_def") if isinstance(test, dict) else None
        if isinstance(md, dict) and isinstance(md.get("id"), str):
            out.setdefault(md["id"], md)
    return out

