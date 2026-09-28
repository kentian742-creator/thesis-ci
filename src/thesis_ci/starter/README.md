# Thesis archive

This archive was started with `thesis-ci init`. It keeps investment theses as code: for each company, the thesis,
the tests that could prove it wrong, a two-minute story and the sources behind every number. ACME Corp. and all its
data are fictitious; replace them with a company you follow. Not investment advice.

## Layout

| Path | What it holds |
| --- | --- |
| `repo.yml` | the archive's visibility (public or private), the specification version and the check profiles to run |
| `companies/ACME/thesis.yml` | the thesis: a summary, the pillars it rests on, grades for the business and management, and the thesis tests |
| `companies/ACME/story.md` | the two-minute story: why the company matters, in at most 350 words, with a source tag on every number |
| `companies/ACME/sources.yml` | the sources: every tag cited in `companies/ACME/` must be listed here |
{{CONSTITUTION_ROWS}}
To add a company, copy `companies/ACME/` to `companies/<TICKER>/` and rewrite the three files.

## The thesis tests

`thesis.yml` holds five tests, the minimum, with at least one of each type:

- **Quantitative** (`ACME-Q1` to `ACME-Q3`): a number computed from the company's SEC XBRL data, with the threshold,
  the direction and the number of consecutive periods written down before the data arrive.
- **Qualitative** (`ACME-L1`): a yes-or-no question answered from named documents by a separate model that must quote
  its evidence.
- **Staleness** (`ACME-S1`): fails when a part of the thesis has not been reviewed for a set number of quarters.

Together the tests in force must cover moat, pricing power, returns on capital, free cash flow, capital allocation
and management.

## Checking the archive

```bash
thesis-ci lint .         # the checks of the profiles named in repo.yml
thesis-ci staleness .    # which parts of each thesis are due for a review
thesis-ci checks         # every check with its profile, scope and level
```

`profiles` in `repo.yml` chooses the checks. `core` suits any thesis archive. Add `pipeline` when an LLM research
pipeline writes the archive, and `owners-office` only to adopt the investing rules of Owner's Office, the archive
thesis-ci was built for. Without the `profiles` line, every profile runs.
{{VISIBILITY_NOTE}}
The file formats are described in the thesis-ci specification (`spec/SPEC.md` in the thesis-ci repository).
