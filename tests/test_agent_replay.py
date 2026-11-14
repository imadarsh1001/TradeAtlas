"""Offline replay: trace format, scripted model, determinism, provenance (tasks 5.1-5.2)."""

from pathlib import Path

import pytest

from tradeatlas.agent import graph as graph_module
from tradeatlas.agent.replay import TRACES_DIR, ScriptedChatModel, load_trace, scripted_model, trace_messages
from tradeatlas.agent.graph import run_agent

TRACES = TRACES_DIR  # single-sourced from the replay module


def replay_once(tmp_path, trace_name):
    trace = load_trace(TRACES / trace_name)
    return run_agent(trace["question"], chat_model=scripted_model(trace), model_id="scripted-trace", runs_dir=tmp_path)


def test_load_trace_rejects_unknown_version(tmp_path):
    bad = tmp_path / "trace.json"
    bad.write_text('{"version": 99, "model_messages": [], "structured_response": {}}', encoding="utf-8")
    with pytest.raises(ValueError, match="trace version"):
        load_trace(bad)


def test_scripted_model_drives_messages_in_order():
    trace = load_trace(TRACES / "anomaly_single_tool.json")
    model = scripted_model(trace)
    first = model._generate([]).generations[0].message
    second = model._generate([]).generations[0].message
    assert first.tool_calls[0]["name"] == "detect_price_anomalies"
    assert "September 2020" in second.content
    with pytest.raises(RuntimeError, match="Trace exhausted"):
        model._generate([])


def test_trace_loader_reconstructs_usage_metadata():
    trace = load_trace(TRACES / "anomaly_single_tool.json")
    (first, second) = trace_messages(trace)
    assert first.usage_metadata["total_tokens"] == 450
    assert second.usage_metadata["total_tokens"] == 1672


def test_replay_is_deterministic(tmp_path):
    trace = load_trace(TRACES / "anomaly_single_tool.json")
    a_answer, a_record = run_agent(trace["question"], chat_model=scripted_model(trace), model_id="s", runs_dir=tmp_path)
    b_answer, b_record = run_agent(trace["question"], chat_model=scripted_model(trace), model_id="s", runs_dir=tmp_path)
    assert a_answer.model_dump() == b_answer.model_dump()  # same validated answer
    # Whole-record determinism except the exempt fields (run id, timestamps, latencies):
    def scrub(record):
        dump = record.model_dump()
        dump.pop("run_id"), dump.pop("started_at"), dump.pop("ended_at")
        for call in dump["tool_calls"]:
            call.pop("latency_ms")
        return dump
    assert scrub(a_record) == scrub(b_record)


def test_answer_figures_trace_to_tools_invoked_in_the_run(tmp_path):
    # Spec scenario: the answer's figures trace to envelopes returned by tool calls made
    # during that run. Fixture-level here; runtime enforcement is the source_tool
    # known-tool validator, and the invoked-set cross-check is the M3-d verifier.
    for trace_name in ("anomaly_single_tool.json", "coverage_retry.json"):
        _, record = replay_once(tmp_path, trace_name)
        invoked = {c.tool for c in record.tool_calls if c.latency_ms is not None}
        cited = {f["source_tool"] for f in record.answer["figures"]}
        assert cited and cited <= invoked, (trace_name, cited, invoked)


def test_failed_then_corrected_trace_records_both_attempts(tmp_path):
    _, record = replay_once(tmp_path, "coverage_retry.json")
    assert [c.attempt_index for c in record.tool_calls] == [1, 2]
    assert record.tool_calls[0].latency_ms is None and "state" in record.tool_calls[0].error
    assert record.tool_calls[1].latency_ms is not None and record.tool_calls[1].error is None


def test_replay_executes_pure_tool_with_optionals_end_to_end(tmp_path):
    # calculate_delivered_cost has optional args and is pure: a minimal model call
    # (optionals omitted, int where float declared) must execute and record latency —
    # the canonical-pairing guarantee, exercised through the real graph.
    trace = {
        "version": 1,
        "question": "Delivered cost for groundnut at 5000 INR/quintal with 900 freight?",
        "model_messages": [
            {
                "role": "ai",
                "content": "",
                "tool_calls": [{
                    "name": "calculate_delivered_cost",
                    "args": {"commodity": "Groundnut", "base_price_rs_qtl": 5000, "freight_per_tonne": 900},
                    "id": "c1",
                    "type": "tool_call",
                }],
                "usage_metadata": {"input_tokens": 100, "output_tokens": 10, "total_tokens": 110},
            },
            {
                "role": "ai",
                "content": "Delivered cost computed deterministically.",
                "tool_calls": [],
                "usage_metadata": {"input_tokens": 400, "output_tokens": 20, "total_tokens": 420},
            },
        ],
        "structured_response": {
            "summary": "Delivered cost computed deterministically from your inputs.",
            "figures": [{
                "value": 50900.0,
                "unit": "INR/tonne",
                "source_tool": "calculate_delivered_cost",
                "selector": {"commodity": "Groundnut", "base_price_rs_qtl": 5000.0, "freight_per_tonne": 900.0},
            }],
        },
    }
    answer, record = run_agent(trace["question"], chat_model=scripted_model(trace), model_id="s", runs_dir=tmp_path)
    assert answer is not None and record.failure_reason is None
    (call,) = record.tool_calls
    assert call.tool == "calculate_delivered_cost"
    assert call.latency_ms is not None and call.error is None
    assert call.arguments == {"commodity": "Groundnut", "base_price_rs_qtl": 5000, "freight_per_tonne": 900}


def test_replay_never_constructs_a_live_model(tmp_path, monkeypatch):
    # Fail-capable tripwire: if the run path ever builds a live ChatOpenAI during
    # replay (e.g. a default-model fallback sneaks in), this test fails loudly.
    def _forbidden(*args, **kwargs):
        raise AssertionError("a live ChatOpenAI was constructed during replay")

    monkeypatch.setattr(graph_module, "ChatOpenAI", _forbidden)
    answer, record = replay_once(tmp_path, "anomaly_single_tool.json")
    assert answer is not None and record.failure_reason is None
