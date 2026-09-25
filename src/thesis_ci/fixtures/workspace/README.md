# Selftest workspace

A clean pair of archive repositories (`public/`, `private/`) that passes every thesis-ci check.
`thesis-ci selftest` copies it to a temporary directory and applies one small mutation per check
(see `thesis_ci/selftest.py`) to prove that each check flags a violation. All companies, numbers
and sources here are fictitious.

Like a real archive, the example is in English. Two places show where Chinese text belongs: the
Chinese version of the ACME story in `public/zh-CN/companies/ACME/story.md`, and the original title
of a Chinese-language report in the `title_original` field of `public/companies/ACME/sources.yml`.
C-LANGUAGE exempts both.
