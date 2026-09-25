# thesis-ci

**Thesis as code.** Maintain an investment thesis like a software project, and check it with CI.

A Chinese version is in [zh-CN/README.md](zh-CN/README.md).

> Not investment advice. thesis-ci never fetches prices, produces no buy or sell signals and executes no trades.

## What it is

thesis-ci is an open format specification and linter for owner-style investment thesis archives:

| Software engineering | In thesis-ci |
| --- | --- |
| Source code | `thesis.yml`: a company's thesis, ratings, industry dependencies and thesis tests |
| Unit tests | Thesis tests: quantitative, qualitative and staleness tests with thresholds written down in advance ("what would prove me wrong") |
| CI | Every new 10-Q, 10-K or 8-K triggers all tests |
| Lint | `thesis-ci lint`: every number carries a source, public content has no valuation or advice, every constitution rule maps to an executable check |

The specification (v0.2) lives in [`spec/`](spec/): [`SPEC.md`](spec/SPEC.md) (a Chinese version is in
[`zh-CN/spec/SPEC.md`](zh-CN/spec/SPEC.md)), 16 JSON Schemas, the check registry [`checks.yml`](spec/checks.yml)
(35 checks), the metric registry [`metrics.yml`](spec/metrics.yml) and the six Lynch monitoring templates in
[`templates/lynch/`](spec/templates/lynch/). Where `SPEC.md` and the machine-readable files disagree, the
machine-readable files win.

An archive is a pair of repositories: a public one (`visibility: public` in `repo.yml`) with theses,
pre-registrations, forecasts and letters, and a private one (`visibility: private`) with value ranges, L3 memos,
escalation requests, the series ranking and the decision log with amounts. `thesis-ci lint` reads `repo.yml` to
decide which checks apply. A pre-registration is three files per event: the immutable items file
`prereg/<period>.yml` (the owner's overrides in `<period>-owner.yml`), the timestamp proof `<period>.yml.ots`, and the
settlement file `<period>.settlement.yml` kept by the pipeline (SPEC 2.1). Archives are English-first: the Chinese
version of a key document lives at `zh-CN/<same path>`, and every other file is in English (SPEC 8.5).

## Quickstart

```bash
pip install git+https://github.com/kentian742-creator/thesis-ci
thesis-ci lint path/to/archive                  # runs the checks that apply to repo.yml's visibility
thesis-ci lint path/to/private --counterpart path/to/public   # private checks may read the public decision rights
thesis-ci lint path/to/archive --format json --today 2026-09-24 --only C-SRC-TAG C-STORY
thesis-ci lint . --expect-visibility public     # lint as a public archive; fail if repo.yml says otherwise
thesis-ci lint . --base-ref origin/main --period FY2027Q1   # after results: thresholds in force stay frozen
thesis-ci checks                                # every check: scope, level, implemented, selftest result
thesis-ci selftest                              # each check must flag a violating fixture and pass a clean one
thesis-ci staleness path/to/archive --today 2026-09-24   # evaluate the staleness tests of every thesis.yml
thesis-ci brier path/to/archive/forecasts/2026.yml       # Brier score and calibration bins per domain and book
```

- `lint` exits 1 when there is any error-level finding, 0 otherwise (warnings do not fail); usage errors exit 2.
- `--expect-visibility public|private` runs the checks for that visibility whatever `repo.yml` says and reports a
  mismatch as a `C-SCHEMA` error. A public archive's CI should pass `--expect-visibility public`; otherwise changing
  `repo.yml` to `private` skips every public check.
- `--base-ref <git ref> --period FY<year>Q<quarter>` compares the thesis tests with that ref (`C-TEST-FROZEN`): the
  criteria of tests in force for the period may not be edited or removed. Without both, the check passes vacuously.
- `--format json` prints `{"repo", "visibility", "errors": [{"check","file","line","message"}], "warnings": [...], "checks_run": [...]}`.
- `staleness` exits 1 when a test fails. `brier` scores resolved forecasts only (`happened` / `not_happened`):
  BS = mean((p − o)²); answering 50% every time scores 0.25.

As a GitHub Action:

```yaml
- uses: actions/checkout@v5
- uses: kentian742-creator/thesis-ci@v0.3.0
  with:
    path: .                      # archive repository root
    # counterpart: ../private    # optional: the other side
    expect-visibility: public    # optional, recommended for a public archive
    # base-ref: origin/main      # optional, with period, for C-TEST-FROZEN (check out with fetch-depth: 0)
    # period: FY2027Q1
```

## Checks

| id | scope | level | check |
| --- | --- | --- | --- |
| `C-SCHEMA` | both | error | Files match their schemas |
| `C-SRC-TAG` | both | error | Fact numbers in Markdown carry source tags |
| `C-SRC-FACT` | both | error | YAML facts carry resolvable sources |
| `C-SRC-ACCESSION` | both | warning | Periodic-report sources carry an EDGAR accession number |
| `C-PUBLIC-NO-VALUATION` | public | error | The public repository contains no value ranges or price ranges |
| `C-PUBLIC-NO-ADVICE` | public | error | Public content contains no buy/sell advice |
| `C-PUBLIC-NO-AMOUNTS` | public | error | The public repository contains no position amounts |
| `C-NO-PRICE-FEED` | both | error | No daily share prices are fetched |
| `C-NO-TRADING` | both | error | No trades are executed |
| `C-LLM-ENTRY` | both | error | Model calls only in pipeline/llm.py |
| `C-NO-SECRETS` | both | error | No secrets are committed |
| `C-TESTS-MIN` | public | error | At least 5 tests per company, all three types |
| `C-TESTS-COVERAGE` | public | error | Tests cover the touchstones of business quality |
| `C-TESTS-CAPALLOC` | public | error | Tests cover capital allocation |
| `C-TEST-METRIC` | public | error | Quantitative tests are executable |
| `C-TEST-QUAL-EVIDENCE` | public | error | Qualitative tests require an independent judgment and sources |
| `C-STALENESS` | public | warning | Staleness tests can be computed and are not expired |
| `C-DEPENDS` | public | error | Industry dependencies resolve and industry modules stay neutral |
| `C-STORY` | public | error | The two-minute story exists and is short enough |
| `C-RATING-ORDER` | both | error | Quality first, management second, valuation third |
| `C-CONCENTRATION` | both | error | Concentrated holdings and the entry bar |
| `C-DISCOUNT-RATE` | private | error | Discount rate = 10-year Treasury yield + this company's premium, with the basis written down |
| `C-SELL-REASONS` | both | error | Sell only for permanent deterioration or a clearly better opportunity |
| `C-HURDLE` | private | error | The long-term expectation clears the Berkshire or VOO hurdle |
| `C-SINGLE-ORDER` | both | error | A position is built with one order |
| `C-DEFAULT-HOLD` | both | error | Money matters default to no action |
| `C-DECISION-RIGHTS` | public | error | The three decision levels are consistent |
| `C-CONSTITUTION-MAP` | public | error | Every constitution rule has an executable check |
| `C-AGENT-ISOLATION` | public | error | What the auditor and the blind reader see is isolated |
| `C-PREREG-TIMING` | public | error | Pre-registrations are merged before the results are first public |
| `C-PREREG-IMMUTABLE` | public | error | Pre-registrations cannot change after the deadline |
| `C-TRUST-WRITE` | public | warning | Trust levels and review dates are maintained by the pipeline |
| `C-TEST-FROZEN` | public | error | Thresholds for the current period do not change after the results are out |
| `C-PROMPT-ISOLATION` | private | warning | Prompt inputs stay within what the role may see |
| `C-LANGUAGE` | both | error | English files contain no CJK text |

The scope is `public`, `private`, `both`, or `workspace` (runs only with `--counterpart`). Full definitions are in
[`spec/checks.yml`](spec/checks.yml). Implementation notes:

- **Sources (SPEC 3.1, 3.4).** Chinese, Japanese and Korean text is split into sentences at the Chinese full stop,
  exclamation mark, question mark and semicolon and at every newline. English text is split at `.`, `!`, `?` and `;`
  followed by whitespace, but not inside a decimal (`3.5%`), after an abbreviation (`U.S.`, `Inc.`, `e.g.`, `vs.`,
  `No. 1`) or inside a source tag; a line break inside an English paragraph does not end a sentence (hard-wrapped
  prose), while a blank line, a heading, a list item, a table row or a block quote does. A sentence with a fact number
  (`$495`, `16%`, `1.04×`, `2 percentage points`, ...) needs a `[src:TAG#LOCATOR]` tag; a tag written right after the
  period (`16%.[src:TAG]`) belongs to that sentence. Other spellings of the SPEC 3.4 units count too: English
  (`16 percent`, `30 basis points`, `40 cents`, `1.2 trillion`, `3 bn`, `25x`, in any letter case), other currencies
  (`€500`, `RMB 5`, `5 USD`, `5 dollars`) and the Chinese units and magnitudes; any whitespace may separate number and
  unit, and zero-width characters do not split them. Years, dates (`September 30, 2026`), quarters, `FY2026`, `3Q26`
  and section numbers are not facts (nor is a date followed by a programme name); front matter, code and link URLs are
  ignored. Markdown under `companies/`, `industries/`, `letters/` and the root `mistakes.md` is checked, and so are
  their Chinese versions under `zh-CN/`. Tags resolve through `sources.yml` in the file's directory and its parents,
  up to the repository root (for a `zh-CN/` file, from the directory of the file it translates).
- **YAML free text.** Fact numbers in `claim`, `summary`, `category_rationale`, `pillars[].claim`,
  `permanent_loss_paths`, `structure`, `implication`, `observable`, `title`, `note`, `statement` and `label` need tags
  too; `fail_if`, `warn_if`, `threshold`, `question` and `rule` are pre-registered criteria, not facts. A `source`
  field in any YAML under `companies/` or `industries/` (update records and every document of a stream included)
  must resolve.
- **YAML dates** are converted to ISO strings before JSON Schema validation, with format checking on (`2026-02-30`, for
  example, is an error). A repeated key
  (PyYAML silently keeps the last value) is a `C-SCHEMA` error; files under `companies/<TICKER>/` must name that
  company, `industry.yml` must carry its directory's id, a tag may appear once per `sources.yml`, and with
  `--counterpart` the two archives must not declare the same `visibility`.
- **What is scanned.** Every directory except `.git`, virtual environments, caches, `build/` and `dist/`, hidden ones
  such as `.claude/` included (they are published too). Inside a git work tree only what git would publish is scanned
  (tracked files and untracked files that are not ignored), so an ignored local `.env` or `logs/` does not fail the
  lint; if an enclosing repository ignores the archive itself, every file is scanned.
- **Public keys and wording.** Key checks read every YAML document (also the ones after `---`) and JSON data files,
  with key names normalized (`valueRanges` and `Value-Ranges` both mean `value_ranges`). The phrase lists are exactly
  the terms of 00 §H4; other wordings of the same valuation or advice are matched as patterns, in Chinese and in
  English (`implied return`, `price grade`, `central value` or `fair range` with a number, `I recommend buying`,
  `rated a Buy`, `investors should sell`, `add to the position`, `buy the dip`, ...; SPEC 7.5). `companies/` (with
  `updates/`), `industries/`, `forecasts/`, `letters/`, the root `mistakes.md`, the progress files `docs/STATUS.md` and
  `CLAUDE.md`, and their Chinese versions under `zh-CN/` are scanned; a price grade next to a ticker (`AXP B− → C`) in a
  sentence about prices or valuation is an error. As in Chinese, a negative sentence is no exception (`we do not recommend buying` fails, 00
  §H4), but a company buying back its own shares (`buyback`, `the company should buy back stock`) or a product name is
  not advice. A
  price-derived multiple (`P/E`, `price-to-earnings`, `market cap`, `FCF yield`, `P/B`, `trades at 25 times
  earnings`, and the Chinese terms) with a number in the same sentence is an error; years, dates, periods, section
  numbers and one-digit numbers do not count. Wording checks apply NFKC, drop zero-width characters and map
  traditional to simplified Chinese characters first; Chinese phrases may contain spaces and English words may be
  joined by spaces, `_` or `-`, so traditional or spaced spellings of a Chinese phrase and `strong-buy` are found.
  `overweight` / `underweight` count as advice only as a rating (`Rating: Overweight`, `rated Overweight`), not in
  `overweight adults`.
- **Two-minute stories (SPEC 5).** A story written in Chinese, Japanese or Korean is at most 700 characters; a story
  written in English at most 350 words, about two minutes read aloud. Source tags, markup and link targets do not
  count.
- **English first (SPEC 8.5).** `C-LANGUAGE` reports every text file outside the root `zh-CN/` directory that
  contains Chinese, Japanese or Korean characters (punctuation and full-width forms included), once per file at its
  first such line. Tests and fixtures, which may exercise Chinese text, are exempt, and so is the `title_original` of
  a `sources.yml` entry, which quotes a source's title in its own language.
- **Vacuous pass**: checks pass when their inputs do not exist yet (no memos, no pre-registrations, ...). A public
  archive must have `constitution/rules.yml` and `constitution/decision-rights.yml`.
- **Selftest.** `thesis-ci selftest` copies the bundled example archive
  ([`src/thesis_ci/fixtures/workspace`](src/thesis_ci/fixtures/workspace), fictitious data) to a temporary directory
  and applies at least one violating edit per check. `C-CONSTITUTION-MAP` requires every check the constitution
  references to pass its selftest, and every check that `spec/checks.yml` ties to a constitution rule ("Constitution
  rule N") to be referenced by some rule in `rules.yml`.

## Not included yet (planned phases)

- **EDGAR listener**: scheduled polling of the EDGAR submissions API and automatic PRs for new filings (phase 2).
- **Settlement** of pre-registrations and the say-do ledger against the pre-written criteria (semi-automatic in
  phase 1, automated in phases 2–3).
- **OpenTimestamps stamping** is the pipeline's job; `C-PREREG-IMMUTABLE` checks that a proof exists after the
  deadline and verifies it when the `ots` client is installed.
- Calibration dashboard and signpost-triggered review issues: phase 4, together with v1.0.

The specification stays at v0.x until two earnings seasons have run; incompatible changes are listed in the
[CHANGELOG](CHANGELOG.md).

## Development

```bash
pip install -e ".[test]"
pytest -q
thesis-ci selftest
```

To add a check: register it in `spec/checks.yml`, implement it in `src/thesis_ci/checks/` with `@check("C-...")`,
add at least one violating case to `src/thesis_ci/selftest.py`, and write a unit test whose docstring names the
check id. The test suite verifies that the registry and the implementations match one to one.

## License

Code: [MIT](LICENSE). Specification (`spec/`) and documentation, the Chinese versions in `zh-CN/` included:
[CC BY 4.0](LICENSE-SPEC.md).
