"""Governance checks: pipeline-maintained trust levels, frozen test thresholds, prompt input isolation (00 §G)."""

from __future__ import annotations

import datetime as dt
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterator

import yaml

from ..engine import Context, Issue, check
from ..periods import in_force_for
from ..repo import Doc, Repo, is_yaml, jsonable
from .constitution import TICKER_RE
from .thesis_tests import tests_of, theses

# -- C-TRUST-WRITE ------------------------------------------------------------------------------------------
TRUST_FILE = "trust/levels.yml"


def trust_levels(data: Any) -> tuple[dict, dict] | None:
    """(companies, industries) from trust/levels.yml; None when the file has neither.

    SPEC 4.2: ``companies: {TICKER: level}`` and ``industries: {id: level}``; tickers at the top level are read
    as companies too.
    """
    if not isinstance(data, dict):
        return None
    companies = data.get("companies")
    if not isinstance(companies, dict):
        companies = {k: v for k, v in data.items() if isinstance(k, str) and TICKER_RE.match(k)}
    industries = data.get("industries") if isinstance(data.get("industries"), dict) else {}
    if not companies and not industries:
        return None
    return companies, industries


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


def update_records(repo: Repo, company_dir: Path) -> Iterator[tuple[Path, dict]]:
    """(path, header) of each update: the front matter of updates/*.md, or the mapping of updates/*.yml."""
    for path in repo.files(f"{repo.rel(company_dir)}/updates/*"):
        if path.suffix.lower() in (".md", ".markdown"):
            doc = repo.front_matter(path)
            header = doc.mapping if doc is not None and not doc.error else {}
        elif is_yaml(path):
            header = repo.doc(path).mapping
        else:
            continue
        if header:
            yield path, header


@check("C-TRUST-WRITE")
def c_trust_write(ctx: Context) -> Iterator[Issue]:
    repo = ctx.repo
    path = repo.root / TRUST_FILE
    if path.is_file():
        doc = repo.doc(path)
        levels = None if doc.error else trust_levels(doc.data)
        if levels is None:
            yield Issue(path, "trust/levels.yml cannot be read: expected companies: {TICKER: level} "
                              "(and industries: {id: level})", doc.error_line or doc.line())
        else:
            companies, industries = levels
            for tpath, tdoc, data in theses(repo):
                ticker = str(data.get("company") or tpath.parent.name)
                have, want = data.get("trust_level"), companies.get(ticker)
                if want is None:
                    yield Issue(tpath, f"trust/levels.yml has no level for {ticker}; the pipeline records every "
                                       "company manager's level there", tdoc.line("trust_level"))
                elif have != want:
                    yield Issue(tpath, f"trust_level {have!r} differs from trust/levels.yml ({want!r}); the pipeline "
                                       "maintains trust levels, a company manager never edits them (§G8)",
                                tdoc.line("trust_level"))
            for ipath in repo.files("industries/*/industry.yml"):
                idoc = repo.doc(ipath)
                module = str(idoc.mapping.get("id") or ipath.parent.name)
                have, want = idoc.mapping.get("trust_level"), industries.get(module)
                if have is not None and want is not None and have != want:
                    yield Issue(ipath, f"trust_level {have!r} differs from trust/levels.yml ({want!r}); the pipeline "
                                       "maintains trust levels (§G8)", idoc.line("trust_level"))
    # §G8: a reviewed date moves only for the sections this update actually reviewed, and they are listed.
    for company_dir in repo.company_dirs():
        tpath = company_dir / "thesis.yml"
        if not tpath.is_file():
            continue
        tdoc = repo.doc(tpath)
        reviewed = tdoc.mapping.get("reviewed")
        if not isinstance(reviewed, dict):
            continue
        listed: dict[dt.date, tuple[set[str], list[str]]] = {}
        for upath, header in update_records(repo, company_dir):
            sections, as_of = header.get("reviewed_sections"), _date(header.get("as_of"))
            if not isinstance(sections, list) or as_of is None:
                continue
            names, files = listed.setdefault(as_of, (set(), []))
            names.update(str(s) for s in sections)
            files.append(upath.name)
        for key, value in reviewed.items():
            day = _date(value)
            if day in listed and str(key) not in listed[day][0]:
                yield Issue(tpath, f"reviewed.{key} = {day} is the as_of of updates/{', updates/'.join(listed[day][1])}, "
                                   f"but {key} is not in its reviewed_sections (§G8)", tdoc.line("reviewed", key))


# -- C-TEST-FROZEN --------------------------------------------------------------------------------------------
# The pre-registered criteria of a test (00 §G7): its rules, their prose, and a staleness test's limit.
FROZEN_FIELDS = ("rule", "fail_if", "warn_rule", "warn_if", "max_age_quarters")


def _git(root: Path, *args: str) -> subprocess.CompletedProcess | None:
    git = shutil.which("git")
    if git is None:
        return None
    try:
        return subprocess.run([git, "-C", str(root), *args], capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None


def base_tests(root: Path, ref: str, rel: str) -> dict[str, dict] | None:
    """Tests of ``rel`` at ``ref`` keyed by id; None when the file does not exist there."""
    proc = _git(root, "show", f"{ref}:./{rel}")
    if proc is None or proc.returncode != 0:
        return None
    try:
        data = yaml.safe_load(proc.stdout)
    except (yaml.YAMLError, ValueError, TypeError):
        return None
    out: dict[str, dict] = {}
    for _i, test in tests_of(data if isinstance(data, dict) else {}):
        if isinstance(test.get("id"), str):
            out.setdefault(test["id"], test)
    return out


@check("C-TEST-FROZEN")
def c_test_frozen(ctx: Context) -> Iterator[Issue]:
    if not ctx.base_ref or not ctx.period:
        return  # vacuous without --base-ref, and without a current period there is nothing to freeze
    repo = ctx.repo
    inside = _git(repo.root, "rev-parse", "--is-inside-work-tree")
    if inside is None or inside.returncode != 0 or inside.stdout.strip() != "true":
        yield Issue(None, f"--base-ref {ctx.base_ref}: {repo.root.name} is not a git work tree, so the thesis tests "
                        "cannot be compared", level="warning")
        return
    resolved = _git(repo.root, "rev-parse", "--verify", "--quiet", f"{ctx.base_ref}^{{commit}}")
    if resolved is None or resolved.returncode != 0:
        yield Issue(None, f"--base-ref {ctx.base_ref} does not name a commit in this repository; the frozen thresholds "
                        "cannot be checked")
        return
    for path, doc, data in theses(repo):
        before = base_tests(repo.root, ctx.base_ref, repo.rel(path))
        if not before:
            continue
        now = {test.get("id"): (i, test) for i, test in tests_of(data) if isinstance(test.get("id"), str)}
        for tid, old in before.items():
            if not in_force_for(old, ctx.period):
                continue
            since = old.get("effective_from") or "the start"
            if tid not in now:
                yield Issue(path, f"{tid} is in force for {ctx.period} (since {since}) and was removed; retire it with "
                                  "retired_at for a later period instead (§G7)", doc.line("tests"))
                continue
            i, new = now[tid]
            for field in FROZEN_FIELDS:
                if jsonable(old.get(field)) != jsonable(new.get(field)):
                    yield Issue(path, f"{tid}: {field} changed although the test is in force for {ctx.period} "
                                      f"(since {since}); thresholds are frozen once they are in force: write a new test "
                                      "with a later effective_from (§G7)", doc.line("tests", i, field) or doc.line("tests", i))


# -- C-PROMPT-ISOLATION ------------------------------------------------------------------------------------------
# 00 §F0: an input taken from one part carries that part's number (findings_04A, test_proposals_04B_lite).
PART_SUFFIX_RE = re.compile(r"_\d{2}[A-Za-z]?(?:_lite)?$")


def _name(item: Any) -> str:
    """An input or cannot_see name without the optional marker: "findings_04A?" -> findings_04a."""
    return str(item).strip().rstrip("?").strip().lower()


def prompt_parts(data: dict) -> Iterator[tuple[str, str | None, tuple, list]]:
    """(part label, role, key path of the part, [(input key, index, name)]) for every part of a prompt.

    A prompt either takes ``role`` and ``inputs`` at the top level, or lists ``parts`` whose role defaults to the
    top-level one; a part's inputs are every key that starts with ``inputs`` (inputs_pass1, inputs_pass2, ...).
    """
    top_role = data.get("role") if isinstance(data.get("role"), str) else None

    def inputs_of(block: dict) -> list:
        out = []
        for key, value in block.items():
            if isinstance(key, str) and key.startswith("inputs") and isinstance(value, list):
                out.extend((key, i, item) for i, item in enumerate(value) if isinstance(item, (str, int, float)))
        return out

    top = inputs_of(data)
    if top:
        yield str(data.get("id") or "prompt"), top_role, (), top
    parts = data.get("parts")
    if isinstance(parts, dict):
        for name, part in parts.items():
            if isinstance(part, dict):
                role = part.get("role") if isinstance(part.get("role"), str) else top_role
                yield str(name), role, ("parts", name), inputs_of(part)


def hidden_by_role(repo: Repo) -> dict[str, tuple[set[str], str]]:
    """role -> (normalized cannot_see names, agents/<file>.yml) from the public archive's agent definitions."""
    out: dict[str, tuple[set[str], str]] = {}
    for path in repo.files("agents/*.yml"):
        data = repo.doc(path).mapping
        role = data.get("role") if isinstance(data.get("role"), str) else path.stem
        hidden = data.get("cannot_see")
        if isinstance(hidden, list):
            names, _file = out.setdefault(role, (set(), repo.rel(path)))
            names.update(_name(x) for x in hidden)
    return out


@check("C-PROMPT-ISOLATION")
def c_prompt_isolation(ctx: Context) -> Iterator[Issue]:
    if ctx.counterpart is None:
        return  # the agent definitions live in the public archive
    hidden = hidden_by_role(ctx.counterpart)
    prompts = ctx.repo.files("prompts/*.md")
    if not hidden or not prompts:
        return
    for path in prompts:
        doc: Doc | None = ctx.repo.front_matter(path)
        if doc is None or doc.error or not isinstance(doc.data, dict):
            continue
        for part, role, where, inputs in prompt_parts(doc.data):
            if role not in hidden:
                continue
            names, agent_file = hidden[role]
            for key, i, item in inputs:
                name = _name(item)
                if name in names or PART_SUFFIX_RE.sub("", name) in names:
                    yield Issue(path, f"part {part} ({role}) takes input {str(item).rstrip('?')!r}, which {agent_file} "
                                      "lists in cannot_see; the pipeline would have to hand the role what it must not see",
                                doc.line(*where, key, i))
