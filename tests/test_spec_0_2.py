"""Specification 0.2: the new schema keys, the pre-registration file layout and the four new checks.

Each test's docstring names the check it covers.
"""

from __future__ import annotations

import datetime as dt
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from thesis_ci import contract, engine, selftest
from thesis_ci.checks import archive
from thesis_ci.checks.public import ADVICE_PHRASES, VALUATION_PHRASES
from thesis_ci.cli import main

THESIS = "public/companies/ACME/thesis.yml"
STORY = "public/companies/ACME/story.md"
LEDGER = "public/companies/ACME/ledger.yml"
PREREG = "public/companies/ACME/prereg/FY2027Q1.yml"
OWNER_PREREG = "public/companies/ACME/prereg/FY2027Q1-owner.yml"
SETTLEMENT = "public/companies/ACME/prereg/FY2027Q1.settlement.yml"
PATCH_UPDATE = "public/companies/ACME/updates/2026-09-22.md"
RIGHTS = "public/constitution/decision-rights.yml"
TRUST = "public/trust/levels.yml"
INDUSTRY = "public/industries/widgets/industry.yml"
ACME_VAL = "private/companies/ACME/valuation.yml"
BUY_MEMO = "private/memos/2026-09-20-ACME-entry.yml"
PROMPT_03 = "private/prompts/03-update.md"
PAST = "public/companies/ACME/prereg/FY2026Q4.yml"
AFTER_DEADLINE = dt.date(2026, 10, 28)  # the FY2027Q1 deadline is 2026-10-27 23:59:59 EDT
GIT = shutil.which("git")
POSIX = os.name == "posix"

# 00 §H4, the banned terms in the order the rulebook lists them.
H4_TERMS = [
    "买入区间", "价值中枢", "目标价", "隐含回报", "隐含年化回报", "价格评级", "price target", "target price", "buy range",
    "fair value range", "建议买入", "建议卖出", "建议增持", "建议减持", "建议加仓", "建议减仓", "买入评级", "卖出评级",
    "强烈推荐", "值得买入", "应该买入", "可以买入", "逢低买入", "建议建仓", "建议清仓", "strong buy", "overweight", "underweight",
]


def edit(ws: Path, rel: str, old: str, new: str) -> None:
    selftest.apply(ws, (selftest.replace(rel, old, new),))


def put(ws: Path, rel: str, text: str) -> None:
    selftest.apply(ws, (selftest.write(rel, text),))


def story_line(ws: Path, text: str) -> None:
    edit(ws, STORY, "最可能错在哪", text + "\n最可能错在哪")


def fake_ots(tmp_path: Path, monkeypatch, output: str, status: int) -> None:
    """Put an `ots` executable that prints ``output`` and exits with ``status`` first on PATH."""
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    script = bindir / "ots"
    script.write_text(f"#!/bin/sh\necho '{output}'\nexit {status}\n", encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")


# --------------------------------------------------------------------------- schemas
def test_c_schema_clean_example_uses_every_new_key(ws, lint):
    """C-SCHEMA: the bundled 0.2 example (components, supersedes, retired_at, evaluate_from, the prereg trio,
    escalations, options) passes, so the schemas accept what SPEC 0.2 describes."""
    assert lint(ws, "C-SCHEMA") == [] and lint(ws, "C-SCHEMA", "private") == []
    text = (ws / THESIS).read_text(encoding="utf-8")
    for key in ("components:", "supersedes:", "retired_at:", "evaluate_from:", "judge_notes:", "lookback:", "munger:"):
        assert key in text, key


@pytest.mark.parametrize("old, new, flagged", [
    ("evaluate_from: FY2027Q2", "evaluate_from: FY2028", False),  # a fiscal year is a period for evaluate_*
    ("evaluate_from: FY2027Q2", "evaluate_on: [FY2027Q4, FY2028]", False),
    ("evaluate_from: FY2027Q2", "evaluate_from: 2027Q2", True),
    ("effective_from: FY2027Q2", "effective_from: FY2027", True),  # effective_from is a quarter
    ("metric: recurring_share_v2.recurring", "metric: recurring_share_v2.recurring.us", True),
    ("metric: recurring_share_v2.recurring", "metric: Recurring", True),
    ("judge_notes: 只比较公司自己公布的中期目标；分析师预期不算目标。", "judge_notes: [只比较公司自己公布的中期目标, 分析师预期不算目标]", False),
    ("where: [本期与此前三期的业绩新闻稿与电话会, 投资者日材料]", "where: 本期业绩新闻稿", False),
    ("where: [本期与此前三期的业绩新闻稿与电话会, 投资者日材料]", "where: 3", True),
    ("    data: mixed\n    effective_from: FY2027Q2", "    data: external\n    effective_from: FY2027Q2", True),  # != metric_def
    ("origin: proposal:04B", "origin: proposal:04B-lite", False),
    ("origin: proposal:04B", "origin: archive:breaker", False),
    ("origin: report:watch", "origin: archive:watch", False),
    ("  munger: 2026-09-20\n", "  unknowns: 2026-09-20\n", False),
    ("  runway: 2026-09-20\n", "", True),  # one of the twelve dossier parts
])
def test_c_schema_thesis_0_2_keys(ws, lint, old, new, flagged):
    """C-SCHEMA: thesis.yml 0.2 keys: periods, dotted metrics, where / judge_notes forms, origins, reviewed parts."""
    edit(ws, THESIS, old, new)
    found = lint(ws, "C-SCHEMA")
    if "data: external" in new:  # the schema allows external; C-TEST-METRIC ties it to the definition
        assert found == [] and lint(ws, "C-TEST-METRIC")
        return
    assert bool(found) is flagged, found


def test_c_schema_template_tests_instantiate_into_a_valid_thesis(ws, lint):
    """C-SCHEMA: every Lynch template test, with id and effective_from added, is a valid 0.2 thesis test."""
    import yaml

    data = yaml.safe_load((ws / THESIS).read_text(encoding="utf-8"))
    tests = []
    for category in ("slow_grower", "stalwart", "fast_grower", "cyclical", "turnaround", "asset_play", "_common"):
        for n, t in enumerate(contract.template(category)["tests"]):
            test = {k: v for k, v in t.items() if k != "key"}
            letter = {"quantitative": "Q", "qualitative": "L", "staleness": "S"}[test["type"]]
            test.update(id=f"ACME-{letter}{100 + len(tests)}", origin="template:stalwart", effective_from="FY2027Q1")
            if test["type"] == "qualitative":
                test.update(judge="independent_model", evidence="required")
            tests.append(test)
    data["tests"] = tests
    (ws / THESIS).write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")
    assert lint(ws, "C-SCHEMA") == []
    assert any(t.get("section") == "bear_case" for t in tests)


@pytest.mark.parametrize("path, old, new, flagged", [
    (PREREG, "probability: 0.6\n", "probability: 0.05\n", False),
    (PREREG, "probability: 0.6\n", "probability: 0.04\n", True),
    (PREREG, "  placeholder: false\n", "", True),
    (PREREG, "  form: 8-K\n", "  form: 8-K/A\n", True),
    (PREREG, "  period: FY2027Q1\n", "  period: 2027Q1\n", True),
    (PREREG, "horizon: mixed\n", "", False),  # the top-level horizon is optional now
    (PREREG, "    pillar: P2\n", "    pillar: pillar-2\n", True),
    (PREREG, "    added_by: system\n    pillar: P2", "    added_by: owner\n    pillar: P2", True),  # system file
    (PREREG, "    resolves_by: 2026-11-30\n", "", True),
    (PREREG, "author: system\n", "author: system\nmerged_at: null\n", True),  # settlement data is not in this file
    (OWNER_PREREG, "items:\n", "items: []\nx_items:\n", True),
    (SETTLEMENT, "results: []", "results: [{id: ACME-FY2027Q1-1, outcome: happened, values: {revenue_yoy: 0.12},"
                                " evidence: x, source: ACME-10K-FY2026#Item8, reasoning: y, settled_at: 2026-11-02,"
                                " hq_ruling: null}]", False),
    (SETTLEMENT, "accession: null", "accession: 12-34", True),
])
def test_c_schema_prereg_trio(ws, lint, path, old, new, flagged):
    """C-SCHEMA: items files (system and owner) and the settlement file follow their own schemas."""
    edit(ws, path, old, new)
    assert bool(lint(ws, "C-SCHEMA")) is flagged


def test_c_schema_owner_file_may_only_override(ws, lint):
    """C-SCHEMA: the owner's file may hold overrides and no items, but not nothing at all."""
    text = (ws / OWNER_PREREG).read_text(encoding="utf-8")
    start, end = text.index("items:\n"), text.index("overrides:")
    (ws / OWNER_PREREG).write_text(text[:start] + "items: []\n" + text[end:], encoding="utf-8")
    assert lint(ws, "C-SCHEMA") == []
    edit(ws, OWNER_PREREG, "overrides:\n  - {id: ACME-FY2027Q1-1, probability: 0.7, note: 渠道调研显示订单改善（所有者的判断）}\n", "")
    assert lint(ws, "C-SCHEMA")


@pytest.mark.parametrize("name, text, message", [
    ("FY2027Q1-draft.yml", None, "pre-registration files are named"),
    ("FY2027Q2.yml", None, "does not match the file name"),
    ("FY2027Q2.settlement.yml", "company: ACME\nperiod: FY2027Q1\nresults: []\n", "does not match the file name"),
])
def test_c_schema_prereg_file_names(ws, lint, name, text, message):
    """C-SCHEMA: prereg/<period>.yml, <period>-owner.yml and <period>.settlement.yml carry their period in the name."""
    put(ws, f"public/companies/ACME/prereg/{name}", text or (ws / PREREG).read_text(encoding="utf-8"))
    assert any(message in f.message for f in lint(ws, "C-SCHEMA"))


def test_c_schema_prereg_item_ids_name_company_and_period(ws, lint):
    """C-SCHEMA: item and override ids start with <TICKER>-<period>-."""
    edit(ws, PREREG, "id: ACME-FY2027Q1-2", "id: ACME-FY2026Q4-2")
    edit(ws, OWNER_PREREG, "{id: ACME-FY2027Q1-1,", "{id: BETA-FY2027Q1-1,")
    messages = [f.message for f in lint(ws, "C-SCHEMA")]
    assert len(messages) == 2 and all("does not start with 'ACME-FY2027Q1-'" in m for m in messages)


def test_c_schema_repo_spec_version(ws, lint):
    """C-SCHEMA: repo.yml still at spec 0.1 is a warning during the migration; other versions are errors."""
    edit(ws, "public/repo.yml", 'spec_version: "0.2"', 'spec_version: "0.1"')
    assert [f.level for f in lint(ws, "C-SCHEMA")] == ["warning"]
    edit(ws, "public/repo.yml", 'spec_version: "0.1"', 'spec_version: "0.3"')
    assert [f.level for f in lint(ws, "C-SCHEMA")] == ["error"]


@pytest.mark.parametrize("path, old, new, flagged", [
    (BUY_MEMO, "drafted_by: hq_capital_allocator\n", "drafted_by: company_manager\n", True),
    (BUY_MEMO, "drafted_by: hq_capital_allocator\n", "", True),
    (BUY_MEMO, "  - {key: buy, description: Enter within the entry band.}\n", "", True),  # fewer than two options
    (BUY_MEMO, "constitution_refs: [R4, R7, R8]", "constitution_refs: [R4, H3]", False),
    (BUY_MEMO, "constitution_refs: [R4, R7, R8]", "constitution_refs: [rule4]", True),
    (BUY_MEMO, "trigger: {tests: [], update: companies/ACME/updates/2026-09-22.md}", "trigger: {tests: [ACME-Q2]}", False),
    (BUY_MEMO, "trigger: {tests: [], update: companies/ACME/updates/2026-09-22.md}", "trigger: {update: x}", True),
    (BUY_MEMO, "  - {claim: Recurring revenue is most of ACME's revenue (fictitious)., source: ACME-RPT-2026-09#p4}\n",
     "  - {claim: Recurring revenue is most of ACME's revenue (fictitious).}\n", True),
    (ACME_VAL, "margin_of_safety: [0.25, 0.35]", "margin_of_safety: [25, 35]", True),
    (ACME_VAL, "margin_of_safety: [0.25, 0.35]", "margin_of_safety: [0.25]", True),
    (ACME_VAL, "doc_status: effective", "doc_status: draft", True),
    (ACME_VAL, "price_rating: B", "price_rating: A", False),
    (ACME_VAL, "  note: Recurring revenue and a decade of steady margins make ACME's cash flows predictable (fictitious).\n",
     "", True),  # the schema requires the premium rationale once total is a number
    (ACME_VAL, "source: ACME-RPT-2026-09#p43}", "}", True),
    (ACME_VAL, "  risk_free_date: 2026-09-18\n", "  risk_free_date: 18/09/2026\n", True),
])
def test_c_schema_private_0_2_keys(ws, lint, path, old, new, flagged):
    """C-SCHEMA: memo options / drafted_by / evidence / trigger and valuation doc_status / margin_of_safety / anchor."""
    edit(ws, path, old, new)
    assert bool(lint(ws, "C-SCHEMA", "private")) is flagged


def test_c_schema_amend_constitution_memo_needs_no_company(ws, lint):
    """C-SCHEMA: a constitution amendment memo may omit company; a money memo may not."""
    put(ws, "private/memos/2026-09-23-amend.yml",
        "id: 2026-09-23-amend\naction: amend_constitution\ndefault_option: maintain\ntimeout_days: 14\n"
        "created_at: 2026-09-23\nsummary: Clarify R7.\nconstitution_refs: [R7, H4]\ndrafted_by: hq_capital_allocator\n"
        "options: [{key: maintain}, {key: amend}]\n")
    assert lint(ws, "C-SCHEMA", "private") == []
    edit(ws, BUY_MEMO, "company: ACME\n", "")
    assert any("'company' is a required property" in f.message for f in lint(ws, "C-SCHEMA", "private"))


def test_c_schema_escalations_are_private(ws, lint):
    """C-SCHEMA: escalations/*.yml follow the escalation schema in the private archive only."""
    edit(ws, "private/escalations/2026-09-21-BETA-management.yml", "drafted_by: company_manager", "drafted_by: hq_capital_allocator")
    assert any("escalation.schema.json" in f.message for f in lint(ws, "C-SCHEMA", "private"))
    put(ws, "public/escalations/x.yml", "id: x\n")  # public: C-PUBLIC-NO-VALUATION's job, not a schema error
    assert lint(ws, "C-SCHEMA") == [] and lint(ws, "C-PUBLIC-NO-VALUATION")


@pytest.mark.parametrize("path, old, new, flagged", [
    (LEDGER, "    acknowledged_source: null\n", "    acknowledged_source: ACME-10K-FY2026#Item7\n", False),
    (LEDGER, "    last_mentioned: 2026-08-01\n", "    last_mentioned: August\n", True),
    (LEDGER, "    probability: 0.7\n", "    probability: 0.97\n", True),
    (LEDGER, "    status: pending\n    last_mentioned", "    status: silently_dropped\n    last_mentioned", False),  # management
    (RIGHTS, '    "3": auto-merge and publish once every check passes\n', "", True),
    (RIGHTS, "  scoring: {fact_error: -1, divergence_ruled_against: counted, unit: one quarterly update per company}\n", "", False),
    (RIGHTS, "gate: {lint: no_errors, audit: must_fix_resolved, breakers: disposed}\n", "", False),
    ("public/agents/auditor.yml", "role: auditor", "role: judge", False),
    ("public/agents/auditor.yml", "role: auditor", "role: fact_checker", True),
    ("public/companies/ACME/sources.yml", "    kind: news\n", "    kind: review\n", False),
    ("public/companies/ACME/sources.yml", "    kind: news\n", "    kind: tweet\n", True),
    (INDUSTRY, "trust_level: 1\n", "trust_level: 4\n", True),
])
def test_c_schema_public_0_2_keys(ws, lint, path, old, new, flagged):
    """C-SCHEMA: ledger, decision rights (routing, scoring, gate), agent roles, source kinds, industry trust level."""
    edit(ws, path, old, new)
    assert bool(lint(ws, "C-SCHEMA")) is flagged


# --------------------------------------------------------------------------- thesis tests
@pytest.mark.parametrize("rule, ok", [
    ("{metric: recurring, op: '<', threshold: 1}", True),  # a component by its bare name
    ("{metric: recurring_share_v2.revenue, op: '<', threshold: 1}", True),
    ("{metric: gross_margin.cloud, op: '<', threshold: 1}", True),  # a registered metric: components unverifiable
    ("{metric: recurring_share.recurring, op: '<', threshold: 1}", False),  # another test's metric_def
    ("{metric: recurring_share_v2.recurring_share_v2, op: '<', threshold: 1}", False),
])
def test_c_test_metric_components_resolve(ws, lint, rule, ok):
    """C-TEST-METRIC: rule metrics resolve to the registry, the test's metric_def or one of its components."""
    edit(ws, THESIS, "        - {metric: recurring_share_v2.recurring, op: decrease, threshold: 0, unit: \"%\", consecutive: 1, period: year}",
         f"        - {rule}")
    assert (lint(ws, "C-TEST-METRIC") == []) is ok


def test_c_test_metric_component_without_components(ws, lint):
    """C-TEST-METRIC: <metric>.<component> of a metric_def that defines no components does not resolve."""
    edit(ws, THESIS, "rule: {op: \"<\", threshold: 50, unit: \"%\", consecutive: 2, period: year}\n    data: filing_text",
         "rule: {metric: recurring_share.recurring, op: \"<\", threshold: 50}\n    data: filing_text")
    assert "metric_def has no components" in lint(ws, "C-TEST-METRIC")[0].message


def test_c_test_metric_legacy_param_defs_still_resolve(ws, lint):
    """C-TEST-METRIC: params.metric_defs (0.1) still defines sub-metrics while archives migrate to components."""
    edit(ws, THESIS, "    metric: gross_margin\n",
         "    metric: gross_margin\n    params: {metric_defs: [{id: attach_rate, description: 配套率, unit: '%', data: filing_text}]}\n")
    edit(ws, THESIS, 'rule: {op: "<", threshold: 55, unit: "%", consecutive: 2, period: quarter}',
         'rule: {all_of: [{metric: gross_margin, op: "<", threshold: 55}, {metric: attach_rate.us, op: "<", threshold: 30}]}')
    assert lint(ws, "C-TEST-METRIC") == []


@pytest.mark.parametrize("old, new, message", [
    ("supersedes: ACME-Q4", "supersedes: ACME-Q5", "does not name itself"),
    ("    effective_from: FY2027Q1\n    retired_at: FY2027Q2", "    effective_from: FY2027Q3\n    retired_at: FY2027Q2",
     "comes before effective_from"),
])
def test_c_tests_min_lifecycle(ws, lint, old, new, message):
    """C-TESTS-MIN: supersedes names another test of the file; retired_at does not precede effective_from."""
    edit(ws, THESIS, old, new)
    assert any(message in f.message for f in lint(ws, "C-TESTS-MIN"))


def test_c_tests_min_retirement_follows_the_period(ws, lint):
    """C-TESTS-MIN: with --period, a test retired only from a later period still counts."""
    for anchor in ("  - id: ACME-Q2", "    first_readable", "  - id: ACME-Q4"):
        edit(ws, THESIS, f"    effective_from: FY2027Q1\n{anchor}", f"    effective_from: FY2027Q1\n    retired_at: FY2027Q3\n{anchor}")
    assert lint(ws, "C-TESTS-MIN")  # no period: a test with retired_at is retired
    assert lint(ws, "C-TESTS-MIN", period="FY2027Q2") == []  # FY2027Q2: still in force
    assert lint(ws, "C-TESTS-MIN", period="FY2027Q3")


def test_c_test_qual_evidence_where_must_name_documents(ws, lint):
    """C-TEST-QUAL-EVIDENCE: where lists the documents the judge reads (an empty list does not)."""
    edit(ws, THESIS, "where: [本期与此前三期的业绩新闻稿与电话会, 投资者日材料]", "where: []")
    assert "needs where" in lint(ws, "C-TEST-QUAL-EVIDENCE")[0].message


def test_c_src_fact_ledger_predictions_need_no_tag(ws, lint):
    """C-SRC-FACT: the system's and the owner's ledger predictions are predictions; management statements are facts."""
    assert "55%" in (ws / LEDGER).read_text(encoding="utf-8")  # untagged, in a system entry
    assert lint(ws, "C-SRC-FACT") == []
    edit(ws, LEDGER, "    side: system\n", "    side: management\n")
    assert lint(ws, "C-SRC-FACT")


# --------------------------------------------------------------------------- public content
def test_c_public_no_advice_phrase_lists_are_exactly_h4():
    """C-PUBLIC-NO-ADVICE: the literal phrase lists of the two wording checks are exactly the terms of 00 §H4."""
    assert sorted(VALUATION_PHRASES + ADVICE_PHRASES) == sorted(H4_TERMS)


@pytest.mark.parametrize("term", [t for t in H4_TERMS if t not in ("overweight", "underweight")])
def test_c_public_no_advice_every_h4_term_is_flagged(ws, lint, term):
    """C-PUBLIC-NO-ADVICE: every §H4 term is flagged in public content (valuation terms by C-PUBLIC-NO-VALUATION)."""
    story_line(ws, f"本页不写{term}。")
    check = "C-PUBLIC-NO-VALUATION" if term in VALUATION_PHRASES else "C-PUBLIC-NO-ADVICE"
    assert lint(ws, check)


@pytest.mark.parametrize("rel, text", [
    ("public/mistakes.md", "# 错误清单\n\n上一版写了建议加仓。\n"),
    ("public/companies/ACME/updates/2026-10-30.md", "---\nas_of: 2026-10-30\n---\n\n结论：建议减仓。\n"),
    ("public/companies/ACME/updates/2026-10-30.yml", "pr_body: 摘要。buy rating 不写。\n"),
])
def test_c_public_no_advice_scans_mistakes_and_updates(ws, lint, rel, text):
    """C-PUBLIC-NO-ADVICE: the root mistakes.md and companies/*/updates/ are public content."""
    put(ws, rel, text)
    assert [f.file for f in lint(ws, "C-PUBLIC-NO-ADVICE")] == [rel.split("/", 1)[1]]


@pytest.mark.parametrize("text, flagged", [
    ("市盈率 25 倍[src:ACME-RPT-2026-09#p5]", True),
    ("P/E of 25", True),
    ("p/e 18.5", True),
    ("市值 2 万亿美元[src:ACME-RPT-2026-09#p5]", True),
    ("自由现金流收益率 4%[src:ACME-RPT-2026-09#p5]", True),
    ("FCF yield of 3.5%[src:ACME-RPT-2026-09#p5]", True),
    ("market cap of $2.1 trillion [src:ACME-RPT-2026-09#p5]", True),
    ("现金连续两年高于市值 40%", True),
    ("不以市盈率比较代替估值", False),  # no number
    ("2025 年致股东信说留存收益要创造至少等额的市值[src:ACME-RPT-2026-09#p5]", False),  # a year is not a quantity
    ("BRK-Q7 的分母是市值", False),  # an identifier is not a quantity
    ("占市值的读数只记在私有仓库（硬规则 4）", False),  # a single-digit rule number is not a quantity
    ("FY2026 的市值读数只在私有仓库", False),
    ("资本回报率 30%[src:ACME-RPT-2026-09#p5]", False),  # operating ratios are fine
    ("每股派息 10 美分[src:ACME-RPT-2026-09#p5]；2025 年起只要留存收益创造等额市值就不派息", False),  # ；ends a sentence
    ("每股派息 10 美分[src:ACME-RPT-2026-09#p5]；市值 3,000 亿美元时复核", True),
    ("市净率 1.5 倍[src:ACME-RPT-2026-09#p5]", True),
    ("P/B of 1.4", True),
    ("price-to-book of 1.3", True),
    ("价格低于 1.2 倍账面时连续四个季度零回购", True),
    ("股价跌到 1.1 倍每股账面", True),
    ("回购均价高于 1.8 倍账面[src:ACME-RPT-2026-09#p5]", False),  # the company's disclosed repurchase price (§H2 item 3)
    ("回购价格高于 1.8 倍账面", False),
    ("metric: buyback_avg_price_to_book, threshold: 1.8", False),  # an identifier for the repurchase-price ratio
    ("不看市净率", False),  # no number
])
def test_c_public_no_valuation_price_multiples(ws, lint, text, flagged):
    """C-PUBLIC-NO-VALUATION: a price-derived multiple and a number in the same sentence (00 §H4)."""
    story_line(ws, text + "。")
    assert bool(lint(ws, "C-PUBLIC-NO-VALUATION")) is flagged


def test_c_public_no_valuation_price_multiples_in_yaml_and_mistakes(ws, lint):
    """C-PUBLIC-NO-VALUATION: the multiples check reads YAML content and mistakes.md too, sentence by sentence."""
    edit(ws, THESIS, "todo:\n  - 补充分部数据", "todo:\n  - 补充分部数据；市值读数不写\n  - 市盈率 30 倍时复核")
    put(ws, "public/mistakes.md", "# 错误清单\n\n上一版写了市值 3,000 亿美元[src:OO-LOG-2026-09]。\n")
    found = lint(ws, "C-PUBLIC-NO-VALUATION")
    assert sorted((f.file, f.line) for f in found) == [("companies/ACME/thesis.yml", 166), ("mistakes.md", 3)]


# --------------------------------------------------------------------------- code
def test_c_no_price_feed_private_price_history_is_allowed(ws, lint):
    """C-NO-PRICE-FEED: the private pipeline/price_history.py may fetch prices (year-end closes, 00 §H2); public may not."""
    put(ws, "private/pipeline/price_history.py", "import yfinance  # year-end unadjusted closes\n")
    assert lint(ws, "C-NO-PRICE-FEED", "private") == []
    put(ws, "private/pipeline/price_other.py", "import yfinance\n")
    assert [f.file for f in lint(ws, "C-NO-PRICE-FEED", "private")] == ["pipeline/price_other.py"]
    put(ws, "public/pipeline/price_history.py", "import yfinance\n")
    assert [f.file for f in lint(ws, "C-NO-PRICE-FEED")] == ["pipeline/price_history.py"]


# --------------------------------------------------------------------------- constitution
def test_c_rating_order_ranking_file_is_checked_where_it_lives(ws, lint):
    """C-RATING-ORDER: runs on both sides: ratings in the public archive, the ranking in the private one."""
    assert lint(ws, "C-RATING-ORDER", "private") == []
    edit(ws, "private/hq/ranking.yml", "reason: Clears the Berkshire hurdle", "why: Clears the Berkshire hurdle")
    found = lint(ws, "C-RATING-ORDER", "private", counterpart=False)
    assert len(found) == 1 and "row 1 (ACME) has no reason" in found[0].message and found[0].line == 4


# --------------------------------------------------------------------------- C-PREREG-TIMING / C-PREREG-IMMUTABLE
def test_c_prereg_timing_settlement_without_items_is_ignored(ws, lint):
    """C-PREREG-TIMING: a settlement file compares against its own period's items file only."""
    put(ws, "public/companies/ACME/prereg/FY2026Q4.settlement.yml",
        "company: ACME\nperiod: FY2026Q4\nmerged_at: \"2026-12-01T00:00:00-05:00\"\nresults: []\n")
    assert lint(ws, "C-PREREG-TIMING") == []


def test_c_prereg_immutable_vacuous(ws, lint, tmp_path):
    """C-PREREG-IMMUTABLE: nothing to check before the deadline or without pre-registrations."""
    assert lint(ws, "C-PREREG-IMMUTABLE", today=dt.date(2026, 10, 27)) == []  # the deadline is the end of the 27th
    for rel in (PREREG, OWNER_PREREG, SETTLEMENT):
        (ws / rel).unlink()
    assert lint(ws, "C-PREREG-IMMUTABLE", today=AFTER_DEADLINE) == []


def test_c_prereg_immutable_missing_proofs_after_the_deadline(ws, lint):
    """C-PREREG-IMMUTABLE: after the deadline the items files (system and owner) need <file>.ots; the settlement does not."""
    found = lint(ws, "C-PREREG-IMMUTABLE", today=AFTER_DEADLINE)
    assert [(f.level, f.file) for f in found] == [
        ("error", "companies/ACME/prereg/FY2027Q1-owner.yml"), ("error", "companies/ACME/prereg/FY2027Q1.yml")]
    assert all(".ots is missing" in f.message for f in found)


def test_c_prereg_immutable_cannot_verify_without_ots(ws, lint, monkeypatch):
    """C-PREREG-IMMUTABLE: a proof that cannot be verified here (no ots client) is a warning."""
    monkeypatch.setattr(archive, "ots_executable", lambda: None)
    for rel in (PREREG, OWNER_PREREG):
        (ws / f"{rel}.ots").write_bytes(b"\x00OpenTimestamps\x00\x00Proof\x00")
    found = lint(ws, "C-PREREG-IMMUTABLE", today=AFTER_DEADLINE)
    assert [f.level for f in found] == ["warning", "warning"] and all("not installed" in f.message for f in found)


@pytest.mark.skipif(not POSIX, reason="the fake ots client is a shell script")
@pytest.mark.parametrize("output, status, expected", [
    ("Success! Bitcoin block 123456 attests existence as of 2026-10-20 EDT", 0, []),
    ("File does not match original!", 1, ["error"]),
    ("Could not connect to local Bitcoin node", 1, ["warning"]),
    ("Pending confirmation in Bitcoin blockchain", 1, ["warning"]),
    ("Bad timestamp", 1, ["error"]),
])
def test_c_prereg_immutable_ots_verify(ws, lint, tmp_path, monkeypatch, output, status, expected):
    """C-PREREG-IMMUTABLE: `ots verify` must pass; a mismatch fails, an unreachable node or a pending proof warns."""
    fake_ots(tmp_path, monkeypatch, output, status)
    (ws / OWNER_PREREG).unlink()
    (ws / f"{PREREG}.ots").write_bytes(b"\x00OpenTimestamps\x00\x00Proof\x00")
    found = lint(ws, "C-PREREG-IMMUTABLE", today=AFTER_DEADLINE)
    assert [f.level for f in found] == expected
    assert all(f.file == "companies/ACME/prereg/FY2027Q1.yml.ots" for f in found)


# --------------------------------------------------------------------------- C-TRUST-WRITE
def test_c_trust_write_clean_and_without_levels_file(ws, lint):
    """C-TRUST-WRITE: the example passes; without trust/levels.yml only reviewed_sections is checked."""
    assert lint(ws, "C-TRUST-WRITE") == []
    (ws / TRUST).unlink()
    edit(ws, THESIS, "trust_level: 1", "trust_level: 3")
    assert lint(ws, "C-TRUST-WRITE") == []


@pytest.mark.parametrize("text, message", [
    ("companies:\n  BETA: 1\n", "has no level for ACME"),
    ("ACME: 2\n", "differs from trust/levels.yml (2)"),  # tickers at the top level
    ("as_of: 2026-09-22\n", "cannot be read"),
    ("companies: [ACME]\n", "cannot be read"),
])
def test_c_trust_write_levels_file(ws, lint, text, message):
    """C-TRUST-WRITE: thesis trust_level equals the pipeline's record in trust/levels.yml (warnings)."""
    put(ws, TRUST, text)
    found = lint(ws, "C-TRUST-WRITE")
    assert [f.level for f in found] == ["warning"] and message in found[0].message


def test_c_trust_write_industry_level(ws, lint):
    """C-TRUST-WRITE: an industry module's trust_level equals trust/levels.yml's industries entry."""
    edit(ws, TRUST, "  widgets: 1", "  widgets: 0")
    found = lint(ws, "C-TRUST-WRITE")
    assert [f.file for f in found] == ["industries/widgets/industry.yml"]


def test_c_trust_write_reviewed_sections(ws, lint):
    """C-TRUST-WRITE: a reviewed date equal to an update's as_of must be listed in that update's reviewed_sections."""
    edit(ws, THESIS, "  moat: 2026-09-20", "  moat: 2026-09-22")
    found = lint(ws, "C-TRUST-WRITE")
    assert len(found) == 1 and "reviewed.moat = 2026-09-22" in found[0].message and found[0].line == 21
    put(ws, "public/companies/ACME/updates/2026-09-22-b.yml", "as_of: 2026-09-22\nreviewed_sections: [moat]\n")
    assert lint(ws, "C-TRUST-WRITE") == []  # two updates on one day: their lists together


# --------------------------------------------------------------------------- C-TEST-FROZEN
def test_c_test_frozen_vacuous_without_base_ref_or_period(ws, lint):
    """C-TEST-FROZEN: without --base-ref, or without --period, nothing is compared."""
    edit(ws, THESIS, 'rule: {op: "<", threshold: 55,', 'rule: {op: "<", threshold: 50,')
    assert lint(ws, "C-TEST-FROZEN") == []
    assert lint(ws, "C-TEST-FROZEN", base_ref="HEAD") == []
    assert lint(ws, "C-TEST-FROZEN", period="FY2027Q1") == []


def test_c_test_frozen_outside_git(ws, lint):
    """C-TEST-FROZEN: outside a git work tree the comparison cannot run (warning)."""
    if GIT is not None:
        top = subprocess.run([GIT, "-C", str(ws / "public"), "rev-parse", "--is-inside-work-tree"], capture_output=True)
        if top.returncode == 0:
            pytest.skip("the temporary directory is inside a git work tree")
    found = lint(ws, "C-TEST-FROZEN", base_ref="HEAD", period="FY2027Q1")
    assert [f.level for f in found] == ["warning"] and "not a git work tree" in found[0].message


@pytest.mark.skipif(GIT is None, reason="git not installed")
def test_c_test_frozen_unknown_base_ref(ws, lint):
    """C-TEST-FROZEN: a --base-ref that names no commit is an error (the comparison cannot be skipped silently)."""
    selftest.apply(ws, (selftest.git_commit("public"),))
    found = lint(ws, "C-TEST-FROZEN", base_ref="origin/no-such-branch", period="FY2027Q1")
    assert [f.level for f in found] == ["error"] and "does not name a commit" in found[0].message


@pytest.mark.skipif(GIT is None, reason="git not installed")
@pytest.mark.parametrize("old, new, period, flagged", [
    ('rule: {op: "<", threshold: 55,', 'rule: {op: "<", threshold: 50,', "FY2027Q1", True),
    ("fail_if: 连续两个季度低于 55%", "fail_if: 连续三个季度低于 55%", "FY2027Q1", True),
    ("warn_if: 低于 58%", "warn_if: 低于 57%", "FY2027Q1", True),
    ("    max_age_quarters: 4\n", "    max_age_quarters: 6\n", "FY2027Q1", True),
    ('rule: {op: "<", threshold: 55,', 'rule: {op: "<", threshold: 50,', "FY2026Q4", False),  # not in force yet
    ("fail_if: 连续两年低于 50%，且经常性收入同比下降", "fail_if: 连续两年低于 45%，且经常性收入同比下降", "FY2027Q1", False),  # from FY2027Q2
    ("fail_if: 连续两年低于 50%\n", "fail_if: 连续两年低于 40%\n", "FY2027Q2", False),  # ACME-Q4 retired at FY2027Q2
    ("fail_if: 连续两年低于 50%\n", "fail_if: 连续两年低于 40%\n", "FY2027Q1", True),
    ("claim: 毛利率守住定价权", "claim: 毛利率守住定价权与护城河", "FY2027Q1", False),  # not a criterion
    ('rule: {op: "<", threshold: 55, unit: "%", consecutive: 2, period: quarter}',
     'rule:\n      op: "<"\n      threshold: 55\n      unit: "%"\n      consecutive: 2\n      period: quarter', "FY2027Q1", False),
])
def test_c_test_frozen_compares_with_the_base(ws, lint, old, new, period, flagged):
    """C-TEST-FROZEN: criteria of tests in force for --period are frozen; later tests, retired tests and style are free."""
    selftest.apply(ws, (selftest.git_commit("public"),))
    edit(ws, THESIS, old, new)
    found = lint(ws, "C-TEST-FROZEN", base_ref="HEAD", period=period)
    assert bool(found) is flagged, found


@pytest.mark.skipif(GIT is None, reason="git not installed")
def test_c_test_frozen_tests_without_effective_from_count_as_in_force(ws, lint):
    """C-TEST-FROZEN: a base test written before effective_from existed is in force; a new test may be added."""
    edit(ws, THESIS, "    data: xbrl\n    effective_from: FY2027Q1\n    first_readable", "    data: xbrl\n    first_readable")
    selftest.apply(ws, (selftest.git_commit("public"),))
    edit(ws, THESIS, "    data: xbrl\n    first_readable", "    data: xbrl\n    effective_from: FY2027Q1\n    first_readable")
    edit(ws, THESIS, "todo:\n", "  - {id: ACME-S9, type: staleness, claim: 未知清单每季复查, origin: manual, severity: watch,"
                               " covers: [other], section: unknowns, max_age_quarters: 1, effective_from: FY2027Q2}\ntodo:\n")
    assert lint(ws, "C-TEST-FROZEN", base_ref="HEAD", period="FY2027Q1") == []
    edit(ws, THESIS, 'rule: {op: "<", threshold: 55,', 'rule: {op: "<", threshold: 50,')
    assert "ACME-Q2: rule changed" in lint(ws, "C-TEST-FROZEN", base_ref="HEAD", period="FY2027Q1")[0].message


@pytest.mark.skipif(GIT is None, reason="git not installed")
def test_c_test_frozen_cli_options(ws, capsys):
    """C-TEST-FROZEN: lint --base-ref and --period reach the check; a malformed period is a usage error."""
    selftest.apply(ws, (selftest.git_commit("public"),))
    edit(ws, THESIS, 'rule: {op: "<", threshold: 55,', 'rule: {op: "<", threshold: 50,')
    args = ["lint", str(ws / "public"), "--only", "C-TEST-FROZEN", "--today", "2026-09-24", "--base-ref", "HEAD"]
    assert main(args) == 0  # no period: nothing is frozen
    assert main(args + ["--period", "FY2027Q1"]) == 1
    assert "[C-TEST-FROZEN] ACME-Q2: rule changed" in capsys.readouterr().out
    with pytest.raises(SystemExit) as exc:
        main(args + ["--period", "2027Q1"])
    assert exc.value.code == 2


# --------------------------------------------------------------------------- C-PROMPT-ISOLATION
def test_c_prompt_isolation_vacuous(ws, lint):
    """C-PROMPT-ISOLATION: the example passes; without the counterpart, prompts or agents there is nothing to compare."""
    edit(ws, PROMPT_03, '"question_list?"]', '"question_list?", blind_answers]')
    assert lint(ws, "C-PROMPT-ISOLATION", "private", counterpart=False) == []
    shutil.rmtree(ws / "public" / "agents")
    assert lint(ws, "C-PROMPT-ISOLATION", "private") == []


@pytest.mark.parametrize("front, flagged", [
    ('role: company_manager\ninputs: [run_date, "blind_answers?"]\n', True),  # top-level role and inputs, optional mark
    ('role: company_manager\nparts:\n  A: {inputs: [blind_answers_14A]}\n', True),  # §F0 part suffix
    ('role: company_manager\nparts:\n  A: {inputs_pass1: [dossier], inputs_pass2: [blind_answers]}\n', True),
    ('role: company_manager\nparts:\n  A: {role: hq_capital_allocator, inputs: [blind_answers]}\n', False),  # HQ sees all
    ('parts:\n  A: {role: pipeline, inputs: [blind_answers]}\n', False),  # no agent file for the role
    ('role: company_manager\ninputs: [blind_answers_draft_summary]\n', False),  # another thing
    ('role: blind_reader\ninputs: [filings, question_list_stripped, draft]\n', True),
])
def test_c_prompt_isolation_front_matter_forms(ws, lint, front, flagged):
    """C-PROMPT-ISOLATION: top-level inputs, parts, inputs_pass*, role defaults, ? and part suffixes (warnings)."""
    put(ws, "private/prompts/99-example.md", f"---\nid: \"99\"\ntitle: example\n{front}---\n\nbody\n")
    found = lint(ws, "C-PROMPT-ISOLATION", "private")
    assert bool(found) is flagged, found
    assert all(f.level == "warning" and f.file == "prompts/99-example.md" for f in found)


def test_c_prompt_isolation_reports_the_input_line(ws, lint):
    """C-PROMPT-ISOLATION: the finding points at the part's line in the front matter."""
    edit(ws, PROMPT_03, "  revise: {inputs: [draft_outputs, findings_04A]", "  revise: {inputs: [draft_outputs, findings_04A, blind_answers]")
    found = lint(ws, "C-PROMPT-ISOLATION", "private")
    assert len(found) == 1 and found[0].line == 8 and "part revise (company_manager)" in found[0].message


# --------------------------------------------------------------------------- whole archive
def test_every_new_check_is_in_the_registry_and_documented():
    """C-PREREG-IMMUTABLE, C-TRUST-WRITE, C-TEST-FROZEN, C-PROMPT-ISOLATION: registered with the contract's scope and level."""
    meta = {m["id"]: m for m in contract.registered_checks()}
    assert (meta["C-PREREG-IMMUTABLE"]["scope"], meta["C-PREREG-IMMUTABLE"]["level"]) == ("public", "error")
    assert (meta["C-TRUST-WRITE"]["scope"], meta["C-TRUST-WRITE"]["level"]) == ("public", "warning")
    assert (meta["C-TEST-FROZEN"]["scope"], meta["C-TEST-FROZEN"]["level"]) == ("public", "error")
    assert (meta["C-PROMPT-ISOLATION"]["scope"], meta["C-PROMPT-ISOLATION"]["level"]) == ("private", "warning")
    spec = (contract.spec_dir() / "SPEC.md").read_text(encoding="utf-8")
    for cid in ("C-PREREG-TIMING", "C-PREREG-IMMUTABLE", "C-TRUST-WRITE", "C-TEST-FROZEN", "C-PROMPT-ISOLATION"):
        assert cid in spec, f"SPEC.md does not mention {cid}"


def test_clean_example_passes_with_a_period_and_after_the_deadline(ws, monkeypatch):
    """C-PREREG-IMMUTABLE: with proofs in place and a verifying client, the example passes after the deadline too."""
    monkeypatch.setattr(archive, "ots_verify", lambda ots, target, proof: (True, "Success!"))
    monkeypatch.setattr(archive, "ots_executable", lambda: "/usr/bin/true")
    for rel in (PREREG, OWNER_PREREG):
        (ws / f"{rel}.ots").write_bytes(b"proof")
    selftest.apply(ws, (selftest.replace(SETTLEMENT, "acceptance_datetime: null", 'acceptance_datetime: "2026-10-28T16:05:00-04:00"'),))
    report = engine.run(ws / "public", ws / "private", AFTER_DEADLINE, period="FY2027Q1")
    assert [f for f in report.findings if f.check != "C-STALENESS"] == []
