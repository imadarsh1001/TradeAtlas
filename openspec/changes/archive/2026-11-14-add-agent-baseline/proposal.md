# Proposal

## Why

TradeAtlas's evidence core is deterministic but unreachable from natural language: a buyer asking "what's groundnut running at in Rajkot this week?" has no agent to parse the question, call the right evidence-card tool, and answer from the evidence-card envelopes (the self-describing tool outputs defined by the `evidence-cards` capability, implemented as `EvidenceEnvelope` in `tradeatlas/models.py`). M3 (docs/ROADMAP.md) calls for two builds with a promotion gate — Build 1 is the single agent over the evidence-card tools, and nothing downstream (golden buyer cases, HITL, specialist promotion) can be measured until it exists and produces run records. This change delivers Build 1 with its observability substrate.

## What Changes

- Add a single LangGraph agent bound to the same seven evidence-card tools the MCP server exposes (daily mandi prices, benchmark hub summary, spot weekly prices, macro supply balance, delivered cost, price anomalies, series coverage).
- All model→system communication flows through Pydantic schemas: tool arguments come from validated tool-call structures (never prose parsing), and the final answer is a validated structured object whose figures each carry their source tool and selector (the tool arguments identifying the data slice — state, commodity, market, date). These are the proposal-level name for the two `Structured *` requirements in the agent-baseline spec.
- Untrusted-data hygiene: tool-result envelopes (and anything fetched from live APIs) are data, never instructions; envelope content is never concatenated into agent instructions; the system prompt is versioned and carries this contract (flagged by a pre-M3 security review of the MCP layer as an indirect prompt-injection surface).
- Run records: every agent run writes a JSON record with pinned model id + prompt version + code version, per-tool-call telemetry (arguments, latency, attempt index), and token usage from the model's usage metadata.
- Offline replay: a recorded message trace format plus a scripted model that replays it through the graph, so agent behaviour is testable deterministically with no network and no live model calls.
- A CLI entry point (`python -m tradeatlas.agent "question"`) for manual runs that emits a run record.

Out of scope (this change is **M3-a**, the first of four planned M3 slices labelled M3-a…M3-d in these artifacts, mapping to the ROADMAP M3 deliverables in order): the buyer/adversarial golden suites (M3-b), human-in-the-loop (HITL) clarification via `interrupt()` — LangGraph's pause-for-input mechanism (M3-c), the multi-agent build and deterministic evidence verifier with its retry budget (M3-d), and methodology retrieval-augmented generation (RAG) (stretch).

## Capabilities

### New Capabilities

- `agent-baseline`: the single-agent contract — one agent bound to the seven evidence-card tools with structured-output routing, Pydantic-validated tool arguments with no silent substitution, and untrusted-data hygiene for envelope payloads.
- `agent-run-records`: the observability contract — the run-record schema (model/prompt/code versions, per-stage telemetry, token usage), written for every agent run, and the offline-replay mechanism that makes agent behaviour deterministically testable.

### Modified Capabilities

(none — the agent consumes existing tool behaviour; evidence-cards, deterministic-core, and the other five specs are unchanged)

## Impact

- New code: `tradeatlas/agent/` package (tool bindings, graph assembly, structured answer schema, run-record writer, replay machinery, versioned prompts) and `tests/test_agent_*.py`.
- Reused unchanged: `tradeatlas/ingest.py`, `analytics.py`, `calculator.py` (the seven tool functions behind both surfaces — MCP server for external clients, LangChain bindings for the agent; a parity test pins the two tool sets together).
- Dependencies: `langgraph==1.2.20` and `langchain-openai==1.7.4` are already pinned in `pyproject.toml`; no new dependencies.
- Model access: the chat model id is read from configuration (no provider key is required for the test suite — replay tests use the scripted model only).
- `evals/runs/` added to `.gitignore` (same rationale as `evals/results/`: reproducible from code + config, not archived).
