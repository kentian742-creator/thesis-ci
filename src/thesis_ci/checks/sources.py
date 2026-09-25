"""Provenance checks: C-SRC-TAG (Markdown), C-SRC-FACT (YAML), C-SRC-ACCESSION (sources.yml)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterator

from ..engine import Context, Issue, check
from ..repo import Repo, is_yaml, walk_items
from ..textscan import snippet, source_tags, untagged_facts

# Markdown under these top-level directories is archive content (facts need tags).
ARCHIVE_DIRS = ("companies", "industries", "letters")
# Root-level archive Markdown: the public mistakes list says its fact numbers carry [src:] tags as usual.
ARCHIVE_ROOT_FILES = ("mistakes.md",)
MARKDOWN_SUFFIXES = (".md", ".markdown")
# Any YAML under these directories: a `source` key is a source tag (SPEC 3.1) and must resolve.
SOURCE_KEY_DIRS = ("companies", "industries")

# YAML files whose free text is scanned for fact numbers. (Pre-registrations are predictions, not facts: only
# their source fields are checked, like every other YAML file under companies/ and industries/.)
FACT_FILES = (
    "companies/*/thesis.yml",
    "companies/*/ledger.yml",
    "companies/*/valuation.yml",
    "industries/*/industry.yml",
)

FREE_TEXT_KEYS = frozenset(
    {"claim", "summary", "category_rationale", "implication", "observable", "title", "note", "statement", "label"}
)
FREE_TEXT_LISTS = frozenset({"permanent_loss_paths", "structure"})
# Pre-registered criteria are thresholds, not facts; definitions and to-do notes are not facts either.
EXEMPT_KEYS = frozenset({"fail_if", "warn_if", "threshold", "question", "rule", "warn_rule", "metric_def", "params", "todo"})
SOURCE_KEYS = frozenset({"source", "settlement_source", "acknowledged_source"})
# 00 §E1: pre-registered predictions need no tag. In ledger.yml the system's and the owner's entries are predictions
# (their criterion is in `note`); only the management side records facts.
PREDICTION_SIDES = frozenset({"system", "owner"})


def dotted(path: tuple) -> str:
    out = ""
    for part in path:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out


def prose_issues(
    repo: Repo, path: Path, text: str, markdown: bool, line: Callable[[int], int | None], label: str = ""
) -> Iterator[Issue]:
    known = repo.known_tags(path)
    for n, tag, raw in source_tags(text, markdown):
        if tag is None:
            yield Issue(path, f"{label}malformed source tag {raw}", line(n))
        elif tag not in known:
            yield Issue(path, f"{label}source tag {tag} is not in the applicable sources.yml", line(n))
    for n, sentence, number in untagged_facts(text, markdown):
        yield Issue(path, f"{label}fact number '{number}' has no [src:] tag in its sentence: {snippet(sentence)}", line(n))


@check("C-SRC-TAG")
def c_src_tag(ctx: Context) -> Iterator[Issue]:
    repo = ctx.repo
    for path in repo.all_files:
        rel = repo.rel(path)
        in_archive = ("/" in rel and rel.split("/")[0] in ARCHIVE_DIRS) or rel in ARCHIVE_ROOT_FILES
        if path.suffix.lower() not in MARKDOWN_SUFFIXES or not in_archive:
            continue
        text = repo.text(path)
        if text:
            yield from prose_issues(repo, path, text, True, lambda n: n)


def free_text(data: Any, path: tuple = ()) -> Iterator[tuple[tuple, str]]:
    """(path, text) for free-text fields, skipping criteria subtrees."""
    if isinstance(data, dict):
        for key, value in data.items():
            if key in EXEMPT_KEYS:
                continue
            here = path + (key,)
            if key in FREE_TEXT_KEYS and isinstance(value, str):
                yield here, value
            elif key in FREE_TEXT_LISTS and isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, str):
                        yield here + (i,), item
            else:
                yield from free_text(value, here)
    elif isinstance(data, list):
        for i, value in enumerate(data):
            yield from free_text(value, path + (i,))


@check("C-SRC-FACT")
def c_src_fact(ctx: Context) -> Iterator[Issue]:
    repo = ctx.repo
    # Source fields resolve in every YAML document under companies/ and industries/, not only in the files
    # that have a schema: an update record or a second document of a stream cites sources too.
    for path in repo.all_files:
        rel = repo.rel(path)
        if not (is_yaml(path) and "/" in rel and rel.split("/")[0] in SOURCE_KEY_DIRS and path.name != "sources.yml"):
            continue
        known = repo.known_tags(path)
        for doc in repo.data_docs(path):
            for where, key, value in walk_items(doc.data):
                if key in SOURCE_KEYS and isinstance(value, str) and value.split("#", 1)[0].strip() not in known:
                    yield Issue(path, f"{dotted(where)}: source {value!r} is not in the applicable sources.yml", doc.line(*where))
    for pattern in FACT_FILES:
        for path in repo.files(pattern):
            doc = repo.doc(path)
            if doc.error or doc.data is None:
                continue  # reported by C-SCHEMA
            ledger = path.name == "ledger.yml"
            for where, text in free_text(doc.data):
                if ledger and _prediction(doc.data, where):
                    continue
                line = doc.line(*where)
                yield from prose_issues(repo, path, text, False, lambda _n, line=line: line, f"{dotted(where)}: ")


def _prediction(data: Any, where: tuple) -> bool:
    """True for the statement or note of a system / owner ledger entry (a prediction, not a fact)."""
    if len(where) != 3 or where[0] != "entries" or where[2] not in ("statement", "note"):
        return False
    entries = data.get("entries") if isinstance(data, dict) else None
    entry = entries[where[1]] if isinstance(entries, list) and isinstance(where[1], int) else None
    return isinstance(entry, dict) and entry.get("side") in PREDICTION_SIDES


@check("C-SRC-ACCESSION")
def c_src_accession(ctx: Context) -> Iterator[Issue]:
    repo = ctx.repo
    for path in repo.files("**/sources.yml"):
        doc = repo.doc(path)
        entries = doc.mapping.get("sources")
        for i, entry in enumerate(entries if isinstance(entries, list) else []):
            if isinstance(entry, dict) and entry.get("kind") == "filing" and not entry.get("accession"):
                yield Issue(
                    path,
                    f"filing source {entry.get('tag')} has no EDGAR accession yet (track it in docs/STATUS.md)",
                    doc.line("sources", i),
                )
