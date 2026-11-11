# Expansion to Edible Oilseeds Complex and FastMCP Ingestion Architecture

## Status
Accepted

## Context
Initial TradeAtlas milestones evaluated a narrow slice: Groundnut in Gujarat and Rajasthan using static historical extracts. In review, this was identified as too narrow for a functional procurement intelligence MVP. Agricultural processors, crushing mills, and traders in Central and Western India operate across the entire edible oilseeds basket and procurement corridor.

Furthermore, dynamic data retrieval from official APIs (`data.gov.in`, `api.agmarknet.gov.in`) required an interface that serves both programmatic research scripts (notebooks, backtests) and AI agents (Antigravity IDE, Claude Code, Cursor) without exposing fragile scraping scripts or unstructured HTTP access.

## Decision
1. **Commodity Scope: The Edible Oilseeds Complex**:
   TradeAtlas expands its scope to India's "Big 3" domestic oilseeds: **Groundnut**, **Soybean**, and **Mustard/Rapeseed**, representing over 85% of domestic crushing and meal volume.
2. **Geographic Scope: The 5-State Oilseed Corridor**:
   Sourcing intelligence expands to the contiguous western and central belt: **Gujarat, Rajasthan, Madhya Pradesh, Maharashtra, and Haryana**.
3. **Benchmark Hub Mandis**:
   To avoid noise from 4,000+ irregularly reporting APMCs, TradeAtlas defines curated **Benchmark Hub Mandis** (configured in `config/benchmark_mandis.json`) representing primary price-discovery and liquidity centers in each state.
4. **MSP Spread & Macro Balance Layers**:
   - **MSP Spread**: Live tracking of `(Mandi Modal Price - Central MSP)` to detect distress selling or procurement interventions.
   - **Macro Supply Balance**: Comparing UPAg latest advance production estimates against 3-year historical baselines to flag regional surplus/deficit.
5. **Dual Architecture & FastMCP Server**:
   - Deterministic fetching, caching, and arithmetic live in a pure Python package (`tradeatlas/`).
   - Exposed to AI agents and external tools via a standard **FastMCP Server** (`tradeatlas_mcp.py`) implementing 5 dedicated tools:
     1. `get_daily_mandi_prices`
     2. `get_benchmark_hub_summary`
     3. `get_spot_weekly_prices`
     4. `get_macro_supply_balance`
     5. `calculate_delivered_cost`
6. **Local DuckDB Cache (6-Hour TTL)**:
   All `data.gov.in` queries are cached in `data/cache/live_mandi.duckdb` with a 6-hour TTL to guard against `HTTP 429 Too Many Requests` rate limiting.

## Consequences
- **Positive**: AI agents and traders gain instant, verified market intelligence across the major Indian oilseeds corridor without violating portal terms or triggering CAPTCHAs.
- **Negative**: API rate limits on `data.gov.in` require caching discipline; intra-day spot prices rely on AGMARKNET 2.0 unauthenticated weekly spot endpoints until a dedicated private API feed is provisioned.
