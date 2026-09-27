"""Compute ``data: xbrl`` metrics of ``spec/metrics.yml`` from an SEC companyfacts document (SPEC 4.5, 9).

``readings_from_companyfacts(companyfacts, metric_ids, periods, fiscal_year_end)`` is a pure function: it reads the
JSON the SEC serves at ``api/xbrl/companyfacts/CIK##########.json`` (already downloaded) and returns readings
(``readings.py``) for the metrics and fiscal periods asked for. A metric it cannot compute is left out; nothing is
estimated.

How values are taken:

- Only facts from periodic reports count: 10-K, 10-Q, 20-F, 40-F (and their amendments and transition reports).
  Facts from 8-Ks and other forms are ignored.
- A fact's period comes from its start and end dates, matched to the fiscal calendar that ``fiscal_year_end``
  defines (within 10 days, for 52/53-week years), not from the filing's ``fy`` / ``fp`` fields, which describe the
  filing, not the fact.
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

Each reading's ``source`` is ``<TICKER>-XBRL#<concept>:<accession>``, with ``+`` joining further concept:accession
pairs when the value rests on several facts; ``basis`` spells out the formula with the values used.
"""

from __future__ import annotations

import datetime as dt
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

from . import contract
from .periods import Fiscal, fiscal_year_end as parse_fye, parse_fiscal, period_dates, quarter_end_date

PERIODIC_FORMS = {"10-K", "10-Q", "20-F", "40-F", "10-KT", "10-QT", "10-K/A", "10-Q/A", "20-F/A", "40-F/A",
                  "10-KT/A", "10-QT/A"}
TOLERANCE = dt.timedelta(days=10)
CURRENCY_UNIT = re.compile(r"^[A-Z]{3}$")
GROWTH_FORMULA = re.compile(r"^\s*([a-z][a-z0-9_]*)_t\s*/\s*\1_\{t-(4q|1y)\}\s*-\s*1\s*$")


@dataclass(frozen=True)
class Quantity:
    """One quantity a formula uses, with its candidate concepts in order of preference."""

    name: str
    concepts: tuple[str, ...]
    kind: str  # "money" | "shares" | "per_share"


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
EQUITY = Quantity("equity", ("us-gaap:StockholdersEquity", "ifrs-full:Equity"), "money")
DEBT = Quantity("debt", ("us-gaap:LongTermDebt",), "money")
CASH = Quantity("cash", ("us-gaap:CashAndCashEquivalentsAtCarryingValue", "ifrs-full:CashAndCashEquivalents"), "money")
SHORT_TERM_INVESTMENTS = Quantity("short_term_investments", ("us-gaap:ShortTermInvestments",), "money")
INCOME_TAX = Quantity("income_tax", ("us-gaap:IncomeTaxExpenseBenefit",), "money")
PRETAX_INCOME = Quantity("pretax_income", (
    "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "us-gaap:IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments",
), "money")
DEPRECIATION = Quantity("d_and_a", ("us-gaap:DepreciationDepletionAndAmortization",), "money")
RPO = Quantity("rpo", ("us-gaap:RevenueRemainingPerformanceObligation",), "money")
PROVISION = Quantity("provision", ("us-gaap:ProvisionForLoanLeaseAndOtherLosses",
                                   "us-gaap:ProvisionForLoanAndLeaseLosses"), "money")
INTEREST_EXPENSE = Quantity("interest_expense", ("us-gaap:InterestExpense", "us-gaap:InterestExpenseOperating"), "money")
INTEREST_INCOME = Quantity("interest_income", ("us-gaap:InterestAndDividendIncomeOperating",), "money")
TOTAL_ASSETS = Quantity("total_assets", ("us-gaap:Assets",), "money")


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


class Facts:
    """The periodic-report facts of one companyfacts document, indexed by concept and unit."""

    def __init__(self, companyfacts: dict, fye: tuple[int, int], currency: str | None = None):
        self.fye = fye
        self._rows: dict[tuple[str, str], list[Fact]] = defaultdict(list)
        counts: Counter = Counter()
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
        self.currency = currency or (counts.most_common(1)[0][0] if counts else "USD")

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
        start = quarter_end_date(year - 1, 4, self.fye) + dt.timedelta(days=1)
        return start, quarter_end_date(year, quarter, self.fye)

    def flow(self, concept: str, kind: str, period: Fiscal) -> Value | None:
        """A flow (income or cash flow statement line) over a fiscal period, reported or derived from YTD figures."""
        start, end = period_dates(period, self.fye)
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
        end = period_dates(period, self.fye)[1]
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
    see ``metric_definitions``), of which only a single-quantity growth formula (``x_t / x_{t-4q} - 1`` or
    ``x_t / x_{t-1y} - 1`` over the definition's ``xbrl`` concepts) is computed. ``periods`` are fiscal periods
    (``FY2026Q3``, ``FY2026H1``, ``FY2026``); ``fiscal_year_end`` is ``filer.fiscal_year_end`` (``MM-DD``).
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
            definition = definitions[metric]
            formula = None if definition.get("data") != "xbrl" else (lambda c, p, d=definition: c.defined_growth(d, p))
        elif metric in REGISTRY_FORMULAS and registry.get(metric, {}).get("data") == "xbrl":
            formula = REGISTRY_FORMULAS[metric]
        else:
            formula = None
        if formula is None:
            continue
        for p in parsed:
            result = formula(calc, p)
            if result is None:
                continue
            out.append({"metric": metric, "period": p.label, "value": _round(result.value, result.unit),
                        "unit": result.unit, "source": _source(tag, result.facts), "basis": result.basis})
    return out


def metric_definitions(thesis: dict) -> dict[str, dict]:
    """The ``metric_def`` of every test in a thesis that has an id, keyed by that id (for ``definitions``)."""
    out = {}
    for test in thesis.get("tests") or []:
        md = test.get("metric_def") if isinstance(test, dict) else None
        if isinstance(md, dict) and isinstance(md.get("id"), str):
            out.setdefault(md["id"], md)
    return out

