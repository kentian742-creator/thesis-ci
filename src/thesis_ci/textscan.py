"""Source tags and fact numbers in prose (SPEC 3.1 and 3.4), and wording scans for public content.

A sentence is split on 。！？； and newlines. Every sentence that contains a fact number must contain at
least one ``[src:TAG]`` tag. Front matter, fenced code, inline code and link URLs never count; they are
blanked out (not deleted) so line numbers stay correct.
"""

from __future__ import annotations

import re
import unicodedata
from bisect import bisect_right
from typing import Iterable, Iterator

# SPEC 3.1
TAG_RE = re.compile(r"\[src:([A-Z0-9][A-Za-z0-9._-]*)(?:#([^\]\s]+))?\]")
# Anything that looks like a tag; checked against TAG_RE to report malformed tags.
TAG_LIKE_RE = re.compile(r"\[src:[^\]\n]*\]")

# SPEC 3.4 lists the units that make a number a fact. The same units are also recognised in their other
# spellings, so a fact cannot dodge its tag by the way it is written: English words (percent, basis points,
# percentage points, cents, thousand / trillion, tn / mn, an "x" multiple as in 25x), other currencies
# (€ £ ¥ ₹, USD / RMB / HKD ... codes, 港元 欧元 日元 英镑 人民币 ...) and a Chinese magnitude in front of a
# unit (5 千美元, 3 百亿). Any whitespace may separate a number from its unit (PDF text often has two spaces).
_CURRENCY_WORD = r"(?:[美港欧加澳韩]?元|日元(?!旦)|港币|台币|英镑|人民币|美金|比索|卢比|雷亚尔|卢布)"
_UNIT = (
    r"%|％|‰|亿|万|千万|百万|" + _CURRENCY_WORD +
    r"|美分|倍|×|个百分点|百分点|基点|¢"
    r"|(?:pp|bps?|bn|tn|mn|pct)(?![A-Za-z])"
    r"|(?:million|billion|trillion|thousand)s?(?![A-Za-z])"
    r"|(?:percent|per\s?cent|percentage\s+points?|basis\s+points?|cents?)(?![A-Za-z])"
)
FACT_RE = re.compile(
    r"[$＄€£¥￥₹]\s*\d"
    r"|(?<![A-Za-z])(?:USD|US\$|RMB|CNY|HKD|EUR|JPY|GBP|CAD|AUD)\s*\d"
    r"|\d[\d,.]*\s*(?:" + _UNIT + r")"
    # 十 / 百 / 千 as a magnitude: a short number only, not one ending a date (2019-06 百亿补贴 is a name)
    r"|(?<![\d\-/.:,])\d{1,3}(?:\.\d+)?\s*[十百千](?:[万亿]|" + _CURRENCY_WORD + r")"
    r"|\d[\d,.]*[xX](?![A-Za-z0-9])"
)
SENTENCE_RE = re.compile(r"[^。！？；\n]+")
FRONT_MATTER_RE = re.compile(r"\A\ufeff?---[ \t]*\r?\n(.*?)^---[ \t]*\r?$", re.S | re.M)

_FENCE_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})[^\n]*\n.*?^[ \t]{0,3}\1[`~]*[ \t]*\r?$", re.S | re.M)
_INLINE_CODE_RE = re.compile(r"(`+)[^\n]*?\1")
_LINK_URL_RE = re.compile(r"\]\(([^)\s]*)((?:\s+\"[^\"\n]*\")?)\)")
_AUTOLINK_RE = re.compile(r"<(?:https?|ftp|mailto):[^>\s]*>")
_REF_DEF_RE = re.compile(r"^[ \t]{0,3}\[[^\]\n]+\]:[ \t]*(\S+)", re.M)
_BARE_URL_RE = re.compile(r"(?:https?|ftp)://[^\s)\]>\"'，。；）]+")

# Invisible characters that can split a number from its unit or a phrase in two.
_INVISIBLE = dict.fromkeys(map(ord, "\u00ad\u180e\u200b\u200c\u200d\u2060\ufeff"), None)
# Traditional forms of the characters used in the wording lists, so 建議買入 reads as 建议买入.
_TRADITIONAL = str.maketrans(
    "議買賣減標價區間樞倉級薦該應隱報強賴業這於評組權東頭點將",
    "议买卖减标价区间枢仓级荐该应隐报强赖业这于评组权东头点将",
)


def _blank(s: str) -> str:
    return re.sub(r"[^\n]", " ", s)


def _blank_matches(rx: re.Pattern, text: str, group: int = 0) -> str:
    def repl(m: re.Match) -> str:
        if group == 0:
            return _blank(m.group(0))
        start, end = m.span(group)
        base = m.start(0)
        whole = m.group(0)
        return whole[: start - base] + _blank(m.group(group)) + whole[end - base:]

    return rx.sub(repl, text)


def mask(text: str, markdown: bool = True) -> str:
    """Blank out regions that never carry facts and drop invisible characters, keeping every newline in place."""
    text = text.translate(_INVISIBLE)
    if markdown:
        m = FRONT_MATTER_RE.match(text)
        if m:
            text = _blank(m.group(0)) + text[m.end():]
        text = _blank_matches(_FENCE_RE, text)
    text = _blank_matches(_INLINE_CODE_RE, text)
    text = _blank_matches(_LINK_URL_RE, text, 1)
    text = _blank_matches(_AUTOLINK_RE, text)
    text = _blank_matches(_REF_DEF_RE, text, 1)
    text = _blank_matches(_BARE_URL_RE, text)
    return text


def _line_index(text: str) -> list[int]:
    return [0] + [i + 1 for i, ch in enumerate(text) if ch == "\n"]


def line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def sentences(text: str, markdown: bool = True) -> Iterator[tuple[int, str]]:
    """(line, sentence) pairs of the masked text."""
    masked = mask(text, markdown)
    starts = _line_index(masked)
    for m in SENTENCE_RE.finditer(masked):
        if m.group(0).strip():
            yield bisect_right(starts, m.start()), m.group(0)


def untagged_facts(text: str, markdown: bool = True) -> list[tuple[int, str, str]]:
    """(line, sentence, number) for every sentence with a fact number and no [src:] tag."""
    out = []
    for line, sentence in sentences(text, markdown):
        fact = FACT_RE.search(sentence)
        if fact and not TAG_RE.search(sentence):
            out.append((line, sentence.strip(), fact.group(0).strip()))
    return out


def source_tags(text: str, markdown: bool = True) -> list[tuple[int, str | None, str]]:
    """(line, tag, raw) for every tag-like token; tag is None when the token is malformed."""
    masked = mask(text, markdown)
    starts = _line_index(masked)
    out = []
    for m in TAG_LIKE_RE.finditer(masked):
        full = TAG_RE.fullmatch(m.group(0))
        out.append((bisect_right(starts, m.start()), full.group(1) if full else None, m.group(0)))
    return out


def split_front_matter(text: str) -> tuple[str | None, str]:
    """(front matter YAML or None, body)."""
    m = FRONT_MATTER_RE.match(text)
    if not m:
        return None, text
    body = text[m.end():]
    return m.group(1), body[1:] if body.startswith("\n") else body


def story_length(body: str) -> int:
    """Characters of a story body without source tags, Markdown markup, link targets or whitespace."""
    t = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    t = TAG_RE.sub("", t)
    t = _LINK_URL_RE.sub("]", t)
    t = re.sub(r"<[^>\n]+>", "", t)
    t = t.translate(_INVISIBLE)
    t = re.sub(r"[\s#*_>\-|`\[\]!]", "", t)
    return len(t)


def phrase_hits(text: str, phrases: tuple[str, ...] | list[str]) -> Iterator[tuple[int, str]]:
    """(line, phrase) for every case-insensitive substring occurrence of any phrase (used for code)."""
    low = text.lower()
    for phrase in phrases:
        needle = phrase.lower()
        start = low.find(needle)
        while start >= 0:
            yield line_of(text, start), phrase
            start = low.find(needle, start + 1)


# -- wording in prose ------------------------------------------------------------------------------------
def normalize_prose(text: str) -> str:
    """NFKC (full-width letters and digits), invisible characters removed, traditional to simplified.

    Newlines are preserved, so line numbers computed on the result are the file's line numbers.
    """
    return unicodedata.normalize("NFKC", text.translate(_INVISIBLE)).translate(_TRADITIONAL)


def phrase_pattern(phrase: str) -> str:
    """Regex for a wording phrase: any whitespace between Chinese characters (建议 买入), any run of spaces,
    underscores or hyphens between English words (strong-buy, price_target), and whole English words only
    (strong buy does not match strong buyer), an English plural allowed."""
    units = re.findall(r"[A-Za-z0-9]+|\S", phrase)
    out = ""
    prev_word = False
    for i, unit in enumerate(units):
        word = unit.isascii() and unit.isalnum()
        if i:
            out += r"[\s_\-]+" if (word and prev_word) else r"\s*"
        out += re.escape(unit)
        prev_word = word
    if units and units[0].isascii() and units[0].isalnum():
        out = r"(?<![A-Za-z0-9])" + out
    if units and units[-1].isascii() and units[-1].isalnum():
        out += r"(?:s|es)?(?![A-Za-z0-9])"
    return out


def compile_wording(phrases: Iterable[str] = (), patterns: Iterable[tuple[str, str]] = ()) -> list[tuple[str, re.Pattern]]:
    """(label, compiled regex) for literal phrases plus (label, regex) pairs, all case-insensitive."""
    out = [(p, re.compile(phrase_pattern(p), re.I)) for p in phrases]
    out += [(label, re.compile(rx, re.I | re.M)) for label, rx in patterns]
    return out


def wording_hits(text: str, wording: list[tuple[str, re.Pattern]]) -> Iterator[tuple[int, str, str]]:
    """(line, label, matched text) for every match of the compiled wording in the normalized text.

    A match that overlaps an earlier one is not reported again, so a listed phrase and a broader pattern
    report the same words once (under the first, i.e. the listed, label).
    """
    norm = normalize_prose(text)
    taken: list[tuple[int, int]] = []
    hits = []
    for label, rx in wording:
        for m in rx.finditer(norm):
            start, end = m.span()
            if end == start or any(start < e and s < end for s, e in taken):
                continue
            taken.append((start, end))
            hits.append((start, label, " ".join(m.group(0).split())))
    for start, label, matched in sorted(hits):
        yield line_of(norm, start), label, matched


def snippet(s: str, width: int = 60) -> str:
    s = " ".join(s.split())
    return s if len(s) <= width else s[: width - 1] + "…"
