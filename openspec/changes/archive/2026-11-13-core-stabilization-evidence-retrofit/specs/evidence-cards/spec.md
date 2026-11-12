# Spec Delta

## Purpose

Every TradeAtlas tool output is a self-describing evidence card disclosing data age, coverage, scope tier, and caveats, so no consumer — trader, agent, or dashboard — can mistake stale, thin-tier, or gapped data for verified intelligence (the ADR 0002 discipline applied to the live layer).

## ADDED Requirements

### Requirement: Evidence-card envelope on every tool output
Every TradeAtlas tool (daily mandi prices, benchmark hub summary, spot weekly prices, macro supply balance, delivered cost) SHALL return an evidence-card envelope containing at minimum: the result payload, the observation date(s) of the underlying data, the retrieval timestamp in UTC, a coverage statement, a scope tier label, and any applicable caveats. Observation date and retrieval timestamp MUST be distinct, separately named fields.

#### Scenario: Daily mandi prices return a self-describing envelope
- **WHEN** `get_daily_mandi_prices` is called for a state and commodity
- **THEN** the response includes the price records plus `observation_date`, `retrieved_at` (UTC), `coverage`, `tier`, and `caveats` fields, and `observation_date` is derived from the data (arrival dates), not from the fetch time

#### Scenario: Benchmark hub summary discloses its coverage denominator
- **WHEN** `get_benchmark_hub_summary` is called
- **THEN** the response states how many configured hubs are reporting and how many are monitored, alongside the per-hub details

### Requirement: Deep/thin tier labelling
Tool outputs SHALL carry a tier label reflecting the verification guarantee: groundnut for Gujarat and Rajasthan is `deep`; soybean, mustard, and groundnut outside the proof states are `thin`. Thin-tier responses MUST include an explicit unverified-coverage caveat.

#### Scenario: Thin-tier commodity is labelled
- **WHEN** a mustard price query is served for any state
- **THEN** the response is labelled `thin` and includes a caveat stating coverage has not been verified

#### Scenario: Deep-tier commodity is labelled
- **WHEN** a groundnut query is served for Gujarat or Rajasthan
- **THEN** the response is labelled `deep`

### Requirement: Tier for state-less and input-only tools
Tools whose selectors cannot identify a state+commodity pair SHALL be labelled `thin` (numeric AGMARKNET IDs cannot establish proof-state coverage). Tools that compute purely on user-supplied inputs without fetched data (delivered cost) SHALL report no observation date, coverage "user-supplied inputs", and tier `deep` — their guarantee is deterministic arithmetic verified by the test suite, not live-data verification.

#### Scenario: Spot-weekly prices are thin
- **WHEN** `get_spot_weekly_prices` is called with numeric market/state/commodity IDs
- **THEN** the response is labelled `thin` with the unverified-coverage caveat

#### Scenario: Delivered cost is input-only deep
- **WHEN** `calculate_delivered_cost` is called with buyer-supplied prices
- **THEN** the envelope has no observation date, coverage "user-supplied inputs", tier `deep`, and no live-data caveat

### Requirement: Coverage statement content
Each envelope's coverage statement SHALL report the number of records returned and the selector it applies to; a denominator SHALL be included only where a configured denominator exists.

#### Scenario: Record count with selector
- **WHEN** a daily-price query returns N records
- **THEN** the envelope's coverage states "N records for (state, commodity[, market, date])"

#### Scenario: Denominator where configured
- **WHEN** the benchmark hub summary is served
- **THEN** coverage includes hubs reporting out of hubs monitored

### Requirement: Cache-age disclosure
When a response is served from the DuckDB cache, the envelope SHALL disclose the cached-as-of time in UTC so consumers can judge staleness independently of the fetch.

#### Scenario: Cached response shows its age
- **WHEN** a query is answered from cache without a live fetch
- **THEN** the envelope includes the original fetch timestamp (`cached_as_of`) and the current retrieval timestamp, both UTC

### Requirement: No silent gaps
When a query matches no records — a hub not reporting today, a state/commodity/date with no data — the tool SHALL return an explicit no-data statement (including which selector matched nothing) rather than an empty list or an omitted field.

#### Scenario: Unreported hub is explicit
- **WHEN** a configured benchmark hub has no record for the queried day
- **THEN** its entry states it was not reported (with the hub's district and MSP benchmark retained) instead of being silently absent

#### Scenario: Empty result set is explicit
- **WHEN** a state/commodity combination matches zero records
- **THEN** the response contains an explicit no-data message naming the selectors, not an empty list

### Requirement: Caveats travel with derived numbers
Derived figures — kernel-equivalent prices, supply-balance percentages, MSP spreads — SHALL carry their basis caveat (70% shelling-outturn benchmark; latest advance estimate vs. 3-year baseline; MSP comparison basis) inside the same output.

#### Scenario: Pod-to-kernel conversion states its basis
- **WHEN** a delivered-cost calculation uses the pod→kernel conversion
- **THEN** the output includes the valuation basis ("Kernel Equivalent Benchmark, 70% shelling outturn") and the decortication allowance used
