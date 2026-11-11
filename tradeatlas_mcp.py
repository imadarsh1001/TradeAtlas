"""TradeAtlas Model Context Protocol (MCP) Server.

Exposes deterministic agricultural commodity intelligence, mandi prices, and
quote calculation tools for the Indian Edible Oilseeds Complex.
"""

from typing import Any, Dict, List, Optional
from mcp.server.mcpserver import MCPServer

from tradeatlas.calculator import calculate_delivered_cost as calc_delivered_cost
from tradeatlas.ingest import (
    fetch_benchmark_hub_summary,
    fetch_daily_mandi_prices,
    fetch_macro_supply_balance,
    fetch_spot_weekly_prices,
)

mcp = MCPServer(
    "TradeAtlas Procurement Intelligence",
    description="Real-time mandi prices, benchmark hub comparisons, and procurement cost calculations for Indian oilseeds."
)


@mcp.tool()
def get_daily_mandi_prices(
    state: str,
    commodity: str,
    market: Optional[str] = None,
    arrival_date: Optional[str] = None,
    force_refresh: bool = False,
) -> List[Dict[str, Any]]:
    """Fetch daily wholesale mandi prices from data.gov.in (cached in local DuckDB with 6h TTL).

    Args:
        state: Indian State name (e.g. 'Gujarat', 'Rajasthan', 'Madhya Pradesh', 'Maharashtra', 'Haryana').
        commodity: Target crop ('Groundnut', 'Soybean', 'Mustard').
        market: Optional specific APMC mandi filter (e.g. 'Rajkot', 'Bikaner', 'Indore').
        arrival_date: Optional date string in 'DD/MM/YYYY' format.
        force_refresh: Set to True to bypass DuckDB cache and re-query data.gov.in.

    Returns:
        List of records with market, district, variety, grade, min_price, max_price, and modal_price.
    """
    return fetch_daily_mandi_prices(
        state=state,
        commodity=commodity,
        market=market,
        arrival_date=arrival_date,
        force_refresh=force_refresh,
    )


@mcp.tool()
def get_benchmark_hub_summary(state: str, commodity: str) -> Dict[str, Any]:
    """Fetch live benchmark prices and MSP spread across curated hub mandis for a state.

    Args:
        state: State in the 5-state corridor ('Gujarat', 'Rajasthan', 'Madhya Pradesh', 'Maharashtra', 'Haryana').
        commodity: 'Groundnut', 'Soybean', or 'Mustard'.

    Returns:
        Consolidated summary comparing benchmark APMC prices against central Minimum Support Price (MSP).
    """
    return fetch_benchmark_hub_summary(state=state, commodity=commodity)


@mcp.tool()
def get_spot_weekly_prices(
    market_id: int,
    state_id: int,
    commodity_id: int,
) -> Dict[str, Any]:
    """Fetch rolling 7-day spot prices from AGMARKNET 2.0 unauthenticated portal endpoint.

    Args:
        market_id: AGMARKNET APMC market ID (e.g. 60 for Rajkot APMC).
        state_id: AGMARKNET state ID (e.g. 11 for Gujarat, 29 for Rajasthan).
        commodity_id: AGMARKNET commodity ID (e.g. 10 for Groundnut).

    Returns:
        7-day rolling prices broken down by variety with non-reporting (NR) flags.
    """
    return fetch_spot_weekly_prices(
        market_id=market_id,
        state_id=state_id,
        commodity_id=commodity_id,
    )


@mcp.tool()
def get_macro_supply_balance(state: str, crop: str) -> Dict[str, Any]:
    """Compute crop harvest supply balance comparing UPAg latest advance estimates against 3-year baseline.

    Args:
        state: State name (e.g. 'Gujarat', 'Rajasthan', 'Madhya Pradesh').
        crop: 'Groundnut', 'Soybean', or 'Mustard'.

    Returns:
        Macro harvest outlook percentage showing harvest surplus or deficit.
    """
    return fetch_macro_supply_balance(state=state, crop=crop)


@mcp.tool()
def calculate_delivered_cost(
    commodity: str,
    base_price_rs_qtl: float,
    freight_per_tonne: float,
    ancillary_per_tonne: float = 0.0,
    order_tonnes: float = 100.0,
    is_pod: bool = False,
    decortication_allowance_tonne: float = 1500.0,
) -> Dict[str, Any]:
    """Deterministically calculate total delivered landed procurement cost per tonne and order total.

    Args:
        commodity: 'Groundnut', 'Soybean', or 'Mustard'.
        base_price_rs_qtl: Wholesale price in INR per quintal (1 Quintal = 100 kg).
        freight_per_tonne: Logistics & transport cost per metric tonne.
        ancillary_per_tonne: Mandi cess, loading, unloading, brokerage, and weighment charges.
        order_tonnes: Order requirement volume in metric tonnes (default 100 MT).
        is_pod: True if groundnut quote is for unshelled raw pods (applies 70% shelling outturn).
        decortication_allowance_tonne: Processing cost per tonne for decorticating pods to kernels.

    Returns:
        Full cost breakdown with delivered cost per tonne and total order value.
    """
    return calc_delivered_cost(
        commodity=commodity,
        base_price_rs_qtl=base_price_rs_qtl,
        freight_per_tonne=freight_per_tonne,
        ancillary_per_tonne=ancillary_per_tonne,
        order_tonnes=order_tonnes,
        is_pod=is_pod,
        decortication_allowance_tonne=decortication_allowance_tonne,
    )


if __name__ == "__main__":
    mcp.run()
