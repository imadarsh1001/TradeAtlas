# Tasks: add-llm-gateway-model-registry

## 1. Model registry module

- [x] 1.1 Create `tradeatlas/agent/model_registry.py`: `GatewaySettings` (pydantic-settings; repo `.env` via python-dotenv; `cf_account_id`, `cf_gateway_id`, `cf_aig_token` required, `cf_wai_token`/`nvidia_api_key`/`gcp_project_id` optional, `gcp_region="global"`; `base_gateway_url` + `gateway_headers` properties), `ModelEntry` frozen dataclass (key, provider_type, model, route, enabled, use_byok, api_key_env, rpm_limit, daily_limit, notes, params), `MODEL_REGISTRY` with all 10 sandbox entries ported verbatim plus owner-set `daily_limit` values (groq 500, openrouter_ling_3_2 50, cf_workers_ai 500; google entries disabled with "enable after smoke" notes)
- [x] 1.2 Implement `resolve_model_entry(selector)`: match by key then by model id among entries, unique-match enforced; disabled → RuntimeError naming entry + notes; unknown → error listing enabled keys; verify with unit tests
- [x] 1.3 Implement `build_model_for_entry(entry)`: openai_compat path builds `_AgentChatModel` with `base_url={gateway}/{route}`, gateway headers, BYOK placeholder key + per-model httpx client with Authorization-strip hook, or env-resolved provider key (`env → cf_wai_token → cf_aig_token`, named error when empty), `**entry.params`, timeout from params else 300.0, `max_retries=1`; google paths build `_GoogleAgentChatModel` per the notebook-proven construction; verify with construction-only tests (no network)

## 2. Agent graph integration

- [x] 2.1 Move `_AgentChatModel` construction behind the registry: `build_chat_model(model_id=None)` resolves the selector via `resolve_model_entry` and delegates to `build_model_for_entry`; `get_model_id()` error text names the registry contract; signature and callers unchanged
- [x] 2.2 Add `_GoogleAgentChatModel(ChatGoogleGenerativeAI)` with the same structured-output contract (schema sent non-strict via `method="json_schema"`, client-side `model_validate` wrapper) — Google entries stay disabled until smoked
- [x] 2.3 Add `model_touches` to `RunRecord` and populate it in `run_agent` (the run's model messages plus the structured-response call on runs that reach it — langgraph returns that touch outside state messages; failed-mid-loop runs report only the messages they made); update run-record tests

## 3. Ledger module

- [x] 3.1 Create `evals/ledger.py`: `record_case_outcome()` appends one JSONL line per live case to `evals/results/run_ledger.jsonl` (ts, model_key, model_id, persona, case_id, outcome classification, duration_s, model_touches, total_tokens, failure_class) tolerating a partial trailing line on read; `usage_today(model_key)`/`record_usage(model_key, touches)` maintain date-keyed counters in `evals/results/usage_daily.json` (atomic rewrite); `daily_cap_reached(entry)` projects `used_today + avg_touches(entry) > daily_limit` from ledger history (default 6 touches when unknown)
- [x] 3.2 Implement `history_summary()` reading the JSONL ledger into a per-model table (runs, pass rate, avg duration_s, avg touches, transport-failure count) for drop decisions

## 4. Runner integration

- [x] 4.1 Add failure classification (`_classify_failure`): transport signatures (429/RateLimit/quota/timeout/connection/503) → `transport`; anything else → `behaviour`; replay mode unaffected
- [x] 4.2 Live-case execution policy: transport-class failures retry up to 3 attempts with linear backoff (5s, 10s before retries 2 and 3), then the case is recorded as `provider-unavailable (retryable)` and the suite continues; behaviour failures score `run failed` unretried; daily-cap projection skips a case before it runs (classified `daily-cap`); every outcome appends to the run ledger
- [x] 4.3 Pacing: sleep `max(delay, 60/rpm_limit)` between live cases (delay default 45s from `TRADEATLAS_INTER_CASE_DELAY` or CLI `--delay`); replay mode performs no pacing
- [x] 4.4 CLI: `--case-ids a,b,c` (exposes the existing resume filter), `--delay`, `--history` (prints the per-model ledger summary and exits); update runner tests incl. tripwires (replay writes nothing to the ledger)

## 5. Env + docs

- [x] 5.1 `.env.example`: add `CF_ACCOUNT_ID`, `CF_GATEWAY_ID`, `CF_AIG_TOKEN`, `CF_WAI_TOKEN`, `TRADEATLAS_INTER_CASE_DELAY` (names only); re-label the OPENAI_* lines as not used by the agent path
- [x] 5.2 Docs: `docs/BENCHMARK_METHODOLOGY.md` credential contract → gateway contract + BYOK explanation; `docs/BENCHMARK_FINDINGS.md` §5 items 2–4 annotated implemented + timeout-policy revision note; `docs/ROADMAP.md` status line; `docs/LEARNINGS.md` entry; README one-liner

## 6. Gate

- [x] 6.1 Full gate green: `uv run python -m pytest tests/ -q` (check PIPESTATUS after piped tails), `uv run python -m evals.runner analyst` 10/10, `uv lock --check`
- [x] 6.2 Post-apply review (karpathy lens + EGM agents); fix findings; verify ledger/registry behaviour matches the deltas
