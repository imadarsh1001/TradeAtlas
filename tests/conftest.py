"""Shared test fixtures: recorded API responses, isolated DuckDB cache, transport seam."""

import json
from pathlib import Path

import httpx
import pandas as pd
import pytest

from tradeatlas import cache as cache_mod
from tradeatlas import ingest as ingest_mod

FIXTURES = Path(__file__).parent / "fixtures"


def make_series(values, start: str = "2024-01") -> pd.Series:
    """Synthetic monthly series for analytics tests; None entries stay as gaps (NaN)."""
    months = pd.period_range(start, periods=len(values), freq="M")
    return pd.Series([float(v) if v is not None else float("nan") for v in values], index=months)


@pytest.fixture(scope="session")
def datagov_payload() -> dict:
    """Recorded data.gov.in response: Gujarat Groundnut daily prices."""
    return json.loads((FIXTURES / "datagov_gujarat_groundnut.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def agmarknet_payload() -> dict:
    """Recorded AGMARKNET 2.0 spot-weekly response: Rajkot APMC, Groundnut."""
    return json.loads((FIXTURES / "agmarknet_spot_rajkot.json").read_text(encoding="utf-8"))


@pytest.fixture(autouse=True)
def hermetic_api_key(monkeypatch):
    """Tests never depend on a real .env or live network: pin a fake key."""
    monkeypatch.setattr(ingest_mod, "get_api_key", lambda: "test-key")


@pytest.fixture()
def isolated_cache(tmp_path, monkeypatch):
    """Point the DuckDB cache at a temp directory for test isolation."""
    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(cache_mod, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(cache_mod, "DB_PATH", cache_dir / "test_live_mandi.duckdb")
    return cache_mod


def datagov_transport(payload, calls=None, status_code=200):
    """MockTransport serving a recorded data.gov.in payload, counting requests."""

    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        if status_code == 200:
            return httpx.Response(200, json=payload)
        return httpx.Response(status_code, json={"error": "boom"})

    return httpx.MockTransport(handler)


def failing_transport(calls=None):
    """MockTransport whose connection always fails (network down)."""

    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        raise httpx.ConnectError("network down")

    return httpx.MockTransport(handler)
