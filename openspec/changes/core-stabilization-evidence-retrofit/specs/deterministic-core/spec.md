# Spec Delta

## Purpose

The `tradeatlas/` deterministic core behaves correctly and reproducibly — cost arithmetic, cache lifecycle, hub matching, supply balance, and HTTP hygiene — and is verified by an offline pytest suite using recorded fixtures, making "deterministic correctness" a tested property rather than a claim.

## ADDED Requirements

### Requirement: Delivered-cost arithmetic
Delivered cost per tonne SHALL equal `(base price ₹/qtl × 10) + freight + ancillary charges`. For groundnut quoted as pods, the kernel-equivalent material cost SHALL equal `(base price ₹/qtl × 10 / 0.70) + decortication allowance`, and pod-case delivered cost SHALL equal that material cost plus freight plus ancillary charges; the valuation basis MUST be reported in the output. All monetary outputs SHALL be rounded to two decimals.

#### Scenario: Whole-seed basis
- **WHEN** a delivered cost is calculated with base price ₹5,000/qtl, freight ₹500/t, ancillary ₹200/t
- **THEN** delivered cost per tonne is ₹50,700 and the valuation basis is the whole-seed basis

#### Scenario: Pod-to-kernel conversion
- **WHEN** a groundnut pod quote of ₹4,000/qtl is converted with a ₹1,500/t decortication allowance
- **THEN** the kernel-equivalent material cost is (₹40,000 / 0.70) + ₹1,500 = ₹58,642.86/t and the basis is labelled as the kernel-equivalent benchmark

### Requirement: Cache freshness lifecycle
A cache key fetched within its TTL SHALL be served from cache without a network call. A key older than the TTL SHALL trigger a live fetch. When the live fetch fails, the previously cached records SHALL be returned rather than an error.

#### Scenario: Fresh cache avoids the network
- **WHEN** a state/commodity key was fetched less than the TTL ago and a query arrives
- **THEN** records are served from cache and no HTTP request is made

#### Scenario: Stale cache triggers refetch
- **WHEN** the cached key is older than the TTL
- **THEN** the tool fetches from data.gov.in and refreshes the cache before answering

#### Scenario: Failed fetch falls back to cache
- **WHEN** the live fetch raises an error or returns a non-200 status
- **THEN** the previously cached records are returned with no exception raised to the caller

### Requirement: Cache upsert isolation and UTC timestamps
Refreshing a cache key SHALL replace that state+commodity's previous records without leaving duplicates, and all cache timestamps SHALL be timezone-aware UTC.

#### Scenario: Refetch leaves no duplicates
- **WHEN** the same state/commodity key is fetched and saved twice
- **THEN** the cache holds only the latest record set for that key

#### Scenario: Timestamps are UTC
- **WHEN** a cache timestamp is written
- **THEN** it is stored as UTC (naive, per the DuckDB TIMESTAMP convention) and any timestamp exposed to consumers is timezone-aware UTC

### Requirement: TLS-verified HTTP clients
Outbound HTTP clients SHALL be constructed with certificate verification enabled; the codebase MUST NOT disable verification (no `verify=False` anywhere in `tradeatlas/`).

#### Scenario: Verification is enabled
- **WHEN** any outbound HTTP client in the package is constructed
- **THEN** certificate verification is on, and a codebase scan finds no `verify=False`

### Requirement: Benchmark hub matching
Hub matching against fetched records SHALL be case-insensitive on market name. A matched hub SHALL report its modal price and MSP spread; an unmatched hub SHALL report an explicit not-reported status while retaining its configured MSP benchmark.

#### Scenario: Hub matched
- **WHEN** the fetched records contain the hub's market name in any casing
- **THEN** the hub entry carries the record's prices and the computed MSP spread with its distress/firm status

#### Scenario: Hub unmatched
- **WHEN** no fetched record matches a configured hub
- **THEN** the hub entry reports not-reported status and keeps the configured MSP benchmark

### Requirement: Supply-balance computation
The harvest supply balance SHALL compare the latest advance production estimate (filtered to official state-season totals) against the mean of the prior crop years (up to three), reporting the percentage and a surplus/deficit status. When no prior crop year exists, the status SHALL be `Baseline Unavailable` with no percentage. Missing estimates SHALL produce an explicit error naming the state and crop, never a fabricated number.

#### Scenario: Surplus computed
- **WHEN** the latest advance estimate exceeds the 3-year baseline
- **THEN** the output reports the percentage above baseline and a surplus status with the crop year and estimation cycle

#### Scenario: Missing estimates error explicitly
- **WHEN** no official estimates exist for the requested state and crop
- **THEN** the response is an explicit error naming the state and crop

#### Scenario: Baseline unavailable
- **WHEN** only one crop year of official estimates exists
- **THEN** the output reports the latest production with status `Baseline Unavailable` and no percentage

### Requirement: Offline-verified suite
The deterministic core SHALL be covered by a pytest suite that runs entirely offline using recorded fixtures, and `uv run pytest` SHALL pass with no network access.

#### Scenario: Suite passes offline
- **WHEN** `uv run pytest` is executed with no network connectivity
- **THEN** every test passes, exercising arithmetic, cache lifecycle, hub matching, and supply balance against recorded fixtures
