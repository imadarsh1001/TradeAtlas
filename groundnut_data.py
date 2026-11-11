from hashlib import file_digest
from pathlib import Path

import pandas as pd

RAW = Path(__file__).resolve().parent / "data" / "raw"
REVISION = "5c22c9261a290d61fb879b2e3f66f76a691a3e67"
SOURCE = f"https://github.com/herrrickshaw/india-mandi-arrivals/blob/{REVISION}/data"
STATES = ["Gujarat", "Rajasthan"]
REPORTING_CHANGE = pd.Period("2025-11", freq="M")

SOURCES = {
    "state_monthly.csv.gz": (
        f"{SOURCE}/agmarknet/state_monthly.csv.gz",
        "0c8018504242f769a05baac386691983f9ad9eef3cc655b48c127367c1077d32",
    ),
    "apy_state.csv.gz": (
        f"{SOURCE}/upag/apy_state.csv.gz",
        "a62f9e9e79d6c7fa3b55fb6fde3f285999ff73f3e9ff3f4821ad4212c1e1c331",
    ),
}


def pinned_file(filename):
    url, expected_hash = SOURCES[filename]
    path = RAW / filename
    if not path.is_file():
        raise FileNotFoundError(f"Save the raw download from {url} to {path}")
    with path.open("rb") as source_file:
        actual_hash = file_digest(source_file, "sha256").hexdigest()
    if actual_hash != expected_hash:
        raise ValueError(f"{path} differs from the pinned extract at {url}")
    print(f"{path}: SHA-256 {actual_hash}")
    return path


def load_state_months():
    market = pd.read_csv(
        pinned_file("state_monthly.csv.gz"),
        usecols=["month", "commodity", "state", "price_rs_qtl", "arrivals_t"],
    )
    market = market.loc[market["commodity"].eq("Groundnut") & market["state"].isin(STATES)].copy()
    market["month"] = pd.PeriodIndex(market["month"], freq="M")
    if set(market["state"]) != set(STATES) or market.duplicated(["state", "month"]).any():
        raise ValueError("Expected both states and at most one Groundnut row per state and month")

    months = pd.period_range(market["month"].min(), market["month"].max(), freq="M")
    panel = market.pivot(index="month", columns="state", values=["price_rs_qtl", "arrivals_t"])
    panel = panel.reindex(months)
    prices = panel["price_rs_qtl"]
    arrivals = panel["arrivals_t"]
    return prices.where(prices.gt(0)), arrivals.where(arrivals.ge(0))


def load_state_production():
    apy = pd.read_csv(pinned_file("apy_state.csv.gz"), dtype={"Latest Estimate": "string"})
    production = apy.loc[
        apy["State"].isin(STATES)
        & apy["Crop"].eq("Groundnut")
        & apy["RecordType"].eq("State - Season Total")
        & apy["Season"].eq("Total")
        & apy["Metric"].eq("Production")
        & apy["Latest Estimate"].eq("1"),
        ["State", "Crop Year", "Estimation Cycle", "Unit Of Measure", "Value"],
    ].copy()
    if set(production["State"]) != set(STATES) or production.duplicated(["State", "Crop Year"]).any():
        raise ValueError("Expected one latest production estimate per state and crop year")
    if not production["Unit Of Measure"].eq("Lakh Tonnes").all():
        raise ValueError("Unexpected unit in the groundnut production series")
    production["Production (tonnes)"] = pd.to_numeric(production["Value"]) * 100_000
    return production
