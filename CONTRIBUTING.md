# Contributing to thesis-ci

Thank you for helping. thesis-ci is small on purpose: a specification, a linter and a few scoring tools that let an
investment thesis be checked like code. Contributions that make it clearer, more correct or easier to adopt are the
most welcome.

## Reporting a problem

Open an issue with:

- what you ran (`thesis-ci --version` and the command line),
- what you expected and what happened (the check id and message, or the traceback),
- a minimal archive that reproduces it. `thesis-ci init repro` writes a lint-clean starting point; change only what the
  problem needs. Use fictitious data: never attach real valuations, positions or anything private.

A false positive or a false negative of a check is a bug. So is wording in the README or the SPEC that a newcomer
cannot follow.

## Proposing a change to the specification

The specification (`spec/`) is a contract other archives depend on. Open an issue first and describe the problem, the
proposed rule and how existing archives are affected. Incompatible changes are listed one by one in `CHANGELOG.md`
and wait for a minor version.

## Development

```bash
git clone https://github.com/kentian742-creator/thesis-ci
cd thesis-ci
python -m pip install -e ".[test]"
python -m pytest -q
thesis-ci selftest
```

Every change keeps the whole test suite and the selftest passing.

## Adding a check

1. Register it in `spec/checks.yml`: id, title, scope, level, profile (`core`, `pipeline` or `owners-office`) and a
   description that says exactly what it enforces and how far a machine can check it.
2. Implement it in `src/thesis_ci/checks/` with `@check("C-...")`.
3. Add at least one violating case to `src/thesis_ci/selftest.py`: the check must flag it, and must pass the clean
   example archive.
4. Write a unit test whose docstring names the check id.
5. Add it to the check tables in `README.md`, `zh-CN/README.md`, `spec/SPEC.md` §8.6 and `zh-CN/spec/SPEC.md` (a test
   keeps the tables and the registry in step).

## Writing

The repository is English first; a Chinese version of a key document lives at `zh-CN/<same path>`. Write plainly and
precisely: say what a thing is and why it matters before how it works, and define a term the first time it appears.
When you change a document that has a Chinese version, update both or say in the pull request that the translation is
still to do.

## Releasing (maintainers)

1. Update the version in `pyproject.toml` and `src/thesis_ci/__init__.py`, and date the section in `CHANGELOG.md`.
2. Update the version in the README's GitHub Action example.
3. Tag `vX.Y.Z` on `main`, push the tag and publish a GitHub release with the changelog section as its notes.
4. The `publish` workflow tests the tagged commit and publishes it to PyPI through trusted publishing; no token is
   stored anywhere.

## License

By contributing you agree that code is licensed under MIT and the specification and documentation under CC BY 4.0, as
the repository's `LICENSE` and `LICENSE-SPEC.md` state.
