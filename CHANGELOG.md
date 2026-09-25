# Changelog

The specification (`spec/`) and the tool (`thesis_ci`) are released together. Incompatible specification changes
before v1.0 are listed here one by one.

## v0.3.0 — English first (2026-09-25)

The archives are English-first from now on: the Chinese version of a key document lives at `zh-CN/<same path>`, and
every other file is in English. thesis-ci follows: its documentation, specification data and example archive are in
English, the checks read English content properly, and a new check keeps English files free of Chinese, Japanese and
Korean text. File formats are unchanged apart from the optional `title_original`; archives keep `spec_version: "0.2"`.

### Incompatible changes

- New check `C-LANGUAGE` (both, error; 35 checks): a text file outside the root `zh-CN/` directory must not contain
  Chinese, Japanese or Korean characters (CJK ideographs, kana, hangul, CJK punctuation and full-width forms). Exempt
  are `zh-CN/`; tests and fixtures (`tests/`, `test/` and `fixtures/` directories, `test_*.py`, `*_test.py`,
  `conftest.py`); and the `title_original` of a `sources.yml` entry. One error per file, at its first line with CJK
  text. An archive still written in Chinese fails until its translation lands.
- English sentences are split at `.`, `!`, `?` and `;` followed by whitespace (not after `U.S.`, `Inc.`, `Corp.`,
  `Ltd.`, `e.g.`, `i.e.`, `vs.`, `No. 1`, an initial or an abbreviated month, and not in a decimal or a source tag). A
  line break inside an English paragraph no longer ends a sentence; blank lines, headings, list items, table rows and
  block quotes do. `C-SRC-TAG`, `C-SRC-FACT` and the price-multiple rule of `C-PUBLIC-NO-VALUATION` work sentence by
  sentence, so one tag no longer covers several English sentences on a line, and a tag on the next line of a
  hard-wrapped sentence now counts. A tag written right after the period (`16%.[src:TAG]`) belongs to that sentence.
  Lines with CJK characters are split exactly as before. A finding points at the line of the fact number.
- The Chinese version of public content is public content: the wording checks of `C-PUBLIC-NO-VALUATION`,
  `C-PUBLIC-NO-ADVICE`, `C-PUBLIC-NO-AMOUNTS`, `C-NO-PRICE-FEED` (share prices) and `C-DEPENDS` (neutrality), and
  `C-SRC-TAG`, read `zh-CN/companies/`, `zh-CN/industries/`, `zh-CN/forecasts/`, `zh-CN/letters/` and
  `zh-CN/mistakes.md`; tags there resolve as for the English file (SPEC 8.5).
- `spec/checks.yml` ties checks to constitution rules as "Constitution rule N" (it used the Chinese form);
  `C-CONSTITUTION-MAP` reads the new form.

### English support

- Fact numbers (SPEC 3.4): English units in any letter case (`3 Billion`, `16 PERCENT`), plus `ppt` / `ppts`, `bln`,
  `mln`, currency names (`dollars`, `euros`, `yuan`, `yen`, ...), ISO codes after the number (`5 USD`) and `CHF`,
  `INR`, `KRW`, `TWD`, `SGD` before it. English dates (`September 30, 2026`), `3Q26` / `1H26` and section numbers
  (`Item 15`, `Note 12`) are not quantities for the price-multiple rule.
- 00 §H4 in English (SPEC 7.5). `C-PUBLIC-NO-VALUATION`: `implied return` (annual, annualized, IRR), `price grade`,
  `price rating`, `value centre`; `central value`, `fair` / `value` / `buy` / `cheap range`, `intrinsic value` and `margin of safety`
  with a number (and "a 30% margin of safety", "a 30% discount to intrinsic value"); a price event on a range
  ("entered the buy range"); the multiples `price-to-earnings`, `price/earnings`, `PE ratio` and "trades at 25 times
  earnings". `C-PUBLIC-NO-ADVICE`: recommending a buy, a sell, adding, reducing, or opening or closing a position
  ("analysts recommend buying the stock", "we recommend ACME", "our recommendation is to buy"), ratings ("rated a Buy", "upgraded to Buy", "Rating: Sell", "Buy-rated", "is a buy"),
  "should buy / sell" with the investor as subject, "the shares should be sold", adding to, trimming or accumulating a
  position, buying on dips, "top pick", "worth buying", "time to buy". As with the Chinese terms, a negative sentence is
  no exception ("we do not recommend buying" fails, 00 §H4). Not advice: a company buying back its own
  shares ("buybacks", "the company should buy back stock", "we recommend buying back shares"), a company's own trades
  ("Berkshire trimmed its position"), corporate actions ("the board recommended selling the division") and product
  names ("Best Buy", "Buy with Prime", "Buy Box"). The v0.2 pattern "I / we recommend adding / trimming / reducing" now
  needs a security or a position after the verb, so "we suggest adding a source tag" or "we recommend reducing debt"
  (in a README, say) no longer fails.
- `C-PUBLIC-NO-VALUATION` and `C-PUBLIC-NO-ADVICE` also read the progress files `docs/STATUS.md` and `CLAUDE.md` (and
  their Chinese versions): a progress file once listed two companies' price-grade changes. The rule documents
  (`docs/DESIGN.md`, `docs/decisions/`, `constitution/`) are still not read. A price grade next to a ticker
  ("AXP B− → C", "AXP: C") in a sentence about prices or valuation is an error, unless the sentence speaks of the
  business, management, quality, culture or capital-allocation ratings.
- `C-STORY`: a story in English is at most 350 words, about two minutes read aloud; a story in Chinese, Japanese or
  Korean keeps the 700-character limit. A story is measured in characters when it has at least as many CJK characters
  as English words.
- `C-DEPENDS`: "we hold ACME" or "I own shares of ACME" in an industry module (a ticker in capitals; "we hold that ..."
  is an opinion). `C-PUBLIC-NO-AMOUNTS`: a portfolio weight in a two-minute story.
- `C-SINGLE-ORDER`: a negation up to 12 characters before the tranche wording (`without tranches`) now counts.

### Documentation and data in English

- `README.md`, `spec/SPEC.md`, `CHANGELOG.md` and `LICENSE-SPEC.md` are in English. The Chinese text of the README and
  the specification is kept in `zh-CN/README.md` and `zh-CN/spec/SPEC.md`, which carry the 0.3.0 additions too.
- The titles and descriptions of `spec/checks.yml`, the descriptions and `where` of `spec/metrics.yml`, the titles and
  descriptions of the JSON Schemas and the Lynch templates (claims, questions, `fail_if`, `where`, notes) are in
  English; every id, key, enum and number is unchanged. `sources.schema.json` has an optional `title_original`.
- The example archive (`src/thesis_ci/fixtures/workspace`) is in English, with the Chinese version of the ACME story
  in `public/zh-CN/` and a `title_original` in `public/companies/ACME/sources.yml`. The selftest cases are in English;
  the cases that fed Chinese text are kept in `tests/test_chinese.py`.
- Code comments, docstrings and lint messages are in English; the Chinese detection lists (units, the §H4 phrases and
  patterns, neutrality phrases, sell reasons, tranche wording) are unchanged.

## v0.2.1 — bug fix (2026-09-25)

- `C-PREREG-IMMUTABLE`: a pending proof checked while the OpenTimestamps calendars were unreachable was reported as
  an error ("the file changed after it was timestamped"), which was false. The check now compares the file's sha256
  with the digest the proof commits to locally first (`ots info`, no network): a different digest or an unreadable
  proof is an error; once the digest matches, `ots verify` failing for lack of a Bitcoin node, a pending attestation or
  unreachable calendars is a warning, and only a client message that the proof itself is bad is an error.

## v0.2.0 — specification 0.2 (2026-09-24)

Specification 0.2 aligns the format with the owner's rulebook (series rules 00 v3: §H4, §V1/§V7/§V10/§V11/§V13/§V20,
§G3/§G7/§G8/§G9, §F2/§F5/§F6). Archives written for 0.1 must be migrated; `C-SCHEMA` reports every file that is
not. The hardening changes below (previously unreleased) ship in this version too.

### Incompatible changes

- `thesis.yml`: `schema_version: "0.2"`. `reviewed` keys are the twelve dossier parts `business`, `economics`,
  `moat`, `capital_allocation`, `management`, `culture`, `runway`, `valuation`, `bear_case`, `monitoring`, `thesis`,
  `breakers` (required) plus `munger`, `unknowns` (optional); `ratings`, `matrix`, `peers`, `ranking` and
  `failure_modes` are gone. Staleness `section` takes the same fourteen keys. Lynch `_common.yml`: `S-failure`
  (`failure_modes`) is now `S-bear_case` (`bear_case`, 2 quarters).
- Every thesis test requires `effective_from` (`FY<year>Q<quarter>`); optional `supersedes` (a test id) and
  `retired_at`. Retired tests are records: they no longer count toward the five tests, the three types or the
  covers of `C-TESTS-MIN`, `C-TESTS-COVERAGE`, `C-TESTS-CAPALLOC`, and `C-STALENESS` skips them.
- Qualitative tests require `where` (string or list) and `lookback` (integer ≥ 1); optional `judge_notes`. The Lynch
  templates' qualitative tests carry default `where` and `lookback`.
- `prereg.schema.json` describes the immutable items file only: required `company`, `event` (`period`
  `FY<year>Q<quarter>`, `expected_release`, `form`, `placeholder`), `deadline` (ISO 8601 date-time with a UTC
  offset), `author`, `items`; optional `horizon`. Items (1–8) require `id` (`<TICKER>-<period>-<n>`), `statement`,
  `probability` (0.05–0.95), `criterion`, `data_source`, `horizon`, `resolves_by`, `domain`, `added_by`; optional
  `pillar`, `falsifies_thesis`, `reference`. `merged_at`, `ots_proof`, `acceptance_datetime`, `accession` and
  results moved to the new `prereg/<period>.settlement.yml` (`prereg-settlement.schema.json`). The owner's file
  `prereg/<period>-owner.yml` (`author: owner`) may add `overrides`; the system's file may not.
- `ledger.schema.json`: `probability` (0.05–0.95) is required for `side: system|owner`, whose status is one of
  `pending`, `kept`, `not_kept`, `undetermined`; new `last_mentioned`, `acknowledged_source`.
- `valuation.schema.json`: required `doc_status` (`proposed` / `effective`); new `margin_of_safety`,
  `comparable_anchor`, `discount_rate.risk_free_date`; `discount_rate.note` (the premium rationale) is required once
  `total` is a number; `price_rating` is `A`–`E` without a sign; `error_band` is documented as an absolute band in
  the unit of `center`; the quality description no longer says "higher quality, lower premium".
- `memo.schema.json`: required `options` (at least two, one with `key: maintain`) and `drafted_by:
  hq_capital_allocator`; new `evidence`, `trigger`; `company` may be omitted for `amend_constitution`;
  `constitution_refs` accept `R<n>` and `H<n>`. New `escalation.schema.json` for the private `escalations/*.yml`.
- `decision-rights.schema.json`: `ranking` is `{rule, candidates?, rotation?}` (no `order`); `trust.routing`
  (`"0"`–`"3"`) is required, `trust.scoring` and a top-level `gate` are optional; actions add `valuation_update` and
  `prompt_change`.
- `agent.schema.json`: roles are `company_manager`, `auditor`, `model_reviewer`, `red_team`, `synthesis_reviewer`,
  `design_reviewer`, `blind_reader`, `judge`, `settler`, `extractor`, `hq_capital_allocator`,
  `industry_researcher`, `typesetter`.
- `C-TEST-METRIC`: a rule's `metric` that does not resolve is an error (was a warning).
- `C-RATING-ORDER` runs on both archives (the ranking file is private).

### Additions

- `metric_def.components` (component → `{description, unit, where?, xbrl?}`), `rule.metric` as `<metric>.<component>`,
  `rule.evaluate_on` / `rule.evaluate_from`, test `data: external | mixed`, `origin` values `archive:breaker`,
  `archive:watch`, `proposal:04B|04B-lite|07|08|11`. `params.metric_defs` still resolves during the migration.
- `sources.yml` kinds `news`, `review`; SPEC 3.3 follows 00 §E1 (owner reports `<TICKER>-RPT<n>-<YYYY-MM-DD>`).
- `industry.yml` optional `trust_level`; `trust/levels.yml` (SPEC 4.2) records the pipeline's trust levels.
- `metrics.yml`: card-issuer metrics (`net_card_fees_yoy`, `card_member_services_to_revenue`,
  `discount_revenue_to_billed_business`, `reserve_build_release`); the header no longer says 20-F filers use
  `ifrs-full` (the taxonomy follows the accounting standard: PDD reports under US GAAP).
- `lint --base-ref REF --period FY####Q#` (and the Action inputs `base-ref`, `period`).
- New checks: `C-PREREG-IMMUTABLE` (error: timestamp proof after the deadline, `ots verify` when installed),
  `C-TRUST-WRITE` (warning: trust levels and `reviewed_sections`), `C-TEST-FROZEN` (error: thresholds of tests in
  force are not edited or removed after the base ref), `C-PROMPT-ISOLATION` (warning: prompt inputs against the
  role's `cannot_see`). 34 checks.

### Changed checks

- `C-DISCOUNT-RATE`: the cross-company rule "higher quality must not carry a higher premium" is removed (it
  contradicted §V10: the premium comes from the company's own record). Checks `total = risk_free + premium`,
  a non-empty `discount_rate.note`, a non-empty `method_note`, and warns when `risk_free_date` is missing.
- `C-RATING-ORDER`: no longer reads `ranking.order`; checks the business and management ratings and that every
  row of the private `hq/ranking.yml` states a `reason`.
- `C-PUBLIC-NO-ADVICE` / `C-PUBLIC-NO-VALUATION`: the literal phrase lists are exactly the terms of 00 §H4
  (`建议加仓`, `建议减仓` added; `buy rating`, `sell rating`, `we recommend …` are still caught as other wordings);
  `mistakes.md` and `companies/*/updates/` are scanned; a price-derived multiple (`市盈率`, `P/E`, `市值`,
  `自由现金流收益率`, `FCF yield`) with a number in the same sentence is an error; `escalations/` is private-only.
- `C-NO-PRICE-FEED`: the private `pipeline/price_history.py` is allowed next to `pipeline/price_alert.py`.
- `C-PREREG-TIMING`: reads `merged_at` / `acceptance_datetime` from the settlement file; the owner's file must use
  the system file's deadline.
- `C-SCHEMA`: prereg file names, periods, authors and item ids must agree; `repo.yml` at `spec_version: "0.1"`
  warns during the migration.
- `C-SRC-FACT`: `acknowledged_source` must resolve; the system's and the owner's ledger predictions need no tags
  (00 §E1).

### Hardening after an adversarial mutation run (2026-09-24)

A mutation run injected one or more realistic violations per check into an independent clean archive pair,
plus false-positive probes. Every violation below used to pass the lint, or clean content used to fail it. Each
fix has a regression test (`tests/test_hardening.py`) and, for violations, a selftest case. The specification
files are unchanged; the lint is stricter where noted, so content that passed before can now fail.

#### File walking and parsing (all checks)

- Hidden directories other than `.github` were skipped entirely, so a secret in `.claude/settings.json`, a model
  call in `.claude/hooks/`, or `valuation.yml` under `.data/` went unseen. Only `.git`, virtual environments,
  caches, `build/` and `dist/` are skipped now. Inside a git work tree, files git ignores are not scanned (they are
  not published); if the archive itself is ignored by an enclosing repository, everything is scanned.
- Key scans read only the first document of a YAML file: `value_ranges` or `cost_basis` after a `---` separator
  passed. They now read every document, and JSON data files too (tool configuration such as `package.json` or
  `.vscode/` excepted). Key names are normalized (`valueRanges`, `Value-Ranges`).
- A UTF-8 byte-order mark or Windows line endings made `story.md` look like it had no front matter (false error
  in `C-SCHEMA` / `C-STORY`), and CRLF fenced code blocks were not masked.
- Crashes found by type fuzzing (a crashing check reports only an internal error and hides its findings):
  `sources: -1.5` or `sources: true` in a sources.yml crashed `C-SRC-TAG` and `C-SRC-FACT`; a thesis test with
  `type: []` crashed `C-TESTS-MIN`. 5,004 single-value type mutations now run without a crash.

#### Per check

- `lint --expect-visibility public|private` (and the Action's `expect-visibility` input) lints as that visibility
  whatever `repo.yml` says and reports a mismatch under `C-SCHEMA`: without it, changing a public archive's
  `repo.yml` to `private` skipped every public check in its own CI.
- `C-SCHEMA`: repeated YAML keys (PyYAML keeps the last value silently) are errors; `company` must match the
  `companies/<TICKER>/` directory (thesis, ledger, valuation, prereg) and `id` the `industries/<id>/` directory;
  a tag may be defined once per `sources.yml`; with `--counterpart`, both archives may not declare the same
  visibility (a public archive relabelled `private` skipped every public check).
- `C-SRC-TAG`: other spellings of the SPEC 3.4 units are fact numbers (`16 percent`, `30 basis points`, `40 cents`,
  `1.2 trillion`, `25x`, `€500`, `RMB 5`, `5 港元`, `5 千美元`, `3 百亿`, `＄66`); two spaces between number and unit
  (common in PDF text: `1,570  亿美元`) or a zero-width character no longer hide a fact. `mistakes.md` is scanned
  (its own format says fact numbers carry tags). A date before a name (`2019-06 百亿补贴`) is not a fact.
- `C-SRC-FACT`: `source` fields resolve in every YAML file under `companies/` and `industries/` (update records and
  every document of a stream), not only in the files that have a schema.
- `C-PUBLIC-NO-VALUATION`: `valuation.json`, key aliases (`price_target`, `target_price`, `intrinsic_value`, ...),
  the value ranges by their DESIGN names with a number (`合理区间 280–330`) or a price event on them (`进入便宜区间`),
  `估值中枢`, intrinsic value or margin of safety with a number.
- `C-PUBLIC-NO-ADVICE`: advice in other words (`建议减仓`, the conclusion wording DESIGN.md names; `建议加仓`,
  `推荐买入`, `应该卖出`, `评级上调至买入`, `I recommend buying`, `strong sell`), in traditional characters, with spaces,
  zero-width or full-width characters, or hyphenated (`strong-buy`). `overweight` / `underweight` count only as a
  rating (a beverage module can write about overweight adults); `strong buyer power` no longer matches `strong buy`.
- `C-PUBLIC-NO-AMOUNTS`: IBKR paper accounts (`DU1234567`); position sizes in prose (`我们的仓位 15%`,
  `our stake in X is 12%`; in `story.md` any `仓位 15%`, per SPEC 5). Python escapes such as `"\U00020000"` are
  no longer taken for account numbers.
- `C-NO-PRICE-FEED`: quote clients by import (`polygon`, `akshare`, `tushare`, `pandas_datareader`, ...) and by name
  or URL (Financial Modeling Prep, EOD Historical Data, Tiingo, ...); price-key aliases (`share_price`, ...); a
  share price displayed in public prose (`现价 $350`, `shares closed at $350`; hard rule 2).
- `C-NO-TRADING`: Futu / moomoo, Tiger, Longbridge, Questrade, Wealthsimple, Tradier, tastytrade, Webull, Kite,
  ccxt, `create_order` / `createOrder` / `submitOrder`; short names are matched as imports (`from __future__` is
  not `futu`).
- `C-LLM-ENTRY`: more SDKs (`claude_agent_sdk`, `vertexai`, `groq`, `ollama`, `dashscope`, ...), model APIs over
  HTTP (`api.anthropic.com`, ...), JavaScript SDK imports, notebook code cells, and model actions in workflows or
  scripts (`anthropics/claude-code-action`). Dependency lists may still name the SDK that `pipeline/llm.py` uses.
- `C-NO-SECRETS`: GitHub `ghs_` / `ghu_` / `ghr_` tokens, private keys (PEM, PGP), Google `AIza` keys, Hugging Face
  and Slack tokens, `sk-` keys in lowercase hex (DeepSeek / DashScope style), `apiKey` / `*_SECRET` / `*_PASSWORD`
  literals. No longer reported: attribute references (`api_key = self.settings.api_key`), `"${ANTHROPIC_API_KEY}"`
  and environment-variable names.
- `C-DEPENDS`: holdings and dependants in other words (`我们持有`, `仓位`, `our portfolio`, `our stake in`,
  `依赖于本行业的公司`, `companies that rely on this industry`); `our holding company` (20-F wording) is allowed.
- `C-STORY`: the story's `status` and `category` must match `thesis.yml`.
- `C-SELL-REASONS`: the allowed reasons never go beyond the memo schema's enum, so an edited `sell_reasons` list in
  the counterpart cannot let a `price_decline` trim or sell memo through.
- `C-HURDLE`: Berkshire's hurdle is the first bar and VOO's a second reference (00 §V6); the check no longer takes
  the higher of the two. A buy/add memo's `hurdle` may not be below the first bar in the company's `valuation.yml`
  and `implied_return` must beat it (error); clearing the first bar but not VOO is a warning. With no Berkshire
  number, VOO is the bar. A holding below either line is a warning.
- `C-PUBLIC-NO-VALUATION`: the price-multiple terms also cover price-to-book (`市净率`, `P/B`, `price-to-book`) and
  the market price against book value in words (`价格低于 1.2 倍账面`). A company's disclosed average repurchase price
  against book is a company fact (00 §H2 item 3) and is not flagged.
- `C-CONCENTRATION`: 10–20% is an entry bar, not a target (constitution rule 4). A buy/add memo's `target_weight`
  below 10% is an error; above 20% is allowed, with a warning when the new optional `weight_note` is empty. More
  holdings than `max_holdings`, or `max_holdings` above 5, is a warning ("about 4–5 companies").
- `C-SINGLE-ORDER`: a buy/add memo whose `order.note` or `summary` plans tranches (`分两批`, `scale in`, ...) is an
  error even with `order.type: single`; several live buy/add memos for one company within 31 days warn.
- `C-DECISION-RIGHTS`: `levels.L3.who` must name the owner (the chairman).
- `C-CONSTITUTION-MAP`: every check that `spec/checks.yml` ties to a constitution rule (by rule number) must be
  referenced by some rule; dropping a rule from `rules.yml` no longer passes.
- `C-AGENT-ISOLATION`: `can_see` may not list what `cannot_see` hides (`conclusions`, `draft_conclusions`, `thesis`;
  the last token decides, so `thesis_question_list` stays allowed).
- `C-PREREG-TIMING`: the deadline must fall before the release day (a deadline set after the release excused a
  merge after the results); a UTC deadline is read on EDGAR's US Eastern clock. A deadline that has passed with no
  `merged_at` recorded warns.

## v0.1.0 — 2026-09-24

First release.

### Specification v0.1

- `SPEC.md`: repository roles, directory layout, file-to-schema mapping, source tags and the fact-number rule,
  `thesis.yml` and thesis tests, two-minute stories, industry modules, private value ranges.
- 14 JSON Schemas (draft 2020-12): `agent`, `constitution-rules`, `decision-log`, `decision-rights`, `forecast`,
  `industry`, `ledger`, `memo`, `prereg`, `repo`, `sources`, `story`, `thesis`, `valuation`.
- `checks.yml`: 30 registered checks. `metrics.yml`: 29 metrics. Six Lynch monitoring templates.

### Tool

- `thesis-ci lint PATH [--format text|json] [--counterpart PATH] [--today DATE] [--only CHECK_ID ...]`:
  reads `repo.yml`, runs every applicable check, exits 1 on any error-level finding.
- `thesis-ci checks`, `thesis-ci selftest`, `thesis-ci staleness`, `thesis-ci brier`.
- All 30 checks implemented and registered with `@check`; the selftest proves each one flags a violating fixture
  and passes the bundled clean example archive.
- The spec ships inside the wheel as `thesis_ci/spec`; editable installs read `spec/` directly.
- Composite GitHub Action (`action.yml`) and CI workflow (pytest + selftest).

### Notes

- `C-TEST-METRIC` also warns (does not fail) when a compound rule's sub-rule `metric` is neither registered nor
  defined in the test (`metric`, `metric_def`, `params.metric_defs`, or `<id>.<component>` of one of those).
- Not yet included: EDGAR listener, settlement, OpenTimestamps verification (planned phases).
