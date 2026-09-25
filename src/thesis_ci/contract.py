"""Locate and load the format contract: schemas, the check and metric registries, Lynch templates.

A wheel ships the contract inside the package as ``thesis_ci/spec``. An editable install or a source
checkout reads the repository's top-level ``spec/`` directly, so there is a single source of truth.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import jsonschema
import yaml

_PKG = Path(__file__).resolve().parent
_CANDIDATES = (_PKG / "spec", _PKG.parent.parent / "spec")


@lru_cache(maxsize=None)
def spec_dir() -> Path:
    for cand in _CANDIDATES:
        if (cand / "checks.yml").is_file() and (cand / "schemas").is_dir():
            return cand
    looked = ", ".join(str(c) for c in _CANDIDATES)
    raise FileNotFoundError(f"thesis-ci: spec directory not found (looked in {looked}); reinstall thesis-ci")


def _load_yaml(rel: str):
    return yaml.safe_load((spec_dir() / rel).read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def registered_checks() -> tuple[dict, ...]:
    """Entries of spec/checks.yml, in file order."""
    return tuple(_load_yaml("checks.yml")["checks"])


def check_meta(check_id: str) -> dict:
    for meta in registered_checks():
        if meta["id"] == check_id:
            return meta
    raise KeyError(check_id)


@lru_cache(maxsize=None)
def metrics() -> dict[str, dict]:
    """spec/metrics.yml keyed by metric id."""
    return {m["id"]: m for m in _load_yaml("metrics.yml")["metrics"]}


@lru_cache(maxsize=None)
def schema(name: str) -> dict:
    return json.loads((spec_dir() / "schemas" / f"{name}.schema.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def validator(name: str) -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(schema(name), format_checker=jsonschema.FormatChecker())


def schema_names() -> list[str]:
    return sorted(p.name[: -len(".schema.json")] for p in (spec_dir() / "schemas").glob("*.schema.json"))


def template(category: str) -> dict:
    """A Lynch monitoring template (spec/templates/lynch/<category>.yml)."""
    return _load_yaml(f"templates/lynch/{category}.yml")


def sell_reason_enum() -> list[str]:
    return list(schema("memo")["properties"]["sell_reason"]["enum"])
