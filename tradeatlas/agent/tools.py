"""LangChain tool bindings over the seven evidence-card service functions.

The MCP server (tradeatlas_mcp.py) and this module are two surfaces over the same
functions; tests/test_agent_tools.py pins names, argument names, required-ness,
defaults, and descriptions between them so the surfaces cannot drift.

Agent-side hardening (no MCP counterpart, by design): serialized tool results are
size-capped for the model context (payload replaced with a disclosed truncation
marker), and per-run force_refresh calls are budgeted so a model — or a payload
steering it — cannot burn cache-bypass fetches.
"""

import json
import time
from typing import Any, Callable, Dict, List, Optional

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from tradeatlas.analytics import check_series_coverage, detect_price_anomalies
from tradeatlas.calculator import calculate_delivered_cost
from tradeatlas.ingest import (
    fetch_benchmark_hub_summary,
    fetch_daily_mandi_prices,
    fetch_macro_supply_balance,
    fetch_spot_weekly_prices,
)
from tradeatlas.models import EvidenceEnvelope

AGENT_TOOL_NAMES = (
    "get_daily_mandi_prices",
    "get_benchmark_hub_summary",
    "get_spot_weekly_prices",
    "get_macro_supply_balance",
    "calculate_delivered_cost",
    "detect_price_anomalies",
    "check_series_coverage",
)

# Agent-context guards (see module docstring).
MAX_TOOL_RESULT_CHARS = 20_000
FORCE_REFRESH_BUDGET_PER_RUN = 3



class DailyMandiPricesArgs(BaseModel):
    """Arguments for get_daily_mandi_prices, mirroring the MCP signature."""

    state: str = Field(description="Indian State name (e.g. 'Gujarat', 'Rajasthan', 'Madhya Pradesh', 'Maharashtra', 'Haryana').")
    commodity: str = Field(description="Target crop ('Groundnut', 'Soybean', 'Mustard').")
    market: Optional[str] = Field(default=None, description="Optional specific APMC mandi filter (e.g. 'Rajkot', 'Bikaner', 'Indore').")
    arrival_date: Optional[str] = Field(default=None, description="Optional date string in 'DD/MM/YYYY' format.")
    force_refresh: bool = Field(default=False, description="Set to True to bypass DuckDB cache and re-query data.gov.in.")


class BenchmarkHubSummaryArgs(BaseModel):
    """Arguments for get_benchmark_hub_summary, mirroring the MCP signature."""

    state: str = Field(description="State in the 5-state corridor ('Gujarat', 'Rajasthan', 'Madhya Pradesh', 'Maharashtra', 'Haryana').")
    commodity: str = Field(description="'Groundnut', 'Soybean', or 'Mustard'.")


class SpotWeeklyPricesArgs(BaseModel):
    """Arguments for get_spot_weekly_prices, mirroring the MCP signature."""

    market_id: int = Field(description="AGMARKNET APMC market ID (e.g. 60 for Rajkot APMC).")
    state_id: int = Field(description="AGMARKNET state ID (e.g. 11 for Gujarat, 29 for Rajasthan).")
    commodity_id: int = Field(description="AGMARKNET commodity ID (e.g. 10 for Groundnut).")


class MacroSupplyBalanceArgs(BaseModel):
    """Arguments for get_macro_supply_balance, mirroring the MCP signature."""

    state: str = Field(description="State name (e.g. 'Gujarat', 'Rajasthan', 'Madhya Pradesh').")
    crop: str = Field(description="'Groundnut', 'Soybean', or 'Mustard'.")


class DeliveredCostArgs(BaseModel):
    """Arguments for calculate_delivered_cost, mirroring the MCP signature.

    Monetary/volume fields are agent-side bounded to non-negative (positive volume)
    values — a model emitting negatives is a validation error, not a quote.
    """

    commodity: str = Field(description="'Groundnut', 'Soybean', or 'Mustard'.")
    base_price_rs_qtl: float = Field(ge=0, description="Wholesale price in INR per quintal (1 Quintal = 100 kg).")
    freight_per_tonne: float = Field(ge=0, description="Logistics & transport cost per metric tonne.")
    ancillary_per_tonne: float = Field(default=0.0, ge=0, description="Mandi cess, loading, unloading, brokerage, and weighment charges.")
    order_tonnes: float = Field(default=100.0, gt=0, description="Order requirement volume in metric tonnes (default 100 MT).")
    is_pod: bool = Field(default=False, description="True if groundnut quote is for unshelled raw pods (applies 70% shelling outturn).")
    decortication_allowance_tonne: float = Field(default=1500.0, ge=0, description="Processing cost per tonne for decorticating pods to kernels.")


class PriceAnomaliesArgs(BaseModel):
    """Arguments for detect_price_anomalies, mirroring the MCP signature."""

    state: str = Field(description="State in the pinned extract ('Gujarat' or 'Rajasthan').")
    commodity: str = Field(description="'Groundnut' (the pinned extract's commodity).")


class SeriesCoverageArgs(BaseModel):
    """Arguments for check_series_coverage, mirroring the MCP signature."""

    state: str = Field(description="State in the pinned extract ('Gujarat' or 'Rajasthan').")
    commodity: str = Field(description="'Groundnut' (the pinned extract's commodity).")


class _ToolSpec:
    """One bound tool: name, model-facing description, schema, and service attribute name.

    The service callable resolves lazily (``globals()[run_name]`` at build time) so the
    module's imported service names stay the single seam tests can monkeypatch.
    """

    def __init__(self, name: str, description: str, args_schema: type, run_name: str):
        self.name = name
        self.description = description
        self.args_schema = args_schema
        self.run_name = run_name


_TOOL_SPECS = [
    _ToolSpec(
        "get_daily_mandi_prices",
        """Fetch daily wholesale mandi prices from data.gov.in (cached in local DuckDB with 6h TTL).

    Args:
        state: Indian State name (e.g. 'Gujarat', 'Rajasthan', 'Madhya Pradesh', 'Maharashtra', 'Haryana').
        commodity: Target crop ('Groundnut', 'Soybean', 'Mustard').
        market: Optional specific APMC mandi filter (e.g. 'Rajkot', 'Bikaner', 'Indore').
        arrival_date: Optional date string in 'DD/MM/YYYY' format.
        force_refresh: Set to True to bypass DuckDB cache and re-query data.gov.in.

    Returns:
        EvidenceEnvelope: price records plus observation date(s), retrieval time (UTC),
        coverage count, deep/thin tier label, and caveats (explicit no-data statement when empty).
        """,
        DailyMandiPricesArgs,
        "fetch_daily_mandi_prices",
    ),
    _ToolSpec(
        "get_benchmark_hub_summary",
        """Fetch live benchmark prices and MSP spread across curated hub mandis for a state.

    Args:
        state: State in the 5-state corridor ('Gujarat', 'Rajasthan', 'Madhya Pradesh', 'Maharashtra', 'Haryana').
        commodity: 'Groundnut', 'Soybean', or 'Mustard'.

    Returns:
        EvidenceEnvelope: consolidated hub summary comparing benchmark APMC prices against
        central Minimum Support Price (MSP), with coverage (hubs reporting / monitored) and tier label.
        """,
        BenchmarkHubSummaryArgs,
        "fetch_benchmark_hub_summary",
    ),
    _ToolSpec(
        "get_spot_weekly_prices",
        """Fetch rolling 7-day spot prices from AGMARKNET 2.0 unauthenticated portal endpoint.

    Args:
        market_id: AGMARKNET APMC market ID (e.g. 60 for Rajkot APMC).
        state_id: AGMARKNET state ID (e.g. 11 for Gujarat, 29 for Rajasthan).
        commodity_id: AGMARKNET commodity ID (e.g. 10 for Groundnut).

    Returns:
        EvidenceEnvelope: 7-day rolling prices broken down by variety with non-reporting (NR) flags,
        passed through from AGMARKNET 2.0; labelled thin-tier (numeric IDs cannot establish state coverage).
        """,
        SpotWeeklyPricesArgs,
        "fetch_spot_weekly_prices",
    ),
    _ToolSpec(
        "get_macro_supply_balance",
        """Compute crop harvest supply balance comparing UPAg latest advance estimates against 3-year baseline.

    Args:
        state: State name (e.g. 'Gujarat', 'Rajasthan', 'Madhya Pradesh').
        crop: 'Groundnut', 'Soybean', or 'Mustard'.

    Returns:
        EvidenceEnvelope: macro harvest outlook percentage showing harvest surplus or deficit,
        with the crop year, estimation cycle, and basis caveats.
        """,
        MacroSupplyBalanceArgs,
        "fetch_macro_supply_balance",
    ),
    _ToolSpec(
        "calculate_delivered_cost",
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
        EvidenceEnvelope: full cost breakdown with delivered cost per tonne and total order value;
        deterministic arithmetic on user-supplied inputs (tier deep, coverage "user-supplied inputs").
        """,
        DeliveredCostArgs,
        "calculate_delivered_cost",
    ),
    _ToolSpec(
        "detect_price_anomalies",
        """Flag statistically unusual monthly price observations (robust MAD, threshold 3.5) from the pinned series.

    Args:
        state: State in the pinned extract ('Gujarat' or 'Rajasthan').
        commodity: 'Groundnut' (the pinned extract's commodity).

    Returns:
        EvidenceEnvelope: flagged observations (month, value, score, direction) with per-segment
        statistics, method/threshold caveats, and examined/flagged coverage.
        """,
        PriceAnomaliesArgs,
        "detect_price_anomalies",
    ),
    _ToolSpec(
        "check_series_coverage",
        """Report month coverage, gaps, and trailing staleness for a pinned state/commodity series.

    Args:
        state: State in the pinned extract ('Gujarat' or 'Rajasthan').
        commodity: 'Groundnut' (the pinned extract's commodity).

    Returns:
        EvidenceEnvelope: observed/missing months, longest gap, latest month, pre/post-break
        month counts (separate), and trailing staleness vs. the extract's own range.
        """,
        SeriesCoverageArgs,
        "check_series_coverage",
    ),
]

# Derived from _TOOL_SPECS so tests and pairing logic never re-encode them.
SERVICE_FOR_TOOL = {spec.name: spec.run_name for spec in _TOOL_SPECS}
AGENT_TOOL_SCHEMAS = {spec.name: spec.args_schema for spec in _TOOL_SPECS}


class ToolCallRecorder:
    """Collects executed tool invocations at the tool boundary (M3-a telemetry seam)."""

    def __init__(self) -> None:
        self.executed: List[Dict[str, Any]] = []

    def record_executed(self, tool: str, arguments: Dict[str, Any], latency_ms: Optional[float], error: Optional[str]) -> None:
        self.executed.append({"tool": tool, "arguments": arguments, "latency_ms": latency_ms, "error": error})


def canonical_tool_args(tool: str, args: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Schema-canonical form of model-call arguments — defaults filled, types coerced.

    Returns None when the arguments fail the tool's schema (a schema-rejected call).
    langchain-core passes exactly this canonical form to the tool function, so it is
    the key both the model's call and the recorder's entry reduce to (a raw-args
    comparison misclassifies executed calls whenever optionals are omitted or ints
    arrive for floats — langchain-core fills and coerces before invoking).
    """
    schema = AGENT_TOOL_SCHEMAS.get(tool)
    if schema is None:
        return None
    try:
        return schema.model_validate(args).model_dump()
    except Exception:
        return None


def build_agent_tools(recorder: Optional[ToolCallRecorder] = None) -> List[StructuredTool]:
    """Build the seven agent tools; when a recorder is given, time every executed call.

    The per-run guards (refresh budget, result cap) are scoped to one build — the
    graph rebuilds tools per run, so budgets never leak across runs.
    """
    run_state = {"force_refreshes": 0}
    tools: List[StructuredTool] = []
    for spec in _TOOL_SPECS:
        run, name = globals()[spec.run_name], spec.name

        def _recorded(
            run: Callable[..., EvidenceEnvelope] = run,
            name: str = name,
            run_state: Dict[str, int] = run_state,
            **kwargs: Any,
        ) -> Dict[str, Any]:
            started = time.perf_counter()
            error: Optional[str] = None
            try:
                if kwargs.get("force_refresh"):
                    run_state["force_refreshes"] += 1
                    if run_state["force_refreshes"] > FORCE_REFRESH_BUDGET_PER_RUN:
                        raise ValueError(
                            f"force_refresh budget exhausted for this run ({FORCE_REFRESH_BUDGET_PER_RUN}); use cached results"
                        )
                envelope = run(**kwargs)
                if len(json.dumps(envelope.model_dump(mode="json"))) > MAX_TOOL_RESULT_CHARS:
                    envelope = envelope.model_copy(
                        update={
                            "payload": (
                                f"[truncated: the serialized envelope exceeded {MAX_TOOL_RESULT_CHARS} chars; "
                                "query a narrower selector for full records]"
                            ),
                            "caveats": list(envelope.caveats) + ["payload truncated for agent context"],
                        }
                    )
            except Exception as exc:
                error = f"{type(exc).__name__}: {exc}"
                raise
            finally:
                if recorder is not None:
                    recorder.record_executed(name, kwargs, (time.perf_counter() - started) * 1000.0, error)
            return envelope.model_dump(mode="json")

        tools.append(
            StructuredTool(
                name=name,
                description=spec.description,
                args_schema=spec.args_schema,
                func=_recorded,
            )
        )
    return tools
