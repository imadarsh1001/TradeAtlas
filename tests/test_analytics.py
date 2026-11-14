"""Analytics: robust MAD anomalies (edge policies, break isolation) and coverage reporting."""

import pandas as pd
import pytest

from tradeatlas.analytics import (
    MIN_SCORED_CHANGES,
    check_series_coverage,
    coverage_report,
    detect_anomalies,
    detect_price_anomalies,
)
from tests.conftest import make_series


def _smooth_series(months: int, start: str = "2023-01") -> list:
    pattern = [0.03, -0.01, 0.02, -0.02, 0.01]
    values = [100.0]
    for i in range(months - 1):
        values.append(values[-1] * (1 + pattern[i % 5]))
    return values


# --- Anomaly core (task 3.1) ---

def test_injected_outlier_is_flagged_as_spike():
    values = _smooth_series(30)
    values[20] = values[19] * 1.6  # injected outlier ≈ +0.47 log change
    result = detect_anomalies(make_series(values, start="2023-01"))  # single pre-break segment
    assert any(
        f["month"] == "2024-09" and f["direction"] == "spike" and abs(f["score"]) > 3.5
        for f in result["flags"]
    )


def test_clean_series_flags_nothing():
    result = detect_anomalies(make_series(_smooth_series(30, start="2023-01")))
    assert result["flags"] == []


def test_short_segment_declines_with_thin_support():
    values = _smooth_series(6)  # 5 scored changes < MIN_SCORED_CHANGES
    result = detect_anomalies(make_series(values))
    assert result["flags"] == []
    assert result["thin_support_segments"], "expected a thin-support segment"


def test_segment_initial_month_unexamined():
    values = _smooth_series(28)  # 2024-01 → 2026-04, crossing the November 2025 break
    result = detect_anomalies(make_series(values))
    post = next(s for s in result["segments"] if s["segment"] == "November 2025 onward")
    post_months = 6  # 2025-11 .. 2026-04
    assert post["scored_changes"] == post_months - 1  # segment-initial excluded
    assert sum(s["scored_changes"] for s in result["segments"]) == result["examined"]


def test_level_shift_at_break_is_not_pooled():
    values = _smooth_series(28)
    series = make_series(values)
    for i, month in enumerate(series.index):
        if month >= pd.Period("2025-11", freq="M"):
            values[i] = values[i] * 2  # 2× level shift exactly at the break
    result = detect_anomalies(make_series(values))
    assert not any(f["month"] >= "2025-11" for f in result["flags"])
    medians = {s["segment"]: s["median"] for s in result["segments"]}
    assert set(medians) == {"Before November 2025", "November 2025 onward"}
    # Same relative pattern on both sides → same median log change, computed independently.
    assert medians["Before November 2025"] == pytest.approx(medians["November 2025 onward"], abs=1e-9)


def test_nan_pairs_skipped_and_counted():
    values = _smooth_series(30)
    values[15] = None
    result = detect_anomalies(make_series(values))
    assert result["skipped_nan"] >= 2  # the change into and out of the gap


def test_detection_is_deterministic():
    series = make_series(_smooth_series(30))
    assert detect_anomalies(series) == detect_anomalies(series)


# --- Coverage core (task 3.2) ---

def test_gap_identified_and_longest_gap():
    values = _smooth_series(14)
    values[7] = None
    report = coverage_report(make_series(values))
    assert "2024-08" in report["missing_months"]
    assert report["longest_gap"] == 1


def test_no_gap_reports_zero():
    report = coverage_report(make_series(_smooth_series(14)))
    assert report["missing_months"] == []
    assert report["longest_gap"] == 0


def test_trailing_staleness_measured_to_range_end():
    values = _smooth_series(14)
    values[-3:] = [None, None, None]
    report = coverage_report(make_series(values))
    assert report["staleness_months"] == 3
    assert report["latest_month"] == "2024-11"


def test_break_counts_are_the_pinned_literal_counts():
    # Real tripwire: 2019-01..2025-10 = 82 pre-break months, 2025-11..2026-10 = 12 post.
    report = coverage_report(make_series(_smooth_series(28)))
    assert report["pre_break_months"] + report["post_break_months"] == report["observed_months"]
    pinned = coverage_report(make_series_from_pinned_shape())
    assert pinned["pre_break_months"] == 82
    assert pinned["post_break_months"] == 12


def make_series_from_pinned_shape():
    from tradeatlas.forecasting import load_monthly_prices
    return load_monthly_prices()["Gujarat"]


def test_unknown_series_raises_naming_selector():
    with pytest.raises(ValueError, match="No observations"):
        coverage_report(make_series([None, None, None]))


# --- Envelope wrappers + tier rules (tasks 3.1/3.2) ---

def test_anomaly_envelope_for_pinned_scope():
    env = detect_price_anomalies("Gujarat", "Groundnut")
    assert env.tier == "deep"
    assert env.no_data is False
    assert any("3.5" in c for c in env.caveats)
    assert any("signal to investigate" in c for c in env.caveats)
    assert env.coverage.startswith(f"{env.payload['examined']} scored changes examined")


def test_anomaly_unknown_commodity_is_explicit():
    env = detect_price_anomalies("Gujarat", "Soybean")
    assert env.no_data is True
    assert "Soybean" in env.payload["error"]


def test_coverage_unknown_state_is_explicit():
    env = check_series_coverage("Maharashtra", "Groundnut")
    assert env.no_data is True
    assert "Maharashtra" in env.payload["error"]


def test_coverage_envelope_for_pinned_series():
    env = check_series_coverage("Gujarat", "Groundnut")
    assert env.tier == "deep"
    assert env.payload["observed_months"] == 94
    assert env.payload["longest_gap"] == 0
    assert env.payload["staleness_months"] == 0
    assert env.payload["latest_month"] == "2026-10"
    assert env.payload["pre_break_months"] + env.payload["post_break_months"] == 94
