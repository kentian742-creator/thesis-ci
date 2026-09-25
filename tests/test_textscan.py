"""Source-tag and fact-number rules (SPEC 3.1 and 3.4) used by C-SRC-TAG and C-SRC-FACT."""

from __future__ import annotations

import pytest

from thesis_ci.textscan import FACT_RE, TAG_RE, mask, source_tags, split_front_matter, story_length, untagged_facts

NOT_FACTS = [
    "2026 年",
    "2026年9月",
    "FY2026",
    "FY2027 的目标",
    "截至 2026-09-24",
    "Q2",
    "2026Q2 财报",
    "## 3. 护城河",
    "1. 第一条",
    "第 12 节",
    "12 个维度",
    "Item 7 与 Item 8",
    "10-K、10-Q、8-K、20-F",
    "S&P 500 指数",
    "Windows 11",
]
FACTS = [
    "16%",
    "$495",
    "$ 12",
    "1,020 亿美元",
    "1.04×",
    "45 个百分点",
    "10％",
    "3 bp",
    "30 bps",
    "5pp",
    "12 倍",
    "2 万",
    "5 千万",
    "3 百万",
    "8 美分",
    "7 元",
    "20 million",
    "3.5 billion",
    "4 bn",
    "25 基点",
]


@pytest.mark.parametrize("text", NOT_FACTS)
def test_c_src_tag_dates_years_quarters_and_section_numbers_are_not_facts(text):
    """C-SRC-TAG: years, dates, quarters, FY labels and section numbers never need a tag."""
    assert FACT_RE.search(text) is None
    assert untagged_facts(text) == []


@pytest.mark.parametrize("text", FACTS)
def test_c_src_tag_fact_numbers_need_a_tag(text):
    """C-SRC-TAG: amounts, percentages, multiples and basis points need a tag."""
    assert FACT_RE.search(text)
    assert len(untagged_facts(f"收入 {text}。")) == 1
    assert untagged_facts(f"收入 {text}[src:ACME-RPT-2026-09#p3]。") == []


def test_tag_regex_matches_spec():
    m = TAG_RE.search("x [src:MSFT-10K-FY2026#Item7] y")
    assert m.group(1) == "MSFT-10K-FY2026" and m.group(2) == "Item7"
    assert TAG_RE.search("[src:MSFT-RPT-2026-09]").group(2) is None
    assert TAG_RE.search("[src:AXP-CALL-2026Q2#MD&A]").group(2) == "MD&A"
    assert TAG_RE.search("[src: MSFT]") is None
    assert TAG_RE.search("[src:msft]") is None


def test_sentence_split_on_chinese_punctuation_and_newline():
    text = "营收 16%[src:A#p1]。利润 20%。\n现金 $5 亿[src:A#p2]；负债 3 亿！"
    found = untagged_facts(text)
    assert [(line, number) for line, _s, number in found] == [(1, "20%"), (2, "3 亿")]


def test_tag_after_the_full_stop_belongs_to_the_next_sentence():
    assert len(untagged_facts("营收增长 16%。[src:A#p1]")) == 1


def test_code_links_and_front_matter_are_ignored():
    text = (
        "---\nweight: 15%\n---\n"
        "见 `16%` 与 ``20%``。\n"
        "```\n增长 30%\n```\n"
        "[报告](https://example.com/a?share=45%25) 与 <https://x.org/10%> 以及 https://y.org/5%\n"
        "[ref]: https://z.org/7%\n"
    )
    assert untagged_facts(text) == []


def test_mask_keeps_line_numbers():
    text = "---\na: 1\n---\n```\nx 5%\n```\n收入 7%\n"
    assert len(mask(text)) == len(text)
    assert untagged_facts(text) == [(7, "收入 7%", "7%")]


def test_malformed_tags_are_reported():
    tags = source_tags("见 [src:ACME-RPT#p1] 与 [src: bad] 与 `[src:IGNORED]`")
    assert [(tag, raw) for _line, tag, raw in tags] == [("ACME-RPT", "[src:ACME-RPT#p1]"), (None, "[src: bad]")]


def test_c_story_length_excludes_tags_markup_and_links():
    """C-STORY: the 700-character limit counts prose only."""
    body = "# 标题\n\n**加粗**[src:ACME-RPT-2026-09#p1] [链接](https://example.com/very/long/url)\n- 列表\n"
    assert story_length(body) == len("标题加粗链接列表")


def test_split_front_matter():
    fm, body = split_front_matter("---\ncompany: ACME\n---\n正文\n")
    assert fm == "company: ACME\n" and body == "正文\n"
    assert split_front_matter("正文") == (None, "正文")
