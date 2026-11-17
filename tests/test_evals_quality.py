"""Quality layer + observability: judge routing, non-gating guarantee, trace-free replay/CI."""

import copy
import json
from pathlib import Path

import pytest

from evals import quality
from evals.runner import run_suite


# --- judge resolution through the registry ---

def test_resolve_judge_requires_the_env_var(monkeypatch):
    monkeypatch.delenv("TRADEATLAS_JUDGE_MODEL", raising=False)
    with pytest.raises(RuntimeError, match="TRADEATLAS_JUDGE_MODEL"):
        quality.resolve_judge()


def test_resolve_judge_rejects_disabled_entry(monkeypatch):
    monkeypatch.setenv("TRADEATLAS_JUDGE_MODEL", "google_ai_studio")  # disabled until smoked
    with pytest.raises(RuntimeError, match="disabled"):
        quality.resolve_judge()


def test_resolve_judge_builds_through_the_registry(monkeypatch):
    """Construction only, no network: the judge is a GatewayJudgeModel over the raw model id."""
    monkeypatch.setenv("TRADEATLAS_JUDGE_MODEL", "groq")  # registry KEY, not model id
    monkeypatch.setenv("CF_ACCOUNT_ID", "a")
    monkeypatch.setenv("CF_GATEWAY_ID", "g")
    monkeypatch.setenv("CF_AIG_TOKEN", "t")
    judge = quality.resolve_judge()
    assert judge.get_model_name() == "qwen/qwen3.8-27b"  # attribution keeps the raw id
    assert judge.load_model().openai_api_base.endswith("/groq")


# --- the layer records pairing and never touches the gate ---

class _FakeMetric:
    def __init__(self, score):
        self._score = score
        self.score = None
        self.reason = None

    def measure(self, test_case):
        self.score = self._score
        self.reason = "fake judge"


def test_run_quality_records_pairing_and_leaves_results_untouched(tmp_path, monkeypatch):
    results_payload = {
        "persona": "buyer", "mode": "live",
        "cases": [{"id": "c1", "kind": "agent-evidence-fidelity", "run_id": "rec-1",
                   "passed": True, "scored_value": "all assertions held", "expected": {}}],
    }
    before = copy.deepcopy(results_payload)
    (tmp_path / "rec-1.json").write_text(json.dumps({
        "answer": {"summary": "Veraval modal is 7650 INR/qtl.", "figures": []},
        "tool_calls": [{"tool": "get_daily_mandi_prices", "result_excerpt": "payload: 7650.0"}],
    }), encoding="utf-8")

    monkeypatch.setattr(quality, "GEval", lambda **kwargs: _FakeMetric(0.86))
    monkeypatch.setattr(quality, "FaithfulnessMetric", lambda **kwargs: _FakeMetric(0.91))

    out = quality.run_quality(
        "buyer", results_payload,
        judge=quality.GatewayJudgeModel(chat_model=object(), model_name="fake-judge"),
        runs_dir=tmp_path, out_dir=tmp_path / "q",
    )
    assert out["cases"][0]["deterministic_passed"] is True  # the pairing
    assert out["cases"][0]["relevance"]["score"] == 0.86
    assert out["cases"][0]["faithfulness"]["score"] == 0.91
    assert results_payload == before, "the quality layer must never write to the results payload"
    assert (tmp_path / "q").exists() and out["path"].endswith(".json")


def test_run_quality_skips_cases_without_run_records(tmp_path, monkeypatch):
    results_payload = {"persona": "buyer", "mode": "live", "cases": [
        {"id": "daily-cap-case", "kind": "agent-abstention", "passed": False,
         "classification": "daily-cap", "scored_value": "skipped", "expected": {}},
        {"id": "scored-case", "kind": "agent-abstention", "run_id": "missing-record",
         "passed": False, "scored_value": "run failed", "expected": {}},
    ]}
    monkeypatch.setattr(quality, "GEval", lambda **kwargs: _FakeMetric(0.5))
    monkeypatch.setattr(quality, "FaithfulnessMetric", lambda **kwargs: _FakeMetric(0.5))
    out = quality.run_quality(
        "buyer", results_payload,
        judge=quality.GatewayJudgeModel(chat_model=object(), model_name="fake-judge"),
        runs_dir=tmp_path, out_dir=tmp_path / "q",
    )
    assert out["cases"] == []
    assert sorted(out["skipped_no_record"]) == ["daily-cap-case", "scored-case"]


def test_result_excerpt_pinned_in_run_records(tmp_path):
    """The faithfulness evidence: executed calls carry bounded result text, rejected ones none."""
    from tradeatlas.agent.run_records import RunRecord, build_tool_call_records, write_run_record
    from tradeatlas.agent.tools import ToolCallRecorder

    recorder = ToolCallRecorder()
    recorder.record_executed("get_daily_mandi_prices", {"state": "Gujarat", "commodity": "Groundnut"}, 5.0, None)
    from langchain_core.messages import AIMessage, ToolMessage

    payload = "x" * 3000
    messages = [
        AIMessage(content="", tool_calls=[{"name": "get_daily_mandi_prices",
                                           "args": {"state": "Gujarat", "commodity": "Groundnut"}, "id": "c1",
                                           "type": "tool_call"}]),
        ToolMessage(content=payload, tool_call_id="c1"),
        AIMessage(content="", tool_calls=[{"name": "check_series_coverage", "args": {"state": "Rajasthan"}, "id": "c2",
                                           "type": "tool_call"}]),
        ToolMessage(content="Error: state: Field required", tool_call_id="c2", status="error"),
    ]
    records = build_tool_call_records(messages, recorder)
    executed = records[0]
    assert executed.result_excerpt is not None and len(executed.result_excerpt) == 2000  # bounded
    rejected = records[1]
    assert rejected.result_excerpt is None and "state" in (rejected.error or "")
    record = RunRecord(run_id="r", started_at="t", ended_at="t", model_id="m", prompt_version="v1",
                       code_version="c", tool_calls=records)
    dumped = json.loads(write_run_record(record, tmp_path).read_text(encoding="utf-8"))
    assert len(dumped["tool_calls"][0]["result_excerpt"]) == 2000


# --- replay/CI never trace ---

def test_replay_emits_no_traces_even_when_tracing_env_is_set(tmp_path, monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")  # operator env present — replay must ignore it

    def forbidden_tracer(*args, **kwargs):
        raise AssertionError("a LangSmith tracer was constructed during replay")

    monkeypatch.setattr("langchain_core.tracers.langchain.LangChainTracer", forbidden_tracer)
    fixture_trace = {
        "version": 1, "question": "q",
        "model_messages": [
            {"role": "ai", "content": "done.", "tool_calls": [], "usage_metadata": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}},
        ],
        "structured_response": {"summary": "unavailable for Punjab", "figures": []},
    }
    traces_dir = tmp_path / "traces" / "buyer"
    traces_dir.mkdir(parents=True)
    (traces_dir / "guard.json").write_text(json.dumps(fixture_trace), encoding="utf-8")
    suite_path = tmp_path / "mini.json"
    suite_path.write_text(json.dumps({"version": 1, "cases": [
        {"id": "mini-guard", "persona": "buyer", "question": "q", "kind": "agent-abstention",
         "target": "agent", "args": {}, "trace": "guard.json",
         "expected": {"unavailability_signal": "unavailable"}}
    ]}), encoding="utf-8")
    payload = run_suite("buyer", suite_path=suite_path, results_dir=tmp_path / "res",
                        mode="replay", traces_dir=tmp_path / "traces")
    assert payload["cases"][0]["passed"] is True
    import os

    assert os.environ.get("LANGSMITH_TRACING") == "true"  # the operator's env is restored on exit


def test_quality_layer_never_imported_outside_the_flag():
    """CI/replay isolation is structural: importing the runner never pulls in the judged layer."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-c",
         "import evals.runner, sys; assert 'evals.quality' not in sys.modules, 'judged layer leaked into import'"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr

def test_quality_flag_requires_live_mode_pre_validated(tmp_path, monkeypatch, capsys):
    """--quality without --agent is rejected BEFORE the suite runs (no wasted replay)."""
    from evals import runner as runner_mod

    ran = {"suite": False}

    def exploding_suite(*args, **kwargs):
        ran["suite"] = True
        raise AssertionError("the suite must not run when --quality misuse is rejected")

    monkeypatch.setattr(runner_mod, "run_suite", exploding_suite)
    monkeypatch.setattr("sys.argv", ["runner", "buyer", "--quality"])
    with pytest.raises(SystemExit):
        runner_mod.main()
    assert ran["suite"] is False


def test_live_runs_inherit_the_operator_tracing_env(tmp_path, monkeypatch):
    """Live mode (even simulated) never strips the operator's opt-in — only replay does."""
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    from evals import ledger, runner as runner_mod
    from tradeatlas.agent.replay import scripted_model

    trace = {
        "version": 1, "question": "q",
        "model_messages": [
            {"role": "ai", "content": "done.", "tool_calls": [], "usage_metadata": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}},
        ],
        "structured_response": {"summary": "unavailable for Punjab", "figures": []},
    }
    suite_path = tmp_path / "mini.json"
    suite_path.write_text(json.dumps({"version": 1, "cases": [
        {"id": "mini-live-trace", "persona": "buyer", "question": "q", "kind": "agent-abstention",
         "target": "agent", "args": {}, "expected": {"unavailability_signal": "unavailable"}}
    ]}), encoding="utf-8")
    monkeypatch.setattr(ledger, "RUN_LEDGER_PATH", tmp_path / "run_ledger.jsonl")
    monkeypatch.setattr(ledger, "USAGE_PATH", tmp_path / "usage_daily.json")
    payload = runner_mod.run_suite("buyer", suite_path=suite_path, results_dir=tmp_path / "res",
                                   mode="live", model_factory=lambda: scripted_model(trace),
                                   traces_dir=tmp_path / "traces", delay_seconds=0)
    assert payload["cases"][0]["passed"] is True
    import os

    assert os.environ.get("LANGSMITH_TRACING") == "true"  # live inherits the operator's env

