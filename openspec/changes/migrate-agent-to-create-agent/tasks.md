# Tasks: migrate-agent-to-create-agent

## 1. Dependency + construction

- [x] 1.1 Add `langchain>=1.0` to the project dependencies; `uv lock`; verify `from langchain.agents import create_agent, AgentState` imports alongside the pinned langgraph/langchain-openai
- [x] 1.2 Rebuild `build_agent` on `create_agent(model, tools, system_prompt=SYSTEM_PROMPT_V3, response_format=ToolStrategy(AgentAnswer), ...)`; pass tools as BaseTool instances (no ToolNode); verify the seven-tool parity test still passes against the new construction
- [x] 1.3 Remove the `create_react_agent` deprecation suppression (pyproject filterwarnings + comment); add the `langchain.agents` dependency note; sweep for any NEW v1 deprecation warnings and evaluate individually

## 2. Contract ports (the five load-bearing behaviors)

- [x] 2.1 Structured answer: wire `ToolStrategy(AgentAnswer)` + client-side `model_validate` (never-emit-unvalidated); verify the non-conforming-output test fails the run identically under the new mechanism
- [x] 2.2 State extraction: locate the structured answer + messages in the new state shape behind `run_agent`'s existing RunRecord surface (records/traces/replay formats unchanged); `model_touches` re-baselined per D2
- [x] 2.3 Gemini handling: run the vertex smoke FIRST; remove `_ensure_trailing_user_turn` only if the main-loop shape provably needs nothing; re-add if the smoke 400s
- [x] 2.4 Output-version pin: verify parsed content shape against the fixture transcripts; pin `output_version="v0"` on the chat-model subclasses only if the default changes it
- [x] 2.5 The quirk test (D5): a multi-tool scripted trace drives EVERY call through the new loop (coverage_retry + a multi-tool trace); document the result

## 3. Acceptance gate

- [x] 3.1 Full pytest green (197+); the forbidden-live tripwires and replay determinism tests pass on the new graph
- [x] 3.2 The 25-case replay gate: buyer 14/15, adversarial 7/10 — identical tool-call sequences and outcomes; ANY drift is a D3 blocker reported to the owner
- [x] 3.3 Live smokes: vertex + workers-ai + groq, one case each (protocol §5.1); ledger rows recorded
- [x] 3.4 Post-apply review (karpathy lens + EGM axes); fix findings; archive

## Outcome notes (2026-11-18 apply)

- D1 revised from ToolStrategy-only after source verification: ProviderStrategy was REJECTED because create_agent force-adds strict=True for OpenAI-compatible models (installed 1.5.0 factory source) — the wiretap-proven rejection path. ToolStrategy(AgentAnswer) adopted.
- D3 contingency exercised and PASSED: scripted replay drives the new loop via a contract-preserving adaptation — the LAST scripted turn is served as the synthesized AgentAnswer tool call built from the trace's validated structured_response (recorded prose was the old architecture's separate-call artifact; recorded messages never mutated; usage metadata carried over).
- D5 quirk test result: the loop does not skip tool calls; the observed workers-ai failure mode is variance-driven looping (re-calling evidence tools without delivering) — scored honestly by the duplicate-call trajectory invariant; intermittent, not deterministic.
- Live smokes: vertex PASS; workers-ai mechanism VERIFIED via runner-conditions debug (structured answer produced and validated; runner smoke variance-exposed); groq blocked by its pre-existing server-side tool-name validation quirk (documented, not migration-caused).
- LESSON: migration-era live smokes ran without trace redirection and CLOBBERED two canonical traces (hub-msp, daily-price) — caught by replay anomalies, restored from git, re-verified. Future smokes must redirect or restore.
