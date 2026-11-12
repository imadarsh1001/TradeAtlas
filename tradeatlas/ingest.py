"""Live and Cached Ingestion Service for TradeAtlas.

Every service function returns an EvidenceEnvelope (tradeatlas.models) so all
consumers — MCP clients, future agents, dashboards — get the same
self-describing contract: data age, coverage, tier, caveats.
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from tradeatlas.cache import (
    get_cache_fetched_at,
    get_cached_records,
    is_cache_fresh,
    save_records_to_cache,
)
from tradeatlas.models import EvidenceEnvelope, utc_now_iso

logger = logging.getLogger(__name__)

ROOT_DIR = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT_DIR / "config" / "benchmark_mandis.json"
DATA_GOV_IN_RESOURCE = "9ef84268-d588-465a-a308-a864a43d0070"
DATA_GOV_IN_URL = f"https://api.data.gov.in/resource/{DATA_GOV_IN_RESOURCE}"
AGMARKNET_SPOT_URL = "https://api.agmarknet.gov.in/v1/prices-and-arrivals/market-price/lastweek"

# Deep-tier guarantee set: groundnut in its proof states (ADR 0006, ROADMAP M1).
DEEP_STATES = {"gujarat", "rajasthan"}
PAGE_LIMIT = 1000  # data.gov.in single-page cap
THIN_TIER_CAVEAT = (
    "Thin tier: live data without the deep-tier verification set; coverage has not been verified."
)
MSP_CAVEAT = "MSP spread compares mandi modal price to the central Minimum Support Price benchmark."
SUPPLY_CAVEAT = (
    "Compares the latest advance production estimate against the mean of up to three prior "
    "crop years; advance estimates are revised."
)


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


def tier_for(state: str, commodity: str) -> str:
    """Deep-tier only for groundnut in its proof states (Gujarat, Rajasthan); else thin."""
    if commodity.strip().lower() == "groundnut" and state.strip().lower() in DEEP_STATES:
        return "deep"
    return "thin"


def _no_data_caveat(selector: str, retrieved_at: str) -> str:
    return (
        f"No records reported for {selector} in this snapshot (retrieved {retrieved_at}). "
        "Absence of a report is not evidence that no trade occurred."
    )


def _tier_caveats(state: str, commodity: str) -> List[str]:
    return [THIN_TIER_CAVEAT] if tier_for(state, commodity) == "thin" else []


def _fetch_datagov(
    params: Dict[str, Any],
    headers: Dict[str, str],
    transport: Optional[httpx.BaseTransport],
) -> tuple[List[Dict[str, Any]], bool, bool]:
    """One live data.gov.in request. Returns (records, fetch_failed, upstream_empty)."""
    try:
        with httpx.Client(timeout=20.0, transport=transport) as client:
            resp = client.get(DATA_GOV_IN_URL, params=params, headers=headers)
        if resp.status_code == 200:
            records = resp.json().get("records", [])
            return records, False, not records
        logger.warning("data.gov.in returned HTTP %s", resp.status_code)
        return [], True, False
    except Exception as e:
        logger.warning("Failed to fetch live data from data.gov.in: %s", e)
        return [], True, False


def fetch_daily_mandi_prices(
    state: str,
    commodity: str,
    market: Optional[str] = None,
    arrival_date: Optional[str] = None,
    force_refresh: bool = False,
    transport: Optional[httpx.BaseTransport] = None,
) -> EvidenceEnvelope:
    """Fetch daily mandi prices from data.gov.in with local DuckDB caching."""
    selector = f"({state}, {commodity}"
    if market:
        selector += f", market~{market}"
    if arrival_date:
        selector += f", date={arrival_date}"
    selector += ")"

    cache_key = f"{state.strip().lower()}_{commodity.strip().lower()}"
    cached_at_entry = get_cache_fetched_at(cache_key)
    cached_at_entry_iso = cached_at_entry.isoformat() if cached_at_entry else None
    records: List[Dict[str, Any]] = []
    cached_as_of: Optional[str] = None
    upstream_notes: List[str] = []

    # 1. Check DuckDB cache
    if not force_refresh and is_cache_fresh(cache_key, ttl_hours=6.0):
        cached = get_cached_records(state, commodity, market, arrival_date)
        if cached:
            records = cached
            cached_as_of = cached_at_entry_iso
    else:
        # 2. Fetch from data.gov.in
        api_key = get_api_key()
        if not api_key:
            # Fall back to whatever is cached if no API key is provided
            records = get_cached_records(state, commodity, market, arrival_date)
            if records:
                cached_as_of = cached_at_entry_iso
        else:
            params: Dict[str, Any] = {
                "api-key": api_key,
                "format": "json",
                "limit": PAGE_LIMIT,
                "filters[state]": state,
                "filters[commodity]": commodity,
            }
            if arrival_date:
                params["filters[arrival_date]"] = arrival_date

            headers = {"User-Agent": "TradeAtlas/0.2.0 (Procurement Intelligence)"}
            live_records, fetch_failed, upstream_empty = _fetch_datagov(params, headers, transport)

            if live_records:
                save_records_to_cache(cache_key, live_records)
                records = get_cached_records(state, commodity, market, arrival_date)

            if not records:
                # Fallback to whatever is in DuckDB cache
                records = get_cached_records(state, commodity, market, arrival_date)
                if records:
                    cached_as_of = cached_at_entry_iso
                    if fetch_failed:
                        upstream_notes.append(
                            f"Live fetch failed; serving cached data fetched {cached_as_of}."
                        )
                    elif upstream_empty:
                        upstream_notes.append(
                            f"Upstream returned no records in this snapshot; serving cached data fetched {cached_as_of}."
                        )

    retrieved_at = utc_now_iso()
    observation_dates = sorted({str(r["arrival_date"]) for r in records if r.get("arrival_date")})
    caveats: List[str] = _tier_caveats(state, commodity)
    if len(records) >= PAGE_LIMIT:
        caveats.append(f"Result truncated at the first {PAGE_LIMIT} records (data.gov.in page limit).")
    caveats.extend(upstream_notes)
    no_data = not records
    if no_data:
        caveats.append(_no_data_caveat(selector, retrieved_at))

    return EvidenceEnvelope(
        payload=records,
        coverage=f"{len(records)} records for {selector}",
        tier=tier_for(state, commodity),
        retrieved_at=retrieved_at,
        observation_dates=observation_dates,
        cached_as_of=cached_as_of,
        caveats=caveats,
        no_data=no_data,
    )


def fetch_spot_weekly_prices(
    market_id: int,
    state_id: int,
    commodity_id: int,
    transport: Optional[httpx.BaseTransport] = None,
) -> EvidenceEnvelope:
    """Fetch 7-day rolling spot prices from AGMARKNET 2.0 unauthenticated portal endpoint."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json",
        "Origin": "https://agmarknet.gov.in",
        "Referer": "https://agmarknet.gov.in/",
    }
    selector = f"(market_id={market_id}, state_id={state_id}, commodity_id={commodity_id})"
    url = f"{AGMARKNET_SPOT_URL}?marketId={market_id}&stateId={state_id}&commodityId={commodity_id}"
    retrieved_at = utc_now_iso()
    error: Optional[str] = None
    payload: Any = {}
    try:
        with httpx.Client(timeout=15.0, transport=transport) as client:
            resp = client.get(url, headers=headers)
            if resp.status_code == 200:
                payload = resp.json()
            else:
                error = f"HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        error = str(e)

    caveats = [
        THIN_TIER_CAVEAT,
        "Payload is passed through from AGMARKNET 2.0 unmodified; observation dates are inside the payload.",
    ]
    if error:
        caveats.append(f"Upstream error: {error}")

    return EvidenceEnvelope(
        payload=payload if not error else {"error": error},
        coverage=f"upstream AGMARKNET spot-weekly payload for {selector}",
        tier="thin",
        retrieved_at=retrieved_at,
        caveats=caveats,
        no_data=bool(error),
    )


def fetch_benchmark_hub_summary(
    state: str,
    commodity: str,
    transport: Optional[httpx.BaseTransport] = None,
) -> EvidenceEnvelope:
    """Return live benchmark prices and MSP spread across curated hub mandis for a state."""
    config = load_benchmark_config()
    msp = config.get("msp_benchmark_inr_qtl", {}).get(commodity)

    state_hubs = config.get("hubs", {}).get(state, {}).get(commodity, [])
    hub_records: List[Dict[str, Any]] = []
    prices_envelope: Optional[EvidenceEnvelope] = None

    if state_hubs:
        prices_envelope = fetch_daily_mandi_prices(state, commodity, transport=transport)
        for hub in state_hubs:
            hub_name = hub["market"].lower()
            matched = [r for r in prices_envelope.payload if hub_name in r["market"].lower()]
            if matched:
                top_rec = matched[0]
                modal = float(top_rec.get("modal_price", 0.0) or 0.0)
                if msp:
                    msp_spread: Optional[float] = modal - msp
                    distress_status = (
                        "Discount to MSP (Distress / Surplus)"
                        if msp_spread < 0
                        else "Premium to MSP (Firm Market)"
                    )
                else:
                    msp_spread = None
                    distress_status = "MSP benchmark unavailable"
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
                        "distress_status": distress_status,
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

    hubs_reporting = len([h for h in hub_records if "modal_price" in h])
    retrieved_at = utc_now_iso()
    observation_dates = sorted(
        {str(h["arrival_date"]) for h in hub_records if h.get("arrival_date")}
    )
    caveats: List[str] = [MSP_CAVEAT, *_tier_caveats(state, commodity)]
    no_data = hubs_reporting == 0
    if not state_hubs:
        caveats.append(
            f"No curated benchmark hub mandis are configured for ({state}, {commodity})."
        )
    elif no_data:
        caveats.append(_no_data_caveat(f"({state}, {commodity}) hubs", retrieved_at))

    return EvidenceEnvelope(
        payload={
            "state": state,
            "commodity": commodity,
            "msp_benchmark_inr_qtl": msp,
            "hubs_monitored": len(state_hubs),
            "hubs_reporting_today": hubs_reporting,
            "hub_details": hub_records,
        },
        coverage=f"{hubs_reporting} of {len(state_hubs)} configured hub mandis reporting for ({state}, {commodity})",
        tier=tier_for(state, commodity),
        retrieved_at=retrieved_at,
        observation_dates=observation_dates,
        cached_as_of=prices_envelope.cached_as_of if prices_envelope is not None else None,
        caveats=caveats,
        no_data=no_data,
    )


def fetch_macro_supply_balance(state: str, crop: str) -> EvidenceEnvelope:
    """Compute harvest supply balance comparing latest advance estimates against prior-year baseline."""
    apy_path = ROOT_DIR / "data" / "raw" / "apy_state.csv.gz"
    if not apy_path.is_file():
        return EvidenceEnvelope(
            payload={"error": f"APY dataset not found at {apy_path}"},
            coverage=f"0 estimates for ({state}, {crop})",
            tier=tier_for(state, crop),
            retrieved_at=utc_now_iso(),
            caveats=[f"APY dataset not found at {apy_path}"],
            no_data=True,
        )

    # Lazy import: keeps module import light and lets tests monkeypatch pd.read_csv.
    import pandas as pd

    df = pd.read_csv(apy_path, dtype={"Latest Estimate": "string"})
    crop_df = df.loc[
        df["State"].str.lower().eq(state.lower())
        & df["Crop"].str.lower().eq(crop.lower())
        & df["Metric"].eq("Production")
        & df["RecordType"].eq("State - Season Total")
        & df["Season"].eq("Total")
        & df["Latest Estimate"].eq("1")
    ].sort_values("Crop Year")

    retrieved_at = utc_now_iso()
    if crop_df.empty:
        return EvidenceEnvelope(
            payload={"error": f"No official production estimates found for {crop} in {state}."},
            coverage=f"0 estimates for ({state}, {crop})",
            tier=tier_for(state, crop),
            retrieved_at=retrieved_at,
            caveats=[f"No official production estimates found for {crop} in {state}."],
            no_data=True,
        )

    crop_df["Production_Tonnes"] = pd.to_numeric(crop_df["Value"], errors="coerce") * 100_000.0
    latest_row = crop_df.iloc[-1]
    latest_year = str(latest_row["Crop Year"])
    latest_cycle = latest_row["Estimation Cycle"]
    latest_prod = latest_row["Production_Tonnes"]

    # Historical baseline from up to three crop years prior to the latest
    prior_df = crop_df.iloc[:-1].tail(3)
    baseline_prod = float(prior_df["Production_Tonnes"].mean()) if not prior_df.empty else None

    caveats: List[str] = [SUPPLY_CAVEAT, *_tier_caveats(state, crop)]

    if baseline_prod is None or baseline_prod <= 0:
        # No usable prior-year baseline: report the latest estimate without a fabricated percentage.
        payload = {
            "state": state,
            "crop": crop,
            "latest_crop_year": latest_year,
            "estimation_cycle": latest_cycle,
            "latest_production_tonnes": round(latest_prod, 0),
            "harvest_outlook": "Baseline Unavailable",
        }
    else:
        pct_change = ((latest_prod - baseline_prod) / baseline_prod) * 100.0
        status = f"Harvest Surplus (+{pct_change:.1f}%)" if pct_change >= 0 else f"Harvest Deficit ({pct_change:.1f}%)"
        payload = {
            "state": state,
            "crop": crop,
            "latest_crop_year": latest_year,
            "estimation_cycle": latest_cycle,
            "latest_production_tonnes": round(latest_prod, 0),
            "baseline_tonnes": round(baseline_prod, 0),
            "supply_balance_pct": round(pct_change, 1),
            "harvest_outlook": status,
        }

    return EvidenceEnvelope(
        payload=payload,
        coverage=f"latest official estimate for ({state}, {crop}) from data/raw/apy_state.csv.gz",
        tier=tier_for(state, crop),
        retrieved_at=retrieved_at,
        observation_dates=[latest_year],
        caveats=caveats,
        no_data=False,
    )
