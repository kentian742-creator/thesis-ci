# thesis-ci format specification v0.2

A Chinese version is in [zh-CN/spec/SPEC.md](../zh-CN/spec/SPEC.md).

This specification defines the file formats of "thesis as code". The specification text is licensed under CC BY 4.0; the implementation code is licensed under MIT.
"MUST", "MUST NOT" and "SHOULD" in this specification are to be read as described in RFC 2119. The machine-readable definitions are `spec/schemas/*.schema.json`, `spec/checks.yml`, `spec/metrics.yml` and `spec/templates/lynch/*.yml`; where this file conflicts with them, the machine-readable files prevail.

In this text, "00 §X" means a clause of the series rules (prompt 00) that the archives follow, for example §H4 (public/private separation) and §G7 (write it down first, verify later).

## 1. Repository roles

| Role | Marker | Contents |
| --- | --- | --- |
| Public archive repository | `visibility: public` in `repo.yml` | Constitution, method, thesis.yml, two-minute stories, pre-registrations, forecasts, ledgers, quarterly updates, letters to the owner |
| Private archive repository | `visibility: private` in `repo.yml` | Value ranges, L3 memos, escalation requests, series ranking, decision log with amounts, complete reports, prompts |

Every archive repository MUST have a `repo.yml` at its root:

```yaml
visibility: public          # public | private
owner: kentian742-creator
spec_version: "0.2"
```

`thesis-ci lint <path>` reads `repo.yml` to decide which checks apply (see `scope` in `spec/checks.yml`). During the migration `spec_version: "0.1"` is still accepted, but `C-SCHEMA` gives a warning; once an archive has been migrated to this specification, set it to `"0.2"`.

## 2. Directory layout

```text
companies/<TICKER>/thesis.yml     # public; thesis and thesis tests
companies/<TICKER>/story.md       # public; the two-minute reason for holding
companies/<TICKER>/sources.yml    # public; source tag table
companies/<TICKER>/prereg/        # public; pre-registrations, one set of files per earnings event (2.1)
companies/<TICKER>/ledger.yml     # public; say-do ledger (may be an empty list)
companies/<TICKER>/updates/       # public; a record of every update (Markdown; the front matter includes reviewed_sections)
industries/<id>/industry.yml      # public; industry module and signposts
industries/<id>/README.md         # public; industry module summary
industries/<id>/sources.yml
forecasts/<YYYY>.yml              # public; system forecasts and your overrides
letters/<YYYY-MM>.md              # public; monthly letters
mistakes.md                       # public; mistakes list (00 §G5)
constitution/rules.yml            # public; constitution rules and their checks
constitution/decision-rights.yml  # public; three decision levels, trust levels and routing
agents/<role>.yml                 # public; role definitions (what each role can see)
trust/levels.yml                  # public, optional; trust levels computed by the pipeline (4.2)
sources.yml                       # optional; repository-level source tag table
zh-CN/<path>                      # the Chinese version of a key document (8.5)

# private repository
companies/<TICKER>/valuation.yml  # value ranges, discount rate, implied return (section 7)
companies/<TICKER>/sources.yml
memos/<YYYY-MM-DD>-<TICKER>-<slug>.yml        # L3 memos (drafted by HQ)
escalations/<YYYY-MM-DD>-<TICKER>-<slug>.yml  # escalation requests (drafted by the company manager, sent to HQ)
hq/ranking.yml                    # series ranking (00 §V13)
decision-log/<YYYY>.yml
prompts/<number>-<name>.md        # prompts; the front matter declares the role and inputs of each part (8.3)
```

Mapping from file names to schemas (the first match applies):

| File | Schema |
| --- | --- |
| `repo.yml` | `repo.schema.json` |
| `companies/*/thesis.yml` | `thesis.schema.json` |
| `companies/*/sources.yml`, `industries/*/sources.yml`, `sources.yml` | `sources.schema.json` |
| front matter of `companies/*/story.md` | `story.schema.json` |
| `companies/*/prereg/*.settlement.yml` | `prereg-settlement.schema.json` |
| `companies/*/prereg/*.yml` (`<period>.yml` and `<period>-owner.yml`) | `prereg.schema.json` |
| `companies/*/ledger.yml` | `ledger.schema.json` |
| `companies/*/valuation.yml` | `valuation.schema.json` (private repository only) |
| `industries/*/industry.yml` | `industry.schema.json` |
| `forecasts/*.yml` | `forecast.schema.json` |
| `constitution/decision-rights.yml` | `decision-rights.schema.json` |
| `constitution/rules.yml` | `constitution-rules.schema.json` |
| `agents/*.yml` | `agent.schema.json` |
| `memos/*.yml` | `memo.schema.json` (private repository only) |
| `escalations/*.yml` | `escalation.schema.json` (private repository only) |
| `decision-log/*.yml` | `decision-log.schema.json` (private repository only) |

Other YAML files (`trust/levels.yml`, `hq/ranking.yml`, `updates/*.yml` and so on) are checked only for syntax and repeated keys; their content is read by the checks concerned.

### 2.1 The pre-registration trio

Each earnings event (period `FY<year>Q<quarter>`, in the company's fiscal year) has at most four files in `companies/<TICKER>/prereg/`:

| File | Written by | Contents | Immutable |
| --- | --- | --- | --- |
| `<period>.yml` | the system (15A, `author: system`) | file header and 1–8 expectations | after the deadline |
| `<period>-owner.yml` | the owner (`author: owner`) | new items (`added_by: owner`) and `overrides` that rewrite the probabilities of system items | after the deadline |
| `<period>.yml.ots` (and `<period>-owner.yml.ots`) | the pipeline | OpenTimestamps timestamp proof | — |
| `<period>.settlement.yml` | the pipeline (15B and GitHub) | merge time, acceptance time, accession number, settlement results | filled in at settlement |

Items file (`prereg.schema.json`):

```yaml
company: MSFT
event:
  period: FY2027Q1             # the period in the file name; must match
  expected_release: 2026-10-28
  form: 8-K                    # 8-K | 6-K | 10-Q | 10-K | 20-F
  placeholder: false           # whether the release date is a placeholder
deadline: "2026-10-27T23:59:59-04:00"   # ISO 8601 with a UTC offset; the end of the day before the release date (US Eastern Time)
author: system                 # system | owner, matching the file name
horizon: mixed                 # optional: quarter | 18m | mixed
items:
  - id: MSFT-FY2027Q1-1        # <TICKER>-<period>-<n>
    statement: Year-on-year revenue growth this quarter is no lower than last quarter's
    probability: 0.6           # 0.05–0.95
    criterion: Per the 10-Q income statement ...
    data_source: 10-Q income statement
    horizon: quarter           # quarter | 18m
    resolves_by: 2026-11-30
    domain: enterprise_software
    added_by: system           # always system in the system's file
    pillar: P1                 # optional
    falsifies_thesis: true     # optional
    reference: reference class, frequency and source   # optional
```

- The system's file has at least 1 and at most 8 items and MUST NOT have `overrides`. Items in the owner's file are written `added_by: owner`; the owner's file may contain only `overrides: [{id, probability, note?}]` (with `items: []`), but not both empty; its `deadline` is the same as the system file's.
- Items files do not contain `merged_at`, `ots_proof`, `acceptance_datetime`, `accession` or settlement results: these are known only after the deadline and go in the settlement file, so an items file can be timestamped before the deadline and then stay unchanged.
- The settlement file (`prereg-settlement.schema.json`): `company`, `period`, optionally `acceptance_datetime`, `accession`, `merged_at` (when the items file was merged into the default branch, taken from GitHub) and `ots_proof`, and `results: [{id, outcome, values?, calculation?, evidence?, source?, reasoning?, settled_at?, hq_ruling?}]`, where `outcome` is `happened`, `not_happened` or `undetermined`.
- `C-PREREG-TIMING` checks that the deadline falls before the release date, that `merged_at` is earlier than the deadline, and that the deadline is earlier than `acceptance_datetime`. `C-PREREG-IMMUTABLE` checks that once the deadline has passed an items file has `<file>.ots` next to it; when the `ots` client is installed, it first compares the file's sha256 with the hash recorded in the proof, locally (`ots info`, no network), and a mismatch or an unreadable proof is an error; once they match, `ots verify` checks the time attestation, and a missing Bitcoin node, a proof still awaiting confirmation or unreachable calendar servers give only a warning.

## 3. Source tags

### 3.1 Syntax

In Markdown, a source tag is written `[src:TAG]` or `[src:TAG#LOCATOR]`:

- `TAG` matches `^[A-Z0-9][A-Za-z0-9._-]*$` and MUST be registered in the applicable `sources.yml`.
- `LOCATOR` is a position within the source, containing no whitespace and no `]`, e.g. `p3`, `Item7`, `MD&A`, `note-12`.

Regex: `\[src:([A-Z0-9][A-Za-z0-9._-]*)(?:#([^\]\s]+))?\]`

In YAML, a fact is written as an object whose `source` field takes the same `TAG` or `TAG#LOCATOR` string:

```yaml
value: 52
unit: "%"
period: FY2026
as_of: 2026-06-30
source: MSFT-10K-FY2026#Item8
```

`settlement_source` and `acknowledged_source` are source fields as well.

### 3.2 Tag resolution order

1. `sources.yml` in the same directory (company or industry);
2. `sources.yml` at the repository root.

A tag that is not found is an error.

### 3.3 Naming convention (SHOULD, as in 00 §E1)

| Kind | Format | Example |
| --- | --- | --- |
| Own report | `<TICKER>-RPT<n>-<YYYY-MM-DD>` | `MSFT-RPT1-2026-09-17`, `MSFT-RPT2-2026-09-30` |
| Periodic report | `<TICKER>-<FORM>-<PERIOD>` | `MSFT-10K-FY2026`, `AXP-10Q-FY2026Q2`, `PDD-20F-FY2025` |
| Current report | `<TICKER>-<FORM>-<YYYY-MM-DD>` | `MSFT-8K-2026-09-02` |
| Earnings call transcript | `<TICKER>-CALL-<PERIOD>` | `AXP-CALL-FY2026Q2` |
| News | `<TICKER>-NEWS-<YYYY-MM-DD>-<outlet>` | `APP-NEWS-2026-03-12-WSJ` |
| Review page | `<TICKER>-REV-<platform>-<YYYY-MM-DD>` | `PDD-REV-TRUSTPILOT-2026-09-01` |
| Other web page | `<TICKER>-WEB-<YYYY-MM-DD>-<n>` | `SPGI-WEB-2026-08-30-1` |
| The dossier itself | `<TICKER>-DOSSIER-<version date>` (locator `#s<part>`) | `MSFT-DOSSIER-2026-09-24#s3` |
| Shareholder letter | `<TICKER>-LTR-<YYYY>` | `BRK-LTR-2024` |
| Industry report | `IND-<ID>-<YYYY-MM>` | `IND-PAYMENTS-2026-09` |

`FORM` drops the hyphen: `10K`, `10Q`, `8K`, `6K`, `20F`, `DEF14A`. The `PERIOD` of a periodic report follows the company's own fiscal year (`FY2026`, `FY2027Q1`), written as in the pre-registration periods; the date of a current report is EDGAR's filing date (a filing accepted after 17:30 US Eastern Time moves to the next business day), not the date on the press release. When two filings of the same form on the same day both need to be registered, the later one by accession number gets `-2`, `-3` (e.g. `PDD-6K-2025-12-19-2`), and its `note` gives the accession number. Own reports carry a number and a full date, so two reports in the same month do not collide; the old form `<TICKER>-RPT-<YYYY-MM>` still resolves, but SHOULD be migrated before a pre-registration is timestamped, so that the old tag is not frozen into the timestamp.

### 3.4 What is a "number that needs a source"

In the body of a Markdown file (not counting front matter, code blocks, inline code and link URLs), any of the following is a fact number:

- a dollar sign followed by a digit: `\$\s?\d`
- a digit followed by a unit: `\d[\d,.]*\s?(%|％|亿|万|千万|百万|美元|元|倍|×|pp|个百分点|bp|bps|基点|美分|¢|bn|million|billion)`

Bare years, dates and quarters (`2026`, `FY2027`, `2026-09-24`, `Q2`, `2026 年`), section numbers and list numbers are not.
**Rule:** every sentence (separated by `。！？；` or a newline) that contains a fact number MUST contain at least one `[src:...]` tag. Thresholds and forecasts written down in advance (a test's `fail_if`, `warn_if` and `rule`, pre-registration items, the system's and the owner's predictions in the ledger) are not facts and need no tag; a baseline number quoted in the same sentence is tagged as usual.

**English text (thesis-ci 0.3.0).** The rule applies to English text with English sentence boundaries: a sentence ends at `.`, `!`, `?` or `;` followed by whitespace (a closing quotation mark or parenthesis may come in between, and so may a source tag written right after the punctuation, which then belongs to that sentence). A period is not a sentence end inside a number (`3.5%`), after a common abbreviation (`U.S.`, `Inc.`, `Corp.`, `Ltd.`, `e.g.`, `i.e.`, `vs.`, `No. 1`, an initial or an abbreviated month) or inside a source tag. A line break inside an English paragraph does not end a sentence, because English prose is often hard-wrapped; a blank line, a heading, a list item, a table row and a block quote do. A line that contains Chinese, Japanese or Korean characters is split as described above, at `。！？；` and at every newline. The units of the regex also count in their other spellings, in any letter case: `percent`, `per cent`, `pct`, `percentage points`, `pp`, `ppt`, `basis points`, `bp`, `bps`, `cents`, `thousand`, `million`, `mn`, `mln`, `billion`, `bn`, `bln`, `trillion`, `tn`, a multiple such as `25x`, currency names (`dollars`, `euros`, `yuan` and so on), currency codes before or after the number (`USD 5`, `5 USD`, `RMB 5`) and other currency symbols (`€`, `£`, `¥`, `₹`). English dates (`September 30, 2026`, `30 June 2026`), periods (`FY26`, `3Q26`, `1H26`) and section numbers (`Item 7A`, `Section 3.4`, `Note 12`) are not facts.

### 3.5 sources.yml entries

See `sources.schema.json`. `kind` takes `filing`, `report`, `industry_report`, `transcript`, `press_release`, `letter`, `presentation`, `proxy`, `news`, `review`, `web` or `other`. An entry with `kind: filing` SHOULD have an `accession` (EDGAR accession number); a missing one is a warning, not an error.

Titles are in English. A source in another language (such as the owner's reports in Chinese) gives its English translation followed by "(in Chinese)" in `title`, and may quote its original title verbatim in the optional `title_original`, the one field of an archive outside `zh-CN/` that may contain CJK text (8.5).

## 4. thesis.yml

See `thesis.schema.json` (`schema_version: "0.2"`). Key points:

- `status`: `holding`, `candidate`, `archive`.
- `category`: one of Lynch's six categories: `slow_grower`, `stalwart`, `fast_grower`, `cyclical`, `turnaround`, `asset_play`. The category determines the default monitoring template (`spec/templates/lynch/<category>.yml`); a change of category means a change of template.
- `domain`: the calibration group; see the schema enum.
- `depends_on`: a list of industry module paths such as `industries/payments-card-networks`; may be empty.
- `trust_level`: the company manager's trust level, 0–3, maintained by the pipeline (4.2).
- `reviewed`: the date each part of the dossier was last reviewed, used by the staleness tests. The twelve required keys correspond to the twelve parts of the dossier: `business`, `economics`, `moat`, `capital_allocation`, `management`, `culture`, `runway`, `valuation`, `bear_case`, `monitoring`, `thesis`, `breakers`; the two supplementary lists `munger` (the Munger matrix, the dossier's first supplementary list) and `unknowns` (the unknowns register) are optional. The keys are the same as `archive_patch.section` in 00 §F5 (except `ratings`).
- `ratings`: only `business` and `management` (required) and `capital_allocation` and `culture` (may be omitted; omitted means left blank, not neutral); **price grades, value ranges and any price numbers MUST NOT appear in the public thesis.yml**; they belong in the private repository's `valuation.yml`.
- `tests`: at least 5 tests still in force, with at least 1 of each of the three types (`quantitative`, `qualitative`, `staleness`).

### 4.1 thesis tests

Fields every test has: `id` (`<TICKER>-<Q|L|S><n>`), `type`, `claim` (the part of the thesis this test guards, in one sentence), `origin`, `severity`, `covers`, `effective_from`; optionally `supersedes`, `retired_at`, `pillar`, `note`.

- `origin`: `template:<category>` (from a Lynch template), `report:breaker` / `report:watch` (from the report's thesis breakers / watch signals), `archive:breaker` / `archive:watch` (from part 12 / part 10 of the dossier), `proposal:04B`, `proposal:04B-lite`, `proposal:07`, `proposal:08`, `proposal:11` (a test proposed by an audit or research step and adopted by the company manager), `manual` (written by the company manager).
- `severity`: `breaker` (a failure voids that part of the investment case; it is handled within 7 days under 00 §G3) or `watch` (a failure is a warning and goes into the next update).
- `covers`: the quality dimensions the test examines; see the schema enum. Constitution rules 2 and 3 require the tests still in force for each company to cover, together, `moat`, `pricing_power`, `returns_on_capital`, `free_cash_flow`, `capital_allocation` and `management`.
- **Lifecycle (00 §G7).** `effective_from` (`FY<year>Q<quarter>`): the test is judged from this period on; new or changed tests apply only to later periods. A threshold is changed without editing the old entry: write a new test whose `supersedes` names the old test's id, and give the old test `retired_at` (from that period on it is no longer judged; the entry stays as a record). A test with `retired_at` does not count toward the minimum of 5 tests or the coverage requirements; when `--period` is given, only a test whose `retired_at` is not later than the current period counts as retired.
- `note` may carry thesis wording; the judge does not see it. Rules for the judge go in a qualitative test's `judge_notes`.

**Quantitative tests** (`type: quantitative`):

```yaml
- id: MSFT-Q1
  type: quantitative
  claim: Microsoft Cloud's gross margin holds above the level at which the capex cycle pays back
  origin: report:breaker
  severity: breaker
  covers: [returns_on_capital]
  metric: microsoft_cloud_gross_margin      # an id in spec/metrics.yml, or define it in place with metric_def
  fail_if: below 58% for two consecutive quarters
  rule: {op: "<", threshold: 58, unit: "%", consecutive: 2, period: quarter}
  warn_if: below 62%
  warn_rule: {op: "<", threshold: 62, unit: "%", consecutive: 1, period: quarter}
  data: filing_text                          # xbrl | filing_text | external | mixed
  effective_from: FY2027Q1
  first_readable: 2026-10
  baseline: {value: 66, unit: "%", period: FY2026, source: MSFT-RPT1-2026-09-17#p10}
```

- `data`: `xbrl` (EDGAR XBRL), `filing_text` (the text of a filing, extracted by a model with its source noted), `external` (official data from outside SEC filings, such as FRED, NAIC or ETF assets under management), `mixed` (components come from different sources). `data` MUST match the metric definition.
- `rule` may combine several sub-rules with `all_of` / `any_of`. A threshold is a criterion written down in advance and needs no source; `baseline` is a fact and MUST have a source.
- **A test that uses several quantities** writes `metric_def.components`: component name (`^[a-z][a-z0-9_]*$`) → `{description, unit, where?, xbrl?}`; a sub-rule's `metric` is a component name or `<metric>.<component>` (before the dot: this test's `metric` or `metric_def.id`). `rule.metric` MUST resolve: a metric in the registry, this test's metric, or one of its components. The `params.metric_defs` of 0.1 still resolves during the migration and SHOULD be rewritten as `components`; `params` itself is still allowed (e.g. `params.segment`).

```yaml
  metric_def:
    id: recurring_share
    description: recurring revenue ÷ total revenue
    unit: "%"
    data: mixed
    formula: recurring / revenue
    components:
      recurring: {description: recurring revenue, unit: USD, where: revenue disaggregation note of the 10-K}
      revenue: {description: total revenue, unit: USD, xbrl: ["us-gaap:Revenues"]}
  rule:
    all_of:
      - {metric: recurring_share, op: "<", threshold: 50, unit: "%", consecutive: 2, period: year}
      - {metric: recurring_share.recurring, op: decrease, threshold: 0, unit: "%", period: year}
    evaluate_from: FY2028Q4
```

- **Choosing periods**: `rule` (and its sub-rules) may give `evaluate_on` (evaluate only in these periods) or `evaluate_from` (evaluate from this period on), with values `FY<year>` or `FY<year>Q<quarter>`.

**Qualitative tests** (`type: qualitative`): MUST have `question` (a yes/no question an independent model answers), `fail_if`, `judge: independent_model`, `evidence: required`, `where` (which documents are read for the judgment: a string or a list of strings, which the pipeline fetches) and `lookback` (how many periods of documents are read, the current one included; a positive integer; a period is a fiscal quarter, counted as for `effective_from`, with annual filings converted to fiscal quarters: to reach back to the previous annual report, for example, write 5); optionally `judge_notes` (rules for the judge, a string or a list). A judgment MUST give its source and a quotation of at most one sentence from the original text.

**Staleness tests** (`type: staleness`): `section` is one of the fourteen keys of `reviewed`, and `max_age_quarters` is an integer; measured from `reviewed.<section>`, the test fails once more than `max_age_quarters × 91` days have passed.

A test has only four possible results: `pass`, `warn`, `fail`, `undetermined`. How quantitative tests are judged is set out in 4.5.

### 4.2 Fields maintained by the pipeline (00 §G8)

A company manager MUST NOT change `trust_level`, `status`, `filer` or `schema_version`. The pipeline records each role's trust level in the public repository's `trust/levels.yml`:

```yaml
as_of: 2026-10-30
companies:                 # company managers, by ticker
  MSFT: 1
industries:                # industry researchers, by industry module id (matching trust_level in industry.yml)
  payments-card-networks: 1
```

`C-TRUST-WRITE` (warning) checks that `trust_level` in `thesis.yml` agrees with this file (and likewise `trust_level` in `industry.yml`, when written). A `reviewed` date is updated only for the parts actually reviewed this time, and those parts are listed in `reviewed_sections` in the front matter of that update's record:

```markdown
---
company: MSFT
doc: update
as_of: 2026-10-30
doc_status: final
reviewed_sections: [economics, monitoring]
---
```

For every `reviewed` date in `thesis.yml` that equals the `as_of` of an update, the part MUST be listed in that update's `reviewed_sections` (several updates on the same day count together).

### 4.3 Thresholds do not change once the results are out (00 §G7)

`thesis-ci lint --base-ref <git ref> --period FY<year>Q<quarter>` compares the tests in `thesis.yml` one by one with the version at that ref (`C-TEST-FROZEN`): for tests in force for the current period (the base version's `effective_from` is not later than the current period and the test is not retired; an old test without `effective_from` counts as always in force), `rule`, `fail_if`, `warn_rule`, `warn_if` and `max_age_quarters` MUST NOT be changed, and the test MUST NOT be deleted. A change of formatting only (for example a flow mapping rewritten as a block mapping) is not a change. A PR made after results filings have arrived SHOULD pass both options.

### 4.5 Evaluation (thesis-ci 0.4.0)

`thesis-ci evaluate <archive> --company <TICKER> --period FY<year>Q<quarter> --readings <file> [--today YYYY-MM-DD] [--format yaml|json]` judges one company's quantitative tests against a readings document and prints a `ci_results` document (`ci-results.schema.json`). It exits 0 whenever it ran, because a failing test is a result, not an error; a usage error (an unreadable or invalid file, companies that disagree) exits 2.

**Readings** (`readings.schema.json`): `{company, as_of, readings: [{metric, period, value, unit, source, basis?, note?, segment?, series?}]}`.

- `metric` is a registry id, a test's `metric` or `metric_def.id`, or `<metric>.<component>`; a reading for an `op: event` sub-rule that names no metric is keyed by the test id (`MSFT-Q9`). `period` is `FY<year>`, `FY<year>H<half>` or `FY<year>Q<quarter>`, in the company's fiscal year. `source` is a source tag (3.1).
- `value` is a number, `true` or `false` for an event, or `null` when the metric was checked and there is nothing to measure (no qualifying event, or not computed by its definition); a `null` reading needs a `note`. A reading that could not be found is left out, never written as `null`.
- A test with `params.segment` uses only readings whose `segment` equals it, and a test without one only readings without one. Readings of one metric that carry `series` (for example one per holder group in `params.holders`) are judged series by series, and a sub-rule holds when it holds for any series.
- `data: xbrl` metrics can be computed from EDGAR companyfacts (`thesis_ci.metrics`): only 10-K, 10-Q, 20-F and 40-F facts, each placed in the fiscal calendar by its start and end dates, the most recently filed value of a span winning; quarters no filing reports on their own are derived from year-to-date figures (Q4 = FY − 9M), except share counts and per-share amounts; the source is `<TICKER>-XBRL#<concept>:<accession>`. A metric that cannot be computed is left out.

**Which tests, which periods.** Only tests in force for the period are judged (`effective_from` ≤ period < `retired_at`); the others are listed under `not_in_force`. A `quarter` or `event` rule reads the evaluated quarter; a `half` rule reads the half that ends with it (`FY<year>H<n>`, judged in Q2 and Q4); a `year` rule reads the fiscal year that ends with it (judged in Q4). A rule is not due when its period does not end with the quarter, when its `evaluate_on` does not name the quarter (a year in `evaluate_on` names each of its quarters), or when its `evaluate_from` is later. `all_of` is due only when all its sub-rules are; `any_of` when at least one is, and then only the due ones are judged. A test with nothing due is reported `not_due`, with the reason: this records that it was not judged this period and is not a fifth result.

**How a rule is judged.**

- A sub-rule without `period` inherits its parent's; the root's default is the frequency of the test's metric, else `quarter`.
- `consecutive` (default 1) on a comparison asks it to hold in each of the last N periods; on `all_of` or `any_of` it asks the combination to hold, in the same period, in each of the last N periods, and all the sub-rules must then share its `period`. Periods before `evaluate_from` never count toward the run.
- `increase` and `decrease` compare a reading with the same period one fiscal year earlier (for a quarter rule, the same quarter a year earlier; for a year rule, the previous year) and hold when the change exceeds `threshold`: in `pp`, the difference of two percentages; in `%`, the relative change of a metric that is not itself a percentage (a `%` threshold on a percentage is ambiguous and not accepted); in the metric's own unit, the difference.
- `between` includes both ends; `outside` is its complement. An event holds when its reading is `true`.
- Units of one kind are converted (`USD`, `USD million`, `RMB 100 million`, which is `CNY 100 million`); any other mismatch leaves the comparison undetermined.
- A missing reading leaves a comparison undetermined, and a run of `consecutive` periods whose latest period has no reading is undetermined even when an earlier period already breaks it: a result for a period rests on that period's data. `all_of` is not triggered as soon as one sub-rule is not triggered, and `any_of` is triggered as soon as one is, whatever else is missing. A `null` reading means the comparison does not hold.
- The fail rule is judged first: triggered gives `fail`, undetermined gives `undetermined`. Otherwise `warn_rule` is judged: triggered gives `warn`, undetermined gives `undetermined`, and anything else `pass`.

`C-TEST-METRIC` reports a rule the engine cannot judge (units that do not fit the metric, an ambiguous `increase` or `decrease` unit, an `evaluate_on` that can never be due). Each result carries `reading` (this period's reading of the rule's first metric), `readings` (every reading used, the earlier periods of a run and the year-earlier bases included), `rule` and `warn_rule` as registered (with `op`, `threshold` and `unit` when the rule is one comparison), `fail_if`, `warn_if`, `consecutive_count`, `missing` (the readings an undetermined result lacked), `reason`, and the judged rule tree under `evaluation`. Readings of a period that had not ended on `--today` are ignored and listed under `ignored_readings`.

### 4.4 The say-do ledger ledger.yml

See `ledger.schema.json`. `side`: `management` (management's commitments, settled on four grades: `kept`, `partially_kept`, `not_kept`, `silently_dropped`, or `undetermined`), `system` and `owner` (predictions; `probability` required, 0.05–0.95; the statuses are only `pending`, `kept`, `not_kept`, `undetermined`, and the criterion is written in `note`). `last_mentioned`: the date management last mentioned the commitment (to judge "silently dropped"); `acknowledged_source`: where management acknowledged an unmet commitment on its own (a source tag, or null).

## 5. story.md

The two-minute reason for holding. The YAML front matter is described by `story.schema.json`. The body of a story written in Chinese (or Japanese or Korean) is at most 700 characters, each character counting as one; the body of a story written in English is at most 350 words. Neither count includes source tags, Markdown markup or link targets. A story is measured in characters when it has at least as many CJK characters as English words. 350 words is about two minutes read aloud at 150–175 words a minute, and about what 700 Chinese characters become in English (a Chinese character carries roughly half an English word). The body MUST NOT contain prices, value ranges, implied returns, position sizes or buy/sell advice. Fact numbers carry sources as described in 3.4.

## 6. Industry modules

`industry.yml`: see `industry.schema.json`. An industry module describes only the industry itself: it MUST NOT list holdings, give advice, or name "companies that depend on this industry". Dependencies are written only on the company side, in `depends_on`. Every module has at least 3 observable signposts (`signposts`); each signpost has an observable quantity, a threshold written down in advance and a check frequency. The optional `trust_level` (0–3) records the industry researcher's trust level, maintained by the pipeline (4.2).

## 7. Files of the private repository

### 7.1 Value ranges valuation.yml

See `valuation.schema.json`. Key points:

- `doc_status`: `proposed` (a recalculated version awaiting review by 04C) or `effective` (the version in force). At any time a company has only one version in force (00 §V20).
- `value_ranges`: `center` (central value), `fair` (fair range), `cheap` (buy range), `error_band` (error band `[low, high]`: an absolute range in the unit of `center`, not a relative proportion).
- `margin_of_safety`: the margin-of-safety range `[lower bound, upper bound]`, as decimals, default `[0.25, 0.35]` (00 §V2).
- `discount_rate`: `risk_free` (the 10-year US Treasury yield), `risk_free_date` (the date it was read), `premium`, `total` (= `risk_free` + `premium`), `source`, `note`. When `total` has a value, `note` MUST be written: the basis for the premium, that is, which readings in this company's cash-flow record make it more predictable and which less (00 §V1). The premium is derived only from the company's own record and is not compared or interpolated across companies (00 §V10); `C-DISCOUNT-RATE` therefore does not check an order of premiums across companies.
- `comparable_anchor`: the second reference anchor `{value, description, source}`, the market-implied return of a comparable asset (00 §V6).
- `price_rating`: `A`–`E`, given by the mechanical scale of 00 §V11, without a plus or minus sign; `quality_rating` is the business rating, on the same scale as `ratings.business` in `thesis.yml`.
- `method_note`: a note on the method of this valuation; MUST NOT be empty.

### 7.2 L3 memos memos/*.yml

See `memo.schema.json`. Memos are drafted only by HQ (`drafted_by: hq_capital_allocator`): `options` has at least two options, and the `key` of one of them is `maintain` (the default option, `default_option: maintain`; with no reply within 14 days the default applies); `evidence: [{claim, source}]`; `trigger: {tests: [test ids], update?}`; `constitution_refs` cite `R<n>` or `H<n>`. A memo amending the constitution (`action: amend_constitution`) may omit `company`; every other memo MUST have it.

Buy and add memos also give `target_weight`, `order: {type: single}`, `implied_return` and `hurdle`. `target_weight` MUST NOT be below the bottom of the entry bar (10%); 10–20% is a bar, not a target: above the top is allowed, but `weight_note` must give the reason (constitution rule 4). `hurdle` MUST NOT be below the first hurdle, Berkshire's, in the company's `valuation.yml`, and `implied_return` MUST be above it; clearing only the first hurdle and not the VOO reference gives a warning (constitution rule 7, 00 §V6).

### 7.3 Escalation requests escalations/*.yml

See `escalation.schema.json`: `id`, `company`, `created_at`, `test_ids`, `facts: [{claim, source}]` (at least one), `reason` (one of R6's four reasons inside the company: `moat_permanent_impairment`, `business_model_change`, `management_deterioration`, `capital_allocation_failure`), `conclusion`, `drafted_by: company_manager`. "A clearly better opportunity" is a judgment across companies, raised only by HQ, and never in an escalation request.

### 7.4 Series ranking hq/ranking.yml

HQ ranks by an overall judgment under 00 §V13, never mechanically by any single field. Every row MUST give a one-sentence reason for its place, `reason`:

```yaml
as_of: 2026-10-01
rule: "§V13"
rows:
  - {rank: 1, company: ACME, reason: ...}   # a fictitious company, only as a format example
```

`C-RATING-ORDER` checks that every row has a `reason` (the rows may also be written under `ranking:`, or the whole file may be a list).

### 7.5 What must not appear in the public repository (00 §H4)

In the public repository each of the following is an error: `valuation.yml`, `memos/`, `escalations/`, `decision-log/`; keys such as `value_ranges`, `price_reference`, `implied_return` and `price_rating`; and the wording of 00 §H4 in public content (`companies/` (including `updates/`), `industries/`, `forecasts/`, `letters/`, `mistakes.md`). The valuation wording (`买入区间` (buy range), `价值中枢` (value centre), `目标价` (target price), `隐含回报` (implied return), `隐含年化回报` (implied annualized return), `价格评级` (price grade), `price target`, `target price`, `buy range`, `fair value range`) is checked by `C-PUBLIC-NO-VALUATION`; the buy/sell advice wording (`建议买入` (recommend buying), `建议卖出` (recommend selling), `建议增持` (recommend adding), `建议减持` (recommend reducing), `建议加仓` (recommend adding to the position), `建议减仓` (recommend trimming the position), `买入评级` (buy rating), `卖出评级` (sell rating), `强烈推荐` (strongly recommend), `值得买入` (worth buying), `应该买入` (should buy), `可以买入` (can buy), `逢低买入` (buy on dips), `建议建仓` (recommend opening a position), `建议清仓` (recommend closing the position), `strong buy`, `overweight`, `underweight`) by `C-PUBLIC-NO-ADVICE`. Public content also does not state multiples or ratios that take the current share price as an input: `市盈率` (P/E), `P/E`, `市值` (market capitalization), `自由现金流收益率` (free cash flow yield), `FCF yield`, `市净率` (P/B), `P/B` (or wording such as "the price is below N times book"; the company's disclosed ratio of its average repurchase price to book is a fact about the company and does not count) together with a number in the same sentence (years, dates, periods and one-digit numbers do not count) is an error.

**English wording (thesis-ci 0.3.0).** The same checks match the English equivalents of these lists. Valuation: `implied return`, `implied annual` or `annualized return`, `price grade`, `price rating` and `value centre` (the banned term) wherever they appear; `central value` (the neutral name of the valuation midpoint in private files), `fair range`, `value range`, `buy range`, `cheap range`, `intrinsic value` and `margin of safety` when a number follows (a margin of safety also when a percentage precedes it); a price event on a range ("entered the buy range"). Advice: recommending a buy, a sell, adding, reducing, or opening or closing a position ("we recommend buying", "recommend investors sell", "we recommend ACME", "recommend opening a position"), a buy or sell rating ("rated a Buy", "upgraded to Buy", "Rating: Sell", "Buy-rated"), "should buy / sell" with the investor as subject ("investors should buy the stock", "the shares should be sold"), "is a buy", adding to, trimming or accumulating a position ("add to the position", "trim our stake"), buying on dips. As in Chinese, a negative sentence is no exception: "we do not recommend buying" is an error (00 §H4). A company buying back its own shares ("buyback", "the company should buy back stock") or a product name is not advice. Multiples: `price-to-earnings`, `price/earnings`, `price-to-book` and "trades at 25 times earnings" with a number in the same sentence.

**Progress files and price grades (thesis-ci 0.3.0).** The valuation and advice wording checks also read `docs/STATUS.md` and `CLAUDE.md` (and their Chinese versions), which report on the archive's own work and once carried price-grade changes; the documents that define the rules and must name the banned terms (`docs/DESIGN.md`, `docs/decisions/`, `constitution/`) are not read. In every file these checks read, a price grade next to a ticker ("AXP B− → C", "AXP: C") is an error when its sentence is about prices or valuation (price, valuation, §V11) and does not speak of the business, management, quality, culture or capital-allocation ratings, which use the same letters.

## 8. Checks

`spec/checks.yml` is the registry of all checks. Each check has `id`, `title`, `scope` (`public`, `private`, `both`, `workspace`), `level` (`error` or `warning`) and `description`. An implementation MUST provide a function and at least one unit test for each registered check; the name or the docstring of the unit test MUST contain the check id.

Every rule of the constitution (`constitution/rules.yml`) MUST reference at least one registered check id.

### 8.1 Command line

```bash
thesis-ci lint <path> [--counterpart <other repository>] [--today YYYY-MM-DD] [--expect-visibility public|private]
                      [--base-ref <git ref>] [--period FY<year>Q<quarter>] [--only <check id> ...] [--format text|json]
```

`--today` decides whether a deadline has passed (`C-PREREG-TIMING`, `C-PREREG-IMMUTABLE`) and the staleness (`C-STALENESS`); `--base-ref` and `--period` are used only by `C-TEST-FROZEN`; `--counterpart` lets the private repository read the public repository's decision rights and role definitions (`C-PROMPT-ISOLATION`).

### 8.2 Decision rights and trust levels decision-rights.yml

See `decision-rights.schema.json`. `levels` holds the three decision levels, with actions from the schema enum (0.2 adds `valuation_update` and `prompt_change`); money matters and constitution amendments are L3 only. Besides `levels`, `initial`, `window`, `downgrade` and `upgrade`, `trust` MUST have `routing`: routing by trust level (00 §G9), one sentence for each of the keys `"3"`, `"2"`, `"1"` and `"0"` (level 3: auto-merge and publish; level 2: auto-merge, reviewed by HQ before publishing; level 1: kept in the private repository first and published after HQ reviews it item by item; level 0: autonomy paused); the optional `scoring` describes the scoring method (how a fact error downgrades, how a divergence ruling counts, which output of whom counts as one update). The optional `gate` gives the release rules of 17A. `ranking` is `{rule, candidates?, rotation?}`: `rule` cites the ranking clause (e.g. `"§V13"`); there is no mechanical `order` any more.

### 8.3 Isolation of roles and prompts

`role` in `agents/<role>.yml` is one of `company_manager`, `auditor`, `model_reviewer`, `red_team`, `synthesis_reviewer`, `design_reviewer`, `blind_reader`, `judge`, `settler`, `extractor`, `hq_capital_allocator`, `industry_researcher`, `typesetter`; `can_see` and `cannot_see` use the same input names as the front matter of the prompts. The private repository's `prompts/*.md` declare the role and inputs in their front matter: a top-level `role` and `inputs`, or, under `parts`, a `role` for each part (the top-level one when omitted) and `inputs` (and `inputs_pass1`, `inputs_pass2` and so on); a `?` at the end of an input name marks it optional. `C-PROMPT-ISOLATION` (warning; runs in the private repository with `--counterpart`) reports every part whose inputs appear in that role's `cannot_see`; the comparison drops the `?` and the part-number suffix of 00 §F0 (`findings_04A` is compared as `findings`).

### 8.4 Checks added in 0.2

| id | scope | level | check |
| --- | --- | --- | --- |
| `C-PREREG-IMMUTABLE` | public | error | an items file past its deadline has `<file>.ots`; with `ots` installed, `ots verify` passes; a warning when it cannot be verified |
| `C-TRUST-WRITE` | public | warning | `trust_level` equals `trust/levels.yml`; changed `reviewed` dates are listed in the update's `reviewed_sections` |
| `C-TEST-FROZEN` | public | error | with `--base-ref` and `--period`, no threshold of a test in force for the period was changed or deleted |
| `C-PROMPT-ISOLATION` | private | warning | the inputs of every part of a prompt do not intersect the role's `cannot_see` |

### 8.5 English first: zh-CN/ and C-LANGUAGE (thesis-ci 0.3.0)

The archives are English-first. The Chinese version of a key document lives at `zh-CN/<same path>` at the repository root; after any front matter, its first line links back to the English file, and the English file says near the top where the Chinese version is. Every other file is in English only.

- A Chinese version is published like the file it translates. The checks of public content (`C-PUBLIC-NO-VALUATION`, `C-PUBLIC-NO-ADVICE`, `C-PUBLIC-NO-AMOUNTS`, the share-price check of `C-NO-PRICE-FEED`, the neutrality check of `C-DEPENDS`) read `zh-CN/companies/`, `zh-CN/industries/`, `zh-CN/forecasts/`, `zh-CN/letters/` and `zh-CN/mistakes.md` as they read the English files, and `C-SRC-TAG` checks their fact numbers, resolving tags as for the English file (`zh-CN/companies/<TICKER>/story.md` reads `companies/<TICKER>/sources.yml`).
- `C-LANGUAGE` (both, error): no text file outside `zh-CN/` contains CJK characters (Han ideographs, kana, hangul, CJK punctuation or full-width forms). Exempt are `zh-CN/` at the repository root; tests and fixtures (a `tests/`, `test/` or `fixtures/` directory, `test_*.py`, `*_test.py`, `conftest.py`), which may exercise Chinese text; and the value of `title_original` in a `sources.yml` (3.5). The check reports one error per file, at its first line with CJK text, with the number of such lines.

| id | scope | level | check |
| --- | --- | --- | --- |
| `C-LANGUAGE` | both | error | an English file contains no CJK text; `zh-CN/`, tests, fixtures and `title_original` in `sources.yml` are exempt |

## 9. Metric registry

`spec/metrics.yml` lists the metrics that quantitative tests can reference: `id`, `description`, `unit`, `frequency`, `data` (`xbrl` or `filing_text`), `xbrl` (candidate concepts in order of preference), `formula` and `where`. thesis-ci computes the `xbrl` metrics from EDGAR companyfacts (4.5), except `book_value_per_share_yoy`, whose share count no registered concept gives. XBRL concepts follow the accounting standards the issuer reports under, not the form: a foreign private issuer reporting under US GAAP (for example PDD's 20-F) uses `us-gaap` concepts as well; only issuers reporting under IFRS use `ifrs-full`. A metric not in the registry is defined in place with the test's `metric_def` (the same fields as a registry entry, plus `components`; `data` may also be `external` or `mixed`).

## 10. Versions

This specification is v0.2. v1.0 will be set after two earnings seasons have run; until then, incompatible changes are recorded one by one in `CHANGELOG.md`.

thesis-ci 0.3.0 adds English-language support and `C-LANGUAGE` (3.4, 3.5, 5, 7.5, 8.5) and changes no file format apart from the optional `title_original`; archives keep `spec_version: "0.2"`.

thesis-ci 0.4.0 adds the evaluation of quantitative tests (4.5) with two new documents, readings and `ci_results` (`readings.schema.json`, `ci-results.schema.json`); `C-TEST-METRIC` now also reports rules the engine cannot judge. The format of archive files is unchanged; archives keep `spec_version: "0.2"`.
