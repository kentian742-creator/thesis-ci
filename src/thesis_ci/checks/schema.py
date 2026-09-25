"""C-SCHEMA: every YAML file and story.md front matter matches its JSON Schema (SPEC section 2)."""

from __future__ import annotations

import json
import re
from typing import Iterator

from jsonschema.exceptions import ValidationError

from .. import contract
from ..engine import Context, Issue, check
from ..repo import Doc, Repo, is_yaml, jsonable, path_match

# (path pattern, schema name, only in this visibility). First match wins.
SCHEMA_MAP = (
    ("repo.yml", "repo", None),
    ("companies/*/thesis.yml", "thesis", None),
    ("**/sources.yml", "sources", None),
    ("companies/*/prereg/*.settlement.yml", "prereg-settlement", None),
    ("companies/*/prereg/*.yml", "prereg", None),  # prereg/<period>.yml and prereg/<period>-owner.yml
    ("companies/*/ledger.yml", "ledger", None),
    ("companies/*/valuation.yml", "valuation", "private"),
    ("industries/*/industry.yml", "industry", None),
    ("forecasts/*.yml", "forecast", None),
    ("constitution/decision-rights.yml", "decision-rights", None),
    ("constitution/rules.yml", "constitution-rules", None),
    ("agents/*.yml", "agent", None),
    ("memos/*.yml", "memo", "private"),
    ("escalations/*.yml", "escalation", "private"),
    ("decision-log/*.yml", "decision-log", "private"),
)
STORY = "companies/*/story.md"
# SPEC section 2: companies/<TICKER>/... and industries/<id>/... ; the directory names the company or module.
COMPANY_FILES = ("companies/*/thesis.yml", "companies/*/ledger.yml", "companies/*/valuation.yml", "companies/*/prereg/*.yml")
INDUSTRY_FILE = "industries/*/industry.yml"
SPEC_VERSION = "0.2"
PREVIOUS_SPEC_VERSIONS = ("0.1",)  # accepted by repo.schema.json during the migration, with a warning
# SPEC 2.1: prereg/<period>.yml (system), prereg/<period>-owner.yml (owner), prereg/<period>.settlement.yml
PREREG_NAME_RE = re.compile(r"^(FY\d{4}Q[1-4])(-owner|\.settlement)?\.yml$")


def schema_for(rel: str, visibility: str) -> str | None:
    for pattern, name, only in SCHEMA_MAP:
        if path_match(rel, pattern):
            return name if only in (None, visibility) else None
    return None


def _leaves(err: ValidationError) -> list[ValidationError]:
    """Replace an opaque oneOf/anyOf error by the errors of the branch the instance was aiming at.

    A branch is discarded when it fails on its ``type`` discriminator (e.g. a qualitative test is not
    checked against the quantitative branch); if exactly one branch is left, its errors are reported.
    """
    if err.validator in ("oneOf", "anyOf") and err.context:
        branches: dict[int, list[ValidationError]] = {}
        for sub in err.context:
            branches.setdefault(sub.relative_schema_path[0], []).append(sub)
        plausible = [
            subs for subs in branches.values()
            if not any(s.validator == "const" and list(s.relative_path) == ["type"] for s in subs)
        ]
        if len(plausible) == 1:
            return [leaf for sub in plausible[0] for leaf in _leaves(sub)]
    return [err]


def _message(err: ValidationError) -> str:
    if err.validator == "not":
        banned = err.validator_value.get("required") if isinstance(err.validator_value, dict) else None
        if isinstance(banned, list) and len(err.validator_value) == 1:
            return f"must not have {', '.join(repr(k) for k in banned)}"
        return f"must not match {json.dumps(err.validator_value, ensure_ascii=False)}"
    msg = err.message
    return msg if len(msg) <= 200 else msg[:199] + "…"


def schema_issues(doc: Doc, name: str) -> Iterator[Issue]:
    instance = jsonable(doc.data)
    errors = sorted(contract.validator(name).iter_errors(instance), key=lambda e: [str(p) for p in e.absolute_path])
    for err in errors:
        for leaf in _leaves(err):
            path = list(leaf.absolute_path)
            where = "/" + "/".join(str(p) for p in path)
            yield Issue(doc.path, f"{name}.schema.json {where}: {_message(leaf)}", doc.line(*path))


def duplicate_issues(path, duplicates: list[tuple[int, str]]) -> Iterator[Issue]:
    for line, key in duplicates:
        yield Issue(path, f"duplicate key '{key}': YAML keeps only the last value, so readers and checks disagree", line)


def consistency_issues(repo: Repo, rel: str, doc: Doc, name: str) -> Iterator[Issue]:
    """What a JSON Schema cannot say: the directory names the company or module; source tags are unique."""
    data = doc.mapping
    if any(path_match(rel, p) for p in COMPANY_FILES):
        ticker = rel.split("/")[1]
        if "company" in data and data.get("company") != ticker:
            yield Issue(doc.path, f"company {data.get('company')!r} does not match directory companies/{ticker}/", doc.line("company"))
    elif path_match(rel, INDUSTRY_FILE):
        module = rel.split("/")[1]
        if "id" in data and data.get("id") != module:
            yield Issue(doc.path, f"id {data.get('id')!r} does not match directory industries/{module}/", doc.line("id"))
    if name == "sources" and isinstance(data.get("sources"), list):
        seen: set[str] = set()
        for i, entry in enumerate(data["sources"]):
            tag = entry.get("tag") if isinstance(entry, dict) else None
            if isinstance(tag, str):
                if tag in seen:
                    yield Issue(doc.path, f"source tag {tag} is defined twice; a tag must name one source", doc.line("sources", i))
                seen.add(tag)
    if name in ("prereg", "prereg-settlement"):
        yield from prereg_consistency(rel, doc, name)
    if name == "repo" and data.get("spec_version") in PREVIOUS_SPEC_VERSIONS:
        yield Issue(doc.path, f"repo.yml declares spec_version {data.get('spec_version')!r}; this thesis-ci lints against "
                              f"spec {SPEC_VERSION} (set it to \"{SPEC_VERSION}\" once the archive is migrated)",
                    doc.line("spec_version"), level="warning")


def prereg_consistency(rel: str, doc: Doc, name: str) -> Iterator[Issue]:
    """SPEC 2.1: the file name gives the period and the author; item ids are <TICKER>-<period>-<n>."""
    data = doc.mapping
    fname = rel.rsplit("/", 1)[-1]
    m = PREREG_NAME_RE.match(fname)
    if m is None:
        yield Issue(doc.path, f"{fname}: pre-registration files are named <FY####Q#>.yml, <FY####Q#>-owner.yml "
                              "or <FY####Q#>.settlement.yml", doc.line())
        return
    period, kind = m.group(1), m.group(2)
    if name == "prereg-settlement":
        if "period" in data and data.get("period") != period:
            yield Issue(doc.path, f"period {data.get('period')!r} does not match the file name {fname}", doc.line("period"))
        return
    event = data.get("event") if isinstance(data.get("event"), dict) else {}
    if "period" in event and event.get("period") != period:
        yield Issue(doc.path, f"event.period {event.get('period')!r} does not match the file name {fname}", doc.line("event", "period"))
    author = "owner" if kind == "-owner" else "system"
    if "author" in data and data.get("author") != author:
        yield Issue(doc.path, f"{fname} is the {author}'s file, but author is {data.get('author')!r}", doc.line("author"))
    prefix = f"{rel.split('/')[1]}-{period}-"
    for key in ("items", "overrides"):
        entries = data.get(key)
        for i, entry in enumerate(entries if isinstance(entries, list) else []):
            iid = entry.get("id") if isinstance(entry, dict) else None
            if isinstance(iid, str) and not iid.startswith(prefix):
                yield Issue(doc.path, f"{key}[{i}].id {iid!r} does not start with '{prefix}'", doc.line(key, i, "id"))


@check("C-SCHEMA")
def c_schema(ctx: Context) -> Iterator[Issue]:
    repo = ctx.repo
    if not (repo.root / "repo.yml").is_file():
        yield Issue("repo.yml", f"repo.yml is missing (visibility unknown; linted as {ctx.visibility})")
    elif ctx.expected_visibility and repo.visibility != ctx.expected_visibility:
        yield Issue("repo.yml", f"repo.yml declares visibility {repo.visibility!r}, but this repository is expected to be "
                                f"{ctx.expected_visibility} (--expect-visibility); linted as {ctx.expected_visibility}",
                    repo.doc(repo.root / "repo.yml").line("visibility"))
    elif ctx.counterpart is not None and repo.visibility and repo.visibility == ctx.counterpart.visibility:
        yield Issue("repo.yml", f"this repository and its counterpart both declare visibility {repo.visibility}; "
                                "one archive is public and the other private", repo.doc(repo.root / "repo.yml").line("visibility"))
    for path in repo.all_files:
        rel = repo.rel(path)
        if path_match(rel, STORY):
            doc = repo.front_matter(path)
            if doc is None:
                yield Issue(path, "story.md has no YAML front matter", 1)
            elif doc.error:
                yield Issue(path, doc.error, doc.error_line)
            else:
                yield from duplicate_issues(path, doc.duplicates)
                yield from schema_issues(doc, "story")
        elif is_yaml(path):
            name = schema_for(rel, ctx.visibility)
            if name is None:
                problem = repo.yaml_stream_error(path)
                if problem:
                    yield Issue(path, problem[0], problem[1])
                else:
                    yield from duplicate_issues(path, repo.yaml_duplicates(path))
                continue
            doc = repo.doc(path)
            if doc.error:
                yield Issue(path, doc.error, doc.error_line)
            else:
                yield from duplicate_issues(path, doc.duplicates)
                yield from schema_issues(doc, name)
                yield from consistency_issues(repo, rel, doc, name)
