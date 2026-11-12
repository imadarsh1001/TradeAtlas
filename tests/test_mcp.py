"""MCP boundary: every tool is callable through the server and returns a valid envelope.

This is the layer the SDK validates against the return annotation — a wrong
annotation breaks every tool call even when the suite below it is green.
"""

import asyncio
import json

import pytest

import tradeatlas_mcp as server
from tradeatlas.models import EvidenceEnvelope

STUB_ENV = EvidenceEnvelope(
    payload=[{"market": "Rajkot APMC", "modal_price": 7200}],
    coverage="1 records for (Gujarat, Groundnut)",
    tier="deep",
    retrieved_at="2026-11-13T00:00:00+00:00",
)


def _call(tool: str, args: dict):
    return asyncio.run(server.mcp.call_tool(tool, args))


def _serialized(result) -> str:
    return json.dumps(result, default=str)


@pytest.mark.parametrize(
    "tool,args,stub_attr",
    [
        ("get_daily_mandi_prices", {"state": "Gujarat", "commodity": "Groundnut"}, "fetch_daily_mandi_prices"),
        ("get_benchmark_hub_summary", {"state": "Gujarat", "commodity": "Groundnut"}, "fetch_benchmark_hub_summary"),
        ("get_spot_weekly_prices", {"market_id": 60, "state_id": 11, "commodity_id": 10}, "fetch_spot_weekly_prices"),
        ("get_macro_supply_balance", {"state": "Gujarat", "crop": "Groundnut"}, "fetch_macro_supply_balance"),
    ],
)
def test_tool_call_succeeds_with_envelope(monkeypatch, tool, args, stub_attr):
    monkeypatch.setattr(server, stub_attr, lambda **kwargs: STUB_ENV)
    serialized = _serialized(_call(tool, args))
    assert "coverage" in serialized
    assert "tier" in serialized
    assert "deep" in serialized


def test_delivered_cost_through_server():
    serialized = _serialized(
        _call(
            "calculate_delivered_cost",
            {
                "commodity": "Groundnut",
                "base_price_rs_qtl": 4000,
                "freight_per_tonne": 500,
                "ancillary_per_tonne": 200,
                "is_pod": True,
            },
        )
    )
    assert "59342.86" in serialized
    assert "Kernel Equivalent Benchmark" in serialized
