# %% [markdown]
# # Groundnut price backtest
# Run `uv run python groundnut_price_backtest.py` to print the benchmark scores.
# At each historical cutoff, predict the price one, two, and three months ahead.
# The pinned extract provides one historical snapshot without release vintages.
# Treat each completed month as available at its cutoff for this exercise.
# Method reference: https://otexts.com/fpp3/tscv.html
#
# NOTE: historical M0 evidence, kept as-is. The authoritative productized
# harness is tradeatlas/forecasting.py (verified against this script's output).

# %%
from statistics import linear_regression

import pandas as pd

from groundnut_data import REPORTING_CHANGE, REVISION, STATES, load_state_months

HORIZONS = (1, 2, 3)
MIN_TRAINING_MONTHS = 24
METHODS = ["Last observed", "Same month last year", "Linear trend"]


def backtest(prices):
    """Predict held-out prices from a contiguous monthly series with possible gaps."""
    predictions = []
    for origin_position in range(MIN_TRAINING_MONTHS - 1, len(prices) - 1):
        origin = prices.index[origin_position]
        history = prices.iloc[: origin_position + 1].dropna()
        if len(history) < MIN_TRAINING_MONTHS:
            continue

        # Fit on elapsed calendar months so missing observations preserve spacing.
        positions = prices.index.get_indexer(history.index).tolist()
        slope, intercept = linear_regression(positions, history.tolist())
        for horizon in HORIZONS:
            target = origin + horizon
            actual = prices.get(target)
            seasonal = prices.get(target - 12)
            if pd.isna(actual) or pd.isna(seasonal):
                continue
            predictions.append({
                "Origin": origin,
                "Target": target,
                "Months ahead": horizon,
                "Actual": actual,
                "Last observed": history.iloc[-1],
                "Same month last year": seasonal,
                "Linear trend": intercept + slope * (origin_position + horizon),
            })
    return pd.DataFrame(predictions)


# %% [markdown]
# ## Compare errors on the same targets
# Each method gets the same scored rows for a state and horizon. The last
# observed baseline carries the latest known price forward. The seasonal
# baseline uses the target month one year earlier. The trend is a straight
# line fitted again at every cutoff using all available training prices.

# %%
def evaluate_prices(complete_prices):
    """Return per-target predictions and MAE grouped by state, period, and horizon."""
    forecasts = pd.concat(
        [backtest(complete_prices[state]).assign(State=state) for state in STATES],
        ignore_index=True,
    )
    if forecasts.empty:
        raise ValueError("No common forecast targets have actual prices and seasonal observations")

    forecasts["Target period"] = "Before November 2025"
    forecasts.loc[forecasts["Target"].ge(REPORTING_CHANGE), "Target period"] = "November 2025 onward"
    errors = forecasts[METHODS].sub(forecasts["Actual"], axis="index").abs()
    groups = ["State", "Target period", "Months ahead"]
    grouped = forecasts[groups].join(errors).groupby(groups)
    summary = grouped[METHODS].mean()
    summary.insert(0, "Targets", grouped.size())
    return forecasts, summary


def main():
    print(f"Source revision: {REVISION}")
    prices, _ = load_state_months()
    # The collector may have stopped partway through the final calendar month.
    complete_prices = prices.iloc[:-1]
    print(f"Price history: {complete_prices.index[0]} through {complete_prices.index[-1]}")
    print(f"Minimum observed training months per cutoff: {MIN_TRAINING_MONTHS}")

    forecasts, summary = evaluate_prices(complete_prices)
    print("\nMean absolute error (INR/quintal). Lower is better.")
    print(summary.to_string(float_format=lambda value: f"{value:,.2f}"))
    print("\nInspect one prediction per horizon for the latest scored Gujarat target:")
    gujarat = forecasts.loc[forecasts["State"].eq("Gujarat")]
    latest = gujarat.loc[gujarat["Target"].eq(gujarat["Target"].max())].sort_values("Months ahead")
    print(latest[["Origin", "Target", "Months ahead", "Actual", *METHODS]].to_string(
        index=False, float_format=lambda value: f"{value:,.2f}",
    ))


if __name__ == "__main__":
    main()

# %% [markdown]
# ## Exercises
# 1. Recreate a three-month seasonal forecast from its target month minus 12
#    months. Explain why looking up the origin month minus 12 changes the result.
# 2. Compare errors by state and horizon. Does the trend improve on the best
#    baseline? How many scored months support that result after the change?
# 3. Plot observed prices and forecasts for one state and horizon. Mark
#    November 2025 and inspect which individual months drive the errors.
