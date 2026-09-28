"""thesis-ci init: write a minimal, lint-clean archive around one fictitious example company.

The files come from ``starter/`` (the README, and companies/ACME/ with thesis.yml, story.md and sources.yml);
repo.yml is written here. ``{{TODAY}}`` becomes the date of the run, so the review dates are fresh, and
``{{NEXT_PERIOD}}`` the next calendar quarter, from which the thesis tests are judged. A public archive that selects
the owners-office profile also gets that profile's constitution (constitution/rules.yml and decision-rights.yml, the
bundled example's), which two of its checks require.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Iterable

from . import contract

STARTER = Path(__file__).resolve().parent / "starter"
CONSTITUTION = Path(__file__).resolve().parent / "fixtures" / "workspace" / "public" / "constitution"
CONSTITUTION_FILES = ("rules.yml", "decision-rights.yml")
DEFAULT_PROFILES = ("core",)

PRIVATE_NOTE = """
`visibility: private` in `repo.yml` makes this a private archive. thesis-ci runs on it only the checks that apply to a
private archive (`thesis-ci checks` lists each check's scope): the checks of thesis tests, stories and
pre-registrations run on a public archive.
"""
CONSTITUTION_ROWS = """| `constitution/rules.yml` | the owners-office profile's investing rules, each mapped to the checks that enforce it |
| `constitution/decision-rights.yml` | who decides what: actions an agent takes alone, with a report, or only with the owner |
"""


def next_period(today: dt.date) -> str:
    """The calendar quarter after ``today``'s, as FY<year>Q<quarter> (the example's fiscal year is the calendar year)."""
    quarter = (today.month - 1) // 3 + 1
    return f"FY{today.year + 1}Q1" if quarter == 4 else f"FY{today.year}Q{quarter + 1}"


def repo_yml(visibility: str, profiles: Iterable[str]) -> str:
    chosen = ", ".join(p for p in contract.profiles() if p in set(profiles))
    return (
        "# Archive repository marker (thesis-ci SPEC 1; schema: spec/schemas/repo.schema.json)\n"
        "# visibility: public or private. profiles: the check profiles thesis-ci lint runs (SPEC 8.6), any of core,\n"
        "# pipeline and owners-office; without the profiles line every profile runs.\n"
        f"visibility: {visibility}\n"
        'spec_version: "0.2"\n'
        f"profiles: [{chosen}]\n"
    )


def plan(visibility: str = "public", profiles: Iterable[str] = DEFAULT_PROFILES,
         today: dt.date | None = None) -> dict[str, str]:
    """The files of a new archive: relative path -> contents."""
    profiles = list(profiles)
    if visibility not in ("public", "private"):
        raise ValueError(f"visibility must be public or private, not {visibility!r}")
    unknown = sorted(set(profiles) - set(contract.profiles()))
    if unknown or not profiles:
        raise ValueError(f"unknown profile(s): {', '.join(unknown) or '(none given)'}")
    today = today or dt.date.today()
    constitution = visibility == "public" and "owners-office" in profiles
    tokens = {
        "{{TODAY}}": today.isoformat(),
        "{{NEXT_PERIOD}}": next_period(today),
        "{{VISIBILITY_NOTE}}": PRIVATE_NOTE if visibility == "private" else "",
        "{{CONSTITUTION_ROWS}}": CONSTITUTION_ROWS if constitution else "",
    }
    files = {"repo.yml": repo_yml(visibility, profiles)}
    for path in sorted(p for p in STARTER.rglob("*") if p.is_file()):
        text = path.read_text(encoding="utf-8")
        for token, value in tokens.items():
            text = text.replace(token, value)
        files[path.relative_to(STARTER).as_posix()] = text
    if constitution:
        for name in CONSTITUTION_FILES:
            files[f"constitution/{name}"] = (CONSTITUTION / name).read_text(encoding="utf-8")
    return files


def init_archive(target: str | Path, visibility: str = "public", profiles: Iterable[str] = DEFAULT_PROFILES,
                 today: dt.date | None = None) -> list[Path]:
    """Write a new archive into ``target``; nothing is written when any of its files already exists."""
    root = Path(target)
    if root.exists() and not root.is_dir():
        raise NotADirectoryError(f"{root} exists and is not a directory")
    files = plan(visibility, profiles, today)
    existing = [rel for rel in files if (root / rel).exists()]
    if existing:
        raise FileExistsError(f"{root} already has {', '.join(existing)}; init never overwrites a file, so nothing "
                              "was written")
    written = []
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "x", encoding="utf-8") as fh:  # "x": fail rather than overwrite a file that appeared meanwhile
            fh.write(text)
        written.append(path)
    return written
