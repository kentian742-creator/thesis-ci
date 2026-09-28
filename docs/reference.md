# How the checks read an archive

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
  archive that runs the `owners-office` profile must have `constitution/rules.yml` and
  `constitution/decision-rights.yml` (SPEC 8.6).
- **Selftest.** `thesis-ci selftest` copies the bundled example archive
  ([`src/thesis_ci/fixtures/workspace`](../src/thesis_ci/fixtures/workspace), fictitious data) to a temporary directory
  and applies at least one violating edit per check. `C-CONSTITUTION-MAP` requires every check the constitution
  references to pass its selftest, and every check that `spec/checks.yml` ties to a constitution rule ("Constitution
  rule N") to be referenced by some rule in `rules.yml`.

The checks themselves are listed in the [README](../README.md#checks) and defined in [`spec/checks.yml`](../spec/checks.yml).
