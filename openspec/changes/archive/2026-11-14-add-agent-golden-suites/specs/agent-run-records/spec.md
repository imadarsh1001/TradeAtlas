# Spec Delta

## ADDED Requirements

### Requirement: Trace export for benchmark runs
A completed agent run SHALL be exportable as a trace file in the offline replay format (versioned; the model's messages including tool calls, the structured answer, and the question), saved under `evals/traces/<suite>/` and named for the case. An exported trace SHALL load through the existing replay loader and replay to the same tool-call sequence and the same structured answer. Benchmark runs in live mode SHALL export one trace per case.

#### Scenario: Exported benchmark trace replays identically
- **WHEN** a live benchmark run exports a case's trace and that trace is replayed through the agent
- **THEN** the replay produces the same tool-call sequence and the same structured answer as the recorded run
