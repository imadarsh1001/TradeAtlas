# %% [markdown]
# # Groundnut data proof
# Run `uv run python groundnut_data_proof.py` from the TradeAtlas directory.
# The first question is whether the two states have comparable historical evidence.

# %%
import pandas as pd

from groundnut_data import REPORTING_CHANGE, REVISION, STATES, load_state_months, load_state_production

print(f"Source revision: {REVISION}")

# %% [markdown]
# ## 1. Measure coverage before comparing prices
# Use the exact publisher label. Seed, split product and raw pods have separate
# labels. The aggregate Groundnut series does not establish a buyer's grade.
# Counts below measure usable state-month observations, not mandi reporting coverage.

# %%
prices, arrivals = load_state_months()
months = prices.index
coverage = pd.DataFrame(
    {"Calendar months": len(months), "Usable price months": prices.count(),
     "Usable arrival months": arrivals.count()},
)
print(f"\nState-month coverage, {months[0]} through {months[-1]}\n{coverage.to_string()}")

# %% [markdown]
# ## 2. Compare price differences on matched months
# The collector can stop before the last day of the final month. Exclude that month
# from comparisons until its actual cutoff is established. Examine the periods
# before and after the reporting change separately. A difference in the results
# could reflect a change in which mandis reported.

# %%
matched = prices.loc[prices.index < months[-1], STATES].dropna().copy()
price_spread = matched["Gujarat"] - matched["Rajasthan"]
matched["Gujarat minus Rajasthan (INR/quintal)"] = price_spread
before = price_spread.loc[price_spread.index < REPORTING_CHANGE]
after = price_spread.loc[price_spread.index >= REPORTING_CHANGE]

print("\nMedian of monthly Gujarat minus Rajasthan price differences")
for label, spread in [("Before November 2025", before), ("November 2025 onward", after)]:
    result = f"{spread.median():,.2f} INR/quintal" if len(spread) else "no matched months"
    print(f"{label}: {result} across {len(spread)} matched months")
print("\nLatest five matched months (INR/quintal)")
print(matched.tail().to_string(float_format=lambda value: f"{value:,.2f}"))

# %% [markdown]
# ## 3. Keep production at crop-year grain
# Use the published state total so seasonal rows are counted once. Preserve the
# estimate cycle. These quantities describe production, while arrivals describe
# what reporting markets received. Compare each at its own time scale.

# %%
production = load_state_production()
print("\nLatest three published crop years per state")
recent = production.sort_values(["State", "Crop Year"]).groupby("State").tail(3)
print(recent.drop(columns=["Unit Of Measure", "Value"]).to_string(
    index=False, float_format=lambda value: f"{value:,.0f}",
))

# %% [markdown]
# ## Exercises
# 1. Recalculate one displayed price spread by hand from the raw CSV. Explain
#    how an unmatched month could change a comparison of state medians.
# 2. Group the pre-change matched prices by calendar month and plot the medians.
#    Show how many observations support each month and look for recurring patterns.
# 3. Pick a production row and check the conversion and estimate cycle against
#    the source. List the additional evidence needed to advise where to seek quotes.
# 4. Open groundnut_price_backtest.py to evaluate two baselines and a linear trend
#    on historical cutoffs.
