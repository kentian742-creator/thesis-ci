"""thesis-ci: thesis as code.

thesis.yml is the source, thesis tests are the unit tests, and every new 10-Q / 10-K / 8-K is a CI run.
This package lints archive repositories against the format contract in ``spec/`` and judges quantitative thesis
tests against metric readings (``evaluate``, ``readings``, ``metrics``).
"""

__version__ = "0.5.0"
