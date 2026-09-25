"""Public-repository hygiene: no valuation, no advice, no position amounts."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable, Iterator

from ..engine import Context, Issue, check
from ..repo import YAML_SUFFIXES, Repo, translated_rel, walk_items
from ..textscan import (
    FACT_RE, TAG_LIKE_RE, compile_wording, normalize_prose, phrase_pattern, sentences, snippet, wording_hits,
)

# Archive content: everything under these directories (companies/ includes companies/*/updates/), plus the
# root-level files published as archive content: the public mistakes list (00 §G5: mistakes.md). The Chinese version
# of a content file (zh-CN/<same path>) is published content too.
CONTENT_DIRS = ("companies", "industries", "forecasts", "letters")
CONTENT_ROOT_FILES = ("mistakes.md",)
# Public files that report on the archive's own work and so can leak private valuation (a progress file once listed
# price-grade changes): the valuation and advice wording checks read them too. The files that define the rules and
# must name the banned terms (docs/DESIGN.md, docs/decisions/, constitution/) are not scanned.
REPORT_FILES = ("docs/STATUS.md", "CLAUDE.md")
TEXT_SUFFIXES = {".md", ".markdown", ".yml", ".yaml", ".txt", ".json", ".csv", ".tsv", ".html", ".htm", ""}
# JSON files that are tool configuration, not archive data (their keys are the tool's, e.g. "position").
CONFIG_JSON = ("package.json", "package-lock.json", "composer.json", "tsconfig*.json", "jsconfig*.json")
CONFIG_DIRS = (".github", ".vscode", ".claude", ".devcontainer", ".idea", ".husky")

_CUR = r"(?:[$＄€£¥￥]\s*)?"
# English: the words that may stand between a valuation term and its number ("central value of about $120", "margin
# of safety is now 30%"), a number that is not a year ("intrinsic value at 2026 year-end" states no value), and a
# range of numbers or an amount of money ("fair range 110–130", "value range of $110").
_EN_LINK = (r"(?:\s+(?:of|at|is|was|were|are|be|now|to|from|near|around|about|roughly|approximately|approx\.?|"
            r"estimated|est\.?|currently|still|for\s+\S+|(?:stands?|sits?|set|starts?|begins?|ends?)\s+at|runs?\s+from)"
            r"(?![A-Za-z]))*\s*[:~≈=]?\s*")
_EN_NUM = _CUR + r"(?!(?:19|20)\d{2}(?!\d|[,.]\d|\s*%))\d"
_EN_RANGE_OR_MONEY = r"(?:" + _CUR + r"\d[\d,.]*\s*(?:[–—-]|to)\s*" + _CUR + r"\d|[$＄€£¥￥]\s*\d)"

# spec/checks.yml, C-PUBLIC-NO-VALUATION: the valuation terms of 00 §H4, exactly.
VALUATION_PHRASES = (
    "买入区间", "价值中枢", "目标价", "隐含回报", "隐含年化回报", "价格评级",
    "price target", "target price", "buy range", "fair value range",
)
# The same wording in other forms: the value ranges by their DESIGN names with a number, or a price event on them;
# the valuation centre; intrinsic value or margin of safety with a number. Then the English equivalents of the whole
# list (SPEC 7.5): implied (annualized) return, price grade and price rating anywhere; central value, the ranges,
# intrinsic value and margin of safety with a number.
VALUATION_PATTERNS = (
    ("value range with a number", r"(?:合理|便宜|价值|估值|内在价值)区间\s*(?:[:：]|为|是|在|约|大约|大致)?\s*" + _CUR + r"\d"),
    ("price event on a value range",
     r"(?:进入|跌入|落入|回到|离开|跌破|突破|高于|低于|接近|触及)了?\s*(?:合理|便宜|价值|买入)区间"),
    ("valuation centre", r"估值中枢"),
    ("intrinsic value with a number", r"内在价值\s*(?:[:：]|为|是|约|大约|在)?\s*" + _CUR + r"\d"),
    ("margin of safety with a number", r"安全边际\s*(?:[:：]|为|是|约|有|达|达到|仅)?\s*\d"),
    ("implied return", r"(?<![A-Za-z])implied\s+(?:(?:annual(?:i[sz]ed)?|annually|yearly|long[\s-]term|expected|forward|"
                       r"total|shareholder|(?:5|10|five|ten)[\s-]year)[\s-]+)*(?:rates?\s+of\s+)?(?:returns?|IRRs?)(?![A-Za-z])"),
    ("price grade", phrase_pattern("price grade")),
    ("value centre", r"(?<![A-Za-z])value\s+cent(?:re|er)s?(?![A-Za-z])"),
    ("price rating", phrase_pattern("price rating")),
    ("central value with a number", r"(?<![A-Za-z])central\s+values?" + _EN_LINK + _EN_NUM),
    ("value range with a number", r"(?<![A-Za-z])(?:fair|value|buy(?:ing)?|cheap|valuation|intrinsic[\s-]+value)[\s-]+"
                                  r"(?:price[\s-]+)?ranges?" + _EN_LINK + _EN_RANGE_OR_MONEY),
    ("price event on a value range",
     r"(?<![A-Za-z])(?:enter(?:s|ed|ing)?|f[ae]ll(?:s|ing)?|dropp?(?:s|ed|ing)?|dipp?(?:s|ed|ing)?|slipp?(?:s|ed|ing)?|"
     r"mov(?:e|es|ed|ing)|trad(?:e|es|ed|ing)|sits?|sitting|sat|is|was|are|were|stays?|stayed|remains?|remained|"
     r"returns?|returned|back)\s+(?:(?:back|now|still|firmly|well|deep(?:ly)?|again|just)\s+)*"
     r"(?:in|into|inside|within|below|above|under|out\s+of|to|at|near)\s+(?:the\s+|its\s+|our\s+|a\s+)?"
     r"(?:fair|value|buy(?:ing)?|cheap)[\s-]+(?:price[\s-]+)?range(?![A-Za-z])"),
    ("intrinsic value with a number",
     r"(?<![A-Za-z])intrinsic\s+values?(?:\s+per\s+share)?(?:\s+(?:estimate|range))?" + _EN_LINK + _EN_NUM),
    ("margin of safety with a number", r"(?<![A-Za-z])margin[\s-]+of[\s-]+safety" + _EN_LINK + _EN_NUM),
    ("margin of safety with a number", r"\d[\d.,]*\s*(?:%|percent|per\s?cent)\s+margin[\s-]+of[\s-]+safety(?![A-Za-z])"),
    ("discount to intrinsic value", r"\d[\d.,]*\s*(?:%|percent|per\s?cent)\s+(?:discount|premium)\s+to\s+"
                                    r"(?:its\s+|our\s+|the\s+)?(?:estimated\s+)?intrinsic\s+value(?![A-Za-z])"),
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
# The market price against book value (or earnings) in words ("price-to-book of 1.3", "trades at 25 times earnings",
# and the Chinese wording for a price below N times book). A company's own average repurchase price against book is a
# disclosed fact (00 §H2 item 3), so the repurchase price and identifiers such as buyback_avg_price_to_book are not
# matched.
MULTIPLE_PATTERNS = (
    ("price-to-book", r"(?<![A-Za-z0-9_])price[\s\-]+to[\s\-]+book(?![A-Za-z0-9_])"),
    ("price against book value", r"(?<!回购)(?:股价|价格|市价)[^。；;\n]{0,10}?倍(?:的)?(?:每股)?(?:账面|净资产)"),
    ("price-to-earnings", r"(?<![A-Za-z0-9_])price[\s\-]+to[\s\-]+earnings(?![A-Za-z0-9_])"),
    ("price/earnings", r"(?<![A-Za-z0-9_])price\s*/\s*(?:earnings|book)(?![A-Za-z0-9_])"),
    ("PE ratio", r"(?<![A-Za-z0-9_/])pe\s+ratios?(?![A-Za-z0-9_])"),
    ("price multiple in words",
     r"(?<![A-Za-z])(?:trades?|trading|traded|(?:shares|stock)\s+(?:is|are|was|were))\s+"
     r"(?:at|for|below|above|under|near|around|over)\s+(?:about\s+|roughly\s+|only\s+|just\s+|less\s+than\s+|"
     r"more\s+than\s+)?\d[\d.,]*\s*(?:x|×|times)\s+(?:its\s+|the\s+)?(?:forward\s+|trailing\s+|next\s+year's\s+|"
     r"this\s+year's\s+)?(?:earnings|book(?:\s+value)?|sales|revenue|ebitda|free\s+cash\s+flow|fcf|cash\s+flow)(?![A-Za-z])"),
)
MULTIPLE_WORDING = compile_wording(MULTIPLE_TERMS + MULTIPLE_SPELLINGS, MULTIPLE_PATTERNS)
_MONTH = (r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|"
          r"oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)")
_NOT_A_QUANTITY_RE = re.compile(
    r"\d{4}-\d{2}(?:-\d{2})?"                                                              # dates
    r"|(?<![A-Za-z])" + _MONTH + r"\.?\s+\d{1,2}(?:st|nd|rd|th)?(?![\d%])(?:,?\s+(?:19|20)\d{2}(?!\d))?"  # Sept. 30, 2026
    r"|(?<![\d.,])\d{1,2}(?:st|nd|rd|th)?\s+" + _MONTH + r"(?![A-Za-z])\.?(?:,?\s+(?:19|20)\d{2}(?!\d))?"  # 30 June 2026
    r"|FY\d{2,4}(?:Q[1-4])?|\d{4}\s*Q[1-4]|(?<![A-Za-z])[QH][1-4](?![0-9])"                # fiscal periods and quarters
    r"|(?<![A-Za-z0-9])[1-4][QH]\d{2}(?![0-9])"                                            # 3Q26, 1H26
    r"|(?<![\d,.])(?:19|20)\d{2}(?![\d,.])"                                                # years
    r"|(?<![A-Za-z])(?:section|sec\.|item|note|part|chapter|exhibit|rule|article|appendix|schedule|table|figure|"
    r"fig\.|page|pp?\.|§)\s*\d+(?:\.\d+)*[A-Za-z]?",                                       # section and item numbers
    re.I,
)
# A price grade (A-E, 00 §V11) next to a ticker: "AXP B− → C", "AXP: C". Flagged only in a sentence about prices or
# valuation (price, valuation, §V11, or the Chinese words for price, valuation and grading) that does not speak of the
# public business, management, quality, culture or capital-allocation ratings, which use the same letters.
_GRADE = r"(?<![A-Za-z0-9])[A-E][+\-\u2212\u2013]?(?![A-Za-z0-9+\-\u2212\u2013])"
_ARROW = r"\s*(?:\u2192|->|\u27f6|to)\s*"
GRADE_LEAK_RE = re.compile(
    # a change of grade: "AXP B− → C", "AXP: B → C", "AXP moved from B to C"
    r"(?<![A-Za-z0-9])[A-Z][A-Z0-9.]{1,9}(?:\s*[:(]\s*|\s+(?:\w+\s+){0,2}?(?:from\s+)?)" + _GRADE + _ARROW + _GRADE +
    # a single grade that ends a list item: "AXP: C, BRK: B" ("APP: A price event" is an article, not a grade)
    r"|(?<![A-Za-z0-9])[A-Z][A-Z0-9.]{1,9}\s*[:(]\s*" + _GRADE + r"(?=\s*(?:[,;)]|\.(?!\w)|$))"
)
_PRICE_CONTEXT_RE = re.compile(r"(?<![A-Za-z])(?:prices?|valuations?)(?![A-Za-z])|§\s*V11|价格|估值|分档", re.I)
_RATING_CONTEXT_RE = re.compile(r"(?<![A-Za-z])(?:business|management|quality|culture|capital[\s-]+allocation)(?![A-Za-z])"
                                r"|生意|管理层|质量|企业文化|资本配置", re.I)
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
# English advice (SPEC 7.5). A buy or sell counts as advice when it is about the stock ("buy the shares", "sell ACME",
# "buy now", "buy." at the end of a clause, "buying or selling") or about the position ("add to the position", "trim
# our stake"); a company buying back its own shares ("buyback", "buy back"), selling a division or buying land is not
# investment advice. As in Chinese, a negative sentence is no exception (00 §H4): "we do not recommend buying" fails.
# Tickers are matched in capitals only.
_TICKER = r"(?-i:[A-Z][A-Z0-9.]{0,9})"
_INVESTOR = r"(?:you|investors?|we|i|one|readers?|owners?|shareholders?|clients?|the\s+owner)"
_NOT_BUYBACK = r"(?![A-Za-z\-])(?!\s+back(?![A-Za-z]))"
_SECURITY_AHEAD = (
    r"(?=\s*(?:[.,;:!?)\]]|$)"
    r"|\s+(?:or|and|nor)\s+(?:buy|sell|short|hold|trim|add|reduc|accumulat)"
    r"|\s+(?:(?:more|some|a\s+few|additional)\s+)?(?:shares|stock|equit(?:y|ies)|ADSs?|ADRs?|it|them|now|here|today|"
    r"immediately|at|below|above|under|on|into|ahead|before|after|the\s+(?:stock|shares|dip|name))(?![A-Za-z])"
    r"|\s+(?:(?:more|some)\s+)?" + _TICKER + r"(?![A-Za-z]))"
)
_POSITION = (
    r"(?:(?:the|our|my|your|this|that|an?)\s+(?:(?:" + _TICKER + r"|core|existing|current|full|whole|entire|new)\s+)?positions?"
    r"|(?:our|my|your)\s+(?:(?:" + _TICKER + r"|core|existing|current|full|whole|entire)\s+)?(?:stakes?|holdings?))"
    r"(?![A-Za-z])(?!\s+(?:of|as)(?![A-Za-z]))"
)
_ADVICE_VERB = (
    r"(?:(?:buy(?:ing)?|sell(?:ing)?|short(?:ing)?|accumulat(?:e|ing)|dump(?:ing)?|add(?:ing)?|reduc(?:e|ing)|trim(?:ming)?)"
    + _NOT_BUYBACK + _SECURITY_AHEAD +
    r"|(?:add(?:ing)?\s+to|trim(?:ming)?|exit(?:ing)?|reduc(?:e|ing)|accumulat(?:e|ing)|open(?:ing)?|clos(?:e|ing)|"
    r"initiat(?:e|ing)|build(?:ing)?|establish(?:ing)?)\s+" + _POSITION + r")"
)
_RATING = r"(?:buy|sell|accumulate|outperform|underperform|market[\s-]+perform)"
ADVICE_PATTERNS = (
    ("buy/sell advice", r"(?:建议|推荐)\s*" + _WHEN + r"\s*" + _ACT),
    ("buy/sell advice", r"(?:应该|应当|可以|值得|不妨|最好|考虑)\s*" + _WHEN + r"\s*" + _HOLD_ACT),
    ("buy/sell advice", r"(?:应该|应当|最好|不妨)\s*" + _WHEN + r"\s*(?:卖出|抛售)"),
    ("buy/sell advice", r"逢高(?:卖出|减持|减仓)"),
    ("rating wording", r"(?:增持|减持|跑赢大市|跑输大市|持有|中性)评级"),
    ("rating wording", r"评级\s*(?:[:：]|为|是|调至|上调至|下调至)?\s*(?:买入|卖出|增持|减持|强烈推荐|推荐|跑赢大市|跑输大市)"),
    # "we recommend adding / trimming / reducing" counts when a security or a position follows ("we suggest adding a
    # source tag" is not advice)
    ("buy/sell advice", r"(?<![A-Za-z])(?:i|we)\s+(?:would\s+|strongly\s+|still\s+)*(?:recommend|suggest|advise|advocate)\s+"
                        r"(?:(?:buying|selling|accumulating|shorting|a\s+(?:buy|sell)|(?:investors\s+)?to\s+(?:buy|sell))"
                        r"(?![A-Za-z])(?!\s+back(?![A-Za-z]))"
                        r"|(?:adding|trimming|reducing)" + _NOT_BUYBACK + _SECURITY_AHEAD +
                        r"|(?:adding\s+to|trimming|reducing)\s+" + _POSITION + r")"),
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
    # English equivalents of the §H4 list (thesis-ci 0.3.0): recommending a buy or sell, buy and sell ratings,
    # "should buy", "is a buy", adding to or trimming a position, buying on dips, "worth buying", "time to buy"
    ("buy/sell advice", r"(?<![A-Za-z])recommend(?:s|ed|ing)?\s+(?:that\s+)?(?:" + _INVESTOR + r"\s+)?(?:to\s+)?" + _ADVICE_VERB),
    ("buy/sell advice", r"(?<![A-Za-z])recommend(?:s|ed|ing)?\s+(?:the|its)\s+(?:stock|shares|ADSs?)(?![A-Za-z])"),
    ("buy/sell advice", r"(?<![A-Za-z])recommend(?:s|ed|ing)?\s+" + _TICKER + r"(?:\s+(?:shares|stock))?(?![A-Za-z'\u2019])"),
    ("buy/sell advice", r"(?<![A-Za-z])(?:recommendation|advice|verdict)\s+(?:is\s+|would\s+be\s+|remains\s+)?to\s+" + _ADVICE_VERB),
    ("buy/sell rating", r"(?<![A-Za-z])(?:rat(?:e|es|ed|ing)|upgrad(?:e|es|ed|ing)|downgrad(?:e|es|ed|ing)|initiat(?:e|es|ed|ing)|"
                        r"reiterat(?:e|es|ed|ing)|maintain(?:s|ed|ing)?)\s+(?:(?:it|them|the\s+(?:stock|shares?|company|name)|shares|"
                        r"coverage(?:\s+(?:of|on)\s+\S+)?|" + _TICKER + r")\s+)?(?:(?:to|at|as|with)\s+)?(?:an?\s+)?(?:strong\s+)?"
                        + _RATING + _NOT_BUYBACK + r"(?!\s+(?:order|side|signal|button|box)(?![A-Za-z]))"),
    ("buy/sell rating", r"(?<![A-Za-z])(?:rating|recommendation|stance|verdict)\s*[:：]\s*(?:strong\s+)?"
                        r"(?:buy|sell|hold|accumulate|reduce|outperform|underperform)(?![A-Za-z_\-])"),
    ("buy/sell rating", r"(?<![A-Za-z])(?:strong[\s-]+)?(?:buy|sell|hold|outperform|underperform)[\s-]rated(?![A-Za-z])"),
    ("buy/sell advice", r"(?<![A-Za-z])(?:is|are|remains?|remained|was|were|looks?\s+like|becomes?|became|stays?)\s+"
                        r"(?:still\s+|now\s+|clearly\s+|definitely\s+)?an?\s+(?:strong\s+|clear\s+|compelling\s+)?(?:buy|sell)"
                        + _NOT_BUYBACK + r"(?!\s+(?:order|side|signal|button|box|decision|program|programme)(?![A-Za-z]))"),
    ("buy/sell advice", r"(?<![A-Za-z])" + _INVESTOR + r"\s+(?:should|must|ought\s+to|need\s+to|have\s+to|had\s+better|"
                        r"would\s+do\s+well\s+to|may\s+want\s+to|might\s+want\s+to)\s+(?:(?:now|still|probably|definitely|"
                        r"seriously|really|also|simply|just|all)\s+)*(?:(?:consider|start|keep|continue|begin)\s+)?" + _ADVICE_VERB),
    ("buy/sell advice", r"(?<![A-Za-z])(?:stock|shares?|ADSs?|position|" + _TICKER + r")\s+(?:should|must|ought\s+to)\s+"
                        r"(?:now\s+|still\s+)?be\s+(?:bought|sold|accumulated|trimmed|shorted|added\s+to|reduced|exited)(?![A-Za-z])"),
    ("position advice", r"(?<![A-Za-z])(?:accumulate|add\s+to|trim|top\s+up|scale\s+(?:into|out\s+of)|double\s+down\s+on|"
                        r"reduce|exit)\s+" + _POSITION),
    ("buy/sell advice", r"(?<![A-Za-z])(?:buy(?:ing)?|accumulat(?:e|ing)|add(?:ing)?)\s+(?:(?:more\s+|some\s+)?"
                        r"(?:shares|stock|the\s+stock|" + _TICKER + r")\s+)?(?:on|into|during)\s+(?:any\s+|the\s+|further\s+|a\s+)?"
                        r"(?:weakness|dips?|pullbacks?|declines?|sell[\s-]?offs?|corrections?)(?![A-Za-z])"),
    ("buy/sell advice", r"(?<![A-Za-z])buy(?:ing)?\s+the\s+dips?(?![A-Za-z])"),
    ("buy/sell advice", r"(?<![A-Za-z])(?:our|my)\s+top\s+picks?(?![A-Za-z])"),
    ("buy/sell advice", r"(?<![A-Za-z])(?:stock|shares?|ADSs?|" + _TICKER + r")\s+(?:is|are|looks?|remains?|seems?)\s+"
                        r"(?:still\s+|well\s+|now\s+)?worth\s+(?:buying|owning|accumulating|adding)(?![A-Za-z])"),
    ("buy/sell advice", r"(?<![A-Za-z])(?:(?:a\s+)?(?:good|great|right|best|perfect)\s+time|now\s+is\s+the\s+time|it'?s\s+time|"
                        r"it\s+is\s+time)\s+to\s+" + _ADVICE_VERB),
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
# The owner's position sizes in public prose ("our stake in X is 12%", and the Chinese first-person wording). Only
# first-person wording counts: Berkshire's own holdings ("cost basis of $24.5 billion") are facts about a company.
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
    ("position size", r"(?<![A-Za-z])(?:portfolio\s+weight(?:ing)?|weight(?:ing)?\s+in\s+(?:the|our|my)\s+portfolio)"
                      r"\s*(?:is|of|at|was|:|~)?\s*" + _CUR + r"\d"),
))


def content_files(repo: Repo, dirs: Iterable[str] = CONTENT_DIRS, root_files: Iterable[str] = CONTENT_ROOT_FILES) -> Iterator[Path]:
    """Text files under the archive content directories, plus the root-level content files, and their Chinese
    versions under zh-CN/ (published like the files they translate)."""
    dirs, root_files = tuple(dirs), tuple(root_files)
    for path in repo.all_files:
        rel = translated_rel(repo.rel(path))
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
    """A fact number (SPEC 3.4 units), a decimal, or a number of two or more digits that is not a year, a date, a
    period or a section number."""
    s = TAG_LIKE_RE.sub(" ", sentence)
    return bool(FACT_RE.search(s) or _PLAIN_NUMBER_RE.search(_NOT_A_QUANTITY_RE.sub(" ", s)))


def price_multiple_issues(repo: Repo, paths: Iterable[Path]) -> Iterator[Issue]:
    """00 §H4: a price-derived multiple (P/E, market cap, FCF yield, P/B, ...) and a number in the same sentence."""
    for path in paths:
        markdown = path.suffix.lower() in (".md", ".markdown")
        # Split first: NFKC turns the full-width Chinese sentence marks into ASCII punctuation.
        for line, raw in sentences(repo.text(path) or "", markdown):
            sentence = normalize_prose(raw)
            for label, rx in MULTIPLE_WORDING:
                if rx.search(sentence) and has_quantity(sentence):
                    yield Issue(path, f"price-derived multiple in public content: '{label}' with a number in the same "
                                      f"sentence (00 §H4): {snippet(raw)}", line)
                    break


def price_grade_issues(repo: Repo, paths: Iterable[Path]) -> Iterator[Issue]:
    """00 §H4: a price grade next to a ticker ("AXP B− → C") in a sentence about prices or valuation."""
    for path in paths:
        markdown = path.suffix.lower() in (".md", ".markdown")
        for line, raw in sentences(repo.text(path) or "", markdown):
            sentence = normalize_prose(raw)
            m = GRADE_LEAK_RE.search(sentence)
            if m and _PRICE_CONTEXT_RE.search(sentence) and not _RATING_CONTEXT_RE.search(sentence):
                yield Issue(path, f"price grade in public content: '{snippet(m.group(0), 30)}' in a sentence about prices "
                                  f"or valuation (00 §H4): {snippet(raw)}", line)


def valuation_files(repo: Repo) -> list[Path]:
    """Public content plus the progress files (REPORT_FILES), for the valuation and advice wording checks."""
    return list(content_files(repo, root_files=CONTENT_ROOT_FILES + REPORT_FILES))


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
    yield from forbidden_wording(repo, valuation_files(repo), VALUATION_WORDING, "price-range wording in public content")
    yield from price_multiple_issues(repo, valuation_files(repo))
    yield from price_grade_issues(repo, valuation_files(repo))


def advice_files(repo: Repo) -> list[Path]:
    readmes = [p for p in repo.all_files if p.name.lower().startswith("readme")]
    return sorted(set(valuation_files(repo)) | set(readmes))


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
        story = path.name == "story.md" and translated_rel(repo.rel(path)).startswith("companies/")
        yield from forbidden_wording(repo, [path], STORY_POSITION_WORDING if story else POSITION_WORDING,
                                     "position amount in public content")
