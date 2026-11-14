"""Forecasting harness: loader integrity, baseline semantics, break isolation, MASE, reproducibility."""

import json

import pandas as pd
import pytest

from tradeatlas import forecasting
from tradeatlas.forecasting import (
    METHODS,
    MIN_TRAINING_MONTHS,
    REPORTING_CHANGE,
    _scaling_factors,
    backtest_series,
    build_report,
    evaluate_panel,
    load_monthly_prices,
)
from tests.conftest import make_series


@pytest.fixture(scope="module")
def panel():
    return load_monthly_prices()


@pytest.fixture(scope="module")
def evaluation(panel):
    forecasts, summary = evaluate_panel(panel)
    q = _scaling_factors(forecasts, ["State", "Target period", "Months ahead"])
    return forecasts, summary, q


@pytest.fixture(scope="module")
def report():
    return build_report(clock=lambda: "2026-11-13T00:00:00+00:00")


# --- Loader (task 1.1) ---

def test_loader_reads_full_pinned_series(panel):
    assert str(panel.index[0]) == "2019-01"
    assert str(panel.index[-1]) == "2026-10"  # FULL series: final month included
    assert list(panel.columns) == ["Gujarat", "Rajasthan"]
    assert panel.notna().all().all()


def test_loader_fails_on_tampered_digest(tmp_path, monkeypatch):
    bad_manifest = tmp_path / "manifest.json"
    bad_manifest.write_text(json.dumps({
        "files": [{
            "path": "data/raw/state_monthly.csv.gz",
            "sha256": "0" * 64,
            "source": "test", "retrieved_date": "2026-11-13", "terms": "test",
        }]
    }), encoding="utf-8")
    monkeypatch.setattr(forecasting, "MANIFEST_PATH", bad_manifest)
    with pytest.raises(ValueError, match="state_monthly"):
        load_monthly_prices()


# --- Baseline semantics (task 2.1) ---

def test_seasonal_baseline_reads_target_minus_12_not_origin_minus_12():
    values = [100.0 + i for i in range(30)]
    values[15] = 999.0  # target−12 for origin idx 26, h=1 (target idx 27 − 12 = 15)
    values[14] = 888.0  # origin−12 — must NOT be used
    rows = backtest_series(make_series(values, start="2023-01"))
    row = rows.loc[rows["Origin"] == pd.Period("2025-03", freq="M")].iloc[0]
    assert row["Months ahead"] == 1
    assert row["Same month last year"] == 999.0


def test_last_observed_carries_cutoff_price_forward():
    values = [100.0 + i for i in range(30)]
    rows = backtest_series(make_series(values, start="2023-01"))
    latest = rows.loc[rows["Origin"] == rows["Origin"].max()]
    for _, row in latest.iterrows():
        assert row["Last observed"] == values[rows["Origin"].max().ordinal - pd.Period("2023-01", freq="M").ordinal]


def test_minimum_training_months_enforced():
    short = make_series([100.0 + i for i in range(24)], start="2023-01")
    assert backtest_series(short).empty  # 24 months → no cutoff with 24 training months + a target


# --- Scoring, isolation, MASE (task 2.2) ---

def test_identical_targets_per_method(evaluation):
    forecasts, summary, _ = evaluation
    scored = forecasts[METHODS + ["Actual"]]
    assert scored.notna().all().all()  # rows dropped uniformly → every method scores every row
    # Known pinned count: a real tripwire against data or computation drift.
    gujarat_pre_h1 = summary.xs(("Gujarat", "Before November 2025", 1))
    assert int(gujarat_pre_h1["Targets"]) == 58


def test_break_boundary_months_land_on_the_right_side(evaluation):
    # Independent literal check: October 2025 targets are pre-break, November 2025
    # targets post-break (inclusive boundary) — catches off-by-one at the split.
    forecasts, _, _ = evaluation
    october = forecasts.loc[forecasts["Target"] == pd.Period("2025-10", freq="M")]
    november = forecasts.loc[forecasts["Target"] == pd.Period("2025-11", freq="M")]
    assert (october["Target period"] == "Before November 2025").all()
    assert (november["Target period"] == "November 2025 onward").all()


def test_seasonal_mase_is_exactly_one(evaluation):
    _, summary, q = evaluation
    mase = summary[METHODS].div(q, axis=0)
    assert (mase["Same month last year"] - 1.0).abs().lt(1e-9).all()


def test_mase_equals_mae_over_independently_computed_q(evaluation, report):
    # q recomputed from raw forecast rows for one specific group — without
    # _scaling_factors — then checked against the report's printed q and MASE.
    forecasts, _, _ = evaluation
    rows = forecasts.loc[
        (forecasts["State"] == "Gujarat")
        & (forecasts["Target period"] == "Before November 2025")
        & (forecasts["Months ahead"] == 1)
    ]
    q_manual = (rows["Actual"] - rows["Same month last year"]).abs().mean()
    mae_manual = (rows["Last observed"] - rows["Actual"]).abs().mean()
    assert q_manual > 0

    group = next(
        g for g in report["groups"]
        if g["state"] == "Gujarat"
        and g["target_period"] == "Before November 2025"
        and g["months_ahead"] == 1
    )
    # Report values are rounded to 2dp — compare with half-a-hundredth tolerance.
    assert group["q"] == pytest.approx(q_manual, abs=0.006)
    assert group["mae"]["Last observed"] == pytest.approx(mae_manual, abs=0.006)
    # mae/q on 2dp-rounded report values: abs tolerance covers the rounding.
    assert group["mase"]["Last observed"] == pytest.approx(
        group["mae"]["Last observed"] / group["q"], abs=0.02
    )


def test_post_break_groups_have_computable_q(evaluation):
    forecasts, _, q = evaluation
    post = forecasts.loc[forecasts["Target period"] == "November 2025 onward"]
    assert not post.empty
    post_groups = q.xs("November 2025 onward", level="Target period")
    assert post_groups.notna().all() and (post_groups > 0).all()


def test_flat_seasonal_panel_yields_null_mase():
    # 36 months repeating [100, 105, 103] → every y_t == y_{t−12} → q = 0 → MASE null,
    # while MAE stays positive (the baselines still err within the cycle).
    values = [100.0, 105.0, 103.0] * 12
    prices = make_series(values, start="2022-01")
    panel = pd.DataFrame({"Gujarat": prices, "Rajasthan": prices})
    report = build_report(clock=lambda: "2026-11-13T00:00:00+00:00", prices=panel)
    flat = [g for g in report["groups"] if g["q"] is None]  # q=0 → null in the report
    assert flat, "expected null-q groups on the flat seasonal panel"
    assert all(all(m is None for m in g["mase"].values()) for g in flat)
    # On a period-3 cycle the h=3 last-observed error is exactly 0 — assert on the
    # linear trend instead, which errs against the cycle mean on every horizon.
    assert all(g["mae"]["Linear trend"] > 0 for g in flat)


# --- Report (task 2.3) ---

def test_report_reproducible_with_injected_clock():
    a = build_report(clock=lambda: "2026-11-13T00:00:00+00:00")
    b = build_report(clock=lambda: "2026-11-13T00:00:00+00:00")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)

    c = build_report(clock=lambda: "2027-01-01T00:00:00+00:00")
    a_copy, c_copy = dict(a), dict(c)
    a_copy.pop("generated_at"), c_copy.pop("generated_at")
    assert json.dumps(a_copy, sort_keys=True) == json.dumps(c_copy, sort_keys=True)
    assert c["generated_at"] == "2027-01-01T00:00:00+00:00"


def test_report_carries_provenance(report):
    manifest = json.loads(forecasting.MANIFEST_PATH.read_text(encoding="utf-8"))
    state_entry = next(
        f for f in manifest["files"] if f["path"] == forecasting.SERIES_RELATIVE_PATH
    )
    assert report["source_revision"] == state_entry["revision"]
    assert report["min_training_months"] == MIN_TRAINING_MONTHS
    assert report["scored_range"]["first_origin"].startswith("20")
    assert report["scored_range"]["last_target"].startswith("20")
