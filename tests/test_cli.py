"""The thesis-ci command line: output shapes and exit codes."""

from __future__ import annotations

import json
import subprocess
import sys

import pytest

from thesis_ci import __version__, selftest
from thesis_ci.cli import main


def run_cli(capsys, *argv):
    code = main(list(argv))
    out = capsys.readouterr().out
    return code, out


def test_lint_json_shape_and_exit_zero(ws, capsys):
    code, out = run_cli(capsys, "lint", str(ws / "public"), "--format", "json", "--counterpart", str(ws / "private"),
                        "--today", "2026-09-24")
    data = json.loads(out)
    assert code == 0
    assert set(data) == {"repo", "visibility", "errors", "warnings", "checks_run"}
    assert data["visibility"] == "public" and data["errors"] == [] and data["warnings"] == []
    assert "C-PUBLIC-NO-VALUATION" in data["checks_run"] and "C-DISCOUNT-RATE" not in data["checks_run"]


def test_lint_private_runs_private_checks(ws, capsys):
    code, out = run_cli(capsys, "lint", str(ws / "private"), "--format", "json", "--today", "2026-09-24")
    data = json.loads(out)
    assert code == 0 and data["visibility"] == "private"
    assert "C-DISCOUNT-RATE" in data["checks_run"] and "C-STORY" not in data["checks_run"]


def test_lint_exit_one_on_error_with_finding_fields(ws, capsys):
    selftest.apply(ws, (selftest.before_story_end("Revenue grew 16%."),))
    code, out = run_cli(capsys, "lint", str(ws / "public"), "--format", "json", "--today", "2026-09-24")
    data = json.loads(out)
    assert code == 1
    assert data["errors"] == [{
        "check": "C-SRC-TAG",
        "file": "companies/ACME/story.md",
        "line": 15,
        "message": data["errors"][0]["message"],
    }]
    assert "16%" in data["errors"][0]["message"]


def test_lint_warnings_do_not_fail(ws, capsys):
    selftest.apply(ws, (selftest.replace("public/companies/ACME/sources.yml", "accession: 0000000001-26-000001", "accession: null"),))
    code, out = run_cli(capsys, "lint", str(ws / "public"), "--format", "json", "--today", "2026-09-24")
    data = json.loads(out)
    assert code == 0 and len(data["warnings"]) == 1 and data["warnings"][0]["check"] == "C-SRC-ACCESSION"


def test_lint_only_and_text_output(ws, capsys):
    selftest.apply(ws, (selftest.replace("public/constitution/decision-rights.yml", "initial: 1", "initial: 2"),))
    code, out = run_cli(capsys, "lint", str(ws / "public"), "--only", "C-DECISION-RIGHTS,C-STORY", "--only", "C-SCHEMA",
                        "--today", "2026-09-24")
    assert code == 1
    assert "constitution/decision-rights.yml:25: error [C-DECISION-RIGHTS] trust.initial must be 1" in out
    assert "3 checks on public repo" in out


def test_lint_usage_errors(ws, capsys):
    assert main(["lint", str(ws / "nope")]) == 2
    assert main(["lint", str(ws / "public"), "--only", "C-NOPE"]) == 2
    with pytest.raises(SystemExit) as exc:
        main(["lint", str(ws / "public"), "--today", "24/09/2026"])
    assert exc.value.code == 2


def test_checks_json(capsys):
    code, out = run_cli(capsys, "checks", "--format", "json")
    rows = json.loads(out)
    assert code == 0 and len(rows) == 35
    assert set(rows[0]) == {"id", "title", "scope", "level", "implemented", "selftest"}
    assert all(r["implemented"] and r["selftest"] == "pass" for r in rows)


def test_selftest_command(capsys):
    code, out = run_cli(capsys, "selftest")
    assert code == 0 and "35/35 checks pass" in out


def test_staleness_command(ws, capsys):
    code, out = run_cli(capsys, "staleness", str(ws / "public"), "--today", "2026-09-24", "--format", "json")
    data = json.loads(out)
    assert code == 0 and [r["result"] for r in data["results"]] == ["pass", "pass"]
    code, out = run_cli(capsys, "staleness", str(ws / "public"), "--today", "2027-06-01")
    assert code == 1 and "FAIL" in out and "ACME-S2" in out


def test_brier_command(tmp_path, capsys):
    path = tmp_path / "2026.yml"
    path.write_text(
        "year: 2026\nforecasts:\n"
        "  - {id: a, company: ACME, domain: other, statement: x, probability: 0.8, made_at: 2026-01-01,"
        " resolves_by: 2026-06-01, source_file: f, book: system, outcome: happened}\n"
        "  - {id: b, company: ACME, domain: other, statement: y, probability: 0.3, made_at: 2026-01-01,"
        " resolves_by: 2026-06-01, source_file: f, book: owner_override, outcome: pending}\n",
        encoding="utf-8",
    )
    code, out = run_cli(capsys, "brier", str(path), "--format", "json")
    data = json.loads(out)
    assert code == 0 and data["n_forecasts"] == 2 and data["n_resolved"] == 1
    assert data["overall"]["brier"] == pytest.approx(0.04)
    code, out = run_cli(capsys, "brier", str(path))
    assert "brier=0.0400" in out
    assert main(["brier", str(tmp_path / "missing.yml")]) == 2


def test_module_entry_point_and_version():
    proc = subprocess.run([sys.executable, "-m", "thesis_ci", "--version"], capture_output=True, text=True)
    assert proc.returncode == 0 and proc.stdout.strip() == f"thesis-ci {__version__}"
