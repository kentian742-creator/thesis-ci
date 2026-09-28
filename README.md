# thesis-ci

**Continuous integration for investment theses.** thesis-ci turns a written thesis into tests that can fail, checks
that every number cites a filing, freezes each quarter's thresholds once results are public, and scores the forecasts
you registered before earnings.

> **Not investment advice.** thesis-ci fetches no prices, gives no buy or sell signals and executes no trades.

A Chinese version of this page is in [zh-CN/README.md](zh-CN/README.md).

## Why

Most investment theses are prose: easy to write, hard to check, and quietly revised when the facts change. thesis-ci
makes a thesis behave like code:

| Software | Investing, with thesis-ci |
| --- | --- |
| Source code | `thesis.yml`: the thesis, its grades for business quality, management and capital allocation, the industry modules it relies on, and its tests |
| Unit tests | Thesis tests, each written before the data (three kinds, below) |
| CI | `thesis-ci evaluate` judges the quantitative tests against a quarter's readings; once a period's results are out, CI rejects any edit to that period's thresholds (checked against git history) |
| Lint | `thesis-ci lint`: every number cites a primary source, public files are scanned for valuation figures and buy or sell wording, and you choose which groups of checks (profiles) apply |
| Test reports | `thesis-ci brier` scores resolved forecasts: Brier score and calibration by domain, and separately for the system's forecasts and the owner's overrides |

The three kinds of test:

- **Quantitative:** a number that must hold, computed from the company's SEC XBRL data or read off a named line of a
  filing, with the threshold, direction and number of consecutive periods written down in advance.
- **Qualitative:** a yes-or-no question answered from named documents by a separate model that must quote its
  evidence. thesis-ci defines the question, the documents and how far back to read; the model call belongs to your
  pipeline.
- **Staleness:** fails when a part of the thesis has not been reviewed within a set number of quarters.

It is built for individual investors and small teams who keep written theses and want them checkable, and for anyone
running an LLM research pipeline that needs guardrails: sourced facts, no advice in public output, and auditing models
that never see the drafting model's inputs.

## Profiles

Every check belongs to one of three profiles, and an archive chooses the ones it runs:

- **`core`**, for any thesis archive: files match their schemas; every number cites a source; thesis tests are
  complete and executable, and together cover moat, pricing power, returns on capital, free cash flow, capital
  allocation and management; reviews are not overdue; each company has a short two-minute story; pre-registrations
  are made before the results and never change; thresholds freeze once results are out; nothing commits a secret, fetches
  share prices or places orders; and a public archive holds no valuations, share prices, position amounts or buy and
  sell advice.
- **`pipeline`**, for an archive that an LLM research pipeline writes: all model calls go through one module, the
  auditor and the blind reader never see the drafts and conclusions they judge, each prompt gives its role only what
  the role may see, and only the pipeline changes trust levels and review dates.
- **`owners-office`**, one investor's rules: the constitution of
  [Owner's Office](https://github.com/kentian742-creator/owners-office), where thesis-ci was built. Holdings stay
  concentrated and a new position is at least 10% of the portfolio; a position is opened with a single order; a sale
  needs one of the allowed reasons; a purchase must clear a benchmark (Berkshire Hathaway first, an S&P 500 index fund
  second); a discount rate is the 10-year Treasury yield plus a company premium; a decision involving money defaults
  to doing nothing and rests with the owner; each constitution rule maps to a check; and every file outside `zh-CN/`
  is in English. Its checks of memos and valuations pass when there are none, but a public archive needs
  `constitution/rules.yml` and `constitution/decision-rights.yml`.

Choose them in `repo.yml`, for example `profiles: [core]` or `profiles: [core, pipeline]`. Most archives want `core`;
add `pipeline` if models write your research, and `owners-office` only if you adopt those rules as your own.
`thesis-ci init` starts a new archive with `profiles: [core]`. When `repo.yml` has no `profiles` line, every profile
runs, which is how thesis-ci behaved before profiles existed. `thesis-ci checks` shows each check's profile, and the
table under [Checks](#checks) lists them.

## What a test looks like

```yaml
# From the bundled example archive (fictitious company), lightly trimmed
- id: ACME-Q2
  type: quantitative
  claim: Gross margin shows that pricing power holds
  origin: report:breaker       # where the test came from: the research report's list of thesis breakers
  severity: breaker            # failing it breaks the thesis; "watch" only raises a flag
  covers: [pricing_power, moat]
  metric: gross_margin         # defined in spec/metrics.yml, computed from XBRL
  fail_if: below 55% for two consecutive quarters
  rule: {op: "<", threshold: 55, unit: "%", consecutive: 2, period: quarter}
  warn_if: below 58%
  effective_from: FY2027Q1     # judged from this period on; never edited once results are out
  baseline: {value: 62, unit: "%", period: FY2026, source: ACME-10K-FY2026#Item8}
```

The bundled example archive ([`fixtures/workspace`](src/thesis_ci/fixtures/workspace), fictitious data) shows every
file type. A real archive run on thesis-ci is public at
[owners-office](https://github.com/kentian742-creator/owners-office).

## The specification

The specification (v0.2) lives in [`spec/`](spec/): [`SPEC.md`](spec/SPEC.md) (a Chinese version is in
[`zh-CN/spec/SPEC.md`](zh-CN/spec/SPEC.md)), 18 JSON Schemas, the check registry [`checks.yml`](spec/checks.yml)
(35 checks), the metric registry [`metrics.yml`](spec/metrics.yml) and six monitoring templates in
[`templates/lynch/`](spec/templates/lynch/), one for each of Peter Lynch's company types (slow growers, stalwarts,
fast growers, cyclicals, turnarounds and asset plays). Where `SPEC.md` and the machine-readable files disagree, the
machine-readable files win.

Your research lives in an archive: a public repository (theses, forecasts, letters) and, if you keep valuations or
position sizes, a private one next to it (`visibility` in each `repo.yml` says which is which). `thesis-ci lint` reads
`visibility` and `profiles` in `repo.yml` to decide which checks apply. A pre-registration is three files per event
(SPEC 2.1):

- `prereg/<period>.yml`, the forecasts, frozen once the deadline passes (the owner's overrides go in
  `<period>-owner.yml`);
- `<period>.yml.ots`, the OpenTimestamps proof that the file existed before the results;
- `<period>.settlement.yml`, the settlement against the criteria written in advance.

With the `owners-office` profile, archives are English first: the Chinese version of a key document lives at
`zh-CN/<same path>`, and every other file is in English (SPEC 8.5).

## Quickstart

```bash
pip install git+https://github.com/kentian742-creator/thesis-ci
thesis-ci init my-archive                       # a new archive with one fictitious example company, profiles: [core]
thesis-ci lint my-archive                       # 0 error(s), 0 warning(s)
thesis-ci lint path/to/archive                  # runs the checks of repo.yml's profiles that apply to its visibility
thesis-ci lint path/to/private --counterpart path/to/public   # lint the private side with the public one alongside
thesis-ci lint path/to/archive --format json --today 2026-09-24 --only C-SRC-TAG C-STORY
thesis-ci lint . --expect-visibility public     # lint as a public archive; fail if repo.yml says otherwise
thesis-ci lint . --profile core                 # run the core checks only, whatever repo.yml says
thesis-ci lint . --base-ref origin/main --period FY2027Q1   # after results: thresholds in force stay frozen
thesis-ci checks                                # every check: profile, scope, level, implemented, selftest result
thesis-ci selftest                              # each check must flag a violating fixture and pass a clean one
thesis-ci staleness path/to/archive --today 2026-09-24   # evaluate the staleness tests of every thesis.yml
thesis-ci brier path/to/archive/forecasts/2026.yml       # Brier score and calibration by domain, system vs owner
thesis-ci evaluate path/to/archive --company ACME --period FY2027Q1 --readings readings.yml   # judge the quantitative tests (SPEC 4.5)
```

- `init <dir> [--visibility public|private] [--profiles core,pipeline,owners-office]` writes `repo.yml`, a short
  `README.md` and one example company, `companies/ACME/` (`thesis.yml` with five tests, the minimum, including a
  quantitative, a qualitative and a staleness test; `story.md`; `sources.yml`). The data are fictitious. It never
  overwrites a file: if any of them exists, it writes nothing and exits 2. A public archive with `owners-office` also
  gets the two files that profile requires, `constitution/rules.yml` and `constitution/decision-rights.yml`.
- `lint` exits 1 when there is any error-level finding, 0 otherwise (warnings do not fail); usage errors exit 2.
- `--profile core,pipeline` runs those profiles instead of the ones `repo.yml` names (repeat the option or separate
  names with commas). `--only` runs exactly the checks it names, whatever the profiles.
- `--expect-visibility public|private` runs the checks for that visibility whatever `repo.yml` says and reports a
  mismatch as a `C-SCHEMA` error. A public archive's CI should pass `--expect-visibility public`; otherwise changing
  `repo.yml` to `private` skips every public check. For the same reason CI can pin the profiles with `--profile`, so
  that removing a profile from `repo.yml` does not switch its checks off.
- `--base-ref <git ref> --period FY<year>Q<quarter>` compares the thesis tests with that ref (`C-TEST-FROZEN`): the
  criteria of tests in force for the period may not be edited or removed. Without both, the check is skipped and
  reported as passing.
- `--format json` prints `{"repo", "visibility", "errors": [{"check","file","line","message"}], "warnings": [...], "checks_run": [...]}`.
- `staleness` exits 1 when a test fails. `brier` scores resolved forecasts only (`happened` / `not_happened`):
  BS = mean((p − o)²); answering 50% every time scores 0.25.
- `evaluate` prints the `ci_results` of one company for one fiscal quarter (YAML, or JSON with `--format json`) and
  exits 0 whenever it ran: a failing test is a result, not an error.

As a GitHub Action:

```yaml
- uses: actions/checkout@v5
- uses: kentian742-creator/thesis-ci@v0.5.0
  with:
    path: .                      # archive repository root
    # counterpart: ../private    # optional: path to the paired public or private archive
    expect-visibility: public    # optional, recommended for a public archive
    # profile: core              # optional: run these profiles whatever repo.yml says
    # base-ref: origin/main      # optional, with period, for C-TEST-FROZEN (check out with fetch-depth: 0)
    # period: FY2027Q1
```

## Checks

| id | profile | scope | level | check |
| --- | --- | --- | --- | --- |
| `C-SCHEMA` | core | both | error | Files match their schemas |
| `C-SRC-TAG` | core | both | error | Fact numbers in Markdown carry source tags |
| `C-SRC-FACT` | core | both | error | YAML facts carry resolvable sources |
| `C-SRC-ACCESSION` | core | both | warning | Periodic-report sources carry an EDGAR accession number |
| `C-PUBLIC-NO-VALUATION` | core | public | error | The public repository contains no value ranges or price ranges |
| `C-PUBLIC-NO-ADVICE` | core | public | error | Public files are scanned for buy or sell wording |
| `C-PUBLIC-NO-AMOUNTS` | core | public | error | The public repository contains no position amounts |
| `C-NO-PRICE-FEED` | core | both | error | Code contains no daily share price feed (static scan) |
| `C-NO-TRADING` | core | both | error | Code contains no broker or order interface (static scan) |
| `C-LLM-ENTRY` | pipeline | both | error | All model calls go through one module, pipeline/llm.py |
| `C-NO-SECRETS` | core | both | error | No secrets are committed |
| `C-TESTS-MIN` | core | public | error | At least 5 tests per company, all three types |
| `C-TESTS-COVERAGE` | core | public | error | Tests cover moat, pricing power, returns on capital and free cash flow |
| `C-TESTS-CAPALLOC` | core | public | error | Tests cover capital allocation |
| `C-TEST-METRIC` | core | public | error | Quantitative tests are executable |
| `C-TEST-QUAL-EVIDENCE` | core | public | error | Qualitative tests require an independent judgment and sources |
| `C-STALENESS` | core | public | warning | Staleness tests can be computed and are not expired |
| `C-DEPENDS` | core | public | error | Industry dependencies resolve and industry modules stay neutral |
| `C-STORY` | core | public | error | Each company has a two-minute story (at most 350 English words or 700 CJK characters) |
| `C-RATING-ORDER` | owners-office | both | error | Quality first, management second, valuation third |
| `C-CONCENTRATION` | owners-office | both | error | Holdings stay concentrated, and a new position clears the entry bar |
| `C-DISCOUNT-RATE` | owners-office | private | error | Discount rate = 10-year Treasury yield + this company's premium, with the basis written down |
| `C-SELL-REASONS` | owners-office | both | error | A sale gives an allowed reason: permanent deterioration or a clearly better opportunity |
| `C-HURDLE` | owners-office | private | error | A purchase clears the benchmark: Berkshire Hathaway first, an S&P 500 fund second |
| `C-SINGLE-ORDER` | owners-office | both | error | A position is opened with a single order |
| `C-DEFAULT-HOLD` | owners-office | both | error | Decisions involving money default to doing nothing |
| `C-DECISION-RIGHTS` | owners-office | public | error | The three decision levels (act, act and report, the owner decides) are consistent |
| `C-CONSTITUTION-MAP` | owners-office | public | error | Every constitution rule has an executable check |
| `C-AGENT-ISOLATION` | pipeline | public | error | The auditor and the blind reader never see what they must judge independently of |
| `C-PREREG-TIMING` | core | public | error | Pre-registrations are merged before the results are first public |
| `C-PREREG-IMMUTABLE` | core | public | error | Pre-registrations cannot change after the deadline |
| `C-TRUST-WRITE` | pipeline | public | warning | Only the pipeline edits trust levels and review dates |
| `C-TEST-FROZEN` | core | public | error | Thresholds for the current period do not change after the results are out |
| `C-PROMPT-ISOLATION` | pipeline | private | warning | Prompt inputs stay within what the role may see |
| `C-LANGUAGE` | owners-office | both | error | English files contain no CJK text |

The profile is `core`, `pipeline` or `owners-office` ([Profiles](#profiles)). The scope is `public`, `private`, `both`,
or `workspace` (runs only with `--counterpart`). Full definitions are in [`spec/checks.yml`](spec/checks.yml), and SPEC
8.6 explains the profile of each borderline check.

How each check reads an archive (sentence splitting, what counts as a fact number, which files are scanned, wording
normalization, story length, the language check, vacuous passes and the selftest) is described in
[docs/reference.md](docs/reference.md).

## Not included yet

- **An EDGAR listener** that polls the submissions API and opens a pull request when a new filing arrives (planned).
- **Settlement** of pre-registrations and say-do ledgers against their written criteria: the file format is specified
  (`prereg-settlement.schema.json`); the settling itself is done by your pipeline.
- A calibration dashboard and signpost-triggered review issues, together with v1.0.

Out of scope: thesis-ci creates no timestamps. Stamp pre-registrations with the OpenTimestamps `ots` client;
`C-PREREG-IMMUTABLE` checks that a proof exists after the deadline and verifies it when `ots` is installed.

The specification stays at v0.x until two earnings seasons have run; incompatible changes are listed in the
[CHANGELOG](CHANGELOG.md).

## Development

```bash
pip install -e ".[test]"
pytest -q
thesis-ci selftest
```

To add a check: register it in `spec/checks.yml` with its profile, implement it in `src/thesis_ci/checks/` with
`@check("C-...")`, add at least one violating case to `src/thesis_ci/selftest.py`, write a unit test whose docstring
names the check id, and list it in the check tables of this README and SPEC 8.6 (and of their Chinese versions). The
test suite verifies that the registry, the implementations and those tables match one to one.

## License

Code: [MIT](LICENSE). Specification (`spec/`) and documentation, the Chinese versions in `zh-CN/` included:
[CC BY 4.0](LICENSE-SPEC.md).
