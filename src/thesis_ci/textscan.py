"""Source tags and fact numbers in prose (SPEC 3.1 and 3.4), and wording scans for public content.

Every sentence that contains a fact number must contain at least one ``[src:TAG]`` tag. Text in Chinese, Japanese or
Korean is split into sentences at the Chinese full stop, exclamation mark, question mark and semicolon and at every
newline. English text is split at ``.``, ``!``, ``?`` and ``;`` followed by whitespace (``;`` not inside parentheses), except after an abbreviation
(``U.S.``, ``Inc.``, ``e.g.``, ``No. 1``) and inside a source tag; a line break inside an English paragraph does not end a
sentence (prose is often hard-wrapped), but a blank line, a heading, a list item, a table row or a block quote does.
Front matter, fenced code, inline code and link URLs never count; they are blanked out (not deleted) so line numbers
stay correct.
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

# Chinese, Japanese and Korean letters: Han ideographs, kana and hangul. A line that contains any CJK character is
# split into sentences the Chinese way (SPEC 3.4); a story with mostly CJK letters is measured in characters (SPEC 5).
_CJK_LETTERS = (
    "\u1100-\u11ff"          # Hangul Jamo
    "\u3040-\u30ff"          # Hiragana, Katakana
    "\u3130-\u318f"          # Hangul Compatibility Jamo
    "\u31f0-\u31ff"          # Katakana Phonetic Extensions
    "\u3400-\u4dbf"          # CJK Unified Ideographs Extension A
    "\u4e00-\u9fff"          # CJK Unified Ideographs
    "\ua960-\ua97f"          # Hangul Jamo Extended-A
    "\uac00-\ud7ff"          # Hangul Syllables, Hangul Jamo Extended-B
    "\uf900-\ufaff"          # CJK Compatibility Ideographs
    "\U0001b000-\U0001b16f"  # Kana Supplement, Kana Extended-A, Small Kana Extension
    "\U00020000-\U000323af"  # CJK Unified Ideographs Extensions B-H, CJK Compatibility Ideographs Supplement
)
CJK_LETTER_RE = re.compile(f"[{_CJK_LETTERS}]")
# Any CJK character, punctuation and full-width forms included (C-LANGUAGE: an English file contains none).
CJK_RE = re.compile(
    f"[{_CJK_LETTERS}"
    "\u2e80-\u2fff"          # CJK Radicals Supplement, Kangxi Radicals, Ideographic Description Characters
    "\u3000-\u303f"          # CJK Symbols and Punctuation
    "\u3100-\u312f"          # Bopomofo
    "\u3190-\u31ef"          # Kanbun, Bopomofo Extended, CJK Strokes
    "\u3200-\u33ff"          # Enclosed CJK Letters and Months, CJK Compatibility
    "\ufe30-\ufe4f"          # CJK Compatibility Forms
    "\uff00-\uffef"          # Halfwidth and Fullwidth Forms
    "]"
)

# SPEC 3.4 lists the units that make a number a fact. The same units are also recognised in their other spellings, so
# a fact cannot dodge its tag by the way it is written: English words (percent, basis points, percentage points,
# cents, thousand / million / billion / trillion, bn / mn / tn, an "x" multiple as in 25x, currency names), other
# currencies (symbols, ISO codes before or after the number, the Chinese currency names) and a Chinese magnitude in
# front of a unit. English units are matched in any letter case. Any whitespace may separate a number from its unit
# (PDF text often has two spaces).
_CURRENCY_WORD = r"(?:[美港欧加澳韩]?元|日元(?!旦)|港币|台币|英镑|人民币|美金|比索|卢比|雷亚尔|卢布)"
_CURRENCY_CODE = r"(?:USD|RMB|CNY|HKD|EUR|JPY|GBP|CAD|AUD|CHF|INR|KRW|TWD|SGD)"
_UNIT = (
    r"%|％|‰|亿|万|千万|百万|" + _CURRENCY_WORD +
    r"|美分|倍|×|个百分点|百分点|基点|¢"
    r"|(?i:pp|ppts?|bps?|bn|bln|tn|mn|mln|pct)(?![A-Za-z])"
    r"|(?i:million|billion|trillion|thousand)s?(?![A-Za-z])"
    r"|(?i:percent|per\s?cent|percentage\s+points?|basis\s+points?|cents?)(?![A-Za-z])"
    r"|(?i:dollars?|euros?|yuan|renminbi|yen|pesos?|rupees?|reais|rubles?|roubles?|francs?)(?![A-Za-z])"
    r"|" + _CURRENCY_CODE + r"(?![A-Za-z])"
)
FACT_RE = re.compile(
    r"[$＄€£¥￥₹]\s*\d"
    r"|(?<![A-Za-z])(?:US\$|" + _CURRENCY_CODE[3:-1] + r")\s*\d"
    r"|\d[\d,.]*\s*(?:" + _UNIT + r")"
    # a Chinese magnitude (ten, hundred, thousand) before a unit: a short number only, not one ending a date
    # (a date followed by a programme name is not a fact)
    r"|(?<![\d\-/.:,])\d{1,3}(?:\.\d+)?\s*[十百千](?:[万亿]|" + _CURRENCY_WORD + r")"
    r"|\d[\d,.]*[xX](?![A-Za-z0-9])"
)
FRONT_MATTER_RE = re.compile(r"\A\ufeff?---[ \t]*\r?\n(.*?)^---[ \t]*\r?$", re.S | re.M)

# -- sentences (SPEC 3.4) ----------------------------------------------------------------------------------------
# Chinese: the full stop, exclamation mark, question mark and semicolon end a sentence, and so does every newline.
_CN_END_RE = re.compile(r"[。！？；]")
# English: . ! ? or ; followed by whitespace; a closing quote or parenthesis may come in between ("... 16%.) Next"),
# and so may a source tag written right after the punctuation, footnote style ("... 16%.[src:TAG] Next"), which then
# belongs to the sentence it follows.
_EN_END_RE = re.compile(r"[.!?;][\"'\u201d\u2019)]*(?:\[src:[^\]\s]*\])*(?=\s|\Z)")
# A period after one of these ends an abbreviation, not a sentence (compared in lower case, without the period).
ABBREVIATIONS = frozenset({
    "inc", "corp", "ltd", "co", "cos", "llc", "bros", "intl",
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st",
    "vs", "approx", "est", "avg", "incl", "excl", "dept", "fig", "figs", "al", "cf", "viz",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec",
})
# "No." and "Nos." abbreviate "number" only before a number ("No. 1"); "the answer is no." ends a sentence.
_NUMBER_ABBREVIATIONS = frozenset({"no", "nos"})
_ABBR_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])[A-Za-z](?:[A-Za-z]|\.(?=[A-Za-z]))*\Z")
# Markdown blocks: a line that starts one of these begins a new sentence even in English.
_BLOCK_START_RE = re.compile(
    r"[ \t]*(?:#{1,6}(?:[ \t]|$)|>|\||[-*+][ \t]|\d{1,3}[.)](?:[ \t]|$)|(?:[-*_=][ \t]*){3,}$)"
)
_HEADING_RE = re.compile(r"[ \t]*#{1,6}(?:[ \t]|$)")
_TABLE_ROW_RE = re.compile(r"[ \t]*\||.*[ \t]\|[ \t]")
_QUOTE_RE = re.compile(r"[ \t]*>")

_FENCE_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})[^\n]*\n.*?^[ \t]{0,3}\1[`~]*[ \t]*\r?$", re.S | re.M)
_INLINE_CODE_RE = re.compile(r"(`+)[^\n]*?\1")
_LINK_URL_RE = re.compile(r"\]\(([^)\s]*)((?:\s+\"[^\"\n]*\")?)\)")
_AUTOLINK_RE = re.compile(r"<(?:https?|ftp|mailto):[^>\s]*>")
_REF_DEF_RE = re.compile(r"^[ \t]{0,3}\[[^\]\n]+\]:[ \t]*(\S+)", re.M)
_BARE_URL_RE = re.compile(r"(?:https?|ftp)://[^\s)\]>\"'，。；）]+")

# Invisible characters that can split a number from its unit or a phrase in two.
_INVISIBLE = dict.fromkeys(map(ord, "\u00ad\u180e\u200b\u200c\u200d\u2060\ufeff"), None)
# Traditional forms of the characters used in the wording lists, so the traditional spelling of a listed phrase is
# read as the simplified one.
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


def _abbreviation(text: str, dot: int) -> bool:
    """True when the period at ``dot`` ends an abbreviation (U.S., Inc., e.g., vs., No. 1) rather than a sentence."""
    m = _ABBR_TOKEN_RE.search(text, max(0, dot - 24), dot)
    if m is None:
        return False
    token = m.group(0)
    low = token.lower()
    if low in _NUMBER_ABBREVIATIONS:
        rest = text[dot + 1: dot + 12].lstrip()
        return rest[:1].isdigit() or rest[:1] == "#"
    if "." in token or (len(token) == 1 and token.isupper()):
        return True  # initialisms (U.S., e.g., i.e., a.m.) and initials (J. Smith)
    return low in ABBREVIATIONS


def _hard_break(prev: str, nxt: str) -> bool:
    """Whether the newline between two English lines ends a sentence; a soft-wrapped line inside a paragraph does not."""
    if not prev.strip() or not nxt.strip():
        return True
    if _HEADING_RE.match(prev) or _TABLE_ROW_RE.match(prev) or _TABLE_ROW_RE.match(nxt):
        return True
    if _QUOTE_RE.match(nxt):  # a block quote starts, unless the quoted paragraph continues
        return not (_QUOTE_RE.match(prev) and prev.strip() != ">" and nxt.strip() != ">")
    return bool(_BLOCK_START_RE.match(nxt))


def _inside_parentheses(text: str, pos: int) -> bool:
    """Whether ``pos`` lies inside a parenthesis opened earlier in the same paragraph."""
    start = text.rfind("\n\n", 0, pos)
    segment = text[start + 1 if start >= 0 else 0: pos]
    return segment.count("(") > segment.count(")")


def sentence_spans(masked: str) -> list[tuple[int, int]]:
    """(start, end) offsets of the sentences of already masked text (see the module docstring)."""
    lines = masked.split("\n")
    starts = _line_index(masked)
    cjk = [bool(CJK_RE.search(line)) for line in lines]
    seps: set[tuple[int, int]] = {m.span() for m in _CN_END_RE.finditer(masked)}
    for i in range(len(lines) - 1):
        if cjk[i] or cjk[i + 1] or _hard_break(lines[i].rstrip("\r"), lines[i + 1].rstrip("\r")):
            newline = starts[i + 1] - 1
            seps.add((newline, newline + 1))
    tags = [m.span() for m in TAG_LIKE_RE.finditer(masked)]
    for m in _EN_END_RE.finditer(masked):
        pos = m.start()
        if cjk[bisect_right(starts, pos) - 1] or any(s <= pos < e for s, e in tags):
            continue
        if masked[pos] == "." and _abbreviation(masked, pos):
            continue
        if masked[pos] == ";" and _inside_parentheses(masked, pos):
            continue  # "(... for 2016-2025; [src:X])": the tag after the semicolon belongs to the same sentence
        seps.add((m.end(), m.end()))
    spans: list[tuple[int, int]] = []
    prev = 0
    for start, end in sorted(seps):
        if start > prev:
            spans.append((prev, start))
        prev = max(prev, end)
    if prev < len(masked):
        spans.append((prev, len(masked)))
    return spans


def sentences(text: str, markdown: bool = True) -> Iterator[tuple[int, str]]:
    """(line, sentence) pairs of the masked text; the line is where the sentence starts."""
    masked = mask(text, markdown)
    starts = _line_index(masked)
    for start, end in sentence_spans(masked):
        sentence = masked[start:end]
        if sentence.strip():
            first = start + len(sentence) - len(sentence.lstrip())
            yield bisect_right(starts, first), sentence


# A forecast stated in the standard probability language with its probability, "It is likely (0.65) that ...": a
# judgment written in advance, not a fact, so it needs no tag (SPEC 3.1).
PROBABILITY_JUDGMENT_RE = re.compile(r"(?i)\b(?:very likely|likely|uncertain|unlikely|very unlikely)\s*\(\s*(?:0?\.\d{1,2}|1(?:\.0+)?|\d{1,2}%)\s*\)")


def untagged_facts(text: str, markdown: bool = True) -> list[tuple[int, str, str]]:
    """(line, sentence, number) for every sentence with a fact number and no [src:] tag; the line is the number's. A
    sentence stating a probability judgment (PROBABILITY_JUDGMENT_RE) is a forecast, not a fact."""
    masked = mask(text, markdown)
    starts = _line_index(masked)
    out = []
    for start, end in sentence_spans(masked):
        sentence = masked[start:end]
        fact = FACT_RE.search(sentence)
        if fact and not TAG_RE.search(sentence) and not PROBABILITY_JUDGMENT_RE.search(sentence):
            out.append((bisect_right(starts, start + fact.start()), sentence.strip(), fact.group(0).strip()))
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


# -- two-minute stories (SPEC 5) ----------------------------------------------------------------------------------
_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['\u2019.,\-/&][A-Za-z0-9]+)*")


def _story_prose(body: str) -> str:
    """A story body without HTML comments, source tags, link targets, HTML tags or invisible characters."""
    t = re.sub(r"<!--.*?-->", "", body, flags=re.S)
    t = TAG_RE.sub("", t)
    t = _LINK_URL_RE.sub("]", t)
    t = re.sub(r"<[^>\n]+>", "", t)
    return t.translate(_INVISIBLE)


def story_length(body: str) -> int:
    """Characters of a story body without source tags, Markdown markup, link targets or whitespace."""
    return len(re.sub(r"[\s#*_>\-|`\[\]!]", "", _story_prose(body)))


def story_words(body: str) -> int:
    """English words of a story body; source tags, link targets and Markdown markup do not count."""
    return len(_WORD_RE.findall(CJK_RE.sub(" ", _story_prose(body))))


def story_is_cjk(body: str) -> bool:
    """True for a story written in Chinese, Japanese or Korean: at least as many CJK letters as English words."""
    cjk = len(CJK_LETTER_RE.findall(_story_prose(body)))
    return cjk > 0 and cjk >= story_words(body)


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
    """Regex for a wording phrase: any whitespace between Chinese characters, any run of spaces, underscores or
    hyphens between English words (strong-buy, price_target), and whole English words only (strong buy does not
    match strong buyer), an English plural allowed."""
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
