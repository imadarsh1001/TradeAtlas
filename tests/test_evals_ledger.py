"""Ledger mechanics + runner policy: JSONL durability, daily caps, retry-then-skip, pacing.

The runner-policy tests use a fake `_run_agent_case` (no model, no network) with a
monkeypatched registry entry, so the real-live path (factory=None) is exercised
end-to-end without touching a provider.
"""

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from evals import ledger, runner as runner_mod
from evals.runner import run_suite
from tradeatlas.agent.answer import AgentAnswer
from tradeatlas.agent.model_registry import ModelEntry
from tradeatlas.agent.run_records import RunRecord


# --- failure classification ---

def test_transport_signatures_classify_as_transport():
    for reason in [
        "Error code: 429 - rate limit exceeded",
        "RateLimitError: quota exceeded for this request",
        "APITimeoutError: Request timed out",
        "APIConnectionError: Connection error.",
        "APIStatusError: Error code: 503 - overloaded",
    ]:
        assert ledger.classify_failure(reason) == "transport", reason


def test_behaviour_failures_and_empty_reasons_never_retry():
    assert ledger.classify_failure("ValidationError: summary Field required") == "behaviour"
    # pydantic embeds the invalid payload, whose repr may mention transport words
    assert ledger.classify_failure(
        'ValidationError: 1 validation error for AgentAnswer — input_value={"note": "timeout, connection 429"}'
    ) == "behaviour"
    assert ledger.classify_failure("RuntimeError: Trace exhausted") == "behaviour"
    assert ledger.classify_failure(None) is None
    assert ledger.classify_failure("") is None


# --- run ledger durability ---

def test_ledger_round_trip_and_torn_write_tolerance(tmp_path):
    path = tmp_path / "run_ledger.jsonl"
    ledger.record_case_outcome("groq", "qwen/qwen3.8-27b", "buyer", "c1", "passed", 12.5, 3, 450, path=path)
    ledger.record_case_outcome("groq", "qwen/qwen3.8-27b", "buyer", "c2", "failed", 8.0, 2, 100,
                               failure_class="behaviour", path=path)
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"ts": "torn')  # a killed append leaves a partial line
    rows = ledger.read_ledger(path=path)
    assert [r["case_id"] for r in rows] == ["c1", "c2"]  # readable prefix survives
    assert rows[0]["outcome"] == "passed" and rows[1]["failure_class"] == "behaviour"


def test_read_ledger_on_missing_file_is_empty(tmp_path):
    assert ledger.read_ledger(path=tmp_path / "nope.jsonl") == []


# --- usage ledger + daily caps ---

def test_usage_counter_is_date_keyed_and_atomic(tmp_path):
    path = tmp_path / "usage_daily.json"
    day = date(2026, 11, 17)
    ledger.record_usage("groq", 3, path=path, today=day)
    ledger.record_usage("groq", 2, path=path, today=day)
    ledger.record_usage("groq", 5, path=path, today=date(2026, 11, 18))
    assert ledger.usage_today("groq", path=path, today=day) == 5
    assert ledger.usage_today("groq", path=path, today=date(2026, 11, 18)) == 5
    assert ledger.usage_today("unknown", path=path, today=day) == 0


def test_daily_cap_projection_uses_history_or_default(tmp_path):
    path = tmp_path / "run_ledger.jsonl"
    entry = SimpleNamespace(key="m", daily_limit=10)
    assert ledger.daily_cap_reached(entry, used=0, usage_path=tmp_path / "u.json", ledger=[]) is False
    # exactly AT the cap is still allowed (skip happens only when the case would exceed it)
    assert ledger.daily_cap_reached(entry, used=4, usage_path=tmp_path / "u.json", ledger=[]) is False
    # default avg (6 touches) plus used 5 exceeds 10
    assert ledger.daily_cap_reached(entry, used=5, usage_path=tmp_path / "u.json", ledger=[]) is True
    # history-derived avg (2) corrects the projection downward
    ledger.record_case_outcome("m", "m-id", "buyer", "c1", "passed", 1.0, 2, path=path)
    assert ledger.daily_cap_reached(entry, used=5, usage_path=tmp_path / "u.json",
                                    ledger=ledger.read_ledger(path=path)) is False
    assert ledger.daily_cap_reached(entry, used=9, usage_path=tmp_path / "u.json",
                                    ledger=ledger.read_ledger(path=path)) is True


def test_entries_without_daily_cap_never_block():
    entry = SimpleNamespace(key="m", daily_limit=None)
    assert ledger.daily_cap_reached(entry, used=99999, usage_path=None, ledger=[]) is False


# --- history summary (the drop-decision table) ---

def test_history_summary_and_format():
    rows = [
        {"ts": "t", "model_key": "groq", "model_id": "qwen/qwen3.8-27b", "persona": "buyer",
         "case_id": "a", "outcome": "passed", "duration_s": 10.0, "model_touches": 3,
         "total_tokens": 100, "failure_class": None},
        {"ts": "t", "model_key": "groq", "model_id": "qwen/qwen3.8-27b", "persona": "buyer",
         "case_id": "b", "outcome": "provider-unavailable", "duration_s": 30.0, "model_touches": 2,
         "total_tokens": 50, "failure_class": "transport"},
        {"ts": "t", "model_key": "cfw", "model_id": "@cf/zai-org/glm-4.7-flash", "persona": "buyer",
         "case_id": "a", "outcome": "daily-cap", "duration_s": 0.0, "model_touches": 0,
         "total_tokens": None, "failure_class": None},
        {"ts": "t", "model_key": "cfw", "model_id": "@cf/zai-org/glm-4.7-flash", "persona": "buyer",
         "case_id": "b", "outcome": "passed", "duration_s": 5.0, "model_touches": 4,
         "total_tokens": 200, "failure_class": None},
    ]
    summary = ledger.history_summary(ledger=rows)
    # skipped rows (provider-unavailable, daily-cap) never happened as measurements —
    # pass rate / avg duration / avg touches come from EXECUTED runs only
    assert summary["groq"]["runs"] == 2 and summary["groq"]["executed"] == 1
    assert summary["groq"]["passed"] == 1 and summary["groq"]["pass_rate"] == 1.0
    assert summary["groq"]["transport_failures"] == 1 and summary["groq"]["skipped"] == 1
    assert summary["groq"]["avg_duration_s"] == 10.0 and summary["groq"]["avg_touches"] == 3.0
    assert summary["cfw"]["skipped"] == 1 and summary["cfw"]["pass_rate"] == 1.0
    assert summary["cfw"]["avg_duration_s"] == 5.0  # the 0.0 daily-cap row does not drag it down
    text = ledger.format_history(summary)
    assert "groq" in text and "cfw" in text
    assert "100%" in text and "qwen/qwen3.8-27b" in text  # row-specific, not header-echoing


# --- runner policy integration (fake case executor; no model, no network) ---

def _stub_record(touches=2, failure=None):
    return RunRecord(
        run_id="stub-run", started_at="2026-11-17T00:00:00+00:00", ended_at="2026-11-17T00:00:01+00:00",
        model_id="t-model", prompt_version="v1", code_version="test",
        answer=None, failure_reason=failure, model_touches=touches,
    )


def _stub_answer():
    return AgentAnswer(summary="the selector is unavailable", figures=[])


@pytest.fixture()
def policy_env(tmp_path, monkeypatch):
    """Real-live path prerequisites: registry entry, gateway envs, tmp ledgers, sleep capture.

    Returns (tmp_path, sleeps, monkeypatch) — tests patch `_run_agent_case` with the
    fixture's monkeypatch (no nested patcher)."""
    monkeypatch.setattr(
        "tradeatlas.agent.model_registry.MODEL_REGISTRY",
        [ModelEntry(key="t", provider_type="openai_compat", model="t-model", route="groq",
                    rpm_limit=30, daily_limit=7)],
    )
    monkeypatch.setenv("TRADEATLAS_AGENT_MODEL", "t")
    monkeypatch.setenv("CF_ACCOUNT_ID", "acct")
    monkeypatch.setenv("CF_GATEWAY_ID", "gw")
    monkeypatch.setenv("CF_AIG_TOKEN", "tok")
    monkeypatch.delenv("TRADEATLAS_INTER_CASE_DELAY", raising=False)
    monkeypatch.setattr(ledger, "RUN_LEDGER_PATH", tmp_path / "run_ledger.jsonl")
    monkeypatch.setattr(ledger, "USAGE_PATH", tmp_path / "usage_daily.json")
    sleeps = []
    monkeypatch.setattr(runner_mod, "_sleep", lambda s: sleeps.append(s))
    return tmp_path, sleeps, monkeypatch


def _mini_suite(tmp_path, n=4):
    suite_path = tmp_path / "mini.json"
    cases = [
        {"id": f"mini-{i}", "persona": "buyer", "question": "q", "kind": "agent-abstention",
         "target": "agent", "args": {}, "expected": {"unavailability_signal": "unavailable"}}
        for i in range(n)
    ]
    suite_path.write_text(json.dumps({"version": 1, "cases": cases}), encoding="utf-8")
    return suite_path


def test_live_policy_paces_records_and_caps(tmp_path, policy_env):
    """4 cases, daily_limit 7: three execute (2 touches each), the fourth projects over the cap."""
    tmp_path, sleeps, monkeypatch = policy_env
    executions = []

    def fake_case(case, persona, mode, model_factory, traces_root, live_model=None, live_model_id=None):
        executions.append(case["id"])
        assert live_model_id == "t-model"  # records name the raw model id, not the key
        return _stub_answer(), _stub_record(touches=2), False

    monkeypatch.setattr(runner_mod, "_run_agent_case", fake_case)
    payload = run_suite("buyer", suite_path=_mini_suite(tmp_path), results_dir=tmp_path / "res",
                        mode="live", traces_dir=tmp_path / "traces", delay_seconds=0)

    by_id = {c["id"]: c for c in payload["cases"]}
    assert executions == ["mini-0", "mini-1", "mini-2"]  # three executed
    assert by_id["mini-3"]["classification"] == "daily-cap" and by_id["mini-3"]["passed"] is False
    # pacing: one sleep before each subsequent case, at the RPM floor (60/30 = 2s; delay 0)
    assert sleeps == [2.0, 2.0, 2.0]
    rows = ledger.read_ledger(path=tmp_path / "run_ledger.jsonl")
    assert [r["outcome"] for r in rows] == ["passed", "passed", "passed", "daily-cap"]
    assert ledger.usage_today("t", path=tmp_path / "usage_daily.json") == 6  # 3 × 2 touches
    assert rows[0]["model_id"] == "t-model" and rows[0]["failure_class"] is None


def test_live_policy_retries_transport_then_succeeds(tmp_path, policy_env):
    tmp_path, sleeps, monkeypatch = policy_env
    calls = {"n": 0}

    def fake_case(case, persona, mode, model_factory, traces_root, live_model=None, live_model_id=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return None, _stub_record(failure="Error code: 429 - rate limited"), False
        return _stub_answer(), _stub_record(touches=2), False

    monkeypatch.setattr(runner_mod, "_run_agent_case", fake_case)
    payload = run_suite("buyer", suite_path=_mini_suite(tmp_path, n=1), results_dir=tmp_path / "res",
                        mode="live", traces_dir=tmp_path / "traces", delay_seconds=0)

    assert calls["n"] == 2  # one retry after the transport failure
    assert sleeps == [5.0]  # linear backoff, first attempt
    assert payload["cases"][0]["passed"] is True  # the retry succeeded
    rows = ledger.read_ledger(path=tmp_path / "run_ledger.jsonl")
    assert len(rows) == 1 and rows[0]["outcome"] == "passed"  # one ledger row per case, not per attempt


def test_live_policy_marks_persistent_transport_unavailable(tmp_path, policy_env):
    tmp_path, sleeps, monkeypatch = policy_env
    calls = {"n": 0}

    def fake_case(case, persona, mode, model_factory, traces_root, live_model=None, live_model_id=None):
        calls["n"] += 1
        return None, _stub_record(failure="APIConnectionError: connection refused"), False

    monkeypatch.setattr(runner_mod, "_run_agent_case", fake_case)
    payload = run_suite("buyer", suite_path=_mini_suite(tmp_path, n=1), results_dir=tmp_path / "res",
                        mode="live", traces_dir=tmp_path / "traces", delay_seconds=0)

    assert calls["n"] == 3  # bounded: 3 attempts, no more
    assert sleeps == [5.0, 10.0]
    case = payload["cases"][0]
    assert case["classification"] == "provider-unavailable" and case["passed"] is False
    rows = ledger.read_ledger(path=tmp_path / "run_ledger.jsonl")
    assert rows[0]["outcome"] == "provider-unavailable" and rows[0]["failure_class"] == "transport"


def test_behaviour_failure_is_never_retried(tmp_path, policy_env):
    tmp_path, sleeps, monkeypatch = policy_env
    calls = {"n": 0}

    def fake_case(case, persona, mode, model_factory, traces_root, live_model=None, live_model_id=None):
        calls["n"] += 1
        return None, _stub_record(failure="ValidationError: summary Field required"), False

    monkeypatch.setattr(runner_mod, "_run_agent_case", fake_case)
    payload = run_suite("buyer", suite_path=_mini_suite(tmp_path, n=1), results_dir=tmp_path / "res",
                        mode="live", traces_dir=tmp_path / "traces", delay_seconds=0)

    assert calls["n"] == 1 and sleeps == []  # behaviour evidence: no retries, no backoff
    assert "run failed" in payload["cases"][0]["scored_value"]


def test_suite_continues_after_provider_unavailable(tmp_path, policy_env):
    """Spec scenario 'one flaky provider never kills the session': case 0 exhausts
    its transport retries, case 1 still executes and passes."""
    tmp_path, sleeps, monkeypatch = policy_env

    def fake_case(case, persona, mode, model_factory, traces_root, live_model=None, live_model_id=None):
        if case["id"] == "mini-0":
            return None, _stub_record(failure="APIConnectionError: connection refused"), False
        return _stub_answer(), _stub_record(touches=2), False

    monkeypatch.setattr(runner_mod, "_run_agent_case", fake_case)
    payload = run_suite("buyer", suite_path=_mini_suite(tmp_path, n=2), results_dir=tmp_path / "res",
                        mode="live", traces_dir=tmp_path / "traces", delay_seconds=0)

    by_id = {c["id"]: c for c in payload["cases"]}
    assert by_id["mini-0"]["classification"] == "provider-unavailable"
    assert by_id["mini-1"]["passed"] is True  # the session moved on
    # backoff sleeps for case 0's retries, then the inter-case pace before case 1
    assert sleeps == [5.0, 10.0, 2.0]
    rows = ledger.read_ledger(path=tmp_path / "run_ledger.jsonl")
    assert [r["outcome"] for r in rows] == ["provider-unavailable", "passed"]


def test_simulated_transport_failure_never_retries_or_sleeps(tmp_path, monkeypatch):
    """Simulations (model_factory set) bypass the retry/backoff policy entirely —
    a transport-looking failure scores 'run failed' with no real sleeps."""
    sleeps = []
    monkeypatch.setattr(runner_mod, "_sleep", lambda s: sleeps.append(s))
    monkeypatch.setattr(ledger, "RUN_LEDGER_PATH", tmp_path / "run_ledger.jsonl")
    monkeypatch.setattr(ledger, "USAGE_PATH", tmp_path / "usage_daily.json")
    calls = {"n": 0}

    def fake_case(case, persona, mode, model_factory, traces_root, live_model=None, live_model_id=None):
        calls["n"] += 1
        return None, _stub_record(failure="Error code: 429 - rate limited"), False

    monkeypatch.setattr(runner_mod, "_run_agent_case", fake_case)
    payload = run_suite("buyer", suite_path=_mini_suite(tmp_path, n=1), results_dir=tmp_path / "res",
                        mode="live", model_factory=lambda: None, traces_dir=tmp_path / "traces",
                        delay_seconds=0)

    assert calls["n"] == 1 and sleeps == []  # no retry, no real backoff
    assert "run failed" in payload["cases"][0]["scored_value"]  # not classified provider-unavailable
    assert not (tmp_path / "run_ledger.jsonl").exists()  # simulations write no ledger rows


def test_replay_mode_writes_nothing_to_the_ledger(tmp_path, monkeypatch):
    """Tripwire: replay verification is CI-only — it must never touch the benchmark evidence."""
    ledger_path, usage_path = tmp_path / "run_ledger.jsonl", tmp_path / "usage_daily.json"
    monkeypatch.setattr(ledger, "RUN_LEDGER_PATH", ledger_path)
    monkeypatch.setattr(ledger, "USAGE_PATH", usage_path)
    fixture_trace = {
        "version": 1, "question": "q",
        "model_messages": [
            {"role": "ai", "content": "done.", "tool_calls": [], "usage_metadata": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}},
        ],
        "structured_response": {"summary": "unavailable for Punjab", "figures": []},
    }
    traces_dir = tmp_path / "traces" / "buyer"
    traces_dir.mkdir(parents=True)
    (traces_dir / "mini.json").write_text(json.dumps(fixture_trace), encoding="utf-8")
    suite_path = tmp_path / "mini.json"
    suite_path.write_text(json.dumps({"version": 1, "cases": [
        {"id": "mini-replay", "persona": "buyer", "question": "q", "kind": "agent-abstention",
         "target": "agent", "args": {}, "trace": "mini.json",
         "expected": {"unavailability_signal": "unavailable"}}
    ]}), encoding="utf-8")
    payload = run_suite("buyer", suite_path=suite_path, results_dir=tmp_path / "res",
                        mode="replay", traces_dir=tmp_path / "traces")
    assert payload["cases"][0]["passed"] is True
    assert not ledger_path.exists() and not usage_path.exists()


def test_case_ids_filter_and_cli_flags(tmp_path, monkeypatch, capsys):
    """--case-ids exposes the resume filter; --history prints the ledger table."""
    monkeypatch.setattr(ledger, "RUN_LEDGER_PATH", tmp_path / "run_ledger.jsonl")
    monkeypatch.setattr(ledger, "USAGE_PATH", tmp_path / "usage_daily.json")
    captured = {}

    def fake_run_suite(persona, mode="replay", case_ids=None, delay_seconds=None):
        captured["persona"], captured["case_ids"] = persona, case_ids
        return {"missing_traces": [], "cases": [], "passed": 0, "total": 0, "mode": mode}

    monkeypatch.setattr(runner_mod, "run_suite", fake_run_suite)
    monkeypatch.setattr("sys.argv", ["runner", "buyer", "--case-ids", " a , b ,"])
    assert runner_mod.main() == 0
    assert captured["persona"] == "buyer" and captured["case_ids"] == ["a", "b"]

    monkeypatch.setattr("sys.argv", ["runner", "--history"])
    assert runner_mod.main() == 0
    assert "model_key" in capsys.readouterr().out


def test_run_suite_case_ids_runs_only_named_cases(tmp_path, monkeypatch, isolated_cache):
    """The resume filter executes exactly the named cases; the rest stay validated but unrun."""
    real_args = {"state": "Gujarat", "target_period": "Before November 2025",
                 "months_ahead": 1, "metric": "mae", "method": "Last observed"}
    suite_path = tmp_path / "mini.json"
    suite_path.write_text(json.dumps({"version": 1, "cases": [
        {"id": "case-a", "persona": "analyst", "question": "q", "kind": "numeric-exact",
         "target": "forecast_group", "args": real_args, "expected": 191.55},
        {"id": "case-b", "persona": "analyst", "question": "q", "kind": "numeric-exact",
         "target": "forecast_group", "args": real_args, "expected": 191.55},
    ]}), encoding="utf-8")
    payload = run_suite("analyst", suite_path=suite_path, results_dir=tmp_path / "res",
                        mode="replay", case_ids=["case-b"])
    assert [c["id"] for c in payload["cases"]] == ["case-b"] and payload["total"] == 1
    assert payload["cases"][0]["passed"] is True  # the real resolver ran for the named case only


def test_simulated_runs_write_nothing_to_the_ledger(tmp_path, monkeypatch):
    """Simulations (model_factory) bypass ledger/usage — they must not pollute benchmark evidence."""
    ledger_path, usage_path = tmp_path / "run_ledger.jsonl", tmp_path / "usage_daily.json"
    monkeypatch.setattr(ledger, "RUN_LEDGER_PATH", ledger_path)
    monkeypatch.setattr(ledger, "USAGE_PATH", usage_path)
    sleeps = []
    monkeypatch.setattr(runner_mod, "_sleep", lambda s: sleeps.append(s))
    from tradeatlas.agent.replay import scripted_model

    trace = {
        "version": 1, "question": "q",
        "model_messages": [
            {"role": "ai", "content": "", "tool_calls": [{"name": "check_series_coverage", "args": {"state": "Rajasthan", "commodity": "Groundnut"}, "id": "c1", "type": "tool_call"}], "usage_metadata": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15}},
            {"role": "ai", "content": "done.", "tool_calls": [], "usage_metadata": {"input_tokens": 20, "output_tokens": 5, "total_tokens": 25}},
        ],
        "structured_response": {"summary": "unavailable for Punjab", "figures": []},
    }
    suite_path = tmp_path / "mini.json"
    suite_path.write_text(json.dumps({"version": 1, "cases": [
        {"id": "mini-sim", "persona": "buyer", "question": "q", "kind": "agent-abstention",
         "target": "agent", "args": {}, "expected": {"unavailability_signal": "unavailable"}}
    ]}), encoding="utf-8")
    payload = run_suite("buyer", suite_path=suite_path, results_dir=tmp_path / "res", mode="live",
                        model_factory=lambda: scripted_model(trace), traces_dir=tmp_path / "traces",
                        delay_seconds=0)
    assert payload["cases"][0]["passed"] is True
    assert not ledger_path.exists() and not usage_path.exists()
    assert sleeps == []  # simulations never pace

# --- statistical intervals (the uncertainty layer) ---

def test_wilson_known_bounds():
    lo, hi = ledger.wilson_interval(8, 10)
    assert abs(lo - 0.4903) < 1e-3 and abs(hi - 0.9434) < 1e-3  # closed-form check
    lo3, hi3 = ledger.wilson_interval(3, 3)
    assert lo3 == pytest.approx(0.4386, abs=1e-3) and hi3 == 1.0  # 3/3 shows honest wide bounds
    lo0, hi0 = ledger.wilson_interval(0, 5)
    assert 0.0 <= lo0 <= 0.01 and hi0 < 0.491  # 0/5: lower edge, upper below half
    assert ledger.wilson_interval(5, 0) is None


def test_bootstrap_interval_is_deterministic_and_bounded():
    flags = [True] * 8 + [False] * 2
    a = ledger.bootstrap_interval(flags)
    b = ledger.bootstrap_interval(flags)
    assert a == b  # seeded: eval evidence must be reproducible
    lo, hi = a
    assert 0.0 <= lo <= 0.8 <= hi <= 1.0
    assert ledger.bootstrap_interval([]) is None


def test_history_summary_carries_ci95():
    rows = [
        {"ts": "t", "model_key": "m", "model_id": "m-id", "persona": "buyer", "case_id": "a",
         "outcome": "passed", "duration_s": 1.0, "model_touches": 2, "total_tokens": 1, "failure_class": None},
        {"ts": "t", "model_key": "m", "model_id": "m-id", "persona": "buyer", "case_id": "b",
         "outcome": "failed", "duration_s": 2.0, "model_touches": 3, "total_tokens": 1, "failure_class": None},
        {"ts": "t", "model_key": "m", "model_id": "m-id", "persona": "buyer", "case_id": "c",
         "outcome": "daily-cap", "duration_s": 0.0, "model_touches": 0, "total_tokens": None, "failure_class": None},
    ]
    summary = ledger.history_summary(ledger=rows)
    wilson = summary["m"]["ci95"]["wilson"]
    assert wilson[0] <= summary["m"]["pass_rate"] <= wilson[1]  # the point estimate sits inside the interval
    text = ledger.format_history(summary)
    assert "ci95" in text and f"{wilson[0]:.2f}-{wilson[1]:.2f}" in text

def test_history_summary_dedupes_rerun_rows():
    """A re-run appends rows for the same case; the summary counts the LATEST outcome once."""
    def row(case_id, outcome, ts):
        return {"ts": ts, "model_key": "m", "model_id": "m-id", "persona": "buyer",
                "case_id": case_id, "outcome": outcome, "duration_s": 1.0, "model_touches": 2,
                "total_tokens": 1, "failure_class": None}
    rows = [row("a", "failed", "t1"), row("a", "passed", "t2"), row("b", "failed", "t3")]
    summary = ledger.history_summary(ledger=rows)
    assert summary["m"]["runs"] == 2 and summary["m"]["executed"] == 2  # 2 cases, not 3 rows
    assert summary["m"]["passed"] == 1  # case a's latest outcome (passed) counted, not both

