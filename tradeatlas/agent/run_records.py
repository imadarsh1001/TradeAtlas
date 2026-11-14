"""Run records: one JSON record per agent run — telemetry, provenance, and outcome.

Written for every run under evals/runs/ (git-ignored): successful runs carry the
structured answer, failed runs carry the failure reason. Code version follows the
evals/runner.py convention (git short SHA, 'unknown' outside a checkout).
"""

import json
import subprocess
import uuid
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from langchain_core.messages import ToolMessage
from pydantic import BaseModel, Field

from tradeatlas.models import utc_now_iso

if TYPE_CHECKING:  # tools imports services; the recorder type is only needed for annotations
    from tradeatlas.agent.tools import ToolCallRecorder

ROOT_DIR = Path(__file__).resolve().parents[2]
RUNS_DIR = ROOT_DIR / "evals" / "runs"


class TokenUsage(BaseModel):
    """Token counts as reported by the model's usage metadata."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ToolCallRecord(BaseModel):
    """One tool invocation: executed calls carry latency; schema-rejected ones carry the error."""

    tool: str
    arguments: Dict[str, Any]
    attempt_index: int  # 1-based ordinal across the run
    latency_ms: Optional[float] = None
    error: Optional[str] = None


class RunRecord(BaseModel):
    """Everything a benchmark or review needs to know about one agent run."""

    run_id: str
    started_at: str
    ended_at: str
    model_id: str
    prompt_version: str
    code_version: str
    answer: Optional[Dict[str, Any]] = None
    failure_reason: Optional[str] = None
    tool_calls: List[ToolCallRecord] = Field(default_factory=list)
    token_usage: Optional[TokenUsage] = None


def code_version() -> str:
    """Short git SHA of the current checkout ('unknown' outside a repo)."""
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


def sum_token_usage(messages: List[Any]) -> Optional[TokenUsage]:
    """Sum usage_metadata across the run's model messages; None when the model reports none."""
    prompt = completion = total = 0
    seen = False
    for message in messages:
        usage = getattr(message, "usage_metadata", None)
        if not usage:
            continue
        seen = True
        prompt += int(usage.get("input_tokens", 0))
        completion += int(usage.get("output_tokens", 0))
        total += int(usage.get("total_tokens", 0))
    return TokenUsage(prompt_tokens=prompt, completion_tokens=completion, total_tokens=total) if seen else None


def build_tool_call_records(messages: List[Any], recorder: Any) -> List[ToolCallRecord]:
    """Merge the recorder's executed calls with the run's message history.

    Every tool call the model attempted gets one record in invocation order
    (attempt_index from 1). Executed calls pair with recorder entries by
    (tool name, schema-canonical arguments): langchain-core fills defaults and
    coerces types before invoking, so raw model args and function kwargs can
    differ — both sides reduce to the canonical form (``canonical_tool_args``),
    and a schema-rejected call has no canonical form at all. Calls with no
    matching recorder entry never reached a service function: schema-rejected,
    carrying the validation error from the matching tool message and no latency.

    Recorder entries left unpaired after the walk still executed — the transcript
    can be lost when the run fails mid-flight — so they are appended in execution
    order with continuing attempt indices (spec: every tool call made during the
    run appears in the record, on every path).
    """
    from tradeatlas.agent.tools import canonical_tool_args  # deferred: keeps run_records import-light

    pending: Dict[str, deque] = {}
    for entry in recorder.executed:
        canonical = canonical_tool_args(entry["tool"], entry["arguments"])
        key = (entry["tool"], json.dumps(canonical, sort_keys=True)) if canonical else None
        if key is None:
            continue
        pending.setdefault(key, deque()).append(entry)

    records: List[ToolCallRecord] = []
    attempt = 0
    for message in messages:
        for call in getattr(message, "tool_calls", None) or []:
            attempt += 1
            name = call["name"]
            canonical = canonical_tool_args(name, call["args"])
            queue = pending.get((name, json.dumps(canonical, sort_keys=True))) if canonical else None
            if queue:
                entry = queue.popleft()
                records.append(
                    ToolCallRecord(
                        tool=name,
                        arguments=call["args"],
                        attempt_index=attempt,
                        latency_ms=entry["latency_ms"],
                        error=entry["error"],
                    )
                )
            else:
                records.append(
                    ToolCallRecord(
                        tool=name,
                        arguments=call["args"],
                        attempt_index=attempt,
                        latency_ms=None,
                        error=_tool_message_error(messages, call.get("id")),
                    )
                )
    for pending_queues in pending.values():
        for entry in pending_queues:
            attempt += 1
            records.append(
                ToolCallRecord(
                    tool=entry["tool"],
                    arguments=entry["arguments"],
                    attempt_index=attempt,
                    latency_ms=entry["latency_ms"],
                    error=entry["error"],
                )
            )
    return records


def _tool_message_error(messages: List[Any], tool_call_id: Optional[str]) -> Optional[str]:
    """The error text of the tool message answering this call id, if it reports one."""
    if not tool_call_id:
        return None
    for message in messages:
        if not isinstance(message, ToolMessage) or message.tool_call_id != tool_call_id:
            continue
        content = message.content if isinstance(message.content, str) else str(message.content)
        if message.status == "error" or content.startswith("Error:"):
            return content
    return None


def write_run_record(record: RunRecord, runs_dir: Optional[Path] = None) -> Path:
    """Persist one run record as JSON; return the written path."""
    directory = Path(runs_dir) if runs_dir is not None else RUNS_DIR
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{record.run_id}.json"
    path.write_text(json.dumps(record.model_dump(mode="json"), indent=2), encoding="utf-8")
    return path


def new_run_id() -> str:
    """Fresh run identifier."""
    return uuid.uuid4().hex
