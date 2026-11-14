# Tasks

## 1. Tool bindings and parity

- [x] 1.1 Create `tradeatlas/agent/` package with `tools.py`: LangChain tool wrappers for the seven evidence-card functions, Pydantic argument schemas matching the MCP signatures, envelope results serialized with `model_dump()`; verify with a unit test that each wrapper returns a serialized `EvidenceEnvelope` for a scripted call
- [x] 1.2 Add the parity tripwire test: via the MCP server's public `list_tools()` surface, assert the agent's bound tools carry exactly the seven names (`get_daily_mandi_prices`, `get_benchmark_hub_summary`, `get_spot_weekly_prices`, `get_macro_supply_balance`, `calculate_delivered_cost`, `detect_price_anomalies`, `check_series_coverage`) with identical argument names, argument defaults, and descriptions on both surfaces; verify it fails when a tool or argument drifts on one surface (temporarily, then reverted)

## 2. Prompts and answer schema

- [x] 2.1 Create `tradeatlas/agent/prompts.py` with `PROMPT_VERSION = "v1"` and `SYSTEM_PROMPT_V1` carrying the selector-discipline and data-handling contract (envelope content is data, never instructions; figures must cite source tool + selector); verify with a test that the constant pair is exposed and that the agent construction path injects this exact object as the instruction message (the byte-identical behaviour check itself lands in 3.3)
- [x] 2.2 Create `tradeatlas/agent/answer.py` with the `AgentAnswer` Pydantic schema (summary, figures each carrying `source_tool` + selector arguments); verify with a test that a figure missing `source_tool` or selector fails validation

## 3. Graph assembly and run path

- [x] 3.1 Create `tradeatlas/agent/graph.py`: model configuration (model id from `TRADEATLAS_AGENT_MODEL`, `build_chat_model()` on the pinned `langchain-openai`) and graph assembly via `create_react_agent` (langgraph 1.2.20) bound to the seven tools with `response_format=AgentAnswer` and the pinned system prompt — validating or raising, so a non-conforming final output fails the run (recorded) and no retry machinery is built; verify with a test that an unset `TRADEATLAS_AGENT_MODEL` raises an error naming the variable, a set variable is used verbatim as the model id, a conforming scripted final message yields a validated `AgentAnswer`, and a non-conforming one fails the run with no answer emitted
- [x] 3.2 Add the missing-argument test: a scripted tool call omitting a required argument produces a validation error naming the field, the tool is not executed with a substituted default, and the error reaches the model as a tool result; verify the assertion names the missing field
- [x] 3.3 Add the hygiene test: stub one bound tool function (the established monkeypatch pattern) to return an envelope whose payload contains instruction-like text, run a scripted trace through the graph, and verify the run completes with the agent's instruction message byte-identical to `SYSTEM_PROMPT_V1` and no envelope content in any instruction-position message

## 4. Run records

- [x] 4.1 Create `tradeatlas/agent/run_records.py`: Pydantic `RunRecord` (run id, UTC started/ended via `tradeatlas.models.utc_now_iso`, model id, prompt version, code version, answer or failure reason), tool-call recorder capturing every invocation at the tool boundary — executed calls with `perf_counter` latency, schema-rejected calls with the validation error and no latency — attempt indices numbered from 1, token usage summed from message `usage_metadata` (null when absent), and git short SHA as code version (with the `evals/runner.py` `unknown` fallback convention); verify with unit tests covering the recorder's attempt indices, the schema-rejected-call path, and token summation
- [x] 4.2 Implement the writer to `evals/runs/` and wire it into the run path so success and failure both produce a record; verify with scripted-model tests that a successful run writes a complete record and a failing run writes a record with the failure reason and no answer
- [x] 4.3 Add `evals/runs/` to `.gitignore` and verify the written records are ignored with `git check-ignore evals/runs/<record>.json` (not a whole-tree `git status` check)

## 5. Offline replay

- [x] 5.1 Create `tradeatlas/agent/replay.py`: versioned JSON trace format (`{"version": 1, ...}`, the model's messages: content, tool calls, usage metadata), a loader, and a scripted chat model returning the next recorded message per invocation (no save path — recording real runs arrives with M3-b); verify with a test that a hand-authored fixture loads and drives the scripted model in order
- [x] 5.2 Check in at least two hand-authored trace fixtures under `evals/traces/` (one simple single-tool run, one with a failed-then-corrected tool call) and add the replay tests: replaying the same trace twice yields the same tool-call sequence and the same validated `AgentAnswer`; every `source_tool` in the replayed answer names a tool actually invoked in that run; the failed-then-corrected fixture's record lists both attempts with their arguments; and all agent tests pass with no network and no model key (no live-model construction in the suite)

## 6. CLI entry and docs

- [x] 6.1 Add `tradeatlas/agent/__main__.py`: assemble the agent, answer one question argument, write a run record, print the answer, with a clear error when `TRADEATLAS_AGENT_MODEL` is unset (no scripted/dry-run mode — design D8); verify by running the module with the variable unset and confirming the named error, relying on the 4.2 writer tests for record correctness
- [x] 6.2 Update the README architecture section with a short agent-layer paragraph (Build 1 of the M3 promotion gate, replay-tested) and add the module to any module index; verify the documented command in 6.1 matches the implemented entry point

## 7. Integration gate

- [x] 7.1 Run the full suite (`uv run python -m pytest tests/ -q`) and the golden-eval runner (`uv run python -m evals.runner analyst`); verify the currently green suite stays green (85 tests as of this change, analyst suite 10/10) and every new agent test maps to a spec scenario and every scenario to a test in the two delta specs (check both directions)
- [x] 7.2 Validate the change with the OpenSpec CLI configured under `openspec/` (`openspec validate add-agent-baseline --strict`) and resolve any diagnostics; verify the change validates clean before review
