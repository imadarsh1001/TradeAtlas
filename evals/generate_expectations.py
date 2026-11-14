"""Regenerate numeric-exact expectations in a golden suite from the current code.

Checked-in by design: numeric expectations are a regression signal, so a data
refresh or intentional computation change regenerates them IN THE SAME CHANGE
(with manifest updates), keeping the suite's drift detection honest.
"""

import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evals.runner import REQUIRED_FIELDS, RESOLVERS, isolated_cache  # noqa: E402

GOLDEN = Path(__file__).resolve().parent / "golden"
TESTS_FIXTURES = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
EVALS_FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _fixture_transport(directory: Path, name: str) -> httpx.MockTransport:
    """Serve a committed fixture (the benchmark's data seam)."""
    payload = json.loads((directory / name).read_text(encoding="utf-8"))
    return httpx.MockTransport(lambda request: httpx.Response(200, json=payload))


# Agent numeric expectations derive from the deterministic functions against the
# committed fixtures — same source of truth as the resolver suites. The scorer
# compares the agent's answer figure to the CHECKED-IN literal these write.
def _daily_gujarat_modal() -> float:
    from tradeatlas.ingest import fetch_daily_mandi_prices

    with isolated_cache():
        envelope = fetch_daily_mandi_prices(
            state="Gujarat", commodity="Groundnut",
            transport=_fixture_transport(TESTS_FIXTURES, "datagov_gujarat_groundnut.json"),
        )
    return float(envelope.payload[0]["modal_price"])


def _hub_rajkot_msp_spread() -> float:
    from tradeatlas.ingest import fetch_benchmark_hub_summary

    with isolated_cache():
        envelope = fetch_benchmark_hub_summary(
            state="Gujarat", commodity="Groundnut",
            transport=_fixture_transport(EVALS_FIXTURES, "datagov_hub_rajkot_groundnut.json"),
        )
    rajkot = next(h for h in envelope.payload["hub_details"] if "rajkot" in h["market"].lower())
    return float(rajkot["msp_spread"])


def _delivered_cost_kernels() -> float:
    from tradeatlas.calculator import calculate_delivered_cost

    envelope = calculate_delivered_cost(commodity="Groundnut", base_price_rs_qtl=5123.45, freight_per_tonne=900.0)
    return float(envelope.payload["delivered_cost_per_tonne"])


def _delivered_cost_pods() -> float:
    from tradeatlas.calculator import calculate_delivered_cost

    envelope = calculate_delivered_cost(
        commodity="Groundnut", base_price_rs_qtl=5123.45, freight_per_tonne=900.0, is_pod=True
    )
    return float(envelope.payload["delivered_cost_per_tonne"])


def _anomaly_flag_gujarat() -> float:
    from tradeatlas.analytics import detect_price_anomalies

    envelope = detect_price_anomalies(state="Gujarat", commodity="Groundnut")
    return float(envelope.payload["flags"][0]["value"])


DERIVATIONS = {
    "buyer-daily-price-gujarat": _daily_gujarat_modal,
    "buyer-hub-msp-rajkot": _hub_rajkot_msp_spread,
    "buyer-delivered-cost-kernels": _delivered_cost_kernels,
    "buyer-delivered-cost-pods": _delivered_cost_pods,
    "buyer-anomaly-flag-gujarat": _anomaly_flag_gujarat,
}


def regenerate(persona: str) -> None:
    suite_path = GOLDEN / f"{persona}.json"
    original_text = suite_path.read_text(encoding="utf-8")
    suite = json.loads(original_text)
    updated = 0
    for case in suite["cases"]:
        missing = [f for f in REQUIRED_FIELDS if f not in case]
        if missing:
            raise ValueError(f"Case '{case.get('id', '?')}': missing fields {missing}")
        if case["kind"] == "numeric-exact":
            value = RESOLVERS[case["target"]](case["args"])
            case["expected"] = round(float(value), 2)
            updated += 1
        elif case["kind"] == "agent-evidence-fidelity" and case["id"] in DERIVATIONS:
            value = DERIVATIONS[case["id"]]()
            for figure in case["expected"].get("figures", []):
                if "value" in figure:
                    figure["value"] = round(float(value), 2)
            updated += 1
    rendered = json.dumps(suite, indent=2, ensure_ascii=False) + "\n"
    if rendered != original_text:  # zero-diff property: unchanged code rewrites nothing
        suite_path.write_text(rendered, encoding="utf-8")
    print(f"{persona}: regenerated {updated} expectations (numeric-exact + agent figures)")


if __name__ == "__main__":
    regenerate(sys.argv[1] if len(sys.argv) > 1 else "analyst")
