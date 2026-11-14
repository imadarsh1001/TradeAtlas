# Spec Delta

## Purpose

Rolling-cutoff backtesting of price baselines on the pinned monthly series — every method scored on identical held-out targets, with reporting-break isolation and MAE/MASE scoring — so forecast claims are measured, reproducible, and honest about what the data supports.

## ADDED Requirements

### Requirement: Rolling-cutoff baseline scoring
The harness SHALL backtest three baselines — last observed, same month last year (the target month minus 12), and a linear trend refit at every cutoff on elapsed calendar positions — at horizons of 1, 2, and 3 months, using only information available at each cutoff and at least 24 training months per cutoff.

#### Scenario: Last-observed baseline carries forward
- **WHEN** the harness predicts horizon 1 from a cutoff
- **THEN** the last-observed prediction equals the latest observed price at that cutoff

#### Scenario: Seasonal baseline reads the target year
- **WHEN** the harness predicts any horizon for target month T
- **THEN** the same-month-last-year prediction is the observed price at month T−12, not month origin−12

### Requirement: Identical scored targets per method
For each state, target period, and horizon, every method SHALL be scored on exactly the same held-out rows; no method may gain targets another lacks.

#### Scenario: Equal target counts
- **WHEN** the summary is produced
- **THEN** all methods share the same target count within every state × period × horizon group

### Requirement: Reporting-break isolation
Scores SHALL be grouped into targets before November 2025 and targets from November 2025 onward, and no metric SHALL aggregate observations across that boundary (ADR 0001).

#### Scenario: No cross-break aggregation
- **WHEN** the summary is grouped by state, target period, and horizon
- **THEN** each group contains targets from only one side of the November 2025 boundary

### Requirement: MAE and MASE scoring
The harness SHALL report mean absolute error and mean absolute scaled error. The MASE scaling factor q SHALL be computed per printed group (state × target-period × horizon) as the mean of |y_t − y_{t−12}| over the group's scored targets t whose t−12 exists in the training panel — mirroring the seasonal baseline's own lookback. q is a scaling constant, not a scored metric, and SHALL be printed per group so MASE = MAE / q is checkable. If a group has no such pair with a nonzero seasonal error — including an all-flat seasonal panel where q = 0 — MASE SHALL be reported as null for that group.

#### Scenario: MASE is MAE over the scaling factor
- **WHEN** a group reports MAE, MASE, and q
- **THEN** MASE equals MAE divided by that group's printed q

#### Scenario: Post-break groups have a computable q
- **WHEN** the post-break groups are scored on the pinned extract
- **THEN** q is computed from the scored targets' seasonal lookback pairs (11 pairs on the pinned data) rather than being undefined

#### Scenario: Flat seasonal panel yields null MASE
- **WHEN** every scored target's y_t equals its y_{t−12} (q = 0) while the baselines still produce errors
- **THEN** the group reports MAE normally and MASE as null

### Requirement: Pinned-source verification and provenance
Report generation SHALL verify the pinned extract's SHA-256 against the manifest before scoring and SHALL record the source revision read from the manifest's `revision` field.

#### Scenario: Hash mismatch blocks scoring
- **WHEN** the extract's content differs from the pinned digest
- **THEN** report generation fails with an error naming the file and expected hash

#### Scenario: Report carries provenance
- **WHEN** a report is generated from the pinned extract
- **THEN** it states the manifest's source revision, the scored date range, and the training-month minimum

### Requirement: Reproducible report
Running the package entry point on the pinned extract SHALL produce identical summary output on every run, except for the single `generated_at` field (supplied by an injectable clock).

#### Scenario: Two runs are identical
- **WHEN** the report entry point runs twice on the same pinned data with the same injected clock
- **THEN** both summaries are byte-identical, and with different clocks only `generated_at` differs
