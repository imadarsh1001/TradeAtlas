# Proposal

## Why

ROADMAP M2 (Analyst lens) is next after M1: the forecasting harness exists only as an experiment script (`experiments/groundnut_price_backtest.py`), anomaly detection and month-coverage/gap/staleness analysis exist nowhere, and the golden-eval infrastructure promised at every milestone exit does not exist. M3's Decision and Discovery agents are blocked on these exact tools (they consume forecasting and anomaly evidence), and the ML stage gate ("one ML model only after the baseline harness passes") cannot be evaluated until the baseline harness is productized and scored.

## What Changes

- The rolling-cutoff backtest harness moves from `experiments/` into the package: three baselines (last observed, same-month-last-year, linear trend) scored at 1–3 month horizons with MAE and MASE, grouped by state × pre/post-reporting-break × horizon (ADR 0001 isolation preserved), producing a reproducible report from package code against the pinned, hash-verified extract.
- A deterministic **anomaly-detection tool** flags statistically unusual observations in the monthly price series (robust MAD method), returned as evidence cards.
- A deterministic **coverage-detection tool** reports per-state month coverage, gaps, and trailing staleness for the pinned series, returned as evidence cards.
- Both tools are exposed through the MCP server, corresponding to the plan's §5 `analytics.detect_anomalies` / `evidence.check_coverage` responsibilities — renamed to `detect_price_anomalies` / `check_series_coverage` to match the server's existing snake_case tool convention.
- The **golden-evals infrastructure** lands: versioned JSON suites in `evals/golden/`, a runner writing `evals/results/`, seeded with the Analyst suite (10 questions) at this milestone's exit gate.
- Methodology notes document the scoring definitions, anomaly method, and the pinned series' known limits (`docs/`).

## Capabilities

### New Capabilities

- `price-forecasting`: rolling-cutoff backtesting of price baselines on the pinned monthly series — same targets per method, MAE/MASE scoring, reporting-break isolation, reproducible report generation.
- `anomaly-detection`: deterministic flagging of statistically unusual monthly price observations (robust MAD threshold), with each result carrying its evidence card and never aggregating across the reporting break.
- `coverage-detection`: deterministic reporting-coverage analysis of the pinned monthly series — per-state observed months, missing months, longest gaps, and trailing staleness, as evidence cards.
- `golden-evals`: versioned, per-persona golden evaluation suites (JSON + rubric) executed by a runner that records results, extended at each milestone's exit gate; seeded here with the Analyst suite.

### Modified Capabilities

(none — no existing capability's requirements change; the MCP server gains two pass-through tools which is additive surface, covered by the new capability specs)

## Impact

- **Code**: new `tradeatlas/forecasting.py` (harness + report), `tradeatlas/analytics.py` (anomaly + coverage), both returning `EvidenceEnvelope`s; `tradeatlas_mcp.py` gains `detect_price_anomalies` and `check_series_coverage` pass-through tools.
- **Reuses**: `EvidenceEnvelope` (M1), `data/manifest.json` integrity, the pinned `data/raw/state_monthly.csv.gz` extract (already hash-pinned in both the manifest and `experiments/groundnut_data.py` — same digest), ADR 0001 break isolation.
- **New**: `evals/golden/analyst.json` + runner (`evals/` package or pytest module), `evals/results/`, `docs/ANALYST_METHODOLOGY.md`.
- **Dependencies**: none new (pandas, statistics already present); statsmodels/StatsForecast explicitly NOT added at this stage (stage gate).
- **Consumers**: M3 agents (forecast + anomaly evidence), MCP clients, the analyst persona (notebooks/API).
- **No change**: existing tool behavior, live-ingest paths; docs changes limited to ROADMAP status line, README tool/eval mentions, and the new methodology notes.
