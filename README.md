# TradeAtlas — India Agricultural Intelligence

Evidence-grounded procurement intelligence for India's edible oilseeds complex (Groundnut · Soybean · Mustard) across the 5-state corridor (Gujarat · Rajasthan · Madhya Pradesh · Maharashtra · Haryana) — built for procurement leads at edible-oil processors and agri-traders.

TradeAtlas answers one buyer question reliably: **"I need N tonnes of commodity X — where and when should I seek quotes, and what must I verify before acting?"** — with comparable market evidence, explicit data-age and coverage disclosure, and deterministic cost arithmetic. It never dresses a data gap up as a recommendation. Three personas share one evidence core — **Buyer** (primary, the north star), **Sell-side** (farmer/FPO), and **Analyst** — see [PERSONAS.md](PERSONAS.md).

## The thesis

**Agentic value through restriction, not freedom.** Deterministic Python and DuckDB own 100% of arithmetic, filtering, and evidence generation, producing immutable **Evidence Cards**. LLM agents are restricted to query parsing and executive briefing, and a deterministic citation verifier — delivered with the agent layer in roadmap M3 — cross-checks every figure an agent emits against the evidence. The [MVP plan](TradeAtlas_India_Agricultural_Intelligence_MVP_Plan.md) (historical) documents this architecture in full; [docs/ROADMAP.md](docs/ROADMAP.md) is the single source of truth for what's next.

## What works today

- **MCP (Model Context Protocol) server** (`tradeatlas_mcp.py`) with 7 deterministic tools, consumable from Claude Code, Cursor, or any MCP client:
  - `get_daily_mandi_prices` — live daily wholesale prices from data.gov.in (DuckDB-cached, 6 h TTL)
  - `get_benchmark_hub_summary` — curated benchmark hub mandis vs. the central Minimum Support Price (MSP) spread
  - `get_spot_weekly_prices` — 7-day rolling AGMARKNET 2.0 spot prices (India's official agricultural market-price network; unauthenticated, compliant)
  - `get_macro_supply_balance` — UPAg (Unified Portal for Agricultural Statistics) advance estimates vs. 3-year baseline (surplus/deficit signal)
  - `calculate_delivered_cost` — landed cost per tonne incl. the 70% shelling-outturn pod→kernel benchmark
  - `detect_price_anomalies` — robust MAD flagging of unusual monthly price changes (threshold 3.5, per-segment)
  - `check_series_coverage` — month coverage, gaps, and trailing staleness for the pinned series

  Every tool returns an **evidence-card envelope** (`tradeatlas.models.EvidenceEnvelope`): the payload plus observation date(s), retrieval time (UTC), a coverage statement, a deep/thin tier label, and caveats — including explicit no-data statements instead of empty lists. **Breaking vs. pre-M1 raw record lists.** Groundnut in Gujarat/Rajasthan is `deep`; everything else is `thin` with an unverified-coverage caveat.
- **Forecasting harness** (`tradeatlas/forecasting.py`): rolling-cutoff backtest of three baselines at 1–3 month horizons with MAE/MASE and reporting-break isolation — `uv run python -m tradeatlas.forecasting`
- **Golden evals** (`evals/`): versioned per-persona suites with a runner recording results — `uv run python -m evals.runner analyst`
- **Reproducible experiments** (`experiments/`): groundnut data proof, price backtest (3 baselines × 3 horizons, reporting-break isolated), LangGraph agent benchmark (fixed report vs. single agent vs. specialists), marimo lab ([marimo](https://marimo.io) — reactive Python notebooks).
- **Spec & decision record**: [MVP plan](TradeAtlas_India_Agricultural_Intelligence_MVP_Plan.md) (historical), [concepts brief](concepts_brief.md) (historical), [glossary](GLOSSARY.md), [personas](PERSONAS.md), [roadmap](docs/ROADMAP.md), and [six ADRs](docs/adr/) (architecture decision records).

**Status:** M0–M2 complete (evidence-card tools, forecasting harness, anomaly/coverage detection, golden evals) → **M3 (agent layer) is next**. See the [roadmap](docs/ROADMAP.md).

## Quickstart

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12 (pinned in `.python-version`).

```powershell
# 1. Install the pinned environment
uv sync --locked

# 2. Configure the data.gov.in API key (register at https://data.gov.in)
Copy-Item .env.example .env   # then set DATA_GOV_IN_API_KEY=...

# 3. Run the MCP server (from any MCP client or directly)
uv run --locked python tradeatlas_mcp.py

# 4. Or explore the analysis lab (marimo reactive notebooks)
./run-tradeatlas.ps1                                # opens experiments/groundnut_lab.py
uv run --locked python experiments/groundnut_data_proof.py
uv run --locked python experiments/groundnut_price_backtest.py
uv run --locked python experiments/groundnut_agent_benchmark.py
```

## Repository layout

```text
tradeatlas/            Deterministic core: ingest, cache, calculator, forecasting, analytics, models
tradeatlas_mcp.py      MCP server (7 tools)
config/                Benchmark hub mandis + MSP benchmarks
data/raw/              Pinned historical extracts (UPAg APY — area/production/yield — AGMARKNET state-monthly)
data/manifest.json     SHA-256 provenance for pinned files (enforced by tests)
evals/                 Golden suites + runner (analyst suite gates M2)
experiments/           Research scripts and marimo lab (M0 evidence)
docs/adr/              Architecture decision records (ADRs)
docs/ROADMAP.md        Reconciled milestones — source of truth
PERSONAS.md            Buyer (primary) · Sell-side · Analyst
GLOSSARY.md            Canonical domain terminology
```

## Data sources & compliance

- **data.gov.in** — official Open Government Data platform REST API (authenticated key); primary live source ([details](docs/DATA_GOV_IN_API.md)).
- **AGMARKNET 2.0** — only unauthenticated public endpoints; bulk reports requiring CAPTCHA/JWT are **never** bypassed ([ADR 0004](docs/adr/0004-live-mandi-data-ingestion-architecture.md)).
- **UPAg** — official production estimates (pinned extract in `data/raw/`).

Known limitation: data.gov.in omits daily arrival volumes in tonnes; arrival feeds are the first candidate beyond the current roadmap ([ADR 0004](docs/adr/0004-live-mandi-data-ingestion-architecture.md) → [Beyond M6](docs/ROADMAP.md#beyond-m6-long-term-direction)).

## Scope honesty

Groundnut is **deep-tier** in its proof states, Gujarat and Rajasthan: coverage checks, reconciliation, and backtests. Soybean and mustard are **thin-tier** — live data without the full verification set — and are labelled as such. Arrivals ≠ sales; production ≠ purchasable inventory; every recommendation names what a buyer must still verify directly.

## Beyond the corridor

The corridor is the beachhead, not the boundary: the standing ambition is more commodities, pan-India state coverage rising to mandi-level detail, arrival-volume feeds, and international trade context — each admitted only through the verification gates in [Beyond M6](docs/ROADMAP.md#beyond-m6-long-term-direction).
