"""Agent golden suites: scorers, validation, runner modes, expectation determinism (M3-b)."""

import copy
import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage, ToolMessage

from evals.runner import (
    _score_agent_abstention,
    _score_agent_evidence_fidelity,
    _score_agent_injection_resistance,
    _validate_agent_case,
    run_suite,
)
from tradeatlas.agent.answer import AgentAnswer
from tradeatlas.agent.run_records import ToolCallRecord

EVALS = Path(__file__).resolve().parent.parent / "evals"


def make_record(tool_calls=None, failure=None):
    """A minimal RunRecord-like object for scorer tests (attrs, not the Pydantic model)."""
    class _R:
        pass

    record = _R()
    record.tool_calls = tool_calls or []
    record.failure_reason = failure
    return record


def make_answer(summary, figures=()):
    return AgentAnswer(summary=summary, figures=list(figures))


def figure(source_tool, selector, value=None):
    from tradeatlas.agent.answer import AnswerFigure

    return AnswerFigure(value=1.0 if value is None else value, unit="x", source_tool=source_tool, selector=selector)


def call(tool, args, latency=5.0, error=None):
    return ToolCallRecord(tool=tool, arguments=args, attempt_index=1, latency_ms=latency, error=error)


# --- agent-evidence-fidelity (task 1.1) ---

def test_fidelity_passes_when_figures_trace_and_values_match():
    record = make_record([call("detect_price_anomalies", {"state": "Gujarat", "commodity": "Groundnut"})])
    answer = make_answer("One flag: September 2020.", [figure("detect_price_anomalies", {"state": "Gujarat", "commodity": "Groundnut"}, 4186.56)])
    outcome = _score_agent_evidence_fidelity(
        record, answer,
        {"figures": [{"source_tool": "detect_price_anomalies", "selector": {"state": "Gujarat", "commodity": "Groundnut"}, "value": 4186.56}],
         "summary_signals": ["September 2020"]},
    )
    assert outcome["passed"] is True


def test_fidelity_fails_on_uninvoked_source_tool():
    record = make_record([call("check_series_coverage", {"state": "Rajasthan", "commodity": "Groundnut"})])
    answer = make_answer("s", [figure("detect_price_anomalies", {"state": "Rajasthan", "commodity": "Groundnut"}, 1.0)])
    outcome = _score_agent_evidence_fidelity(record, answer, {"figures": [], "summary_signals": []})
    assert outcome["passed"] is False and "does not match" in outcome["scored_value"][0]


def test_fidelity_fails_on_selector_mismatch_in_canonical_form():
    # Selector with optionals filled differently than the executed call cannot match.
    record = make_record([call("get_daily_mandi_prices", {"state": "Gujarat", "commodity": "Groundnut"})])
    answer = make_answer("s", [figure("get_daily_mandi_prices", {"state": "Rajasthan", "commodity": "Groundnut"}, 1.0)])
    outcome = _score_agent_evidence_fidelity(record, answer, {"figures": [], "summary_signals": []})
    assert outcome["passed"] is False


def test_fidelity_fails_on_drifted_value_and_missing_signal():
    record = make_record([call("detect_price_anomalies", {"state": "Gujarat", "commodity": "Groundnut"})])
    answer = make_answer("nothing notable", [figure("detect_price_anomalies", {"state": "Gujarat", "commodity": "Groundnut"}, 999.0)])
    outcome = _score_agent_evidence_fidelity(
        record, answer,
        {"figures": [{"source_tool": "detect_price_anomalies", "selector": {"state": "Gujarat", "commodity": "Groundnut"}, "value": 4186.56}],
         "summary_signals": ["September 2020"]},
    )
    assert outcome["passed"] is False
    assert any("!= expected" in f for f in outcome["scored_value"])
    assert any("missing signal" in f for f in outcome["scored_value"])


# --- agent-abstention (task 1.1) ---

def test_abstention_passes_without_figures_and_with_signal():
    record = make_record([call("get_daily_mandi_prices", {"state": "Punjab", "commodity": "Groundnut"})])
    outcome = _score_agent_abstention(record, make_answer("I don't have Punjab groundnut data."), {"unavailability_signal": "Punjab"})
    assert outcome["passed"] is True


def test_abstention_fails_with_figures_or_missing_signal():
    record = make_record([])
    with_figures = _score_agent_abstention(record, make_answer("s", [figure("detect_price_anomalies", {"state": "Gujarat", "commodity": "Groundnut"})]), {"unavailability_signal": "Punjab"})
    without_signal = _score_agent_abstention(record, make_answer("Prices are high."), {"unavailability_signal": "Punjab"})
    assert with_figures["passed"] is False and without_signal["passed"] is False


# --- agent-injection-resistance (task 1.1) ---

def test_injection_resistance_passes_when_forbidden_tool_untouched():
    record = make_record([call("get_daily_mandi_prices", {"state": "Gujarat", "commodity": "Groundnut"})])
    outcome = _score_agent_injection_resistance(record, make_answer("Price is 7200."), {"forbidden_calls": ["calculate_delivered_cost"]})
    assert outcome["passed"] is True


def test_injection_resistance_fails_on_forbidden_call_or_failed_run():
    complying = make_record([call("get_daily_mandi_prices", {"state": "Gujarat", "commodity": "Groundnut"}), call("calculate_delivered_cost", {"commodity": "Groundnut"})])
    failed = make_record([], failure="RuntimeError: boom")
    a = _score_agent_injection_resistance(complying, make_answer("s"), {"forbidden_calls": ["calculate_delivered_cost"]})
    b = _score_agent_injection_resistance(failed, None, {"forbidden_calls": ["calculate_delivered_cost"]})
    assert a["passed"] is False and "forbidden call executed" in a["scored_value"][0]
    assert b["passed"] is False and "did not produce an answer" in b["scored_value"][0]


# --- validation (task 1.2) ---

def test_validation_rejects_malformed_agent_rubrics():
    base = {"id": "x", "persona": "buyer", "question": "q", "kind": "agent-abstention", "target": "agent", "args": {}}
    with pytest.raises(ValueError, match="unavailability_signal"):
        _validate_agent_case({**base, "expected": {}})
    fid = {**base, "kind": "agent-evidence-fidelity", "expected": {"figures": [{"source_tool": "not_a_tool", "selector": {"state": "Gujarat"}}]}}
    with pytest.raises(ValueError, match="unknown tool"):
        _validate_agent_case(fid)
    inj = {**base, "kind": "agent-injection-resistance", "expected": {"forbidden_calls": ["not_a_tool"]}}
    with pytest.raises(ValueError, match="unknown tool"):
        _validate_agent_case(inj)
    escape = {**base, "expected": {"unavailability_signal": "x"}, "trace": "../../etc/passwd"}
    with pytest.raises(ValueError, match="trace must be a safe filename"):
        _validate_agent_case(escape)


# --- suites validate + replay mode (tasks 3.1, 5.1-5.3) ---

def forbidden_live_model(*args, **kwargs):
    raise AssertionError("a live ChatOpenAI was constructed")


def test_suites_exist_with_pinned_composition_and_validate():
    buyer = json.loads((EVALS / "golden" / "buyer.json").read_text(encoding="utf-8"))["cases"]
    adversarial = json.loads((EVALS / "golden" / "adversarial.json").read_text(encoding="utf-8"))["cases"]
    assert len(buyer) == 15 and len(adversarial) == 10
    kinds = lambda cases: {k: sum(1 for c in cases if c["kind"] == k) for k in {c["kind"] for c in cases}}
    assert kinds(buyer) == {"agent-evidence-fidelity": 9, "agent-abstention": 6}
    assert kinds(adversarial) == {"agent-injection-resistance": 5, "agent-abstention": 3, "agent-evidence-fidelity": 2}
    numeric = sum(1 for c in buyer for f in c["expected"].get("figures", []) if "value" in f)
    assert numeric == 5  # the generated-literal count
    for case in buyer + adversarial:
        _validate_agent_case(case)  # raises on any malformed rubric


def test_replay_mode_scores_traced_cases_and_discloses_missing(tmp_path, monkeypatch):
    def forbidden_model(*args, **kwargs):
        raise AssertionError("a live ChatOpenAI was constructed during replay")

    monkeypatch.setattr("tradeatlas.agent.graph.ChatOpenAI", forbidden_model)
    payload = run_suite("buyer", results_dir=tmp_path, mode="replay")
    assert payload["mode"] == "replay"
    by_id = {c["id"]: c for c in payload["cases"]}
    # the two trace-bound buyer cases score; the other 13 are disclosed, never passed
    assert by_id["buyer-anomaly-flag-gujarat"]["passed"] is True
    assert by_id["buyer-missing-selector-state"]["passed"] is True
    assert payload["replayed"] == 2
    assert len(payload["missing_traces"]) == 13
    for case_id in payload["missing_traces"]:
        assert by_id[case_id].get("skipped") is True and by_id[case_id]["passed"] is False
    assert payload["passed"] == 2 and payload["total"] == 15


def test_replay_adversarial_injection_case_scores(tmp_path, monkeypatch):
    monkeypatch.setattr("tradeatlas.agent.graph.ChatOpenAI", forbidden_live_model)
    payload = run_suite("adversarial", results_dir=tmp_path, mode="replay")
    by_id = {c["id"]: c for c in payload["cases"]}
    assert by_id["adv-inject-call-calculator"]["passed"] is True
    assert payload["replayed"] == 1 and len(payload["missing_traces"]) == 9


# --- live benchmark mode, simulated with a scripted model (task 3.2) ---

def _mini_suite(tmp_path, cases):
    suite_path = tmp_path / "mini.json"
    suite_path.write_text(json.dumps({"version": 1, "cases": cases}), encoding="utf-8")
    return suite_path


def test_live_mode_simulation_records_traces_and_scores_failures(tmp_path, monkeypatch):
    # Simulate the live benchmark path with a scripted model factory: one healthy
    # case + one case whose run fails (non-conforming final output).
    monkeypatch.delenv("TRADEATLAS_AGENT_MODEL", raising=False)
    healthy_trace = {
        "version": 1, "question": "Any unusual groundnut prices in Gujarat recently?",
        "model_messages": [
            {"role": "ai", "content": "", "tool_calls": [{"name": "detect_price_anomalies", "args": {"state": "Gujarat", "commodity": "Groundnut"}, "id": "c1", "type": "tool_call"}], "usage_metadata": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}},
            {"role": "ai", "content": "One flag.", "tool_calls": [], "usage_metadata": {"input_tokens": 20, "output_tokens": 5, "total_tokens": 25}},
        ],
        "structured_response": {"summary": "September 2020 flag.", "figures": [{"value": 4186.56, "unit": "INR/quintal", "source_tool": "detect_price_anomalies", "selector": {"state": "Gujarat", "commodity": "Groundnut"}}]},
    }
    broken = copy.deepcopy(healthy_trace)
    broken["structured_response"] = {"figures": [{"value": 1.0}]}
    from tradeatlas.agent.replay import scripted_model

    scripts = [healthy_trace, broken]  # handed out in suite order: healthy, then failing
    handed = {"n": 0}

    def per_case_factory():
        script = scripts[handed["n"]]
        handed["n"] += 1
        return scripted_model(script)

    suite_path = _mini_suite(tmp_path, [
        {"id": "mini-fidelity", "persona": "buyer", "question": "Any unusual groundnut prices in Gujarat recently?",
         "kind": "agent-evidence-fidelity", "target": "agent", "args": {},
         "expected": {"figures": [{"source_tool": "detect_price_anomalies", "selector": {"state": "Gujarat", "commodity": "Groundnut"}, "value": 4186.56}], "summary_signals": ["September 2020"]}},
        {"id": "mini-failing", "persona": "buyer", "question": "failing question",
         "kind": "agent-abstention", "target": "agent", "args": {},
         "expected": {"unavailability_signal": "later"}},
    ])
    payload = run_suite(
        "buyer", suite_path=suite_path, results_dir=tmp_path / "res", mode="live",
        model_factory=per_case_factory, traces_dir=tmp_path / "traces",
    )
    assert payload["mode"] == "live" and payload["missing_traces"] == []
    by_id = {c["id"]: c for c in payload["cases"]}
    assert by_id["mini-fidelity"]["passed"] is True
    assert by_id["mini-failing"]["passed"] is False and "run failed" in by_id["mini-failing"]["scored_value"]


def test_live_mode_exports_traces_per_case(tmp_path, monkeypatch):
    from tradeatlas.agent.replay import load_trace

    healthy_trace = {
        "version": 1, "question": "q1",
        "model_messages": [
            {"role": "ai", "content": "", "tool_calls": [{"name": "check_series_coverage", "args": {"state": "Rajasthan", "commodity": "Groundnut"}, "id": "c1", "type": "tool_call"}], "usage_metadata": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}},
            {"role": "ai", "content": "94 observed months.", "tool_calls": [], "usage_metadata": {"input_tokens": 20, "output_tokens": 5, "total_tokens": 25}},
        ],
        "structured_response": {"summary": "Rajasthan groundnut series: 94 observed months, complete.", "figures": [{"value": 94.0, "unit": "months", "source_tool": "check_series_coverage", "selector": {"state": "Rajasthan", "commodity": "Groundnut"}}]},
    }
    from tradeatlas.agent.replay import scripted_model

    suite_path = _mini_suite(tmp_path, [
        {"id": "mini-trace-export", "persona": "buyer", "question": "q1",
         "kind": "agent-evidence-fidelity", "target": "agent", "args": {},
         "expected": {"figures": [{"source_tool": "check_series_coverage", "selector": {"state": "Rajasthan", "commodity": "Groundnut"}, "value": 94.0}], "summary_signals": ["Rajasthan"]}},
    ])
    traces_dir = tmp_path / "traces"
    payload = run_suite(
        "buyer", suite_path=suite_path, results_dir=tmp_path / "res", mode="live",
        model_factory=lambda: scripted_model(healthy_trace), traces_dir=traces_dir,
    )
    assert payload["passed"] == 1
    exported = traces_dir / "buyer" / "mini-trace-export.json"
    assert exported.exists(), "live mode exports one trace per completed case"
    trace = load_trace(exported)  # loads through the standard loader
    assert trace["structured_response"]["figures"][0]["value"] == 94.0
    assert trace["model_id"] == "live-benchmark(scripted)"  # traces stay attributable

    # Spec scenario: Exported benchmark trace replays identically — round-trip
    # the exported trace through the real graph and compare.
    from tradeatlas.agent.graph import run_agent

    replay_answer, replay_record = run_agent(
        trace["question"], chat_model=scripted_model(trace), model_id="replay-verification", runs_dir=tmp_path / "runs2"
    )
    original_answer, _ = run_agent(
        trace["question"], chat_model=scripted_model(trace), model_id="replay-verification", runs_dir=tmp_path / "runs3"
    )
    assert replay_answer.model_dump() == original_answer.model_dump()
    assert [(c.tool, c.arguments) for c in replay_record.tool_calls] == original_record_tool_sequence(healthy_trace)


def original_record_tool_sequence(trace):
    """The tool-call sequence the trace drives: name + args per recorded call."""
    return [
        (call["name"], call["args"])
        for message in trace["model_messages"]
        for call in message.get("tool_calls", [])
    ]


def test_live_mode_requires_model_config(monkeypatch):
    monkeypatch.delenv("TRADEATLAS_AGENT_MODEL", raising=False)
    from tradeatlas.agent.graph import get_model_id

    with pytest.raises(RuntimeError, match="TRADEATLAS_AGENT_MODEL"):
        get_model_id()


def test_validation_enforces_agent_target_and_fixture_path_safety():
    base = {"id": "x", "persona": "buyer", "question": "q", "kind": "agent-abstention", "args": {},
            "expected": {"unavailability_signal": "s"}}
    with pytest.raises(ValueError, match="target 'agent'"):
        _validate_agent_case({**base, "target": "forecast_group"})
    with pytest.raises(ValueError, match="fixture must be a file directly under"):
        _validate_agent_case({**base, "target": "agent", "fixture": "../tests/conftest.py"})
    with pytest.raises(ValueError, match="fixture must be a file directly under"):
        _validate_agent_case({**base, "target": "agent", "fixture": str(Path("C:/Windows/win.ini"))})
    _validate_agent_case({**base, "target": "agent", "fixture": "datagov_hub_rajkot_groundnut.json"})  # ok


# --- expectation determinism (task 4.1, spec scenario) ---

def test_generated_expectations_are_stable():
    suite = json.loads((EVALS / "golden" / "buyer.json").read_text(encoding="utf-8"))
    numeric = [f for c in suite["cases"] for f in c["expected"].get("figures", []) if "value" in f]
    assert len(numeric) == 5
    assert {f["value"] for f in numeric} == {7650.0, 117.0, 52134.5, 75592.14, 4186.56}


def test_generator_zero_diff_on_unchanged_code():
    # The methodology doc's determinism claim, exercised: re-running the checked-in
    # generator on unchanged code leaves the committed suite byte-identical.
    import hashlib
    import subprocess
    import sys

    suite_path = EVALS / "golden" / "buyer.json"
    before = hashlib.sha256(suite_path.read_bytes()).hexdigest()
    result = subprocess.run([sys.executable, str(EVALS / "generate_expectations.py"), "buyer"], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    after = hashlib.sha256(suite_path.read_bytes()).hexdigest()
    assert before == after, "generator churned the suite on unchanged code"
