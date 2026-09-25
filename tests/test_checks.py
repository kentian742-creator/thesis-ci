"""Positive and negative tests for every check. Each test's docstring names the check it covers."""

from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path

import pytest

from thesis_ci import engine, selftest
from thesis_ci.selftest import CASES

THESIS = "public/companies/ACME/thesis.yml"
STORY = "public/companies/ACME/story.md"
RIGHTS = "public/constitution/decision-rights.yml"
INDUSTRY = "public/industries/widgets/industry.yml"
IND_README = "public/industries/widgets/README.md"
PREREG = "public/companies/ACME/prereg/FY2027Q1.yml"
SETTLEMENT = "public/companies/ACME/prereg/FY2027Q1.settlement.yml"
BUY_MEMO = "private/memos/2026-09-20-ACME-entry.yml"
ACME_VAL = "private/companies/ACME/valuation.yml"
BETA_VAL = "private/companies/BETA/valuation.yml"
LETTER = "public/letters/2026-09.md"
STORY_END = selftest.STORY_END  # the English story's last sentence
MODULE_ONLY = "This module describes only the industry itself"  # a sentence of the industry README


def edit(ws: Path, rel: str, old: str, new: str) -> None:
    selftest.apply(ws, (selftest.replace(rel, old, new),))


def put(ws: Path, rel: str, text: str) -> None:
    selftest.apply(ws, (selftest.write(rel, text),))


def errors(findings):
    return [f for f in findings if f.level == "error"]


# --------------------------------------------------------------------------- whole workspace
def test_clean_workspace_passes_every_check():
    """The clean fixture passes all checks on both sides, with and without the counterpart."""
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        ws = selftest.materialize(Path(tmp) / "ws")
        for side, other in (("public", "private"), ("private", "public")):
            for cp in (ws / other, None):
                report = engine.run(ws / side, cp, selftest.TODAY)
                assert report.findings == [], (side, cp, report.findings)


@pytest.mark.parametrize("case", CASES, ids=[f"{c.check}:{c.why}" for c in CASES])
def test_violating_fixture_is_flagged(case, tmp_path, lint):
    """Every selftest case (one or more per check id) is flagged by its check."""
    missing = [exe for exe in case.requires if shutil.which(exe) is None]
    if missing:
        pytest.skip(f"needs {', '.join(missing)}")
    ws = selftest.materialize(tmp_path / "ws", case.ops)
    assert lint(ws, case.check, case.target, case.counterpart, **dict(case.options))


def test_vacuous_pass_on_empty_archives(tmp_path):
    """Checks pass when their inputs do not exist yet; a public archive still needs its constitution."""
    pub, priv = tmp_path / "pub", tmp_path / "priv"
    for root, vis in ((pub, "public"), (priv, "private")):
        root.mkdir()
        (root / "repo.yml").write_text(f'visibility: {vis}\nspec_version: "0.2"\n', encoding="utf-8")
    assert engine.run(priv, pub, selftest.TODAY).findings == []
    assert engine.run(priv, None, selftest.TODAY).findings == []
    public = engine.run(pub, priv, selftest.TODAY)
    assert sorted({f.check for f in public.findings}) == ["C-CONSTITUTION-MAP", "C-DECISION-RIGHTS"]


# --------------------------------------------------------------------------- C-SCHEMA
def test_c_schema_reports_branch_errors_with_lines(ws, lint):
    """C-SCHEMA: a qualitative test missing its question is reported precisely, not as an opaque oneOf."""
    edit(ws, THESIS, "    question: In this period's documents, did management lower or withdraw the medium-term financial "
                     "targets it had published?\n", "")
    found = lint(ws, "C-SCHEMA")
    assert len(found) == 1
    assert "'question' is a required property" in found[0].message
    assert found[0].line == 132  # the list item of ACME-L1


def test_c_schema_yaml_syntax_error_and_unmapped_yaml(ws, lint):
    """C-SCHEMA: syntax errors are reported for mapped and unmapped YAML files."""
    put(ws, "public/companies/ACME/updates/2026-10.yml", "a: [1, 2\n")
    edit(ws, "public/forecasts/2026.yml", "year: 2026", "year: [2026")
    files = sorted(f.file for f in lint(ws, "C-SCHEMA"))
    assert files == ["companies/ACME/updates/2026-10.yml", "forecasts/2026.yml"]


def test_c_schema_unquoted_datetimes_are_iso_strings(ws, lint):
    """C-SCHEMA: YAML dates and datetimes are converted to ISO strings before validation."""
    edit(ws, PREREG, 'deadline: "2026-10-27T23:59:59-04:00"', "deadline: 2026-10-27T23:59:59-04:00")
    edit(ws, SETTLEMENT, 'merged_at: "2026-09-21T10:00:00-04:00"', "merged_at: 2026-09-21T10:00:00-04:00")
    assert lint(ws, "C-SCHEMA") == []
    assert lint(ws, "C-PREREG-TIMING") == []


def test_c_schema_prereg_deadline_needs_an_offset(ws, lint):
    """C-SCHEMA: a pre-registration deadline is an ISO 8601 date-time with its UTC offset."""
    edit(ws, PREREG, 'deadline: "2026-10-27T23:59:59-04:00"', 'deadline: "2026-10-27T23:59:59"')
    assert any("/deadline" in f.message for f in lint(ws, "C-SCHEMA"))


def test_c_schema_private_only_schemas_not_applied_in_public(ws, lint):
    """C-SCHEMA: memo/valuation schemas apply to the private repository only."""
    put(ws, "private/memos/2026-09-25-ACME-x.yml", "id: x\n")
    assert any("memo.schema.json" in f.message for f in lint(ws, "C-SCHEMA", "private"))
    put(ws, "public/memos/2026-09-25-ACME-x.yml", "id: x\n")  # C-PUBLIC-NO-VALUATION's job in public
    assert lint(ws, "C-SCHEMA", "public") == []


# --------------------------------------------------------------------------- C-SRC-TAG
def test_c_src_tag_code_spans_and_root_sources(ws, lint):
    """C-SRC-TAG: code spans are ignored; letters resolve tags through the root sources.yml."""
    edit(ws, STORY, STORY_END, "`growth 16%` does not count. " + STORY_END)
    assert lint(ws, "C-SRC-TAG") == []
    edit(ws, LETTER, "[src:OO-LOG-2026-09]", "[src:ACME-RPT-2026-09#p1]")
    found = lint(ws, "C-SRC-TAG")
    assert len(found) == 1 and "ACME-RPT-2026-09" in found[0].message


def test_c_src_tag_malformed_tag_and_industry_readme(ws, lint):
    """C-SRC-TAG: malformed tags and untagged numbers in industry READMEs are errors."""
    edit(ws, IND_README, "[src:IND-WIDGETS-2026-09#p2]", "[src: IND-WIDGETS]")
    messages = [f.message for f in lint(ws, "C-SRC-TAG")]
    assert any("malformed" in m for m in messages)
    assert any("70%" in m for m in messages)


def test_c_src_tag_only_archive_markdown(ws, lint):
    """C-SRC-TAG: Markdown outside companies/, industries/, letters/ (docs, constitution) is not scanned."""
    put(ws, "public/docs/DESIGN.md", "预算每月 20 美元，10–20% 是门槛。\n")
    put(ws, "public/constitution/owner.md", "集中持有，10–20% 是入选门槛。\n")
    assert lint(ws, "C-SRC-TAG") == []


# --------------------------------------------------------------------------- C-SRC-FACT
def test_c_src_fact_criteria_are_exempt(ws, lint):
    """C-SRC-FACT: fail_if, warn_if, threshold, question and rule are pre-registered criteria, not facts."""
    edit(ws, THESIS, 'rule: {op: "<", threshold: 55, unit: "%", consecutive: 2, period: quarter}',
         'rule: {op: "<", threshold: 55, unit: "%", consecutive: 2, period: quarter, note: fails below 55%}')
    edit(ws, THESIS, "question: In this period's documents", "question: Is gross margin below 50%? In this period's documents")
    assert lint(ws, "C-SRC-FACT") == []


@pytest.mark.parametrize(
    "path, old, new",
    [
        (THESIS, "    - A new open standard makes compatibility worthless", "    - Market share falls below 20%"),
        (THESIS, "claim: Free cash flow grows with revenue", "claim: Free cash flow grew 40% in three years"),
        (THESIS, "by about 11% a year for many years [src:ACME-RPT-2026-09#p3]", "by about 11% a year for many years"),
        (THESIS, "    label: Gross margin", "    label: Gross margin 62%"),
        (INDUSTRY, "  - Demand comes from factory automation, where certification cycles are long",
         "  - Demand comes from factory automation, 80% of it"),
        (INDUSTRY, "implication: The compatibility moat narrows", "implication: Share could fall 10 percentage points"),
        (INDUSTRY, "observable: Share of new production lines that adopt the open interface standard",
         "observable: Share of new production lines (12% last year)"),
        ("public/companies/ACME/ledger.yml", "$3 billion of stock within three years [src:ACME-10K-FY2026#Item5]",
         "$3 billion of stock within three years"),
    ],
)
def test_c_src_fact_free_text_needs_tags(ws, lint, path, old, new):
    """C-SRC-FACT: fact numbers in YAML free text need a [src:] tag in the same sentence."""
    edit(ws, path, old, new)
    assert errors(lint(ws, "C-SRC-FACT"))


def test_c_src_fact_predictions_and_todo_are_not_facts(ws, lint):
    """C-SRC-FACT: prereg statements are predictions and todo items are not facts."""
    edit(ws, PREREG, "statement: Year-on-year revenue growth this quarter is no lower than last quarter's",
         "statement: Year-on-year revenue growth this quarter is at least 8%")
    edit(ws, THESIS, "  - Add segment data", "  - Add segment data (the report covers only 40% of revenue)")
    assert lint(ws, "C-SRC-FACT") == []


def test_c_src_fact_industry_source_field(ws, lint):
    """C-SRC-FACT: current_reading.source must resolve in the industry's sources.yml."""
    edit(ws, INDUSTRY, "source: IND-WIDGETS-2026-09#p9", "source: IND-OTHER-2026-09#p9")
    found = lint(ws, "C-SRC-FACT")
    assert len(found) == 1 and "signposts[0].current_reading.source" in found[0].message


# --------------------------------------------------------------------------- C-SRC-ACCESSION
def test_c_src_accession_is_a_warning(ws, lint):
    """C-SRC-ACCESSION: a filing without accession is a warning, not an error."""
    edit(ws, "public/companies/ACME/sources.yml", "    accession: 0000000001-26-000001\n", "")
    found = lint(ws, "C-SRC-ACCESSION")
    assert [f.level for f in found] == ["warning"]
    assert engine.run(ws / "public", None, selftest.TODAY, only=["C-SRC-ACCESSION"]).errors == []


# --------------------------------------------------------------------------- public hygiene
def test_c_public_no_valuation_keys_phrases_and_dirs(ws, lint):
    """C-PUBLIC-NO-VALUATION: value_ranges key, English phrases (any case) and decision-log/ are errors."""
    edit(ws, "public/forecasts/2026.yml", "brier: null", "brier: null\n    value_ranges: {fair: [1, 2]}")
    edit(ws, LETTER, "below budget", "no Price Target here")
    put(ws, "public/decision-log/2026.yml", "entries: []\n")
    messages = " ".join(f.message for f in lint(ws, "C-PUBLIC-NO-VALUATION"))
    assert "value_ranges" in messages and "price target" in messages and "decision-log" in messages


def test_c_public_no_valuation_ignores_docs(ws, lint):
    """C-PUBLIC-NO-VALUATION: wording checks cover companies/, industries/, forecasts/, letters/ only."""
    put(ws, "public/docs/DESIGN.md", "Value ranges and the target price live in the private repository only.\n")
    assert lint(ws, "C-PUBLIC-NO-VALUATION") == []


def test_c_public_no_advice_readme_anywhere_and_case(ws, lint):
    """C-PUBLIC-NO-ADVICE: README files anywhere and case-insensitive English phrases."""
    put(ws, "public/agents/README.md", "Rated Overweight.\n")
    assert len(lint(ws, "C-PUBLIC-NO-ADVICE")) == 1
    put(ws, "public/docs/notes.md", "strong buy\n")  # not a README, not archive content
    assert len(lint(ws, "C-PUBLIC-NO-ADVICE")) == 1


def test_c_public_no_amounts_weight_key_and_short_ids(ws, lint):
    """C-PUBLIC-NO-AMOUNTS: a weight key is an error; short U-numbers are not account ids."""
    edit(ws, LETTER, "below budget", "below budget; the U123 model")
    assert lint(ws, "C-PUBLIC-NO-AMOUNTS") == []
    edit(ws, "public/forecasts/2026.yml", "brier: null", "brier: null\n    weight: 0.15")
    assert len(lint(ws, "C-PUBLIC-NO-AMOUNTS")) == 1


# --------------------------------------------------------------------------- code guards
def test_c_no_price_feed_private_exception_and_docs(ws, lint):
    """C-NO-PRICE-FEED: private pipeline/price_alert.py is exempt; prose mentions are not code."""
    put(ws, "private/pipeline/price_alert.py", "import yfinance  # phase 2 range alerts\n")
    assert lint(ws, "C-NO-PRICE-FEED", "private") == []
    put(ws, "public/pipeline/price_alert.py", "import yfinance\n")
    assert len(lint(ws, "C-NO-PRICE-FEED")) == 1
    put(ws, "public/docs/NOTES.md", "We never use yfinance.\n")
    assert len(lint(ws, "C-NO-PRICE-FEED")) == 1


def test_c_no_price_feed_workflows_and_json(ws, lint):
    """C-NO-PRICE-FEED: workflow files are code; public JSON data may not carry price keys."""
    put(ws, "public/.github/workflows/nightly.yml", "on: push\njobs: {a: {runs-on: x, steps: [{run: pip install finnhub-python}]}}\n")
    put(ws, "public/forecasts/dash.json", '{"rows": [{"close": 1}]}')
    files = sorted(f.file for f in lint(ws, "C-NO-PRICE-FEED"))
    assert files == [".github/workflows/nightly.yml", "forecasts/dash.json"]


def test_c_no_trading_workflow_and_prose(ws, lint):
    """C-NO-TRADING: broker names in workflows are flagged; prose is not code."""
    put(ws, "public/letters/2026-10.md", "This system never connects to Schwab.\n")
    assert lint(ws, "C-NO-TRADING") == []
    put(ws, "public/.github/workflows/x.yml", "jobs: {a: {steps: [{run: python -m ib_insync}]}}\n")
    assert len(lint(ws, "C-NO-TRADING")) == 1


@pytest.mark.parametrize(
    "code, flagged",
    [
        ("import anthropic\n", True),
        ("import openai.types\n", True),
        ("from langchain_openai import ChatOpenAI\n", True),
        ("import google.generativeai as genai\n", True),
        ("import importlib\nm = importlib.import_module('litellm')\n", True),
        ("import openai_helpers\n", False),
        ("import googleapiclient\n", False),
        ("def broken(:\n    pass\nimport cohere\n", True),
    ],
)
def test_c_llm_entry_imports(ws, lint, code, flagged):
    """C-LLM-ENTRY: model SDK imports outside pipeline/llm.py, including dynamic and fallback detection."""
    put(ws, "public/scripts/tool.py", code)
    assert bool(lint(ws, "C-LLM-ENTRY")) is flagged


@pytest.mark.parametrize(
    "text, flagged",
    [
        ("ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}\n", False),
        ('api_key = os.environ["ANTHROPIC_API_KEY"]\n', False),
        ('ANTHROPIC_API_KEY="your-anthropic-api-key-here"\n', False),
        ("see https://example.com/sk-hynix-memory-market-share-2025\n", False),
        ("MAX_TOKENS = 4096\n", False),
        ('HF_TOKEN = "hfAbCdEf0123456789xyz"\n', True),
        ('{"OPENAI_API_KEY": "abcDEF1234567890ghij"}\n', True),
        ("aws = " + "AKIA" + "ABCDEFGHIJ012345\n", True),
        ("token: " + "github_" + "pat_" + "11ABCDEFG0abcdefghij_klmnop\n", True),
    ],
)
def test_c_no_secrets_patterns(ws, lint, text, flagged):
    """C-NO-SECRETS: key-shaped strings and literal assignments; references and placeholders pass."""
    put(ws, "public/docs/setup.md", text)
    assert bool(lint(ws, "C-NO-SECRETS")) is flagged


# --------------------------------------------------------------------------- thesis tests
def test_c_tests_min_counts_five(ws, lint):
    """C-TESTS-MIN: fewer than five tests in force is an error (the retired ACME-Q4 does not count)."""
    text = (ws / THESIS).read_text(encoding="utf-8")
    start = text.index("  - id: ACME-L1")
    (ws / THESIS).write_text(text[:start] + "todo:\n  - x\n", encoding="utf-8")
    assert any("4 thesis tests in force (1 retired tests do not count)" in f.message for f in lint(ws, "C-TESTS-MIN"))


def test_c_tests_coverage_all_touchstones(ws, lint):
    """C-TESTS-COVERAGE: moat, pricing_power, returns_on_capital, free_cash_flow must all be covered."""
    edit(ws, THESIS, "covers: [free_cash_flow, returns_on_capital]", "covers: [growth]")
    msg = lint(ws, "C-TESTS-COVERAGE")[0].message
    assert "returns_on_capital" in msg and "free_cash_flow" in msg


def test_c_tests_capalloc_passes_when_covered(ws, lint):
    """C-TESTS-CAPALLOC: capital_allocation and management each covered by some test."""
    assert lint(ws, "C-TESTS-CAPALLOC") == []
    edit(ws, THESIS, "covers: [capital_allocation]", "covers: [capital_allocation, management]")
    edit(ws, THESIS, "covers: [management]", "covers: [culture]")
    assert lint(ws, "C-TESTS-CAPALLOC") == []


@pytest.mark.parametrize(
    "old, new, level",
    [
        ('rule: {op: "<", threshold: 55, unit: "%", consecutive: 2, period: quarter}',
         'rule: {op: between, threshold: [60, 50], period: quarter}', "error"),
        ('rule: {op: "<", threshold: 55, unit: "%", consecutive: 2, period: quarter}',
         'rule: {op: "<", threshold: 55, all_of: [{op: "<", threshold: 1}]}', "error"),
        ('warn_rule: {op: "<", threshold: 58, unit: "%", consecutive: 1, period: quarter}',
         'warn_rule: {op: "<<", threshold: 58}', "error"),
        ('rule: {op: "<", threshold: 55, unit: "%", consecutive: 2, period: quarter}',
         'rule: {any_of: []}', "error"),
        ('rule: {op: "<", threshold: 55, unit: "%", consecutive: 2, period: quarter}',
         'rule: {all_of: [{metric: gross_margin, op: "<", threshold: 55}, {metric: mystery_metric, op: ">", threshold: 1}]}',
         "error"),
    ],
)
def test_c_test_metric_rules(ws, lint, old, new, level):
    """C-TEST-METRIC: rules must be machine-decidable; a sub-rule metric must resolve (SPEC 4.1)."""
    edit(ws, THESIS, old, new)
    assert [f.level for f in lint(ws, "C-TEST-METRIC")] == [level]


def test_c_test_metric_metric_def_and_param_defs(ws, lint):
    """C-TEST-METRIC: metric_def replaces the registry; params.metric_defs and dotted ids define sub-metrics."""
    edit(ws, THESIS, "    metric: gross_margin\n",
         "    metric_def: {id: widget_margin, description: widget gross margin, unit: '%', data: xbrl, xbrl: [us-gaap:GrossProfit]}\n"
         "    params: {metric_defs: [{id: attach_rate, description: attach rate, unit: '%', data: filing_text}]}\n")
    edit(ws, THESIS, 'rule: {op: "<", threshold: 55, unit: "%", consecutive: 2, period: quarter}',
         'rule: {all_of: [{metric: widget_margin, op: "<", threshold: 55}, {metric: attach_rate.us, op: "<", threshold: 30}]}')
    assert lint(ws, "C-TEST-METRIC") == []
    edit(ws, THESIS, "data: xbrl, xbrl: [us-gaap:GrossProfit]", "data: filing_text")
    assert "does not match" in lint(ws, "C-TEST-METRIC")[0].message


def test_c_test_qual_evidence_needs_question(ws, lint):
    """C-TEST-QUAL-EVIDENCE: question and fail_if must be non-empty."""
    edit(ws, THESIS, "fail_if: Yes, without giving new, testable targets at the same time", 'fail_if: " "')
    assert "fail_if" in lint(ws, "C-TEST-QUAL-EVIDENCE")[0].message


@pytest.mark.parametrize(
    "today, expected",
    [(dt.date(2027, 9, 19), []), (dt.date(2027, 9, 20), ["warning"]), (dt.date(2026, 9, 1), ["warning", "warning"])],
)
def test_c_staleness_boundary(ws, lint, today, expected):
    """C-STALENESS: fails only beyond max_age_quarters x 91 days; future review dates are undetermined."""
    # moat: 4 quarters = 364 days after 2026-09-20 -> 2027-09-19 passes, 2027-09-20 fails.
    edit(ws, THESIS, "  bear_case: 2026-09-22", "  bear_case: 2027-09-01")
    assert [f.level for f in lint(ws, "C-STALENESS", today=today)] == expected


def test_c_staleness_retired_tests_are_not_evaluated(ws, lint):
    """C-STALENESS: a retired staleness test is a record only; munger and unknowns are valid sections."""
    edit(ws, THESIS, "  moat: 2026-09-20", "  moat: 2025-01-15")
    assert len(lint(ws, "C-STALENESS")) == 1
    edit(ws, THESIS, "    section: moat\n", "    section: moat\n    retired_at: FY2027Q2\n")
    assert lint(ws, "C-STALENESS") == []
    edit(ws, THESIS, "    section: bear_case\n", "    section: munger\n")
    assert lint(ws, "C-STALENESS") == [] and lint(ws, "C-SCHEMA") == []


def test_c_staleness_missing_section(ws, lint):
    """C-STALENESS: a staleness test whose reviewed date is missing is reported."""
    edit(ws, THESIS, "  moat: 2026-09-20\n", "")
    assert "cannot evaluate" in lint(ws, "C-STALENESS")[0].message


# --------------------------------------------------------------------------- archive structure
def test_c_depends_allows_bank_holding_company(ws, lint):
    """C-DEPENDS: 'bank holding company' is an ordinary word; 'our holdings' is not."""
    edit(ws, IND_README, MODULE_ONLY, "AXP is a bank holding company")
    assert lint(ws, "C-DEPENDS") == []
    edit(ws, IND_README, "AXP is a bank holding company", "one of our holdings")
    assert len(lint(ws, "C-DEPENDS")) == 1


def test_c_depends_flags_depends_on_in_module(ws, lint):
    """C-DEPENDS: industry modules may not list dependants (depends_on, companies that depend on this industry)."""
    edit(ws, INDUSTRY, "tests_to_rerun: [moat, pricing_power]", "tests_to_rerun: [moat, pricing_power]\n    # depends_on: ACME")
    edit(ws, IND_README, MODULE_ONLY, "Companies that depend on this industry: ACME")
    assert len(lint(ws, "C-DEPENDS")) == 2


def test_c_story_prose_limit_ignores_tags(ws, lint):
    """C-STORY: a story in Chinese passes at exactly 700 prose characters, however many source tags it has."""
    text = (ws / STORY).read_text(encoding="utf-8")
    fm = text[: text.index("# ACME")]
    body = ("字" * 70 + "[src:ACME-RPT-2026-09#p1]\n") * 10
    (ws / STORY).write_text(fm + body, encoding="utf-8")
    assert lint(ws, "C-STORY") == []
    (ws / STORY).write_text(fm + body + "多", encoding="utf-8")
    assert "701" in lint(ws, "C-STORY")[0].message


def test_c_story_front_matter_schema(ws, lint):
    """C-STORY: front matter must be present and valid."""
    text = (ws / STORY).read_text(encoding="utf-8")
    (ws / STORY).write_text(text.replace("---\n", "", 2), encoding="utf-8")
    assert "no YAML front matter" in lint(ws, "C-STORY")[0].message


@pytest.mark.parametrize(
    "merged, acceptance, ok",
    [
        ('"2026-10-27T23:00:00-04:00"', '"2026-10-28T20:05:13.000Z"', True),
        ('"2026-10-27T23:00:00-04:00"', '"20261028160513"', False),  # naive vs aware
        ("null", '"2026-10-28T04:00:00Z"', True),  # deadline 23:59:59 EDT on the 27th = 03:59:59 UTC on the 28th
        ("null", '"2026-10-28T03:59:58Z"', False),
        ('"2026-10-28"', "null", False),
    ],
)
def test_c_prereg_timing_times(ws, lint, merged, acceptance, ok):
    """C-PREREG-TIMING: timezone-aware comparison of merged_at < deadline < acceptance_datetime (settlement file)."""
    edit(ws, SETTLEMENT, 'merged_at: "2026-09-21T10:00:00-04:00"', f"merged_at: {merged}")
    edit(ws, SETTLEMENT, "acceptance_datetime: null", f"acceptance_datetime: {acceptance}")
    assert (lint(ws, "C-PREREG-TIMING") == []) is ok


# --------------------------------------------------------------------------- constitution
def test_c_rating_order_requires_business_rating(ws, lint):
    """C-RATING-ORDER: every thesis rates business and management."""
    edit(ws, THESIS, "  business: A-\n", "")
    assert "ratings.business" in lint(ws, "C-RATING-ORDER")[0].message


def test_c_rating_order_no_mechanical_order(ws, lint):
    """C-RATING-ORDER: decision-rights.yml no longer fixes a ranking order (§V13 is a judgement, not a sort)."""
    edit(ws, "public/constitution/decision-rights.yml", '  rule: "§V13"', '  rule: "00 §V13: judged, not sorted"')
    assert lint(ws, "C-RATING-ORDER") == []


@pytest.mark.parametrize("rows, flagged", [
    ("rows:\n  - {rank: 1, company: ACME, reason: '  '}\n", True),
    ("ranking:\n  - {rank: 1, company: ACME}\n", True),
    ("- {rank: 1, company: ACME, reason: Clears the Berkshire hurdle (fictitious).}\n", False),
    ("as_of: 2026-09-20\nnote: no rows yet\n", True),
])
def test_c_rating_order_ranking_rows_need_a_reason(ws, lint, rows, flagged):
    """C-RATING-ORDER: every row of the private hq/ranking.yml states a reason (under rows, ranking, or a top-level list)."""
    put(ws, "private/hq/ranking.yml", rows)
    assert bool(lint(ws, "C-RATING-ORDER", "private")) is flagged


def test_c_concentration_holdings_count(ws, lint):
    """C-CONCENTRATION: more holdings than max_holdings is a warning (rule 4 says about 4-5)."""
    edit(ws, RIGHTS, "max_holdings: 5", "max_holdings: 1")
    put(ws, "public/companies/BETA/thesis.yml", "company: BETA\nstatus: holding\n")
    found = [f for f in lint(ws, "C-CONCENTRATION") if "status holding" in f.message]
    assert found and all(f.level == "warning" for f in found)


def test_c_concentration_max_holdings_above_five_warns(ws, lint):
    """C-CONCENTRATION: max_holdings above 5 warns; zero or a non-integer is an error."""
    edit(ws, RIGHTS, "max_holdings: 5", "max_holdings: 6")
    assert [f.level for f in lint(ws, "C-CONCENTRATION")] == ["warning"]
    edit(ws, RIGHTS, "max_holdings: 6", "max_holdings: 0")
    errors = [f for f in lint(ws, "C-CONCENTRATION") if f.level == "error"]
    assert len(errors) == 1 and "positive integer" in errors[0].message


@pytest.mark.parametrize("weight, note, levels", [
    ("0.05", None, ["error"]),          # below the bar: not a meaningful position
    ("0.10", None, []),
    ("0.20", None, []),
    ("0.30", None, ["warning"]),        # above the bar's top without a reason
    ("0.30", "the business we understand best and are surest of", []),  # higher conviction, reason stated
])
def test_c_concentration_entry_bar_not_target(ws, lint, weight, note, levels):
    """C-CONCENTRATION: 10-20% is an entry bar, not a target (rule 4)."""
    edit(ws, BUY_MEMO, "target_weight: 0.15", f"target_weight: {weight}" + (f"\nweight_note: {note}" if note else ""))
    assert [f.level for f in lint(ws, "C-CONCENTRATION", "private")] == levels


def test_c_concentration_private_without_counterpart_uses_constitution_band(ws, lint):
    """C-CONCENTRATION: without decision-rights.yml the constitution's [0.10, 0.20] band applies."""
    edit(ws, BUY_MEMO, "target_weight: 0.15", "target_weight: 0.05")
    assert lint(ws, "C-CONCENTRATION", "private", counterpart=False)
    edit(ws, BUY_MEMO, "target_weight: 0.05", "target_weight: null")
    assert lint(ws, "C-CONCENTRATION", "private", counterpart=False)


def test_c_discount_rate_null_is_warning_partial_is_error(ws, lint):
    """C-DISCOUNT-RATE: all-null rates warn; partial rates, a missing rationale and empty method_note are errors."""
    edit(ws, BETA_VAL, "  risk_free: 0.045\n  risk_free_date: 2026-09-18\n  premium: 0.03\n  total: 0.075\n",
         "  risk_free: null\n  risk_free_date: null\n  premium: null\n  total: null\n")
    edit(ws, BETA_VAL, "  note: Cyclical demand makes BETA's cash flows less predictable (fictitious).\n", "")
    assert [f.level for f in lint(ws, "C-DISCOUNT-RATE", "private")] == ["warning"]
    edit(ws, BETA_VAL, "total: null", "total: 0.075")
    edit(ws, BETA_VAL, "method_note: One discount rate from BETA's own cash-flow record (fictitious numbers).", 'method_note: ""')
    messages = [f.message for f in lint(ws, "C-DISCOUNT-RATE", "private") if f.level == "error"]
    assert len(messages) == 3 and any("numeric" in m for m in messages) and any("discount_rate.note" in m for m in messages)
    assert any("method_note" in m for m in messages)


def test_c_discount_rate_premiums_are_not_compared_across_companies(ws, lint):
    """C-DISCOUNT-RATE: a higher-quality company may carry a higher premium (§V10: no cross-company ordering)."""
    edit(ws, ACME_VAL, "premium: 0.02\n  total: 0.065", "premium: 0.04\n  total: 0.085")
    assert lint(ws, "C-DISCOUNT-RATE", "private") == []


def test_c_discount_rate_missing_risk_free_date_warns(ws, lint):
    """C-DISCOUNT-RATE: the Treasury yield needs the date it was read (warning)."""
    edit(ws, ACME_VAL, "  risk_free_date: 2026-09-18\n", "")
    found = lint(ws, "C-DISCOUNT-RATE", "private")
    assert [f.level for f in found] == ["warning"] and "risk_free_date" in found[0].message


def test_c_sell_reasons_chinese_forbidden_reasons(ws, lint):
    """C-SELL-REASONS: forbidden reasons may be written in Chinese."""
    edit(ws, RIGHTS, "forbidden_sell_reasons: [price_decline, recession, panic, single_quarter_miss]",
         "forbidden_sell_reasons: [价格下跌, 经济衰退, 市场恐慌, 单季不及预期]")
    assert lint(ws, "C-SELL-REASONS") == []


def test_c_sell_reasons_private_needs_reason(ws, lint):
    """C-SELL-REASONS: a trim memo without sell_reason is flagged even without the counterpart."""
    edit(ws, "private/memos/2026-09-22-BETA-trim.yml", "sell_reason: management_deterioration\n", "")
    assert lint(ws, "C-SELL-REASONS", "private", counterpart=False)


def test_c_hurdle_warnings(ws, lint):
    """C-HURDLE: unquantified hurdles and holdings below the hurdle are warnings."""
    edit(ws, BETA_VAL, "hurdles: {brk: 0.09, voo: 0.08}", "hurdles: {brk: null, voo: null}")
    edit(ws, ACME_VAL, "implied_return: 0.11", "implied_return: 0.085")
    found = lint(ws, "C-HURDLE", "private")
    assert sorted(f.level for f in found) == ["warning", "warning"]
    assert any("holding ACME" in f.message and "first hurdle 0.09" in f.message for f in found)
    assert not any("holding ACME" in f.message for f in lint(ws, "C-HURDLE", "private", counterpart=False))


def test_c_hurdle_berkshire_is_the_first_bar_not_the_higher_of_two(ws, lint):
    """C-HURDLE: rule 7 says Berkshire or VOO; Berkshire is the first bar, VOO a second reference (§V6)."""
    edit(ws, ACME_VAL, "brk: 0.09, voo: 0.08", "brk: 0.08, voo: 0.10")
    edit(ws, BUY_MEMO, "hurdle: 0.09", "hurdle: 0.08")
    edit(ws, BUY_MEMO, "implied_return: 0.11", "implied_return: 0.09")
    found = lint(ws, "C-HURDLE", "private")
    assert [f.level for f in found if "memo" in f.message] == ["warning"]
    assert any("VOO reference 0.1" in f.message for f in found)


def test_c_single_order_monthly_memo_count(ws, lint):
    """C-SINGLE-ORDER: more than monthly_target_max memos in a month is a warning."""
    put(ws, "private/memos/2026-09-23-BETA-sell.yml",
        "id: x\ncompany: BETA\naction: sell\ndefault_option: maintain\ntimeout_days: 14\ncreated_at: 2026-09-23\n"
        "summary: x\nconstitution_refs: [R6]\nsell_reason: better_opportunity\n")
    found = lint(ws, "C-SINGLE-ORDER", "private")
    assert [f.level for f in found] == ["warning"] and "2026-09" in found[0].message


def test_c_default_hold_rights_default_option(ws, lint):
    """C-DEFAULT-HOLD: the decision-rights default option is maintain."""
    edit(ws, RIGHTS, "default_option: maintain", "default_option: execute")
    assert lint(ws, "C-DEFAULT-HOLD")


def test_c_decision_rights_l3_complete_and_trust_levels(ws, lint):
    """C-DECISION-RIGHTS: L3 holds every money action and amend_constitution; trust has levels 0-3."""
    edit(ws, RIGHTS, "actions: [buy, add, trim, sell, amend_constitution]", "actions: [buy, add, trim, sell]")
    edit(ws, RIGHTS, "    3: auto-merge and publish\n", "")
    messages = " ".join(f.message for f in lint(ws, "C-DECISION-RIGHTS"))
    assert "amend_constitution" in messages and "trust.levels" in messages


def test_c_constitution_map_failing_selftest(ws, lint, monkeypatch):
    """C-CONSTITUTION-MAP: a referenced check whose selftest fails is flagged."""
    monkeypatch.setattr(selftest, "selftest_passes", lambda cid: cid != "C-HURDLE")
    found = lint(ws, "C-CONSTITUTION-MAP")
    assert len(found) == 1 and "C-HURDLE fails its selftest" in found[0].message


def test_c_constitution_map_empty_check_list(ws, lint):
    """C-CONSTITUTION-MAP: a rule with no checks is flagged."""
    edit(ws, "public/constitution/rules.yml", "checks: [C-LLM-ENTRY]", "checks: []")
    assert "references no check" in lint(ws, "C-CONSTITUTION-MAP")[0].message


def test_c_agent_isolation_tokens_and_role_field(ws, lint):
    """C-AGENT-ISOLATION: cannot_see items may be compound tokens; the role field identifies the agent."""
    edit(ws, "public/agents/auditor.yml", "cannot_see: [reasoning, conclusions]", "cannot_see: [thesis_reasoning, draft_conclusions]")
    assert lint(ws, "C-AGENT-ISOLATION") == []
    put(ws, "public/agents/second_opinion.yml",
        "role: blind_reader\nname: x\nmodel: {id: m}\ncan_see: []\ncannot_see: [thesis]\noutputs: []\nprompts: []\n")
    assert len(lint(ws, "C-AGENT-ISOLATION")) == 2  # draft and conclusions missing
