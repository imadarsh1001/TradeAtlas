"""Pinned-series forecasting: rolling-cutoff backtest harness and report.

Scores three baselines (last observed, same month last year, linear trend) at
1–3 month horizons on identical held-out targets, grouped by state × pre/post
reporting break × horizon (ADR 0001). Series integrity verifies against
data/manifest.json (source-manifest capability).
"""

import json
import statistics
from hashlib import file_digest
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from tradeatlas.models import utc_now_iso

ROOT_DIR = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT_DIR / "data" / "manifest.json"
SERIES_RELATIVE_PATH = "data/raw/state_monthly.csv.gz"

STATES = ["Gujarat", "Rajasthan"]
PINNED_COMMODITY = "Groundnut"
REPORTING_CHANGE = pd.Period("2025-11", freq="M")
PRE_BREAK = "Before November 2025"
POST_BREAK = "November 2025 onward"
HORIZONS = (1, 2, 3)
MIN_TRAINING_MONTHS = 24
METHODS = ["Last observed", "Same month last year", "Linear trend"]


def load_manifest_entry(relative_path: str) -> Dict[str, Any]:
    """Return the manifest entry for a pinned file, or raise KeyError."""
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for entry in manifest["files"]:
        if entry["path"] == relative_path:
            return entry
    raise KeyError(f"No manifest entry for {relative_path}")


def _verify_pinned_extract() -> Dict[str, Any]:
    """Verify the pinned extract's SHA-256 against the manifest; return its entry."""
    entry = load_manifest_entry(SERIES_RELATIVE_PATH)
    path = ROOT_DIR / SERIES_RELATIVE_PATH
    if not path.is_file():
        raise FileNotFoundError(f"Pinned extract missing: {path}")
    with path.open("rb") as source_file:
        actual = file_digest(source_file, "sha256").hexdigest()
    if actual != entry["sha256"]:
        raise ValueError(
            f"{path} differs from the pinned digest {entry['sha256']} (got {actual})"
        )
    return entry


def load_monthly_prices() -> pd.DataFrame:
    """Full pinned Groundnut price panel (both states), PeriodIndex monthly; non-positive prices → NaN.

    Returns the FULL series including the extract's final month — only the
    backtest harness drops the partial trailing month (see evaluate_panel).
    """
    _verify_pinned_extract()
    market = pd.read_csv(
        ROOT_DIR / SERIES_RELATIVE_PATH,
        usecols=["month", "commodity", "state", "price_rs_qtl"],
    )
    market = market.loc[
        market["commodity"].eq(PINNED_COMMODITY) & market["state"].isin(STATES)
    ].copy()
    market["month"] = pd.PeriodIndex(market["month"], freq="M")
    if set(market["state"]) != set(STATES) or market.duplicated(["state", "month"]).any():
        raise ValueError("Expected both states and at most one Groundnut row per state and month")
    months = pd.period_range(market["month"].min(), market["month"].max(), freq="M")
    panel = market.pivot(index="month", columns="state", values="price_rs_qtl").reindex(months)
    return panel.where(panel.gt(0))


def backtest_series(prices: pd.Series) -> pd.DataFrame:
    """Predict held-out prices from a contiguous monthly series with possible gaps."""
    predictions: List[Dict[str, Any]] = []
    for origin_position in range(MIN_TRAINING_MONTHS - 1, len(prices) - 1):
        origin = prices.index[origin_position]
        history = prices.iloc[: origin_position + 1].dropna()
        if len(history) < MIN_TRAINING_MONTHS:
            continue

        # Fit on elapsed calendar months so missing observations preserve spacing.
        positions = prices.index.get_indexer(history.index).tolist()
        slope, intercept = statistics.linear_regression(positions, history.tolist())
        for horizon in HORIZONS:
            target = origin + horizon
            actual = prices.get(target)
            seasonal = prices.get(target - 12)  # target-12, never origin-12
            if pd.isna(actual) or pd.isna(seasonal):
                continue
            predictions.append(
                {
                    "Origin": origin,
                    "Target": target,
                    "Months ahead": horizon,
                    "Actual": actual,
                    "Last observed": history.iloc[-1],
                    "Same month last year": seasonal,
                    "Linear trend": intercept + slope * (origin_position + horizon),
                }
            )
    return pd.DataFrame(predictions)


def evaluate_panel(prices: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Score all methods on identical held-out rows, grouped by state × target period × horizon."""
    complete_prices = prices.iloc[:-1]  # harness-only: drop the possibly partial final month
    forecasts = pd.concat(
        [backtest_series(complete_prices[state]).assign(State=state) for state in STATES],
        ignore_index=True,
    )
    if forecasts.empty:
        raise ValueError("No common forecast targets have actual prices and seasonal observations")

    forecasts["Target period"] = PRE_BREAK
    forecasts.loc[forecasts["Target"].ge(REPORTING_CHANGE), "Target period"] = POST_BREAK
    errors = forecasts[METHODS].sub(forecasts["Actual"], axis="index").abs()
    groups = ["State", "Target period", "Months ahead"]
    grouped = forecasts[groups].join(errors).groupby(groups)
    summary = grouped[METHODS].mean()
    summary.insert(0, "Targets", grouped.size())
    return forecasts, summary


def _scaling_factors(forecasts: pd.DataFrame, groups: List[str]) -> pd.Series:
    """q per group: mean |y_t − y_{t−12}| over the group's scored targets.

    The t−12 lookback reaches into the training panel — the same lookback the
    same-month-last-year baseline takes — so post-break groups have a
    computable q. q is a scaling constant, not a scored metric.
    """
    seasonal_error = (forecasts["Actual"] - forecasts["Same month last year"]).abs()
    return seasonal_error.groupby([forecasts[g] for g in groups]).mean()


def build_report(
    clock: Optional[Callable[[], str]] = None,
    prices: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """Build the reproducible backtest report; run timestamp isolated in generated_at.

    `prices` overrides the pinned loader (synthetic-panel testing); the pinned
    path verifies the extract and cites its manifest revision.
    """
    clock = clock or utc_now_iso
    if prices is None:
        entry = _verify_pinned_extract()
        prices = load_monthly_prices()
    else:
        entry = {"revision": "synthetic"}
    forecasts, summary = evaluate_panel(prices)
    groups = ["State", "Target period", "Months ahead"]
    q = _scaling_factors(forecasts, groups)
    mase = summary[METHODS].div(q, axis=0)

    group_records: List[Dict[str, Any]] = []
    for key, row in summary.iterrows():
        state, period, horizon = key
        q_value = float(q[key]) if pd.notna(q[key]) and q[key] > 0 else None
        mase_row = {
            method: (round(float(mase.loc[key, method]), 2) if q_value is not None else None)
            for method in METHODS
        }
        group_records.append(
            {
                "state": state,
                "target_period": period,
                "months_ahead": int(horizon),
                "targets": int(row["Targets"]),
                "q": round(q_value, 2) if q_value is not None else None,
                "mae": {method: round(float(row[method]), 2) for method in METHODS},
                "mase": mase_row,
            }
        )

    return {
        "generated_at": clock(),
        "source_revision": entry.get("revision", "unknown"),
        "scored_range": {
            "first_origin": str(forecasts["Origin"].min()),
            "last_target": str(forecasts["Target"].max()),
        },
        "min_training_months": MIN_TRAINING_MONTHS,
        "groups": group_records,
    }


def main() -> None:
    report = build_report()
    print(f"Source revision: {report['source_revision']}")
    print(f"Scored range: {report['scored_range']['first_origin']} → {report['scored_range']['last_target']}")
    print(f"Minimum training months per cutoff: {report['min_training_months']}")
    print("\nMean absolute error / MASE per group (MAE in INR/quintal, lower is better):")
    for group in report["groups"]:
        print(
            f"  {group['state']:<10} {group['target_period']:<24} h={group['months_ahead']} "
            f"targets={group['targets']:>3} q={group['q']}"
        )
        for method in METHODS:
            print(
                f"    {method:<22} MAE={group['mae'][method]:>9.2f}  MASE={group['mase'][method]}"
            )


if __name__ == "__main__":
    main()
