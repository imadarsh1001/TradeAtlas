"""Golden-eval runner: executable cases bound to registered resolvers, scored per kind.

Suite: evals/golden/<persona>.json = {"version": 1, "cases": [...]}; case fields:
id, persona, question, kind (numeric-exact | evidence-fidelity | abstention),
target (a registered resolver), args (selector arguments), expected (rubric value).
Results: evals/results/<persona>.json (git-ignored — reproducible from suite + code).
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List

from tradeatlas.models import EvidenceEnvelope

REQUIRED_FIELDS = ["id", "persona", "question", "kind", "target", "args", "expected"]
KINDS = {"numeric-exact", "evidence-fidelity", "abstention"}
EVALS_DIR = Path(__file__).resolve().parent

_report_cache: Dict[str, Any] = {}


def _code_version() -> str:
    """Short git SHA of the current checkout ('unknown' outside a repo)."""
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


def _cached_report() -> Dict[str, Any]:
    if "report" not in _report_cache:
        from tradeatlas.forecasting import build_report
        _report_cache["report"] = build_report()
    return _report_cache["report"]


def _anomaly_envelope(state: str, commodity: str) -> EvidenceEnvelope:
    from tradeatlas.analytics import detect_price_anomalies
    return detect_price_anomalies(state, commodity)


def _coverage_envelope(state: str, commodity: str) -> EvidenceEnvelope:
    from tradeatlas.analytics import check_series_coverage
    return check_series_coverage(state, commodity)


def forecast_group(args: Dict[str, Any]) -> Any:
    """Numeric resolver: an MAE/MASE/q value for one state × period × horizon group."""
    for group in _cached_report()["groups"]:
        if (
            group["state"] == args["state"]
            and group["target_period"] == args["target_period"]
            and group["months_ahead"] == args["months_ahead"]
        ):
            metric = group[args["metric"]]
            return metric[args["method"]] if "method" in args else metric
    raise KeyError(f"No forecast group for {args}")


def _envelope_resolver(fetch):
    """Envelope resolver factory: full envelope, or one named field via args['field']."""

    def resolve(args: Dict[str, Any]) -> Any:
        envelope = fetch(args["state"], args["commodity"])
        field = args.get("field")
        if field is None:
            return envelope
        return getattr(envelope, field) if hasattr(envelope, field) else envelope.payload.get(field)

    return resolve


RESOLVERS: Dict[str, Callable[[Dict[str, Any]], Any]] = {
    "forecast_group": forecast_group,
    "anomaly_result": _envelope_resolver(
        lambda state, commodity: _anomaly_envelope(state, commodity)
    ),
    "coverage_report": _envelope_resolver(
        lambda state, commodity: _coverage_envelope(state, commodity)
    ),
}


def _score_numeric(value: Any, expected: Any) -> Dict[str, Any]:
    scored = round(float(value), 2)
    return {"passed": scored == round(float(expected), 2), "scored_value": scored}


def _score_evidence_fidelity(envelope: EvidenceEnvelope, expected: Dict[str, Any]) -> Dict[str, Any]:
    failures: List[str] = []
    if "tier" in expected and envelope.tier != expected["tier"]:
        failures.append(f"tier={envelope.tier} != {expected['tier']}")
    if "no_data" in expected and envelope.no_data != expected["no_data"]:
        failures.append(f"no_data={envelope.no_data}")
    for substring in expected.get("caveat_contains", []):
        if not any(substring in c for c in envelope.caveats):
            failures.append(f"caveat missing {substring!r}")
    for key in expected.get("payload_has", []):
        if key not in envelope.payload:
            failures.append(f"payload missing {key!r}")
    return {"passed": not failures, "scored_value": failures or "all assertions held"}


def _score_abstention(envelope: EvidenceEnvelope, args: Dict[str, Any]) -> Dict[str, Any]:
    selector = args.get("selector", "")
    named = selector and selector in json.dumps(envelope.payload, default=str)
    passed = bool(envelope.no_data and named)
    return {"passed": passed, "scored_value": {"no_data": envelope.no_data, "selector_found": bool(named)}}


def run_suite(persona: str, suite_path: str = None, results_dir: str = None) -> Dict[str, Any]:
    """Execute one golden suite and write results; raises on malformed cases."""
    suite_file = Path(suite_path) if suite_path else EVALS_DIR / "golden" / f"{persona}.json"
    out_dir = Path(results_dir) if results_dir else EVALS_DIR / "results"

    suite = json.loads(suite_file.read_text(encoding="utf-8"))
    if suite.get("version") != 1 or not isinstance(suite.get("cases"), list):
        raise ValueError(f"{suite_file}: expected top-level {{'version': 1, 'cases': [...]}}")

    results: List[Dict[str, Any]] = []
    seen_ids = set()
    for case in suite["cases"]:
        missing = [f for f in REQUIRED_FIELDS if f not in case or case[f] in (None, "")]
        if missing:
            raise ValueError(f"Case '{case.get('id', '?')}': missing fields {missing}")
        if case["id"] in seen_ids:
            raise ValueError(f"Case '{case['id']}': duplicate case id")
        seen_ids.add(case["id"])
        if case["kind"] not in KINDS:
            raise ValueError(f"Case '{case['id']}': unknown kind '{case['kind']}'")
        resolver = RESOLVERS.get(case["target"])
        if resolver is None:
            raise ValueError(f"Case '{case['id']}': unknown target '{case['target']}'")

        value = resolver(case["args"])
        if case["kind"] == "numeric-exact":
            outcome = _score_numeric(value, case["expected"])
        elif case["kind"] == "evidence-fidelity":
            outcome = _score_evidence_fidelity(value, case["expected"])
        else:
            outcome = _score_abstention(value, case["args"])
        results.append({"id": case["id"], "kind": case["kind"], **outcome, "expected": case["expected"]})

    payload = {
        "persona": persona,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "code_version": _code_version(),
        "passed": sum(1 for r in results if r["passed"]),
        "total": len(results),
        "cases": results,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{persona}.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a golden eval suite")
    parser.add_argument("persona", help="Suite persona, e.g. analyst")
    args = parser.parse_args()
    payload = run_suite(args.persona)
    for case in payload["cases"]:
        if not case["passed"]:
            print(f"FAILED: {case['id']} ({case['kind']}) scored={case['scored_value']} expected={case['expected']}")
    print(f"{payload['passed']}/{payload['total']} cases passed ({args.persona})")
    return 0 if payload["passed"] == payload["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
