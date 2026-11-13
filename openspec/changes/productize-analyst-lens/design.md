# Design

## Context

`experiments/groundnut_price_backtest.py` implements the rolling-cutoff harness (3 methods × 3 horizons, break-isolated MAE grouping) against `groundnut_data.load_state_months()` (pinned-hash loader, PeriodIndex panel). The pinned extract: both state series run 2019-01 → 2026-10 (94 gapless observations); post-break segment is 11 scored months after the harness drops the partial final month. M1 delivered `EvidenceEnvelope`, the manifest, and the MCP envelope pattern. See proposal.md — Why.

## Goals / Non-Goals

**Goals:** package-resident forecasting harness with MAE/MASE; anomaly + coverage tools as evidence cards + MCP tools; golden-eval infrastructure seeded with the Analyst suite; methodology notes.

**Non-Goals:** no ML model (stage gate: a separate future change after baselines pass); no new data sources; no live-data forecasting (pinned extract only); no UI; no changes to M1 tool behavior.

## Decisions

1. **Module layout: `tradeatlas/forecasting.py` + `tradeatlas/analytics.py`.** Forecasting owns the pinned-series loader, backtest, scoring, and report; analytics owns anomaly + coverage and imports the loader from forecasting (stated in tasks). Both return `EvidenceEnvelope`s where they are consumer-facing tools; the backtest report is a plain deterministic structure (it is the analyst's artifact, not a live-data answer).
2. **Series definition: the loader returns the FULL pinned series; only the harness drops the final partial month** (`iloc[:-1]`, the experiment's documented guard — the collector may stop mid-month). Analytics (anomaly, coverage) consume the full series including the extract's final month, and their outputs may legitimately cite 2026-10 where the harness's last scored month is 2026-09; methodology notes document the distinction.
3. **Integrity via the manifest, not a second pin.** The package loader verifies `data/raw/state_monthly.csv.gz` against `data/manifest.json`. The manifest entry gains a `revision` field (the publisher GitHub revision, `5c22c92…`, currently hardcoded only in the experiment) so the report can cite provenance without a second hardcoded pin; source-manifest tolerates additive fields. The experiment keeps its own pin (historical record); digests are identical today.
4. **MASE scaling pinned.** q per state × target-period group = mean of |y_t − y_{t−12}| over the group's scored targets t whose t−12 exists in the training panel. Rationale: the post-break segment has 11 scored months, so a both-endpoints-inside-segment reading yields zero seasonal pairs and an undefined q; the lookback into pre-break history is the *same lookback the same-month-last-year baseline already takes* for post-break targets — it is information available at the cutoff, not a cross-break aggregation. q is a scaling constant, not a scored metric, printed per group; MASE = MAE / q; q undefined (no pairs) → MASE null for that group. This supersedes the earlier "training segment (pre- or post-break)" wording.
5. **Anomaly method pinned: Iglewicz–Hoaglin modified z-score (0.6745·(x−median)/MAD) on month-over-month log changes, threshold 3.5, computed within each reporting-break segment.** Edge policies: segment-initial observations (no prior month) are unexamined; pairs involving NaN are skipped and counted in the examined caveat; a segment with < 6 scored changes yields no flags plus a thin-support caveat; degenerate MAD = 0 flags nothing. Coverage counts scored changes (not raw months). NOT trend/seasonal decomposition — that belongs to a later ML-gated change.
6. **Golden-eval binding is executable, not prose.** Suite: `{"version": 1, "cases": [...]}`; case = `id, persona, question, kind, target, args, expected`. The runner registers resolvers (`forecast_group`, `anomaly_result`, `coverage_report`) mapping `target`+`args` to a computed value/envelope. Scoring: `numeric-exact` = round(computed, 2) == expected; `evidence-fidelity` = named envelope assertions in `expected` (tier equals / caveat substring / coverage shape); `abstention` = pass iff `no_data` true or payload error names the selector. `evals/` is a regular package (`__init__.py`) so imports survive bare pytest, and `evals/runner.py` gains a `__main__` entry. Numeric expectations are generated once by a checked-in `evals/generate_expectations.py` against the pinned extract, rounded to 2 decimals. Code version in results = `git rev-parse --short HEAD` (fallback "unknown"). `evals/results/` is git-ignored.
7. **Staleness reference pinned:** the last month of the pinned extract's own date range — deterministic and consistent with the evals' regression-signal philosophy. Wall-clock staleness is out of scope for the pinned tool (documented in methodology notes). Gap convention: longest consecutive gap = 0 when no gap exists.
8. **MCP tools are pass-through with `EvidenceEnvelope` annotations** (M1's lesson applied on day one): `detect_price_anomalies(state, commodity)`, `check_series_coverage(state, commodity)` — corresponding to the plan §5 catalog responsibilities, renamed to the server's snake_case convention.
9. **Report entry point:** `uv run python -m tradeatlas.forecasting` prints the summary; `build_report(clock=...)` takes an injectable clock (default `utc_now_iso`) so reproducibility is testable by injecting one clock; the report's run timestamp lives only in the top-level `generated_at` field.

## Risks / Trade-offs

- [Pinned extract has no forecast vintages; treating completed months as available at cutoff is an approximation] → already the experiment's documented stance; methodology notes restate it and the report carries the caveat.
- [Only 2 states × groundnut in the pinned extract] → tier labels stay deep for exactly that scope; tool caveats name the pinned-snapshot boundary.
- [Post-break MASE rests on 11 seasonal lookback pairs] → the report shows target counts per group and prints q, so thin support is visible; methodology notes flag interpretation limits.
- [Golden expectations hard-code pinned-data values; any data refresh changes them] → intentional: numeric-exact drift MUST fail the suite (that is the regression signal); refresh = regenerate expectations via the generator script in the same change with manifest updates.

## Migration Plan

Additive only; no existing behavior changes. New modules, two new MCP tools, new `evals/` tree, one additive manifest field. Rollback = revert.

## Open Questions

None material — the three review blockers (MASE q, eval binding, staleness reference) are pinned above; remaining choices are task-level.
