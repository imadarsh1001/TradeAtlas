"""Deterministic analytics over the pinned series: anomaly detection and coverage.

Both tools consume the FULL pinned series (no drop-last — that is the
harness's rule) and return EvidenceEnvelopes with method/coverage caveats.
"""

import math
import statistics
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from tradeatlas.forecasting import (
    PINNED_COMMODITY,
    POST_BREAK,
    PRE_BREAK,
    REPORTING_CHANGE,
    STATES,
    load_monthly_prices,
)
from tradeatlas.ingest import tier_for
from tradeatlas.models import EvidenceEnvelope, utc_now_iso

Z_THRESHOLD = 3.5
MAD_SCALE = 0.6745
MIN_SCORED_CHANGES = 6

FLAG_IS_SIGNAL_CAVEAT = (
    f"Robust MAD method (modified z-score, threshold {Z_THRESHOLD}); a statistical flag is a "
    "signal to investigate, not a proven market event."
)
PINNED_SNAPSHOT_CAVEAT = (
    "Pinned snapshot: statistics use within-segment changes only; staleness is measured "
    "against the extract's own last month, not the wall clock."
)


def _pinned_state_series(state: str, commodity: str) -> Tuple[Optional[pd.Series], Optional[str]]:
    """Return the pinned series for a state, or (None, explicit error)."""
    if commodity != PINNED_COMMODITY:
        return None, f"Commodity '{commodity}' is not in the pinned extract (Groundnut only)."
    if state not in STATES:
        return None, f"State '{state}' is not in the pinned extract ({', '.join(STATES)})."
    return load_monthly_prices()[state], None


def _log_changes(series: pd.Series) -> pd.Series:
    """Month-over-month log change; NaN for missing/non-positive pairs."""
    floats = series.astype(float)
    ratios = floats / floats.shift(1)
    return ratios.map(lambda r: math.log(r) if pd.notna(r) and r > 0 else pd.NA)


def detect_anomalies(series: pd.Series, boundary: pd.Period = REPORTING_CHANGE) -> Dict[str, Any]:
    """Robust MAD flagging within each reporting-break segment (design Decision 5)."""
    changes = _log_changes(series)
    segments = [
        (PRE_BREAK, [m for m in series.index if m < boundary]),
        (POST_BREAK, [m for m in series.index if m >= boundary]),
    ]
    flags: List[Dict[str, Any]] = []
    examined_total = 0
    skipped_nan = 0
    thin_support: List[str] = []
    segment_stats: List[Dict[str, Any]] = []

    for name, months in segments:
        scored: List[Tuple[pd.Period, float]] = []
        for position, month in enumerate(months):
            if position == 0:
                continue  # segment-initial observation: no within-segment prior month
            change = changes.get(month)
            if change is None or pd.isna(change):
                skipped_nan += 1
                continue
            scored.append((month, float(change)))
        if not scored:
            continue

        median = statistics.median(c for _, c in scored)
        mad = statistics.median(abs(c - median) for _, c in scored)
        segment_stats.append(
            {"segment": name, "scored_changes": len(scored), "median": median, "mad": mad}
        )
        examined_total += len(scored)

        if len(scored) < MIN_SCORED_CHANGES:
            thin_support.append(name)
            continue
        if mad == 0:
            continue  # degenerate: typical variation is exactly zero, flag nothing

        for month, change in scored:
            z = MAD_SCALE * (change - median) / mad
            if abs(z) > Z_THRESHOLD:
                flags.append(
                    {
                        "month": str(month),
                        "value": float(series[month]),
                        "score": round(z, 2),
                        "direction": "spike" if z > 0 else "drop",
                    }
                )

    return {
        "flags": flags,
        "examined": examined_total,
        "skipped_nan": skipped_nan,
        "segments": segment_stats,
        "thin_support_segments": thin_support,
    }


def detect_price_anomalies(state: str, commodity: str) -> EvidenceEnvelope:
    """Evidence-card anomaly detection for a pinned state/commodity (MCP pass-through target)."""
    retrieved_at = utc_now_iso()
    series, error = _pinned_state_series(state, commodity)
    if error is not None:
        return EvidenceEnvelope(
            payload={"error": error},
            coverage=f"0 scored changes examined for ({state}, {commodity})",
            tier="thin",
            retrieved_at=retrieved_at,
            caveats=[error],
            no_data=True,
        )

    result = detect_anomalies(series)
    caveats = [FLAG_IS_SIGNAL_CAVEAT, PINNED_SNAPSHOT_CAVEAT]
    caveats.extend(
        f"Thin support in segment '{name}': fewer than {MIN_SCORED_CHANGES} scored changes; no flags computed."
        for name in result["thin_support_segments"]
    )
    if result["skipped_nan"]:
        caveats.append(f"{result['skipped_nan']} month-over-month pairs skipped for missing values.")

    return EvidenceEnvelope(
        payload=result,
        coverage=f"{result['examined']} scored changes examined, {len(result['flags'])} flagged for ({state}, {commodity})",
        tier=tier_for(state, commodity),
        retrieved_at=retrieved_at,
        observation_dates=[str(series.index.max())],
        caveats=caveats,
        no_data=False,
    )


def coverage_report(series: pd.Series, boundary: pd.Period = REPORTING_CHANGE) -> Dict[str, Any]:
    """Per-state coverage of a monthly series (gap convention: 0 when no gap exists)."""
    observed = [m for m in series.index if pd.notna(series.get(m))]
    if not observed:
        raise ValueError("No observations in the requested series")

    missing: List[str] = []
    longest = current = 0
    for month in series.index:
        if pd.isna(series.get(month)):
            missing.append(str(month))
            current += 1
            longest = max(longest, current)
        else:
            current = 0

    pre_break = sum(1 for m in observed if m < boundary)
    latest = observed[-1]
    return {
        "observed_months": len(observed),
        "missing_months": missing,
        "longest_gap": longest,
        "latest_month": str(latest),
        "pre_break_months": pre_break,
        "post_break_months": len(observed) - pre_break,
        "staleness_months": (series.index[-1] - latest).n,
    }


def check_series_coverage(state: str, commodity: str) -> EvidenceEnvelope:
    """Evidence-card coverage report for a pinned state/commodity (MCP pass-through target)."""
    retrieved_at = utc_now_iso()
    series, error = _pinned_state_series(state, commodity)
    if error is not None:
        return EvidenceEnvelope(
            payload={"error": error},
            coverage=f"0 observed months for ({state}, {commodity})",
            tier="thin",
            retrieved_at=retrieved_at,
            caveats=[error],
            no_data=True,
        )

    report = coverage_report(series)
    return EvidenceEnvelope(
        payload=report,
        coverage=f"{report['observed_months']} observed months for ({state}, {commodity})",
        tier=tier_for(state, commodity),
        retrieved_at=retrieved_at,
        observation_dates=[report["latest_month"]],
        caveats=[PINNED_SNAPSHOT_CAVEAT],
        no_data=False,
    )
