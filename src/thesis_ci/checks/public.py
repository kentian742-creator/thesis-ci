"""Public-repository hygiene: no valuation, no advice, no position amounts."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable, Iterator

from ..engine import Context, Issue, check
from ..repo import YAML_SUFFIXES, Repo, walk_items
from ..textscan import FACT_RE, TAG_LIKE_RE, compile_wording, normalize_prose, sentences, snippet, wording_hits

# Archive content: everything under these directories (companies/ includes companies/*/updates/), plus the
# root-level files published as archive content: the public mistakes list (00 §G5: mistakes.md).
CONTENT_DIRS = ("companies", "industries", "forecasts", "letters")
CONTENT_ROOT_FILES = ("mistakes.md",)
TEXT_SUFFIXES = {".md", ".markdown", ".yml", ".yaml", ".txt", ".json", ".csv", ".tsv", ".html", ".htm", ""}
# JSON files that are tool configuration, not archive data (their keys are the tool's, e.g. "position").
CONFIG_JSON = ("package.json", "package-lock.json", "composer.json", "tsconfig*.json", "jsconfig*.json")
CONFIG_DIRS = (".github", ".vscode", ".claude", ".devcontainer", ".idea", ".husky")

# spec/checks.yml, C-PUBLIC-NO-VALUATION: the valuation terms of 00 §H4, exactly.
VALUATION_PHRASES = (
    "买入区间", "价值中枢", "目标价", "隐含回报", "隐含年化回报", "价格评级",
    "price target", "target price", "buy range", "fair value range",
)
# The same wording in other forms: the value ranges by their DESIGN names (合理区间, 便宜区间) with a number, or a
# price event on them; intrinsic value or margin of safety with a number.
_CUR = r"(?:[$＄€£¥￥]\s*)?"
VALUATION_PATTERNS = (
    ("value range with a number", r"(?:合理|便宜|价值|估值|内在价值)区间\s*(?:[:：]|为|是|在|约|大约|大致)?\s*" + _CUR + r"\d"),
    ("price event on a value range",
     r"(?:进入|跌入|落入|回到|离开|跌破|突破|高于|低于|接近|触及)了?\s*(?:合理|便宜|价值|买入)区间"),
    ("valuation centre", r"估值中枢"),
    ("intrinsic value with a number", r"内在价值\s*(?:[:：]|为|是|约|大约|在)?\s*" + _CUR + r"\d"),
    ("margin of safety with a number", r"安全边际\s*(?:[:：]|为|是|约|有|达|达到|仅)?\s*\d"),
    ("intrinsic value with a number", r"(?<![A-Za-z])intrinsic\s+value\s+(?:of|at|is|was|around|near|about|:|~)?\s*" + _CUR + r"\d"),
    ("margin of safety with a number", r"(?<![A-Za-z])margin\s+of\s+safety\s+(?:of|is|was|at|:|~)?\s*\d"),
)
VALUATION_WORDING = compile_wording(VALUATION_PHRASES, VALUATION_PATTERNS)
VALUATION_KEYS = frozenset({"value_ranges", "price_reference", "implied_return", "price_rating"})
# Other spellings of the same data as keys (keys are compared after normalization: valueRanges -> value_ranges).
VALUATION_KEY_ALIASES = frozenset({
    "value_range", "implied_returns", "price_references", "price_ratings", "price_target", "target_price",
    "buy_range", "fair_value_range", "intrinsic_value", "intrinsic_value_range",
})
# 00 §H4: L3 memos, escalation requests and the decision log with amounts live in the private repository only.
PRIVATE_ONLY_DIRS = ("memos", "escalations", "decision-log")

# 00 §H4: public files do not state multiples or ratios that take the current share price as an input. Flagged when
# the sentence also has a number (a fact number, a decimal, or a number of two or more digits that is not a year).
MULTIPLE_TERMS = ("市盈率", "P/E", "市值", "自由现金流收益率", "FCF yield", "市净率", "P/B")
MULTIPLE_SPELLINGS = ("free cash flow yield", "market cap", "market capitalization")  # the same terms in English
# The market price against book value in words ("价格低于 1.2 倍账面", "price-to-book of 1.3"). A company's own average
# repurchase price against book is a disclosed fact (00 §H2 item 3), so 回购均价 / 回购价格 and identifiers such as
# buyback_avg_price_to_book are not matched.
MULTIPLE_PATTERNS = (
    ("price-to-book", r"(?<![A-Za-z0-9_])price[\s\-]+to[\s\-]+book(?![A-Za-z0-9_])"),
    ("price against book value", r"(?<!回购)(?:股价|价格|市价)[^。；;\n]{0,10}?倍(?:的)?(?:每股)?(?:账面|净资产)"),
)
MULTIPLE_WORDING = compile_wording(MULTIPLE_TERMS + MULTIPLE_SPELLINGS, MULTIPLE_PATTERNS)
_NOT_A_QUANTITY_RE = re.compile(
    r"\d{4}-\d{2}(?:-\d{2})?"                                  # dates
    r"|FY\d{2,4}(?:Q[1-4])?|\d{4}\s*Q[1-4]|(?<![A-Za-z])[QH][1-4](?![0-9])"  # fiscal periods and quarters
    r"|(?<![\d,.])(?:19|20)\d{2}(?![\d,.])",                     # years
    re.I,
)
_PLAIN_NUMBER_RE = re.compile(r"(?<![\w.\-/#§])(?:\d+\.\d+|\d{2,}(?:,\d{3})*)(?![\w\-/])")

# spec/checks.yml, C-PUBLIC-NO-ADVICE: the advice terms of 00 §H4, exactly. Other wordings of the same advice are
# caught by ADVICE_PATTERNS. "overweight" / "underweight" count only as a rating or stance, so a beverage industry
# module can still write about overweight adults.
ADVICE_PHRASES = (
    "建议买入", "建议卖出", "建议增持", "建议减持", "建议加仓", "建议减仓", "买入评级", "卖出评级", "强烈推荐",
    "值得买入", "应该买入", "可以买入", "逢低买入", "建议建仓", "建议清仓", "strong buy", "overweight", "underweight",
)
_ACT = r"(?:买入|卖出|增持|减持|加仓|减仓|建仓|清仓|抛售|抄底|止损|止盈)"
_HOLD_ACT = r"(?:买入|增持|减持|加仓|减仓|建仓|清仓|抄底|止损|止盈)"
_WHEN = r"(?:立即|马上|现在|立刻|逢低|逢高|适当|适度|继续|尽快|全部|部分|分批|及时)?"
_OW = r"(?:overweight|underweight)"
ADVICE_PATTERNS = (
    ("buy/sell advice", r"(?:建议|推荐)\s*" + _WHEN + r"\s*" + _ACT),
    ("buy/sell advice", r"(?:应该|应当|可以|值得|不妨|最好|考虑)\s*" + _WHEN + r"\s*" + _HOLD_ACT),
    ("buy/sell advice", r"(?:应该|应当|最好|不妨)\s*" + _WHEN + r"\s*(?:卖出|抛售)"),
    ("buy/sell advice", r"逢高(?:卖出|减持|减仓)"),
    ("rating wording", r"(?:增持|减持|跑赢大市|跑输大市|持有|中性)评级"),
    ("rating wording", r"评级\s*(?:[:：]|为|是|调至|上调至|下调至)?\s*(?:买入|卖出|增持|减持|强烈推荐|推荐|跑赢大市|跑输大市)"),
    ("buy/sell advice", r"(?<![A-Za-z])(?:i|we)\s+(?:would\s+|strongly\s+|still\s+)*(?:recommend|suggest|advise|advocate)\s+"
                        r"(?:buying|selling|adding|trimming|accumulating|shorting|reducing|a\s+(?:buy|sell)|(?:investors\s+)?to\s+(?:buy|sell))(?![A-Za-z])"),
    ("buy/sell advice", r"(?<![A-Za-z])strong[\s_\-]+sell(?![A-Za-z])"),
    ("buy/sell advice", r"(?<![A-Za-z])(?:buy|sell|hold)[\s_\-]+recommendations?(?![A-Za-z])"),
    ("buy/sell advice", r"(?<![A-Za-z])(?:buy|sell|hold)[\s_\-]+ratings?(?![A-Za-z])"),
    ("overweight/underweight rating", r"(?<![A-Za-z])(?:rat(?:e|es|ed|ing)|upgrad(?:e|es|ed|ing)|downgrad(?:e|es|ed|ing)|initiat(?:e|es|ed|ing))"
                                      r"\s+(?:\S+\s+){0,3}?(?:to\s+|at\s+|as\s+|an?\s+)?" + _OW + r"(?![A-Za-z])"),
    ("overweight/underweight rating", r"(?<![A-Za-z])" + _OW + r"\s+(?:rating|recommendation|stance|call|position)s?(?![A-Za-z])"),
    ("overweight/underweight rating", r"(?<![A-Za-z])(?:go|going|went|stay|staying|remain|remaining|turn|turning|move|moving|we're|we\s+are)"
                                      r"\s+(?:to\s+)?" + _OW + r"(?![A-Za-z])"),
    # a labelled rating; a bare table cell or "(overweight)" is left alone (BMI 25–30 (overweight))
    ("overweight/underweight rating", r"(?<![A-Za-z])(?:rating|recommendation|stance|call|view|评级|建议)\s*[:：]\s*" + _OW + r"(?![A-Za-z])"),
)
ADVICE_WORDING = compile_wording([p for p in ADVICE_PHRASES if p not in ("overweight", "underweight")], ADVICE_PATTERNS)

AMOUNT_KEYS = frozenset(
    {"position", "position_size", "shares_held", "cost_basis", "amount_usd", "account", "weight", "target_weight"}
)
AMOUNT_KEY_ALIASES = frozenset({
    "account_id", "account_number", "account_no", "avg_cost", "average_cost", "portfolio_weight", "position_weight",
    "position_value",
})
# IBKR-style account ids (U1234567, paper accounts DU1234567); not a Python "\U0001F600"-style escape.
ACCOUNT_RE = re.compile(r"(?<![\\A-Za-z0-9_])D?U\d{7,}(?![A-Za-z0-9_])")
# The owner's position sizes in public prose (我们的仓位 15%, our stake in X is 12%). Only first-person wording
# counts: Berkshire's own holdings ("cost basis of $24.5 billion", 日本持仓) are facts about a company.
_AMOUNT = r"\s*(?:[:：]|为|是|约|在|达|达到|占|有|降至|升至|提高到|降到|加到)?\s*" + _CUR + r"\d"
POSITION_PATTERNS = (
    ("position size", r"(?:我们|我|本组合|组合中|组合里)的?\s*(?:目标\s*)?(?:仓位|持仓(?:比例|占比|权重|成本|市值|金额)?)" + _AMOUNT),
    ("position size", r"目标仓位" + _AMOUNT),
    ("position size", r"(?<![A-Za-z])(?:our\s+(?:position|stake|holding|weight|cost\s+basis)s?(?:\s+in\s+\S+)?|target\s+weight|position\s+size)"
                      r"\s*(?:is|of|at|was|:|~)?\s*" + _CUR + r"\d"),
)
POSITION_WORDING = compile_wording((), POSITION_PATTERNS)
# SPEC 5: a two-minute story states no position ratio at all.
STORY_POSITION_WORDING = compile_wording((), POSITION_PATTERNS + (
    ("position size", r"(?:仓位|持仓比例|持仓占比|持仓权重)" + _AMOUNT),
))


def content_files(repo: Repo, dirs: Iterable[str] = CONTENT_DIRS, root_files: Iterable[str] = CONTENT_ROOT_FILES) -> Iterator[Path]:
    """Text files under the archive content directories, plus the root-level content files."""
    dirs, root_files = tuple(dirs), tuple(root_files)
    for path in repo.all_files:
        rel = repo.rel(path)
        top = rel.split("/")[0]
        if (top in dirs and "/" in rel and path.suffix.lower() in TEXT_SUFFIXES) or rel in root_files:
            yield path


def data_files(repo: Repo, data_only: bool = False) -> Iterator[Path]:
    """YAML files and JSON data files; ``data_only`` leaves out GitHub workflow and action configuration."""
    for path in repo.all_files:
        rel = repo.rel(path)
        suffix = path.suffix.lower()
        if suffix == ".json":
            if any(Path(rel).match(p) for p in CONFIG_JSON) or any(part in CONFIG_DIRS for part in rel.split("/")[:-1]):
                continue
        elif suffix not in YAML_SUFFIXES:
            continue
        if data_only and rel.startswith(".github/"):
            continue
        yield path


def norm_key(key: Any) -> str:
    """valueRanges, Value-Ranges and value ranges all become value_ranges."""
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(key).strip())
    return re.sub(r"[\s\-]+", "_", s).lower()


def forbidden_keys(repo: Repo, keys: frozenset[str], what: str, data_only: bool = False) -> Iterator[Issue]:
    """Keys in every document of every YAML file and JSON data file (a second YAML document is published too)."""
    for path in data_files(repo, data_only):
        for doc in repo.data_docs(path):
            for where, key, _value in walk_items(doc.data):
                if norm_key(key) in keys:
                    yield Issue(path, f"key '{key}' {what}", doc.line(*where))


def forbidden_wording(repo: Repo, paths: Iterable[Path], wording: list, what: str) -> Iterator[Issue]:
    for path in paths:
        for line, label, matched in wording_hits(repo.text(path) or "", wording):
            shown = label if label.lower() == matched.lower() else f"{label}: {snippet(matched, 40)}"
            yield Issue(path, f"{what}: '{shown}'", line)


def has_quantity(sentence: str) -> bool:
    """A fact number (SPEC 3.4 units), a decimal, or a number of two or more digits that is not a year or a date."""
    s = TAG_LIKE_RE.sub(" ", sentence)
    return bool(FACT_RE.search(s) or _PLAIN_NUMBER_RE.search(_NOT_A_QUANTITY_RE.sub(" ", s)))


def price_multiple_issues(repo: Repo, paths: Iterable[Path]) -> Iterator[Issue]:
    """00 §H4: a price-derived multiple (市盈率, P/E, 市值, FCF yield, ...) and a number in the same sentence."""
    for path in paths:
        markdown = path.suffix.lower() in (".md", ".markdown")
        # Split first: NFKC turns the full-width ；！？ into ASCII punctuation, which no longer ends a sentence.
        for line, raw in sentences(repo.text(path) or "", markdown):
            sentence = normalize_prose(raw)
            for label, rx in MULTIPLE_WORDING:
                if rx.search(sentence) and has_quantity(sentence):
                    yield Issue(path, f"price-derived multiple in public content: '{label}' with a number in the same "
                                      f"sentence (00 §H4): {snippet(raw)}", line)
                    break


@check("C-PUBLIC-NO-VALUATION")
def c_public_no_valuation(ctx: Context) -> Iterator[Issue]:
    repo = ctx.repo
    reported: set[str] = set()
    for path in repo.all_files:
        parts = repo.rel(path).split("/")
        if path.name.lower() in ("valuation.yml", "valuation.yaml", "valuation.json"):
            yield Issue(path, "valuation.yml belongs in the private repository only")
        for i, part in enumerate(parts[:-1]):
            if part in PRIVATE_ONLY_DIRS:
                d = "/".join(parts[: i + 1]) + "/"
                if d not in reported:
                    reported.add(d)
                    yield Issue(d, f"{part}/ belongs in the private repository only")
    for name in PRIVATE_ONLY_DIRS:  # empty directories too
        if (repo.root / name).is_dir() and f"{name}/" not in reported:
            yield Issue(f"{name}/", f"{name}/ belongs in the private repository only")
    yield from forbidden_keys(repo, VALUATION_KEYS | VALUATION_KEY_ALIASES, "is private valuation data")
    yield from forbidden_wording(repo, content_files(repo), VALUATION_WORDING, "price-range wording in public content")
    yield from price_multiple_issues(repo, content_files(repo))


def advice_files(repo: Repo) -> list[Path]:
    readmes = [p for p in repo.all_files if p.name.lower().startswith("readme")]
    return sorted(set(content_files(repo)) | set(readmes))


@check("C-PUBLIC-NO-ADVICE")
def c_public_no_advice(ctx: Context) -> Iterator[Issue]:
    yield from forbidden_wording(ctx.repo, advice_files(ctx.repo), ADVICE_WORDING, "buy/sell advice wording")


@check("C-PUBLIC-NO-AMOUNTS")
def c_public_no_amounts(ctx: Context) -> Iterator[Issue]:
    repo = ctx.repo
    yield from forbidden_keys(repo, AMOUNT_KEYS | AMOUNT_KEY_ALIASES, "looks like a position amount (private data)")
    for path in repo.all_files:
        text = repo.text(path)
        for m in ACCOUNT_RE.finditer(text or ""):
            yield Issue(path, f"string '{m.group(0)}' looks like a brokerage account number", text.count("\n", 0, m.start()) + 1)
    for path in content_files(repo):
        story = path.name == "story.md" and repo.rel(path).startswith("companies/")
        yield from forbidden_wording(repo, [path], STORY_POSITION_WORDING if story else POSITION_WORDING,
                                     "position amount in public content")
