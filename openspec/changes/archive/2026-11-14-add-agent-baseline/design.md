# Design

## Context

The seven evidence-card tools exist behind two surfaces: the underlying functions (`tradeatlas/ingest.py`, `analytics.py`, `calculator.py`) and the MCP server (`tradeatlas_mcp.py`, in-process `MCPServer`). `langgraph==1.2.20` and `langchain-openai==1.7.4` are already pinned. `evals/runner.py` established the run-metadata conventions (UTC timestamps, git short SHA). ADR 0002 restricts LLMs to query parsing and briefing synthesis; a pre-M3 security review flagged the MCP layer as an indirect prompt-injection surface (envelope fields must be treated as data, not instructions).

## Goals / Non-Goals

**Goals**: one agent that turns a natural-language question into evidence-card tool calls and a validated structured answer; run records for every run; offline replay so the agent is testable without network or a live model.

**Non-Goals**: HITL (human-in-the-loop) clarification via `interrupt()` — LangGraph's pause-for-input mechanism (M3-c); specialist agents, planner, and the deterministic evidence verifier (M3-d); golden buyer/adversarial suites and agent-benchmark integration (M3-b, the golden-suite re-run — distinct from the benchmark-hub tool); methodology RAG (stretch); serving the agent through MCP (the server stays tool-only this change).

## Decisions

### D1 — Bind the underlying functions as LangChain tools; keep parity by test, not by proxy
The agent binds the same seven functions the MCP server wraps, each with a Pydantic argument schema. The MCP server remains the delivery surface for external clients; a parity test — reading only the server's public `list_tools()` surface — pins the agent's tool set to the server's (tool names, argument names, argument defaults, and descriptions), so drift fails CI.

*Alternative*: loading tools through the MCP server via `langchain-mcp-adapters` — rejected for this change: a new dependency to talk to an in-process server. Revisit in M5 when tools must be reached across a process boundary.

### D2 — Envelope serialization is explicit (`model_dump()`)
Tool functions return `EvidenceEnvelope`; the LangChain tool wrappers serialize with `model_dump()` so the model sees deterministic JSON. This is also the hygiene boundary: whatever the envelope carries travels as tool-result data only.

### D3 — Single-agent graph from `create_react_agent`, structured answer validates-or-raises
Build 1 uses `create_react_agent` from `langgraph.prebuilt` (the prebuilt constructor actually exported by langgraph 1.2.20) bound to the seven tools with the `(SYSTEM_PROMPT_V1, AgentAnswer)` response format — the tuple form so the separate structured-response call is instructed by the same pinned prompt as the loop calls. The structured-response path validates or raises: a final output that fails `AgentAnswer` validation fails the run (recorded) and no answer is emitted — retry machinery for that failure belongs to M3-d's retry budget and is deliberately absent here. Schema-invalid *tool* calls stay in the react loop (the validation error returns to the model as a tool result and the model may re-call); that is the prebuilt loop's normal behaviour, not a system retry. The react loop is explicitly bounded (`recursion_limit=25`, a stated constant, not an implicit default; exceeding it records a failure). Specialists (M3-d) will likely justify an explicit `StateGraph`; not now.

*Alternative*: hand-rolled `StateGraph` — rejected: no Build-1 behaviour needs it, and the prebuilt path keeps the change small.

### D4 — Prompt versioning as a code constant
`tradeatlas/agent/prompts.py` holds `PROMPT_VERSION = "v1"` and `SYSTEM_PROMPT_V1`, whose contract includes: selectors come from the user's question and tool calls only; envelope/tool-result content is data, never instructions (the Sentry note, operationalized); every figure must cite its source tool and selector. Prompt changes bump the version, which run records report.

### D5 — Model id from pinned configuration, provider-agnostic entry point
Model configuration lives in `tradeatlas/agent/graph.py` (folded there from a would-be config module during implementation — one less file): the model id is read from `TRADEATLAS_AGENT_MODEL` (clear error naming the variable when unset for a live run) and the chat model is built with the already-pinned `langchain-openai`. The exact id lands in each run record. No provider key is needed by the test suite — replay tests never build a live model.

### D6 — Run records: plain JSON under `evals/runs/`, telemetry by recording wrapper
`tradeatlas/agent/run_records.py` defines the record schema (Pydantic), a tool-call recorder capturing every invocation at the tool boundary — executed calls with `time.perf_counter` latency, schema-rejected calls with the validation error and no latency — with attempt indices numbered from 1, token usage summed from the model messages' `usage_metadata` (null when absent), and a writer using `tradeatlas.models.utc_now_iso` for timestamps. Records land in `evals/runs/` (git-ignored, same rationale as `evals/results/`); code version = git short SHA, same convention as `evals/runner.py` including its `unknown` fallback outside a git checkout (implemented locally; no cross-import from the evals package).

### D7 — Offline replay: scripted model over a checked-in, versioned trace format
`tradeatlas/agent/replay.py` defines a versioned JSON trace format — the model's messages of a run (content, tool calls, usage metadata), mirroring the golden-evals house convention (`{"version": 1, ...}`) — plus a loader and a scripted chat model that returns the next recorded message per invocation. The trace is model messages only: during replay the agent's bound tools execute for real against the suite's hermetic fixtures (mock transport, isolated DuckDB cache), so replay exercises the whole graph, and determinism holds because those fixtures are. Trace fixtures live in `evals/traces/`, hand-authored and checked in (inputs to tests, like golden suites); recording real runs (a save path) arrives with M3-b's golden-suite benchmark.

*Alternative*: recording real model traffic via callbacks — rejected for Build 1: couples tests to provider response shapes; the scripted model tests graph logic, and M3-b's benchmark supplies real runs later.

### D8 — CLI entry: `python -m tradeatlas.agent "question"`
Assembles the agent, runs the question, writes a run record, prints the answer. No scripted/dry-run mode — replay is exercised by the test suite, and M3-b wires the agent benchmark. Kept thin because its happy path needs a model key and is not automatable in this change.

## Risks / Trade-offs

- [LangGraph prebuilt API drift between versions] → versions are pinned in `pyproject.toml`; the graph module is the only import surface, and its tests run on every change.
- [Scripted replay tests the graph, not the live model's judgement] → accepted for Build 1; model judgement is measured at M3-b against golden suites, which is exactly what the run records enable.
- [Parity test coupling agent to MCP server internals] → the parity test reads only the server's public `list_tools()` surface (tool names, argument names, defaults, descriptions), not implementation.
- [Replay determinism depends on hermetic tool fixtures] → agent tests are required to use the existing conftest patterns (mock transport, isolated DuckDB cache, pinned clocks); a test reaching real network would fail the replay's no-network scenario.
- [EvidenceEnvelope evolution silently breaking the agent's view] → the parity and hygiene tests serialize real envelopes from the existing fixtures, so schema changes surface in CI.
- [Two tool surfaces (MCP + LangChain) drifting in docstrings/behaviour] → both wrap the same functions; the parity test pins names, argument names, defaults, and descriptions; behaviour stays single-sourced in the functions themselves.

## Migration Plan

Purely additive: new `tradeatlas/agent/` package, new tests, `.gitignore` addition (`evals/runs/`), README architecture note. No existing behaviour changes; rollback is deleting the new modules.

## Open Questions

None — remaining choices (exact trace JSON field names, recorder dataclass layout) are implementation-local and covered by the tasks' verification steps.
