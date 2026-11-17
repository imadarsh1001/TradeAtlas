# run-observability Specification

## Purpose
Live agent runs can be observed — every model call, tool call, token count, and latency captured as traces in an observability backend — while offline verification (replay, CI) stays provably trace-free. Observability is telemetry about runs; it never participates in scoring or gating.

## Requirements

### Requirement: Opt-in tracing for live runs
A live benchmark or agent run MAY emit traces to the observability backend when the operator explicitly opts in via environment variables (tracing toggle, API key, project name). Tracing SHALL be zero-code (env-driven) and attributable: the project name SHALL have a documented convention so runs are findable per persona and campaign. With no opt-in, live runs SHALL behave identically to untraced runs.

#### Scenario: Operator opts in and gets traces
- **WHEN** a live run starts with the tracing env vars set
- **THEN** the run's model calls, tool calls, token usage, and latency are captured as traces under the documented project

#### Scenario: No opt-in changes nothing
- **WHEN** a live run starts without the tracing env vars
- **THEN** the run completes normally with no observability backend calls

### Requirement: Replay and CI never trace
Replay verification mode and the pytest suite SHALL NOT emit observability traces, even when tracing environment variables are set — the suite's zero-network and zero-live-call guarantees extend to observability backends.

#### Scenario: Tracing env vars set during replay are ignored
- **WHEN** replay verification runs with tracing env vars present
- **THEN** no traces are emitted for the duration of the replay run, and the operator's environment is restored afterwards
