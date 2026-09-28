"""C-LANGUAGE: the archives are English-first, so an English file contains no Chinese, Japanese or Korean text.

The Chinese version of a key document lives at zh-CN/<same path> (SPEC 8.5). Everything else is English, with three
exemptions: tests and fixtures, which may exercise Chinese text; the ``title_original`` field of a sources.yml entry,
which quotes a source's title in its own language (``title`` carries the English translation); and the inputs of a
pipeline run (``runs/**/inputs/``), which are verbatim copies of the sources a step read, in their own language.
"""

from __future__ import annotations

from fnmatch import fnmatchcase
from typing import Iterator

import yaml

from ..engine import Context, Issue, check
from ..repo import ZH_DIR
from ..textscan import CJK_RE, snippet

TEST_DIRS = frozenset({"tests", "test", "fixtures"})
TEST_FILES = ("test_*.py", "*_test.py", "conftest.py")
ORIGINAL_TITLE_KEY = "title_original"
RUNS_DIR, RUN_INPUTS_DIR = "runs", "inputs"  # runs/<scope>/<run>/inputs/ (and slices/<id>/inputs/): source copies


def language_exempt(rel: str) -> bool:
    """True for the Chinese versions under zh-CN/, for tests and fixtures, and for a run's copies of its sources."""
    parts = rel.split("/")
    if parts[0] == ZH_DIR or any(part in TEST_DIRS for part in parts[:-1]):
        return True
    if parts[0] == RUNS_DIR and RUN_INPUTS_DIR in parts[1:-1]:
        return True
    return any(fnmatchcase(parts[-1], pattern) for pattern in TEST_FILES)


def original_title_spans(text: str) -> list[tuple[int, int]]:
    """(start, end) offsets of every title_original value in a sources.yml; [] when the file does not parse.

    Only a value written after its key counts: an alias (title_original: *x) would otherwise exempt the text of
    the anchored value elsewhere in the file.
    """
    spans: list[tuple[int, int]] = []
    try:
        for root in yaml.compose_all(text, Loader=yaml.SafeLoader):
            stack = [root] if root is not None else []
            while stack:
                node = stack.pop()
                if isinstance(node, yaml.MappingNode):
                    for key, value in node.value:
                        if (isinstance(key, yaml.ScalarNode) and key.value == ORIGINAL_TITLE_KEY
                                and value.start_mark.index >= key.end_mark.index):
                            spans.append((value.start_mark.index, value.end_mark.index))
                        else:
                            stack.append(value)
                elif isinstance(node, yaml.SequenceNode):
                    stack.extend(node.value)
    except yaml.YAMLError:
        return []  # a syntax error is C-SCHEMA's to report; nothing is exempt
    return spans


def cjk_lines(text: str, exempt: list[tuple[int, int]] = ()) -> list[tuple[int, str]]:
    """(line number, excerpt around the first CJK character) of every line with CJK text outside the exempt spans."""
    out = []
    offset = 0
    for number, line in enumerate(text.split("\n"), 1):
        for m in CJK_RE.finditer(line):
            pos = offset + m.start()
            if not any(start <= pos < end for start, end in exempt):
                out.append((number, line[max(0, m.start() - 15): m.start() + 35]))
                break
        offset += len(line) + 1
    return out


@check("C-LANGUAGE")
def c_language(ctx: Context) -> Iterator[Issue]:
    repo = ctx.repo
    for path in repo.all_files:
        rel = repo.rel(path)
        if language_exempt(rel):
            continue
        text = repo.text(path)
        if not text or not CJK_RE.search(text):
            continue
        sources = path.name == "sources.yml"
        lines = cjk_lines(text, original_title_spans(text) if sources else [])
        if not lines:
            continue
        number, excerpt = lines[0]
        where = ("a source's title in its original language goes in title_original" if sources
                 else f"a Chinese version goes in {ZH_DIR}/{rel}")
        yield Issue(path, f"CJK text on {len(lines)} line(s), first: '{snippet(excerpt.strip(), 50)}'; files outside "
                          f"{ZH_DIR}/ are English ({where})", number)
