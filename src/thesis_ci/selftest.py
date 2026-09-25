"""In-package selftest: every registered check must pass the clean fixture and flag a violating one.

The clean fixture is ``fixtures/workspace`` (a public and a private archive). Each ``Case`` copies it to a
temporary directory, applies a few text edits, and lints one side with only the check under test.
"""

from __future__ import annotations

import datetime as dt
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import contract, engine

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "workspace"
TODAY = dt.date(2026, 9, 24)  # fixed so the selftest never depends on the calendar

PUB, PRIV = "public", "private"
THESIS = "public/companies/ACME/thesis.yml"
STORY = "public/companies/ACME/story.md"
RIGHTS = "public/constitution/decision-rights.yml"
BUY_MEMO = "private/memos/2026-09-20-ACME-entry.yml"
TRIM_MEMO = "private/memos/2026-09-22-BETA-trim.yml"
ACME_VAL = "private/companies/ACME/valuation.yml"
INDUSTRY = "public/industries/widgets/industry.yml"
PREREG = "public/companies/ACME/prereg/FY2027Q1.yml"
OWNER_PREREG = "public/companies/ACME/prereg/FY2027Q1-owner.yml"
SETTLEMENT = "public/companies/ACME/prereg/FY2027Q1.settlement.yml"
RULES = "public/constitution/rules.yml"
UPDATE = "public/companies/ACME/updates/2026-10"
PATCH_UPDATE = "public/companies/ACME/updates/2026-09-22.md"
LEDGER = "public/companies/ACME/ledger.yml"
TRUST = "public/trust/levels.yml"
BETA_VAL = "private/companies/BETA/valuation.yml"
ESCALATION = "private/escalations/2026-09-21-BETA-management.yml"
RANKING = "private/hq/ranking.yml"
PROMPT_03 = "private/prompts/03-update.md"
PROMPT_14 = "private/prompts/14-blind-read.md"
# A pre-registration whose deadline (2026-07-28) is before TODAY and that has no timestamp proof.
PAST_PREREG = """company: ACME
event: {period: FY2026Q4, expected_release: 2026-07-29, form: 8-K, placeholder: false}
deadline: "2026-07-28T23:59:59-04:00"
author: system
items:
  - {id: ACME-FY2026Q4-1, statement: Year-on-year revenue growth this quarter is no lower than last quarter's,
     probability: 0.6, criterion: per the 10-K, data_source: 10-K, horizon: quarter, resolves_by: 2026-08-31,
     domain: other, added_by: system}
"""
STORY_END = "Where this is most likely wrong"  # the story's last sentence; cases insert text in front of it
LETTER = "public/letters/2026-09.md"
IND_README = "public/industries/widgets/README.md"
ZH_STORY = "public/zh-CN/companies/ACME/story.md"
SOURCES = "public/companies/ACME/sources.yml"
# Chinese text for the cases that need it, written as escapes so that this module holds no CJK characters.
CJK = "\u4e2d\u6587"                                  # "Chinese"
CN_ADVICE = "\u5efa\u8bae\u4e70\u5165\u3002"          # "Recommend buying." (a 00 §H4 term)
CN_UNTAGGED = "\u8425\u6536\u589e\u957f 16%\u3002"    # "Revenue grew 16%." with the Chinese full stop, no tag
FULLWIDTH_COMMA = "\uff0c"

# Key-shaped strings assembled at runtime so no secret-like literal is ever committed.
FAKE_KEY = "sk-" + "ant-" + "api03-" + "Q7w" * 12
FAKE_PEM = "-----BEGIN " + "RSA PRIVATE KEY-----\nMIIEow" + "IBAAKCAQEA" * 3 + "\n-----END RSA PRIVATE KEY-----\n"
NOTEBOOK = ('{"cells": [{"cell_type": "code", "source": ["%pip install anthropic\\n", "import anthropic\\n"]}], '
            '"metadata": {}, "nbformat": 4, "nbformat_minor": 5}')


def replace(path: str, old: str, new: str) -> tuple:
    return ("replace", path, old, new)


def write(path: str, text: str) -> tuple:
    return ("write", path, text)


def delete(path: str) -> tuple:
    return ("delete", path)


def git_commit(side: str) -> tuple:
    """Make ``side`` a git work tree and commit everything (the base for C-TEST-FROZEN)."""
    return ("git_commit", side)


def before_story_end(text: str) -> tuple:
    """Insert ``text`` in front of the story's last sentence."""
    return replace(STORY, STORY_END, text + " " + STORY_END)


@dataclass(frozen=True)
class Case:
    check: str
    target: str  # which side to lint: "public" or "private"
    ops: tuple
    why: str
    counterpart: bool = True
    options: tuple = ()  # extra engine.run keyword arguments, as (name, value) pairs
    requires: tuple = ()  # executables the case needs (skipped when missing)


CASES: tuple[Case, ...] = (
    Case("C-SCHEMA", PUB, (replace(THESIS, "trust_level: 1", "trust_level: 9"),), "trust_level outside 0-3"),
    Case("C-SCHEMA", PUB, (replace(STORY, "status: holding", "status: owned"),), "story front matter status not in enum"),
    Case("C-SCHEMA", PUB, (replace(THESIS, "as_of: 2026-09-22", "as_of: 2026-02-30"),), "impossible date"),
    Case("C-SCHEMA", PRIV, (replace(BUY_MEMO, "timeout_days: 14", "timeout_days: 30"),), "memo timeout_days must be 14"),
    Case("C-SCHEMA", PUB, (delete("public/repo.yml"),), "repo.yml missing"),
    Case("C-SRC-TAG", PUB, (before_story_end("Revenue grew 16%."),), "untagged fact sentence"),
    Case("C-SRC-TAG", PUB, (replace(STORY, "[src:ACME-RPT-2026-09#p5]", "[src:NOPE-2026#p5]"),), "unknown tag"),
    Case("C-SRC-TAG", PUB, (replace(LETTER, "$3 [src:OO-LOG-2026-09]", "$3"),), "untagged number in a letter"),
    Case("C-SRC-FACT", PUB, (replace(THESIS, "60% of revenue [src:ACME-RPT-2026-09#p4]", "60% of revenue"),), "untagged fact in summary"),
    Case("C-SRC-FACT", PUB, (replace(THESIS, "source: ACME-10K-FY2026#Item8\ntests:", "source: ACME-10K-FY2099#Item8\ntests:"),),
         "baseline_facts source not in sources.yml"),
    Case("C-SRC-FACT", PRIV, (replace(ACME_VAL, "source: ACME-RPT-2026-09#p41", "source: ACME-RPT-1999#p41"),), "valuation source unresolved"),
    Case("C-SRC-ACCESSION", PUB, (replace(SOURCES, "accession: 0000000001-26-000001", "accession: null"),),
         "filing without accession"),
    Case("C-PUBLIC-NO-VALUATION", PUB, (write("public/companies/ACME/valuation.yml", "company: ACME\n"),), "valuation.yml in public"),
    Case("C-PUBLIC-NO-VALUATION", PUB, (before_story_end("The target price is not set yet."),), "price-range wording"),
    Case("C-PUBLIC-NO-VALUATION", PUB, (replace(THESIS, "todo:", "price_rating: B\ntodo:"),), "valuation key in public YAML"),
    Case("C-PUBLIC-NO-VALUATION", PUB, (write("public/memos/2026-09-20-x.yml", "id: x\n"),), "memos/ in public"),
    Case("C-PUBLIC-NO-ADVICE", PUB, (before_story_end("We recommend buying the shares."),), "advice wording in story"),
    Case("C-PUBLIC-NO-ADVICE", PUB, (replace("public/README.md", "Not investment advice.", "Strong buy."),), "advice in README"),
    Case("C-PUBLIC-NO-AMOUNTS", PUB, (write("public/companies/ACME/updates/2026-10.yml", "shares_held: 100\n"),), "amount key"),
    Case("C-PUBLIC-NO-AMOUNTS", PUB, (replace(LETTER, "below budget", "below budget; account U12345678"),), "account number"),
    Case("C-NO-PRICE-FEED", PUB, (write("public/pipeline/prices.py", "import yfinance\n"),), "price feed import"),
    Case("C-NO-PRICE-FEED", PRIV, (write("private/pipeline/fetch.py", "URL = 'https://query1.finance.yahoo.com/v7/finance/quote'\n"),),
         "quote endpoint in private code"),
    Case("C-NO-PRICE-FEED", PUB, (replace("public/forecasts/2026.yml", "brier: null", "brier: null\n    last_price: 101"),),
         "price key in public data"),
    Case("C-NO-TRADING", PUB, (write("public/pipeline/order.py", "def go(client):\n    client.place_order('ACME', 10)\n"),), "order API"),
    Case("C-NO-TRADING", PRIV, (write("private/requirements.txt", "alpaca-py\n"),), "broker SDK dependency"),
    Case("C-LLM-ENTRY", PUB, (write("public/pipeline/draft.py", "from openai import OpenAI\n"),), "SDK outside pipeline/llm.py"),
    Case("C-LLM-ENTRY", PRIV, (write("private/tools/ask.py", "from google import genai\n"),), "google.genai import"),
    Case("C-NO-SECRETS", PUB, (write("public/pipeline/settings.py", f'ANTHROPIC_API_KEY = "{FAKE_KEY}"\n'),), "API key literal"),
    Case("C-NO-SECRETS", PRIV, (write("private/.env", "GITHUB_TOKEN=" + "gh" + "p_" + "A1b2C3d4" * 5 + "\n"),), "token in .env"),
    Case("C-TESTS-MIN", PUB, (replace(THESIS, "id: ACME-S2", "id: ACME-S1"),), "duplicate test id"),
    Case("C-TESTS-MIN", PUB, (replace(THESIS, "id: ACME-L1", "id: ZZZ-L1"),), "test id without ticker prefix"),
    Case("C-TESTS-MIN", PUB, (replace(THESIS, "type: qualitative", "type: staleness"),), "no qualitative test"),
    Case("C-TESTS-MIN", PUB, (write("public/companies/BETA/story.md", "---\ncompany: BETA\nas_of: 2026-09-20\nstatus: candidate\n---\nx\n"),),
         "company without thesis.yml"),
    Case("C-TESTS-COVERAGE", PUB, (replace(THESIS, "covers: [pricing_power, moat]", "covers: [moat]"),), "pricing_power not covered"),
    Case("C-TESTS-CAPALLOC", PUB, (replace(THESIS, "covers: [capital_allocation]", "covers: [growth]"),), "capital_allocation not covered"),
    Case("C-TESTS-CAPALLOC", PUB, (replace(THESIS, "covers: [management]", "covers: [culture]"),), "management not covered"),
    Case("C-TEST-METRIC", PUB, (replace(THESIS, "metric: gross_margin", "metric: not_a_metric"),), "unregistered metric"),
    Case("C-TEST-METRIC", PUB, (replace(THESIS, 'rule: {op: "<", threshold: 55,', 'rule: {op: "<", threshold: "55%",'),),
         "non-numeric threshold"),
    Case("C-TEST-METRIC", PUB, (replace(THESIS, "metric: gross_margin\n", "metric: net_write_off_rate\n"),),
         "data xbrl but metric is filing_text"),
    Case("C-TEST-QUAL-EVIDENCE", PUB, (replace(THESIS, "evidence: required", "evidence: optional"),), "evidence not required"),
    Case("C-TEST-QUAL-EVIDENCE", PUB, (replace(THESIS, "judge: independent_model", "judge: company_manager"),), "wrong judge"),
    Case("C-STALENESS", PUB, (replace(THESIS, "  moat: 2026-09-20", "  moat: 2025-01-15"),), "moat review too old"),
    Case("C-DEPENDS", PUB, (replace(THESIS, "depends_on: [industries/widgets]", "depends_on: [industries/gadgets]"),), "unknown industry"),
    Case("C-DEPENDS", PUB, (replace(IND_README, "This module describes only the industry itself", "ACME is one of our holdings"),),
         "holding in module"),
    Case("C-DEPENDS", PUB, (replace(INDUSTRY, "implication: Pricing power weakens", "implication: Pricing power weakens, so investors should sell"),),
         "advice in module"),
    Case("C-STORY", PUB, (delete(STORY),), "story.md missing"),
    Case("C-STORY", PUB, (replace(STORY, "company: ACME", "company: BETA"),), "company mismatch"),
    Case("C-STORY", PUB, (before_story_end("word " * 351),), "English story over 350 words"),
    Case("C-RATING-ORDER", PRIV, (replace(RANKING, ", reason: Management deterioration under review; below the hurdle (fictitious).}", "}"),),
         "ranking row without a reason"),
    Case("C-RATING-ORDER", PUB, (replace(THESIS, "  management: B+\n", ""),), "management rating missing"),
    Case("C-CONCENTRATION", PUB, (replace(RIGHTS, "entry_band: [0.10, 0.20]", "entry_band: [0.05, 0.20]"),), "entry band changed"),
    Case("C-CONCENTRATION", PRIV, (replace(BUY_MEMO, "target_weight: 0.15", "target_weight: 0.05"),), "target weight below the entry bar"),
    Case("C-CONCENTRATION", PUB, (replace(RIGHTS, "max_holdings: 5", "max_holdings: 0"),), "max_holdings out of range"),
    Case("C-DISCOUNT-RATE", PRIV, (replace(ACME_VAL, "total: 0.065", "total: 0.08"),), "total != risk_free + premium"),
    Case("C-DISCOUNT-RATE", PRIV, (replace(ACME_VAL, "  note: Recurring revenue and a decade of steady margins make ACME's cash "
                                                     "flows predictable (fictitious).\n", ""),), "premium rationale missing"),
    Case("C-SELL-REASONS", PUB, (replace(RIGHTS, "recession, panic, single_quarter_miss", "recession, single_quarter_miss"),),
         "panic missing from forbidden reasons"),
    Case("C-SELL-REASONS", PUB, (replace(RIGHTS, ", better_opportunity]", ", price_decline]"),), "sell_reasons != memo enum"),
    Case("C-SELL-REASONS", PRIV, (replace(TRIM_MEMO, "sell_reason: management_deterioration", "sell_reason: recession"),),
         "trim memo with a forbidden reason"),
    Case("C-HURDLE", PRIV, (replace(BUY_MEMO, "implied_return: 0.11", "implied_return: 0.05"),), "buy memo below hurdle"),
    Case("C-HURDLE", PRIV, (replace(ACME_VAL, "hurdles: {brk: 0.09, voo: 0.08, source: ACME-RPT-2026-09#p42}", "method: x"),),
         "valuation without hurdles"),
    Case("C-SINGLE-ORDER", PUB, (replace(RIGHTS, "single_order_entry: true", "single_order_entry: false"),), "single order off"),
    Case("C-SINGLE-ORDER", PRIV, (replace(BUY_MEMO, "order: {type: single}", "order: {type: staged}"),), "staged order"),
    Case("C-DEFAULT-HOLD", PUB, (replace(RIGHTS, "timeout_days: 14", "timeout_days: 30"),), "timeout not 14 days"),
    Case("C-DEFAULT-HOLD", PRIV, (replace(TRIM_MEMO, "default_option: maintain", "default_option: execute"),), "memo default not maintain"),
    Case("C-DECISION-RIGHTS", PUB, (replace(RIGHTS, "valuation_update, prompt_change]", "valuation_update, prompt_change, buy]"),), "buy in L2"),
    Case("C-DECISION-RIGHTS", PUB, (replace(RIGHTS, "  initial: 1", "  initial: 3"),), "trust starts at 3"),
    Case("C-DECISION-RIGHTS", PUB, (delete(RIGHTS),), "decision-rights.yml missing"),
    Case("C-CONSTITUTION-MAP", PUB, (replace("public/constitution/rules.yml", "checks: [C-HURDLE]", "checks: [C-NOT-A-CHECK]"),),
         "unregistered check id"),
    Case("C-CONSTITUTION-MAP", PUB, (delete("public/constitution/rules.yml"),), "rules.yml missing"),
    Case("C-AGENT-ISOLATION", PUB, (replace("public/agents/auditor.yml", "cannot_see: [reasoning, conclusions]", "cannot_see: [reasoning]"),),
         "auditor can see conclusions"),
    Case("C-AGENT-ISOLATION", PUB, (replace("public/agents/blind_reader.yml", "reports_to: null", "reports_to: company_manager"),),
         "blind reader reports to the manager"),
    Case("C-PREREG-TIMING", PUB, (replace(SETTLEMENT, 'merged_at: "2026-09-21T10:00:00-04:00"', 'merged_at: "2026-10-28T09:00:00-04:00"'),),
         "merged after the deadline"),
    Case("C-PREREG-TIMING", PUB, (replace(SETTLEMENT, "acceptance_datetime: null", 'acceptance_datetime: "2026-10-27T20:00:00-04:00"'),),
         "results public before the deadline"),
    # --- evasions found by the mutation run (each case once let a violation through)
    Case("C-SCHEMA", PUB, (replace(THESIS, "status: holding\n", "status: holding\nstatus: candidate\n"),), "duplicate YAML key"),
    Case("C-SCHEMA", PUB, (replace(THESIS, "company: ACME\n", "company: ACMF\n"),), "thesis company does not match its directory"),
    Case("C-SCHEMA", PRIV, (replace("private/repo.yml", "visibility: private", "visibility: public"),), "both archives public"),
    Case("C-SRC-TAG", PUB, (before_story_end("Revenue grew 16 percent."),), "untagged English unit"),
    Case("C-SRC-TAG", PUB, (write("public/mistakes.md", "# Mistakes\n\nThe net write-off rate was given as 2.5%; it is 2.0%.\n"),),
         "untagged mistakes.md"),
    Case("C-SRC-FACT", PUB, (write(f"{UPDATE}.yml", "facts: [{value: 1, source: NOPE-2026#p1}]\n"),), "unresolved source in an update"),
    Case("C-PUBLIC-NO-VALUATION", PUB, (write(f"{UPDATE}.yml", "---\nnote: x\n---\nvalue_ranges: {fair: [1, 2]}\n"),),
         "value_ranges in a second YAML document"),
    Case("C-PUBLIC-NO-VALUATION", PUB, (write("public/.data/valuation.yml", "company: ACME\n"),), "valuation.yml in a hidden directory"),
    Case("C-PUBLIC-NO-VALUATION", PUB, (write("public/forecasts/dash.json", '{"ACME": {"valueRanges": [1, 2]}}'),), "JSON valueRanges"),
    Case("C-PUBLIC-NO-ADVICE", PUB, (write(f"{UPDATE}.md", "Conclusion: trim the position.\n"),), "trimming advice in an update"),
    Case("C-PUBLIC-NO-AMOUNTS", PUB, (write("public/forecasts/pos.json", '{"position_size": 0.15}'),), "JSON position_size"),
    Case("C-PUBLIC-NO-AMOUNTS", PUB, (replace(LETTER, "below budget", "below budget; our position is 15%"),), "position in a letter"),
    Case("C-NO-PRICE-FEED", PUB, (write("public/pipeline/prices.py", "from polygon import RESTClient\n"),), "polygon client import"),
    Case("C-NO-PRICE-FEED", PUB, (before_story_end("The shares closed at $350 [src:ACME-RPT-2026-09#p5]."),),
         "share price displayed in the story"),
    Case("C-NO-TRADING", PRIV, (write("private/pipeline/broker.py", "from futu import OpenSecTradeContext\n"),), "futu broker import"),
    Case("C-LLM-ENTRY", PUB, (write("public/pipeline/draft.py", "import requests\nrequests.post('https://api.anthropic.com/v1/messages')\n"),),
         "model API over HTTP"),
    Case("C-LLM-ENTRY", PUB, (write("public/.claude/hooks/hook.py", "import anthropic\n"),), "SDK in a hidden directory"),
    Case("C-LLM-ENTRY", PUB, (write("public/notebooks/draft.ipynb", NOTEBOOK),), "SDK in a notebook"),
    Case("C-NO-SECRETS", PUB, (write("public/.claude/settings.json", '{"env": {"ANTHROPIC_API_KEY": "' + FAKE_KEY + '"}}'),),
         "key in .claude/settings.json"),
    Case("C-NO-SECRETS", PRIV, (write("private/deploy_key", FAKE_PEM),), "private key file"),
    Case("C-DEPENDS", PUB, (replace(IND_README, "This module describes only the industry itself", "We hold ACME"),), "'we hold' in module"),
    Case("C-STORY", PUB, (replace(STORY, "status: holding", "status: candidate"),), "story status differs from thesis"),
    Case("C-SELL-REASONS", PRIV, (replace(RIGHTS, ", better_opportunity]", ", better_opportunity, price_decline]"),
                                  replace(TRIM_MEMO, "sell_reason: management_deterioration", "sell_reason: price_decline")),
         "edited public sell_reasons let a price-decline trim through"),
    Case("C-HURDLE", PRIV, (replace(BUY_MEMO, "hurdle: 0.09", "hurdle: 0.05"),), "memo hurdle below the valuation hurdle"),
    Case("C-SINGLE-ORDER", PRIV, (replace(BUY_MEMO, "order: {type: single}", "order: {type: single, note: build it in two tranches}"),),
         "two tranches in the order note"),
    Case("C-DECISION-RIGHTS", PUB, (replace(RIGHTS, "who: owner", "who: hq agent"),), "L3 decided by an agent"),
    Case("C-CONSTITUTION-MAP", PUB, (replace(RULES, "  - id: R6\n    title: Sell only for permanent deterioration or a clearly better "
                                                    "opportunity\n    text: Never for price declines, recessions, panics or a single "
                                                    "missed quarter.\n    kind: constitution\n    checks: [C-SELL-REASONS]\n", ""),),
         "constitution rule 6 dropped from rules.yml"),
    Case("C-AGENT-ISOLATION", PUB, (replace("public/agents/auditor.yml", "can_see: [draft_facts, source_excerpts]",
                                            "can_see: [draft_facts, source_excerpts, conclusions]"),), "auditor can_see conclusions"),
    Case("C-PREREG-TIMING", PUB, (replace(PREREG, 'deadline: "2026-10-27T23:59:59-04:00"', 'deadline: "2026-10-28T09:00:00-04:00"'),),
         "deadline on the release day"),
    # --- specification 0.2
    Case("C-SCHEMA", PUB, (replace(PREREG, "probability: 0.6\n", "probability: 0.99\n"),), "prereg probability above 0.95"),
    Case("C-SCHEMA", PUB, (replace(PREREG, "horizon: mixed\n", "horizon: mixed\noverrides: [{id: ACME-FY2027Q1-1, probability: 0.5}]\n"),),
         "overrides in the system's file"),
    Case("C-SCHEMA", PUB, (replace(PREREG, "  placeholder: false\n", "  placeholder: false\n  acceptance_datetime: null\n"),),
         "settlement data in the immutable items file"),
    Case("C-SCHEMA", PUB, (write("public/companies/ACME/prereg/FY2027Q1.settlement.yml",
                                 "company: ACME\nperiod: FY2027Q1\nresults: [{id: ACME-FY2027Q1-1, outcome: pending}]\n"),),
         "settlement outcome not in the enum"),
    Case("C-SCHEMA", PUB, (replace(OWNER_PREREG, "author: owner", "author: system"),), "owner file claims the system as author"),
    Case("C-SCHEMA", PUB, (replace(LEDGER, "    probability: 0.7\n", ""),), "system prediction without probability"),
    Case("C-SCHEMA", PUB, (replace(LEDGER, "    status: pending\n    probability: 0.7", "    status: partially_kept\n    probability: 0.7"),),
         "system prediction settled on the four-tier scale"),
    Case("C-SCHEMA", PUB, (replace(THESIS, "    effective_from: FY2027Q1\n  - id: ACME-Q2", "  - id: ACME-Q2"),), "test without effective_from"),
    Case("C-SCHEMA", PUB, (replace(THESIS, "  thesis: 2026-09-20\n", "  failure_modes: 2026-09-20\n"),), "0.1 reviewed key"),
    Case("C-SCHEMA", PUB, (replace(THESIS, "    lookback: 4\n", ""),), "qualitative test without lookback"),
    Case("C-SCHEMA", PUB, (replace(THESIS, "origin: proposal:04B", "origin: proposal:05"),), "origin from a prompt that proposes no tests"),
    Case("C-SCHEMA", PUB, (replace(RIGHTS, "  rule: \"§V13\"\n", "  order: [business, management, valuation]\n"),),
         "mechanical ranking order in decision rights"),
    Case("C-SCHEMA", PRIV, (replace(ACME_VAL, "price_rating: B", "price_rating: B+"),), "price rating with a sign"),
    Case("C-SCHEMA", PRIV, (replace(ACME_VAL, "doc_status: effective\n", ""),), "valuation without doc_status"),
    Case("C-SCHEMA", PRIV, (replace(BUY_MEMO, "  - {key: maintain, description: Do nothing; the default after 14 days.}\n",
                                    "  - {key: wait, description: Wait.}\n"),), "memo without the maintain option"),
    Case("C-SCHEMA", PRIV, (replace(ESCALATION, "reason: management_deterioration", "reason: better_opportunity"),),
         "escalation for a cross-company reason"),
    Case("C-SRC-FACT", PUB, (replace(LEDGER, "    acknowledged_source: null\n", "    acknowledged_source: ACME-10Q-FY2099Q1#p1\n"),),
         "acknowledged_source unresolved"),
    Case("C-PUBLIC-NO-VALUATION", PUB, (before_story_end("P/E is 25x [src:ACME-RPT-2026-09#p5]."),),
         "price-derived multiple with a number"),
    Case("C-PUBLIC-NO-VALUATION", PUB, (write("public/mistakes.md", "# Mistakes\n\nThe previous version put the implied return in a "
                                                                   "public file.\n"),),
         "valuation wording in mistakes.md"),
    Case("C-PUBLIC-NO-VALUATION", PUB, (write("public/escalations/2026-09-21-ACME.yml", "id: x\n"),), "escalations/ in public"),
    Case("C-PUBLIC-NO-ADVICE", PUB, (replace(PATCH_UPDATE, "Does this change the thesis? No.", "Does this change the thesis? No; add to "
                                                                                                "the position."),),
         "adding advice in an update"),
    Case("C-TESTS-MIN", PUB, (replace(THESIS, "supersedes: ACME-Q4", "supersedes: ACME-Q9"),), "supersedes names no test"),
    Case("C-TESTS-MIN", PUB, (replace(THESIS, "    effective_from: FY2027Q1\n  - id: ACME-Q2", "    effective_from: FY2027Q1\n    retired_at: FY2027Q2\n  - id: ACME-Q2"),
                              replace(THESIS, "    effective_from: FY2027Q1\n    first_readable", "    effective_from: FY2027Q1\n    retired_at: FY2027Q2\n    first_readable"),
                              replace(THESIS, "    effective_from: FY2027Q1\n  - id: ACME-Q4", "    effective_from: FY2027Q1\n    retired_at: FY2027Q2\n  - id: ACME-Q4")),
         "retired tests leave fewer than five in force"),
    Case("C-TESTS-COVERAGE", PUB, (replace(THESIS, "    effective_from: FY2027Q1\n  - id: ACME-Q4", "    effective_from: FY2027Q1\n    retired_at: FY2027Q2\n  - id: ACME-Q4"),),
         "the only free_cash_flow test is retired"),
    Case("C-TEST-METRIC", PUB, (replace(THESIS, "metric: recurring_share_v2.recurring", "metric: recurring_share_v2.subscriptions"),),
         "rule names an undefined component"),
    Case("C-TEST-QUAL-EVIDENCE", PUB, (replace(THESIS, "    lookback: 4\n", "    lookback: 0\n"),), "lookback 0"),
    Case("C-STALENESS", PUB, (replace(THESIS, "  bear_case: 2026-09-22", "  bear_case: 2026-01-15"),), "bear case review too old"),
    Case("C-DISCOUNT-RATE", PRIV, (replace(BETA_VAL, "method_note: One discount rate from BETA's own cash-flow record (fictitious numbers).",
                                           'method_note: ""'),), "method_note empty"),
    Case("C-PREREG-TIMING", PUB, (replace(OWNER_PREREG, 'deadline: "2026-10-27T23:59:59-04:00"', 'deadline: "2026-10-26T23:59:59-04:00"'),),
         "owner file with its own deadline"),
    Case("C-PREREG-IMMUTABLE", PUB, (write("public/companies/ACME/prereg/FY2026Q4.yml", PAST_PREREG),),
         "deadline passed, no timestamp proof"),
    Case("C-PREREG-IMMUTABLE", PUB, (write("public/companies/ACME/prereg/FY2026Q4-owner.yml",
                                           PAST_PREREG.replace("author: system", "author: owner").replace("added_by: system", "added_by: owner")),),
         "owner file past its deadline, no timestamp proof"),
    Case("C-TRUST-WRITE", PUB, (replace(TRUST, "  ACME: 1", "  ACME: 2"),), "trust_level differs from the pipeline's record"),
    Case("C-TRUST-WRITE", PUB, (replace(PATCH_UPDATE, "reviewed_sections: [bear_case]", "reviewed_sections: [moat]"),),
         "reviewed date moved for a section the update does not list"),
    Case("C-TEST-FROZEN", PUB, (git_commit("public"),
                                replace(THESIS, 'rule: {op: "<", threshold: 55,', 'rule: {op: "<", threshold: 50,')),
         "threshold lowered after the period's results", options=(("base_ref", "HEAD"), ("period", "FY2027Q1")), requires=("git",)),
    Case("C-TEST-FROZEN", PUB, (git_commit("public"), replace(THESIS, "  - id: ACME-S2\n", "  - id: ACME-S3\n")),
         "test in force removed", options=(("base_ref", "HEAD"), ("period", "FY2027Q1")), requires=("git",)),
    Case("C-PROMPT-ISOLATION", PRIV, (replace(PROMPT_03, '"question_list?"]', '"question_list?", blind_answers]'),),
         "company manager's prompt takes the blind answers"),
    Case("C-PROMPT-ISOLATION", PRIV, (replace(PROMPT_14, "inputs: [filings, question_list_stripped]", "inputs: [filings, question_list_stripped, thesis]"),),
         "blind read takes the thesis"),
    # --- English content and the zh-CN/ convention (thesis-ci 0.3.0)
    Case("C-SRC-TAG", PUB, (replace(STORY, "60% of revenue [src:ACME-RPT-2026-09#p4]",
                                    "60% of revenue. It was 55% a year earlier [src:ACME-RPT-2026-09#p4]"),),
         "one tag for two English sentences"),
    Case("C-SRC-TAG", PUB, (replace(ZH_STORY, "[src:ACME-10K-FY2026#Item8]", "[src:ACME-10K-FY2026#Item8]\n" + CN_UNTAGGED),),
         "untagged fact in the Chinese version of the story"),
    Case("C-PUBLIC-NO-VALUATION", PUB, (before_story_end("The central value is $120."),), "central value with a number"),
    Case("C-PUBLIC-NO-ADVICE", PUB, (replace(LETTER, "below budget.", "below budget. We rate ACME a buy."),), "rated a buy in a letter"),
    Case("C-PUBLIC-NO-ADVICE", PUB, (replace(ZH_STORY, "[src:ACME-10K-FY2026#Item8]", "[src:ACME-10K-FY2026#Item8]\n" + CN_ADVICE),),
         "advice in the Chinese version of the story"),
    Case("C-PUBLIC-NO-VALUATION", PUB, (write("public/docs/STATUS.md", "# Status\n\n- [x] Grades recomputed with the §V11 "
                                                                     "scale (AXP B− → C, BRK B+ → B).\n"),),
         "price-grade change in the public progress file"),
    Case("C-PUBLIC-NO-ADVICE", PUB, (write("public/CLAUDE.md", "# Notes for agents\n\nRating: Buy\n"),), "a rating in CLAUDE.md"),
    Case("C-LANGUAGE", PUB, (before_story_end(f"The {CJK} name is ACME."),), "Chinese in the English story"),
    Case("C-LANGUAGE", PRIV, (replace(BUY_MEMO, "summary: Build the position in one order (fictitious).",
                                      f"summary: Build the position in one order ({CJK})."),), "Chinese in a private memo"),
    Case("C-LANGUAGE", PUB, (replace(SOURCES, "title: ACME company report (in Chinese, fictitious)", f"title: ACME {CJK}"),),
         "a Chinese title outside title_original"),
    Case("C-LANGUAGE", PUB, (write("public/docs/notes.md", f"Notes{FULLWIDTH_COMMA} more notes\n"),), "full-width punctuation"),
)


def _git_commit(repo: Path) -> None:
    git = shutil.which("git")
    if git is None:
        raise ValueError("git is not installed")
    quiet = {"capture_output": True, "check": True, "timeout": 120}
    subprocess.run([git, "init", "-q", str(repo)], **quiet)
    subprocess.run([git, "-C", str(repo), "add", "-A"], **quiet)
    subprocess.run([git, "-C", str(repo), "-c", "user.name=thesis-ci selftest", "-c", "user.email=selftest@example.invalid",
                    "-c", "commit.gpgsign=false", "commit", "-q", "--no-verify", "-m", "base"], **quiet)


def apply(root: Path, ops: tuple) -> None:
    for op in ops:
        path = root / op[1]
        if op[0] == "git_commit":
            _git_commit(path)
        elif op[0] == "write":
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(op[2], encoding="utf-8")
        elif op[0] == "delete":
            path.unlink()
        elif op[0] == "replace":
            text = path.read_text(encoding="utf-8")
            if op[2] not in text:
                raise ValueError(f"selftest fixture bug: {op[2]!r} not found in {op[1]}")
            path.write_text(text.replace(op[2], op[3], 1), encoding="utf-8")
        else:
            raise ValueError(op[0])


def materialize(dest: Path, ops: tuple = ()) -> Path:
    """Copy the clean workspace to ``dest`` and apply ``ops``."""
    shutil.copytree(FIXTURE, dest, dirs_exist_ok=True)
    apply(dest, ops)
    return dest


def lint_side(workspace: Path, check_id: str, target: str, counterpart: bool = True, **options) -> list[engine.Finding]:
    other = PRIV if target == PUB else PUB
    report = engine.run(workspace / target, workspace / other if counterpart else None, TODAY, only=[check_id], **options)
    return [f for f in report.findings if f.check == check_id]


def clean_sides(scope: str) -> list[str]:
    return {"public": [PUB], "private": [PRIV]}.get(scope, [PUB, PRIV])


@dataclass
class Result:
    check: str
    passed: bool
    problems: list[str] = field(default_factory=list)
    cases: int = 0
    skipped: list[str] = field(default_factory=list)  # cases that need an executable this machine lacks


def selftest_check(check_id: str) -> Result:
    engine.load_checks()
    result = Result(check_id, True)
    if check_id not in engine.REGISTRY:
        return Result(check_id, False, ["not implemented"])
    scope = contract.check_meta(check_id)["scope"]
    cases = [c for c in CASES if c.check == check_id]
    if not cases:
        result.problems.append("no violating fixture")
    runnable = []
    for case in cases:
        missing = [exe for exe in case.requires if shutil.which(exe) is None]
        if missing:
            result.skipped.append(f"'{case.why}' needs {', '.join(missing)}")
        else:
            runnable.append(case)
    cases = runnable
    result.cases = len(cases)
    with tempfile.TemporaryDirectory(prefix="thesis-ci-selftest-") as tmp:
        clean = materialize(Path(tmp) / "clean")
        for side in clean_sides(scope):
            for f in lint_side(clean, check_id, side):
                result.problems.append(f"clean {side} fixture flagged: {f.file}:{f.line}: {f.message}")
        for n, case in enumerate(cases):
            try:
                ws = materialize(Path(tmp) / f"case{n}", case.ops)
            except (ValueError, OSError) as exc:
                result.problems.append(f"case '{case.why}': {exc}")
                continue
            findings = lint_side(ws, check_id, case.target, case.counterpart, **dict(case.options))
            crashes = [f for f in findings if f.message.startswith(engine.INTERNAL_ERROR)]
            if crashes:  # a crash is never a detection
                result.problems.append(f"check crashed on '{case.why}': {crashes[0].message}")
            elif not findings:
                result.problems.append(f"violating fixture not flagged: {case.why}")
    result.passed = not result.problems
    return result


_CACHE: dict[str, bool] = {}
_ACTIVE: set[str] = set()


def selftest_passes(check_id: str) -> bool:
    """Cached selftest verdict (used by C-CONSTITUTION-MAP)."""
    if check_id not in _CACHE:
        if check_id in _ACTIVE:  # re-entered while this very check is being self-tested
            return True
        _ACTIVE.add(check_id)
        try:
            _CACHE[check_id] = selftest_check(check_id).passed
        finally:
            _ACTIVE.discard(check_id)
    return _CACHE[check_id]


def run_all() -> list[Result]:
    results = []
    for meta in contract.registered_checks():
        res = selftest_check(meta["id"])
        _CACHE[meta["id"]] = res.passed
        results.append(res)
    return results
