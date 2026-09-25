"""Checks on the thesis tests inside companies/*/thesis.yml."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

from .. import contract
from ..engine import Context, Issue, check
from ..periods import period_key, retired
from ..repo import Doc, Repo, dig, is_number
from ..staleness import evaluate

TEST_TYPES = ("quantitative", "qualitative", "staleness")
TOUCHSTONES = ("moat", "pricing_power", "returns_on_capital", "free_cash_flow")  # constitution rule 2
COMPARISONS = {"<", "<=", ">", ">=", "==", "!="}
CHANGES = {"increase", "decrease"}
RANGES = {"between", "outside"}


def theses(repo: Repo) -> Iterator[tuple[Path, Doc, dict]]:
    for path in repo.files("companies/*/thesis.yml"):
        doc = repo.doc(path)
        if isinstance(doc.data, dict):
            yield path, doc, doc.data


def tests_of(data: dict) -> list[tuple[int, dict]]:
    tests = data.get("tests")
    return [(i, t) for i, t in enumerate(tests) if isinstance(t, dict)] if isinstance(tests, list) else []


def active_tests(data: dict, period: str | None = None) -> list[tuple[int, dict]]:
    """Tests still in force: a test with retired_at is kept as a record but no longer counts (SPEC 4.1)."""
    return [(i, test) for i, test in tests_of(data) if not retired(test, period)]


def covers_of(data: dict, period: str | None = None) -> set[str]:
    out: set[str] = set()
    for _i, test in active_tests(data, period):
        if isinstance(test.get("covers"), list):
            out.update(c for c in test["covers"] if isinstance(c, str))
    return out


@check("C-TESTS-MIN")
def c_tests_min(ctx: Context) -> Iterator[Issue]:
    repo = ctx.repo
    for company_dir in repo.company_dirs():
        path = company_dir / "thesis.yml"
        if not path.is_file():
            yield Issue(path, "company has no thesis.yml (at least 5 thesis tests are required)")
            continue
        doc = repo.doc(path)
        data = doc.mapping
        ticker = str(data.get("company") or company_dir.name)
        tests = tests_of(data)
        active = active_tests(data, ctx.period)
        if len(active) < 5:
            retired_note = f" ({len(tests) - len(active)} retired tests do not count)" if len(tests) > len(active) else ""
            yield Issue(path, f"{len(active)} thesis tests in force{retired_note}; at least 5 are required", doc.line("tests"))
        types = {test["type"] for _i, test in active if isinstance(test.get("type"), str)}  # a list is not a type
        missing = [t for t in TEST_TYPES if t not in types]
        if missing:
            yield Issue(path, f"no {', '.join(missing)} test in force (each of the three types needs at least one)", doc.line("tests"))
        seen: set[str] = set()
        ids = {test.get("id") for _i, test in tests if isinstance(test.get("id"), str)}
        for i, test in tests:
            tid = test.get("id")
            if not (isinstance(tid, str) and tid.startswith(f"{ticker}-")):
                yield Issue(path, f"test id {tid!r} does not start with '{ticker}-'", doc.line("tests", i, "id"))
            if repr(tid) in seen:
                yield Issue(path, f"duplicate test id {tid!r}", doc.line("tests", i, "id"))
            seen.add(repr(tid))
            yield from lifecycle_issues(path, doc, i, test, ids)


def lifecycle_issues(path: Path, doc: Doc, i: int, test: dict, ids: set) -> Iterator[Issue]:
    """supersedes names another test of the file; retired_at does not come before effective_from."""
    tid, old = test.get("id"), test.get("supersedes")
    if isinstance(old, str) and (old == tid or old not in ids):
        what = "itself" if old == tid else "a test in this file"
        yield Issue(path, f"{tid}: supersedes {old!r} does not name {what}", doc.line("tests", i, "supersedes"))
    start, end = period_key(test.get("effective_from")), period_key(test.get("retired_at"))
    if start is not None and end is not None and end < start:
        yield Issue(path, f"{tid}: retired_at {test['retired_at']} comes before effective_from {test['effective_from']}",
                    doc.line("tests", i, "retired_at"))


@check("C-TESTS-COVERAGE")
def c_tests_coverage(ctx: Context) -> Iterator[Issue]:
    for path, doc, data in theses(ctx.repo):
        missing = [c for c in TOUCHSTONES if c not in covers_of(data, ctx.period)]
        if missing:
            yield Issue(path, f"tests in force do not cover {', '.join(missing)} (constitution rule 2)", doc.line("tests"))


@check("C-TESTS-CAPALLOC")
def c_tests_capalloc(ctx: Context) -> Iterator[Issue]:
    for path, doc, data in theses(ctx.repo):
        covered = covers_of(data, ctx.period)
        for need in ("capital_allocation", "management"):
            if need not in covered:
                yield Issue(path, f"no test in force covers {need} (constitution rule 3)", doc.line("tests"))


def rule_problems(rule: Any, where: str = "rule") -> list[str]:
    """Why a rule cannot be evaluated mechanically (empty list when it can)."""
    if not isinstance(rule, dict):
        return [f"{where} must be a mapping"]
    problems = []
    combos = [k for k in ("all_of", "any_of") if k in rule]
    if "op" in rule:
        op, threshold = rule.get("op"), rule.get("threshold")
        op = op if isinstance(op, str) else repr(op)
        if combos:
            problems.append(f"{where} mixes op with {'/'.join(combos)}")
        if op in COMPARISONS | CHANGES:
            if not is_number(threshold):
                problems.append(f"{where}: op {op!r} needs a numeric threshold")
        elif op in RANGES:
            ok = isinstance(threshold, list) and len(threshold) == 2 and all(is_number(x) for x in threshold)
            if not ok or threshold[0] > threshold[1]:
                problems.append(f"{where}: op {op!r} needs threshold [low, high]")
        elif op != "event":
            problems.append(f"{where}: unknown op {op!r}")
    elif combos:
        for key in combos:
            subs = rule[key]
            if not isinstance(subs, list) or not subs:
                problems.append(f"{where}.{key} must be a non-empty list of rules")
                continue
            for i, sub in enumerate(subs):
                problems.extend(rule_problems(sub, f"{where}.{key}[{i}]"))
    else:
        problems.append(f"{where} needs op/threshold or all_of/any_of")
    consecutive = rule.get("consecutive")
    if consecutive is not None and not (isinstance(consecutive, int) and not isinstance(consecutive, bool) and consecutive >= 1):
        problems.append(f"{where}.consecutive must be a positive integer")
    return problems


class MetricNames:
    """What a rule's ``metric`` may name in one test (SPEC 4.1): a registered metric, the test's own metric
    (``metric`` / ``metric_def.id``) or one of its components, or a legacy ``params.metric_defs`` entry;
    ``<metric>.<component>`` names a component of the test's own ``metric_def``."""

    def __init__(self, test: dict):
        metric_def = test.get("metric_def") if isinstance(test.get("metric_def"), dict) else {}
        comps = metric_def.get("components")
        self.components = set(comps) if isinstance(comps, dict) else set()
        self.own = {m for m in (test.get("metric"), metric_def.get("id")) if isinstance(m, str)} if metric_def else set()
        legacy = dig(test, "params", "metric_defs")
        self.legacy = {d["id"] for d in legacy if isinstance(d, dict) and isinstance(d.get("id"), str)} \
            if isinstance(legacy, list) else set()
        self.plain = set(contract.metrics()) | self.legacy | self.components | self.own
        if isinstance(test.get("metric"), str):
            self.plain.add(test["metric"])

    def problem(self, name: Any) -> str | None:
        if not isinstance(name, str):
            return f"{name!r} is not a metric id"
        base, _, component = name.partition(".")
        if not component:
            return None if name in self.plain else "is not in spec/metrics.yml and not defined in the test"
        if base in self.own:
            if component in self.components:
                return None
            return (f"names component {component!r}, but metric_def.components does not define it"
                    if self.components else f"names component {component!r}, but metric_def has no components")
        if base in contract.metrics() or base in self.legacy:
            return None  # a registered metric or a legacy params.metric_defs entry: components cannot be checked
        return f"{base!r} is not in spec/metrics.yml and not defined in the test"


def unresolved_metrics(rule: Any, where: str, names: MetricNames) -> Iterator[str]:
    """Sub-rule metrics that do not resolve (SPEC 4.1: rule.metric must resolve)."""
    if not isinstance(rule, dict):
        return
    if "metric" in rule:
        problem = names.problem(rule["metric"])
        if problem:
            yield f"{where}.metric {rule['metric']!r} {problem}"
    for key in ("all_of", "any_of"):
        subs = rule.get(key)
        for i, sub in enumerate(subs if isinstance(subs, list) else []):
            yield from unresolved_metrics(sub, f"{where}.{key}[{i}]", names)


@check("C-TEST-METRIC")
def c_test_metric(ctx: Context) -> Iterator[Issue]:
    registry = contract.metrics()
    for path, doc, data in theses(ctx.repo):
        for i, test in tests_of(data):
            if test.get("type") != "quantitative":
                continue
            tid, metric, metric_def = test.get("id"), test.get("metric"), test.get("metric_def")
            line = doc.line("tests", i)
            if isinstance(metric_def, dict):
                definition = metric_def
            elif isinstance(metric, str) and metric in registry:
                definition = registry[metric]
            else:
                what = f"metric {metric!r} is not in spec/metrics.yml" if metric else "no metric"
                yield Issue(path, f"{tid}: {what} and no metric_def is given", doc.line("tests", i, "metric") or line)
                definition = None
            if "rule" not in test:
                yield Issue(path, f"{tid}: quantitative test has no rule", line)
            names = MetricNames(test)
            for key in ("rule", "warn_rule"):
                if key in test:
                    for problem in rule_problems(test[key], key):
                        yield Issue(path, f"{tid}: {problem}", doc.line("tests", i, key))
                    for problem in unresolved_metrics(test[key], key, names):
                        yield Issue(path, f"{tid}: {problem}", doc.line("tests", i, key))
            if definition is not None and test.get("data") != definition.get("data"):
                yield Issue(
                    path,
                    f"{tid}: data {test.get('data')!r} does not match the metric definition ({definition.get('data')!r})",
                    doc.line("tests", i, "data") or line,
                )


@check("C-TEST-QUAL-EVIDENCE")
def c_test_qual_evidence(ctx: Context) -> Iterator[Issue]:
    for path, doc, data in theses(ctx.repo):
        for i, test in tests_of(data):
            if test.get("type") != "qualitative":
                continue
            tid = test.get("id")
            for key in ("question", "fail_if"):
                if not (isinstance(test.get(key), str) and test[key].strip()):
                    yield Issue(path, f"{tid}: qualitative test needs a {key}", doc.line("tests", i))
            if test.get("judge") != "independent_model":
                yield Issue(path, f"{tid}: judge must be independent_model", doc.line("tests", i, "judge") or doc.line("tests", i))
            if test.get("evidence") != "required":
                yield Issue(path, f"{tid}: evidence must be required", doc.line("tests", i, "evidence") or doc.line("tests", i))
            where = test.get("where")
            texts = where if isinstance(where, list) else [where]
            if not any(isinstance(w, str) and w.strip() for w in texts):
                yield Issue(path, f"{tid}: qualitative test needs where (the documents the judge reads)",
                            doc.line("tests", i, "where") or doc.line("tests", i))
            lookback = test.get("lookback")
            if not (isinstance(lookback, int) and not isinstance(lookback, bool) and lookback >= 1):
                yield Issue(path, f"{tid}: lookback must be a positive number of periods, found {lookback!r}",
                            doc.line("tests", i, "lookback") or doc.line("tests", i))


@check("C-STALENESS")
def c_staleness(ctx: Context) -> Iterator[Issue]:
    for path, doc, data in theses(ctx.repo):
        for res in evaluate(data, ctx.today):
            if res.result == "fail":
                msg = (f"{res.test}: reviewed.{res.section} = {res.reviewed} is {res.age_days} days old "
                       f"(limit {res.limit_days} days); re-review the section")
            elif res.result == "undetermined":
                msg = f"{res.test}: cannot evaluate staleness ({res.note})"
            else:
                continue
            yield Issue(path, msg, doc.line("reviewed", res.section) if res.section else doc.line("tests", res.index))
