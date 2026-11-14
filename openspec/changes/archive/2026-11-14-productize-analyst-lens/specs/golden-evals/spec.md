# Spec Delta

## Purpose

Versioned, per-persona golden evaluation suites — JSON cases bound to executable targets with a scoring rubric, executed by a deterministic runner that records results — so every milestone's exit gate is a measurable evaluation, not a feeling.

## ADDED Requirements

### Requirement: Suite file format
A golden suite SHALL be a versioned JSON file at `evals/golden/<persona>.json` with top-level shape `{"version": 1, "cases": [...]}`. Each case SHALL contain: unique `id`, `persona`, `question` (human-readable), `kind` (`numeric-exact`, `evidence-fidelity`, or `abstention`), `target` (a resolver name registered in the runner, e.g. `forecast_group`, `anomaly_result`, `coverage_report`), `args` (the resolver's selector arguments), and `expected` (the expected value per the scoring rubric).

#### Scenario: Analyst suite binds to resolvers
- **WHEN** the Analyst suite is loaded by the runner
- **THEN** all 10 cases are recognized with distinct ids and every `target` names a registered resolver

### Requirement: Case rejection
The runner SHALL reject a case missing any required field, naming the case and the missing field, and SHALL reject a case whose `target` names an unregistered resolver, naming the case and the target.

#### Scenario: Malformed case is rejected
- **WHEN** a suite file contains a case missing `id`, `persona`, `question`, `kind`, `target`, `args`, or `expected`
- **THEN** the runner fails naming the case and the missing field

#### Scenario: Unknown target is rejected
- **WHEN** a case names a resolver the runner does not register
- **THEN** the runner fails naming the case and the unknown target

### Requirement: Scoring rubric per kind
The runner SHALL score `numeric-exact` cases by comparing the resolver's computed value rounded to 2 decimals against `expected` rounded to 2 decimals (pass iff equal); `evidence-fidelity` cases by checking the named envelope assertions in `expected` (e.g. tier equals, caveat substring present, coverage shape); `abstention` cases by requiring the explicit no-data signal **and** the selector named in the payload or error (pass iff `no_data` is true and the selector appears in the payload or its error) — the conjunction prevents an unrelated no-data envelope from scoring a false pass.

#### Scenario: Numeric-exact compares rounded values
- **WHEN** a numeric-exact case's computed value differs from `expected` after rounding both to 2 decimals
- **THEN** the case fails and the results file records both values

#### Scenario: Abstention requires the explicit signal naming the selector
- **WHEN** an abstention case's resolver returns an envelope with `no_data` true and the selector named in the payload or error
- **THEN** the case passes; a missing selector name or a populated answer fails it

### Requirement: Runner records results
The runner SHALL execute a suite against the current code, score each case by its kind, and write `evals/results/<persona>.json` containing per-case pass/fail, the scored value, and run metadata (timestamp, git short SHA as code version). The results directory SHALL be git-ignored (runs are reproducible from the suite plus code, not archived artifacts).

#### Scenario: Results file is written
- **WHEN** the runner executes a valid suite
- **THEN** `evals/results/<persona>.json` exists with one entry per case and run metadata

### Requirement: Deterministic expectations
`numeric-exact` expectations SHALL be generated from the pinned extract by a checked-in generator script and rounded to 2 decimals; any change in the underlying computation's output SHALL fail the affected cases.

#### Scenario: Regression fails the case
- **WHEN** the underlying computation's output changes
- **THEN** the affected numeric-exact cases fail and the results file records the deviation

### Requirement: Exit-gate suites
Each milestone's golden suite SHALL be added at that milestone's exit gate; the Analyst suite SHALL contain exactly 10 cases at the M2 gate — 4 `numeric-exact`, 3 `evidence-fidelity`, 3 `abstention` — covering forecasting, anomaly, and coverage behaviour.

#### Scenario: Analyst suite exists at M2
- **WHEN** the M2 exit gate runs
- **THEN** the Analyst suite contains exactly 10 cases and all pass
