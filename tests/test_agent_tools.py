"""Agent tool bindings: envelope serialization and MCP parity tripwire."""

import asyncio
import json
import re
import textwrap

import pytest

from tradeatlas.agent import tools as agent_tools
from tradeatlas.agent.tools import (
    AGENT_TOOL_NAMES,
    FORCE_REFRESH_BUDGET_PER_RUN,
    MAX_TOOL_RESULT_CHARS,
    SERVICE_FOR_TOOL,
    build_agent_tools,
)
from tradeatlas.models import EvidenceEnvelope
from tradeatlas_mcp import mcp


def make_envelope(**overrides) -> EvidenceEnvelope:
    base = dict(payload={"ok": True}, coverage="test", tier="deep", retrieved_at="2026-11-14T00:00:00+00:00")
    base.update(overrides)
    return EvidenceEnvelope(**base)


@pytest.fixture()
def stubbed_services(monkeypatch):
    """Stub all seven service functions behind the bindings with fixed envelopes."""
    calls = {}
    for tool_name, service_name in SERVICE_FOR_TOOL.items():
        def stub(*args, _tool=tool_name, **kwargs):
            calls[_tool] = kwargs
            return make_envelope(payload={"stub": _tool})
        monkeypatch.setattr(agent_tools, service_name, stub, raising=True)
    return calls


def test_every_wrapper_returns_a_serialized_envelope(stubbed_services):
    tools = {t.name: t for t in build_agent_tools()}
    selectors = {
        "get_daily_mandi_prices": dict(state="Gujarat", commodity="Groundnut"),
        "get_benchmark_hub_summary": dict(state="Gujarat", commodity="Groundnut"),
        "get_spot_weekly_prices": dict(market_id=60, state_id=11, commodity_id=10),
        "get_macro_supply_balance": dict(state="Gujarat", crop="Groundnut"),
        "calculate_delivered_cost": dict(commodity="Groundnut", base_price_rs_qtl=5000.0, freight_per_tonne=900.0),
        "detect_price_anomalies": dict(state="Gujarat", commodity="Groundnut"),
        "check_series_coverage": dict(state="Gujarat", commodity="Groundnut"),
    }
    for name in AGENT_TOOL_NAMES:
        result = tools[name].func(**selectors[name])
        envelope = EvidenceEnvelope.model_validate(result)  # serialized dict round-trips
        assert envelope.payload == {"stub": name}
        assert tools[name].args_schema.model_validate(selectors[name])  # schema accepts the selector
    assert set(stubbed_services) == set(AGENT_TOOL_NAMES)  # every service was reached exactly once


def test_recorder_times_executed_calls(stubbed_services):
    recorded = agent_tools.ToolCallRecorder()
    tools = {t.name: t for t in build_agent_tools(recorded)}
    tools["detect_price_anomalies"].func(state="Gujarat", commodity="Groundnut")
    (entry,) = recorded.executed
    assert entry["tool"] == "detect_price_anomalies"
    assert entry["arguments"] == {"state": "Gujarat", "commodity": "Groundnut"}
    assert entry["latency_ms"] >= 0.0 and entry["error"] is None


def test_recorder_captures_service_errors_then_reraises(stubbed_services, monkeypatch):
    recorded = agent_tools.ToolCallRecorder()

    def boom(**kwargs):
        raise ValueError("manifest mismatch")

    monkeypatch.setattr(agent_tools, SERVICE_FOR_TOOL["check_series_coverage"], boom)
    tools = {t.name: t for t in build_agent_tools(recorded)}
    with pytest.raises(ValueError, match="manifest mismatch"):
        tools["check_series_coverage"].func(state="Gujarat", commodity="Groundnut")
    (entry,) = recorded.executed
    assert "manifest mismatch" in entry["error"] and entry["latency_ms"] is not None


# --- Parity tripwire (task 1.2): agent surface == MCP surface, exactly seven ---

def _mcp_tools():
    return {t.name: t for t in asyncio.run(mcp.list_tools())}


def _normalized(description: str) -> str:
    # FastMCP dedents docstrings; pin content, not indentation.
    return textwrap.dedent(description).strip()


def test_parity_exactly_the_seven_names_on_both_surfaces():
    mcp_tools = _mcp_tools()
    agent_tools_by_name = {t.name: t for t in build_agent_tools()}
    assert set(mcp_tools) == set(AGENT_TOOL_NAMES)
    assert set(agent_tools_by_name) == set(AGENT_TOOL_NAMES)


def test_parity_argument_names_required_defaults_and_descriptions():
    mcp_tools = _mcp_tools()
    agent_tools_by_name = {t.name: t for t in build_agent_tools()}
    for name in AGENT_TOOL_NAMES:
        mcp_tool = mcp_tools[name]
        agent_tool = agent_tools_by_name[name]
        assert _normalized(agent_tool.description) == _normalized(mcp_tool.description), name

        schema = mcp_tool.input_schema
        properties = schema.get("properties", {})
        required = set(schema.get("required", []))
        fields = agent_tool.args_schema.model_fields
        assert set(fields) == set(properties), name
        for arg, field in fields.items():
            assert (arg in required) == field.is_required(), (name, arg)
            mcp_default = properties[arg].get("default")
            if field.is_required():
                assert "default" not in properties[arg], (name, arg)
            else:
                assert mcp_default == field.default, (name, arg)


def _docstring_args(description: str) -> dict:
    """The `arg: description` pairs from a tool description's Args section."""
    section = description.split("Args:", 1)[1].split("Returns:", 1)[0]
    pairs = {}
    for line in section.strip().splitlines():
        match = re.match(r"\s*(\w+): (.+)", line)
        if match:
            pairs[match.group(1)] = match.group(2).strip()
    return pairs


def test_per_argument_descriptions_match_the_tool_docstring():
    # The model reads both the schema descriptions and the docstring-derived
    # description; they must say the same thing (MCP pins the docstring side).
    for tool in build_agent_tools():
        doc_args = _docstring_args(tool.description)
        for arg, field in tool.args_schema.model_fields.items():
            assert arg in doc_args, (tool.name, arg)
            assert field.description == doc_args[arg], (tool.name, arg)


def test_oversized_payload_is_truncated_with_disclosure(monkeypatch):
    huge = {"flags": [{"month": "2020-09", "value": 1.0, "score": 1.0, "direction": "drop"}] * 2000}

    def huge_envelope(**kwargs):
        return EvidenceEnvelope(
            payload=huge, coverage="many records", tier="deep", retrieved_at="2026-11-14T00:00:00+00:00"
        )

    monkeypatch.setattr(agent_tools, "detect_price_anomalies", huge_envelope)
    tools = {t.name: t for t in build_agent_tools()}  # built AFTER the stub: specs resolve lazily
    result = tools["detect_price_anomalies"].func(state="Gujarat", commodity="Groundnut")
    assert result["payload"].startswith("[truncated:")
    assert "payload truncated for agent context" in result["caveats"]
    assert len(json.dumps(result)) < MAX_TOOL_RESULT_CHARS


def test_force_refresh_budget_caps_cache_bypasses(monkeypatch):
    calls = {"n": 0}

    def counting_fetch(**kwargs):
        calls["n"] += 1
        return make_envelope(payload={"stub": True})

    monkeypatch.setattr(agent_tools, "fetch_daily_mandi_prices", counting_fetch)
    tools = {t.name: t for t in build_agent_tools()}
    for _ in range(FORCE_REFRESH_BUDGET_PER_RUN):
        tools["get_daily_mandi_prices"].func(state="Gujarat", commodity="Groundnut", force_refresh=True)
    with pytest.raises(ValueError, match="force_refresh budget exhausted"):
        tools["get_daily_mandi_prices"].func(state="Gujarat", commodity="Groundnut", force_refresh=True)
    assert calls["n"] == FORCE_REFRESH_BUDGET_PER_RUN  # the over-budget call never fetched


def test_delivered_cost_rejects_negative_inputs_at_the_schema():
    schema = agent_tools.AGENT_TOOL_SCHEMAS["calculate_delivered_cost"]
    base = {"commodity": "Groundnut", "base_price_rs_qtl": 5000.0, "freight_per_tonne": 900.0}
    assert schema.model_validate(base)
    with pytest.raises(Exception, match="greater than or equal to 0"):
        schema.model_validate({**base, "base_price_rs_qtl": -5.0})
    with pytest.raises(Exception, match="greater than 0"):
        schema.model_validate({**base, "order_tonnes": 0})
