# Spec Delta

## Purpose

Every agent run leaves a JSON record — model id, prompt version, code version, per-tool-call telemetry, and token usage — and a recorded message trace can be replayed through the agent offline, so agent behaviour is measurable and deterministically testable without network or live model access.

## ADDED Requirements

### Requirement: Run record for every agent run
The system SHALL write one JSON run record per agent run under `evals/runs/` (a git-ignored directory), containing: a run identifier, started and ended timestamps in UTC, the model id, the prompt version, the code version (git short SHA), and the final structured answer or the failure reason. A run that fails SHALL still produce a record.

#### Scenario: Successful run writes a record
- **WHEN** an agent run completes successfully
- **THEN** a run record exists under `evals/runs/` with the run identifier, UTC timestamps, model id, prompt version, code version, and the structured answer

#### Scenario: Failed run still writes a record
- **WHEN** an agent run fails (for example, answer-schema validation never succeeds)
- **THEN** a run record exists with the failure reason and no answer

### Requirement: Per-stage telemetry in the run record
Each run record SHALL list every tool call made during the run — tool name, arguments as invoked, attempt index (numbered from 1), and latency in milliseconds for executed calls (schema-rejected calls record the validation error and no latency) — and SHALL report token usage (prompt, completion, total) when the model provides usage metadata.

#### Scenario: Tool calls are recorded with attempts
- **WHEN** a run includes a tool call that fails schema validation and a corrected retry that succeeds
- **THEN** the record lists both attempts with their arguments and latencies, and the attempt indices distinguish them

#### Scenario: Token usage is captured
- **WHEN** the model reports usage metadata during a run
- **THEN** the run record contains prompt, completion, and total token counts

### Requirement: Pinned model and prompt versions
Every run record SHALL identify the exact model id and prompt version in effect, and the code version SHALL be the git short SHA recorded by the run. Model id and prompt version SHALL be read from pinned configuration, not hard-coded at call sites.

#### Scenario: Record identifies its configuration
- **WHEN** any run record is inspected
- **THEN** it names the model id and prompt version that produced it, and the code version matches the current git short SHA

### Requirement: Offline replay of a recorded trace
The system SHALL provide a replay mechanism: a recorded message trace (the model's messages of a run, including their tool calls) can be replayed through the agent in place of a live model, with the agent's tools executing normally, no network access, and no live model calls. The replay SHALL produce the same tool-call sequence and the same validated answer on every replay, and the test suite SHALL exercise the agent through replay, never through live model calls.

#### Scenario: Replay is deterministic
- **WHEN** the same recorded trace is replayed twice
- **THEN** both replays produce the same tool-call sequence and the same structured answer; only the run identifier, timestamps, latencies, and token-usage provenance may differ

#### Scenario: Tests run without network or live model
- **WHEN** the agent test suite executes on a machine with no model API access
- **THEN** all agent tests pass using recorded traces only
