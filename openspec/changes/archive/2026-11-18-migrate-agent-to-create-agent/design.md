# Design: migrate-agent-to-create-agent

## Context

`create_react_agent` (langgraph.prebuilt, langgraph 1.2.20) is deprecated since LangChain/LangGraph v1.0 (2025-10-22) in favour of `langchain.agents.create_agent` + middleware. Our stack carries five wiretap-proven load-bearing behaviors: (1) non-strict json_schema structured output with client-side validation (`_AgentChatModel`/`_GoogleAgentChatModel`), (2) the `response_format=(prompt, Schema)` tuple semantics, (3) ToolNode parallel-thread cache serialization (cache.py write lock), (4) the Gemini trailing-user-turn fix, (5) canonical-args pairing. The migration must preserve the CONTRACT (prompt v3, seven tools, validated AgentAnswer, records/traces/replay formats) while re-proving all five on the new architecture. Known migration hazards from the official guide + community reports: pre-bound models and `ToolNode` rejected; `response_format` tuple removed (replaced by `ToolStrategy`/`ProviderStrategy`, generated in the main loop); state schemas restricted to TypedDict (`langchain.agents.AgentState`); a reported quirk where the new loop sometimes skips tool calls; `langchain-openai` Responses-API content default change.

## Goals / Non-Goals

**Goals:** land the current recommended framework API; keep measured behaviour bit-identical (replay gate); unblock M3-c's middleware-native HITL (`HumanInTheLoopMiddleware` exists in the new system).

**Non-Goals:** any behaviour change beyond the mechanism-required prompt adjustment (see D7 — the ToolStrategy delivery directive is enabling, not behavioural tuning); scoring unchanged; new features; adopting `langchain-classic`; migrating the MCP server layer.

## Decisions

- **D1 — Strategy: `ToolStrategy(AgentAnswer)`, decided on installed-source evidence.** `ProviderStrategy` was REJECTED after reading installed langchain 1.5.0 source: create_agent force-adds `strict=True` for OpenAI-compatible models regardless of `ProviderStrategy(strict=False)` — the wiretap-proven rejection path.** The old strict-json_schema rejections (Groq/Gemini 400s — wiretap-proven) came from provider `response_format` handling; `ProviderStrategy` is exactly that mechanism, so it re-introduces the rejected path. `ToolStrategy` produces the structured answer via a tool call — sidesteps provider response_format entirely and matches how the react loop already works. Client-side `model_validate` stays as the final gate (never-emit-unvalidated, unchanged). **Fallback:** if ToolStrategy misbehaves on any registry provider (e.g. double-tool-call confusion), the per-provider decision is revisited with smoke evidence before merging — not tuned silently.
- **D7 — Prompt v4 delivery directive (owned scope addition).** Under ToolStrategy the model must CALL the AgentAnswer tool to deliver; weak models (glm-4.7-flash) loop on evidence tools instead — measured: 24 evidence calls, 0 AgentAnswer attempts, GraphRecursionError. A Delivery directive was added to the system prompt (v3→v4) after the official structured-output docs confirmed no automatic instruction injection exists. Evidence: the workers-ai hub case then produced and validated a structured answer. Replay is prompt-agnostic (scripted), so the 25-case gate is unaffected.
- **D2 — Main-loop structured output removes the separate structured call.** Consequences: (a) the Gemini trailing-user-turn fix likely becomes dead code — removed ONLY after the vertex smoke proves the new shape needs nothing; (b) `model_touches` counting changes shape (no separate structured touch — the main-loop call IS the structured one); the replay traces' recorded model-message counts must be re-baselined: the committed 25 traces were recorded under the old shape, so replay under the new graph re-baselines touch counts per trace (the replay gate compares tool-call sequences and validated answers — NOT touch counts, which the spec exempts as provenance).
- **D8 — Replay synthesis at the boundary (the D3 contingency, exercised).** ScriptedChatModel serves the LAST recorded turn as a synthesized AgentAnswer tool call built from the trace's validated `structured_response` — the recorded prose content was the old architecture's separate-call artifact that ToolStrategy cannot consume. Recorded messages are never mutated; usage metadata is carried over; the evidence-tool-call sequence is unaffected; the walker excludes the structured call from telemetry. The gate remains fail-capable: tampering with the trace's structured_response flows through ToolStrategy validation and run_agent re-validation to a recorded failure.
- **D3 — Replay is the migration's acceptance gate.** `ScriptedChatModel` stays a `BaseChatModel`; the committed 25 traces replay through the NEW graph and must produce identical tool-call sequences and identical validated outcomes (buyer 14/15, adversarial 8/10). If the new loop's message flow differs such that scripted replay cannot drive it, that is a BLOCKER reported to the owner — not papered over by rewriting traces (the traces are the measured evidence; rewriting them would make the migration self-graded).
- **D4 — Dependencies.** Add `langchain>=1.0` (successor package). Keep `langgraph` pinned (create_agent returns a langgraph graph; checkpointer/interrupt for M3-c remain langgraph mechanisms). `output_version="v0"` pinned on `_AgentChatModel`/`_GoogleAgentChatModel` only if the Responses-API default changes parsed content shape — verified during implementation against the fixture transcripts, not assumed.
- **D5 — The quirk test.** The community-reported tool-call-skipping behaviour gets an explicit test: a scripted trace with multiple sequential tool calls must drive every call through the new loop (the existing `coverage_retry` trace plus a multi-tool trace serve as the harness). Failing this = migration blocked pending a workaround (middleware `wrap_model_call` investigation), reported to the owner.
- **D6 — Warning hygiene.** Remove the `filterwarnings` entry for the old deprecation (no longer importable-path relevant) and the pyproject comment; add the `langchain` dependency note. Any NEW deprecation warnings from v1 packages are evaluated on arrival, not blanket-suppressed.

## Risks / Trade-offs

- [Scripted replay may not drive the new loop] → D3 blocker path: report, do not fake. Fallback research: `wrap_model_call` middleware or a hand-built graph — owner decides.
- [ToolStrategy changes answer emission shape (tool call vs JSON)] → client-side validation unchanged; replay gate catches outcome drift.
- [Gemini trailing-turn fix removal regression] → vertex smoke BEFORE removing the mapper; re-add if the smoke 400s.
- [State extraction moves (`structured_response` key)] → run_agent's extraction updated behind the same RunRecord surface; records/traces/replay formats unchanged (contract surface).
- [The 25 traces embed old-graph message shapes] → replay only requires AIMessage tool_calls + structured_response; format-agnostic by design.

## Migration Plan

1. Implement on a branch-like working state; full pytest + 25-case replay gate green.
2. Live smokes: vertex, workers-ai, groq (one case each, protocol §5.1).
3. Commit; the deprecated constructor and its warning suppression disappear together.
4. Rollback: revert the commit — the old constructor returns with its pinned stack intact.
