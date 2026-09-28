"""Check profiles (SPEC 8.6) and thesis-ci init."""

from __future__ import annotations

import datetime as dt
import re
import shutil
from pathlib import Path

import pytest
import yaml

from thesis_ci import contract, engine, scaffold, selftest
from thesis_ci.cli import main

ROOT = Path(__file__).resolve().parents[1]
TODAY = dt.date(2026, 9, 24)
PROFILES = ("core", "pipeline", "owners-office")
OWNERS_OFFICE = {"C-RATING-ORDER", "C-CONCENTRATION", "C-DISCOUNT-RATE", "C-SELL-REASONS", "C-HURDLE", "C-SINGLE-ORDER",
                 "C-DEFAULT-HOLD", "C-DECISION-RIGHTS", "C-CONSTITUTION-MAP", "C-LANGUAGE"}
PIPELINE = {"C-LLM-ENTRY", "C-AGENT-ISOLATION", "C-PROMPT-ISOLATION", "C-TRUST-WRITE"}


def profile_of() -> dict[str, str]:
    return {m["id"]: m["profile"] for m in contract.registered_checks()}


def applicable(visibility: str, counterpart: bool, profiles=PROFILES) -> list[str]:
    return [m["id"] for m in contract.registered_checks()
            if m["profile"] in profiles and engine.applies(m["scope"], visibility, counterpart)]


def set_profiles(ws: Path, side: str, line: str | None) -> None:
    path = ws / side / "repo.yml"
    text = re.sub(r"(?m)^profiles:.*\n", "", path.read_text(encoding="utf-8"))
    path.write_text(text + (line + "\n" if line else ""), encoding="utf-8")


# -- the registry ----------------------------------------------------------------------------------------------------

def test_profiles_are_registered_and_every_check_has_one():
    assert contract.profiles() == PROFILES
    assert all(meta.get("profile") in PROFILES for meta in contract.registered_checks())


def test_profile_assignment():
    """The core / pipeline / owners-office split of SPEC 8.6."""
    of = profile_of()
    assert {c for c, p in of.items() if p == "owners-office"} == OWNERS_OFFICE
    assert {c for c, p in of.items() if p == "pipeline"} == PIPELINE
    assert {"C-SCHEMA", "C-TESTS-COVERAGE", "C-TESTS-CAPALLOC", "C-TEST-QUAL-EVIDENCE", "C-NO-TRADING",
            "C-PUBLIC-NO-ADVICE", "C-TEST-FROZEN"} <= {c for c, p in of.items() if p == "core"}


def test_repo_schema_lists_the_profiles():
    enum = contract.schema("repo")["properties"]["profiles"]["items"]["enum"]
    assert tuple(enum) == PROFILES


@pytest.mark.parametrize("readme", ["README.md", "zh-CN/README.md"])
def test_readme_check_tables_show_each_checks_profile(readme):
    rows = re.findall(r"^\| `(C-[A-Z-]+)` \| (\S+) \|", (ROOT / readme).read_text(encoding="utf-8"), re.M)
    assert dict(rows) == profile_of()


def test_spec_profile_tables_list_every_check():
    """SPEC 8.6 (English and Chinese) names every check under its profile."""
    for spec in ("spec/SPEC.md", "zh-CN/spec/SPEC.md"):
        text = (ROOT / spec).read_text(encoding="utf-8")
        rows = re.findall(r"^\| `(core|pipeline|owners-office)` \|[^|]*\|([^|]+)\|", text, re.M)
        listed = {cid: profile for profile, cells in rows for cid in re.findall(r"C-[A-Z-]+", cells)}
        assert listed == profile_of(), spec


# -- selection -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("side", ["public", "private"])
def test_without_profiles_every_profile_runs(ws, side):
    """Backward compatible: a repo.yml without profiles lints exactly as before 0.5.0."""
    other = "private" if side == "public" else "public"
    report = engine.run(ws / side, ws / other, TODAY)
    assert report.profiles is None and report.findings == []
    assert report.checks_run == applicable(side, True)


def test_repo_yml_selects_profiles(ws):
    set_profiles(ws, "public", "profiles: [core]")
    report = engine.run(ws / "public", ws / "private", TODAY)
    assert report.profiles == ("core",) and report.findings == []
    assert report.checks_run == applicable("public", True, ("core",))
    set_profiles(ws, "public", "profiles: [owners-office, core]")  # order does not matter
    report = engine.run(ws / "public", ws / "private", TODAY)
    assert report.profiles == ("core", "owners-office")
    assert report.checks_run == applicable("public", True, ("core", "owners-office"))


def test_profile_option_overrides_repo_yml(ws):
    set_profiles(ws, "public", "profiles: [core]")
    report = engine.run(ws / "public", ws / "private", TODAY, profiles=["pipeline"])
    assert report.checks_run == applicable("public", True, ("pipeline",))
    with pytest.raises(ValueError, match="unknown profile"):
        engine.run(ws / "public", None, TODAY, profiles=["investing"])


def test_only_overrides_the_profiles(ws):
    set_profiles(ws, "public", "profiles: [core]")
    report = engine.run(ws / "public", ws / "private", TODAY, only=["C-DECISION-RIGHTS"], profiles=["pipeline"])
    assert report.checks_run == ["C-DECISION-RIGHTS"] and report.profiles is None


@pytest.mark.parametrize("value", ["[coer]", "[]", "core", "[pipeline, pipeline]", "[core, 1]"])
def test_malformed_profiles_run_every_profile_and_fail_c_schema(ws, value):
    """C-SCHEMA: a profiles typo cannot switch checks off; every profile runs and the value is an error."""
    set_profiles(ws, "public", f"profiles: {value}")
    report = engine.run(ws / "public", ws / "private", TODAY)
    assert report.profiles is None and report.checks_run == applicable("public", True)
    assert [f.check for f in report.errors] == ["C-SCHEMA"] and "/profiles" in report.errors[0].message


def test_core_needs_no_file_of_another_profile(ws):
    """core alone never asks for constitution/, agents/ or trust/ (read only by owners-office and pipeline)."""
    for name in ("constitution", "agents", "trust"):
        shutil.rmtree(ws / "public" / name)
    for pipeline in (False, True):
        for side in ("public", "private"):
            set_profiles(ws, side, "profiles: [core, pipeline]" if pipeline else "profiles: [core]")
        for side, other in (("public", "private"), ("private", "public")):
            report = engine.run(ws / side, ws / other, TODAY)
            assert report.findings == [], (side, pipeline, report.findings)
    set_profiles(ws, "public", "profiles: [core, owners-office]")
    report = engine.run(ws / "public", ws / "private", TODAY)
    assert sorted(f.check for f in report.errors) == ["C-CONSTITUTION-MAP", "C-DECISION-RIGHTS"]


def test_lint_cli_profile_option_and_summary(ws, capsys):
    assert main(["lint", str(ws / "public"), "--profile", "core,pipeline", "--today", "2026-09-24"]) == 0
    out = capsys.readouterr().out
    assert f"{len(applicable('public', False, ('core', 'pipeline')))} checks (profiles: core, pipeline) on public" in out
    assert main(["lint", str(ws / "public"), "--today", "2026-09-24"]) == 0
    assert "checks on public repo" in capsys.readouterr().out  # no selection: the summary line is as before
    assert main(["lint", str(ws / "public"), "--profile", "investing"]) == 2


# -- thesis-ci init ----------------------------------------------------------------------------------------------------

def lint_new(root: Path, **options) -> engine.Report:
    return engine.run(root, None, TODAY, **options)


@pytest.mark.parametrize("visibility", ["public", "private"])
def test_init_core_archive_lints_clean(tmp_path, visibility):
    """thesis-ci init writes an archive with profiles: [core] that lints with zero errors and zero warnings."""
    root = tmp_path / "archive"
    written = scaffold.init_archive(root, visibility, ["core"], today=TODAY)
    assert sorted(p.relative_to(root).as_posix() for p in written) == [
        "README.md", "companies/ACME/sources.yml", "companies/ACME/story.md", "companies/ACME/thesis.yml", "repo.yml"]
    meta = yaml.safe_load((root / "repo.yml").read_text(encoding="utf-8"))
    assert meta == {"visibility": visibility, "spec_version": "0.2", "profiles": ["core"]}
    report = lint_new(root)
    assert report.profiles == ("core",)
    assert report.errors == [] and report.warnings == []
    assert report.checks_run == applicable(visibility, False, ("core",))


def test_init_example_has_one_test_of_each_type(tmp_path):
    scaffold.init_archive(tmp_path, today=TODAY)
    thesis = yaml.safe_load((tmp_path / "companies/ACME/thesis.yml").read_text(encoding="utf-8"))
    types = [t["type"] for t in thesis["tests"]]
    assert set(types) == {"quantitative", "qualitative", "staleness"} and len(types) == 5  # five is the minimum
    assert thesis["as_of"] == TODAY and {t["effective_from"] for t in thesis["tests"]} == {"FY2026Q4"}


@pytest.mark.parametrize("visibility", ["public", "private"])
@pytest.mark.parametrize("profiles", [["core", "pipeline"], ["core", "owners-office"], list(PROFILES), ["owners-office"]])
def test_init_lints_clean_with_any_profiles(tmp_path, visibility, profiles):
    """With owners-office, a public archive also gets the constitution files that profile requires."""
    scaffold.init_archive(tmp_path, visibility, profiles, today=TODAY)
    report = lint_new(tmp_path)
    assert report.errors == [] and report.warnings == []
    has_constitution = (tmp_path / "constitution" / "rules.yml").is_file()
    assert has_constitution == (visibility == "public" and "owners-office" in profiles)


def test_init_never_overwrites(tmp_path):
    (tmp_path / "companies" / "ACME").mkdir(parents=True)
    story = tmp_path / "companies" / "ACME" / "story.md"
    story.write_text("mine\n", encoding="utf-8")
    with pytest.raises(FileExistsError, match="companies/ACME/story.md"):
        scaffold.init_archive(tmp_path, today=TODAY)
    assert story.read_text(encoding="utf-8") == "mine\n"
    assert sorted(p.name for p in tmp_path.rglob("*") if p.is_file()) == ["story.md"]  # nothing else written


def test_init_command(tmp_path, capsys):
    root = tmp_path / "new"
    assert main(["init", str(root), "--visibility", "private", "--profiles", "core,pipeline"]) == 0
    out = capsys.readouterr().out
    assert "wrote a private archive" in out and "(profiles: core, pipeline)" in out and "companies/ACME/thesis.yml" in out
    assert "profiles: [core, pipeline]" in (root / "repo.yml").read_text(encoding="utf-8")
    assert main(["lint", str(root)]) == 0
    capsys.readouterr()
    assert main(["init", str(root)]) == 2  # the files exist now
    assert "never overwrites" in capsys.readouterr().err
    assert main(["init", str(tmp_path / "other"), "--profiles", "investing"]) == 2
    assert not (tmp_path / "other").exists()


def test_init_next_period():
    assert scaffold.next_period(dt.date(2026, 9, 24)) == "FY2026Q4"
    assert scaffold.next_period(dt.date(2026, 12, 31)) == "FY2027Q1"
    assert scaffold.next_period(dt.date(2027, 1, 1)) == "FY2027Q2"


def test_selftest_fixture_is_unaffected():
    """The bundled example has no profiles line, so every profile keeps running on it."""
    assert "profiles" not in yaml.safe_load((selftest.FIXTURE / "public" / "repo.yml").read_text(encoding="utf-8"))
