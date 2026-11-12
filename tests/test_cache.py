"""Cache lifecycle: freshness, upsert isolation, UTC timestamps (offline, isolated DB)."""

from tradeatlas import cache as cache_mod
from tradeatlas.cache import (
    get_cache_fetched_at,
    get_cached_records,
    is_cache_fresh,
    save_records_to_cache,
)

RECORDS = [
    {
        "state": "Gujarat",
        "district": "Rajkot",
        "market": "Rajkot APMC",
        "commodity": "Groundnut",
        "variety": "Bold",
        "grade": "FAQ",
        "arrival_date": "12/11/2026",
        "min_price": 7000,
        "max_price": 7300,
        "modal_price": 7200,
    }
]


def test_fresh_cache_is_fresh(isolated_cache):
    save_records_to_cache("gujarat_groundnut", RECORDS)
    assert is_cache_fresh("gujarat_groundnut", ttl_hours=6.0) is True


def test_stale_cache_is_not_fresh(isolated_cache):
    save_records_to_cache("gujarat_groundnut", RECORDS)
    # Age the metadata row beyond the TTL (7 hours).
    conn = cache_mod.get_db_connection()
    try:
        conn.execute(
            "UPDATE cache_metadata SET last_fetched = last_fetched - INTERVAL '7 hours'"
        )
    finally:
        conn.close()
    assert is_cache_fresh("gujarat_groundnut", ttl_hours=6.0) is False


def test_unknown_key_is_not_fresh(isolated_cache):
    assert is_cache_fresh("never_cached", ttl_hours=6.0) is False


def test_upsert_replaces_without_duplicates(isolated_cache):
    save_records_to_cache("gujarat_groundnut", RECORDS)
    newer = [dict(RECORDS[0], modal_price=7250)]
    save_records_to_cache("gujarat_groundnut", newer)
    rows = get_cached_records("Gujarat", "Groundnut")
    assert len(rows) == 1
    assert rows[0]["modal_price"] == 7250


def test_timestamps_are_timezone_aware_utc(isolated_cache):
    save_records_to_cache("gujarat_groundnut", RECORDS)
    fetched = get_cache_fetched_at("gujarat_groundnut")
    assert fetched is not None
    assert fetched.tzinfo is not None
    assert fetched.utcoffset().total_seconds() == 0
