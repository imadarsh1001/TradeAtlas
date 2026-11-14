# Design

## Context

The M3-a agent writes a `RunRecord` per run (structured answer, tool-call telemetry with attempt indices, token usage — arguments stored as invoked) and replays versioned traces (model messages + structured answer) through the real graph under hermetic fixtures. The golden-eval runner scores resolver suites from a registered resolver set (`forecast_group`, `anomaly_result`, `coverage_report`) against the pinned extract. Buyer persona vocabulary (PERSONAS.md): state/mandi comparisons, delivered cost, firm-or-distressed vs MSP, and hard honesty about what the data cannot say. The user's live-model credential is a Groq key (`GROQ_API_KEY` in `.env`, git-ignored) at an OpenAI-compatible endpoint; no Groq-specific code exists or is wanted.

## Goals / Non-Goals

**Goals**: measure the single-agent baseline against buyer and adversarial suites, every score traceable to a run record; keep CI free of live models, network, and cache contamination; make expectations as deterministic as the resolver suites.

**Non-Goals**: HITL `interrupt()` cases (M3-c); the M3-d deterministic verifier — this change's fidelity matching is post-hoc, offline, per-case scoring over finished runs, whereas M3-d adds an in-run blocking verifier with retry budget; specialist comparison (M3-d); methodology RAG; changing any tool or product code.

## Decisions

### D1 — Score run records, never prose
The scored artifacts are the `RunRecord` and its `AgentAnswer`. No string-mining of summaries for numbers. The selector-matching rule is defined once: both the answer figure's selector and the run's recorded tool-call arguments are reduced to schema-canonical form via `canonical_tool_args` (defaults filled, types coerced — `RunRecord` stores arguments as invoked, so recorded calls need canonicalizing too) and compared for exact equality.

### D2 — Two modes, honestly separated
**Live benchmark** (`--agent`) runs the real model per case; **replay verification** (default) replays each case's recorded trace through the real graph and scores it. CI runs replay only. A live model cannot be honestly measured in CI — the machinery is CI-gated; the agent's actual quality is measured in user-triggered benchmark runs whose run records are the M3 exit-gate evidence (a manual gate after apply, tracked in tasks).

### D3 — Expectations are checked-in literals from one generator
The existing `evals/generate_expectations.py` (persona-parametric) is extended: for buyer cases it computes expected numeric literals by invoking the deterministic functions directly (calculator, forecast report, analytics) against the pinned extract and writes them into `expected`. No runtime resolution, no `value_from` indirection — a runtime-resolved expectation drifts together with the agent's answer and passes forever, defeating the regression signal. Drift surfaces two ways: the generator produces a diff at review time, and replay comparison fails at CI time.

### D4 — Hostile payloads enter through the data seam only
Injection cases ship committed hostile-response fixtures served through the established mock-transport pattern, prebound onto the tool services — the data layer is hermetic in BOTH modes; the model is the only live component in a benchmark run. No product code changes to make data hostile.

### D5 — Trace export completes the M3-a replay format
`tradeatlas/agent/replay.py` gains the save path (load-only was M3-a's deliberate scope): writing the versioned format the loader already reads, including usage metadata (a zero-cost projection that keeps replayed run records faithful to the recorded ones). Exporting is a pure projection of the run's state.

### D6 — Hermetic benchmark data: prebind map + cache pinning
Before building the agent, the runner pins, per tool: `fetch_daily_mandi_prices`, `fetch_benchmark_hub_summary`, `fetch_spot_weekly_prices` → `functools.partial(service, transport=...)` over committed fixtures; `fetch_macro_supply_balance` (reads the pinned APY extract) and the pure calculator/analytics functions need no prebinding. Critically, the runner ALSO pins the DuckDB cache to a run-local temp directory for the benchmark's duration (the `isolated_cache` mechanism from conftest, set outside pytest) — otherwise benchmark runs would read the developer's live cache and write mock payloads into it. Both mechanisms act on the same lazy service seam M3-a tests monkeypatch (`tradeatlas.agent.tools` module attributes, resolved at build time).

### D7 — Agent scorers are pure functions; agent cases branch before resolver dispatch
`evals/runner.py` gains `_score_agent_*` functions over `(record, answer, expected)` — unit-testable without running the graph — and `run_suite` routes agent kinds through their own path BEFORE the resolver dispatch (`RESOLVERS[case["target"]]` never sees `agent` targets). Validation for agent kinds enforces per-kind rubric fields and validates tool references against `AGENT_TOOL_NAMES`. Resolver results format unchanged; agent results add mode and disclosure fields (`replayed` count derivable from the `missing_traces` list — one list is kept).

### D8 — Replay-mode trace availability is disclosed, never faked
Exactly 3 cases (one per agent kind, pinned-tool cases chosen first) get hand-authored traces checked in under `evals/traces/<persona>/`; the count is capped because hand traces are high-labor, low-signal machinery checks that benchmark recordings supersede. Replay mode scores cases with traces and discloses the rest (`missing_traces`); the first live benchmark completes the set.

### D9 — Sizing: one change, content-heavy tail
Estimated ~1.8–2.2k lines, near the M3-a precedent (~1.8k total) and above the >1000 heuristic. Kept as ONE change because the suites are data (not code) and splitting would archive spec deltas separate from the content they govern; the cap on hand-authored traces (D8) bounds the highest-cost item. The natural future seam (machinery vs suites) is noted should a follow-up extension grow it again.

### D10 — Credentials: provider-agnostic via the OpenAI-compatible contract
Live mode requires `TRADEATLAS_AGENT_MODEL` plus the standard OpenAI-compatible environment variables (`OPENAI_API_KEY`, `OPENAI_API_BASE`/`OPENAI_BASE_URL`) — for the user's Groq key: `OPENAI_API_KEY=<groq key>`, `OPENAI_BASE_URL=https://api.groq.com/openai/v1`. No provider-specific code, no new env-var plumbing; `.env.example` gains the names (never values) and `docs/BENCHMARK_METHODOLOGY.md` documents the setup. `LANGSMITH_API_KEY` stays inert — the pytest plugin is suppressed and no code reads tracing vars; it is available for optional live-run observability later and is out of scope here.

## Risks / Trade-offs

- [Live-model nondeterminism makes suite results non-reproducible] → per-case run records + traces are the reproducible artifacts; CI gates machinery, not model behaviour; re-running the benchmark re-measures honestly.
- [Benchmark runs cost tokens] → user-triggered only (manual gate in tasks), documented command, 25 cases of bounded spend; no CI spend.
- [Recorded traces are committed fixtures] → model outputs and questions only (no keys, no env); reviewed like any fixture; version-gated loader refuses foreign formats.
- [Replay circularity (scoring our own recordings)] → replay is labeled machinery verification in results and docs; the M3 exit measurement is the live benchmark's run records.
- [Suites drift from real tool names/selectors] → rubric tool references validated against `AGENT_TOOL_NAMES`; expectations generated from the deterministic functions.

## Migration Plan

Additive: suite files, runner extensions, trace-save function, docs. Rollback = revert the runner additions and delete the new files; the M3-a replay loader is untouched.

## Open Questions

None — the live benchmark's model id is a run-time user choice via `TRADEATLAS_AGENT_MODEL` (D10 fixes the credential contract around it).
