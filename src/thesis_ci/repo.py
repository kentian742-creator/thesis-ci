"""Archive repositories: file walking, YAML documents with line numbers, source-tag lookup."""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import unicodedata
from fnmatch import fnmatchcase
from functools import cached_property
from pathlib import Path
from typing import Any, Iterator

import yaml

from .textscan import FRONT_MATTER_RE

# Directories never scanned: version control, virtual environments, caches and build output.
# Every other directory is scanned, hidden ones included (.github, .claude, ...): a hidden directory is
# published like any other, so it must not be a place where a secret, a model call or valuation data can hide.
IGNORED_DIRS = {
    ".git", ".hg", ".svn",
    "node_modules", "__pycache__", "site-packages",
    ".venv", "venv", "env", ".tox", ".nox", ".eggs",
    ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "build", "dist",
}
BINARY_SUFFIXES = {
    ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".zip", ".gz", ".tgz", ".bz2", ".xz",
    ".xlsx", ".xls", ".docx", ".pptx", ".ots", ".woff", ".woff2", ".ttf", ".otf", ".mp4", ".mov",
    ".pyc", ".whl", ".sqlite", ".db",
}
YAML_SUFFIXES = (".yml", ".yaml")
MAX_TEXT_BYTES = 5_000_000
_MERGE_TAG = "tag:yaml.org,2002:merge"


def jsonable(obj: Any) -> Any:
    """Map YAML data onto the JSON data model: dates become ISO strings, mapping keys become strings."""
    if isinstance(obj, (dt.date, dt.datetime)):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {_json_key(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [jsonable(v) for v in obj]
    return obj


def _json_key(key: Any) -> str:
    if isinstance(key, str):
        return key
    if isinstance(key, bool):
        return "true" if key else "false"
    if key is None:
        return "null"
    if isinstance(key, (dt.date, dt.datetime)):
        return key.isoformat()
    return str(key)


def path_match(rel: str, pattern: str) -> bool:
    """Segment-wise glob: ``*`` stays within one path segment, ``**`` spans any number of segments."""
    return _match(rel.split("/"), pattern.split("/"))


def _match(parts: list[str], pats: list[str]) -> bool:
    if not pats:
        return not parts
    if pats[0] == "**":
        return any(_match(parts[i:], pats[1:]) for i in range(len(parts) + 1))
    return bool(parts) and fnmatchcase(parts[0], pats[0]) and _match(parts[1:], pats[1:])


def is_yaml(path: Path) -> bool:
    return path.suffix.lower() in YAML_SUFFIXES


def dig(data: Any, *keys: Any) -> Any:
    for key in keys:
        if isinstance(data, dict):
            data = data.get(key)
        elif isinstance(data, list) and isinstance(key, int) and 0 <= key < len(data):
            data = data[key]
        else:
            return None
    return data


def walk_items(data: Any, path: tuple = ()) -> Iterator[tuple[tuple, Any, Any]]:
    """Yield (path, key, value) for every mapping entry, recursively (lists included)."""
    if isinstance(data, dict):
        for key, value in data.items():
            yield path + (key,), key, value
            yield from walk_items(value, path + (key,))
    elif isinstance(data, list):
        for i, value in enumerate(data):
            yield from walk_items(value, path + (i,))


def is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _bad_timestamp_line(node: yaml.Node | None) -> int | None:
    """1-based line of the first timestamp scalar PyYAML cannot turn into a date."""
    probe = yaml.SafeLoader("")
    bad: list[int] = []
    stack = [node] if node is not None else []
    try:
        while stack:
            n = stack.pop()
            if isinstance(n, yaml.ScalarNode) and n.tag == "tag:yaml.org,2002:timestamp":
                try:
                    probe.construct_yaml_timestamp(n)
                except ValueError:
                    bad.append(n.start_mark.line + 1)
            elif isinstance(n, yaml.SequenceNode):
                stack.extend(n.value)
            elif isinstance(n, yaml.MappingNode):
                stack.extend(x for pair in n.value for x in pair)
    finally:
        probe.dispose()
    return min(bad) if bad else None


def duplicate_keys(node: yaml.Node | None) -> list[tuple[int, str]]:
    """(1-based line, key) of every repeated key in a YAML mapping.

    YAML forbids repeated mapping keys, but PyYAML silently keeps the last value, so a file could show a
    reader one value and hand the checks another.
    """
    out: list[tuple[int, str]] = []
    visited: set[int] = set()
    stack = [node] if node is not None else []
    while stack:
        n = stack.pop()
        if id(n) in visited:  # an alias shares its anchor's node
            continue
        visited.add(id(n))
        if isinstance(n, yaml.MappingNode):
            keys: set[str] = set()
            for knode, vnode in n.value:
                if isinstance(knode, yaml.ScalarNode) and knode.tag != _MERGE_TAG:
                    if knode.value in keys:
                        out.append((knode.start_mark.line + 1, knode.value))
                    keys.add(knode.value)
                stack.extend((knode, vnode))
        elif isinstance(n, yaml.SequenceNode):
            stack.extend(n.value)
    return sorted(out)


def node_line(node: yaml.Node | None, keys: tuple, offset: int = 0) -> int | None:
    """1-based line of the deepest node reachable along ``keys`` (mapping keys / list indexes)."""
    if node is None:
        return None
    line = node.start_mark.line
    for key in keys:
        if isinstance(node, yaml.MappingNode):
            for knode, vnode in node.value:
                if isinstance(knode, yaml.ScalarNode) and knode.value == str(key):
                    line, node = knode.start_mark.line, vnode
                    break
            else:
                break
        elif isinstance(node, yaml.SequenceNode) and isinstance(key, int) and 0 <= key < len(node.value):
            node = node.value[key]
            line = node.start_mark.line
        else:
            break
    return line + 1 + offset


class Doc:
    """One YAML document: the parsed data plus its node tree, so findings can point at a line."""

    def __init__(self, path: Path, text: str, line_offset: int = 0):
        self.path = path
        self.line_offset = line_offset
        self.data: Any = None
        self.node: yaml.Node | None = None
        self.error: str | None = None
        self.error_line: int | None = None
        loader = yaml.SafeLoader(text)
        try:
            self.node = loader.get_single_node()
            if self.node is not None:
                self.data = loader.construct_document(self.node)
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            self.error_line = mark.line + 1 + line_offset if mark is not None else None
            problem = getattr(exc, "problem", None) or str(exc).splitlines()[0]
            self.error = f"YAML syntax error: {problem}"
        except (ValueError, TypeError, OverflowError) as exc:  # e.g. an impossible date such as 2026-02-30
            self.data = None
            line = _bad_timestamp_line(self.node)
            self.error_line = line + line_offset if line else None
            self.error = f"invalid YAML value: {exc}"
        finally:
            loader.dispose()
        self.duplicates = [(line + line_offset, key) for line, key in duplicate_keys(self.node)]

    @property
    def mapping(self) -> dict:
        return self.data if isinstance(self.data, dict) else {}

    def line(self, *keys: Any) -> int | None:
        """1-based line of the deepest node reachable along ``keys`` (mapping keys / list indexes)."""
        return node_line(self.node, keys, self.line_offset)


class DataDoc:
    """One document of a data file (one document of a YAML stream, or a JSON file), for key scans."""

    def __init__(self, data: Any, node: yaml.Node | None = None, text: str = ""):
        self.data = data
        self.node = node
        self._text = text

    def line(self, *keys: Any) -> int | None:
        if self.node is not None:
            return node_line(self.node, keys)
        # JSON: the first line that spells the innermost key
        key = next((k for k in reversed(keys) if isinstance(k, str)), None)
        if key is None or not self._text:
            return None
        pos = self._text.find(json.dumps(key, ensure_ascii=False))
        if pos < 0:
            pos = self._text.find(json.dumps(key))
        return self._text.count("\n", 0, pos) + 1 if pos >= 0 else None


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def git_visible_files(root: Path) -> set[str] | None:
    """Paths under ``root`` that git would publish (tracked, or untracked and not ignored), NFC-normalized.

    None when ``root`` is not inside a git work tree or git is unavailable; the caller then scans everything.
    """
    git = shutil.which("git")
    if git is None:
        return None
    try:
        proc = subprocess.run(
            [git, "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            capture_output=True, timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return {_nfc(os.fsdecode(p)) for p in proc.stdout.split(b"\0") if p}


class Repo:
    """An archive repository (public or private) rooted at ``root``."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self._docs: dict[Path, Doc] = {}
        self._data_docs: dict[Path, list[DataDoc]] = {}
        self._texts: dict[Path, str | None] = {}
        self._tags: dict[Path, frozenset[str]] = {}

    # -- files -----------------------------------------------------------------------------------
    @cached_property
    def all_files(self) -> list[Path]:
        """Every file of the archive, hidden directories included, minus the files git ignores.

        Inside a git work tree only what git would publish is scanned, so an ignored local ``.env`` or ``logs/``
        does not fail the lint. Outside a work tree, or when git does not list repo.yml itself (the archive is
        ignored by an enclosing repository), every file is scanned.
        """
        out: list[Path] = []
        for dirpath, dirnames, filenames in os.walk(self.root):
            dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS)
            out.extend(Path(dirpath) / f for f in sorted(filenames))
        visible = git_visible_files(self.root)
        if visible and ("repo.yml" in visible or not (self.root / "repo.yml").is_file()):
            out = [p for p in out if _nfc(self.rel(p)) in visible]
        return out

    def rel(self, path: str | Path) -> str:
        path = Path(path)
        if not path.is_absolute():
            return path.as_posix()
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            return str(path)

    def files(self, pattern: str) -> list[Path]:
        return [p for p in self.all_files if path_match(self.rel(p), pattern)]

    def company_dirs(self) -> list[Path]:
        base = self.root / "companies"
        if not base.is_dir():
            return []
        return sorted(d for d in base.iterdir() if d.is_dir() and not d.name.startswith((".", "_")))

    def text(self, path: Path) -> str | None:
        """File contents (without a UTF-8 byte-order mark), or None for binary / oversized / unreadable files."""
        if path not in self._texts:
            content = None
            if path.suffix.lower() not in BINARY_SUFFIXES:
                try:
                    raw = path.read_bytes()
                except OSError:
                    raw = None
                if raw is not None and len(raw) <= MAX_TEXT_BYTES and b"\x00" not in raw[:8192]:
                    content = raw.decode("utf-8-sig", errors="replace")
            self._texts[path] = content
        return self._texts[path]

    # -- YAML --------------------------------------------------------------------------------------
    def doc(self, path: Path) -> Doc:
        if path not in self._docs:
            self._docs[path] = Doc(path, self.text(path) or "")
        return self._docs[path]

    def front_matter(self, path: Path) -> Doc | None:
        """YAML front matter of a Markdown file, or None when there is none."""
        text = self.text(path) or ""
        m = FRONT_MATTER_RE.match(text)
        return Doc(path, m.group(1), line_offset=1) if m else None

    def yaml_stream_error(self, path: Path) -> tuple[str, int | None] | None:
        """Syntax check for YAML files that have no schema (multi-document streams allowed)."""
        try:
            for _ in yaml.safe_load_all(self.text(path) or ""):
                pass
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            problem = getattr(exc, "problem", None) or str(exc).splitlines()[0]
            return f"YAML syntax error: {problem}", (mark.line + 1 if mark is not None else None)
        except (ValueError, TypeError, OverflowError) as exc:
            return f"invalid YAML value: {exc}", None
        return None

    def yaml_duplicates(self, path: Path) -> list[tuple[int, str]]:
        """Repeated mapping keys in every document of a YAML file (which may be a multi-document stream)."""
        out: list[tuple[int, str]] = []
        loader = yaml.SafeLoader(self.text(path) or "")
        try:
            while loader.check_node():
                out.extend(duplicate_keys(loader.get_node()))
        except yaml.YAMLError:
            pass  # syntax errors are reported on their own
        finally:
            loader.dispose()
        return out

    def data_docs(self, path: Path) -> list[DataDoc]:
        """Every document of a YAML stream (``---`` separated) or of a JSON file; [] when it does not parse.

        Key scans (valuation, amounts, prices) must see every document: a second document is published too.
        """
        if path not in self._data_docs:
            text = self.text(path) or ""
            docs: list[DataDoc] = []
            if path.suffix.lower() == ".json":
                try:
                    docs.append(DataDoc(json.loads(text), text=text))
                except ValueError:
                    pass
            else:
                loader = yaml.SafeLoader(text)
                try:
                    while loader.check_node():
                        node = loader.get_node()
                        docs.append(DataDoc(loader.construct_document(node), node))
                except (yaml.YAMLError, ValueError, TypeError, OverflowError):
                    pass  # reported by C-SCHEMA; the documents read so far are still scanned
                finally:
                    loader.dispose()
            self._data_docs[path] = docs
        return self._data_docs[path]

    @cached_property
    def meta(self) -> dict | None:
        path = self.root / "repo.yml"
        if not path.is_file():
            return None
        data = self.doc(path).data
        return data if isinstance(data, dict) else None

    @property
    def visibility(self) -> str | None:
        vis = (self.meta or {}).get("visibility")
        return vis if vis in ("public", "private") else None

    def rights(self) -> dict | None:
        """constitution/decision-rights.yml as a mapping, if present and parseable."""
        path = self.root / "constitution" / "decision-rights.yml"
        if not path.is_file():
            return None
        data = self.doc(path).data
        return data if isinstance(data, dict) else None

    # -- sources -----------------------------------------------------------------------------------
    def _tags_in(self, sources_file: Path) -> frozenset[str]:
        if sources_file not in self._tags:
            tags: set[str] = set()
            entries = self.doc(sources_file).mapping.get("sources") if sources_file.is_file() else None
            for entry in entries if isinstance(entries, list) else []:  # a malformed file is C-SCHEMA's to report
                if isinstance(entry, dict) and isinstance(entry.get("tag"), str):
                    tags.add(entry["tag"])
            self._tags[sources_file] = frozenset(tags)
        return self._tags[sources_file]

    def known_tags(self, path: Path) -> set[str]:
        """Tags resolvable from ``path``: sources.yml in its directory and each parent up to the root."""
        rel_dir = Path(self.rel(path)).parent
        if rel_dir.is_absolute():  # outside the repository: only its own directory applies
            dirs = [self.root, rel_dir]
        else:
            dirs = [self.root] + [self.root.joinpath(*rel_dir.parts[: i + 1]) for i in range(len(rel_dir.parts))]
        tags: set[str] = set()
        for d in dirs:
            tags |= self._tags_in(d / "sources.yml")
        return tags
