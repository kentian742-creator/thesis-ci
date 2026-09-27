"""Readings documents (readings.py, readings.schema.json), units, and fiscal periods (periods.py)."""

from __future__ import annotations

import datetime as dt

import pytest

from thesis_ci import periods, readings
from thesis_ci.periods import Fiscal, parse_fiscal, period_at, period_dates, quarter_end_date


def doc(*rows, **top):
    return {"company": "AXP", "as_of": "2026-10-17", "readings": list(rows), **top}


def row(**kw):
    base = {"metric": "revenue_yoy", "period": "FY2026Q3", "value": 9.8, "unit": "%",
            "source": "AXP-XBRL#us-gaap:RevenuesNetOfInterestExpense:0000004962-26-000400"}
    base.update(kw)
    return {k: v for k, v in base.items() if v is not ...}


def test_valid_document_with_every_optional_field():
    good = doc(row(), row(metric="net_card_fees_yoy.card_member_services_expense_yoy", basis="10-Q income statement",
                          note="x", segment="International Card Services", series="A"),
               row(metric="MSFT-Q9", value=True, unit="event"), row(value=None, note="no qualifying event", period="FY2026"),
               row(period="FY2027H1"))
    assert readings.problems(good) == []


@pytest.mark.parametrize("bad,why", [
    (row(source=...), "'source' is a required property"),
    (row(value=None), "'note' is a required property"),
    (row(period="2026Q3"), "does not match"),
    (row(period="FY2026Q5"), "does not match"),
    (row(metric="Revenue YoY"), "does not match"),
    (row(value="9.8%"), "is not of type"),
    (row(source="axp xbrl"), "does not match"),
    (row(extra=1), "Additional properties"),
])
def test_invalid_readings_are_reported(bad, why):
    problems = readings.problems(doc(bad))
    assert problems and any(why in p for p in problems), problems


def test_repeated_reading_is_reported_but_separate_series_are_not():
    assert readings.problems(doc(row(series="A"), row(series="B"))) == []
    assert readings.problems(doc(row(), row(value=1.0))) == ["readings/1: repeats readings/0 (revenue_yoy FY2026Q3)"]


def test_load_yaml_and_json(tmp_path):
    y = tmp_path / "r.yml"
    y.write_text("company: AXP\nas_of: 2026-10-17\nreadings: []\n", encoding="utf-8")
    assert readings.load(y) == {"company": "AXP", "as_of": "2026-10-17", "readings": []}  # the date became a string
    j = tmp_path / "r.json"
    j.write_text('{"company": "AXP", "as_of": "2026-10-17", "readings": []}', encoding="utf-8")
    assert readings.problems(readings.load(j)) == []
    with pytest.raises(ValueError):
        readings.load(tmp_path / "missing.yml")
    (tmp_path / "bad.yml").write_text("a: [", encoding="utf-8")
    with pytest.raises(ValueError):
        readings.load(tmp_path / "bad.yml")


@pytest.mark.parametrize("a,b,value,expected", [
    ("USD", "USD 100 million", 12_000_000_000, 120),
    ("RMB 100 million", "CNY", 1.5, 150_000_000),
    ("USD Billion", "USD million", 2, 2000),
    ("bps", "BPS", 5, None),
    ("×", "x", 3, 3),
    ("%", "%", 5, 5),
    ("%", "pp", 5, None),
    ("USD", "CNY", 5, None),
    ("shares", "USD", 5, None),
])
def test_unit_conversion(a, b, value, expected):
    assert readings.convert(value, a, b) == (pytest.approx(expected) if expected is not None else None)


def test_fiscal_periods():
    assert parse_fiscal("FY2026Q3") == Fiscal(2026, "quarter", 3)
    assert parse_fiscal("FY2026H2") == Fiscal(2026, "half", 2) and parse_fiscal("FY2026").unit == "year"
    assert parse_fiscal("2026Q3") is None and parse_fiscal("FY2026Q5") is None
    assert Fiscal(2026, "quarter", 1).shift(-1).label == "FY2025Q4"
    assert Fiscal(2026, "half", 1).shift(-1).label == "FY2025H2"
    assert Fiscal(2026, "quarter", 3).year_ago().label == "FY2025Q3"
    assert period_at("year", (2026, 3)) is None and period_at("half", (2026, 4)).label == "FY2026H2"
    assert Fiscal(2026, "half", 2).start_quarter == (2026, 3)


def test_fiscal_calendar_dates():
    june = periods.fiscal_year_end("06-30")
    assert quarter_end_date(2027, 1, june) == dt.date(2026, 9, 30)
    assert quarter_end_date(2027, 3, june) == dt.date(2027, 3, 31)  # a month-end year puts every quarter at a month end
    assert period_dates(Fiscal(2027, "year"), june) == (dt.date(2026, 7, 1), dt.date(2027, 6, 30))
    dec = periods.fiscal_year_end("12-31")
    assert period_dates(Fiscal(2026, "half", 2), dec) == (dt.date(2026, 7, 1), dt.date(2026, 12, 31))
    assert quarter_end_date(2026, 2, periods.fiscal_year_end("12-28")) == dt.date(2026, 6, 28)
    assert periods.fiscal_year_end(None) == (12, 31) and periods.fiscal_year_end("13-40") == (12, 31)
