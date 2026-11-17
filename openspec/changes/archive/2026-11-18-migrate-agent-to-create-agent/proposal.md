# Proposal: migrate-agent-to-create-agent

## Why

`langgraph.prebuilt.create_react_agent` is deprecated since LangChain/LangGraph v1.0 (2025-10-22): the recommended constructor is `langchain.agents.create_agent` with the middleware system. We run it with a deliberately suppressed warning and a documented revisit marker pinned to M3-d — pulled forward here, before M3-c, because M3-c's checkpointer/`interrupt()` integration is framework-coupled: building HITL on the deprecated constructor means re-proving it after a later migration. The migration must RE-PROVE, not re-design: the agent contract (pinned prompt v3, seven evidence tools, validated AgentAnswer, run records, traces, replay) is frozen, and the acceptance gate is the committed 25-case replay reproducing identical outcomes plus live gateway smokes.

## What Changes

- Replace `create_react_agent` with `langchain.agents.create_agent` (`system_prompt=` string, tools passed separately — pre-bound models and `ToolNode` are not accepted).
- Port the structured-output contract: the removed `response_format=(prompt, Schema)` tuple form becomes an explicit strategy (`ToolStrategy(AgentAnswer)` — decision in design.md D1) with client-side `model_validate` retained so an unvalidated answer is never emitted.
- Adopt the new dependency `langchain>=1.0` (dev-versioned in lock alongside the existing langgraph/langchain-openai pins); pin `output_version="v0"` on `ChatOpenAI` if the Responses-API content default changes our parsed content shape.
- Re-point `_GoogleAgentChatModel`'s Gemini handling at the new mechanism: structured output in the main loop may eliminate the trailing-user-turn fix — verified by the vertex smoke, removed only if provably unnecessary.
- Replay architecture: `ScriptedChatModel` stays framework-agnostic (`BaseChatModel`); the replay gate requires the committed 25-case traces to produce IDENTICAL evidence-tool-call sequences and validated answers under the new graph (the framework's structured-output tool call is synthesized at the replay boundary from the trace's validated answer and is not part of the recorded sequence).
- The deprecation warning suppression in `pyproject.toml` is removed; the `langchain.agents` dependency note replaces it.
- **BREAKING (internal)**: the graph-construction seam (`build_agent`) changes signature/behavior; `state["structured_response"]` extraction may move (new state shape per `AgentState`) — run records, traces, and the replay loader format are UNCHANGED (the contract surface).
- **Prompt v4 (owned scope addition)**: ToolStrategy delivers the answer as a tool call — weak models loop on evidence tools instead of delivering unless told. A Delivery directive was added to the system prompt (v3→v4) after the workers-ai recursion evidence; this is a mechanism-enabling prompt change, measured on the live smoke, recorded in the outcome notes. Replay is prompt-agnostic and unaffected.

## Capabilities

### New Capabilities
- *(none — this is a framework modernization of the `agent-baseline` capability; no new external behaviour)*

### Modified Capabilities
- `agent-baseline`: the agent SHALL be constructed via the current recommended framework API (`langchain.agents.create_agent`), preserving every existing requirement — seven-tool parity, structured routing, provenance, untrusted-data hygiene — with the replay contract as the regression gate.

## Impact

- Code: `tradeatlas/agent/graph.py` (construction + state extraction), `tradeatlas/agent/model_registry.py` (`output_version` pin if needed), `pyproject.toml` (+`langchain>=1.0`, warning-filter removal), tests (`tests/test_agent_graph.py`, `tests/test_agent_replay.py`, `tests/test_agent_benchmark.py`).
- Dependencies: +`langchain>=1.0` (the successor package; `langchain-core`/`langchain-openai`/`langgraph` stay pinned).
- Risk surface: the community-reported tool-call-skipping quirk must be explicitly tested; the Gemini trailing-user-turn fix may become dead code (removed only with proof); `ScriptedChatModel` compatibility with the new loop is the critical unknown.
- Verification: 197-test suite green; 25-case replay identical to the recorded verdict (14/15 buyer, 7/10 adversarial); live smokes on vertex + workers-ai + groq (one case each, protocol §5.1).
