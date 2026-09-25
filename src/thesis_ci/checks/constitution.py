"""Constitution checks: decision rights, portfolio rules, valuation discipline, agent isolation."""

from __future__ import annotations

import datetime as dt
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterator

from .. import contract
from ..engine import REGISTRY, Context, Issue, check
from ..repo import Doc, dig, is_number
from .thesis_tests import theses

RIGHTS = "constitution/decision-rights.yml"
RULES = "constitution/rules.yml"
RANKING = "hq/ranking.yml"  # private: the series ranking (17C, §V13)
MONEY_ACTIONS = ("buy", "add", "trim", "sell")
L3_ONLY = MONEY_ACTIONS + ("amend_constitution",)
ENTRY_BAND = (0.10, 0.20)
# Constitution rule 6: never sell for these. Matched by keyword, English snake_case or Chinese.
FORBIDDEN_SELL_CONCEPTS = {
    "price decline": ("price_decline", "price_drop", "price_fall", "price_down", "drawdown", "下跌"),
    "recession": ("recession", "衰退"),
    "panic": ("panic", "恐慌"),
    "single-quarter miss": ("quarter_miss", "quarterly_miss", "single_quarter", "earnings_miss", "单季", "不及预期"),
}
# L3 is the owner's level (DESIGN: 董事长).
OWNER_RE = re.compile(r"owner|chairman|董事长|主人|你", re.I)
TICKER_RE = re.compile(r"^[A-Z][A-Z0-9.]{0,9}$")
# Constitution rule 8 (one order builds a position): wording of a staged entry in a buy/add memo.
TRANCHE_RE = re.compile(
    r"分\s*(?:[两二三四五六几多]|\d+)\s*(?:批|次|笔|步)|分批|分步(?:建仓|买入|加仓)|逐步(?:建仓|买入|加仓)|定投"
    r"|(?:第[一二三四1-4]|首)批|先买\s*(?:一半|部分|入?\s*\d+\s*%)"
    r"|(?<![A-Za-z])(?:tranches?|scal(?:e|ing)\s+in(?:to)?|dollar[\s-]+cost\s+averag\w*|dca|laddered|staged\s+(?:entry|buying|purchases?))(?![A-Za-z])"
    r"|(?<![A-Za-z])in\s+(?:two|three|four|\d+)\s+(?:steps|parts|lots|orders|tranches|batches)(?![A-Za-z])",
    re.I,
)
NEGATION_RE = re.compile(r"(?:不|无需|无须|无|非|避免|不要|不会|不必|没有|\bnot|\bno|\bnever|\bwithout|\bavoid)\s*$", re.I)
STAGED_ENTRY_DAYS = 31
# cannot_see words a role's can_see must not expose (compared with the last token of a can_see item).
WORD_FORMS = {"reasoning": {"reasoning"}, "conclusions": {"conclusion", "conclusions"},
              "thesis": {"thesis", "theses"}, "draft": {"draft", "drafts"}}


def own_rights(ctx: Context) -> tuple[Path, Doc] | None:
    """This repository's decision-rights.yml, when it exists and parses to a mapping."""
    path = ctx.repo.root / RIGHTS
    if not path.is_file():
        return None
    doc = ctx.repo.doc(path)
    return (path, doc) if isinstance(doc.data, dict) else None


def memos_by_action(ctx: Context, actions: tuple[str, ...]) -> Iterator[tuple[Path, Doc, dict]]:
    for path, doc in ctx.memos():
        data = doc.mapping
        if data.get("action") in actions:
            yield path, doc, data


def _filled(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _norm(item: Any) -> str:
    return re.sub(r"[\s\-]+", "_", str(item).strip().lower())


def _numbers(value: Any) -> list[float]:
    if is_number(value):
        return [float(value)]
    if isinstance(value, list):
        return [float(v) for v in value if is_number(v)]
    return []


def _date(value: Any) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, str):
        try:
            return dt.date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None


def ranking_rows(data: Any) -> tuple[str | None, list] | None:
    """(key, rows) of hq/ranking.yml: a `rows` (or `ranking`) list, or a top-level list; None when there is none."""
    if isinstance(data, list):
        return None, data
    if isinstance(data, dict):
        for key in ("rows", "ranking"):
            if isinstance(data.get(key), list):
                return key, data[key]
    return None


@check("C-RATING-ORDER")
def c_rating_order(ctx: Context) -> Iterator[Issue]:
    for path, doc, data in theses(ctx.repo):
        ratings = data.get("ratings") if isinstance(data.get("ratings"), dict) else {}
        for need in ("business", "management"):
            if not ratings.get(need):
                yield Issue(path, f"ratings.{need} is missing (quality first, management second)", doc.line("ratings"))
    path = ctx.repo.root / RANKING
    if not path.is_file():
        return
    doc = ctx.repo.doc(path)
    if doc.error:
        return  # reported by C-SCHEMA
    found = ranking_rows(doc.data)
    if found is None:
        yield Issue(path, "hq/ranking.yml has no list of rows (write them under `rows`)", doc.line())
        return
    key, rows = found
    for i, row in enumerate(rows):
        where = (key, i) if key else (i,)
        if not (isinstance(row, dict) and _filled(row.get("reason"))):
            company = row.get("company") if isinstance(row, dict) else None
            yield Issue(path, f"ranking row {i + 1}{f' ({company})' if company else ''} has no reason: every row states "
                              "one sentence on why it ranks there (§V13)", doc.line(*where))


@check("C-CONCENTRATION")
def c_concentration(ctx: Context) -> Iterator[Issue]:
    # Rule 4 says "about 4-5 companies" and "10-20% is an entry bar, not a target; higher conviction can mean a
    # larger position". So only a weight below the bar is an error; a count above max_holdings, or a weight above
    # the bar's top without a stated reason, is a warning.
    rights = own_rights(ctx)
    if rights:
        path, doc = rights
        max_holdings = dig(doc.data, "portfolio", "max_holdings")
        if not (isinstance(max_holdings, int) and not isinstance(max_holdings, bool) and max_holdings >= 1):
            yield Issue(path, f"portfolio.max_holdings must be a positive integer, found {max_holdings!r}", doc.line("portfolio", "max_holdings"))
        elif max_holdings > 5:
            yield Issue(path, f"portfolio.max_holdings is {max_holdings}; constitution rule 4 says about 4-5 core companies",
                        doc.line("portfolio", "max_holdings"), level="warning")
        band = dig(doc.data, "portfolio", "entry_band")
        if not (isinstance(band, list) and len(band) == 2 and all(is_number(x) for x in band)
                and all(abs(a - b) < 1e-9 for a, b in zip(band, ENTRY_BAND))):
            yield Issue(path, f"portfolio.entry_band must be [0.10, 0.20] (a bar, not a target), found {band!r}", doc.line("portfolio", "entry_band"))
    if not ctx.is_private:
        limit = ctx.setting("portfolio", "max_holdings")
        holdings = [(p, d) for p, d, data in theses(ctx.repo) if data.get("status") == "holding"]
        if is_number(limit) and len(holdings) > limit:
            yield Issue(holdings[-1][0], f"{len(holdings)} companies have status holding; max_holdings is {limit} "
                                         "(constitution rule 4: about 4-5 core companies)", holdings[-1][1].line("status"), level="warning")
        return
    band = ctx.setting("portfolio", "entry_band")
    low, high = band if isinstance(band, list) and len(band) == 2 and all(is_number(x) for x in band) else ENTRY_BAND
    for path, doc, memo in memos_by_action(ctx, ("buy", "add")):
        weight = memo.get("target_weight")
        if not is_number(weight) or weight < low - 1e-9:
            yield Issue(path, f"{memo.get('action')} memo target_weight {weight!r} is below the entry bar {low}: a company "
                              "not worth a meaningful position is not worth owning (constitution rule 4)", doc.line("target_weight"))
        elif weight > high + 1e-9 and not _filled(memo.get("weight_note")):
            yield Issue(path, f"{memo.get('action')} memo target_weight {weight} is above the entry bar's top {high}: allowed "
                              "for higher conviction (constitution rule 4), but weight_note must say why", doc.line("target_weight"),
                        level="warning")


@check("C-DISCOUNT-RATE")
def c_discount_rate(ctx: Context) -> Iterator[Issue]:
    # One company at a time: the premium comes from the company's own cash-flow record (§V1, §V10), so premiums
    # are never compared across companies.
    for path in ctx.repo.files("companies/*/valuation.yml"):
        doc = ctx.repo.doc(path)
        data = doc.mapping
        rate = data.get("discount_rate") if isinstance(data.get("discount_rate"), dict) else None
        if rate is None:
            yield Issue(path, "discount_rate is missing", doc.line())
        else:
            rf, premium, total = rate.get("risk_free"), rate.get("premium"), rate.get("total")
            if rf is None and premium is None and total is None:
                yield Issue(path, "discount_rate not filled in yet (risk_free, premium, total are null)", doc.line("discount_rate"), level="warning")
            elif not all(is_number(x) for x in (rf, premium, total)):
                yield Issue(path, "discount_rate needs numeric risk_free, premium and total", doc.line("discount_rate"))
            elif abs(total - (rf + premium)) > 0.0005:
                yield Issue(path, f"discount_rate.total {total} != risk_free {rf} + premium {premium}", doc.line("discount_rate", "total"))
            if any(is_number(x) for x in (rf, premium, total)) and not _filled(rate.get("note")):
                yield Issue(path, "discount_rate.note is empty: write the premium rationale (which readings of this "
                                  "company's own cash-flow record make it more or less predictable, §V1)",
                            doc.line("discount_rate", "note") or doc.line("discount_rate"))
            if is_number(rf) and not rate.get("risk_free_date"):
                yield Issue(path, "discount_rate.risk_free_date is missing (the date of the 10-year Treasury yield, §V1)",
                            doc.line("discount_rate", "risk_free"), level="warning")
        if not _filled(data.get("method_note")):
            yield Issue(path, "method_note is empty (explain the discount rate)", doc.line("method_note"))


@check("C-SELL-REASONS")
def c_sell_reasons(ctx: Context) -> Iterator[Issue]:
    rights = own_rights(ctx)
    enum = contract.sell_reason_enum()
    if rights:
        path, doc = rights
        reasons = dig(doc.data, "memo", "sell_reasons")
        if not isinstance(reasons, list) or sorted(map(str, reasons)) != sorted(enum):
            yield Issue(path, f"memo.sell_reasons must equal the memo schema's sell_reason enum {enum}", doc.line("memo", "sell_reasons") or doc.line("memo"))
        forbidden = dig(doc.data, "memo", "forbidden_sell_reasons")
        items = [_norm(x) for x in forbidden] if isinstance(forbidden, list) else []
        for concept, keywords in FORBIDDEN_SELL_CONCEPTS.items():
            if not any(k in item for item in items for k in keywords):
                yield Issue(path, f"memo.forbidden_sell_reasons must include {concept} (constitution rule 6)",
                            doc.line("memo", "forbidden_sell_reasons") or doc.line("memo"))
    if not ctx.is_private:
        return
    # The allowed reasons come from decision-rights.yml but never go beyond the memo schema's enum, so an
    # edited list (say, one that adds price_decline) cannot let a trim or sell memo through.
    allowed = ctx.setting("memo", "sell_reasons")
    allowed = [str(x) for x in allowed if str(x) in enum] if isinstance(allowed, list) else enum
    for path, doc, memo in memos_by_action(ctx, ("trim", "sell")):
        reason = memo.get("sell_reason")
        if reason not in allowed:
            yield Issue(path, f"{memo.get('action')} memo sell_reason {reason!r} is not an allowed reason {allowed}", doc.line("sell_reason") or doc.line("action"))


def _bars(hurdles: Any) -> tuple[float | None, float | None]:
    """(first bar, second reference) from a valuation.yml hurdles mapping (§V6 engineering default).

    Rule 7 says "Berkshire or VOO" and does not take the higher of the two: Berkshire's implied return at its
    current price is the first bar and the index's forward return the second reference. With no Berkshire
    number, VOO is the only bar.
    """
    if not isinstance(hurdles, dict):
        return None, None
    brk, voo = _numbers(hurdles.get("brk")), _numbers(hurdles.get("voo"))
    if brk:
        return brk[0], (voo[0] if voo else None)
    return (voo[0] if voo else None), None


def valuation_bars(ctx: Context, company: Any) -> tuple[float | None, float | None]:
    """_bars() for this repository's companies/<company>/valuation.yml ((None, None) if none)."""
    if not (isinstance(company, str) and TICKER_RE.match(company)):
        return None, None
    path = ctx.repo.root / "companies" / company / "valuation.yml"
    return _bars(ctx.repo.doc(path).mapping.get("hurdles")) if path.is_file() else (None, None)


@check("C-HURDLE")
def c_hurdle(ctx: Context) -> Iterator[Issue]:
    holdings = ctx.holdings()
    for path in ctx.repo.files("companies/*/valuation.yml"):
        doc = ctx.repo.doc(path)
        data = doc.mapping
        hurdles = data.get("hurdles")
        if not isinstance(hurdles, dict):
            yield Issue(path, "hurdles are missing (VOO / Berkshire, constitution rule 7)", doc.line())
            continue
        first, second = _bars(hurdles)
        if first is None:
            yield Issue(path, "hurdles not quantified yet (brk and voo are null)", doc.line("hurdles"), level="warning")
            continue
        company = str(data.get("company") or path.parent.name)
        implied = data.get("implied_return")
        if not (holdings and company in holdings and is_number(implied)):
            continue
        # A holding below the line is for HQ to weigh in the quarterly ranking (17C), not an error (§G3).
        if implied < first:
            yield Issue(path, f"holding {company}: implied_return {implied} is below the first hurdle {first} (§V6)",
                        doc.line("implied_return"), level="warning")
        elif second is not None and implied < second:
            yield Issue(path, f"holding {company}: implied_return {implied} clears the first hurdle {first} but is below "
                              f"the VOO reference {second} (§V6)", doc.line("implied_return"), level="warning")
    for path, doc, memo in memos_by_action(ctx, ("buy", "add")):
        implied, hurdle = memo.get("implied_return"), memo.get("hurdle")
        if not (is_number(implied) and is_number(hurdle)):
            yield Issue(path, f"{memo.get('action')} memo needs numeric implied_return and hurdle", doc.line("implied_return") or doc.line("action"))
            continue
        # The memo cannot pick its own, lower bar: the company's valuation.yml sets the hurdles.
        first, second = valuation_bars(ctx, memo.get("company"))
        if first is not None and hurdle < first - 1e-9:
            yield Issue(path, f"{memo.get('action')} memo hurdle {hurdle} is below the first hurdle {first} "
                              f"in companies/{memo.get('company')}/valuation.yml", doc.line("hurdle"))
        bar = max(hurdle, first) if first is not None else hurdle
        if not implied > bar:
            yield Issue(path, f"{memo.get('action')} memo implied_return {implied} does not beat hurdle {bar}", doc.line("implied_return"))
        elif second is not None and not implied > second:
            yield Issue(path, f"{memo.get('action')} memo implied_return {implied} clears the first hurdle {bar} but not "
                              f"the VOO reference {second}: say why in the memo (§V6)", doc.line("implied_return"), level="warning")


@check("C-SINGLE-ORDER")
def c_single_order(ctx: Context) -> Iterator[Issue]:
    rights = own_rights(ctx)
    if rights:
        path, doc = rights
        if dig(doc.data, "portfolio", "single_order_entry") is not True:
            yield Issue(path, "portfolio.single_order_entry must be true (constitution rule 8)", doc.line("portfolio"))
    if not ctx.is_private:
        return
    entries: dict[str, list[tuple[dt.date, Path]]] = {}
    for path, doc, memo in memos_by_action(ctx, ("buy", "add")):
        if dig(memo, "order", "type") != "single":
            yield Issue(path, f"{memo.get('action')} memo order.type must be single", doc.line("order") or doc.line("action"))
        # order.type single, but the note or summary plans tranches
        for where in (("order", "note"), ("summary",)):
            text = dig(memo, *where)
            for m in TRANCHE_RE.finditer(text if isinstance(text, str) else ""):
                if not NEGATION_RE.search(text[max(0, m.start() - 6): m.start()]):
                    yield Issue(path, f"{memo.get('action')} memo {'.'.join(where)} plans a staged entry ('{m.group(0)}'); "
                                      "one order builds the position (constitution rule 8)", doc.line(*where))
                    break
        created = _date(memo.get("created_at"))
        if created is not None and memo.get("decision") not in ("rejected", "defaulted"):
            entries.setdefault(str(memo.get("company")), []).append((created, path))
    for company, dated in sorted(entries.items()):  # several live entry memos for one company close together
        dated.sort()
        for (d1, p1), (d2, p2) in zip(dated, dated[1:]):
            if (d2 - d1).days <= STAGED_ENTRY_DAYS:
                yield Issue(p2, f"{company} has buy/add memos {d1} and {d2} within {STAGED_ENTRY_DAYS} days: "
                                f"a staged entry, not one order (constitution rule 8)", level="warning")
    per_month: Counter[str] = Counter()
    for _path, doc in ctx.memos():
        created = str(doc.mapping.get("created_at") or "")
        if re.match(r"\d{4}-\d{2}", created):
            per_month[created[:7]] += 1
    limit = ctx.setting("memo", "monthly_target_max")
    for month, count in sorted(per_month.items()):
        if is_number(limit) and count > limit:
            yield Issue("memos/", f"{count} L3 memos in {month}; the monthly target is at most {limit}", level="warning")


@check("C-DEFAULT-HOLD")
def c_default_hold(ctx: Context) -> Iterator[Issue]:
    rights = own_rights(ctx)
    if rights:
        path, doc = rights
        if dig(doc.data, "memo", "default_option") != "maintain":
            yield Issue(path, "memo.default_option must be maintain", doc.line("memo", "default_option") or doc.line("memo"))
        timeout = dig(doc.data, "memo", "timeout_days")
        if not (timeout == 14 and not isinstance(timeout, bool)):
            yield Issue(path, f"memo.timeout_days must be 14, found {timeout!r}", doc.line("memo", "timeout_days") or doc.line("memo"))
    for path, doc in ctx.memos():
        if doc.mapping.get("default_option") != "maintain":
            yield Issue(path, "memo default_option must be maintain", doc.line("default_option") or doc.line())


@check("C-DECISION-RIGHTS")
def c_decision_rights(ctx: Context) -> Iterator[Issue]:
    path = ctx.repo.root / RIGHTS
    if not path.is_file():
        yield Issue(RIGHTS, "constitution/decision-rights.yml is missing")
        return
    doc = ctx.repo.doc(path)
    data = doc.mapping
    actions = {}
    for level in ("L1", "L2", "L3"):
        acts = dig(data, "levels", level, "actions")
        actions[level] = [a for a in acts if isinstance(a, str)] if isinstance(acts, list) else []
    for level in ("L1", "L2"):
        bad = [a for a in actions[level] if a in L3_ONLY]
        if bad:
            yield Issue(path, f"{level} contains {bad}; money matters and constitution changes are L3 only", doc.line("levels", level))
    missing = [a for a in L3_ONLY if a not in actions["L3"]]
    if missing:
        yield Issue(path, f"L3 is missing {missing}", doc.line("levels", "L3"))
    who = dig(data, "levels", "L3", "who")
    if not (isinstance(who, str) and OWNER_RE.search(who)):
        yield Issue(path, f"levels.L3.who must be the owner (董事长): money matters and constitution changes are "
                          f"never delegated, found {who!r}", doc.line("levels", "L3", "who") or doc.line("levels", "L3"))
    seen = Counter(a for acts in actions.values() for a in set(acts))
    dupes = sorted(a for a, n in seen.items() if n > 1)
    if dupes:
        yield Issue(path, f"actions assigned to more than one level: {dupes}", doc.line("levels"))
    levels = dig(data, "trust", "levels")
    keys = sorted(str(k) for k in levels) if isinstance(levels, dict) else None
    if keys != ["0", "1", "2", "3"]:
        yield Issue(path, f"trust.levels must define exactly 0, 1, 2, 3; found {keys}", doc.line("trust", "levels") or doc.line("trust"))
    initial = dig(data, "trust", "initial")
    if not (initial == 1 and not isinstance(initial, bool)):
        yield Issue(path, f"trust.initial must be 1, found {initial!r}", doc.line("trust", "initial") or doc.line("trust"))


@check("C-CONSTITUTION-MAP")
def c_constitution_map(ctx: Context) -> Iterator[Issue]:
    from ..selftest import selftest_passes  # late import: the selftest runs checks itself

    path = ctx.repo.root / RULES
    if not path.is_file():
        yield Issue(RULES, "constitution/rules.yml is missing")
        return
    doc = ctx.repo.doc(path)
    rules = doc.mapping.get("rules")
    if not isinstance(rules, list) or not rules:
        yield Issue(path, "constitution/rules.yml has no rules", doc.line())
        return
    known = {m["id"] for m in contract.registered_checks()}
    referenced: set[str] = set()
    for i, rule in enumerate(rules):
        rule = rule if isinstance(rule, dict) else {}
        rid, checks = rule.get("id"), rule.get("checks")
        if not isinstance(checks, list) or not checks:
            yield Issue(path, f"rule {rid} references no check", doc.line("rules", i))
            continue
        for j, cid in enumerate(checks):
            line = doc.line("rules", i, "checks", j)
            referenced.add(str(cid))
            if not isinstance(cid, str) or cid not in known:
                yield Issue(path, f"rule {rid}: {cid} is not registered in spec/checks.yml", line)
            elif cid not in REGISTRY:
                yield Issue(path, f"rule {rid}: {cid} has no implementation", line)
            elif cid != "C-CONSTITUTION-MAP" and not selftest_passes(cid):
                yield Issue(path, f"rule {rid}: {cid} fails its selftest", line)
    # The other direction: every constitution rule the registry enforces ("宪法第 N 条") must be mapped, so
    # dropping a rule from rules.yml does not silently leave it without an executable check.
    for number, cids in sorted(constitution_checks().items()):
        if not referenced.intersection(cids):
            yield Issue(path, f"constitution rule {number} is not mapped: no rule in rules.yml references {', '.join(cids)}",
                        doc.line("rules"))


def constitution_checks() -> dict[int, list[str]]:
    """Constitution rule number -> the registered checks whose description cites it (宪法第 N 条)."""
    out: dict[int, list[str]] = {}
    for meta in contract.registered_checks():
        for number in re.findall(r"宪法第\s*(\d+)\s*条", str(meta.get("description", ""))):
            out.setdefault(int(number), []).append(meta["id"])
    return out


def _tokens(item: Any) -> list[str]:
    return [t for t in re.split(r"[^a-z]+", str(item).lower()) if t]


def _mentions(items: Any, word: str) -> bool:
    """True when a list item is ``word`` or contains it as a separate token (e.g. thesis_reasoning)."""
    return isinstance(items, list) and any(word in _tokens(item) for item in items)


def _exposes(item: Any, word: str) -> bool:
    """True when a can_see item is the hidden thing itself: conclusions, draft_conclusions, full_thesis.

    Only the last token counts, so thesis_question_list (a list of questions) does not expose the thesis.
    """
    tokens = _tokens(item)
    return bool(tokens) and tokens[-1] in WORD_FORMS.get(word, {word})


@check("C-AGENT-ISOLATION")
def c_agent_isolation(ctx: Context) -> Iterator[Issue]:
    repo = ctx.repo
    required = {"auditor": ("reasoning", "conclusions"), "blind_reader": ("thesis", "draft", "conclusions")}
    for path in repo.files("agents/*.yml"):
        doc = repo.doc(path)
        data = doc.mapping
        role = data.get("role")
        role = role if isinstance(role, str) and role in required else path.stem if path.stem in required else None
        if role is None:
            continue
        cannot_see = data.get("cannot_see") if isinstance(data.get("cannot_see"), list) else []
        can_see = data.get("can_see") if isinstance(data.get("can_see"), list) else []
        for word in required[role]:
            if not _mentions(cannot_see, word):
                yield Issue(path, f"{role} must not see {word} (add it to cannot_see)", doc.line("cannot_see") or doc.line())
        for i, item in enumerate(can_see):
            exposed = [w for w in required[role] if _exposes(item, w)]
            if exposed or item in cannot_see:
                what = exposed[0] if exposed else "an item it also lists in cannot_see"
                yield Issue(path, f"{role} can_see {item!r} exposes {what}; isolation needs it hidden", doc.line("can_see", i))
        reports_to = str(data.get("reports_to") or "")
        if "company_manager" in reports_to:
            yield Issue(path, f"{role} must not report to company_manager", doc.line("reports_to"))
