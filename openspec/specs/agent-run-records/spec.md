# agent-run-records Specification

## Purpose
Every agent run leaves a JSON record — model id, prompt version, code version, per-tool-call telemetry, and token usage — and a recorded message trace can be replayed through the agent offline, so agent behaviour is measurable and deterministically testable without network or live model access.

## Requirements

### Requirement: Run record for every agent run
The system SHALL write one JSON run record per agent run under `evals/runs/` (a git-ignored directory), containing: a run identifier, started and ended timestamps in UTC, the model id, the prompt version, the code version (git short SHA), and the final structured answer or the failure reason. A run that fails SHALL still produce a record.

#### Scenario: Successful run writes a record
- **WHEN** an agent run completes successfully
- **THEN** a run record exists under `evals/runs/` with the run identifier, UTC timestamps, model id, prompt version, code version, and the structured answer

#### Scenario: Failed run still writes a record
- **WHEN** an agent run fails (for example, answer-schema validation never succeeds)
- **THEN** a run record exists with the failure reason and no answer

### Requirement: Per-stage telemetry in the run record
Each run record SHALL list every evidence-tool call made during the run — tool name, arguments as invoked, attempt index (numbered from 1), latency in milliseconds for executed calls (schema-rejected calls record the validation error and no latency), and an excerpt of the tool's result text for executed calls (truncated to a bounded length; schema-rejected calls carry no excerpt) — SHALL report token usage (prompt, completion, total) when the model provides usage metadata, and SHALL report the number of model requests (`model_touches`) made during the run — equal to the run's captured model messages, because under the current framework the structured answer is emitted by the final main-loop model call rather than a separate touch. The framework's structured-output tool call (which carries the final answer, not evidence) SHALL NOT appear in the evidence-tool telemetry.

#### Scenario: Tool calls are recorded with attempts
- **WHEN** a run includes a tool call that fails schema validation and a corrected retry that succeeds
- **THEN** the record lists both attempts with their arguments and latencies, and the attempt indices distinguish them

#### Scenario: Token usage is captured
- **WHEN** the model reports usage metadata during a run
- **THEN** the run record contains prompt, completion, and total token counts

#### Scenario: Model touches are counted
- **WHEN** an agent run completes (live or replay)
- **THEN** the record's `model_touches` equals the count of model messages in the run's captured transcript, which includes the final main-loop call that carries the structured answer; a run that fails mid-flight reports only what its captured transcript shows (a lost transcript reports none)

#### Scenario: Executed calls carry a result excerpt
- **WHEN** a run executes a tool call that returns a payload
- **THEN** the record carries a bounded excerpt of that call's result text (the judged faithfulness metric's evidence), while schema-rejected calls carry none

#### Scenario: The structured-output call is not evidence telemetry
- **WHEN** the framework delivers the final answer as a structured-output tool call
- **THEN** that call does not appear in the run record's evidence-tool telemetry (it carries no evidence), while every evidence-tool call does

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

### Requirement: Trace export for benchmark runs
A completed agent run SHALL be exportable as a trace file in the offline replay format (versioned; the model's messages including tool calls, the structured answer, and the question), saved under `evals/traces/<suite>/` and named for the case. An exported trace SHALL load through the existing replay loader and replay to the same tool-call sequence and the same structured answer. Benchmark runs in live mode SHALL export one trace per case.

#### Scenario: Exported benchmark trace replays identically
- **WHEN** a live benchmark run exports a case's trace and that trace is replayed through the agent
- **THEN** the replay produces the same tool-call sequence and the same structured answer as the recorded run
