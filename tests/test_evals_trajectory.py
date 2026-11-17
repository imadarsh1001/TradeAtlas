"""Trajectory checks + signal semantics: the deterministic Gate Layer additions."""

import json
from pathlib import Path

import pytest

from evals.runner import (
    _pinned_args_agree,
    _signal_satisfied,
    _trajectory_failures,
    _validate_agent_case,
)
from tradeatlas.agent.run_records import ToolCallRecord

EVALS = Path(__file__).resolve().parent.parent / "evals"


def call(tool, args, latency=5.0, error=None):
    return ToolCallRecord(tool=tool, arguments=args, attempt_index=1, latency_ms=latency, error=error)


class _R:
    def __init__(self, calls):
        self.tool_calls = calls


# --- duplicate-call invariant ---

def test_duplicate_identical_successful_call_fails():
    record = _R([
        call("get_daily_mandi_prices", {"state": "Gujarat", "commodity": "Groundnut"}),
        call("get_daily_mandi_prices", {"state": "Gujarat", "commodity": "Groundnut"}),
    ])
    failures = _trajectory_failures(record, {})
    assert any("duplicate call" in f for f in failures)


def test_rejected_then_corrected_retry_is_not_a_violation():
    # Schema-rejected calls carry no latency and never enter the successful set —
    # the coverage-retry pattern (different canonical args on the retry) is safe.
    record = _R([
        ToolCallRecord(tool="check_series_coverage", arguments={"commodity": "Groundnut"},
                       attempt_index=1, latency_ms=None, error="state: Field required"),
        call("check_series_coverage", {"state": "Rajasthan", "commodity": "Groundnut"}),
    ])
    assert _trajectory_failures(record, {}) == []


def test_same_tool_with_different_args_is_not_a_duplicate():
    record = _R([
        call("get_daily_mandi_prices", {"state": "Gujarat", "commodity": "Groundnut"}),
        call("get_daily_mandi_prices", {"state": "Rajasthan", "commodity": "Groundnut"}),
    ])
    assert _trajectory_failures(record, {}) == []


# --- expected_calls pins (agreement semantics) ---

def test_pinned_call_satisfied_including_extra_executed_args():
    # glm's kernels call explicitly set decortication_allowance_tonne=0 — a value the
    # pin never wrote. The pin is satisfied: agreement covers only what the pin sets.
    record = _R([call("calculate_delivered_cost",
                      {"commodity": "Groundnut", "base_price_rs_qtl": 5123.45,
                       "freight_per_tonne": 900, "decortication_allowance_tonne": 0, "is_pod": False})])
    pin = {"tool": "calculate_delivered_cost",
           "arguments": {"commodity": "Groundnut", "base_price_rs_qtl": 5123.45, "freight_per_tonne": 900.0}}
    assert _trajectory_failures(record, {"expected_calls": [pin]}) == []


def test_pinned_call_missing_or_contradicted_fails():
    pin = {"tool": "get_daily_mandi_prices", "arguments": {"state": "Gujarat", "commodity": "Groundnut"}}
    missing = _R([call("detect_price_anomalies", {"state": "Gujarat", "commodity": "Groundnut"})])
    contradicted = _R([call("get_daily_mandi_prices", {"state": "Rajasthan", "commodity": "Groundnut"})])
    assert any("expected call not executed" in f for f in _trajectory_failures(missing, {"expected_calls": [pin]}))
    assert any("expected call not executed" in f for f in _trajectory_failures(contradicted, {"expected_calls": [pin]}))


def test_pinned_args_agree_coerces_types():
    # Raw model args coerce before invoke (int 900 vs schema float 900.0) — the pin
    # matches across that coercion, never across raw JSON equality.
    assert _pinned_args_agree(
        "calculate_delivered_cost",
        {"commodity": "Groundnut", "base_price_rs_qtl": 5123.45, "freight_per_tonne": 900.0},
        {"commodity": "Groundnut", "base_price_rs_qtl": 5123.45, "freight_per_tonne": 900},
    )


# --- efficiency budgets are recorded, not enforced ---

def test_efficiency_budget_recorded_without_gating(tmp_path, monkeypatch):
    """A run over budget is marked in results with the calibration marker; pass/fail untouched."""
    from evals import ledger, runner as runner_mod
    from tradeatlas.agent.model_registry import ModelEntry
    from tradeatlas.agent.answer import AgentAnswer
    from tradeatlas.agent.run_records import RunRecord

    monkeypatch.setattr(
        "tradeatlas.agent.model_registry.MODEL_REGISTRY",
        [ModelEntry(key="t", provider_type="openai_compat", model="t-model", route="groq", rpm_limit=30)],
    )
    monkeypatch.setenv("TRADEATLAS_AGENT_MODEL", "t")
    monkeypatch.setenv("CF_ACCOUNT_ID", "a")
    monkeypatch.setenv("CF_GATEWAY_ID", "g")
    monkeypatch.setenv("CF_AIG_TOKEN", "t")
    monkeypatch.setattr(ledger, "RUN_LEDGER_PATH", tmp_path / "run_ledger.jsonl")
    monkeypatch.setattr(ledger, "USAGE_PATH", tmp_path / "usage_daily.json")
    monkeypatch.setattr(runner_mod, "_sleep", lambda s: None)

    def fake_case(case, persona, mode, model_factory, traces_root, live_model=None, live_model_id=None):
        record = RunRecord(
            run_id="stub", started_at="2026-11-17T00:00:00+00:00", ended_at="2026-11-17T00:00:01+00:00",
            model_id="t-model", prompt_version="v1", code_version="test",
            answer=AgentAnswer(summary="the selector is unavailable", figures=[]).model_dump(mode="json"),
            model_touches=9,
        )
        return AgentAnswer(summary="the selector is unavailable", figures=[]), record, False

    monkeypatch.setattr(runner_mod, "_run_agent_case", fake_case)
    suite_path = tmp_path / "mini.json"
    suite_path.write_text(json.dumps({"version": 1, "cases": [
        {"id": "mini-budget", "persona": "buyer", "question": "q", "kind": "agent-abstention",
         "target": "agent", "args": {}, "expected": {"unavailability_signal": "unavailable", "efficiency_budget": 4}}
    ]}), encoding="utf-8")
    payload = runner_mod.run_suite("buyer", suite_path=suite_path, results_dir=tmp_path / "res",
                                   mode="live", traces_dir=tmp_path / "traces", delay_seconds=0)
    entry = payload["cases"][0]
    assert entry["passed"] is True  # the budget did NOT flip the gate
    assert entry["efficiency"] == {"budget": 4, "touches": 9, "exceeded": True, "calibration": "pending"}


# --- signal semantics ---

def test_signal_satisfied_str_and_any_of():
    assert _signal_satisfied("quintal", "prices in INR/quintal")
    assert not _signal_satisfied("quintal", "prices in INR/qtl")  # qtl is not inside quintal
    assert _signal_satisfied(["quintal", "qtl"], "prices in INR/qtl")  # any-of accepts the abbreviation
    assert _signal_satisfied(["quintal", "qtl"], "per quintal")
    assert not _signal_satisfied(["quintal", "qtl"], "per tonne")


def test_suite_validation_accepts_any_of_and_trajectory_rubrics():
    base = {"id": "x", "persona": "buyer", "question": "q", "kind": "agent-evidence-fidelity",
            "target": "agent", "args": {}, "expected": {"figures": [], "summary_signals": []}}
    ok = {**base, "expected": {"summary_signals": [["supply", "supplied"], "Gujarat"],
                               "expected_calls": [{"tool": "get_macro_supply_balance",
                                                   "arguments": {"state": "Gujarat", "crop": "Groundnut"}}],
                               "efficiency_budget": 12}}
    _validate_agent_case(ok)  # accepted
    bad_signal = {**base, "expected": {"summary_signals": [[]]}}
    with pytest.raises(ValueError, match="any-of signal"):
        _validate_agent_case(bad_signal)
    bad_call = {**base, "expected": {"figures": [{"source_tool": "detect_price_anomalies",
                                                  "selector": {"state": "Gujarat", "commodity": "Groundnut"}}],
                                     "expected_calls": [{"tool": "not_a_tool", "arguments": {}}]}}
    with pytest.raises(ValueError, match="unknown tool"):
        _validate_agent_case(bad_call)
    bad_budget = {**base, "expected": {"summary_signals": ["Gujarat"], "efficiency_budget": 0}}
    with pytest.raises(ValueError, match="positive integer"):
        _validate_agent_case(bad_budget)


def test_committed_suite_pins_validate():
    """The committed buyer suite (with pins + bindings) validates under the new rubric shapes."""
    cases = json.loads((EVALS / "golden" / "buyer.json").read_text(encoding="utf-8"))["cases"]
    assert sum(1 for c in cases if c.get("trace")) == 15  # canonical vertex traces: fully bound
    assert sum(1 for c in cases if c["expected"].get("expected_calls")) == 5
    for case in cases:
        _validate_agent_case(case)
