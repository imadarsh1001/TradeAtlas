# Spec Delta: agent-run-records

## MODIFIED Requirements

### Requirement: Per-stage telemetry in the run record
Each run record SHALL list every tool call made during the run — tool name, arguments as invoked, attempt index (numbered from 1), and latency in milliseconds for executed calls (schema-rejected calls record the validation error and no latency) — SHALL report token usage (prompt, completion, total) when the model provides usage metadata, and SHALL report the number of model requests (`model_touches`) made during the run — the react-loop touches plus the structured-response call on runs that reach it — as the input for usage accounting, daily-cap projection, and per-model performance comparison.

#### Scenario: Tool calls are recorded with attempts
- **WHEN** a run includes a tool call that fails schema validation and a corrected retry that succeeds
- **THEN** the record lists both attempts with their arguments and latencies, and the attempt indices distinguish them

#### Scenario: Token usage is captured
- **WHEN** the model reports usage metadata during a run
- **THEN** the run record contains prompt, completion, and total token counts

#### Scenario: Model touches are counted
- **WHEN** an agent run completes (live or replay)
- **THEN** the record reports the react-loop's model messages plus the structured-response call, matching the replayed trace's recorded model-message count plus that touch; a run that fails mid-flight reports only what its captured transcript shows (a lost transcript reports none)
