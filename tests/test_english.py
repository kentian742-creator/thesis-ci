"""English content (thesis-ci 0.3.0): sentence splitting, fact numbers, the English wording of 00 §H4, the story's word
limit, the zh-CN/ convention and C-LANGUAGE.

Each test's docstring names the check it covers.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from thesis_ci import engine, selftest
from thesis_ci.checks.constitution import constitution_checks
from thesis_ci.checks.public import has_quantity
from thesis_ci.textscan import FACT_RE, sentences, story_is_cjk, story_words, untagged_facts

STORY = "public/companies/ACME/story.md"
ZH_STORY = "public/zh-CN/companies/ACME/story.md"
LETTER = "public/letters/2026-09.md"
SOURCES = "public/companies/ACME/sources.yml"
IND_README = "public/industries/widgets/README.md"
BUY_MEMO = "private/memos/2026-09-20-ACME-entry.yml"
STORY_END = selftest.STORY_END


def edit(ws: Path, rel: str, old: str, new: str) -> None:
    selftest.apply(ws, (selftest.replace(rel, old, new),))


def put(ws: Path, rel: str, text: str) -> None:
    selftest.apply(ws, (selftest.write(rel, text),))


def story_line(ws: Path, text: str) -> None:
    """Add ``text`` to the English story as a line of its own, before the last sentence."""
    edit(ws, STORY, STORY_END, text + "\n" + STORY_END)


def facts(text: str) -> list[tuple[int, str]]:
    return [(line, number) for line, _sentence, number in untagged_facts(text)]


# --------------------------------------------------------------------------- sentences (SPEC 3.4)
@pytest.mark.parametrize("text, expected", [
    ("Revenue grew 16%. Margins were 62% [src:A#p1].", [(1, "16%")]),
    ("Revenue grew 16% [src:A#p1]. Margins were 62%.", [(1, "62%")]),
    ("Revenue grew 16%; margins were 62% [src:A#p1].", [(1, "16%")]),
    ("Did revenue grow 16%? Margins were 62% [src:A#p1].", [(1, "16%")]),
    ("Revenue grew 16%! Margins were 62% [src:A#p1].", [(1, "16%")]),
    ("(Revenue grew 16%.) Margins were 62% [src:A#p1].", [(1, "16%")]),
    ("Revenue grew 3.5% [src:A#p1] and margins 62.4% [src:A#p2].", []),  # decimals do not end a sentence
])
def test_c_src_tag_english_sentences_end_at_punctuation(text, expected):
    """C-SRC-TAG: in English, . ! ? and ; followed by whitespace end a sentence; a decimal point does not."""
    assert facts(text) == expected


@pytest.mark.parametrize("text", [
    "Revenue grew 16% in the U.S. market [src:A#p1].",
    "Revenue grew 16% at Acme Inc. and its peers [src:A#p1].",
    "Revenue grew 16% at Acme Corp. and its peers [src:A#p1].",
    "Revenue grew 16% at Acme Ltd. and its peers [src:A#p1].",
    "Costs rose 5% on inputs, e.g. freight [src:A#p1].",
    "Margins fell 2 pp, i.e. to 60% [src:A#p1].",
    "Revenue grew 16% vs. 12% a year earlier [src:A#p1].",
    "Revenue grew 16%, which makes it No. 1 in widgets [src:A#p1].",
    "Revenue grew 16% under Warren E. Buffett [src:A#p1].",
    "Revenue grew 16% by Sept. 30 [src:A#p1].",
])
def test_c_src_tag_english_abbreviations_do_not_end_a_sentence(text):
    """C-SRC-TAG: a period after U.S., Inc., Corp., Ltd., e.g., i.e., vs., No. 1, an initial or a month is not an end."""
    assert facts(text) == []


def test_c_src_tag_english_no_ends_a_sentence_unless_a_number_follows():
    """C-SRC-TAG: "No." abbreviates "number" only before a number; "the answer is no." ends a sentence."""
    assert facts("Revenue grew 16% and the answer is no. Margins were 62% [src:A#p1].") == [(1, "16%")]


@pytest.mark.parametrize("text, expected", [
    ("Revenue grew 16%.[src:A#p1] Margins were 62%.", [(1, "62%")]),  # a footnote-style tag belongs to its sentence
    ("Revenue grew 16%.[src:A#p1]", []),
    ("Revenue grew 16%. [src:A#p1]", [(1, "16%")]),  # after the space the tag starts the next sentence
    ("Revenue grew 16% [src:A#p1. x] and more.", [(1, "16%")]),  # a malformed tag is no tag, and is never split
])
def test_c_src_tag_english_tags_and_sentence_ends(text, expected):
    """C-SRC-TAG: a tag written right after the period belongs to that sentence; a tag after a space does not."""
    assert facts(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("Revenue grew 16% in FY2026, driven by\ncloud [src:A#p1].", []),  # a hard-wrapped line continues the sentence
    ("Revenue grew 16% in FY2026, driven by\n\ncloud [src:A#p1].", [(1, "16%")]),  # a blank line ends it
    ("- Revenue grew 16%\n- Margins were 62% [src:A#p1]", [(1, "16%")]),  # each list item is its own sentence
    ("1. Revenue grew 16%\n2. Margins were 62% [src:A#p1]", [(1, "16%")]),
    ("## Revenue grew 16%\nMargins were 62% [src:A#p1].", [(1, "16%")]),  # a heading ends at its line
    ("| Revenue | 16% |\n| Margin | 62% [src:A#p1] |", [(1, "16%")]),  # table rows are separate
    ("> Revenue grew 16%\n> and margins 62% [src:A#p1].", []),  # a quoted paragraph continues
    ("Revenue was flat and margins\nfell 2 percentage points.", [(2, "2 percentage points")]),  # the number's line
])
def test_c_src_tag_english_line_breaks(text, expected):
    """C-SRC-TAG: a line break inside an English paragraph does not end a sentence; Markdown blocks do."""
    assert facts(text) == expected


def test_c_src_tag_chinese_lines_split_as_before():
    """C-SRC-TAG: a line with Chinese text is split at the Chinese marks and newlines only, as before 0.3.0."""
    assert facts("营收增长 16%. 利润 20%[src:A#p1]。") == []
    assert facts("营收 16%[src:A#p1]。利润 20%。\n现金 $5 亿[src:A#p2]；负债 3 亿！") == [(1, "20%"), (2, "3 亿")]


def test_c_src_tag_english_sentences_in_the_archive(ws, lint):
    """C-SRC-TAG: one tag no longer covers two English sentences in a story."""
    edit(ws, STORY, "60% of revenue [src:ACME-RPT-2026-09#p4]", "60% of revenue. It was 55% a year earlier [src:ACME-RPT-2026-09#p4]")
    found = lint(ws, "C-SRC-TAG")
    assert [(f.line, "60%" in f.message) for f in found] == [(13, True)]


def test_c_src_fact_english_sentences_in_yaml(ws, lint):
    """C-SRC-FACT: YAML free text is split into English sentences too."""
    edit(ws, "public/companies/ACME/thesis.yml", "recurring revenue is 60% of revenue [src:ACME-RPT-2026-09#p4].",
         "recurring revenue is 60% of revenue. It keeps rising [src:ACME-RPT-2026-09#p4].")
    assert len(lint(ws, "C-SRC-FACT")) == 1


# --------------------------------------------------------------------------- fact numbers (SPEC 3.4)
ENGLISH_FACTS = [
    "$495", "$3.5 billion", "US$5", "HK$5", "CHF 5", "16%", "16 percent", "16 per cent", "16 PERCENT", "25x", "1.04×",
    "3 bn", "4 bln", "5 mn", "7 mln", "11.9 tn", "20 million", "3.5 billion", "3 Billion", "1.2 trillion", "3 thousand",
    "5 pp", "2 ppts", "5 pct", "30 bps", "3 bp", "12 basis points", "2 percentage points", "40 cents", "5¢",
    "5 dollars", "5 euros", "5 USD", "1.2 billion RMB",
]
ENGLISH_NOT_FACTS = [
    "September 30, 2026", "Sept. 30", "30 June 2026", "FY2026", "FY26", "Q3 2026", "3Q26", "1H26", "the 2020s",
    "Section 3.4", "Item 7A", "Note 12", "Rule 10b5-1", "Form 20-F", "No. 1", "Top 10", "5 years", "12 segments",
    "S&P 500", "a 2x2 matrix", "COVID-19", "401(k)", "24/7", "Windows 11", "5G",
]


@pytest.mark.parametrize("text", ENGLISH_FACTS)
def test_c_src_tag_english_fact_numbers_need_a_tag(text):
    """C-SRC-TAG: $, %, x/× multiples, bn/mn/million/billion/trillion, pp, bps, basis points, percentage points, cents."""
    assert FACT_RE.search(text), text
    assert len(untagged_facts(f"Revenue was {text}.")) == 1
    assert untagged_facts(f"Revenue was {text} [src:ACME-RPT-2026-09#p3].") == []


@pytest.mark.parametrize("text", ENGLISH_NOT_FACTS)
def test_c_src_tag_english_dates_periods_and_sections_are_not_facts(text):
    """C-SRC-TAG: years, dates, periods, section numbers and names are not facts in English either."""
    assert FACT_RE.search(text) is None, text
    assert untagged_facts(f"See {text}.") == []


# --------------------------------------------------------------------------- 00 §H4 in English: valuation
@pytest.mark.parametrize("text", [
    "The implied return is 12% [src:ACME-RPT-2026-09#p5].",
    "Its implied annual return beats the hurdle.",
    "The implied annualized return is not stated here.",
    "The implied annualised return is lower.",
    "We compare the implied IRR with the hurdle.",
    "The market-implied return of a peer.",
    "The value centre moved up.",
    "ACME has a price grade of B.",
    "The price rating is A.",
    "The central value is $120.",
    "The central value for ACME is about 120.",
    "The fair range is 110–130.",
    "The value range is $110 to $130.",
    "The buy range is 78–90.",
    "The cheap range starts at $78.",
    "ACME entered the buy range this month.",
    "The shares fell below the fair range.",
    "The stock is back in the value range.",
    "Intrinsic value of $120 per share.",
    "The intrinsic value per share is $120.",
    "A margin of safety of 30%.",
    "The margin of safety is now 25%.",
    "It offers a 30% margin of safety.",
    "It trades at a 30% discount to intrinsic value.",
])
def test_c_public_no_valuation_english_wording(ws, lint, text):
    """C-PUBLIC-NO-VALUATION: the English equivalents of the §H4 valuation terms are errors in public content."""
    story_line(ws, text)
    assert lint(ws, "C-PUBLIC-NO-VALUATION"), text


@pytest.mark.parametrize("text", [
    "Level 3 fair value measurements were $2.1 billion [src:ACME-10K-FY2026#Item8].",  # accounting fair value
    "Stores carry a fair range of products.",
    "Intrinsic value grew faster than book value.",
    "Buffett explains intrinsic value in the owner's manual.",
    "Buffett's margin of safety principle guides the method.",
    "The central value of the distribution moves little.",
    "Intrinsic value at 2026 year-end is not published.",  # a year is not a price
    "Credit rating agencies rate the bonds A1.",
    "Value ranges live only in the private repository.",
])
def test_c_public_no_valuation_english_traps(ws, lint, text):
    """C-PUBLIC-NO-VALUATION: accounting fair value, principles and words without a number are not valuation wording."""
    story_line(ws, text)
    assert lint(ws, "C-PUBLIC-NO-VALUATION") == [], text


@pytest.mark.parametrize("text, flagged", [
    ("The P/E is 25x [src:ACME-RPT-2026-09#p5].", True),
    ("It trades at 25 times earnings.", True),
    ("The shares are below 1.2x book.", True),
    ("A price-to-earnings ratio of 18.", True),
    ("The price/earnings ratio is 18.5.", True),
    ("Its PE ratio is 22.", True),
    ("A market cap of $2.1 trillion [src:ACME-RPT-2026-09#p5].", True),
    ("An FCF yield of 3.5% [src:ACME-RPT-2026-09#p5].", True),
    ("A free-cash-flow yield of 4% [src:ACME-RPT-2026-09#p5].", True),
    ("We do not compare P/E ratios.", False),  # no number
    ("Market cap readings stay private as of September 30, 2026.", False),  # a date is not a quantity
    ("Market cap is covered in Section 12 of the method.", False),  # nor is a section number
    ("Berkshire repurchased shares at 1.3x book value [src:ACME-RPT-2026-09#p5].", False),  # the company's own buyback
])
def test_c_public_no_valuation_english_price_multiples(ws, lint, text, flagged):
    """C-PUBLIC-NO-VALUATION: an English price-derived multiple with a number in the same sentence."""
    story_line(ws, text)
    assert bool(lint(ws, "C-PUBLIC-NO-VALUATION")) is flagged, text


@pytest.mark.parametrize("sentence, quantity", [
    ("P/E of 25", True),
    ("as of September 30, 2026", False),
    ("as of 30 June 2026", False),
    ("in 3Q26 and 1H26", False),
    ("see Item 15 and Note 12", False),
])
def test_c_public_no_valuation_english_quantities(sentence, quantity):
    """C-PUBLIC-NO-VALUATION: English dates, periods and section numbers are not quantities."""
    assert has_quantity(sentence) is quantity


# --------------------------------------------------------------------------- 00 §H4 in English: advice
@pytest.mark.parametrize("text", [
    "We recommend buying ACME.",
    "Analysts recommend buying the stock.",
    "We recommend that investors sell.",
    "We recommend the shares.",
    "Our recommendation is to buy.",
    "Our advice is to trim the position.",
    "We rate ACME a buy.",
    "The stock is rated a Buy.",
    "Upgraded to Buy.",
    "We initiate coverage of ACME with a Buy.",
    "Rating: Buy",
    "A Buy-rated name.",
    "ACME is a buy.",
    "The shares remain a compelling buy.",
    "Investors should buy the stock.",
    "You should sell now.",
    "We should add to the position.",
    "Shareholders should trim our stake.",
    "The shares should be sold.",
    "ACME should be bought.",
    "Add to the position below $300.",
    "Trim our stake.",
    "Accumulate the position.",
    "Buy on dips.",
    "Buy the dip.",
    "Accumulate on weakness.",
    "ACME is our top pick.",
    "The stock is worth buying.",
    "Now is the time to buy.",
    "It is a good time to sell the shares.",
    "We recommend adding ACME.",
    "We recommend opening a position.",
    "Recommend closing the position.",
    "We strongly recommend ACME.",
    "We suggest trimming.",
])
def test_c_public_no_advice_english_wording_is_flagged(ws, lint, text):
    """C-PUBLIC-NO-ADVICE: English equivalents of the §H4 advice terms (recommend buying, rated a buy, should sell, ...)."""
    story_line(ws, text)
    assert lint(ws, "C-PUBLIC-NO-ADVICE"), text


@pytest.mark.parametrize("text", [
    "ACME's buybacks shrank the share count [src:ACME-RPT-2026-09#p5].",
    "The company should buy back more stock.",
    "Management recommends buying back shares.",
    "We recommend that the company buy back stock.",
    "The CEO said we should buy back shares.",
    "The board recommended selling the division.",
    "It is a good time to buy land for the new plant.",
    "Berkshire trimmed its position in Apple [src:ACME-RPT-2026-09#p5].",
    "Berkshire sold its stake in BYD [src:ACME-RPT-2026-09#p5].",
    "ACME built a strong position in Europe.",
    "Best Buy is a large customer.",
    "Buy with Prime lets shoppers check out on other sites.",
    "The Buy Box decides which seller gets the order.",
    "It is a buy-side firm.",
    "A buy order sits in the queue.",
    "Shoppers buy on promotion.",
    "Customers add to cart and pay later.",
    "Sell on Amazon charges a referral fee.",
    "Customers can buy directly from factories.",
    "Shoppers should buy early for Singles Day.",
    "We recommend reducing debt.",
    "We suggest adding a source tag to each sentence.",
    "The board recommended trimming costs.",
    "Temu wants to build a position in Europe.",
    "We recommend ACME's disclosure style to other issuers.",
])
def test_c_public_no_advice_english_traps(ws, lint, text):
    """C-PUBLIC-NO-ADVICE: buybacks, a company's own trades, product names and process wording are not advice."""
    story_line(ws, text)
    assert lint(ws, "C-PUBLIC-NO-ADVICE") == [], text


@pytest.mark.parametrize("text", [
    "We do not recommend buying or selling.",
    "We don't recommend selling.",
    "We would never rate it a buy.",
    "No investor should buy on the basis of this page.",
])
def test_c_public_no_advice_english_negative_sentences_still_fail(ws, lint, text):
    """C-PUBLIC-NO-ADVICE: as with the Chinese terms, a negative sentence is no exception (00 §H4)."""
    story_line(ws, text)
    assert lint(ws, "C-PUBLIC-NO-ADVICE"), text


@pytest.mark.parametrize("rel, text, check", [
    ("public/docs/STATUS.md", "- [x] Target price recorded.\n", "C-PUBLIC-NO-VALUATION"),
    ("public/CLAUDE.md", "Write the buy range into the letter.\n", "C-PUBLIC-NO-VALUATION"),
    ("public/zh-CN/docs/STATUS.md", "目标价已记录。\n", "C-PUBLIC-NO-VALUATION"),
    ("public/docs/STATUS.md", "- [ ] We recommend buying ACME.\n", "C-PUBLIC-NO-ADVICE"),
    ("public/CLAUDE.md", "Rating: Buy\n", "C-PUBLIC-NO-ADVICE"),
])
def test_c_public_no_valuation_and_advice_scan_status_and_claude_md(ws, lint, rel, text, check):
    """C-PUBLIC-NO-VALUATION, C-PUBLIC-NO-ADVICE: docs/STATUS.md and CLAUDE.md (and their Chinese versions) are scanned."""
    put(ws, rel, text)
    assert [f.file for f in lint(ws, check)] == [rel.split("/", 1)[1]]


@pytest.mark.parametrize("rel", ["public/docs/DESIGN.md", "public/docs/decisions/0010-price-grade-rubric.md",
                                 "public/constitution/owner.md", "public/docs/notes/STATUS.md"])
def test_c_public_no_valuation_rule_documents_may_name_the_terms(ws, lint, rel):
    """C-PUBLIC-NO-VALUATION: the documents that define the rules name the banned terms and are not scanned."""
    put(ws, rel, "Public files never state the target price, the buy range or a price grade (AXP: C per §V11).\n")
    assert lint(ws, "C-PUBLIC-NO-VALUATION") == [] and lint(ws, "C-PUBLIC-NO-ADVICE") == []


@pytest.mark.parametrize("text, flagged", [
    ("Grades recomputed with the §V11 mechanical scale (AXP B− → C, BRK B+ → B, the rest unchanged).", True),
    ("Valuation refresh: AXP: C, BRK: B.", True),
    ("After the price fell, AXP moved from B to C.", True),
    ("估值分档调整：AXP B− → C。", True),
    ("Business ratings: AXP B+ → A-, BRK A.", False),  # the public business rating uses the same letters
    ("Management rating AXP B → B+ although the price fell.", False),
    ("In Phase 0 only APP went through 16A → 04A → revision.", False),  # prompt ids, not grades
    ("SPGI upgraded the issuer from BBB to A- as bond prices rose.", False),  # a credit rating
    ("APP: A price event triggered the alert.", False),  # an article, not a grade
    ("AXP B− → C.", False),  # no word about prices or valuation
])
def test_c_public_no_valuation_price_grade_next_to_a_ticker(ws, lint, text, flagged):
    """C-PUBLIC-NO-VALUATION: a price grade next to a ticker in a sentence about prices or valuation (00 §H4)."""
    put(ws, "public/docs/STATUS.md", f"# Status\n\n- [x] {text}\n")
    assert bool(lint(ws, "C-PUBLIC-NO-VALUATION")) is flagged, text


def test_c_public_no_advice_english_in_readme(ws, lint):
    """C-PUBLIC-NO-ADVICE: README files anywhere are scanned for the English wording too."""
    put(ws, "public/agents/README.md", "Investors should buy the stock.\n")
    assert [f.file for f in lint(ws, "C-PUBLIC-NO-ADVICE")] == ["agents/README.md"]


def test_c_depends_english_first_person_holdings(ws, lint):
    """C-DEPENDS: "we hold ACME" in an industry module is a holding; "we hold that ..." is an opinion."""
    edit(ws, IND_README, "This module describes only the industry itself", "We hold ACME")
    assert lint(ws, "C-DEPENDS")
    edit(ws, IND_README, "We hold ACME", "We hold that the industry is concentrated")
    assert lint(ws, "C-DEPENDS") == []


def test_c_public_no_amounts_english_story_weight(ws, lint):
    """C-PUBLIC-NO-AMOUNTS: a two-minute story states no portfolio weight (SPEC 5)."""
    story_line(ws, "The portfolio weight is 15%.")
    assert lint(ws, "C-PUBLIC-NO-AMOUNTS")


# --------------------------------------------------------------------------- the two-minute story (SPEC 5)
def _story_with_words(ws: Path, n: int) -> None:
    text = (ws / STORY).read_text(encoding="utf-8")
    front = text[: text.index("# ACME")]
    words = " ".join(["word"] * (n - 2))
    (ws / STORY).write_text(front + f"# ACME\n\n{words} [src:ACME-RPT-2026-09#p1] [link](https://example.com/a/b/c).\n",
                            encoding="utf-8")


def test_c_story_english_word_limit(ws, lint):
    """C-STORY: an English story passes at 350 words and fails at 351; tags and link targets do not count."""
    _story_with_words(ws, 350)
    assert lint(ws, "C-STORY") == []
    _story_with_words(ws, 351)
    found = lint(ws, "C-STORY")
    assert len(found) == 1 and "351 words" in found[0].message and "limit 350" in found[0].message


def test_c_story_language_decides_the_measure():
    """C-STORY: a story is measured in characters when it has at least as many CJK letters as English words."""
    english = "# ACME\n\nACME sells small parts [src:ACME-RPT-2026-09#p5]. See [notes](../x.md).\n"
    assert story_words(english) == 7 and not story_is_cjk(english)
    assert story_is_cjk("# 标题\n\nACME 卖的是小部件，FY2026 毛利率 62%。")
    assert not story_is_cjk(english + "中文\n")  # a stray Chinese word does not make an English story Chinese


def test_c_story_english_story_in_the_example(ws, lint):
    """C-STORY: the bundled English story is well under the word limit."""
    body = (ws / STORY).read_text(encoding="utf-8").split("---\n", 2)[2]
    assert 20 < story_words(body) < 350 and lint(ws, "C-STORY") == []


# --------------------------------------------------------------------------- zh-CN/ and C-LANGUAGE (SPEC 8.5)
def test_c_language_clean_example_passes_on_both_sides(ws, lint):
    """C-LANGUAGE: the example archive is English; its zh-CN/ story and title_original are exempt."""
    assert "两分钟故事" in (ws / ZH_STORY).read_text(encoding="utf-8")  # the exemption is exercised
    assert lint(ws, "C-LANGUAGE") == [] and lint(ws, "C-LANGUAGE", "private") == []


def test_c_language_one_finding_per_file_at_the_first_line(ws, lint):
    """C-LANGUAGE: CJK text in an English file is one error at its first line, with the number of lines."""
    edit(ws, STORY, "# ACME: two-minute story", "# ACME：两分钟故事")
    story_line(ws, "中文")
    found = lint(ws, "C-LANGUAGE")
    assert [(f.file, f.line, f.level) for f in found] == [("companies/ACME/story.md", 8, "error")]
    assert "2 line(s)" in found[0].message and "zh-CN/companies/ACME/story.md" in found[0].message


@pytest.mark.parametrize("text", [
    "Notes，more notes",  # full-width comma
    "Revenue grew 16％ [src:X]",  # full-width percent sign
    "カタカナ",  # Japanese kana
    "한국어",  # Korean hangul
    "Tab　stop",  # ideographic space
])
def test_c_language_cjk_characters(ws, lint, text):
    """C-LANGUAGE: CJK punctuation, full-width forms, kana and hangul count as CJK text."""
    put(ws, "public/docs/notes.md", text + "\n")
    assert [f.file for f in lint(ws, "C-LANGUAGE")] == ["docs/notes.md"]


@pytest.mark.parametrize("rel", [
    "public/zh-CN/letters/2026-09.md",
    "public/tests/test_parse.py",
    "public/pipeline/tests/data/filing.txt",
    "public/fixtures/report.md",
    "public/pipeline/test_extract.py",
    "public/pipeline/extract_test.py",
    "public/conftest.py",
])
def test_c_language_exempt_paths(ws, lint, rel):
    """C-LANGUAGE: zh-CN/, tests and fixtures may contain Chinese text."""
    put(ws, rel, "营收增长 16%。\n")
    assert lint(ws, "C-LANGUAGE") == []


def test_c_language_a_run_s_inputs_keep_their_language_and_its_outputs_do_not(ws, lint):
    """C-LANGUAGE: a pipeline run's inputs/ (a slice's too) are verbatim copies of its sources and keep their language;
    what the run wrote, and inputs/ anywhere else, are English like everything else."""
    put(ws, "private/runs/SPGI/2026-09-28-14Q/inputs/dossier.txt", "完整企业报告\n")
    put(ws, "private/runs/AXP/2026-09-27-04A/slices/s01/inputs/sources.txt", "营收\n")
    put(ws, "private/runs/SPGI/2026-09-28-15A/outputs/prereg.yml", "note: 营收\n")
    put(ws, "private/inputs/notes.md", "营收\n")
    found = sorted(f.file for f in lint(ws, "C-LANGUAGE", side="private"))
    assert found == ["inputs/notes.md", "runs/SPGI/2026-09-28-15A/outputs/prereg.yml"]


def test_c_language_nested_zh_cn_is_not_exempt(ws, lint):
    """C-LANGUAGE: only the zh-CN/ directory at the repository root holds the Chinese versions."""
    put(ws, "public/docs/zh-CN/DESIGN.md", "设计\n")
    assert [f.file for f in lint(ws, "C-LANGUAGE")] == ["docs/zh-CN/DESIGN.md"]


def test_c_language_title_original(ws, lint):
    """C-LANGUAGE: title_original in a sources.yml may quote a Chinese title; title, notes and comments may not."""
    assert "title_original" in (ws / SOURCES).read_text(encoding="utf-8")
    edit(ws, SOURCES, "title_original: ACME 公司报告（虚构）", "title_original: |\n      ACME 公司报告\n      （虚构）")
    assert lint(ws, "C-LANGUAGE") == []
    edit(ws, SOURCES, "    primary: false\n  - tag: ACME-10K-FY2026", "    primary: false  # 备注\n  - tag: ACME-10K-FY2026")
    found = lint(ws, "C-LANGUAGE")
    assert len(found) == 1 and "title_original" in found[0].message


def test_c_language_title_original_alias_is_not_an_exemption(ws, lint):
    """C-LANGUAGE: title_original: *alias does not exempt the anchored text elsewhere in the file."""
    edit(ws, SOURCES, "    title: ACME company report (in Chinese, fictitious)\n    title_original: ACME 公司报告（虚构）\n",
         "    title: &t ACME 公司报告\n    title_original: *t\n")
    assert lint(ws, "C-LANGUAGE")


def test_c_language_title_original_only_in_sources_yml(ws, lint):
    """C-LANGUAGE: title_original is exempt in a sources.yml only."""
    put(ws, "public/companies/ACME/updates/2026-10.yml", "title_original: 季度更新\n")
    assert lint(ws, "C-LANGUAGE")


def test_c_language_private_archive_and_binary_files(ws, lint):
    """C-LANGUAGE: runs on the private archive too; binary files are skipped."""
    edit(ws, BUY_MEMO, "summary: Build the position in one order (fictitious).", "summary: 一次下单建仓。")
    (ws / "private" / "reports").mkdir()
    (ws / "private" / "reports" / "ACME.pdf").write_bytes("%PDF-1.7 中文".encode("utf-8"))
    assert [f.file for f in lint(ws, "C-LANGUAGE", "private")] == ["memos/2026-09-20-ACME-entry.yml"]


def test_c_schema_title_original_is_a_string(ws, lint):
    """C-SCHEMA: sources.yml entries accept an optional string title_original."""
    assert lint(ws, "C-SCHEMA") == []
    edit(ws, SOURCES, "title_original: ACME 公司报告（虚构）", "title_original: [ACME]")
    assert any("title_original" in f.message for f in lint(ws, "C-SCHEMA"))


def test_c_src_tag_chinese_version_resolves_tags_like_the_english_file(ws, lint):
    """C-SRC-TAG: a zh-CN/ story is archive content; its tags resolve through companies/ACME/sources.yml."""
    assert lint(ws, "C-SRC-TAG") == []
    edit(ws, ZH_STORY, "[src:ACME-RPT-2026-09#p4]", "[src:NOPE-2026#p4]")
    found = lint(ws, "C-SRC-TAG")
    assert [f.file for f in found] == ["zh-CN/companies/ACME/story.md"] and "NOPE-2026" in found[0].message


def test_c_public_no_advice_chinese_version_is_public_content(ws, lint):
    """C-PUBLIC-NO-ADVICE: the Chinese version of a letter under zh-CN/ is public content."""
    put(ws, "public/zh-CN/letters/2026-09.md", "> 中文版。英文原文：[letters/2026-09.md](../../letters/2026-09.md)\n\n建议买入。\n")
    assert [f.file for f in lint(ws, "C-PUBLIC-NO-ADVICE")] == ["zh-CN/letters/2026-09.md"]


def test_c_public_no_valuation_chinese_version_is_public_content(ws, lint):
    """C-PUBLIC-NO-VALUATION: valuation wording in a zh-CN/ story is an error; zh-CN/docs/ is not content."""
    put(ws, "public/zh-CN/docs/DESIGN.md", "价值区间与目标价只放在私有仓库。\n")
    assert lint(ws, "C-PUBLIC-NO-VALUATION") == []
    edit(ws, ZH_STORY, "最可能错在哪", "目标价尚未确定。最可能错在哪")
    assert [f.file for f in lint(ws, "C-PUBLIC-NO-VALUATION")] == ["zh-CN/companies/ACME/story.md"]


def test_c_depends_chinese_version_of_a_module(ws, lint):
    """C-DEPENDS: the Chinese version of an industry module stays neutral too."""
    put(ws, "public/zh-CN/industries/widgets/README.md", "# 小部件\n\n我们持有 ACME。\n")
    assert [f.file for f in lint(ws, "C-DEPENDS")] == ["zh-CN/industries/widgets/README.md"]


def test_c_constitution_map_reads_english_rule_references():
    """C-CONSTITUTION-MAP: spec/checks.yml ties checks to constitution rules as "Constitution rule N"."""
    assert constitution_checks() == {
        1: ["C-RATING-ORDER"], 2: ["C-TESTS-COVERAGE"], 3: ["C-TESTS-CAPALLOC"], 4: ["C-CONCENTRATION"],
        5: ["C-DISCOUNT-RATE"], 6: ["C-SELL-REASONS"], 7: ["C-HURDLE"], 8: ["C-SINGLE-ORDER"],
    }


def test_c_language_registered_both_error():
    """C-LANGUAGE: registered in spec/checks.yml for both archives as an error, and documented in SPEC.md."""
    from thesis_ci import contract

    meta = contract.check_meta("C-LANGUAGE")
    assert (meta["scope"], meta["level"]) == ("both", "error")
    assert "C-LANGUAGE" in (contract.spec_dir() / "SPEC.md").read_text(encoding="utf-8")
    report = engine.run(Path(selftest.FIXTURE) / "public", None, selftest.TODAY, only=["C-LANGUAGE"])
    assert report.checks_run == ["C-LANGUAGE"] and report.findings == []


@pytest.mark.parametrize("note, levels", [
    ("one order, without tranches", []),
    ("we will not scale in", []),
    ("build it in two tranches", ["error"]),
])
def test_c_single_order_english_negation(ws, lint, note, levels):
    """C-SINGLE-ORDER: English tranche wording counts unless a negation comes right before it."""
    edit(ws, BUY_MEMO, "order: {type: single}", f"order: {{type: single, note: '{note}'}}")
    assert [f.level for f in lint(ws, "C-SINGLE-ORDER", "private")] == levels


def test_sentences_report_the_line_where_a_sentence_starts():
    """C-SRC-TAG: a sentence spanning lines is reported at its first line."""
    assert [line for line, _s in sentences("Intro.\n\nRevenue grew\n16% [src:A#p1]. End.")] == [1, 3, 4]


def test_a_forecast_in_the_probability_language_needs_no_tag():
    """C-SRC-TAG: "It is likely (0.65) that ... at least 4%" is a judgment written in advance, not a fact (SPEC 3.1)."""
    assert untagged_facts("It is likely (0.65) that sales grow by at least 4% in FY2027.") == []
    assert untagged_facts("It is very unlikely (10%) that margins fall below 40%.") == []
    assert len(untagged_facts("Sales are likely to grow 4% next year.")) == 1  # no stated probability: tag it


def test_a_semicolon_inside_parentheses_does_not_end_the_sentence():
    text = ("Capital expenditure exceeded depreciation by $47.3bn ($156.2bn against $109.0bn for 2016–2025; "
            "[src:X-10K-FY2025#p40]).\n")
    assert untagged_facts(text) == []
    assert len(untagged_facts("Revenue was $5bn; costs were $3bn [src:X-10K-FY2025].\n")) == 1  # outside parentheses
