"""The wheel ships the spec inside the package and the CLI works from it (no source tree needed)."""

from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def wheel(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("wheel")
    proc = subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "--quiet", "-w", str(out), str(ROOT)],
        capture_output=True, text=True, timeout=600,
    )
    if proc.returncode != 0:
        pytest.skip(f"cannot build a wheel here (offline?): {proc.stderr.strip()[-300:]}")
    return next(out.glob("thesis_ci-*.whl"))


def test_wheel_contains_spec_and_fixtures(wheel):
    names = set(zipfile.ZipFile(wheel).namelist())
    for required in (
        "thesis_ci/spec/SPEC.md",
        "thesis_ci/spec/checks.yml",
        "thesis_ci/spec/metrics.yml",
        "thesis_ci/spec/schemas/thesis.schema.json",
        "thesis_ci/spec/templates/lynch/stalwart.yml",
        "thesis_ci/fixtures/workspace/public/companies/ACME/thesis.yml",
        "thesis_ci/starter/README.md",
        "thesis_ci/starter/companies/ACME/thesis.yml",
        "thesis_ci/cli.py",
    ):
        assert required in names, required
    metadata = next(n for n in names if n.endswith(".dist-info/entry_points.txt"))
    assert "thesis-ci = thesis_ci.cli:main" in zipfile.ZipFile(wheel).read(metadata).decode()


def test_cli_runs_from_the_unpacked_wheel(wheel, tmp_path):
    site = tmp_path / "site"
    zipfile.ZipFile(wheel).extractall(site)
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]);"
        "from thesis_ci import contract, cli;"
        "print(contract.spec_dir());"
        "sys.exit(cli.main(['selftest']))"
    )
    proc = subprocess.run([sys.executable, "-c", code, str(site)], capture_output=True, text=True, cwd=tmp_path, timeout=300)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert proc.stdout.splitlines()[0] == str(site / "thesis_ci" / "spec")
    assert "35/35 checks pass" in proc.stdout


def test_init_runs_from_the_unpacked_wheel(wheel, tmp_path):
    """thesis-ci init finds its starter files (and the owners-office constitution) inside an installed wheel."""
    site = tmp_path / "site"
    zipfile.ZipFile(wheel).extractall(site)
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]);"
        "from thesis_ci import cli;"
        "assert cli.main(['init', sys.argv[2], '--profiles', 'core,owners-office']) == 0;"
        "sys.exit(cli.main(['lint', sys.argv[2]]))"
    )
    proc = subprocess.run([sys.executable, "-c", code, str(site), str(tmp_path / "archive")], capture_output=True,
                          text=True, cwd=tmp_path, timeout=300)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "0 error(s), 0 warning(s)" in proc.stdout
