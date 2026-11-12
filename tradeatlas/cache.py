"""DuckDB Local Caching Layer for TradeAtlas Live Ingestion."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import duckdb

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"
DB_PATH = CACHE_DIR / "live_mandi.duckdb"


def get_db_connection() -> duckdb.DuckDBPyConnection:
    """Initialize and return a DuckDB connection with initialized schemas."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    conn = duckdb.connect(str(DB_PATH))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS mandi_daily_cache (
            state VARCHAR,
            district VARCHAR,
            market VARCHAR,
            commodity VARCHAR,
            variety VARCHAR,
            grade VARCHAR,
            arrival_date VARCHAR,
            min_price DOUBLE,
            max_price DOUBLE,
            modal_price DOUBLE,
            fetched_at TIMESTAMP
        );
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS cache_metadata (
            cache_key VARCHAR PRIMARY KEY,
            last_fetched TIMESTAMP,
            record_count INTEGER
        );
        """
    )
    return conn


def is_cache_fresh(cache_key: str, ttl_hours: float = 6.0) -> bool:
    """Check if a cached key was updated within the TTL."""
    conn = get_db_connection()
    try:
        res = conn.execute(
            "SELECT last_fetched FROM cache_metadata WHERE cache_key = ?",
            [cache_key],
        ).fetchone()
        if not res or not res[0]:
            return False
        last_fetched = _as_utc(res[0])
        # Calculate elapsed hours
        now = datetime.now(timezone.utc)
        elapsed = (now - last_fetched).total_seconds() / 3600.0
        return elapsed < ttl_hours
    finally:
        conn.close()


def _as_utc(value: datetime) -> datetime:
    """Normalize a stored timestamp to timezone-aware UTC (DuckDB TIMESTAMP is naive; stored values are UTC)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def get_cache_fetched_at(cache_key: str) -> Optional[datetime]:
    """Return the last fetch time for a key as timezone-aware UTC, or None."""
    conn = get_db_connection()
    try:
        res = conn.execute(
            "SELECT last_fetched FROM cache_metadata WHERE cache_key = ?",
            [cache_key],
        ).fetchone()
        return _as_utc(res[0]) if res and res[0] else None
    finally:
        conn.close()


def get_cached_records(
    state: str,
    commodity: str,
    market: Optional[str] = None,
    arrival_date: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieve matching records from the DuckDB cache."""
    conn = get_db_connection()
    try:
        query = "SELECT state, district, market, commodity, variety, grade, arrival_date, min_price, max_price, modal_price FROM mandi_daily_cache WHERE LOWER(state) = LOWER(?) AND LOWER(commodity) = LOWER(?)"
        params: List[Any] = [state, commodity]

        if market:
            query += " AND LOWER(market) LIKE LOWER(?)"
            params.append(f"%{market}%")

        if arrival_date:
            query += " AND arrival_date = ?"
            params.append(arrival_date)

        query += " ORDER BY modal_price DESC"

        cursor = conn.execute(query, params)
        cols = [desc[0] for desc in cursor.description]
        rows = cursor.fetchall()
        return [dict(zip(cols, row)) for row in rows]
    finally:
        conn.close()


def save_records_to_cache(cache_key: str, records: List[Dict[str, Any]]) -> None:
    """Upsert fetched records and update cache metadata in DuckDB."""
    if not records:
        return
    conn = get_db_connection()
    try:
        # Stored naive but representing UTC (DuckDB TIMESTAMP has no zone).
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        # Delete existing entries for this state + commodity if present to avoid stale duplicates
        first = records[0]
        state = first.get("state", "")
        commodity = first.get("commodity", "")
        conn.execute(
            "DELETE FROM mandi_daily_cache WHERE LOWER(state) = LOWER(?) AND LOWER(commodity) = LOWER(?)",
            [state, commodity],
        )

        # Insert new records
        insert_rows = []
        for r in records:
            insert_rows.append(
                (
                    r.get("state"),
                    r.get("district"),
                    r.get("market"),
                    r.get("commodity"),
                    r.get("variety"),
                    r.get("grade"),
                    str(r.get("arrival_date", "")),
                    float(r.get("min_price", 0.0) or 0.0),
                    float(r.get("max_price", 0.0) or 0.0),
                    float(r.get("modal_price", 0.0) or 0.0),
                    now,
                )
            )

        conn.executemany(
            """
            INSERT INTO mandi_daily_cache VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            insert_rows,
        )

        conn.execute(
            """
            INSERT OR REPLACE INTO cache_metadata VALUES (?, ?, ?)
            """,
            [cache_key, now, len(records)],
        )
    finally:
        conn.close()
