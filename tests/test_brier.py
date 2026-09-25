"""Brier score and calibration bins."""

from __future__ import annotations

import pytest

from thesis_ci.brier import bin_index, brier_score, calibration, summarize


def rec(p, outcome, domain="other", book="system"):
    return {"probability": p, "outcome": outcome, "domain": domain, "book": book}


def test_always_fifty_percent_scores_a_quarter():
    assert brier_score([(0.5, 1), (0.5, 0), (0.5, 1)]) == pytest.approx(0.25)


def test_perfect_forecasts_score_zero():
    assert brier_score([(1.0, 1), (0.0, 0)]) == 0


def test_formula():
    assert brier_score([(0.8, 1), (0.3, 0)]) == pytest.approx(((0.2**2) + (0.3**2)) / 2)
    assert brier_score([]) is None


def test_only_resolved_forecasts_are_scored():
    summary = summarize([rec(0.9, "happened"), rec(0.9, "pending"), rec(0.9, "undetermined"), rec(0.9, None)])
    assert summary["n_forecasts"] == 4 and summary["n_resolved"] == 1
    assert summary["overall"]["brier"] == pytest.approx(0.01)


def test_bins_cover_ten_deciles():
    assert [bin_index(p) for p in (0.0, 0.05, 0.1, 0.3, 0.7, 0.95, 0.9999, 1.0)] == [0, 0, 1, 3, 7, 9, 9, 9]
    bins = calibration([(0.72, 1), (0.78, 0), (0.15, 0)])
    assert [b["bin"] for b in bins][:2] == ["0-10%", "10-20%"] and bins[-1]["bin"] == "90-100%"
    assert bins[7]["n"] == 2 and bins[7]["mean_p"] == pytest.approx(0.75) and bins[7]["observed"] == pytest.approx(0.5)
    assert bins[1]["n"] == 1 and bins[1]["observed"] == 0
    assert bins[0]["n"] == 0 and bins[0]["mean_p"] is None


def test_grouped_by_domain_and_book():
    summary = summarize([
        rec(0.9, "happened", "enterprise_software", "system"),
        rec(0.6, "not_happened", "enterprise_software", "owner_override"),
        rec(0.5, "happened", "ecommerce", "system"),
    ])
    assert set(summary["by_domain"]) == {"enterprise_software", "ecommerce"}
    assert summary["by_domain"]["enterprise_software"]["n"] == 2
    assert summary["by_domain"]["enterprise_software"]["brier"] == pytest.approx((0.01 + 0.36) / 2)
    assert summary["by_book"]["owner_override"]["brier"] == pytest.approx(0.36)
    assert summary["by_book"]["system"]["brier"] == pytest.approx((0.01 + 0.25) / 2)
