"""Run + usage ledgers: persisted evidence for per-model drop decisions.

The run ledger is append-only JSONL (one line per live case: outcome
classification, wall duration, model touches, tokens) — a mid-run kill leaves
the completed lines readable, unlike a whole-file results JSON. The usage
ledger is a date-keyed request counter per model (local date) that drives the
runner's daily-cap projection. Both live in evals/results/ (git-ignored):
runs are reproducible from suite + code, but these are the operator's
measurement record — the input for deciding which model to drop next run.
The drop decision stays human; nothing here auto-disables a model.
"""

import json
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from tradeatlas.models import utc_now_iso

EVALS_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EVALS_DIR / "results"
RUN_LEDGER_PATH = RESULTS_DIR / "run_ledger.jsonl"
USAGE_PATH = RESULTS_DIR / "usage_daily.json"

# When a model has no ledger history yet, assume a react-loop case costs this
# many model requests (loop turns + the structured-response call).
DEFAULT_AVG_TOUCHES = 6

_TRANSPORT_SIGNATURES = ("429", "ratelimit", "rate limit", "quota", "timeout", "timed out", "connection", "503", "502", "504", "overloaded")


def classify_failure(failure_reason: Optional[str]) -> Optional[str]:
    """Transport-class vs model-behaviour failure, from the recorded reason text.

    Transport failures (rate limit, quota, timeout, connection) are retryable
    infrastructure events; behaviour failures (schema-validated misbehaviour)
    are evidence about the model and are never retried. Pydantic validation
    errors are always behaviour — their text embeds the invalid payload, whose
    repr can legitimately mention "timeout"/"connection"/"429". Unknown text
    classifies as behaviour (only known transport signatures trigger retries).
    """
    if not failure_reason:
        return None
    prefix = failure_reason.split(":", 1)[0].strip().lower()
    if "validationerror" in prefix or "pydantic" in prefix:
        return "behaviour"
    lowered = failure_reason.lower()
    if any(sig in lowered for sig in _TRANSPORT_SIGNATURES):
        return "transport"
    return "behaviour"


def record_case_outcome(
    model_key: str,
    model_id: str,
    persona: str,
    case_id: str,
    outcome: str,
    duration_s: float,
    model_touches: int,
    total_tokens: Optional[int] = None,
    failure_class: Optional[str] = None,
    path: Optional[Path] = None,
) -> None:
    """Append one JSONL line for a completed live case (crash-safe by design)."""
    ledger_path = Path(path) if path is not None else RUN_LEDGER_PATH
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": utc_now_iso(),
        "model_key": model_key,
        "model_id": model_id,
        "persona": persona,
        "case_id": case_id,
        "outcome": outcome,
        "duration_s": round(duration_s, 2),
        "model_touches": model_touches,
        "total_tokens": total_tokens,
        "failure_class": failure_class,
    }
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())


def read_ledger(path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """All ledger rows, tolerating a partial trailing line (a killed append)."""
    ledger_path = Path(path) if path is not None else RUN_LEDGER_PATH
    if not ledger_path.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    for line in ledger_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # torn write from a mid-run kill — keep the readable prefix
    return rows


def usage_today(model_key: str, path: Optional[Path] = None, today: Optional[date] = None) -> int:
    """Requests recorded today (local date) for one model key."""
    usage_path = Path(path) if path is not None else USAGE_PATH
    if not usage_path.is_file():
        return 0
    data = json.loads(usage_path.read_text(encoding="utf-8"))
    return int(data.get(model_key, {}).get((today or date.today()).isoformat(), 0))


def record_usage(model_key: str, touches: int, path: Optional[Path] = None, today: Optional[date] = None) -> None:
    """Add one run's model requests to the date-keyed counter (atomic rewrite)."""
    usage_path = Path(path) if path is not None else USAGE_PATH
    usage_path.parent.mkdir(parents=True, exist_ok=True)
    data: Dict[str, Dict[str, int]] = {}
    if usage_path.is_file():
        data = json.loads(usage_path.read_text(encoding="utf-8"))
    day = (today or date.today()).isoformat()
    bucket = data.setdefault(model_key, {})
    bucket[day] = int(bucket.get(day, 0)) + int(touches)
    handle, tmp_name = tempfile.mkstemp(dir=str(usage_path.parent), suffix=".tmp")
    os.close(handle)  # Windows: an open handle blocks the replace below
    tmp_path = Path(tmp_name)
    try:
        tmp_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        tmp_path.replace(usage_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def avg_touches(model_key: str, ledger: Optional[List[Dict[str, Any]]] = None) -> float:
    """Mean model requests per case from ledger history (default when unproved)."""
    rows = ledger if ledger is not None else read_ledger()
    touches = [r["model_touches"] for r in rows if r.get("model_key") == model_key and r.get("model_touches")]
    if not touches:
        return float(DEFAULT_AVG_TOUCHES)
    return sum(touches) / len(touches)


def daily_cap_reached(
    entry: Any,
    used: Optional[int] = None,
    projected_touches: Optional[float] = None,
    usage_path: Optional[Path] = None,
    ledger: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    """True when the next case would plausibly exceed the entry's daily cap.

    Projection: requests used today plus the model's average touches per case
    (history-derived, default when unproved). An honest approximation — the
    correction lands post-case from the record's actual model_touches — not a
    guarantee against provider-side counters.
    """
    if entry.daily_limit is None:
        return False
    used_today = usage_today(entry.key, path=usage_path) if used is None else used
    per_case = projected_touches if projected_touches is not None else avg_touches(entry.key, ledger=ledger)
    return used_today + per_case > entry.daily_limit


def history_summary(ledger: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Dict[str, Any]]:
    """Per-model evidence table from the run ledger (the drop-decision input).

    `runs` counts every ledger row; `pass_rate` and `avg_duration_s` are computed
    over EXECUTED runs only — skipped rows (daily-cap, provider-unavailable) never
    happened as model measurements, so counting them would skew the evidence.
    """
    rows = ledger if ledger is not None else read_ledger()
    summary: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        bucket = summary.setdefault(
            row.get("model_key", "?"),
            {"model_id": row.get("model_id"), "runs": 0, "executed": 0, "passed": 0, "durations": [],
             "touches": [], "transport_failures": 0, "skipped": 0},
        )
        bucket["runs"] += 1
        if row.get("failure_class") == "transport":
            bucket["transport_failures"] += 1  # transport events count even when they skip the case
        if row.get("outcome") in {"daily-cap", "provider-unavailable"}:
            bucket["skipped"] += 1
            continue
        bucket["executed"] += 1
        if row.get("outcome") == "passed":
            bucket["passed"] += 1
        if row.get("duration_s") is not None:
            bucket["durations"].append(row["duration_s"])
        if row.get("model_touches"):
            bucket["touches"].append(row["model_touches"])
    for bucket in summary.values():
        durations = bucket.pop("durations")
        touches = bucket.pop("touches")
        executed = bucket["executed"]
        bucket["pass_rate"] = round(bucket["passed"] / executed, 2) if executed else None
        bucket["avg_duration_s"] = round(sum(durations) / len(durations), 1) if durations else None
        bucket["avg_touches"] = round(sum(touches) / len(touches), 1) if touches else None
    return summary


def format_history(summary: Optional[Dict[str, Dict[str, Any]]] = None) -> str:
    """The evidence table as text: model, runs, pass rate, avg duration, avg touches, transport failures."""
    data = summary if summary is not None else history_summary()
    header = f"{'model_key':<26} {'model_id':<36} {'runs':>4} {'pass':>6} {'avg_s':>7} {'touches':>8} {'transport':>9} {'skipped':>8}"
    lines = [header, "-" * len(header)]
    for key in sorted(data):
        b = data[key]
        pass_text = f"{b['pass_rate']:.0%}" if b["pass_rate"] is not None else "-"
        lines.append(
            f"{key:<26} {str(b['model_id']):<36} {b['runs']:>4} {pass_text:>6} "
            f"{str(b['avg_duration_s']):>7} {str(b['avg_touches']):>8} {b['transport_failures']:>9} {b['skipped']:>8}"
        )
    if not data:
        lines.append("(no ledger rows yet — live benchmark runs append here)")
    return "\n".join(lines)
