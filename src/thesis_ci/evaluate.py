"""Evaluate the quantitative thesis tests of one company against metric readings (SPEC 4.5).

``evaluate_company(thesis, readings, period, today)`` turns the tests registered in a ``thesis.yml`` and a list of
readings (``readings.py``) into a ``ci_results`` document (``spec/schemas/ci-results.schema.json``): for every
quantitative test in force for the period, a result (``pass``, ``warn``, ``fail``, ``undetermined`` or ``not_due``)
with the readings it rests on and the reason.

How a rule is judged:

- A rule is a tree. A leaf compares one metric with its threshold (``op``); ``all_of`` / ``any_of`` combine
  sub-rules. A sub-rule without ``period`` inherits its parent's (the root's default is the frequency of the test's
  metric, else ``quarter``). ``consecutive`` is not inherited: on a leaf it asks the comparison to hold in each of
  the last N periods; on ``all_of`` / ``any_of`` it asks the combination to hold, in the same period, in each of
  the last N periods.
- The evaluation period is a fiscal quarter. A ``quarter`` or ``event`` rule reads that quarter, a ``half`` rule
  the half that ends with it (Q2 or Q4), a ``year`` rule the fiscal year that ends with it (Q4). A rule whose
  period does not end with the evaluation quarter, whose ``evaluate_on`` does not name it, or whose
  ``evaluate_from`` is later, is not due. ``all_of`` is due only when every sub-rule is due; ``any_of`` when at
  least one is, and only its due sub-rules are judged.
- ``evaluate_from`` also starts the count of ``consecutive``: periods before it never count toward the run. It
  applies to the node that carries it and to everything below it.
- ``increase`` / ``decrease`` compare a reading with the reading of the same period one fiscal year earlier (the
  previous year for a ``year`` rule, the same quarter a year earlier for a ``quarter`` rule), as the Lynch templates
  and the archives write them ("down year on year"). The change must exceed the threshold. In ``pp`` it is the
  difference of two percentages; in ``%`` on a metric that is not itself a percentage it is the relative change;
  in the metric's own unit it is the difference.
- Three-valued logic: a leaf whose reading is missing is undetermined; ``all_of`` is not triggered as soon as one
  due sub-rule is not triggered, whatever the others; ``any_of`` is triggered as soon as one is. A run of
  ``consecutive`` periods is undetermined whenever its latest period cannot be judged, even if an earlier period
  already breaks the run: a result for a period rests on that period's data.
- A reading with ``value: null`` was checked and has nothing to measure (no qualifying event, or not computed by
  the metric's definition): the comparison does not hold. A missing reading is never guessed.
- The fail rule is judged first; ``warn_rule`` only when the fail rule is not triggered.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import yaml

from . import __version__, contract
from .periods import (Fiscal, fiscal_year_end, in_force_for, parse_fiscal, period_at, period_dates, period_key,
                      quarter_index, from_quarter_index, QUARTERS_PER)
from .readings import Index, compatible, convert, normalize_unit
from .repo import dig, is_number, jsonable

RESULTS = ("pass", "warn", "fail", "undetermined", "not_due")
COMPARISONS = {"<": lambda v, t: v < t, "<=": lambda v, t: v <= t, ">": lambda v, t: v > t,
               ">=": lambda v, t: v >= t, "==": lambda v, t: v == t, "!=": lambda v, t: v != t}
CHANGES = ("increase", "decrease")
RANGES = ("between", "outside")
OPS = set(COMPARISONS) | set(CHANGES) | set(RANGES) | {"event"}
PERIODS = ("quarter", "half", "year", "event")

# Node states. "triggered" means the rule's condition holds (for the fail rule: the test fails).
TRIGGERED, NOT_TRIGGERED, UNDETERMINED, NOT_DUE = "triggered", "not_triggered", "undetermined", "not_due"


class RuleError(ValueError):
    """A rule shape the engine does not understand; the test is reported undetermined."""


# --------------------------------------------------------------------------------------------------- parsing


@dataclass
class Metric:
    """What a leaf reads: the reading key and what the test's definitions say about it."""

    key: str  # the ``metric`` of the readings: registry id, own id, <metric>.<component>, or a test id
    unit: str | None = None
    data: str | None = None
    where: str | None = None
    xbrl: list[str] | None = None


@dataclass
class Node:
    """One node of a parsed rule tree."""

    kind: str  # "leaf" | "all_of" | "any_of"
    path: str  # where it sits in the test, e.g. "rule.all_of[1]"
    period: str  # quarter | half | year | event (inherited when not written)
    consecutive: int = 1
    evaluate_on: list[Fiscal] | None = None
    evaluate_from: Fiscal | None = None
    metric: Metric | None = None
    op: str | None = None
    threshold: Any = None
    unit: str | None = None
    children: list[Node] = field(default_factory=list)

    @property
    def step(self) -> int:
        """How many fiscal quarters one period of this node spans."""
        return QUARTERS_PER.get(self.period, 1)

    def leaves(self) -> Iterator[Node]:
        if self.kind == "leaf":
            yield self
        for child in self.children:
            yield from child.leaves()


def _unit_of(period: str) -> str:
    """The calendar unit of a rule period: an event is read quarter by quarter."""
    return "quarter" if period == "event" else period


def _composite_unit(unit: Any) -> bool:
    """A metric unit that describes several components at once ("% / pp (by component)")."""
    return isinstance(unit, str) and ("by component" in unit or " / " in unit)


class Definitions:
    """The parts of one quantitative test that the rules refer to: its metric, components and segment."""

    def __init__(self, test: dict):
        self.test = test
        self.id = str(test.get("id") or "?")
        md = test.get("metric_def")
        self.metric_def: dict = md if isinstance(md, dict) else {}
        comps = self.metric_def.get("components")
        self.components: dict = comps if isinstance(comps, dict) else {}
        registry = contract.metrics()
        metric = test.get("metric") if isinstance(test.get("metric"), str) else None
        md_id = self.metric_def.get("id") if isinstance(self.metric_def.get("id"), str) else None
        self.own = [m for m in (metric, md_id) if m]
        self.primary = metric or md_id
        base = registry.get(metric) if metric else None
        self.own_def: dict = {**(base or {}), **self.metric_def} if (base or self.metric_def) else {}
        legacy = dig(test, "params", "metric_defs")
        self.legacy = {d["id"]: d for d in legacy if isinstance(d, dict) and isinstance(d.get("id"), str)} \
            if isinstance(legacy, list) else {}
        segment = dig(test, "params", "segment")
        self.segment = segment if isinstance(segment, str) and segment.strip() else None
        freq = self.own_def.get("frequency")
        self.frequency = freq if freq in PERIODS else "quarter"

    def resolve(self, name: Any, op: Any, where: str) -> Metric:
        """The metric a leaf reads; raises RuleError when the name does not resolve (SPEC 4.1)."""
        registry = contract.metrics()
        if name is None:
            if op == "event":
                return Metric(self.id, None, self.metric_def.get("data") or self.test.get("data"),
                              self.metric_def.get("where"))
            if not self.primary:
                raise RuleError(f"{where}: names no metric, and the test's metric has no id")
            name = self.primary
        if not isinstance(name, str):
            raise RuleError(f"{where}: metric {name!r} is not a metric id")
        base, _, comp = name.partition(".")
        if comp:
            if base in self.own:
                if comp not in self.components:
                    raise RuleError(f"{where}: metric {name!r} names a component metric_def does not define")
                return self._component(name, comp)
            if base in registry or base in self.legacy:
                return Metric(name)  # a component of a definition outside this test: its unit is unknown
            raise RuleError(f"{where}: metric {name!r} does not resolve")
        if name in self.components and name not in self.own:
            return self._component(f"{self.primary}.{name}", name)
        if name in self.own:
            d = self.own_def
            return Metric(name, d.get("unit"), d.get("data") or self.test.get("data"), d.get("where"), d.get("xbrl"))
        if name in registry:
            d = registry[name]
            return Metric(name, d.get("unit"), d.get("data"), d.get("where"), d.get("xbrl"))
        if name in self.legacy:
            d = self.legacy[name]
            return Metric(name, d.get("unit"), d.get("data"), d.get("where"), d.get("xbrl"))
        raise RuleError(f"{where}: metric {name!r} is not in spec/metrics.yml and not defined in the test")

    def _component(self, key: str, comp: str) -> Metric:
        if key.startswith("None."):
            raise RuleError(f"component {comp!r} cannot be read: the test's metric has no id (write metric_def.id)")
        d = self.components[comp] if isinstance(self.components[comp], dict) else {}
        data = "xbrl" if d.get("xbrl") else self.metric_def.get("data") or self.test.get("data")
        return Metric(key, d.get("unit"), data, d.get("where") or self.metric_def.get("where"), d.get("xbrl"))


def _fiscal_list(value: Any, where: str) -> list[Fiscal]:
    if not isinstance(value, list) or not value:
        raise RuleError(f"{where}.evaluate_on must be a non-empty list of FY<year> or FY<year>Q<quarter>")
    out = []
    for item in value:
        p = parse_fiscal(item)
        if p is None or p.unit == "half":
            raise RuleError(f"{where}.evaluate_on: {item!r} is not FY<year> or FY<year>Q<quarter>")
        out.append(p)
    return out


def parse_rule(rule: Any, definition: Definitions, where: str = "rule", period: str | None = None) -> Node:
    """Parse one rule (or sub-rule) into a Node; raises RuleError for a shape the engine does not understand."""
    if not isinstance(rule, dict):
        raise RuleError(f"{where} must be a mapping")
    kinds = [k for k in ("op", "all_of", "any_of") if k in rule]
    if len(kinds) != 1:
        raise RuleError(f"{where} needs exactly one of op, all_of, any_of (found {', '.join(kinds) or 'none'})")
    own_period = rule.get("period")
    if own_period is not None and own_period not in PERIODS:
        raise RuleError(f"{where}.period {own_period!r} is not one of {', '.join(PERIODS)}")
    node_period = own_period or period or definition.frequency
    consecutive = rule.get("consecutive", 1)
    if not (isinstance(consecutive, int) and not isinstance(consecutive, bool) and consecutive >= 1):
        raise RuleError(f"{where}.consecutive must be a positive integer")
    node = Node(kind="leaf" if kinds[0] == "op" else kinds[0], path=where, period=node_period, consecutive=consecutive)
    if "evaluate_on" in rule:
        node.evaluate_on = _fiscal_list(rule["evaluate_on"], where)
    if "evaluate_from" in rule:
        start = parse_fiscal(rule["evaluate_from"])
        if start is None or start.unit == "half":
            raise RuleError(f"{where}.evaluate_from {rule['evaluate_from']!r} is not FY<year> or FY<year>Q<quarter>")
        node.evaluate_from = start
    if node.kind == "leaf":
        _parse_leaf(rule, node, definition, where)
        _check_evaluate_on(node)
        return node
    subs = rule[node.kind]
    if not isinstance(subs, list) or not subs:
        raise RuleError(f"{where}.{node.kind} must be a non-empty list of rules")
    node.children = [parse_rule(sub, definition, f"{where}.{node.kind}[{i}]", node_period) for i, sub in enumerate(subs)]
    if node.consecutive > 1:
        for leaf in node.leaves():
            if leaf.period != node.period:
                raise RuleError(f"{where}: consecutive {node.consecutive} counts {node.period}s, but {leaf.path} "
                                f"is judged by {leaf.period}")
    _check_evaluate_on(node)
    return node


def _check_evaluate_on(node: Node) -> None:
    """A quarter named in evaluate_on must be one in which a year or half rule can be judged."""
    if node.evaluate_on is None or not (node.kind == "leaf" or node.consecutive > 1):
        return
    for entry in node.evaluate_on:
        if entry.unit == "quarter" and period_at(_unit_of(node.period), entry.end_quarter) is None:
            raise RuleError(f"{node.path}.evaluate_on: no {node.period} ends with {entry.label}, so the rule would "
                            f"never be judged")


def _parse_leaf(rule: dict, node: Node, definition: Definitions, where: str) -> None:
    op, threshold, unit = rule.get("op"), rule.get("threshold"), rule.get("unit")
    if op not in OPS:
        raise RuleError(f"{where}: unknown op {op!r}")
    if unit is not None and not isinstance(unit, str):
        raise RuleError(f"{where}.unit must be a string")
    node.op, node.threshold, node.unit = op, threshold, unit
    node.metric = definition.resolve(rule.get("metric"), op, where)
    metric_unit = node.metric.unit
    if op in COMPARISONS or op in CHANGES:
        if not is_number(threshold):
            raise RuleError(f"{where}: op {op!r} needs a numeric threshold")
    elif op in RANGES:
        if not (isinstance(threshold, list) and len(threshold) == 2 and all(is_number(x) for x in threshold)
                and threshold[0] <= threshold[1]):
            raise RuleError(f"{where}: op {op!r} needs threshold [low, high] with low <= high")
    if op == "event" or unit is None or metric_unit is None or _composite_unit(metric_unit):
        pass
    elif op in CHANGES:
        if normalize_unit(unit) == "pp":
            if normalize_unit(metric_unit) not in ("%", "pp"):
                raise RuleError(f"{where}: a change in pp needs a metric in % or pp, not {metric_unit!r}")
        elif normalize_unit(unit) == "%":
            if normalize_unit(metric_unit) == "%":
                raise RuleError(f"{where}: a change of a percentage in '%' is ambiguous; write the threshold in pp")
        elif not compatible(unit, metric_unit):
            raise RuleError(f"{where}: unit {unit!r} does not fit the metric's unit {metric_unit!r}")
    elif not compatible(unit, metric_unit):
        raise RuleError(f"{where}: unit {unit!r} does not fit the metric's unit {metric_unit!r}")
    if op in CHANGES and node.period == "event":
        raise RuleError(f"{where}: op {op!r} compares with a year earlier, which an event period does not have")


def parse_test(test: dict) -> tuple[Definitions, Node | None, Node | None]:
    """Parse a quantitative test's rule and warn_rule; raises RuleError when either is not understood."""
    definition = Definitions(test)
    if "rule" not in test:
        raise RuleError("the test has no rule")
    rule = parse_rule(test["rule"], definition, "rule")
    warn = parse_rule(test["warn_rule"], definition, "warn_rule") if "warn_rule" in test else None
    events = {repr(leaf.threshold) for tree in (rule, warn) if tree for leaf in tree.leaves()
              if leaf.op == "event" and leaf.metric and leaf.metric.key == definition.id}
    if len(events) > 1:
        raise RuleError("several op: event sub-rules name no metric; their readings could not be told apart "
                        "(give each a metric_def component)")
    return definition, rule, warn


def shape_problems(test: dict) -> list[str]:
    """Why the engine cannot evaluate a quantitative test's rules (empty when it can). Used by C-TEST-METRIC."""
    try:
        parse_test(test)
    except RuleError as exc:
        return [str(exc)]
    return []


# ------------------------------------------------------------------------------------------------ evaluation

_AND = {TRIGGERED: 2, UNDETERMINED: 1, NOT_TRIGGERED: 0}


def kleene_and(states: list[str]) -> str:
    """Three-valued AND: not triggered wins, then undetermined."""
    return min(states, key=_AND.__getitem__) if states else TRIGGERED


def kleene_or(states: list[str]) -> str:
    """Three-valued OR: triggered wins, then undetermined."""
    return max(states, key=_AND.__getitem__) if states else NOT_TRIGGERED


def _fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


class _Run:
    """The evaluation of one test at one evaluation quarter: what was read, what was missing, what went wrong."""

    def __init__(self, definition: Definitions, index: Index, now: tuple[int, int]):
        self.d = definition
        self.index = index
        self.now = now
        self.used: dict[int, dict] = {}
        self.missing: list[dict] = []
        self.issues: list[str] = []
        self.rule_name = "rule"

    # ---- dueness

    def due(self, node: Node, after: Fiscal | None = None) -> tuple[bool, str]:
        """Whether ``node`` is judged at the evaluation quarter, and why not."""
        start = _later(after, node.evaluate_from)
        if node.kind == "leaf" or node.consecutive > 1:
            if period_at(_unit_of(node.period), self.now) is None:
                ends = "a fiscal year ends (Q4)" if node.period == "year" else "a fiscal half ends (Q2, Q4)"
                return False, f"{node.path} is judged by {node.period}, only when {ends}"
        if node.evaluate_on is not None and not any(_matches(p, self.now) for p in node.evaluate_on):
            names = ", ".join(p.label for p in node.evaluate_on)
            return False, f"{node.path} is judged only in {names}"
        if start is not None and quarter_index(self.now) < quarter_index(start.start_quarter):
            return False, f"{node.path} is judged from {start.label} on"
        if node.kind == "leaf":
            return True, ""
        verdicts = [self.due(child, start) for child in node.children]
        if node.kind == "all_of" and not all(ok for ok, _ in verdicts):
            return False, next(why for ok, why in verdicts if not ok)
        if node.kind == "any_of" and not any(ok for ok, _ in verdicts):
            return False, verdicts[0][1]
        return True, ""

    # ---- judging

    def judge(self, node: Node, end: tuple[int, int], after: Fiscal | None = None) -> dict:
        """Judge a due node at the window position ending with fiscal quarter ``end``."""
        start = _later(after, node.evaluate_from)
        if node.kind == "leaf":
            return self._leaf(node, end, start)
        if node.consecutive > 1:
            window = []
            for i in range(node.consecutive):
                pos = from_quarter_index(quarter_index(end) - i * node.step)
                period = period_at(_unit_of(node.period), pos)
                if start is not None and quarter_index(pos) < quarter_index(start.start_quarter):
                    window.append({"period": period.label, "state": NOT_TRIGGERED,
                                   "note": f"before evaluate_from {start.label}; does not count"})
                    continue
                children = self._combine_children(node, pos, start)
                window.append({"period": period.label, "state": children["state"], "children": children["children"]})
            state = _window_state(window)
            return {"kind": node.kind, "path": node.path, "period": node.period, "consecutive": node.consecutive,
                    "state": state, "consecutive_count": _run_length(window), "window": window}
        combined = self._combine_children(node, end, start)
        return {"kind": node.kind, "path": node.path, **combined}

    def _combine_children(self, node: Node, end: tuple[int, int], start: Fiscal | None) -> dict:
        results = []
        for child in node.children:
            ok, why = self.due(child, start) if end == self.now else (True, "")
            if not ok:  # only any_of reaches here with a sub-rule that is not due
                results.append({"kind": child.kind, "path": child.path, "state": NOT_DUE, "reason": why})
                continue
            results.append(self.judge(child, end, start))
        states = [r["state"] for r in results if r["state"] != NOT_DUE]
        state = kleene_and(states) if node.kind == "all_of" else kleene_or(states)
        return {"state": state, "children": results}

    def _leaf(self, node: Node, end: tuple[int, int], start: Fiscal | None) -> dict:
        key, segment = node.metric.key, self.d.segment
        labels = self.index.series(key, segment)
        out: dict = {"kind": "leaf", "path": node.path, "metric": key, "op": node.op, "threshold": node.threshold,
                     "unit": node.unit, "period": node.period, "consecutive": node.consecutive}
        if segment:
            out["segment"] = segment
        if len(labels) > 1 and None in labels:
            self.issues.append(f"{key}: some readings name a series and some do not")
            out.update(state=UNDETERMINED, consecutive_count=0, window=[])
            return out
        per_series = []
        for label in sorted(labels, key=str) if labels and labels != {None} else [None]:
            window = []
            for i in range(node.consecutive):
                pos = from_quarter_index(quarter_index(end) - i * node.step)
                period = period_at(_unit_of(node.period), pos)
                if start is not None and quarter_index(pos) < quarter_index(start.start_quarter):
                    window.append({"period": period.label, "state": NOT_TRIGGERED,
                                   "note": f"before evaluate_from {start.label}; does not count"})
                else:
                    window.append(self._condition(node, period, label))
            per_series.append((label, window))
        states = [_window_state(window) for _label, window in per_series]
        out["state"] = kleene_or(states)
        if len(per_series) == 1:
            out["consecutive_count"] = _run_length(per_series[0][1])
            out["window"] = per_series[0][1]
        else:
            out["consecutive_count"] = max(_run_length(w) for _l, w in per_series)
            out["series"] = [{"series": label, "state": state, "consecutive_count": _run_length(window),
                              "window": window} for (label, window), state in zip(per_series, states)]
        return out

    def _reading(self, key: str, period: Fiscal, series: str | None) -> tuple[dict | None, str | None]:
        """The reading of ``key`` for ``period`` (and series), or (None, why not)."""
        rows = [r for r in self.index.get(key, self.d.segment, period.label) if r.get("series") == series]
        if not rows:
            entry = {"metric": key, "period": period.label, "rule": self.rule_name}
            if self.d.segment:
                entry["segment"] = self.d.segment
            if series:
                entry["series"] = series
            if entry not in self.missing:
                self.missing.append(entry)
            return None, "no reading"
        first = rows[0]
        if any((r.get("value"), normalize_unit(r.get("unit"))) != (first.get("value"), normalize_unit(first.get("unit")))
               for r in rows[1:]):
            self.issues.append(f"{key} {period.label}: conflicting readings")
            return None, "conflicting readings"
        self.used[id(first)] = first
        return first, None

    def _condition(self, node: Node, period: Fiscal, series: str | None) -> dict:
        """Judge a leaf's comparison in one period."""
        entry: dict = {"period": period.label}
        reading, why = self._reading(node.metric.key, period, series)
        if reading is None:
            entry.update(state=UNDETERMINED, note=why)
            return entry
        value, unit = reading.get("value"), reading.get("unit")
        entry.update(value=value, reading_unit=unit, source=reading.get("source"))
        if value is None:
            entry.update(state=NOT_TRIGGERED, note=f"nothing to measure: {reading.get('note', '')}".rstrip(": "))
            return entry
        if node.op == "event":
            if not isinstance(value, bool):
                return self._fail(entry, f"{node.metric.key} {period.label}: an event reading must be true or false")
            entry["state"] = TRIGGERED if value else NOT_TRIGGERED
            return entry
        if not is_number(value):
            return self._fail(entry, f"{node.metric.key} {period.label}: a reading of {value!r} is not a number")
        if node.op in CHANGES:
            return self._change(node, period, series, reading, entry)
        if node.unit is not None:
            converted = convert(value, unit, node.unit)
            if converted is None:
                return self._fail(entry, f"{node.metric.key} {period.label}: reading in {unit!r}, rule in {node.unit!r}")
            if converted != value:
                entry["value_in_rule_unit"] = converted
            value = converted
        if node.op in COMPARISONS:
            held = COMPARISONS[node.op](value, node.threshold)
        else:
            low, high = node.threshold
            inside = low <= value <= high
            held = inside if node.op == "between" else not inside
        entry["state"] = TRIGGERED if held else NOT_TRIGGERED
        return entry

    def _change(self, node: Node, period: Fiscal, series: str | None, reading: dict, entry: dict) -> dict:
        base_period = period.year_ago()
        base, why = self._reading(node.metric.key, base_period, series)
        if base is None:
            entry.update(state=UNDETERMINED, note=f"{why} for {base_period.label} (the comparison base)")
            return entry
        entry["base"] = {"period": base_period.label, "value": base.get("value"), "reading_unit": base.get("unit")}
        if base.get("value") is None:
            entry.update(state=NOT_TRIGGERED, note=f"nothing to measure in {base_period.label}: {base.get('note', '')}")
            return entry
        if not is_number(base.get("value")):
            return self._fail(entry, f"{node.metric.key} {base_period.label}: a reading of {base['value']!r} is not a number")
        cur, cur_unit = reading["value"], reading.get("unit")
        prev = convert(base["value"], base.get("unit"), cur_unit)
        if prev is None:
            return self._fail(entry, f"{node.metric.key}: {period.label} in {cur_unit!r}, {base_period.label} "
                                     f"in {base.get('unit')!r}")
        rule_unit = normalize_unit(node.unit)
        if rule_unit == "pp":
            if normalize_unit(cur_unit) not in ("%", "pp"):
                return self._fail(entry, f"{node.metric.key}: a change in pp needs readings in %, not {cur_unit!r}")
            change = cur - prev
        elif rule_unit == "%":
            if normalize_unit(cur_unit) == "%":
                return self._fail(entry, f"{node.metric.key}: a change of a percentage in '%' is ambiguous")
            if prev == 0:
                return self._fail(entry, f"{node.metric.key}: no relative change from a zero base in {base_period.label}")
            change = (cur - prev) / abs(prev) * 100
        elif rule_unit is None:
            change = cur - prev
        else:
            a, b = convert(cur, cur_unit, node.unit), convert(prev, cur_unit, node.unit)
            if a is None or b is None:
                return self._fail(entry, f"{node.metric.key}: readings in {cur_unit!r}, rule in {node.unit!r}")
            change = a - b
        entry["change"] = round(change, 10)
        held = change > node.threshold if node.op == "increase" else -change > node.threshold
        entry["state"] = TRIGGERED if held else NOT_TRIGGERED
        return entry

    def _fail(self, entry: dict, issue: str) -> dict:
        self.issues.append(issue)
        entry.update(state=UNDETERMINED, note=issue)
        return entry


def _later(a: Fiscal | None, b: Fiscal | None) -> Fiscal | None:
    if a is None or b is None:
        return a or b
    return a if quarter_index(a.start_quarter) >= quarter_index(b.start_quarter) else b


def _matches(entry: Fiscal, now: tuple[int, int]) -> bool:
    """evaluate_on: FY<year>Q<q> names one quarter; FY<year> names every quarter of that fiscal year."""
    if entry.unit == "quarter":
        return entry.end_quarter == now
    return entry.year == now[0]


def _window_state(window: list[dict]) -> str:
    """The state of a run of periods, latest first: undetermined when the latest period cannot be judged (a result
    for a period rests on that period's data), else three-valued AND over the run."""
    if window and window[0]["state"] == UNDETERMINED:
        return UNDETERMINED
    return kleene_and([w["state"] for w in window])


def _run_length(window: list[dict]) -> int:
    """How many periods in a row, counting back from the latest, the condition held."""
    count = 0
    for w in window:
        if w["state"] != TRIGGERED:
            break
        count += 1
    return count


# ------------------------------------------------------------------------------------------------- results


def _first_leaf_reading(tree: dict | None) -> tuple[str, str] | None:
    """(metric, period) of the first leaf's latest period in a judged tree."""
    if not tree:
        return None
    if tree.get("kind") == "leaf":
        window = tree.get("window") or (tree.get("series") or [{}])[0].get("window") or []
        return (tree["metric"], window[0]["period"]) if window else None
    for part in tree.get("children") or []:
        found = _first_leaf_reading(part)
        if found:
            return found
    for pos in tree.get("window") or []:
        for part in pos.get("children") or []:
            found = _first_leaf_reading(part)
            if found:
                return found
    return None


def _describe(tree: dict) -> str:
    """A one-line account of a judged tree for the result's reason."""
    if tree.get("state") == NOT_DUE:
        return tree.get("reason", "not due")
    if tree.get("kind") == "leaf":
        threshold = tree["threshold"]
        if tree["op"] in RANGES:
            threshold = f"[{_fmt(threshold[0])}, {_fmt(threshold[1])}]"
        head = f"{tree['metric']} {tree['op']} {_fmt(threshold) if tree['op'] != 'event' else ''}".rstrip()
        if tree.get("unit") and tree["op"] != "event":
            head += f" {tree['unit']}"
        window = tree.get("window") or []
        values = ", ".join(_window_text(w) for w in window)
        if tree.get("series"):
            values = "; ".join(f"{s['series']}: " + ", ".join(_window_text(w) for w in s["window"]) for s in tree["series"])
        runs = f" ({tree['consecutive_count']} of {tree['consecutive']} consecutive {tree['period']}s)" \
            if tree["consecutive"] > 1 else ""
        return f"{head} -> {tree['state']}{runs} [{values}]"
    parts = tree.get("children") or []
    if tree.get("window"):
        parts = [c for pos in tree["window"][:1] for c in pos.get("children", [])]
    inner = "; ".join(_describe(p) for p in parts)
    runs = f" in {tree['consecutive_count']} of {tree['consecutive']} consecutive {tree['period']}s" \
        if tree.get("consecutive", 1) > 1 else ""
    return f"{tree['kind']} -> {tree['state']}{runs} ({inner})"


def _window_text(w: dict) -> str:
    if "value" not in w:
        return f"{w['period']}: {w.get('note', 'no reading')}"
    text = f"{w['period']}: {_fmt(w['value'])}"
    if w.get("reading_unit") and not isinstance(w["value"], bool) and w["value"] is not None:
        text += f" {w['reading_unit']}"
    if "change" in w:
        text += f" (change {_fmt(w['change'])} vs {w['base']['period']})"
    if w.get("state") == UNDETERMINED and w.get("note"):
        text += f" ({w['note']})"
    return text


def _public_reading(r: dict) -> dict:
    keys = ("metric", "period", "value", "unit", "source", "basis", "note", "segment", "series")
    return {k: r[k] for k in keys if k in r}


def evaluate_test(test: dict, index: Index, period: str) -> dict:
    """Evaluate one quantitative test in force for ``period`` (FY<year>Q<quarter>) against indexed readings."""
    now = period_key(period)
    if now is None:
        raise ValueError(f"not a fiscal quarter FY<year>Q<quarter>: {period!r}")
    out: dict = {"id": test.get("id"), "severity": test.get("severity"), "claim": test.get("claim")}
    metric = test.get("metric") or dig(test, "metric_def", "id")
    out.update(metric=metric, data=test.get("data"))
    if dig(test, "params", "segment"):
        out["segment"] = dig(test, "params", "segment")
    for key in ("fail_if", "warn_if"):
        if key in test:
            out[key] = test[key]
    out["rule"] = test.get("rule")
    if "warn_rule" in test:
        out["warn_rule"] = test["warn_rule"]
    rule = test.get("rule") if isinstance(test.get("rule"), dict) else {}
    if "op" in rule:
        out.update(op=rule.get("op"), threshold=rule.get("threshold"), unit=rule.get("unit"))
    out["consecutive"] = rule.get("consecutive", 1) if "op" in rule or "consecutive" in rule else None
    if test.get("supersedes"):
        out["supersedes"] = test["supersedes"]
    try:
        definition, fail_node, warn_node = parse_test(test)
    except RuleError as exc:
        out.update(result="undetermined", reason=f"rule not understood by the engine: {exc}", consecutive_count=None,
                   reading=None, readings=[], missing=[], evaluation={"fail": None, "warn": None})
        return out
    run = _Run(definition, index, now)
    fail_tree = _judge_rule(run, fail_node, "rule")
    warn_tree = None
    if warn_node is not None and fail_tree["state"] != TRIGGERED:
        warn_tree = _judge_rule(run, warn_node, "warn_rule")
    result, reason = _verdict(fail_tree, warn_tree, run)
    out["result"] = result
    out["reason"] = reason
    out["consecutive_count"] = fail_tree.get("consecutive_count")
    first = _first_leaf_reading(fail_tree) or _first_leaf_reading(warn_tree)
    primary = None
    if first:
        rows = index.get(first[0], definition.segment, first[1])
        primary = _public_reading(rows[0]) if len(rows) == 1 else None
    out["reading"] = primary
    out["readings"] = sorted((_public_reading(r) for r in run.used.values()),
                             key=lambda r: (r["metric"], _period_sort(r["period"]), str(r.get("series"))))
    # A determinate result did not depend on the readings that were missing, so they are listed only when the
    # result is undetermined; needed_readings() lists everything a test reads.
    out["missing"] = run.missing if result == "undetermined" else []
    out["evaluation"] = {"fail": fail_tree, "warn": warn_tree}
    return out


def _period_sort(label: str) -> tuple:
    p = parse_fiscal(label)
    return (quarter_index(p.end_quarter), p.unit) if p else (0, label)


def _judge_rule(run: _Run, node: Node, name: str) -> dict:
    run.rule_name = name
    ok, why = run.due(node)
    if not ok:
        return {"kind": node.kind, "path": node.path, "state": NOT_DUE, "reason": why}
    return run.judge(node, run.now)


def _verdict(fail: dict, warn: dict | None, run: _Run) -> tuple[str, str]:
    """The test result from the judged fail and warn rules, and a one-line reason."""
    fs, ws = fail["state"], (warn or {}).get("state")
    problems = "; ".join(dict.fromkeys(run.issues))

    def gaps(rule: str) -> str:
        missing = "; ".join(f"{m['metric']} {m['period']}" + (f" [series {m['series']}]" if m.get("series") else "")
                            for m in run.missing if m["rule"] == rule)
        return "; ".join(x for x in (f"missing readings: {missing}" if missing else "", problems) if x) or "no reading"

    if fs == TRIGGERED:
        return "fail", f"fail rule triggered: {_describe(fail)}"
    if fs == UNDETERMINED:
        tail = f"; warn_rule {ws}" if ws else ""
        return "undetermined", f"fail rule undetermined ({gaps('rule')}): {_describe(fail)}{tail}"
    if fs == NOT_DUE and ws in (None, NOT_DUE):
        why = fail.get("reason", "")
        if ws == NOT_DUE:
            why += f"; warn_rule: {warn.get('reason', '')}"
        return "not_due", why
    head = "fail rule not triggered" if fs == NOT_TRIGGERED else f"fail rule not due ({fail.get('reason')})"
    if fs == NOT_TRIGGERED:
        head += f": {_describe(fail)}"
    if ws == TRIGGERED:
        return "warn", f"warn_rule triggered: {_describe(warn)}; {head}"
    if ws == UNDETERMINED:
        return "undetermined", f"warn_rule undetermined ({gaps('warn_rule')}): {_describe(warn)}; {head}"
    if ws == NOT_TRIGGERED:
        head += f"; warn_rule not triggered: {_describe(warn)}"
    elif ws == NOT_DUE:
        head += f"; warn_rule not due ({warn.get('reason')})"
    return "pass", head


def evaluate_company(thesis: dict, readings: list[dict], period: str, today: dt.date) -> dict:
    """Evaluate every quantitative test of ``thesis`` in force for ``period`` and return a ci_results document.

    ``thesis`` is a parsed thesis.yml, ``readings`` the ``readings`` list of a readings document (readings.py),
    ``period`` the fiscal quarter being evaluated (``FY2026Q3``) and ``today`` the evaluation date. Readings of a
    period that ends after ``today`` are ignored (listed under ``ignored_readings``): they cannot be readings yet.
    Tests not in force (``effective_from`` later than the period, or ``retired_at`` reached) are listed under
    ``not_in_force``; qualitative and staleness tests are not evaluated here.
    """
    if period_key(period) is None:
        raise ValueError(f"not a fiscal quarter FY<year>Q<quarter>: {period!r}")
    thesis = jsonable(thesis)
    fye = fiscal_year_end(dig(thesis, "filer", "fiscal_year_end"))
    kept, ignored = [], []
    for r in readings if isinstance(readings, list) else []:
        p = parse_fiscal(r.get("period")) if isinstance(r, dict) else None
        if p is None:
            ignored.append({"reading": jsonable(r), "reason": "period is not FY<year>, FY<year>H<n> or FY<year>Q<n>"})
        elif period_dates(p, fye)[1] > today:
            ignored.append({"metric": r.get("metric"), "period": p.label,
                            "reason": f"{p.label} ends on {period_dates(p, fye)[1].isoformat()}, after {today.isoformat()}"})
        else:
            kept.append(jsonable(r))
    index = Index(kept)
    tests = [t for t in thesis.get("tests") or [] if isinstance(t, dict) and t.get("type") == "quantitative"]
    successors = {t.get("supersedes"): t.get("id") for t in thesis.get("tests") or [] if isinstance(t, dict)}
    results, not_in_force = [], []
    for test in tests:
        if in_force_for(test, period):
            results.append(evaluate_test(test, index, period))
            continue
        tid = test.get("id")
        if test.get("retired_at") and not in_force_for({**test, "effective_from": None}, period):
            reason = f"retired at {test['retired_at']}"
            if successors.get(tid):
                reason += f"; superseded by {successors[tid]}"
        else:
            reason = f"effective from {test.get('effective_from')}"
        not_in_force.append({"id": tid, "reason": reason})
    end = period_dates(parse_fiscal(period), fye)[1]
    warnings = []
    if end > today:
        warnings.append(f"{period} ends on {end.isoformat()}, after the evaluation date {today.isoformat()}")
    if not isinstance(dig(thesis, "filer", "fiscal_year_end"), str):
        warnings.append("filer.fiscal_year_end is missing; periods are dated as if the fiscal year ended on 12-31")
    summary = {name: sum(r["result"] == name for r in results) for name in RESULTS}
    return {
        "company": thesis.get("company"),
        "period": period,
        "evaluated_on": today.isoformat(),
        "engine": f"thesis-ci {__version__}",
        "summary": summary,
        "results": results,
        "not_in_force": not_in_force,
        "ignored_readings": ignored,
        "warnings": warnings,
    }


def needed_readings(thesis: dict, period: str) -> list[dict]:
    """The readings the quantitative tests in force need for ``period``: one entry per metric (and segment).

    Each entry lists the periods to read (the windows of ``consecutive`` and the year-earlier bases of
    ``increase`` / ``decrease``), the unit and data kind the definitions give, and the tests that use it. A
    pipeline uses it to decide what to compute from XBRL (metrics.py) and what to extract from filings.
    """
    now = period_key(period)
    if now is None:
        raise ValueError(f"not a fiscal quarter FY<year>Q<quarter>: {period!r}")
    needs: dict[tuple, dict] = {}
    for test in jsonable(thesis).get("tests") or []:
        if not (isinstance(test, dict) and test.get("type") == "quantitative" and in_force_for(test, period)):
            continue
        try:
            definition, fail_node, warn_node = parse_test(test)
        except RuleError:
            continue
        run = _Run(definition, Index([]), now)
        for node in (fail_node, warn_node):
            if node is not None and run.due(node)[0]:
                for leaf, periods in _leaf_periods(run, node, now, None):
                    key = (leaf.metric.key, definition.segment)
                    entry = needs.setdefault(key, {"metric": leaf.metric.key, "segment": definition.segment,
                                                   "periods": set(), "unit": leaf.metric.unit, "data": leaf.metric.data,
                                                   "where": leaf.metric.where, "xbrl": leaf.metric.xbrl, "tests": []})
                    entry["periods"].update(periods)
                    if definition.id not in entry["tests"]:
                        entry["tests"].append(definition.id)
    out = []
    for entry in needs.values():
        entry["periods"] = sorted(entry["periods"], key=_period_sort)
        out.append({k: v for k, v in entry.items() if v is not None})
    return sorted(out, key=lambda e: (e["metric"], str(e.get("segment"))))


def _leaf_periods(run: _Run, node: Node, end: tuple[int, int], after: Fiscal | None) -> Iterator[tuple[Node, set[str]]]:
    """(leaf, labels of the periods it reads) for every due leaf under ``node`` judged at quarter ``end``."""
    start = _later(after, node.evaluate_from)
    ends = [from_quarter_index(quarter_index(end) - i * node.step) for i in range(node.consecutive)]
    ends = [e for e in ends if start is None or quarter_index(e) >= quarter_index(start.start_quarter)]
    if node.kind == "leaf":
        labels = set()
        for e in ends:
            p = period_at(_unit_of(node.period), e)
            labels.add(p.label)
            if node.op in CHANGES:
                labels.add(p.year_ago().label)
        yield node, labels
        return
    for e in ends:
        for child in node.children:
            if e == run.now and not run.due(child, start)[0]:
                continue
            yield from _leaf_periods(run, child, e, start)


# ----------------------------------------------------------------------------------------------- archive I/O


def load_thesis(archive: str | Path, company: str) -> dict:
    """Read ``companies/<company>/thesis.yml`` from an archive; raises ValueError when it cannot be read."""
    path = Path(archive) / "companies" / company / "thesis.yml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read {path}: {exc}") from None
    except yaml.YAMLError as exc:
        raise ValueError(f"{path} is not valid YAML: {exc}") from None
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a mapping")
    return data
