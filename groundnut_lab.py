import marimo

__generated_with = "0.25.2"
app = marimo.App()


@app.cell
def _():
    import altair as alt
    import marimo as mo
    import pandas as pd

    from groundnut_data import REPORTING_CHANGE, REVISION, STATES, load_state_months
    from groundnut_price_backtest import HORIZONS, METHODS, evaluate_prices

    return (
        HORIZONS,
        METHODS,
        REPORTING_CHANGE,
        REVISION,
        STATES,
        alt,
        evaluate_prices,
        load_state_months,
        mo,
        pd,
    )


@app.cell
def _(mo):
    mo.md("""
    # Groundnut price lab

    Compare monthly state prices for Gujarat and Rajasthan. At each historical
    cutoff, the backtest predicts one to three months ahead using the last
    observed price, the same month last year, and a fitted linear trend.
    """)
    return


@app.cell
def _(evaluate_prices, load_state_months, pd):
    prices, arrivals = load_state_months()
    complete_prices = prices.iloc[:-1]
    coverage = pd.DataFrame({
        "Calendar months": len(complete_prices),
        "Price observations": complete_prices.count(),
        "Arrival observations": arrivals.iloc[:-1].count(),
    }).rename_axis("State").reset_index()
    forecasts, summary = evaluate_prices(complete_prices)
    return complete_prices, coverage, forecasts, prices, summary


@app.cell
def _(REVISION, complete_prices, coverage, mo, prices):
    mo.vstack([
        mo.md(f"""
        ## Data coverage

        The lab uses **{complete_prices.index[0]} through {complete_prices.index[-1]}**.
        It excludes {prices.index[-1]} because the final month may be partial.
        The extract gives one historical snapshot, so the backtest assumes each
        completed month's observation was available at its cutoff.
        [Pinned AGMARKNET extract](https://github.com/herrrickshaw/india-mandi-arrivals/tree/{REVISION}/data/agmarknet)
        """),
        mo.ui.table(coverage, selection=None),
    ])
    return


@app.cell
def _():
    2+3
    return


@app.cell
def _(HORIZONS, STATES, mo):
    state = mo.ui.dropdown(options=STATES, value="Gujarat", label="State")
    horizon = mo.ui.dropdown(
        options={f"{months} month" + ("s" if months > 1 else ""): months for months in HORIZONS},
        value="1 month",
        label="Forecast horizon",
    )
    mo.hstack([state, horizon], justify="start")
    return horizon, state


@app.cell
def _(METHODS, REPORTING_CHANGE, alt, forecasts, horizon, mo, pd, state):
    _selected = forecasts.loc[
        forecasts["State"].eq(state.value) & forecasts["Months ahead"].eq(horizon.value),
        ["Target", "Actual", *METHODS],
    ].copy()
    _selected["Target"] = _selected["Target"].dt.to_timestamp()
    _plot_data = _selected.melt(id_vars="Target", var_name="Series", value_name="Price")
    _lines = alt.Chart(_plot_data).mark_line().encode(
        x=alt.X("Target:T", title="Target month"),
        y=alt.Y("Price:Q", title="INR per quintal", scale=alt.Scale(zero=False)),
        color=alt.Color("Series:N", sort=["Actual", *METHODS]),
        tooltip=[alt.Tooltip("Target:T", format="%b %Y"), "Series:N", alt.Tooltip("Price:Q", format=",.2f")],
    )
    _reporting_change = alt.Chart(pd.DataFrame({
        "Target": [REPORTING_CHANGE.to_timestamp()],
    })).mark_rule(color="#626b76", strokeDash=[5, 4]).encode(x="Target:T")
    mo.vstack([
        mo.md("## Actual and predicted prices\n\nThe dashed line marks the November 2025 reporting change."),
        (_lines + _reporting_change).properties(width="container", height=340),
    ])
    return


@app.cell
def _(horizon, mo, state, summary):
    _score = summary.xs(
        (state.value, horizon.value), level=("State", "Months ahead"),
    ).reset_index().round(2)
    mo.vstack([
        mo.md("""
        ## Forecast error

        Lower mean absolute error is better. Values are in INR per quintal.
        Each method uses the same scored target months in each row. Compare
        target counts before drawing conclusions about the newer period.
        """),
        mo.ui.table(_score, selection=None),
    ])
    return


if __name__ == "__main__":
    app.run()
