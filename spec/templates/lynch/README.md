# Monitoring templates for Lynch's six categories

A company takes the default tests of its Lynch category, supplemented from the thesis breakers and watch signals of the
company report. The thresholds in a template are defaults: the company manager may rewrite them for the company, but
must state the reason in the test's `note`; a rewritten threshold, too, must be written down before the results are out.

The `origin` of a template test is `template:<category>`. When a template is applied, add `id` and `effective_from` (the
period from which the test is judged); qualitative tests also get `judge: independent_model` and `evidence: required`, and
the `where` (which documents are read for the judgment) and `lookback` (how many periods are read, the current one
included) given by the template are defaults that can be rewritten for the company.

When the category changes, the old template's tests are not deleted: they get `retired_at` (the period from which they
are no longer judged), and the new template's tests get `effective_from`; a new test that replaces an old one item by
item gives `supersedes` (the id of the test it replaces).

All templates share three staleness tests: `moat` and `management` at 4 quarters each, and `bear_case` (the bear case)
at 2 quarters.
