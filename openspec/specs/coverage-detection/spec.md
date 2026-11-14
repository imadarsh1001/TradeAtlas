# coverage-detection Specification

## Purpose
Deterministic reporting-coverage analysis of the pinned monthly series — what is observed, what is missing, and how stale the tail is — so every comparison built on the data can state its coverage denominator honestly.

## Requirements

### Requirement: Per-state coverage report
Coverage detection SHALL report, for a requested state in the pinned series: the observed month count, the missing months within the series' own date range, the longest consecutive gap (0 when no gap exists), the latest observed month, and the month counts before and after the November 2025 boundary (counted separately, never summed).

#### Scenario: Gap is identified
- **WHEN** a state's series has a missing month between observed months
- **THEN** that month appears in the state's missing-month list and the longest-gap statistic reflects it

#### Scenario: Break counts stay separate
- **WHEN** the coverage report is produced
- **THEN** pre-break and post-break month counts are reported as separate fields, never as a combined total

### Requirement: Trailing staleness
The report SHALL state how many months separate the latest observation from the reference month, defined as the last month of the pinned extract's own date range (deterministic; wall-clock staleness is out of scope for the pinned tool).

#### Scenario: Stale tail is quantified
- **WHEN** a synthetic series' latest observed month precedes its range's last month
- **THEN** the report quantifies the trailing gap in months

### Requirement: Explicit no-data
A requested state with no observations SHALL produce an explicit error naming the selector, never an empty report.

#### Scenario: Unknown state is explicit
- **WHEN** coverage is requested for a state absent from the pinned series
- **THEN** the response is an explicit error naming the state

### Requirement: Evidence-card results and MCP exposure
Coverage results SHALL be returned as an EvidenceEnvelope (deep tier for groundnut Gujarat/Rajasthan from the pinned extract), and a `check_series_coverage` MCP tool SHALL expose the same report.

#### Scenario: Tool returns coverage envelope
- **WHEN** `check_series_coverage` is called for a state in the pinned series
- **THEN** it returns an EvidenceEnvelope whose payload carries the per-state coverage report
