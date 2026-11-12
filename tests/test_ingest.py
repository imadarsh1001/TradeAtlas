"""Ingest behavior: TLS construction, hub matching, supply balance, fallback paths.

Every fetch test injects a transport — no test reaches the real network.
"""

from pathlib import Path

import httpx
import pandas as pd
import pytest

import tradeatlas.ingest as ingest
from tradeatlas.models import EvidenceEnvelope
from tests.conftest import datagov_transport, failing_transport

PACKAGE_DIR = Path(ingest.__file__).parent


def _age_cache(cache_mod, hours=7):
    """Push the cache_metadata row beyond the TTL."""
    conn = cache_mod.get_db_connection()
    try:
        conn.execute(f"UPDATE cache_metadata SET last_fetched = last_fetched - INTERVAL '{hours} hours'")
    finally:
        conn.close()


# --- TLS: verification enabled, no verify=False anywhere in the package ---

def test_no_verify_false_anywhere_in_package():
    offenders = [
        str(p) for p in PACKAGE_DIR.rglob("*.py") if "verify=False" in p.read_text(encoding="utf-8")
    ]
    assert offenders == []


def test_clients_constructed_with_verification_enabled(monkeypatch, agmarknet_payload):
    seen = {}
    real_client = ingest.httpx.Client

    def spy_client(*args, **kwargs):
        seen.update(kwargs)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(ingest.httpx, "Client", spy_client)
    envelope = ingest.fetch_spot_weekly_prices(60, 11, 10, transport=datagov_transport(agmarknet_payload))
    assert "verify" not in seen or seen["verify"] is not False
    assert isinstance(envelope, EvidenceEnvelope)


# --- Benchmark hub matching ---

def _stub_prices(records, cached_as_of="2026-11-13T06:00:00+00:00"):
    return EvidenceEnvelope(
        payload=records,
        coverage=f"{len(records)} records",
        tier="deep",
        retrieved_at="2026-11-13T06:00:00+00:00",
        cached_as_of=cached_as_of,
    )


def test_hub_matching_case_insensitive(monkeypatch):
    records = [
        {"market": "rajkot apmc", "district": "Rajkot", "variety": "Bold", "grade": "FAQ",
         "arrival_date": "12/11/2026", "min_price": 7000, "max_price": 7300, "modal_price": 7200}
    ]
    monkeypatch.setattr(ingest, "fetch_daily_mandi_prices", lambda *a, **k: _stub_prices(records))
    monkeypatch.setattr(ingest, "load_benchmark_config", lambda: {
        "msp_benchmark_inr_qtl": {"Groundnut": 6783.0},
        "hubs": {"Gujarat": {"Groundnut": [{"market": "Rajkot", "district": "Rajkot"}]}},
    })
    env = ingest.fetch_benchmark_hub_summary("Gujarat", "Groundnut")
    hub = env.payload["hub_details"][0]
    assert hub["modal_price"] == 7200
    assert hub["msp_spread"] == pytest.approx(417.0)
    assert hub["distress_status"] == "Premium to MSP (Firm Market)"
    assert env.coverage == "1 of 1 configured hub mandis reporting for (Gujarat, Groundnut)"


def test_unmatched_hub_reports_not_reported(monkeypatch):
    monkeypatch.setattr(ingest, "fetch_daily_mandi_prices", lambda *a, **k: _stub_prices([]))
    monkeypatch.setattr(ingest, "load_benchmark_config", lambda: {
        "msp_benchmark_inr_qtl": {"Groundnut": 6783.0},
        "hubs": {"Gujarat": {"Groundnut": [{"market": "Gondal", "district": "Rajkot"}]}},
    })
    env = ingest.fetch_benchmark_hub_summary("Gujarat", "Groundnut")
    hub = env.payload["hub_details"][0]
    assert hub["status"] == "Not Reported Today"
    assert hub["msp_benchmark"] == 6783.0
    assert env.no_data is True


def test_missing_msp_benchmark_is_explicit(monkeypatch):
    records = [
        {"market": "Rajkot APMC", "district": "Rajkot", "variety": "Bold", "grade": "FAQ",
         "arrival_date": "12/11/2026", "min_price": 7000, "max_price": 7300, "modal_price": 7200}
    ]
    monkeypatch.setattr(ingest, "fetch_daily_mandi_prices", lambda *a, **k: _stub_prices(records))
    monkeypatch.setattr(ingest, "load_benchmark_config", lambda: {
        "msp_benchmark_inr_qtl": {},  # no MSP entry for the commodity
        "hubs": {"Gujarat": {"Groundnut": [{"market": "Rajkot", "district": "Rajkot"}]}},
    })
    env = ingest.fetch_benchmark_hub_summary("Gujarat", "Groundnut")
    hub = env.payload["hub_details"][0]
    assert hub["msp_benchmark"] is None
    assert hub["msp_spread"] is None
    assert hub["distress_status"] == "MSP benchmark unavailable"


# --- Supply balance ---

def test_supply_balance_surplus_from_pinned_extract():
    env = ingest.fetch_macro_supply_balance("Gujarat", "Groundnut")
    assert env.no_data is False
    assert env.payload["harvest_outlook"].startswith("Harvest Surplus")
    assert env.payload["supply_balance_pct"] == pytest.approx(30.6)
    assert env.payload["latest_crop_year"]


def test_supply_balance_short_baseline_unavailable(monkeypatch):
    one_year = pd.DataFrame([
        {"State": "Testland", "Crop": "Testcrop", "Metric": "Production",
         "RecordType": "State - Season Total", "Season": "Total", "Latest Estimate": "1",
         "Crop Year": "2025-26", "Value": "1.5", "Estimation Cycle": "Advance Estimate"},
    ])
    monkeypatch.setattr(pd, "read_csv", lambda *a, **k: one_year)
    env = ingest.fetch_macro_supply_balance("Testland", "Testcrop")
    assert env.payload["harvest_outlook"] == "Baseline Unavailable"
    # Spec: no percentage and no baseline when no prior crop year exists.
    assert "supply_balance_pct" not in env.payload
    assert "baseline_tonnes" not in env.payload


def test_supply_balance_zero_baseline_unavailable(monkeypatch):
    zero_prior = pd.DataFrame([
        {"State": "Testland", "Crop": "Testcrop", "Metric": "Production",
         "RecordType": "State - Season Total", "Season": "Total", "Latest Estimate": "1",
         "Crop Year": y, "Value": v, "Estimation Cycle": "Advance Estimate"}
        for y, v in [("2024-25", "0"), ("2025-26", "1.5")]
    ])
    monkeypatch.setattr(pd, "read_csv", lambda *a, **k: zero_prior)
    env = ingest.fetch_macro_supply_balance("Testland", "Testcrop")
    assert env.payload["harvest_outlook"] == "Baseline Unavailable"
    assert "supply_balance_pct" not in env.payload


def test_supply_balance_missing_estimates_error():
    env = ingest.fetch_macro_supply_balance("Atlantis", "Groundnut")
    assert env.no_data is True
    assert "Atlantis" in env.payload["error"] and "Groundnut" in env.payload["error"]


# --- Cache/fetch lifecycle (all offline via transport seam) ---

def test_fresh_cache_avoids_network(isolated_cache, datagov_payload):
    from tradeatlas.cache import save_records_to_cache

    save_records_to_cache("gujarat_groundnut", datagov_payload["records"])
    calls = []
    envelope = ingest.fetch_daily_mandi_prices(
        "Gujarat", "Groundnut", transport=datagov_transport(datagov_payload, calls=calls)
    )
    assert calls == []  # fresh cache: zero HTTP requests
    assert envelope.no_data is False
    assert envelope.cached_as_of is not None


def test_stale_cache_triggers_refetch(isolated_cache, datagov_payload):
    from tradeatlas.cache import save_records_to_cache

    save_records_to_cache("gujarat_groundnut", [dict(datagov_payload["records"][0], modal_price=1)])
    _age_cache(isolated_cache)
    calls = []
    envelope = ingest.fetch_daily_mandi_prices(
        "Gujarat", "Groundnut", transport=datagov_transport(datagov_payload, calls=calls)
    )
    assert len(calls) == 1  # stale: exactly one live fetch
    # The stale seeded value is gone; the refreshed records match the fixture set
    # (ordering is modal_price DESC, so compare sets, not [0]).
    assert {r["modal_price"] for r in envelope.payload} == {
        r["modal_price"] for r in datagov_payload["records"]
    }
    assert envelope.cached_as_of is None  # served fresh, not from the old snapshot


def test_failed_fetch_falls_back_to_cache(isolated_cache, datagov_payload):
    from tradeatlas.cache import save_records_to_cache

    save_records_to_cache("gujarat_groundnut", datagov_payload["records"])
    _age_cache(isolated_cache)  # force the stale path so the fetch is attempted
    calls = []
    envelope = ingest.fetch_daily_mandi_prices(
        "Gujarat", "Groundnut", transport=failing_transport(calls=calls)
    )
    assert len(calls) == 1  # the failing fetch was attempted
    assert envelope.no_data is False
    assert len(envelope.payload) == len(datagov_payload["records"])
    assert envelope.cached_as_of is not None  # original snapshot age disclosed
    assert any("Live fetch failed" in c for c in envelope.caveats)


def test_missing_api_key_falls_back_to_cache(isolated_cache, datagov_payload, monkeypatch):
    from tradeatlas.cache import save_records_to_cache

    save_records_to_cache("gujarat_groundnut", datagov_payload["records"])
    _age_cache(isolated_cache)  # force the stale path so the no-key branch runs
    monkeypatch.setattr(ingest, "get_api_key", lambda: "")
    envelope = ingest.fetch_daily_mandi_prices("Gujarat", "Groundnut")
    assert envelope.no_data is False
    assert envelope.cached_as_of is not None


def test_upstream_empty_over_stale_cache_discloses_both(isolated_cache, datagov_payload):
    from tradeatlas.cache import save_records_to_cache

    save_records_to_cache("gujarat_groundnut", datagov_payload["records"])
    _age_cache(isolated_cache)
    envelope = ingest.fetch_daily_mandi_prices(
        "Gujarat", "Groundnut", transport=datagov_transport({"records": []})
    )
    assert envelope.no_data is False  # stale cache served
    assert any("Upstream returned no records" in c for c in envelope.caveats)
    assert envelope.cached_as_of is not None


def test_empty_result_is_explicit_no_data(isolated_cache, datagov_payload):
    envelope = ingest.fetch_daily_mandi_prices(
        "Gujarat", "Groundnut", market="Nowhere", transport=datagov_transport(datagov_payload)
    )
    assert envelope.no_data is True
    assert "0 records for (Gujarat, Groundnut, market~Nowhere)" in envelope.coverage
    assert any("Not reported" in c or "No records" in c for c in envelope.caveats)
