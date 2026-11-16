# Design: add-llm-gateway-model-registry

## Context

`build_chat_model` (`tradeatlas/agent/graph.py`) is the single live-model construction point: `_AgentChatModel(model=..., timeout=300.0, max_retries=1)` with no explicit base_url/key — it inherits `OPENAI_BASE_URL`/`OPENAI_API_KEY` via langchain-openai env defaults. The provider sandbox (`experiments/llm_endpoints_test/models_config.py`) already proves the Cloudflare AI Gateway construction against the real account: `https://gateway.ai.cloudflare.com/v1/{account}/{gateway}/{route}` + `cf-aig-authorization: Bearer` header, BYOK via an httpx request hook that strips `Authorization` (Cloudflare injects stored keys), per-entry params, RPM metadata. Cloudflare docs: gateway rate limiting is dashboard-level and returns a bare 429 (no documented Retry-After), so client-side pacing is the primary defense. The runner (`evals/runner.py`) has zero pacing/429 handling today; the resume seam is the Python-level `case_ids` filter. `.env` already carries `CF_ACCOUNT_ID`, `CF_GATEWAY_ID`, `CF_AIG_TOKEN`, `CF_WAI_TOKEN`, `NVIDIA_API_KEY`. `pydantic-settings`, `python-dotenv`, `langchain-google-genai`, and `httpx` are already declared dependencies (currently used only by the sandbox).

## Goals / Non-Goals

**Goals:**
- One registry owns every live-model decision: which models exist, which are enabled, how they are reached and called, and their rate limits.
- All agent LLM traffic flows through the gateway (unified logging/analytics/BYOK), with no direct-provider fallback.
- The eval runner survives provider misbehaviour: pacing, bounded retries, skip-and-continue, daily-cap projection, and a persisted per-run evidence ledger for drop decisions.

**Non-Goals:**
- Auto-dropping models (the ledger informs; the human decides).
- Benchmark resumption itself (separately gated on protocol-v2 approval).
- Any change to the `experiments/` sandbox.
- M3-d retry budget for model-behaviour failures (transport retries only).

## Decisions

- **D1 — Registry is a Python module (`tradeatlas/agent/model_registry.py`), not JSON+manifest.** The sandbox registry is already a Python dataclass list; porting it verbatim keeps per-entry comments that explain *why* a model is disabled (the notes are the governance), and avoids manifest churn every time an `enabled` flag flips (JSON in `config/` is sha256-pinned by tests). Precedent: prompts are Python constants. Alternative rejected: `config/model_registry.json` — discoverable, but every toggle would force a manifest regen.
- **D2 — Selector contract: key or model id, enabled-only.** `TRADEATLAS_AGENT_MODEL` keeps its role (the agent-baseline spec's pinned-config requirement) but now must resolve to a registry entry — by key (`groq`) or raw id (`qwen/qwen3.8-27b`). Run records/traces keep naming the raw model id (attribution with committed traces preserved; the key is registry-internal). Ambiguity (a key equal to another entry's id) fails resolution loudly.
- **D3 — Gateway routing mandatory; auth per entry.** `base_url = {gateway}/{route}`, `default_headers = {"cf-aig-authorization": Bearer ...}`. BYOK entries: `api_key="byok"` placeholder + per-model httpx client with the Authorization-strip request hook (sandbox-proven; a fresh client per build keeps timeouts/lifecycles clean rather than one module-level shared client). Non-BYOK entries: the key resolves strictly from the entry's named environment variable (error naming it when unset) — deliberately stricter than the sandbox's `env → cf_wai_token → cf_aig_token` fallback, which could silently send a gateway token as a provider key. Gateway settings required (fail-fast before any case): `CF_ACCOUNT_ID`, `CF_GATEWAY_ID`, `CF_AIG_TOKEN`; `GCP_PROJECT_ID` becomes optional (Vertex-only).
- **D4 — `_AgentChatModel` keeps its `with_structured_output` override; Google gets its own subclass.** The override (non-strict JSON-schema dict + client-side validation) is load-bearing for OpenAI-compatible providers. For Google, `ChatGoogleGenerativeAI.with_structured_output(..., method="json_schema")` maps to Gemini's native `responseJsonSchema`; the same client-side `model_validate` wrapper is appended, so the never-emit-unvalidated contract holds regardless of provider quirks. Google entries ship `enabled=False` ("enable after smoke") — the user explicitly permitted dropping AI Studio by default, and the notebook proved the gateway construction but not the in-agent path.
- **D5 — Timeout becomes per-entry with a 300s default.** The old constant was a benchmark discipline; the owner revised it: entries declare their timeout (NIM entries 45–90s), unset → 300s. A disabled slow model (glm) carries its longer timeout *in its own entry*, so "very long context deep reasoning" later is a one-line enable, not a code change. `max_retries=1` stays a constant.
- **D6 — Ledger is append-only JSONL + a small date-keyed JSON counter.** `evals/results/` is already git-ignored. JSONL survives mid-run kills (one line per completed case; a partial last line is tolerated and ignored on read), unlike the whole-file results JSON the 11-15 pause proved fragile. `usage_daily.json` is rewritten atomically per case (date-keyed request counters per model). Both live beside the existing results files; the runner reads them for daily-cap projection (used_today + avg_touches(entry) > daily_limit → skip case as `daily-cap`), corrected post-case with actual `model_touches` from the record.
- **D7 — Transport vs behaviour failures.** `run_agent` catches everything into `failure_reason`; the runner classifies by substring signatures (`429`, `RateLimit`, `quota`, `APITimeout`/`timeout`, `Connection`, `503`) — the sandbox's proven approach (langchain exceptions do not reliably surface Retry-After). Transport-class → up to 3 attempts with linear backoff (5s before retry 2, 10s before retry 3 — no sleep after the final attempt), then `provider-unavailable` skip-and-continue. Behaviour failures → recorded failed, never retried (the M3-d retry budget owns that).
- **D8 — Pacing between cases only.** The react loop's model touches happen inside langgraph with no pacing hook; pacing applies between cases in the runner: `sleep(max(delay, 60/rpm))`, delay default 45s (protocol §5.2's 30–60s band) via `TRADEATLAS_INTER_CASE_DELAY` or `--delay`. Replay mode performs no pacing.
- **D9 — Runner/orchestration rebuild on live-path entry.** The live path builds its model through `build_chat_model()` (registry-resolved) exactly once per suite and injects it into `_run_agent_case`, preserving the forbidden-live tripwire seam: tests monkeypatch `graph.ChatOpenAI`, and registry construction only happens inside `build_chat_model`, which replay never calls.

## Risks / Trade-offs

- [Daily caps count model requests via ledger projection] → pre-case estimate uses the entry's historical avg touches (default 6 when unknown) and is corrected post-case from `record.model_touches`; documented as an honest approximation, not a provider-counter guarantee.
- [Google `json_schema` support unproven in-agent] → entries ship disabled; the smoke gate (one live case) is required before enabling; fallback `method="json_mode"` + client-side validation preserves the contract.
- [Substring classification can mislabel] → classifications are conservative: only transport signatures trigger retries; an unknown failure records as plain `run failed` (never dropped).
- [BYOK requires keys stored in the Cloudflare dashboard] → documented in methodology; sandbox proved BYOK works for groq/openrouter/google routes.
- [.env load side effects] → the registry loads repo `.env` via python-dotenv once at settings construction; ingest's manual `DATA_GOV_IN_API_KEY` loader is untouched.

## Migration Plan

1. Ship code + tests; `.env.example` documents the new variable names (values stay in the git-ignored `.env`).
2. Live smoke per provider, one case at a time (protocol §5.1): groq (BYOK), cf_workers_ai (non-BYOK), openrouter (50/day counter visible in the usage ledger).
3. Rollback: revert the commit — no data migration (ledgers are additive, git-ignored, and readable by older code only in part).
