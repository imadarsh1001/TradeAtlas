# Tasks: migrate-agent-to-create-agent

## 1. Dependency + construction

- [ ] 1.1 Add `langchain>=1.0` to the project dependencies; `uv lock`; verify `from langchain.agents import create_agent, AgentState` imports alongside the pinned langgraph/langchain-openai
- [ ] 1.2 Rebuild `build_agent` on `create_agent(model, tools, system_prompt=SYSTEM_PROMPT_V3, response_format=ToolStrategy(AgentAnswer), ...)`; pass tools as BaseTool instances (no ToolNode); verify the seven-tool parity test still passes against the new construction
- [ ] 1.3 Remove the `create_react_agent` deprecation suppression (pyproject filterwarnings + comment); add the `langchain.agents` dependency note; sweep for any NEW v1 deprecation warnings and evaluate individually

## 2. Contract ports (the five load-bearing behaviors)

- [ ] 2.1 Structured answer: wire `ToolStrategy(AgentAnswer)` + client-side `model_validate` (never-emit-unvalidated); verify the non-conforming-output test fails the run identically under the new mechanism
- [ ] 2.2 State extraction: locate the structured answer + messages in the new state shape behind `run_agent`'s existing RunRecord surface (records/traces/replay formats unchanged); `model_touches` re-baselined per D2
- [ ] 2.3 Gemini handling: run the vertex smoke FIRST; remove `_ensure_trailing_user_turn` only if the main-loop shape provably needs nothing; re-add if the smoke 400s
- [ ] 2.4 Output-version pin: verify parsed content shape against the fixture transcripts; pin `output_version="v0"` on the chat-model subclasses only if the default changes it
- [ ] 2.5 The quirk test (D5): a multi-tool scripted trace drives EVERY call through the new loop (coverage_retry + a multi-tool trace); document the result

## 3. Acceptance gate

- [ ] 3.1 Full pytest green (197+); the forbidden-live tripwires and replay determinism tests pass on the new graph
- [ ] 3.2 The 25-case replay gate: buyer 14/15, adversarial 7/10 — identical tool-call sequences and outcomes; ANY drift is a D3 blocker reported to the owner
- [ ] 3.3 Live smokes: vertex + workers-ai + groq, one case each (protocol §5.1); ledger rows recorded
- [ ] 3.4 Post-apply review (karpathy lens + EGM axes); fix findings; archive
