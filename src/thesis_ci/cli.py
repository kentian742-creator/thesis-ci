"""Command line: thesis-ci lint | checks | selftest | staleness | brier."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

from . import __version__, brier, contract, engine, periods, selftest, staleness


def _date(value: str) -> dt.date:
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"not a YYYY-MM-DD date: {value!r}") from None


def _period(value: str) -> str:
    if not periods.is_period(value):
        raise argparse.ArgumentTypeError(f"not a fiscal period FY<year>Q<quarter>: {value!r}")
    return value


def _print_json(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def cmd_lint(args: argparse.Namespace) -> int:
    root = Path(args.path)
    if not root.is_dir():
        print(f"thesis-ci: {root} is not a directory", file=sys.stderr)
        return 2
    if args.counterpart and not Path(args.counterpart).is_dir():
        print(f"thesis-ci: counterpart {args.counterpart} is not a directory", file=sys.stderr)
        return 2
    only = [c.strip() for item in (args.only or []) for c in item.split(",") if c.strip()]
    known = {m["id"] for m in contract.registered_checks()}
    unknown = sorted(set(only) - known)
    if unknown:
        print(f"thesis-ci: unknown check id(s): {', '.join(unknown)}", file=sys.stderr)
        return 2
    report = engine.run(root, args.counterpart, args.today, only or None, args.expect_visibility,
                        args.base_ref, args.period)
    if args.format == "json":
        _print_json(report.as_dict())
    else:
        for f in report.findings:
            where = f"{f.file}:{f.line}" if f.line else f.file or "."
            print(f"{where}: {f.level} [{f.check}] {f.message}")
        print(f"thesis-ci: {len(report.errors)} error(s), {len(report.warnings)} warning(s); "
              f"{len(report.checks_run)} checks on {report.visibility} repo {report.repo}")
    return 1 if report.errors else 0


def cmd_checks(args: argparse.Namespace) -> int:
    registry = engine.load_checks()
    rows = []
    for meta in contract.registered_checks():
        cid = meta["id"]
        implemented = cid in registry
        passed = selftest.selftest_passes(cid) if implemented else False
        rows.append({"id": cid, "title": meta["title"], "scope": meta["scope"], "level": meta["level"],
                     "implemented": implemented, "selftest": "pass" if passed else "fail"})
    if args.format == "json":
        _print_json(rows)
    else:
        for r in rows:
            impl = "yes" if r["implemented"] else "NO"
            print(f"{r['id']:<24} {r['scope']:<9} {r['level']:<8} implemented={impl:<3} selftest={r['selftest']:<4} {r['title']}")
    return 0


def cmd_selftest(args: argparse.Namespace) -> int:
    results = selftest.run_all()
    failed = [r for r in results if not r.passed]
    if args.format == "json":
        _print_json([{"check": r.check, "passed": r.passed, "cases": r.cases, "problems": r.problems,
                      "skipped": r.skipped} for r in results])
    else:
        for r in results:
            print(f"{'PASS' if r.passed else 'FAIL'} {r.check} ({r.cases} violating fixture(s))")
            for problem in r.problems:
                print(f"     {problem}")
            for skipped in r.skipped:
                print(f"     skipped: {skipped}")
        print(f"thesis-ci selftest: {len(results) - len(failed)}/{len(results)} checks pass (spec: {contract.spec_dir()})")
    return 1 if failed else 0


def cmd_staleness(args: argparse.Namespace) -> int:
    if not Path(args.path).is_dir():
        print(f"thesis-ci: {args.path} is not a directory", file=sys.stderr)
        return 2
    today = args.today or dt.date.today()
    results = staleness.evaluate_repo(args.path, today)
    if args.format == "json":
        _print_json({"today": today.isoformat(), "results": [r.as_dict() for r in results]})
    else:
        for r in results:
            age = f"{r.age_days}d / {r.limit_days}d" if r.age_days is not None else r.note
            print(f"{r.result.upper():<12} {r.test:<12} {str(r.section):<14} reviewed {r.reviewed or '-':<10}  {age}")
        fails = sum(r.result == "fail" for r in results)
        print(f"thesis-ci staleness: {len(results)} tests, {fails} failing (as of {today.isoformat()})")
    return 1 if any(r.result == "fail" for r in results) else 0


def cmd_brier(args: argparse.Namespace) -> int:
    try:
        records = brier.load_records(args.files)
    except (OSError, ValueError) as exc:
        print(f"thesis-ci: {exc}", file=sys.stderr)
        return 2
    summary = brier.summarize(records)
    if args.format == "json":
        _print_json(summary)
    else:
        print(brier.format_text(summary))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="thesis-ci", description="Thesis as code: lint thesis archives.")
    parser.add_argument("--version", action="version", version=f"thesis-ci {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("lint", help="run every applicable check on an archive repository")
    p.add_argument("path", help="archive repository root (must contain repo.yml)")
    p.add_argument("--format", choices=["text", "json"], default="text")
    p.add_argument("--counterpart", help="the other archive (public <-> private) for cross-repository checks")
    p.add_argument("--today", type=_date, help="evaluation date, YYYY-MM-DD (default: today)")
    p.add_argument("--only", nargs="+", action="extend", metavar="CHECK_ID", help="run only these checks")
    p.add_argument("--expect-visibility", choices=["public", "private"],
                   help="lint as this visibility whatever repo.yml says, and fail if repo.yml says otherwise "
                        "(a public archive relabelled private would otherwise skip every public check)")
    p.add_argument("--base-ref", metavar="GIT_REF",
                   help="C-TEST-FROZEN: compare the thesis tests with this git ref (e.g. origin/main)")
    p.add_argument("--period", type=_period, metavar="FY<YEAR>Q<N>",
                   help="C-TEST-FROZEN: the period whose results are in; tests in force for it are frozen")
    p.set_defaults(func=cmd_lint)

    p = sub.add_parser("checks", help="list registered checks with implementation and selftest status")
    p.add_argument("--format", choices=["text", "json"], default="text")
    p.set_defaults(func=cmd_checks)

    p = sub.add_parser("selftest", help="prove every check flags a violating fixture and passes a clean one")
    p.add_argument("--format", choices=["text", "json"], default="text")
    p.set_defaults(func=cmd_selftest)

    p = sub.add_parser("staleness", help="evaluate the staleness tests of every companies/*/thesis.yml")
    p.add_argument("path")
    p.add_argument("--today", type=_date, help="evaluation date, YYYY-MM-DD (default: today)")
    p.add_argument("--format", choices=["text", "json"], default="text")
    p.set_defaults(func=cmd_staleness)

    p = sub.add_parser("brier", help="Brier score and calibration of resolved forecasts")
    p.add_argument("files", nargs="+", metavar="FILE", help="forecasts/<YYYY>.yml file(s)")
    p.add_argument("--format", choices=["text", "json"], default="text")
    p.set_defaults(func=cmd_brier)
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
