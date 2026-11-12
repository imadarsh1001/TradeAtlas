"""Evidence-card contract: tiers, caveats, cache-age disclosure, explicit gaps.

Envelope-only assertions against the shared conftest transports; behavior
(matching, fallback, supply balance) lives in test_ingest.py.
"""

from datetime import datetime

from tradeatlas import ingest
from tradeatlas.calculator import calculate_delivered_cost
from tests.conftest import datagov_transport


def _iso_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None and parsed.utcoffset().total_seconds() == 0
    return parsed


def test_deep_tier_gujarat_groundnut(isolated_cache, datagov_payload):
    env = ingest.fetch_daily_mandi_prices("Gujarat", "Groundnut", transport=datagov_transport(datagov_payload))
    assert env.tier == "deep"
    assert env.coverage == f"{len(env.payload)} records for (Gujarat, Groundnut)"
    assert env.observation_dates == sorted({r["arrival_date"] for r in env.payload})
    assert not any("Thin tier" in c for c in env.caveats)


def test_deep_tier_rajasthan_groundnut(isolated_cache):
    payload = {"records": [{
        "state": "Rajasthan", "district": "Bikaner", "market": "Bikaner",
        "commodity": "Groundnut", "variety": "Bold", "grade": "FAQ",
        "arrival_date": "12/11/2026", "min_price": 6800, "max_price": 7100, "modal_price": 6950,
    }]}
    env = ingest.fetch_daily_mandi_prices("Rajasthan", "Groundnut", transport=datagov_transport(payload))
    assert env.tier == "deep"


def test_thin_tier_mustard(isolated_cache):
    payload = {"records": [{
        "state": "Rajasthan", "district": "Bharatpur", "market": "Bharatpur",
        "commodity": "Mustard", "variety": "Local", "grade": "FAQ",
        "arrival_date": "12/11/2026", "min_price": 5800, "max_price": 6100, "modal_price": 5950,
    }]}
    env = ingest.fetch_daily_mandi_prices("Rajasthan", "Mustard", transport=datagov_transport(payload))
    assert env.tier == "thin"
    assert any("coverage has not been verified" in c for c in env.caveats)


def test_spot_weekly_is_thin_stateless(isolated_cache, agmarknet_payload):
    env = ingest.fetch_spot_weekly_prices(60, 11, 10, transport=datagov_transport(agmarknet_payload))
    assert env.tier == "thin"
    assert env.coverage == "upstream AGMARKNET spot-weekly payload for (market_id=60, state_id=11, commodity_id=10)"
    assert any("passed through" in c for c in env.caveats)
    assert env.no_data is False


def test_spot_weekly_upstream_error_is_explicit(isolated_cache):
    env = ingest.fetch_spot_weekly_prices(60, 11, 10, transport=datagov_transport({}, status_code=500))
    assert env.no_data is True
    assert "HTTP 500" in env.payload["error"]
    assert any("Upstream error" in c for c in env.caveats)


def test_fresh_fetch_has_no_cached_as_of(isolated_cache, datagov_payload):
    env = ingest.fetch_daily_mandi_prices("Gujarat", "Groundnut", transport=datagov_transport(datagov_payload))
    assert env.cached_as_of is None


def test_cached_response_discloses_age(isolated_cache, datagov_payload):
    from tradeatlas.cache import save_records_to_cache

    save_records_to_cache("gujarat_groundnut", datagov_payload["records"])
    env = ingest.fetch_daily_mandi_prices("Gujarat", "Groundnut")  # fresh in TTL, served from cache
    assert env.cached_as_of is not None
    assert _iso_utc(env.cached_as_of) <= _iso_utc(env.retrieved_at)


def test_benchmark_hub_summary_envelope(isolated_cache, datagov_payload):
    env = ingest.fetch_benchmark_hub_summary("Gujarat", "Groundnut", transport=datagov_transport(datagov_payload))
    assert env.tier == "deep"
    assert env.payload["hubs_monitored"] == 4
    assert len(env.payload["hub_details"]) == 4
    assert any(h.get("status") == "Not Reported Today" for h in env.payload["hub_details"])
    assert env.coverage == f"{env.payload['hubs_reporting_today']} of 4 configured hub mandis reporting for (Gujarat, Groundnut)"
    assert any("Minimum Support Price" in c for c in env.caveats)


def test_delivered_cost_envelope_is_input_only():
    env = calculate_delivered_cost("Groundnut", 4000, 500, 200, is_pod=True)
    assert env.tier == "deep"
    assert env.coverage == "user-supplied inputs"
    assert env.observation_dates == []
    assert env.payload["decortication_allowance_per_tonne"] == 1500.0


def test_pagination_caveat_at_page_limit(isolated_cache):
    big = {"records": [{
        "state": "Gujarat", "district": "Dahod", "market": f"Mandali-{i}",
        "commodity": "Groundnut", "variety": "Other", "grade": "Local",
        "arrival_date": "12/11/2026", "min_price": 7000, "max_price": 7300, "modal_price": 7200,
    } for i in range(1000)]}
    env = ingest.fetch_daily_mandi_prices("Gujarat", "Groundnut", transport=datagov_transport(big))
    assert any("first 1000 records" in c for c in env.caveats)
