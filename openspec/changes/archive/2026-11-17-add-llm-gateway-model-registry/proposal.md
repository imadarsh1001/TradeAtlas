# Proposal: add-llm-gateway-model-registry

## Why

Every live LLM call currently goes straight to a provider through implicit `OPENAI_BASE_URL`/`OPENAI_API_KEY` env defaults, with no pacing, no 429 handling, no daily-cap awareness, and no persisted per-run performance data — the exact gaps that poisoned the first live benchmark campaign (429 storms, provider quirks, no evidence to decide which stacks to drop). The provider sandbox in `experiments/llm_endpoints_test/` has since proven the Cloudflare AI Gateway pattern against the real account (BYOK routing, per-model params, RPM metadata); it is time to productionize that harness so all agent LLM traffic flows through the gateway under config governance, and gentle protocol v2's pacing/daily-cap items (docs/BENCHMARK_FINDINGS.md §5 items 2–4) become enforced behaviour instead of prose.

## What Changes

- NEW `tradeatlas/agent/model_registry.py`: a versioned, code-reviewed model registry — `GatewaySettings` (CF_ACCOUNT_ID / CF_GATEWAY_ID / CF_AIG_TOKEN required; provider keys optional per entry), `ModelEntry` (key, provider_type, model, route, enabled, use_byok, api_key_env, rpm_limit, daily_limit, notes, params), and `MODEL_REGISTRY` porting all 10 sandbox entries with owner-set limits (OpenRouter 50 req/day, Groq 500 req/day, Workers AI 500 req/day, NVIDIA NIM 40 RPM; Google entries ship disabled until smoked).
- `build_chat_model` resolves the selector (registry key or raw model id) through the registry and builds the model from the entry — enabled-only, params honored verbatim, per-entry timeout (default 300s), gateway routing mandatory with `cf-aig-authorization` (BYOK = Authorization stripped so Cloudflare injects stored keys; non-BYOK = env-resolved provider key). No direct-provider fallback.
- Google route support in the agent path: `_GoogleAgentChatModel` (ChatGoogleGenerativeAI via the gateway, notebook-proven construction) with the same structured-output contract — non-strict JSON schema sent natively (`responseJsonSchema`), client-side validation so an unvalidated answer is never emitted. Smoke-gated: entries disabled until a live smoke passes.
- NEW `evals/ledger.py` + runner integration: an append-only JSONL run ledger (`evals/results/run_ledger.jsonl`: per-case duration, model touches, tokens, outcome, failure class) and a date-keyed usage ledger (`evals/results/usage_daily.json`) — so the next benchmark run can show, per model, pass rate / average duration / average touches and the human decides what to drop.
- Runner live-mode resilience: inter-case pacing `max(delay, 60/rpm)` (delay from `TRADEATLAS_INTER_CASE_DELAY`, default 45s); transport-class failures (429 / rate limit / timeout / connection) retried up to 3 attempts with linear backoff, then the case is skipped as `provider-unavailable (retryable)` and the suite continues; pre-case daily-cap projection skips cases that would exceed the entry's `daily_limit` (classified `daily-cap`, resumable via `--case-ids`).
- `RunRecord` gains `model_touches` (count of model requests in the run) — the usage-ledger input.
- Runner CLI gains `--case-ids a,b,c` (exposes the existing Python-level resume filter), `--delay`, `--history` (per-model summary table from the run ledger).
- `.env.example` and docs updated: gateway credential contract replaces the OPENAI_BASE_URL contract for the agent; BENCHMARK_FINDINGS §5 items 2–4 annotated as implemented (timeout policy note: per-entry timeout is an owner-approved revision of item 5's constant).
- **BREAKING** (env contract): live agent runs now require the Cloudflare gateway variables (`CF_ACCOUNT_ID`, `CF_GATEWAY_ID`, `CF_AIG_TOKEN`) and a registry-resolvable `TRADEATLAS_AGENT_MODEL`; a bare provider key + base URL no longer drives the agent.

## Capabilities

### New Capabilities
- `llm-model-registry`: gateway-routed, registry-governed live model construction — enabled-only selection, entry params/rate limits honored, BYOK vs explicit-key auth, Google route support, transport-failure policy.

### Modified Capabilities
- `agent-run-records`: run records additionally report `model_touches` (model request count per run) so usage accounting and pacing decisions work off the record itself.
- `golden-evals`: live benchmark mode's credential contract becomes the gateway contract; results gain rate-limited / daily-cap / provider-unavailable classifications (never silently dropped); CLI gains `--case-ids`, `--delay`, `--history`.

## Impact

- Code: `tradeatlas/agent/model_registry.py` (new), `tradeatlas/agent/graph.py` (delegate), `tradeatlas/agent/run_records.py` (one field), `evals/ledger.py` (new), `evals/runner.py` (pacing/retry/classification/CLI).
- Dependencies: no NEW packages introduced by this change — `pydantic-settings`, `dotenv` (corrected here to the canonical `python-dotenv`), `langchain-google-genai`, and `httpx` were added to pyproject by the uncommitted provider-sandbox work this change productionizes, and become genuinely used by package code; the sandbox-only extras the working tree had added (ipykernel, ormsgpack, xxhash, duckdb pin) are left untouched, out of scope.
- Env contract: `.env` needs `CF_ACCOUNT_ID` / `CF_GATEWAY_ID` / `CF_AIG_TOKEN` (already present in the developer's `.env`); `TRADEATLAS_AGENT_MODEL` must now name an enabled registry entry (key or model id). `OPENAI_API_KEY`/`OPENAI_BASE_URL` remain meaningful only for direct-provider fallbacks outside the agent (none in-repo).
- Docs/tests: BENCHMARK_METHODOLOGY, BENCHMARK_FINDINGS, ROADMAP, LEARNINGS, README; new tests `tests/test_model_registry.py`, `tests/test_evals_ledger.py`; updates to `tests/test_agent_graph.py` and `tests/test_agent_benchmark.py`.
- Out of scope: the `experiments/` sandbox stays untouched; benchmark resumption itself remains gated on protocol-v2 approval (this change is its tooling prerequisite).
