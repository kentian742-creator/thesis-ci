"""Code guards: no price feeds, no trading APIs, model calls only in pipeline/llm.py, no secrets."""

from __future__ import annotations

import ast
import json
import re
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Callable, Iterator

from ..engine import Context, Issue, check
from ..repo import Repo
from ..textscan import compile_wording, line_of, phrase_hits
from .public import CONTENT_ROOT_FILES, content_files, forbidden_keys, forbidden_wording

CODE_SUFFIXES = {
    ".py", ".pyw", ".ipynb", ".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".sh", ".bash", ".zsh",
    ".ps1", ".rb", ".go", ".rs", ".java", ".r",
}
JS_SUFFIXES = {".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx"}
MANIFESTS = {"pyproject.toml", "setup.cfg", "Pipfile", "package.json", "environment.yml", "Dockerfile", "Makefile"}
# Dependency lists: they may name the SDK that pipeline/llm.py imports; naming it is not a model call.
DEPENDENCY_FILES = {"pyproject.toml", "setup.cfg", "Pipfile", "package.json", "environment.yml"}

# -- C-NO-PRICE-FEED ----------------------------------------------------------------------------------
# spec/checks.yml names these "等" (and the like): the list below adds other quote sources and clients.
PRICE_FEEDS = (
    "yfinance", "yahoo finance", "yahoo-finance", "yahoo_fin", "yahooquery", "finance.yahoo.com", "alphavantage",
    "alpha_vantage", "polygon.io", "polygon-api-client", "finnhub", "iexcloud", "iexfinance", "twelvedata", "stooq",
    "marketstack", "financialmodelingprep", "eodhistoricaldata", "eodhd.com", "tiingo", "pandas_datareader",
    "pandas-datareader", "investpy", "akshare", "tushare", "baostock", "efinance", "easyquotation",
    "/v7/finance/quote", "/v8/finance/chart",
)
# Python modules whose import alone is a price feed (short or ambiguous names are matched as imports only).
PRICE_MODULES = frozenset({
    "yfinance", "yahoo_fin", "yahooquery", "alpha_vantage", "polygon", "finnhub", "iexfinance", "twelvedata",
    "pandas_datareader", "tiingo", "eodhd", "akshare", "tushare", "efinance", "baostock", "easyquotation", "investpy",
})
PRICE_KEYS = frozenset({"price", "last_price", "close"})
PRICE_KEY_ALIASES = frozenset({
    "share_price", "stock_price", "current_price", "last_close", "close_price", "closing_price", "market_price",
})
# Private repository only (00 §H2): the one-off alert when a price crosses a pre-written value range, and the
# year-end unadjusted closes and price reference used by the private valuation and its five-year backtest.
PRICE_FEED_EXCEPTIONS = ("pipeline/price_alert.py", "pipeline/price_history.py")
# Hard rule 2 (价格静默): public prose does not display a share price either.
_PRICE_AMOUNT = r"(?:[$＄€£¥￥]\s*\d|\d[\d,.]*\s*(?:美元|港元|元|美金|dollars?|usd))"
PRICE_DISPLAY_WORDING = compile_wording((), (
    ("share price", r"(?:股价|现价|收盘价|最新价|市价|股票价格)\s*(?:[:：]|为|是|在|约|报|收于|收在|达|达到|跌至|涨至|跌到|涨到|回落至|升至)?\s*"
                    + _PRICE_AMOUNT),
    ("share price", r"(?<![A-Za-z])(?:share|stock|closing|current|last)\s+price\s+(?:of|at|is|was|:|~|around|near)?\s*" + _PRICE_AMOUNT),
    ("share price", r"(?<![A-Za-z])(?:shares?|stock)\s+(?:trades?|traded|trading|closed|closes)\s+(?:at|near|around)\s+" + _PRICE_AMOUNT),
))

# -- C-NO-TRADING -------------------------------------------------------------------------------------------
TRADING_APIS = (
    "ib_insync", "ib_async", "ibapi", "alpaca", "robin_stocks", "tda-api", "tda_api", "schwab",
    "place_order", "submit_order", "placeorder",
    # other brokers and order clients: Futu / moomoo, Tiger, Longbridge, Questrade, Wealthsimple, Tradier,
    # tastytrade, Webull, Zerodha Kite, crypto exchanges through ccxt
    "futu-api", "moomoo", "tigeropen", "longport", "longbridge", "questrade", "wealthsimple", "tradier",
    "tastytrade", "webull", "kiteconnect", "ccxt", "submitorder",
)
TRADING_PATTERNS = (
    re.compile(r"(?<![A-Za-z0-9_])(?:create|cancel|modify)_?order(?![A-Za-z0-9_])", re.I),
    re.compile(r"(?<![A-Za-z0-9_])futu(?:[-_]api)?(?![A-Za-z0-9_])", re.I),  # not "future"
)
TRADING_MODULES = frozenset({
    "ib_insync", "ib_async", "ibapi", "ibind", "alpaca", "alpaca_trade_api", "robin_stocks", "tda", "schwab", "ccxt",
    "futu", "moomoo", "tigeropen", "longport", "longbridge", "questrade_api", "qtrade", "wealthsimple", "tradier",
    "tastytrade", "webull", "kiteconnect",
})

# -- C-LLM-ENTRY --------------------------------------------------------------------------------------------
LLM_ENTRY = "pipeline/llm.py"
_LLM_MODULES = (
    r"anthropic\w*|openai|litellm|mistralai|cohere|langchain\w*|llama_index|dspy|groq|ollama|together|replicate|"
    r"dashscope|zhipuai|qianfan|vertexai|claude_agent_sdk|claude_code_sdk|instructor|"
    r"google\.generativeai|google\.genai|google\.cloud\.aiplatform"
)
LLM_SDK_RE = re.compile(rf"^(?:{_LLM_MODULES})(?:\.|$)")
LLM_IMPORT_FALLBACK_RE = re.compile(rf"^\s*(?:from|import)\s+((?:{_LLM_MODULES}))\b", re.M)
# Model APIs called without an SDK (HTTP), and model tools run from scripts or workflows.
MODEL_ENDPOINTS = (
    "api.anthropic.com", "api.openai.com", "openai.azure.com", "generativelanguage.googleapis.com",
    "aiplatform.googleapis.com", "bedrock-runtime", "api.mistral.ai", "api.cohere.ai", "api.cohere.com",
    "openrouter.ai/api", "api.deepseek.com", "dashscope.aliyuncs.com", "api.groq.com", "api.together.xyz",
    "api.together.ai", "api.moonshot.cn", "open.bigmodel.cn", "api.x.ai", "api.perplexity.ai", "api.fireworks.ai",
)
MODEL_TOOLS = (
    "anthropics/claude-code-action", "anthropics/claude-code-base-action", "@anthropic-ai/claude-code",
    "@anthropic-ai/claude-agent-sdk", "openai/codex-action", "@openai/codex", "run-gemini-cli",
)
JS_SDK_RE = re.compile(
    r"""(?:\bfrom\s+|\brequire\s*\(\s*|\bimport\s*\(\s*|\bimport\s+)['"]"""
    r"""(@anthropic-ai/[\w./-]+|openai|@openai/[\w./-]+|@google/generative-ai|@google/genai|@mistralai/[\w./-]+|"""
    r"""cohere-ai|groq-sdk|ollama|langchain|@langchain/[\w./-]+|ai|@ai-sdk/[\w./-]+)['"]"""
)

# -- C-NO-SECRETS -------------------------------------------------------------------------------------------
def _looks_random(value: str) -> bool:
    return any(c.isupper() for c in value) and any(c.islower() for c in value) and any(c.isdigit() for c in value)


def _hex_key(value: str) -> bool:
    tail = value.split("-", 1)[-1]
    return any(c.isdigit() for c in tail) and any(c.isalpha() for c in tail)


def _always(_value: str) -> bool:
    return True


SECRET_PATTERNS: tuple[tuple[str, re.Pattern, Callable[[str], bool]], ...] = (
    ("Anthropic API key", re.compile(r"sk-ant-[A-Za-z0-9_\-]{16,}"), _looks_random),
    ("sk- API key", re.compile(r"(?<![A-Za-z0-9_\-])sk-[A-Za-z0-9_\-]{20,}"), _looks_random),
    # DeepSeek / DashScope style: sk- followed by 32+ lowercase hex characters (no upper case to test for)
    ("sk- API key", re.compile(r"(?<![A-Za-z0-9_\-])sk-[0-9a-f]{32,}(?![A-Za-z0-9])"), _hex_key),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"), _always),
    ("GitHub fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), _always),
    ("AWS access key id", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"), _always),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}(?![0-9A-Za-z_\-])"), _always),
    ("Hugging Face token", re.compile(r"\bhf_[A-Za-z0-9]{30,}\b"), _looks_random),
    ("Slack token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}"), _always),
    ("private key", re.compile(r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----"), _always),
)
SECRET_ASSIGN_RE = re.compile(
    r"(?<![A-Za-z0-9_\-])([A-Za-z0-9_\-]*(?:api[_\-]?key|_token|-token|_secret|-secret|secret_key|access_key|private_key|"
    r"_password|_passwd))(?![A-Za-z0-9_\-])[\"']?[ \t]*[:=][ \t]*"
    r"(?:([\"'])([^\"'\s]{12,})\2|([A-Za-z0-9_\-./+=]{16,})[ \t]*$)",
    re.M | re.I,
)
PLACEHOLDER_WORDS = ("your", "example", "placeholder", "changeme", "xxxx", "dummy", "redacted", "secrets.",
                     "${", "$(", "{{", "<", "%(", "process.env", "os.environ", "getenv")
# The name of an environment variable (ANTHROPIC_API_KEY), not an upper-case key such as DEMO1234ABCD5678.
_ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+$")
_DOTTED_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+$")


def _literal_secret(value: str, quoted: bool) -> bool:
    """True when an assigned value looks like a literal secret rather than a reference or a placeholder."""
    low = value.lower()
    if value.startswith("$") or any(w in low for w in PLACEHOLDER_WORDS) or _ENV_NAME_RE.match(value):
        return False
    if not quoted and (_DOTTED_NAME_RE.match(value) or not any(c.isdigit() for c in value)):
        return False  # code (settings.api_key) or a name, not a literal
    return True


def code_files(repo: Repo) -> Iterator[Path]:
    for path in repo.all_files:
        rel = repo.rel(path)
        if (
            path.suffix.lower() in CODE_SUFFIXES
            or path.name in MANIFESTS
            or fnmatchcase(path.name, "requirements*.txt")
            or path.name in ("action.yml", "action.yaml")
            or (rel.startswith(".github/workflows/") and path.suffix.lower() in (".yml", ".yaml"))
        ):
            yield path


def _python_source(repo: Repo, path: Path) -> str | None:
    """Python source of a .py file, or the code cells of a notebook (one cell after another)."""
    text = repo.text(path) or ""
    if path.suffix.lower() in (".py", ".pyw"):
        return text
    if path.suffix.lower() == ".ipynb":
        try:
            cells = json.loads(text).get("cells") or []
        except (ValueError, AttributeError):
            return None
        chunks = []
        for cell in cells:
            if isinstance(cell, dict) and cell.get("cell_type") == "code":
                src = cell.get("source")
                src = "".join(src) if isinstance(src, list) else str(src or "")
                # IPython magics and shell escapes are not Python
                chunks.append("\n".join("" if ln.lstrip().startswith(("%", "!")) else ln for ln in src.splitlines()))
        return "\n".join(chunks)
    return None


def _imports(tree: ast.AST) -> Iterator[tuple[int, str]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield node.lineno, alias.name
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            yield node.lineno, node.module
            for alias in node.names:
                yield node.lineno, f"{node.module}.{alias.name}"
        elif isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in ("import_module", "__import__") and isinstance(node.args[0].value, str):
                yield node.lineno, node.args[0].value


_FALLBACK_IMPORT_RE = re.compile(r"^\s*(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))", re.M)


def python_imports(source: str) -> list[tuple[int, str]]:
    """(line, module) for every import; a line-based fallback when the source does not parse."""
    try:
        return sorted(set(_imports(ast.parse(source))))
    except (SyntaxError, ValueError):
        return [(line_of(source, m.start()), m.group(1) or m.group(2)) for m in _FALLBACK_IMPORT_RE.finditer(source)]


def _module_hits(repo: Repo, path: Path, modules: frozenset[str]) -> Iterator[tuple[int | None, str]]:
    source = _python_source(repo, path)
    if not source:
        return
    notebook = path.suffix.lower() == ".ipynb"
    seen: set[int] = set()
    for line, name in python_imports(source):
        if name.split(".", 1)[0] in modules and line not in seen:
            seen.add(line)
            yield (None if notebook else line), name


def _code_hits(ctx: Context, phrases: tuple[str, ...], what: str, exempt: tuple[str, ...] = (),
               patterns: tuple[re.Pattern, ...] = (), modules: frozenset[str] = frozenset()) -> Iterator[Issue]:
    repo = ctx.repo
    for path in code_files(repo):
        if repo.rel(path) in exempt:
            continue
        text = repo.text(path) or ""
        flagged: set[int | None] = set()
        for line, phrase in phrase_hits(text, phrases):
            flagged.add(line)
            yield Issue(path, f"{what}: '{phrase}'", line)
        for rx in patterns:
            for m in rx.finditer(text):
                line = line_of(text, m.start())
                if line not in flagged:
                    flagged.add(line)
                    yield Issue(path, f"{what}: '{m.group(0)}'", line)
        for line, name in _module_hits(repo, path, modules):
            if line not in flagged or line is None:
                flagged.add(line)
                yield Issue(path, f"{what}: imports '{name}'", line)


@check("C-NO-PRICE-FEED")
def c_no_price_feed(ctx: Context) -> Iterator[Issue]:
    exempt = PRICE_FEED_EXCEPTIONS if ctx.is_private else ()
    yield from _code_hits(ctx, PRICE_FEEDS, "references a market-data price feed", exempt, modules=PRICE_MODULES)
    if ctx.is_private:
        return
    repo = ctx.repo
    yield from forbidden_keys(repo, PRICE_KEYS | PRICE_KEY_ALIASES,
                              "is a price key; prices are private reference data, not public data", data_only=True)
    yield from forbidden_wording(repo, content_files(repo, root_files=CONTENT_ROOT_FILES), PRICE_DISPLAY_WORDING,
                                 "public content displays a share price")


@check("C-NO-TRADING")
def c_no_trading(ctx: Context) -> Iterator[Issue]:
    yield from _code_hits(ctx, TRADING_APIS, "references a broker / order API", patterns=TRADING_PATTERNS,
                          modules=TRADING_MODULES)


def _llm_calls(repo: Repo, path: Path) -> Iterator[tuple[int | None, str]]:
    """(line, what) for every model SDK import, model endpoint and model tool in one code file."""
    text = repo.text(path) or ""
    seen: set[int | None] = set()
    source = _python_source(repo, path)
    if source:
        notebook = path.suffix.lower() == ".ipynb"
        try:
            hits = sorted({(line, name) for line, name in _imports(ast.parse(source)) if LLM_SDK_RE.match(name)})
        except (SyntaxError, ValueError):
            hits = [(line_of(source, m.start()), m.group(1)) for m in LLM_IMPORT_FALLBACK_RE.finditer(source)]
        for line, name in hits:
            line = None if notebook else line
            if line not in seen:
                seen.add(line)
                yield line, f"imports model SDK '{name}'"
    if path.suffix.lower() in JS_SUFFIXES:
        for m in JS_SDK_RE.finditer(text):
            line = line_of(text, m.start())
            if line not in seen:
                seen.add(line)
                yield line, f"imports model SDK '{m.group(1)}'"
    if path.name in DEPENDENCY_FILES or fnmatchcase(path.name, "requirements*.txt"):
        return  # a dependency list may name the SDK that pipeline/llm.py uses
    for line, what in phrase_hits(text, MODEL_ENDPOINTS + MODEL_TOOLS):
        if line not in seen:
            seen.add(line)
            yield line, f"calls a model ('{what}')"


@check("C-LLM-ENTRY")
def c_llm_entry(ctx: Context) -> Iterator[Issue]:
    repo = ctx.repo
    for path in code_files(repo):
        if repo.rel(path) == LLM_ENTRY:
            continue
        for line, what in _llm_calls(repo, path):
            yield Issue(path, f"{what}; model calls belong in {LLM_ENTRY} only", line)


@check("C-NO-SECRETS")
def c_no_secrets(ctx: Context) -> Iterator[Issue]:
    repo = ctx.repo
    for path in repo.all_files:
        text = repo.text(path)
        if not text:
            continue
        flagged: set[int] = set()  # one finding per line
        for label, rx, plausible in SECRET_PATTERNS:
            for m in rx.finditer(text):
                line = line_of(text, m.start())
                if line in flagged or not plausible(m.group(0)):
                    continue
                flagged.add(line)
                yield Issue(path, f"looks like a committed secret ({label})", line)
        for m in SECRET_ASSIGN_RE.finditer(text):
            line = line_of(text, m.start())
            quoted = m.group(3) is not None
            value = m.group(3) if quoted else (m.group(4) or "")
            if line in flagged or not _literal_secret(value, quoted):
                continue
            flagged.add(line)
            yield Issue(path, f"{m.group(1)} is assigned a literal value; keep secrets in GitHub Secrets", line)
