"""Regression tests for the bypasses and false positives found by the adversarial mutation run.

Each test's docstring names the check it covers. Every case here was reproduced against the linter before the
fix: violations that were not reported, or clean content that was.
"""

from __future__ import annotations

import datetime as dt
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from thesis_ci import engine, selftest
from thesis_ci.repo import Repo
from thesis_ci.textscan import FACT_RE, untagged_facts

THESIS = "public/companies/ACME/thesis.yml"
STORY = "public/companies/ACME/story.md"
RIGHTS = "public/constitution/decision-rights.yml"
RULES = "public/constitution/rules.yml"
AUDITOR = "public/agents/auditor.yml"
IND_README = "public/industries/widgets/README.md"
INDUSTRY = "public/industries/widgets/industry.yml"
PREREG = "public/companies/ACME/prereg/FY2027Q1.yml"
OWNER_PREREG = "public/companies/ACME/prereg/FY2027Q1-owner.yml"
SETTLEMENT = "public/companies/ACME/prereg/FY2027Q1.settlement.yml"
LETTER = "public/letters/2026-09.md"
UPDATE = "public/companies/ACME/updates/2026-10"
BUY_MEMO = "private/memos/2026-09-20-ACME-entry.yml"
TRIM_MEMO = "private/memos/2026-09-22-BETA-trim.yml"
FAKE_KEY = selftest.FAKE_KEY


def edit(ws: Path, rel: str, old: str, new: str) -> None:
    selftest.apply(ws, (selftest.replace(rel, old, new),))


def put(ws: Path, rel: str, text: str) -> None:
    selftest.apply(ws, (selftest.write(rel, text),))


def story_line(ws: Path, text: str) -> None:
    edit(ws, STORY, "最可能错在哪", text + "\n最可能错在哪")


# --------------------------------------------------------------------------- file walking
def test_c_no_secrets_hidden_directories_are_scanned(ws, lint):
    """C-NO-SECRETS: hidden directories other than .github (.claude, .vscode) are published and scanned."""
    put(ws, "public/.claude/settings.json", json.dumps({"env": {"ANTHROPIC_API_KEY": FAKE_KEY}}))
    assert [f.file for f in lint(ws, "C-NO-SECRETS")] == [".claude/settings.json"]


def test_c_no_secrets_vcs_and_virtualenv_directories_are_skipped(ws, lint):
    """C-NO-SECRETS: .git and virtual environments are never scanned (a checkout's .git/config holds a token)."""
    put(ws, "public/.git/config", f'[http]\n\textraheader = AUTHORIZATION: basic {FAKE_KEY}\n')
    put(ws, "public/.venv/lib/site.py", f'KEY = "{FAKE_KEY}"\n')
    assert lint(ws, "C-NO-SECRETS") == []


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_c_no_secrets_respects_gitignore_in_a_work_tree(ws, lint):
    """C-NO-SECRETS: inside a git work tree, ignored files (a local .env) are not published and not scanned."""
    pub = ws / "public"
    subprocess.run(["git", "init", "-q", str(pub)], check=True)
    put(ws, "public/.gitignore", ".env\n")
    put(ws, "public/.env", f"ANTHROPIC_API_KEY={FAKE_KEY}\n")
    assert lint(ws, "C-NO-SECRETS") == []
    put(ws, "public/notes/untracked.txt", f"{FAKE_KEY}\n")  # untracked but not ignored: will be committed
    assert [f.file for f in lint(ws, "C-NO-SECRETS")] == ["notes/untracked.txt"]


@pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")
def test_c_no_secrets_archive_ignored_by_enclosing_repo_scans_everything(tmp_path):
    """C-NO-SECRETS: when an enclosing repository ignores the archive itself, every file is scanned (fail closed)."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("ws/\n", encoding="utf-8")
    ws = selftest.materialize(tmp_path / "ws", (selftest.write("public/.env", f"KEY={FAKE_KEY}\n"),))
    report = engine.run(ws / "public", None, selftest.TODAY, only=["C-NO-SECRETS"])
    assert [f.file for f in report.findings] == [".env"]


def test_c_schema_byte_order_mark_is_ignored(ws, lint):
    """C-SCHEMA: a UTF-8 byte-order mark does not hide story.md's front matter."""
    path = ws / STORY
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())
    assert lint(ws, "C-SCHEMA") == [] and lint(ws, "C-STORY") == []


def test_c_story_crlf_line_endings(ws, lint):
    """C-STORY: Windows line endings do not hide story.md's front matter or its fenced code."""
    story_line(ws, "```\n毛利率 66%\n```")
    path = ws / STORY
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    assert lint(ws, "C-STORY") == [] and lint(ws, "C-SCHEMA") == [] and lint(ws, "C-SRC-TAG") == []


# --------------------------------------------------------------------------- C-SCHEMA
def test_c_schema_duplicate_keys(ws, lint):
    """C-SCHEMA: a repeated key (PyYAML silently keeps the last value) is an error; merge keys are fine."""
    edit(ws, THESIS, "  moat: 2026-09-20\n", "  moat: 2020-01-01\n  moat: 2026-09-20\n")
    found = lint(ws, "C-SCHEMA")
    assert len(found) == 1 and "duplicate key 'moat'" in found[0].message and found[0].line == 22
    put(ws, f"{UPDATE}.yml", "base: &b {a: 1}\nx:\n  <<: *b\n  c: 2\ny:\n  <<: *b\n")
    assert len(lint(ws, "C-SCHEMA")) == 1


def test_c_schema_directory_names_company_and_module(ws, lint):
    """C-SCHEMA: companies/<TICKER>/*.yml name that company; industries/<id>/industry.yml has that id."""
    edit(ws, "public/companies/ACME/ledger.yml", "company: ACME", "company: ACMF")
    edit(ws, INDUSTRY, "id: widgets", "id: gadgets")
    messages = sorted(f.message for f in lint(ws, "C-SCHEMA"))
    assert messages == ["company 'ACMF' does not match directory companies/ACME/",
                        "id 'gadgets' does not match directory industries/widgets/"]


def test_c_schema_duplicate_source_tags(ws, lint):
    """C-SCHEMA: a source tag defined twice in one sources.yml is ambiguous."""
    edit(ws, "public/companies/ACME/sources.yml", "  - tag: ACME-10K-FY2026\n",
         "  - tag: ACME-RPT-2026-09\n    kind: report\n    title: again\n  - tag: ACME-10K-FY2026\n")
    assert "defined twice" in lint(ws, "C-SCHEMA")[0].message


def test_c_schema_counterpart_with_the_same_visibility(ws, lint):
    """C-SCHEMA: a public archive relabelled private (skipping every public check) is caught by its counterpart."""
    edit(ws, "public/repo.yml", "visibility: public", "visibility: private")
    assert any("both declare visibility private" in f.message for f in lint(ws, "C-SCHEMA", "private"))


def test_c_schema_expect_visibility_lints_as_expected(ws):
    """C-SCHEMA: with --expect-visibility public, a relabelled public archive still gets every public check."""
    edit(ws, "public/repo.yml", "visibility: public", "visibility: private")
    put(ws, "public/companies/ACME/valuation.yml", "company: ACME\n")
    relabelled = engine.run(ws / "public", None, selftest.TODAY)
    assert "C-PUBLIC-NO-VALUATION" not in relabelled.checks_run  # the bypass
    report = engine.run(ws / "public", None, selftest.TODAY, expect_visibility="public")
    assert report.visibility == "public" and "C-PUBLIC-NO-VALUATION" in report.checks_run
    assert {f.check for f in report.errors} >= {"C-SCHEMA", "C-PUBLIC-NO-VALUATION"}
    assert any("expected to be public" in f.message for f in report.errors if f.check == "C-SCHEMA")


def test_c_schema_expect_visibility_cli(ws, capsys):
    """C-SCHEMA: lint --expect-visibility passes a correctly labelled archive and rejects a bad value."""
    from thesis_ci.cli import main

    assert main(["lint", str(ws / "private"), "--expect-visibility", "private", "--today", "2026-09-24"]) == 0
    assert main(["lint", str(ws / "private"), "--expect-visibility", "public", "--today", "2026-09-24"]) == 1
    capsys.readouterr()
    with pytest.raises(SystemExit):
        main(["lint", str(ws / "public"), "--expect-visibility", "secret"])


# --------------------------------------------------------------------------- facts (SPEC 3.4)
NEW_FACTS = [
    "16 percent", "16 per cent", "30 basis points", "2 percentage points", "40 cents", "1.2 trillion", "3 thousand",
    "25x", "1.04X", "5 港元", "5 欧元", "5 日元", "5 英镑", "5 人民币", "1.50 比索", "5 千美元", "5 千亿", "3 百亿",
    "€500", "£5m", "¥30", "￥30", "₹5", "＄66", "RMB 5", "USD1.1", "11.9tn", "5mn", "66  %", "1,570  亿美元", "5 pct",
]
NEW_NOT_FACTS = [
    "2019-06 百亿补贴上线", "2024 百亿补贴", "1 月 1 日元旦", "图片 1920x1080", "矩阵 4x4", "地址 0x1F", "Web3", "5G 网络",
    "Top 3", "第 3 名", "12 个维度", "10-K", "13F", "Item 7A", "401(k)", "16:05",
]


@pytest.mark.parametrize("text", NEW_FACTS)
def test_c_src_tag_other_spellings_of_listed_units_need_a_tag(text):
    """C-SRC-TAG: English spellings, other currencies and magnitudes of the SPEC 3.4 units are fact numbers."""
    assert FACT_RE.search(text), text
    assert untagged_facts(f"收入 {text}[src:ACME-RPT-2026-09#p3]。") == []


@pytest.mark.parametrize("text", NEW_NOT_FACTS)
def test_c_src_tag_names_dates_and_sizes_are_not_facts(text):
    """C-SRC-TAG: a date before a programme name (百亿补贴), resolutions and hex are not fact numbers."""
    assert FACT_RE.search(text) is None, text


def test_c_src_tag_invisible_characters_do_not_split_a_fact():
    """C-SRC-TAG: a zero-width space or soft hyphen between number and unit does not hide the fact."""
    assert untagged_facts("毛利率 66\u200b%。") and untagged_facts("毛利率 66\u00ad%。")


def test_c_src_tag_mistakes_md_is_archive_content(ws, lint):
    """C-SRC-TAG: the public mistakes list (mistakes.md) tags its fact numbers like any archive Markdown."""
    put(ws, "public/mistakes.md", "# 错误清单\n\n核销率写成 2.5%，实为 2.0%[src:OO-LOG-2026-09]。\n毛利率写成 60%。\n")
    found = lint(ws, "C-SRC-TAG")
    assert [(f.file, f.line) for f in found] == [("mistakes.md", 4)]


def test_c_src_fact_sources_in_any_company_yaml_resolve(ws, lint):
    """C-SRC-FACT: source fields in update records (and every document of a YAML stream) must resolve."""
    put(ws, f"{UPDATE}.yml", "facts: [{value: 1, source: ACME-RPT-2026-09#p1}]\n---\nmore: {source: NOPE-2026#p2}\n")
    found = lint(ws, "C-SRC-FACT")
    assert len(found) == 1 and "NOPE-2026#p2" in found[0].message


# --------------------------------------------------------------------------- C-PUBLIC-NO-VALUATION
def test_c_public_no_valuation_every_yaml_document_and_json(ws, lint):
    """C-PUBLIC-NO-VALUATION: keys are found in a second YAML document, in JSON data and in any spelling."""
    put(ws, f"{UPDATE}.yml", "---\nnote: x\n---\nvalue_ranges: {fair: [1, 2]}\n")
    put(ws, "public/forecasts/dash.json", '{"ACME": {"valueRanges": [1, 2]}}')
    put(ws, "public/forecasts/other.yml", "Price-Target: 350\n")
    found = lint(ws, "C-PUBLIC-NO-VALUATION")
    assert sorted({(f.file, f.line) for f in found}) == [
        ("companies/ACME/updates/2026-10.yml", 4), ("forecasts/dash.json", 1), ("forecasts/other.yml", 1)]


def test_c_public_no_valuation_hidden_directory(ws, lint):
    """C-PUBLIC-NO-VALUATION: valuation.yml in a hidden directory is still in the public repository."""
    put(ws, "public/.data/valuation.yml", "company: ACME\n")
    assert [f.file for f in lint(ws, "C-PUBLIC-NO-VALUATION")] == [".data/valuation.yml"]


@pytest.mark.parametrize("text, flagged", [
    ("合理区间 280–330 美元[src:ACME-RPT-2026-09#p5]", True),
    ("本月 ACME 进入便宜区间", True),
    ("估值中枢上移", True),
    ("安全边际 25%[src:ACME-RPT-2026-09#p5]", True),
    ("目標價 350 美元[src:ACME-RPT-2026-09#p5]", True),  # traditional characters
    ("价值区间只放在私有仓库", False),
    ("合理价格买优秀企业", False),
])
def test_c_public_no_valuation_range_wording(ws, lint, text, flagged):
    """C-PUBLIC-NO-VALUATION: the value ranges by their DESIGN names, with a number or a price event."""
    story_line(ws, text + "。")
    assert bool(lint(ws, "C-PUBLIC-NO-VALUATION")) is flagged


# --------------------------------------------------------------------------- C-PUBLIC-NO-ADVICE
@pytest.mark.parametrize("text, flagged", [
    ("结论：建议减仓", True),
    ("建议加仓", True),
    ("推荐买入", True),
    ("现在应该卖出", True),
    ("建議買入", True),  # traditional
    ("建议 买入", True),  # spaced
    ("建\u200b议买入", True),  # zero-width space
    ("评级上调至买入", True),
    ("商家可以卖出更多商品", False),
    ("管理层建议增加分红，董事会建议回购", False),
])
def test_c_public_no_advice_chinese_wording(ws, lint, text, flagged):
    """C-PUBLIC-NO-ADVICE: advice in other words and spellings; business sentences stay clean."""
    story_line(ws, text + "。")
    assert bool(lint(ws, "C-PUBLIC-NO-ADVICE")) is flagged


@pytest.mark.parametrize("text, flagged", [
    ("I recommend buying ACME.", True),
    ("We would strongly suggest selling.", True),
    ("ｓｔｒｏｎｇ ｂｕｙ", True),  # full-width
    ("Rated strong-buy.", True),
    ("We rate ACME Overweight.", True),
    ("Rating: Underweight", True),
    ("Strong sell.", True),
    ("We never recommend buying or selling.", False),
    ("Strong buyer power keeps bottler margins thin.", False),
    ("Sugar taxes target overweight and obese adults.", False),
    ("| Overweight | 39% |", False),
    ("BMI 25-30 (overweight).", False),
])
def test_c_public_no_advice_english_wording(ws, lint, text, flagged):
    """C-PUBLIC-NO-ADVICE: overweight / underweight count only as a rating; health wording stays clean."""
    put(ws, "public/README.md", text + "\n")
    assert bool(lint(ws, "C-PUBLIC-NO-ADVICE")) is flagged


# --------------------------------------------------------------------------- C-PUBLIC-NO-AMOUNTS
def test_c_public_no_amounts_json_multidoc_and_paper_accounts(ws, lint):
    """C-PUBLIC-NO-AMOUNTS: keys in JSON data and later YAML documents; IBKR paper accounts (DU...)."""
    put(ws, "public/forecasts/pos.json", '{"positionSize": 0.15}')
    put(ws, f"{UPDATE}.yml", "---\nnote: x\n---\ncost_basis: 180\n")
    edit(ws, LETTER, "低于预算", "低于预算，模拟账户 DU1234567")
    assert sorted(f.file for f in lint(ws, "C-PUBLIC-NO-AMOUNTS")) == [
        "companies/ACME/updates/2026-10.yml", "forecasts/pos.json", "letters/2026-09.md"]


def test_c_public_no_amounts_tool_config_and_unicode_escapes(ws, lint):
    """C-PUBLIC-NO-AMOUNTS: tool configuration JSON keys and Python "\\U00020000" escapes are not amounts."""
    put(ws, "public/package.json", '{"name": "x", "weight": 400}')
    put(ws, "public/.vscode/settings.json", '{"position": "bottom"}')
    put(ws, "public/pipeline/glyphs.py", 'CJK = "\\U00020000"\n')
    assert lint(ws, "C-PUBLIC-NO-AMOUNTS") == []


@pytest.mark.parametrize("path, text, flagged", [
    (LETTER, "我们的仓位 15%", True),
    (LETTER, "Our stake in ACME is 12%", True),
    (STORY, "目前仓位 15%", True),  # SPEC 5: the story states no position ratio at all
    (LETTER, "伯克希尔对苹果的持仓成本约 310 亿美元[src:OO-LOG-2026-09]", False),
    (LETTER, "Berkshire's cost basis of $24.5 billion [src:OO-LOG-2026-09]", False),
    (LETTER, "入选门槛是仓位的下限", False),
])
def test_c_public_no_amounts_position_wording(ws, lint, path, text, flagged):
    """C-PUBLIC-NO-AMOUNTS: the owner's position sizes in prose; another company's holdings are facts."""
    edit(ws, path, "低于预算" if path == LETTER else "最可能错在哪",
         ("低于预算。" if path == LETTER else "") + text + ("" if path == LETTER else "。最可能错在哪"))
    assert bool(lint(ws, "C-PUBLIC-NO-AMOUNTS")) is flagged


# --------------------------------------------------------------------------- C-NO-PRICE-FEED
@pytest.mark.parametrize("rel, code, flagged", [
    ("public/pipeline/p.py", "from polygon import RESTClient\n", True),
    ("public/pipeline/p.py", "import akshare as ak\n", True),
    ("public/pipeline/p.py", "import pandas_datareader.data as web\n", True),
    ("private/pipeline/q.py", "URL = 'https://financialmodelingprep.com/api/v3/quote/ACME'\n", True),
    ("public/.github/workflows/q.yml", "on: push\njobs: {a: {runs-on: x, steps: [{run: pip install polygon-api-client}]}}\n", True),
    ("public/.scripts/fetch.py", "import yfinance\n", True),  # hidden directory
    ("public/pipeline/geo.py", "from shapely.geometry import Polygon\n", False),
])
def test_c_no_price_feed_other_quote_sources(ws, lint, rel, code, flagged):
    """C-NO-PRICE-FEED: quote clients by import (polygon, akshare, ...) and by name or URL; shapely is fine."""
    put(ws, rel, code)
    assert bool(lint(ws, "C-NO-PRICE-FEED", rel.split("/")[0])) is flagged


def test_c_no_price_feed_notebook(ws, lint):
    """C-NO-PRICE-FEED: a notebook that installs a quote client is code."""
    nb = {"cells": [{"cell_type": "code", "source": ["!pip install yfinance\n"]}], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
    put(ws, "public/notebooks/p.ipynb", json.dumps(nb))
    assert lint(ws, "C-NO-PRICE-FEED")


@pytest.mark.parametrize("text, flagged", [
    ("现价 $350[src:ACME-RPT-2026-09#p5]", True),
    ("收盘价 350 美元[src:ACME-RPT-2026-09#p5]", True),
    ("Shares closed at $350 [src:ACME-RPT-2026-09#p5]", True),
    ("股价从 2021 年高点下跌 70%[src:ACME-RPT-2026-09#p5]", False),
    ("市值 2 万亿美元[src:ACME-RPT-2026-09#p5]", False),
])
def test_c_no_price_feed_share_price_in_public_prose(ws, lint, text, flagged):
    """C-NO-PRICE-FEED: public content does not display a share price (hard rule 2); price changes are facts."""
    story_line(ws, text + "。")
    assert bool(lint(ws, "C-NO-PRICE-FEED")) is flagged


# --------------------------------------------------------------------------- C-NO-TRADING
@pytest.mark.parametrize("code, flagged", [
    ("from futu import OpenSecTradeContext\n", True),
    ("from tigeropen.trade.trade_client import TradeClient\n", True),
    ("from longport.openapi import TradeContext\n", True),
    ("import ccxt\nccxt.kraken().create_order('X', 'market', 'buy', 1)\n", True),
    ("import tda\n", True),
    ("from __future__ import annotations\nFUTURE = 1\n", False),
    ("def cancel_order_notification():\n    pass\n", False),
])
def test_c_no_trading_other_brokers(ws, lint, code, flagged):
    """C-NO-TRADING: Futu, Tiger, Longbridge, ccxt and generic order calls; "future" is not futu."""
    put(ws, "private/pipeline/broker.py", code)
    assert bool(lint(ws, "C-NO-TRADING", "private")) is flagged


def test_c_no_trading_javascript_order_call(ws, lint):
    """C-NO-TRADING: submitOrder / createOrder in JavaScript."""
    put(ws, "private/scripts/o.js", "client.submitOrder({symbol: 'ACME'});\n")
    assert lint(ws, "C-NO-TRADING", "private")


# --------------------------------------------------------------------------- C-LLM-ENTRY
@pytest.mark.parametrize("rel, code, flagged", [
    ("public/pipeline/d.py", "from claude_agent_sdk import query\n", True),
    ("public/pipeline/d.py", "import vertexai\n", True),
    ("public/pipeline/d.py", "import requests\nrequests.post('https://api.anthropic.com/v1/messages')\n", True),
    ("public/scripts/d.mjs", "import Anthropic from '@anthropic-ai/sdk';\n", True),
    ("public/scripts/d.ts", "const OpenAI = require('openai');\n", True),
    ("public/.github/workflows/ai.yml", "on: push\njobs: {a: {runs-on: x, steps: [{uses: anthropics/claude-code-action@v1}]}}\n", True),
    ("public/Makefile", "draft:\n\tcurl https://api.openai.com/v1/responses\n", True),
    ("public/.claude/hooks/h.py", "import anthropic\n", True),
    ("public/requirements.txt", "anthropic\npyyaml\n", False),
    ("public/pyproject.toml", "[project]\ndependencies = ['anthropic']\n", False),
    ("public/scripts/u.mjs", "import x from 'ai-utils';\n", False),
    ("public/pipeline/llm.py", "import anthropic\nURL = 'https://api.anthropic.com'\n", False),
])
def test_c_llm_entry_every_way_to_call_a_model(ws, lint, rel, code, flagged):
    """C-LLM-ENTRY: SDKs (claude_agent_sdk, vertexai, JS), raw HTTP, workflow actions; dependency lists are fine."""
    put(ws, rel, code)
    assert bool(lint(ws, "C-LLM-ENTRY")) is flagged


def test_c_llm_entry_notebook(ws, lint):
    """C-LLM-ENTRY: code cells of a notebook are Python (IPython magics are skipped)."""
    put(ws, "public/notebooks/d.ipynb", selftest.NOTEBOOK)
    found = lint(ws, "C-LLM-ENTRY")
    assert len(found) == 1 and found[0].line is None


# --------------------------------------------------------------------------- C-NO-SECRETS
@pytest.mark.parametrize("text, flagged", [
    ("client = make('sk-" + "3f9a1c0d7e4b" * 2 + "a1b2c3d4')\n", True),  # lowercase-hex sk- key
    ("token gh" + "s_" + "Aa1Bb2Cc3" * 4 + "\n", True),
    ("KEY = 'AI" + "za" + "SyD4x9Kq2LmN7pQ1rS3tU5vW7yZ0aB2cD4e'\n", True),
    ("-----BEGIN " + "OPENSSH PRIVATE KEY-----\n", True),
    ("const apiKey = 'Qx7Lm2Np9Rt4Vw6Yz8Ab';\n", True),
    ('db_password = "Tr0ub4dor-3xyz"\n', True),
    ("api_key = self.settings.anthropic_api_key\n", False),
    ('export ANTHROPIC_API_KEY="${ANTHROPIC_API_KEY}"\n', False),
    ('API_KEY_ENV = "ANTHROPIC_API_KEY"\n', False),
    ('api_key = "ANTHROPIC_API_KEY"\n', False),
    ('password_hint = "use the vault please"\n', False),
    ("see https://example.com/sk-telecom-5g-market-share-2025-report-final\n", False),
])
def test_c_no_secrets_more_formats_fewer_false_alarms(ws, lint, text, flagged):
    """C-NO-SECRETS: more key formats; references to keys (attributes, ${VAR}, env names) are not secrets."""
    put(ws, "public/pipeline/settings.py", text)
    assert bool(lint(ws, "C-NO-SECRETS")) is flagged


# --------------------------------------------------------------------------- C-DEPENDS
@pytest.mark.parametrize("text, flagged", [
    ("我们持有 ACME", True),
    ("ACME is in our portfolio", True),
    ("our stake in ACME", True),
    ("依赖于本行业的公司：ACME", True),
    ("companies that rely on this industry: ACME", True),
    ("Our holding company structure is set out in the 20-F", False),
    ("Demand depends on factory automation", False),
    ("AXP is a bank holding company", False),
])
def test_c_depends_neutrality_wording(ws, lint, text, flagged):
    """C-DEPENDS: first-person holdings and dependants in other words; legal entities stay allowed."""
    edit(ws, IND_README, "本模块只描述行业本身", text)
    assert bool(lint(ws, "C-DEPENDS")) is flagged


# --------------------------------------------------------------------------- C-STORY
def test_c_story_status_and_category_match_thesis(ws, lint):
    """C-STORY: the story's front matter tells the same status and category as thesis.yml."""
    edit(ws, STORY, "status: holding", "status: candidate")
    edit(ws, STORY, "category: stalwart", "category: fast_grower")
    assert sorted(f.line for f in lint(ws, "C-STORY")) == [4, 5]


# --------------------------------------------------------------------------- constitution
def test_c_sell_reasons_never_wider_than_the_memo_enum(ws, lint):
    """C-SELL-REASONS: an edited public sell_reasons list cannot allow price_decline in a private memo."""
    edit(ws, RIGHTS, ", better_opportunity]", ", better_opportunity, price_decline]")
    edit(ws, TRIM_MEMO, "sell_reason: management_deterioration", "sell_reason: price_decline")
    assert lint(ws, "C-SELL-REASONS", "private")


def test_c_hurdle_memo_cannot_lower_the_bar(ws, lint):
    """C-HURDLE: a buy memo's hurdle cannot be below the first (Berkshire) hurdle in the company's valuation.yml."""
    edit(ws, BUY_MEMO, "hurdle: 0.09", "hurdle: 0.05")
    edit(ws, BUY_MEMO, "implied_return: 0.11", "implied_return: 0.07")
    messages = " | ".join(f.message for f in lint(ws, "C-HURDLE", "private"))
    assert "hurdle 0.05 is below the first hurdle 0.09" in messages and "0.07 does not beat hurdle 0.09" in messages


@pytest.mark.parametrize("old, new, levels", [
    ("order: {type: single}", "order: {type: single, note: 分两批建仓}", ["error"]),
    ("summary: Build the position in one order (fictitious).", "summary: Scale in over three months.", ["error"]),
    ("summary: Build the position in one order (fictitious).", "summary: 不分批，一次下单建仓。", []),
    ("order: {type: single}", "order: {type: single, note: 'one order, no tranches'}", []),
])
def test_c_single_order_tranches_in_words(ws, lint, old, new, levels):
    """C-SINGLE-ORDER: order.type single but the note or summary plans tranches; negated wording is fine."""
    edit(ws, BUY_MEMO, old, new)
    assert [f.level for f in lint(ws, "C-SINGLE-ORDER", "private")] == levels


def test_c_single_order_repeated_entry_memos(ws, lint):
    """C-SINGLE-ORDER: two live buy/add memos for one company within a month warn; a rejected one does not count."""
    memo = (ws / BUY_MEMO).read_text(encoding="utf-8")
    put(ws, "private/memos/2026-10-05-ACME-add.yml", memo.replace("action: buy", "action: add").replace("2026-09-20", "2026-10-05"))
    found = lint(ws, "C-SINGLE-ORDER", "private")
    assert [f.level for f in found] == ["warning"] and "staged entry" in found[0].message
    edit(ws, BUY_MEMO, "decision: pending", "decision: rejected")
    assert lint(ws, "C-SINGLE-ORDER", "private") == []


def test_c_decision_rights_l3_is_the_owner(ws, lint):
    """C-DECISION-RIGHTS: money matters are never delegated: levels.L3.who names the owner (董事长)."""
    edit(ws, RIGHTS, "who: owner", "who: hq_capital_allocator agent")
    assert "L3.who must be the owner" in lint(ws, "C-DECISION-RIGHTS")[0].message
    edit(ws, RIGHTS, "who: hq_capital_allocator agent", "who: 你（董事长）")
    assert lint(ws, "C-DECISION-RIGHTS") == []


def test_c_constitution_map_every_constitution_rule_is_mapped(ws, lint):
    """C-CONSTITUTION-MAP: dropping a constitution rule from rules.yml leaves its check unmapped (宪法第 N 条)."""
    text = (ws / RULES).read_text(encoding="utf-8")
    start, end = text.index("  - id: R7"), text.index("  - id: R8")
    (ws / RULES).write_text(text[:start] + text[end:], encoding="utf-8")
    found = lint(ws, "C-CONSTITUTION-MAP")
    assert len(found) == 1 and "constitution rule 7 is not mapped" in found[0].message and "C-HURDLE" in found[0].message


@pytest.mark.parametrize("old, new, flagged", [
    ("can_see: [draft_facts, source_excerpts]", "can_see: [draft_facts, source_excerpts, conclusions]", True),
    ("can_see: [draft_facts, source_excerpts]", "can_see: [draft_facts, manager_conclusions]", True),
    ("can_see: [draft_facts, source_excerpts]", "can_see: [draft_facts, reasoning]", True),
    ("can_see: [draft_facts, source_excerpts]", "can_see: [draft_facts, source_excerpts, conclusion_log]", False),
])
def test_c_agent_isolation_can_see(ws, lint, old, new, flagged):
    """C-AGENT-ISOLATION: can_see may not list what cannot_see hides (the last token decides: draft_conclusions)."""
    edit(ws, AUDITOR, old, new)
    assert bool(lint(ws, "C-AGENT-ISOLATION")) is flagged


def test_c_agent_isolation_blind_reader_may_see_thesis_questions(ws, lint):
    """C-AGENT-ISOLATION: the blind reader sees the list of thesis questions, not the thesis."""
    edit(ws, "public/agents/blind_reader.yml", "thesis_questions]", "thesis_question_list, thesis]")
    found = lint(ws, "C-AGENT-ISOLATION")
    assert len(found) == 1 and "'thesis'" in found[0].message


# --------------------------------------------------------------------------- C-PREREG-TIMING
@pytest.mark.parametrize("deadline, ok", [
    ('"2026-10-27T23:59:59-04:00"', True),
    ('"2026-10-28T03:59:59Z"', True),  # UTC, but still the 27th on EDGAR's (US Eastern) clock
    ('"2026-10-27"', True),
    ('"2026-10-28T06:00:00-04:00"', False),  # release day, before a pre-market release
    ('"2026-10-29T23:59:59-04:00"', False),
])
def test_c_prereg_timing_deadline_before_release_day(ws, lint, deadline, ok):
    """C-PREREG-TIMING: the deadline ends before the release day, so a late deadline cannot excuse a late merge."""
    for path in (PREREG, OWNER_PREREG):
        edit(ws, path, 'deadline: "2026-10-27T23:59:59-04:00"', f"deadline: {deadline}")
    edit(ws, SETTLEMENT, 'merged_at: "2026-09-21T10:00:00-04:00"', "merged_at: null")  # not merged yet
    assert (lint(ws, "C-PREREG-TIMING") == []) is ok


def test_c_prereg_timing_unrecorded_merge_after_the_deadline(ws, lint):
    """C-PREREG-TIMING: once the deadline has passed, a missing merged_at is reported (warning)."""
    edit(ws, SETTLEMENT, 'merged_at: "2026-09-21T10:00:00-04:00"', "merged_at: null")
    assert lint(ws, "C-PREREG-TIMING") == []  # today is before the deadline
    found = lint(ws, "C-PREREG-TIMING", today=dt.date(2026, 10, 29))
    assert [f.level for f in found] == ["warning"] and found[0].file == "companies/ACME/prereg/FY2027Q1.yml"
    (ws / SETTLEMENT).unlink()  # no settlement file at all
    assert [f.level for f in lint(ws, "C-PREREG-TIMING", today=dt.date(2026, 10, 29))] == ["warning"]


@pytest.mark.parametrize("value", ["-1.5", "true", "7"])
def test_c_src_tag_malformed_sources_yml_does_not_crash(ws, lint, value):
    """C-SRC-TAG: a sources.yml whose `sources` is not a list is a schema error, not a crash of the tag checks."""
    put(ws, "public/companies/ACME/sources.yml", f"sources: {value}\n")
    assert any("not in the applicable sources.yml" in f.message for f in lint(ws, "C-SRC-TAG"))  # lint() asserts no crash
    assert lint(ws, "C-SRC-FACT") and lint(ws, "C-SCHEMA")


@pytest.mark.parametrize("value", ["[]", "{}", "[quantitative]"])
def test_c_tests_min_non_string_type_does_not_crash(ws, lint, value):
    """C-TESTS-MIN: a test whose type is a list or mapping counts as no type; the check does not crash."""
    edit(ws, THESIS, "    type: qualitative\n", f"    type: {value}\n")
    assert any("no qualitative test" in f.message for f in lint(ws, "C-TESTS-MIN"))


def test_repo_data_docs_reads_every_document(tmp_path):
    """C-PUBLIC-NO-VALUATION: Repo.data_docs returns every document of a stream with its own line numbers."""
    (tmp_path / "x.yml").write_text("a: 1\n---\nb: 2\n", encoding="utf-8")
    docs = Repo(tmp_path).data_docs(tmp_path / "x.yml")
    assert [d.data for d in docs] == [{"a": 1}, {"b": 2}] and docs[1].line("b") == 3
