"""Live and Cached Ingestion Service for TradeAtlas."""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import pandas as pd

from tradeatlas.cache import (
    get_cached_records,
    is_cache_fresh,
    save_records_to_cache,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "config" / "benchmark_mandis.json"
DATA_GOV_IN_RESOURCE = "9ef84268-d588-465a-a308-a864a43d0070"
DATA_GOV_IN_URL = f"https://api.data.gov.in/resource/{DATA_GOV_IN_RESOURCE}"
AGMARKNET_SPOT_URL = "https://api.agmarknet.gov.in/v1/prices-and-arrivals/market-price/lastweek"


def get_api_key() -> str:
    """Retrieve data.gov.in API key from environment or .env file."""
    key = os.getenv("DATA_GOV_IN_API_KEY")
    if key:
        return key

    env_file = ROOT_DIR / ".env"
    if env_file.is_file():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("DATA_GOV_IN_API_KEY="):
                key = line.split("=", 1)[1].strip()
                os.environ["DATA_GOV_IN_API_KEY"] = key
                return key
    return ""


def load_benchmark_config() -> Dict[str, Any]:
    """Load benchmark hubs and MSP benchmarks from JSON configuration."""
    if not CONFIG_PATH.is_file():
        return {}
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def fetch_daily_mandi_prices(
    state: str,
    commodity: str,
    market: Optional[str] = None,
    arrival_date: Optional[str] = None,
    force_refresh: bool = False,
) -> List[Dict[str, Any]]:
    """Fetch daily mandi prices from data.gov.in with local DuckDB caching."""
    cache_key = f"{state.strip().lower()}_{commodity.strip().lower()}"

    # 1. Check DuckDB cache
    if not force_refresh and is_cache_fresh(cache_key, ttl_hours=6.0):
        cached = get_cached_records(state, commodity, market, arrival_date)
        if cached:
            return cached

    # 2. Fetch from data.gov.in
    api_key = get_api_key()
    if not api_key:
        # Fall back to whatever is cached if no API key is provided
        return get_cached_records(state, commodity, market, arrival_date)

    params: Dict[str, Any] = {
        "api-key": api_key,
        "format": "json",
        "limit": 1000,
        "filters[state]": state,
        "filters[commodity]": commodity,
    }
    if arrival_date:
        params["filters[arrival_date]"] = arrival_date

    headers = {"User-Agent": "TradeAtlas/0.2.0 (Procurement Intelligence)"}

    try:
        with httpx.Client(timeout=20.0, verify=False) as client:
            resp = client.get(DATA_GOV_IN_URL, params=params, headers=headers)
            if resp.status_code == 200:
                payload = resp.json()
                records = payload.get("records", [])
                if records:
                    save_records_to_cache(cache_key, records)
                    return get_cached_records(state, commodity, market, arrival_date)
    except Exception as e:
        print(f"[Warning] Failed to fetch live data from data.gov.in: {e}")

    # Fallback to whatever is in DuckDB cache
    return get_cached_records(state, commodity, market, arrival_date)


def fetch_spot_weekly_prices(
    market_id: int,
    state_id: int,
    commodity_id: int,
) -> Dict[str, Any]:
    """Fetch 7-day rolling spot prices from AGMARKNET 2.0 unauthenticated portal endpoint."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json",
        "Origin": "https://agmarknet.gov.in",
        "Referer": "https://agmarknet.gov.in/",
    }
    url = f"{AGMARKNET_SPOT_URL}?marketId={market_id}&stateId={state_id}&commodityId={commodity_id}"
    try:
        with httpx.Client(timeout=15.0, verify=False) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                return resp.json()
            return {"error": f"HTTP {resp.status_code}", "message": resp.text[:200]}
    except Exception as e:
        return {"error": str(e)}


def fetch_benchmark_hub_summary(state: str, commodity: str) -> Dict[str, Any]:
    """Return live benchmark prices and MSP spread across curated hub mandis for a state."""
    config = load_benchmark_config()
    msp_dict = config.get("msp_benchmark_inr_qtl", {})
    msp = msp_dict.get(commodity, 0.0)

    state_hubs = config.get("hubs", {}).get(state, {}).get(commodity, [])
    if not state_hubs:
        return {
            "state": state,
            "commodity": commodity,
            "msp_benchmark_inr_qtl": msp,
            "hubs_found": 0,
            "summary": "No curated benchmark hub mandis configured for this state and commodity.",
            "records": [],
        }

    all_prices = fetch_daily_mandi_prices(state, commodity)
    hub_records = []

    for hub in state_hubs:
        hub_name = hub["market"].lower()
        matched = [r for r in all_prices if hub_name in r["market"].lower()]
        if matched:
            top_rec = matched[0]
            modal = float(top_rec.get("modal_price", 0.0) or 0.0)
            msp_spread = modal - msp if msp > 0 else 0.0
            hub_records.append(
                {
                    "market": top_rec.get("market"),
                    "district": top_rec.get("district"),
                    "variety": top_rec.get("variety"),
                    "grade": top_rec.get("grade"),
                    "arrival_date": top_rec.get("arrival_date"),
                    "min_price": top_rec.get("min_price"),
                    "max_price": top_rec.get("max_price"),
                    "modal_price": modal,
                    "msp_benchmark": msp,
                    "msp_spread": msp_spread,
                    "distress_status": "Discount to MSP (Distress / Surplus)"
                    if msp_spread < 0
                    else "Premium to MSP (Firm Market)",
                }
            )
        else:
            hub_records.append(
                {
                    "market": hub["market"],
                    "district": hub["district"],
                    "status": "Not Reported Today",
                    "msp_benchmark": msp,
                }
            )

    return {
        "state": state,
        "commodity": commodity,
        "msp_benchmark_inr_qtl": msp,
        "hubs_monitored": len(state_hubs),
        "hubs_reporting_today": len([h for h in hub_records if "modal_price" in h]),
        "hub_details": hub_records,
    }


def fetch_macro_supply_balance(state: str, crop: str) -> Dict[str, Any]:
    """Compute harvest supply balance comparing latest advance estimates against 3-year baseline."""
    apy_path = ROOT_DIR / "data" / "raw" / "apy_state.csv.gz"
    if not apy_path.is_file():
        return {"error": f"APY dataset not found at {apy_path}"}

    df = pd.read_csv(apy_path, dtype={"Latest Estimate": "string"})
    crop_df = df.loc[
        df["State"].str.lower().eq(state.lower())
        & df["Crop"].str.lower().eq(crop.lower())
        & df["Metric"].eq("Production")
        & df["RecordType"].eq("State - Season Total")
        & df["Season"].eq("Total")
        & df["Latest Estimate"].eq("1")
    ].sort_values("Crop Year")

    if crop_df.empty:
        return {"error": f"No official production estimates found for {crop} in {state}."}

    crop_df["Production_Tonnes"] = pd.to_numeric(crop_df["Value"], errors="coerce") * 100_000.0
    latest_row = crop_df.iloc[-1]
    latest_year = latest_row["Crop Year"]
    latest_cycle = latest_row["Estimation Cycle"]
    latest_prod = latest_row["Production_Tonnes"]

    # Historical 3-year baseline prior to the latest crop year
    prior_df = crop_df.iloc[:-1].tail(3)
    if not prior_df.empty:
        baseline_prod = prior_df["Production_Tonnes"].mean()
        pct_change = ((latest_prod - baseline_prod) / baseline_prod) * 100.0
        status = f"Harvest Surplus (+{pct_change:.1f}%)" if pct_change >= 0 else f"Harvest Deficit ({pct_change:.1f}%)"
    else:
        baseline_prod = latest_prod
        pct_change = 0.0
        status = "Baseline Unavailable"

    return {
        "state": state,
        "crop": crop,
        "latest_crop_year": latest_year,
        "estimation_cycle": latest_cycle,
        "latest_production_tonnes": round(latest_prod, 0),
        "baseline_3yr_tonnes": round(baseline_prod, 0),
        "supply_balance_pct": round(pct_change, 1),
        "harvest_outlook": status,
    }
