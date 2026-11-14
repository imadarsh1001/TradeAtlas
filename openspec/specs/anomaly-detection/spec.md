# anomaly-detection Specification

## Purpose
Deterministic flagging of statistically unusual monthly price observations — robust, explainable, and break-isolated — so sourcing investigations surface genuine market surprises instead of noise, with every result carrying its evidence card.

## Requirements

### Requirement: Robust MAD flagging
Anomaly detection SHALL score each monthly observation that has a computable month-over-month log change within its reporting-break segment using the modified z-score (Iglewicz–Hoaglin: 0.6745·(x−median)/MAD), and SHALL flag observations with |z| > 3.5, reporting the score, month, value, and direction.

#### Scenario: Injected outlier is flagged
- **WHEN** a series contains an observation with a month-over-month change far outside the segment's typical variation
- **THEN** that observation is flagged with |z| > 3.5 and its month, value, score, and direction are reported

#### Scenario: Normal variation is not flagged
- **WHEN** all month-over-month changes lie within the segment's typical variation
- **THEN** no observation is flagged

### Requirement: Segment edge policies
Segment-initial observations (no prior month) SHALL be unexamined. Pairs involving missing values SHALL be skipped and counted in the examined-coverage caveat. A segment with fewer than 6 scored month-over-month changes SHALL yield no flags plus an explicit thin-support caveat, and a degenerate MAD (0) SHALL flag nothing.

#### Scenario: Short segment declines to flag
- **WHEN** a segment has fewer than 6 scored month-over-month changes
- **THEN** no flags are returned and the envelope carries an explicit thin-support caveat

#### Scenario: Segment-initial month is unexamined
- **WHEN** detection runs on a segment
- **THEN** the segment's first month (no prior month) appears in neither the flagged list nor the examined count

### Requirement: Reporting-break isolation
Anomaly scores SHALL be computed within each segment (before November 2025, November 2025 onward); no statistic SHALL pool observations across the boundary (ADR 0001).

#### Scenario: Level shift at the break is not pooled
- **WHEN** the series contains a reporting break and observations differ in scale across it
- **THEN** each segment's median and MAD are computed from its own observations only

### Requirement: Evidence-card results
Anomaly results SHALL be returned as an EvidenceEnvelope stating the method and threshold, coverage as the count of scored changes examined and how many were flagged (segment-initial observations excluded), the deep/thin tier (deep for groundnut Gujarat/Rajasthan from the pinned extract, thin otherwise), and a caveat that a statistical flag is a signal to investigate, not a proven market event.

#### Scenario: Envelope discloses method and coverage
- **WHEN** anomaly detection runs on a series
- **THEN** the envelope's caveats name the robust-MAD method and 3.5 threshold, and coverage states how many scored changes were examined and how many were flagged

### Requirement: Deterministic output
The same input series SHALL always produce the same anomaly results.

#### Scenario: Repeated runs agree
- **WHEN** detection runs twice on the same input
- **THEN** both runs return identical flagged months, scores, and directions

### Requirement: MCP exposure
A `detect_price_anomalies` MCP tool SHALL return the anomaly envelope for a requested state and commodity from the pinned series.

#### Scenario: Tool returns envelope
- **WHEN** the tool is called for a state with series data
- **THEN** it returns an EvidenceEnvelope whose payload carries the flagged observations
