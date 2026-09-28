"""Check registry and runner.

Every check in spec/checks.yml is a function registered with ``@check("C-...")``. It receives a
``Context`` and yields ``Issue`` objects; the runner stamps them with the check id and level.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from . import contract
from .repo import Repo, dig

LEVELS = ("error", "warning")
INTERNAL_ERROR = "internal error"


@dataclass(frozen=True)
class Finding:
    check: str
    level: str
    file: str
    line: int | None
    message: str

    def as_dict(self) -> dict:
        return {"check": self.check, "file": self.file, "line": self.line, "message": self.message}


@dataclass
class Issue:
    """What a check yields. ``level`` defaults to the check's level in spec/checks.yml."""

    file: Path | str | None
    message: str
    line: int | None = None
    level: str | None = None


CheckFn = Callable[["Context"], Iterable[Issue]]
REGISTRY: dict[str, CheckFn] = {}


def check(check_id: str) -> Callable[[CheckFn], CheckFn]:
    """Register the implementation of one check id from spec/checks.yml."""

    def register(fn: CheckFn) -> CheckFn:
        if check_id in REGISTRY:
            raise ValueError(f"check {check_id} registered twice")
        REGISTRY[check_id] = fn
        fn.check_id = check_id  # type: ignore[attr-defined]
        return fn

    return register


def load_checks() -> dict[str, CheckFn]:
    from . import checks  # noqa: F401  (importing registers every implementation)

    return REGISTRY


# Values fixed by the constitution; used when neither repository has constitution/decision-rights.yml.
DEFAULT_RIGHTS: dict[str, Any] = {
    "memo": {"default_option": "maintain", "timeout_days": 14, "monthly_target_max": 2},
    "portfolio": {"max_holdings": 5, "entry_band": [0.10, 0.20], "single_order_entry": True},
}


class Context:
    def __init__(self, repo: Repo, counterpart: Repo | None = None, today: dt.date | None = None,
                 expected_visibility: str | None = None, base_ref: str | None = None, period: str | None = None):
        self.repo = repo
        self.counterpart = counterpart
        self.today = today or dt.date.today()
        # set by `lint --expect-visibility`: the checks for this visibility run whatever repo.yml says
        self.expected_visibility = expected_visibility
        # set by `lint --base-ref` / `--period` (C-TEST-FROZEN): the git ref to compare with, the current period
        self.base_ref = base_ref
        self.period = period

    @property
    def visibility(self) -> str:
        return self.expected_visibility or self.repo.visibility or "public"

    @property
    def is_private(self) -> bool:
        return self.visibility == "private"

    def setting(self, *keys: str) -> Any:
        """A decision-rights value: this repo's file, else the counterpart's, else the constitution default."""
        for repo in (self.repo, self.counterpart):
            if repo is not None:
                value = dig(repo.rights(), *keys)
                if value is not None:
                    return value
        if keys == ("memo", "sell_reasons"):
            return contract.sell_reason_enum()
        return dig(DEFAULT_RIGHTS, *keys)

    def holdings(self) -> set[str] | None:
        """Tickers whose thesis.yml says ``status: holding`` (None when no thesis files are visible).

        The public archive is authoritative, so it is consulted first.
        """
        repos = [r for r in (self.repo, self.counterpart) if r is not None]
        for repo in sorted(repos, key=lambda r: r.visibility != "public"):
            theses = repo.files("companies/*/thesis.yml")
            if theses:
                out = set()
                for path in theses:
                    data = repo.doc(path).mapping
                    if data.get("status") == "holding":
                        out.add(str(data.get("company") or path.parent.name))
                return out
        return None

    def memos(self) -> list[tuple[Path, Any]]:
        """(path, doc) for private L3 memos."""
        return [(p, self.repo.doc(p)) for p in self.repo.files("memos/*.yml")]


@dataclass
class Report:
    repo: str
    visibility: str
    findings: list[Finding] = field(default_factory=list)
    checks_run: list[str] = field(default_factory=list)
    # the profiles that selected the checks; None when every profile ran (no selection) or --only chose them
    profiles: tuple[str, ...] | None = None

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.level == "warning"]

    def as_dict(self) -> dict:
        return {
            "repo": self.repo,
            "visibility": self.visibility,
            "errors": [f.as_dict() for f in self.errors],
            "warnings": [f.as_dict() for f in self.warnings],
            "checks_run": list(self.checks_run),
        }


def declared_profiles(repo: Repo) -> tuple[str, ...] | None:
    """The profiles repo.yml selects, in registry order; None when it selects none (every profile runs).

    A malformed value (anything but a non-empty list of distinct, known profile names, as repo.schema.json has it)
    also runs every profile: a typo must not switch checks off, and C-SCHEMA, which then runs, reports it.
    """
    declared = (repo.meta or {}).get("profiles")
    known = contract.profiles()
    if not (isinstance(declared, list) and declared and all(isinstance(p, str) and p in known for p in declared)
            and len(set(declared)) == len(declared)):
        return None
    return tuple(p for p in known if p in declared)


def select_profiles(repo: Repo, override: Iterable[str] | None = None) -> tuple[str, ...] | None:
    """The profiles a lint runs: ``override`` (lint --profile) if given, else repo.yml's; None means all of them."""
    if override is None:
        return declared_profiles(repo)
    wanted = set(override)
    unknown = sorted(wanted - set(contract.profiles()))
    if unknown or not wanted:
        raise ValueError(f"unknown profile(s): {', '.join(unknown) or '(none given)'}; "
                         f"the profiles are {', '.join(contract.profiles())}")
    return tuple(p for p in contract.profiles() if p in wanted)


def applies(scope: str, visibility: str, has_counterpart: bool) -> bool:
    if scope == "both":
        return True
    if scope == "workspace":
        return has_counterpart
    return scope == visibility


def run(
    path: str | Path,
    counterpart: str | Path | None = None,
    today: dt.date | None = None,
    only: Iterable[str] | None = None,
    expect_visibility: str | None = None,
    base_ref: str | None = None,
    period: str | None = None,
    profiles: Iterable[str] | None = None,
) -> Report:
    """Lint one archive. ``only`` runs exactly those checks; otherwise ``profiles`` (lint --profile), else the
    ``profiles`` of repo.yml, else every profile selects them (SPEC 8.6). Scope then decides what applies."""
    if expect_visibility not in (None, "public", "private"):
        raise ValueError(f"expect_visibility must be public or private, not {expect_visibility!r}")
    registry = load_checks()
    repo = Repo(path)
    ctx = Context(repo, Repo(counterpart) if counterpart else None, today, expect_visibility, base_ref, period)
    wanted = set(only) if only else None
    selected = None if wanted is not None else select_profiles(repo, profiles)
    report = Report(repo=str(repo.root), visibility=ctx.visibility, profiles=selected)
    for meta in contract.registered_checks():
        cid = meta["id"]
        if wanted is not None and cid not in wanted:
            continue
        if selected is not None and meta["profile"] not in selected:
            continue
        if not applies(meta["scope"], ctx.visibility, ctx.counterpart is not None):
            continue
        fn = registry.get(cid)
        if fn is None:
            report.findings.append(Finding(cid, "error", "", None, "registered in spec/checks.yml but not implemented"))
            continue
        report.checks_run.append(cid)
        try:
            for issue in fn(ctx) or ():
                report.findings.append(_finding(meta, issue, repo))
        except Exception as exc:  # a crashing check must not hide the others
            report.findings.append(Finding(cid, "error", "", None, f"{INTERNAL_ERROR}: {type(exc).__name__}: {exc}"))
    report.findings.sort(key=lambda f: (f.file, f.line or 0, f.check))
    return report


def _finding(meta: dict, issue: Issue, repo: Repo) -> Finding:
    level = issue.level or meta["level"]
    if level not in LEVELS:
        raise ValueError(f"bad level {level!r}")
    file = repo.rel(issue.file) if issue.file is not None else ""
    return Finding(meta["id"], level, file, issue.line, issue.message)
