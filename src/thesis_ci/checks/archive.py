"""Archive structure: industry dependencies, two-minute stories, pre-registration timing and immutability."""

from __future__ import annotations

import datetime as dt
import hashlib
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterator

from ..engine import Context, Issue, check
from ..repo import Doc, Repo
from ..textscan import compile_wording, split_front_matter, story_length
from .public import ADVICE_WORDING, content_files, forbidden_wording
from .schema import schema_issues
from .thesis_tests import theses

DEPENDS_RE = re.compile(r"^industries/[a-z0-9-]+$")
# Industry modules describe the industry only: no holdings, no dependants (spec/checks.yml, C-DEPENDS).
# "bank holding company" / 控股公司 / "demand depends on" are ordinary words and stay allowed.
NEUTRALITY_PHRASES = (
    "持仓", "portfolio holding", "depends_on",
    "我们持有", "我持有", "本人持有", "仓位", "本组合", "我们的组合", "我们的投资组合",
    "our portfolio", "dependent companies",
)
NEUTRALITY_PATTERNS = (
    # "our holding company" (a 20-F's own words) is a legal entity, not a portfolio holding
    ("our holding", r"(?<![A-Za-z])our\s+holdings?(?!\s+(?:company|companies|structure|entity|entities))(?![A-Za-z])"),
    ("our position", r"(?<![A-Za-z])our\s+(?:positions?|stakes?)\s+in(?![A-Za-z])"),
    ("依赖本行业的公司", r"依赖(?:于)?\s*(?:本|该|此|这个|这一)\s*(?:行业|模块)"),
    ("companies that depend on this industry",
     r"(?<![A-Za-z])(?:companies|firms|holdings|tickers|stocks|theses)\s+(?:that\s+|which\s+)?"
     r"(?:depend|depends|depending|rely|relies|relying)\s+on\s+(?:this|the)\s+(?:industry|module|sector)(?![A-Za-z])"),
)
NEUTRALITY_WORDING = compile_wording(NEUTRALITY_PHRASES, NEUTRALITY_PATTERNS)
STORY_MAX_CHARS = 700
UTC = dt.timezone.utc
try:  # EDGAR's clock: acceptance times and filing days are US Eastern
    from zoneinfo import ZoneInfo

    EDGAR_TZ: dt.tzinfo | None = ZoneInfo("America/New_York")
except Exception:  # noqa: BLE001  (no tz database on this machine)
    EDGAR_TZ = None


@check("C-DEPENDS")
def c_depends(ctx: Context) -> Iterator[Issue]:
    repo = ctx.repo
    for path, doc, data in theses(repo):
        deps = data.get("depends_on")
        for i, dep in enumerate(deps if isinstance(deps, list) else []):
            ok = isinstance(dep, str) and DEPENDS_RE.match(dep) and (repo.root / dep / "industry.yml").is_file()
            if not ok:
                yield Issue(path, f"depends_on {dep!r} does not resolve to an industries/<id>/industry.yml", doc.line("depends_on", i))
    modules = list(content_files(repo, ("industries",), ()))
    yield from forbidden_wording(repo, modules, NEUTRALITY_WORDING, "industry modules must stay neutral (no holdings or dependants)")
    yield from forbidden_wording(repo, modules, ADVICE_WORDING, "industry modules must not give advice")


@check("C-STORY")
def c_story(ctx: Context) -> Iterator[Issue]:
    repo = ctx.repo
    for company_dir in repo.company_dirs():
        path = company_dir / "story.md"
        if not path.is_file():
            yield Issue(path, "two-minute story (story.md) is missing")
            continue
        doc = repo.front_matter(path)
        if doc is None:
            yield Issue(path, "story.md has no YAML front matter", 1)
        elif doc.error:
            yield Issue(path, doc.error, doc.error_line)
        else:
            yield from schema_issues(doc, "story")
            company = doc.mapping.get("company")
            if company != company_dir.name:
                yield Issue(path, f"front matter company {company!r} does not match directory {company_dir.name!r}", doc.line("company"))
            thesis_path = company_dir / "thesis.yml"
            thesis = repo.doc(thesis_path).mapping if thesis_path.is_file() else {}
            for key in ("status", "category"):  # the story must not tell a different story from thesis.yml
                told, recorded = doc.mapping.get(key), thesis.get(key)
                if told is not None and recorded is not None and told != recorded:
                    yield Issue(path, f"front matter {key} {told!r} does not match thesis.yml {key} {recorded!r}", doc.line(key))
        _fm, body = split_front_matter(repo.text(path) or "")
        n = story_length(body)
        if n > STORY_MAX_CHARS:
            yield Issue(path, f"story body is {n} characters (limit {STORY_MAX_CHARS}, tags and markup excluded)")


def to_datetime(value: Any) -> dt.datetime | None:
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, dt.date):
        return dt.datetime(value.year, value.month, value.day)
    if not isinstance(value, str):
        return None
    s = value.strip()
    if re.fullmatch(r"\d{14}", s):  # EDGAR compact form YYYYMMDDHHMMSS
        s = f"{s[:4]}-{s[4:6]}-{s[6:8]}T{s[8:10]}:{s[10:12]}:{s[12:]}"
    if s[-1:] in ("Z", "z"):
        s = s[:-1] + "+00:00"
    try:
        return dt.datetime.fromisoformat(s)
    except ValueError:
        return None


def to_date(value: Any) -> dt.date | None:
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


def _aware(t: dt.datetime) -> bool:
    return t.tzinfo is not None and t.utcoffset() is not None


def _before(earlier: Any, later: Any, names: tuple[str, str]) -> str | None:
    """Why ``earlier`` is not strictly before ``later`` (None when it is)."""
    a, b = to_datetime(earlier), to_datetime(later)
    if a is None or b is None:
        bad = names[0] if a is None else names[1]
        return f"{bad} is not an ISO 8601 date-time"
    if _aware(a) != _aware(b):
        return f"cannot compare {names[0]} and {names[1]}: give both a timezone"
    if not a < b:
        return f"{names[0]} ({earlier}) must be earlier than {names[1]} ({later})"
    return None


def deadline_day(deadline: dt.datetime) -> dt.date | None:
    """The calendar day a deadline falls on: in its own offset, or in EDGAR's (US Eastern) time for UTC."""
    if not _aware(deadline):
        return deadline.date()
    if deadline.utcoffset() == dt.timedelta(0):
        return deadline.astimezone(EDGAR_TZ).date() if EDGAR_TZ is not None else None
    return deadline.date()


# SPEC 2.1: prereg/<period>.yml (system items, immutable after the deadline), prereg/<period>-owner.yml (the owner's
# overrides and items, same rule), prereg/<period>.yml.ots (the timestamp proof) and prereg/<period>.settlement.yml
# (merge time, acceptance time, accession and results; kept by the pipeline).
PREREG_FILES = "companies/*/prereg/*.yml"
SETTLEMENT_SUFFIX = ".settlement.yml"
OWNER_SUFFIX = "-owner.yml"
OTS_TIMEOUT = 120
# The file is compared with the proof locally first: `ots info` prints the sha256 digest the proof commits to, with no
# network. A different digest, or a proof that cannot be read, is a failure. Only then is `ots verify` asked about the
# attestation; once the digest matches, a verify failure means the proof could not be checked here (no Bitcoin node,
# an attestation still pending, calendars unreachable) unless the client says the proof itself is bad.
OTS_INFO_DIGEST_RE = re.compile(r"File sha256 hash:\s*([0-9a-f]{64})", re.I)
OTS_BAD_PROOF_RE = re.compile(r"does not match|mismatch|bad timestamp|invalid|corrupt|not a timestamp", re.I)


def prereg_kind(path: Path) -> str:
    """settlement, owner or system."""
    if path.name.endswith(SETTLEMENT_SUFFIX):
        return "settlement"
    return "owner" if path.name.endswith(OWNER_SUFFIX) else "system"


def prereg_items_files(repo: Repo) -> Iterator[tuple[Path, Doc, str]]:
    """(path, doc, kind) of every items file: prereg/<period>.yml (system) and prereg/<period>-owner.yml (owner)."""
    for path in repo.files(PREREG_FILES):
        kind = prereg_kind(path)
        if kind != "settlement":
            yield path, repo.doc(path), kind


def _deadline_day(value: Any) -> dt.date | None:
    due = to_datetime(value)
    return deadline_day(due) if due is not None else None


@check("C-PREREG-TIMING")
def c_prereg_timing(ctx: Context) -> Iterator[Issue]:
    repo = ctx.repo
    system: dict[Path, Any] = {}  # prereg directory + period -> the system file's deadline
    for path, doc, kind in prereg_items_files(repo):
        data = doc.mapping
        deadline = data.get("deadline")
        event = data.get("event") if isinstance(data.get("event"), dict) else {}
        # The deadline is the end of the day before the release day (a press release can precede the filing),
        # so a deadline on or after the release day lets a pre-registration be merged after the results.
        day, release = _deadline_day(deadline), to_date(event.get("expected_release"))
        if day is not None and release is not None and not day < release:
            yield Issue(path, f"deadline ({deadline}) falls on {day}, not before the release day {release}; "
                              "set it to the end of the previous day", doc.line("deadline"))
        if kind == "system":
            system[path.with_name(path.name[: -len(".yml")])] = deadline
    for path, doc, kind in prereg_items_files(repo):
        if kind != "owner":
            continue
        base = path.with_name(path.name[: -len(OWNER_SUFFIX)])
        if base in system and to_datetime(doc.mapping.get("deadline")) != to_datetime(system[base]):
            yield Issue(path, f"deadline {doc.mapping.get('deadline')} differs from {base.name}.yml "
                              f"({system[base]}); the owner's overrides share the system file's deadline", doc.line("deadline"))
    for stem, deadline in sorted(system.items()):
        settlement = stem.with_name(stem.name + SETTLEMENT_SUFFIX)
        data = repo.doc(settlement).mapping if settlement.is_file() else {}
        sdoc = repo.doc(settlement) if settlement.is_file() else None
        if data.get("merged_at") is not None:
            why = _before(data["merged_at"], deadline, ("merged_at", "deadline"))
            if why:
                yield Issue(settlement, why, sdoc.line("merged_at"))
        if data.get("acceptance_datetime") is not None:
            why = _before(deadline, data["acceptance_datetime"], ("deadline", "acceptance_datetime"))
            if why:
                yield Issue(settlement, why, sdoc.line("acceptance_datetime"))
        day = _deadline_day(deadline)
        if data.get("merged_at") is None and day is not None and day < ctx.today:
            items = stem.with_name(stem.name + ".yml")
            yield Issue(items, f"deadline {deadline} has passed and merged_at is not recorded in {settlement.name}; "
                               "the merge time cannot be checked", repo.doc(items).line("deadline"), level="warning")


def ots_executable() -> str | None:
    """The OpenTimestamps client (`ots`) on PATH, if any."""
    return shutil.which("ots")


def _run_ots(ots: str, args: list[str]) -> tuple[subprocess.CompletedProcess[str] | None, str]:
    """Run the client; (None, reason) when it could not run or timed out."""
    try:
        return subprocess.run([ots, *args], capture_output=True, text=True, timeout=OTS_TIMEOUT), ""
    except subprocess.TimeoutExpired:
        return None, f"ots {args[0]} timed out after {OTS_TIMEOUT} s"
    except OSError as exc:
        return None, f"ots could not run: {exc}"


def _last_line(proc: subprocess.CompletedProcess[str]) -> str:
    lines = [ln.strip() for ln in "\n".join(s for s in (proc.stdout, proc.stderr) if s).splitlines() if ln.strip()]
    return lines[-1] if lines else f"exit status {proc.returncode}"


def ots_verify(ots: str, target: Path, proof: Path) -> tuple[bool | None, str]:
    """(True, detail) when `ots verify` passes, (False, detail) when it fails, (None, detail) when it cannot check."""
    info, reason = _run_ots(ots, ["info", str(proof)])
    if info is None:
        return None, reason
    found = OTS_INFO_DIGEST_RE.search(f"{info.stdout}\n{info.stderr}")
    if not found:
        return False, f"the proof cannot be read ({_last_line(info)})"
    committed, actual = found.group(1).lower(), hashlib.sha256(target.read_bytes()).hexdigest()
    if committed != actual:
        return False, f"the file's sha256 {actual[:12]}… does not match the proof's {committed[:12]}…"
    proc, reason = _run_ots(ots, ["verify", "-f", str(target), str(proof)])
    if proc is None:
        return None, reason
    output = f"{proc.stdout}\n{proc.stderr}"
    if proc.returncode == 0:
        return True, _last_line(proc)
    return (False if OTS_BAD_PROOF_RE.search(output) else None), _last_line(proc)


@check("C-PREREG-IMMUTABLE")
def c_prereg_immutable(ctx: Context) -> Iterator[Issue]:
    repo = ctx.repo
    published = set(repo.all_files)
    ots: str | None | bool = False  # looked up once, and only when a proof has to be verified
    for path, doc, _kind in prereg_items_files(repo):
        deadline = doc.mapping.get("deadline")
        day = _deadline_day(deadline)
        if day is None or not day < ctx.today:
            continue  # the deadline has not passed (an unreadable deadline is reported by C-SCHEMA)
        proof = path.with_name(path.name + ".ots")
        if proof not in published:
            yield Issue(path, f"deadline {deadline} has passed but the timestamp proof {proof.name} is missing: "
                              "nothing shows that the file is unchanged since the deadline", doc.line("deadline"))
            continue
        if ots is False:
            ots = ots_executable()
        if ots is None:
            yield Issue(proof, f"cannot verify {proof.name}: the OpenTimestamps client (ots) is not installed",
                        level="warning")
            continue
        ok, detail = ots_verify(ots, path, proof)
        if ok is None:
            yield Issue(proof, f"cannot verify {proof.name}: {detail}", level="warning")
        elif not ok:
            yield Issue(proof, f"ots verify failed for {path.name}: {detail} (the file changed after it was "
                               "timestamped, or the proof belongs to another file)")
