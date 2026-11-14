"""Run-record mechanics: attempt merge, token summation, writer, git-ignore (tasks 4.1-4.3)."""

import json
import subprocess
from pathlib import Path

from langchain_core.messages import AIMessage, ToolMessage

from tradeatlas.agent.run_records import (
    RUNS_DIR,
    RunRecord,
    build_tool_call_records,
    code_version,
    new_run_id,
    sum_token_usage,
    write_run_record,
)
from tradeatlas.agent.tools import ToolCallRecorder

ROOT = Path(__file__).resolve().parent.parent


def _ai(tool_calls=None, usage=None):
    kwargs = {"content": ""}
    if tool_calls is not None:
        kwargs["tool_calls"] = tool_calls
    if usage is not None:
        kwargs["usage_metadata"] = usage
    return AIMessage(**kwargs)


def _recorder_with(entries):
    recorder = ToolCallRecorder()
    for tool, args, latency, error in entries:
        recorder.record_executed(tool, args, latency, error)
    return recorder


def test_attempt_indices_pair_by_name_and_exact_arguments():
    recorder = _recorder_with([
        ("check_series_coverage", {"state": "Rajasthan", "commodity": "Groundnut"}, 12.5, None),
        ("detect_price_anomalies", {"state": "Gujarat", "commodity": "Groundnut"}, 30.0, None),
    ])
    calls = {
        "c1": {"name": "check_series_coverage", "args": {"commodity": "Groundnut"}, "id": "c1"},  # rejected
        "c2": {"name": "check_series_coverage", "args": {"state": "Rajasthan", "commodity": "Groundnut"}, "id": "c2"},
        "c3": {"name": "detect_price_anomalies", "args": {"state": "Gujarat", "commodity": "Groundnut"}, "id": "c3"},
    }
    messages = [
        _ai([calls["c1"]]),
        ToolMessage(content="Error invoking tool with error:\n state: Field required", tool_call_id="c1", status="error"),
        _ai([calls["c2"], calls["c3"]]),
        ToolMessage(content="{}", tool_call_id="c2"),
        ToolMessage(content="{}", tool_call_id="c3"),
    ]
    records = build_tool_call_records(messages, recorder)
    assert [r.attempt_index for r in records] == [1, 2, 3]
    rejected = records[0]
    assert rejected.latency_ms is None and "state" in rejected.error and rejected.tool == "check_series_coverage"
    assert records[1].latency_ms == 12.5 and records[1].error is None
    assert records[2].latency_ms == 30.0
    assert records[0].arguments == calls["c1"]["args"]
    assert records[1].arguments == calls["c2"]["args"]
    assert records[2].arguments == calls["c3"]["args"]


def test_repeated_identical_calls_pair_fifo():
    recorder = _recorder_with([
        ("check_series_coverage", {"state": "Gujarat", "commodity": "Groundnut"}, 1.0, None),
        ("check_series_coverage", {"state": "Gujarat", "commodity": "Groundnut"}, 2.0, None),
    ])
    same = {"name": "check_series_coverage", "args": {"state": "Gujarat", "commodity": "Groundnut"}}
    messages = [_ai([{**same, "id": "a"}]), ToolMessage(content="{}", tool_call_id="a"),
                _ai([{**same, "id": "b"}]), ToolMessage(content="{}", tool_call_id="b")]
    records = build_tool_call_records(messages, recorder)
    assert [r.latency_ms for r in records] == [1.0, 2.0]


def test_pairing_survives_schema_default_filling_and_coercion():
    # The model emits minimal args with an int; langchain-core fills defaults and
    # coerces to float before the function runs — canonical pairing (not raw-args
    # JSON equality) must still match the recorder entry, else an executed call
    # records as latency-less (the review's reproduced defect).
    recorder = _recorder_with([(
        "calculate_delivered_cost",
        {"commodity": "Groundnut", "base_price_rs_qtl": 5000.0, "freight_per_tonne": 900.0,
         "ancillary_per_tonne": 0.0, "order_tonnes": 100.0, "is_pod": False,
         "decortication_allowance_tonne": 1500.0},
        7.5, None,
    )])
    messages = [
        _ai([{"name": "calculate_delivered_cost",
              "args": {"commodity": "Groundnut", "base_price_rs_qtl": 5000, "freight_per_tonne": 900},
              "id": "c1"}]),
        ToolMessage(content="{}", tool_call_id="c1"),
    ]
    (record,) = build_tool_call_records(messages, recorder)
    assert record.latency_ms == 7.5 and record.error is None  # executed, not misclassified


def test_unpaired_recorder_entries_survive_transcript_loss():
    # Mid-run failure can lose the transcript; every tool call that executed must
    # still reach the record (spec: every tool call made during the run).
    recorder = _recorder_with([("detect_price_anomalies", {"state": "Gujarat", "commodity": "Groundnut"}, 42.0, None)])
    records = build_tool_call_records([], recorder)
    assert [(r.tool, r.attempt_index, r.latency_ms) for r in records] == [
        ("detect_price_anomalies", 1, 42.0),
    ]


def test_token_usage_sums_and_reports_absence():
    messages = [
        _ai(usage={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}),
        _ai(usage={"input_tokens": 50, "output_tokens": 30, "total_tokens": 80}),
    ]
    usage = sum_token_usage(messages)
    assert (usage.prompt_tokens, usage.completion_tokens, usage.total_tokens) == (150, 50, 200)
    assert sum_token_usage([_ai(), _ai()]) is None


def test_code_version_matches_git_short_sha():
    expected = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT, check=True
    ).stdout.strip()
    assert code_version() == expected


def _sample_record(**overrides) -> RunRecord:
    base = dict(
        run_id=new_run_id(),
        started_at="2026-11-14T00:00:00+00:00",
        ended_at="2026-11-14T00:00:01+00:00",
        model_id="scripted-fixture",
        prompt_version="v1",
        code_version="test123",
        answer={"summary": "s", "figures": []},
        failure_reason=None,
    )
    base.update(overrides)
    return RunRecord(**base)


def test_writer_round_trips_a_record(tmp_path):
    path = write_run_record(_sample_record(), tmp_path)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["model_id"] == "scripted-fixture" and loaded["prompt_version"] == "v1"
    assert loaded["started_at"].endswith("+00:00")  # UTC timestamps


def test_runs_dir_is_git_ignored():
    probe = subprocess.run(
        ["git", "check-ignore", "-q", str(RUNS_DIR.relative_to(ROOT) / "probe.json")],
        cwd=ROOT,
    )
    assert probe.returncode == 0, f"{RUNS_DIR} is not git-ignored"
