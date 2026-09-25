"""Chinese text keeps being checked after the example archive went English (thesis-ci 0.3.0).

The archives are English-first, but Chinese text remains in their zh-CN/ versions, in archives that are still being
translated, and in quoted sources. These cases fed Chinese into the example archive before 0.3.0 (most were selftest
cases); they now write the Chinese inline. Each test's docstring names the check it covers.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from thesis_ci import selftest
from thesis_ci.selftest import Case, replace, write

PUB, PRIV = selftest.PUB, selftest.PRIV
STORY = selftest.STORY
ZH_STORY = selftest.ZH_STORY
ZH_END = "最可能错在哪"  # the Chinese story's last sentence begins with these words
THESIS = selftest.THESIS
INDUSTRY = selftest.INDUSTRY
BUY_MEMO = selftest.BUY_MEMO
UPDATE = selftest.UPDATE


def before_zh_end(text: str) -> tuple:
    return replace(ZH_STORY, ZH_END, text + ZH_END)


CHINESE_CASES: tuple[Case, ...] = (
    Case("C-SRC-TAG", PUB, (before_zh_end("营收增长 16%。"),), "untagged fact sentence in the Chinese story"),
    Case("C-SRC-TAG", PUB, (write("public/letters/2026-10.md", "# 2026 年 10 月股东信\n\n本月模型费用 3 美元，低于预算。\n"),),
         "untagged number in a Chinese letter"),
    Case("C-SRC-TAG", PUB, (before_zh_end("Revenue grew 16 percent。"),), "untagged English unit before a Chinese full stop"),
    Case("C-SRC-TAG", PUB, (write("public/mistakes.md", "# 错误清单\n\n核销率写成 2.5%，实为 2.0%。\n"),), "untagged Chinese mistakes.md"),
    Case("C-SRC-FACT", PUB, (replace(THESIS, "  summary: The leading maker", "  summary: 经常性收入占比 60%。The leading maker"),),
         "untagged Chinese fact in summary"),
    Case("C-PUBLIC-NO-VALUATION", PUB, (before_zh_end("目标价尚未确定。"),), "price-range wording in the Chinese story"),
    Case("C-PUBLIC-NO-VALUATION", PUB, (before_zh_end("市盈率 25 倍[src:ACME-RPT-2026-09#p5]。"),),
         "price-derived multiple with a number in Chinese"),
    Case("C-PUBLIC-NO-VALUATION", PUB, (write("public/mistakes.md", "# 错误清单\n\n上一版把价值中枢写进了公开文件。\n"),),
         "Chinese valuation wording in mistakes.md"),
    Case("C-PUBLIC-NO-ADVICE", PUB, (before_zh_end("建议买入。"),), "advice wording in the Chinese story"),
    Case("C-PUBLIC-NO-ADVICE", PUB, (write(f"{UPDATE}.md", "结论：建议减仓。\n"),), "建议减仓 in an update"),
    Case("C-PUBLIC-NO-ADVICE", PUB, (write(f"{UPDATE}.md", "这改变论点吗？不改变，建议加仓。\n"),), "建议加仓 in an update"),
    Case("C-PUBLIC-NO-AMOUNTS", PUB, (replace(selftest.LETTER, "below budget.", "below budget.\n账户 U12345678 低于预算。"),),
         "account number in Chinese prose"),
    Case("C-PUBLIC-NO-AMOUNTS", PUB, (replace(selftest.LETTER, "below budget.", "below budget.\n我们的仓位 15%。"),),
         "position in a letter, in Chinese"),
    Case("C-NO-PRICE-FEED", PUB, (before_zh_end("现价 $350[src:ACME-RPT-2026-09#p5]。"),), "share price in the Chinese story"),
    Case("C-DEPENDS", PUB, (replace(selftest.IND_README, "This module describes only the industry itself", "ACME 是我们的持仓"),),
         "holding in module, in Chinese"),
    Case("C-DEPENDS", PUB, (replace(selftest.IND_README, "This module describes only the industry itself", "我们持有 ACME"),),
         "我们持有 in module"),
    Case("C-DEPENDS", PUB, (replace(INDUSTRY, "implication: Pricing power weakens", "implication: 定价权减弱，建议减持"),),
         "advice in module, in Chinese"),
    Case("C-SINGLE-ORDER", PRIV, (replace(BUY_MEMO, "order: {type: single}", "order: {type: single, note: 分两批建仓}"),),
         "two tranches in the order note, in Chinese"),
)


@pytest.mark.parametrize("case", CHINESE_CASES, ids=[f"{c.check}:{c.why}" for c in CHINESE_CASES])
def test_chinese_violation_is_flagged(case, tmp_path, lint):
    """Every former Chinese selftest case (C-SRC-TAG, C-PUBLIC-NO-ADVICE, C-DEPENDS, ...) is still flagged."""
    ws = selftest.materialize(tmp_path / "ws", case.ops)
    assert lint(ws, case.check, case.target, case.counterpart)


def test_c_story_chinese_story_keeps_the_character_limit(ws, lint):
    """C-STORY: a story written in Chinese is measured in characters: 700 pass, 701 fail."""
    text = (ws / STORY).read_text(encoding="utf-8")
    front = text[: text.index("# ACME")]
    body = ("字" * 70 + "[src:ACME-RPT-2026-09#p1]\n") * 10
    (ws / STORY).write_text(front + body, encoding="utf-8")
    assert lint(ws, "C-STORY") == []
    (ws / STORY).write_text(front + body + "长", encoding="utf-8")
    found = lint(ws, "C-STORY")
    assert len(found) == 1 and "701 characters" in found[0].message


def test_c_depends_chinese_holding_company_is_an_ordinary_word(ws, lint):
    """C-DEPENDS: 控股公司 (a holding company) is an ordinary word in a module."""
    selftest.apply(ws, (replace(selftest.IND_README, "This module describes only the industry itself", "多家为控股公司"),))
    assert lint(ws, "C-DEPENDS") == []


def test_chinese_version_of_the_story_passes_every_check(ws):
    """C-SRC-TAG, C-PUBLIC-NO-ADVICE, C-LANGUAGE: the verbatim Chinese story under zh-CN/ is clean."""
    from thesis_ci import engine

    text = (ws / ZH_STORY).read_text(encoding="utf-8")
    assert text.split("---\n")[2].startswith("> 中文版。英文原文：[companies/ACME/story.md](../../../companies/ACME/story.md)")
    report = engine.run(ws / "public", ws / "private", selftest.TODAY)
    assert report.findings == []
    assert Path(ws / "public" / "companies" / "ACME" / "story.md").read_text(encoding="utf-8").count(
        "A Chinese version is in [zh-CN/companies/ACME/story.md](../../zh-CN/companies/ACME/story.md).") == 1
