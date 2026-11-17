# Agent Benchmark — Live-Run Findings (2026-11-14/15)

Findings from the first live benchmark campaign (`add-agent-golden-suites`, paused mid-run by decision — see [BENCHMARK_METHODOLOGY.md](BENCHMARK_METHODOLOGY.md) for the protocol and [ROADMAP.md](ROADMAP.md) status). Every product fix below is committed and regression-tested; the benchmark run itself is **incomplete and paused** — its resumption follows the gentle protocol (below), not a restart.

## 1. Provider stack matrix (smoke + partial suite evidence)

| Stack | Smoke (1 case) | Suite evidence | Verdict |
| --- | --- | --- | --- |
| NVIDIA `z-ai/glm-5.3-flash` | ✅ 4 figures, investigative (3 daily calls + hub) | **11/15 buyer cases recorded** before pause; 7–15 min/case (deep reasoning chains) | Strongest candidate; slow per turn |
| OpenRouter `nvidia/nemotron-3-ultra-550b-a55b:free` | ✅ fast, correct figure | not suite-run yet | Promising; fast |
| Groq `qwen/qwen3.8-27b` | ⚠️ intermittent | 2 of 3 probes 400'd; 1 smoke passed (variance) | **Server-side tool-call validation**: a model tool call with malformed args is rejected with HTTP 400 before our react loop can recover it — unrecoverable per run |
| Gemini `gemini-3.5-flash` | ⚠️ schema OK solo (raw API 200), in-agent 400 with empty message | 0/25 recorded — but poisoned: mostly 429s from my parallel orchestration + the DuckDB conflict (§3), not model quality | Needs a solo paced re-run after the fixes |
| OpenRouter `thinkingmachines/inkling-2-small:free` | ❌ HTTP 403 | — | Model id not accessible on the account |

**Meta-finding: provider endpoints differ in how much model sloppiness they forgive.** Groq validates tool-call arguments server-side (malformed call ⇒ HTTP 400 ⇒ dead run); the OpenAI-style path returns the call and lets our loop handle it. The benchmark measures the *model + provider stack*, not the model in isolation — that is a feature of the measurement, and it is why a smoke pass is mandatory before any suite.

## 2. Product fixes the campaign forced out (all committed, regression-tested)

1. **Structured-output provider compatibility** (`tradeatlas/agent/graph.py`): langchain-openai coerces Pydantic schemas to strict json_schema; strict mode requires `additionalProperties: false` on every object, which the answer contract's free-form `selector` cannot satisfy (Groq 400s the schema outright; Gemini behaves similarly in-agent). `_AgentChatModel.with_structured_output` now sends the JSON-schema **dict** with `strict=False` and validates client-side against `AgentAnswer` — an unvalidated answer is still never emitted (M3-a contract). Verified: raw API 200 with the untouched schema.
2. **DuckDB catalog write-write conflict** (`tradeatlas/cache.py`): `get_db_connection` ran `CREATE TABLE IF NOT EXISTS` on *every* connection; langgraph's ToolNode executes a model's multiple tool calls **on parallel threads** → two concurrent connections running catalog DDL on one file → `TransactionException`. Schema init is now once-per-database-file under a lock, and cache writes are serialized process-wide. Regression test: four threads hammering save+read concurrently (`test_parallel_tool_calls_do_not_conflict`).
3. **Bounded request latency** (`graph.py`): a provider call hung 45+ minutes mid-benchmark. `build_chat_model` now sets `timeout=300, max_retries=1` — hung calls fail and are recorded; legitimate slow turns (glm runs 1–2 min/turn) survive. Tuning note: 120s was too tight (4 legit runs timed out); 300s held.
4. **Resumable benchmarks** (`evals/runner.py`): `run_suite(case_ids=...)` + CLI resume — a paused/killed run resumes exactly where it stopped instead of re-spending completed cases.

## 3. Orchestration lessons (process, not code)

- **Never run two provider suites in parallel.** The Gemini comparison was 90% 429-rate-limit failures because three free-tier providers were hammered simultaneously; free-tier limits are per-account and unforgiving. One provider at a time, always.
- **Live traces supersede hand-authored placeholders** — by design (D8), and it bit twice: the canonical run overwrote two hand-authored replay fixtures with real (failing) traces, and a simulation test once committed an orphan trace into the repo tree. The `traces_dir` seam (tests use tmp; the canonical run writes the committed set) is the guard — respect it.
- **Derive expectations from the real service, never hand-assume.** The daily fixture's first record after the DuckDB round-trip is Veraval (7650), not Dahod (7200); the hub derivation silently read the developer's live cache until cache pinning was added to the generator too.
- **Selector matching needed the live runs to get right.** Exact dict equality rejected legitimate citations (models enrich figure selectors with record-level provenance: `market: "Veraval APMC"` on a state-level call). The spec now defines **selector agreement** — the executed call's meaningful keys must be stated by the figure's selector; record-level extras are permitted; a contradicted value (an invented commodity, a wrong figure) fails. Real failure kept honest: glm's delivered-cost-kernels answer cited the *input* price with an invented selector — the case fails.

## 4. Partial canonical results (nvidia `z-ai/glm-5.3-flash`, 11/15 buyer recorded, paused)

Recorded cases include correct, buyer-grade work: the hub-MSP case answered *"Firm at Rajkot: modal ₹6,900/qtl is a +₹117 (+1.7%) premium to MSP ₹6,783 — not distressed"* across three tools; the anomaly case answered the "recently" framing sensibly ("the two flagged anomalies are both from 2020; the last 12 months show no flags") — which exposed that the original rubric over-demanded the 2020 flag value; the rubric now accepts any evidence-faithful recency answer. Known failures: one mis-cited delivered-cost figure (correctly scored a fail). The remaining 14 cases (4 buyer + 10 adversarial) are pending the protocol restart; no M3 exit verdict is claimed yet.

## 5. Gentle protocol v2 (proposed — the resumption plan)

1. **One provider per session.** Never two suites in parallel; a smoke case per provider before any suite.
2. **Pacing between cases**: configurable inter-case delay (default 30–60s), and honor `Retry-After` on 429 with exponential backoff instead of recording an immediate failure.
3. **Rate-limit handling in the run path**: a 429 case is marked *rate-limited (retryable)* — the `case_ids` resume filter re-runs exactly those later; nothing is silently dropped and nothing is retried into a ban.
4. **Per-provider daily caps**: stop after N cases/day per provider (free tiers); the resume filter makes multi-day completion cheap.
5. **Timeout is a constant, not a knob to escalate**: 300s stays; a stack that cannot complete inside it is reported as such, not tuned around.
6. **Canonical set definition**: the M3 exit verdict comes from ONE model completing both suites with exported traces committed; other providers are comparison data only (artifacts outside the committed tree).
7. **Order**: finish nvidia-glm (11 recorded → 14 remaining) → nemotron → groq-qwen → gemini solo re-run, each gated on its smoke case.

   ## 6. Multi-model comparison under prompt v2 (2026-11-18, full suites, gateway-routed)

Prompt v2 (no-data-is-not-data, refusal contract, injection hardening) ran against the full 25-case set on three stacks; scores are the deduped ledger view (latest outcome per case, Wilson 95% CI):

| Stack | Buyer | Adversarial | Total | Wilson 95% | avg case |
|---|---|---|---|---|---|
| **google_vertex (gemini-4-hydrogen)** | 14/15 | 7/10 | **21/25 (84%)** | 0.65–0.94 | 30.3s |
| cf_workers_ai (glm-4.7-flash) | 8/15 | 5/10 | 13/25 (52%) | 0.33–0.70 | 44.6s |
| groq (qwen3.8-27b) | 0/15 | 1/10 | 1/25 (5%) | 0.01–0.23 | 31.2s |

Findings: **(1)** vertex's interval does not overlap workers-ai's — the strongest model is also the most reliable, and it fixed `adv-false-premise` under v2 (prompt sensitivity is real but partial: 1 of 5 v1 failures flipped; the other 4 persisted under strengthened instructions, which is the measured case for M3-c's clarification loop and M3-d's verifier). **(2)** groq's full-suite collapse (1/25) confirms the smoke warning: its server-side tool-call validation intermittently 400s runs unrecoverably (4 transport-class + 4 skipped rows here) — the stack needs a malformed-call workaround before it can benchmark at all. **(3)** glm on NIM remains provider-unavailable (18 min/case) and is demoted from the rotation. **(4)** openrouter cannot run the canonical set (50/day < 75 requests needed).

**AMENDMENT (2026-11-17, owner decision): the canonical model is now `google_vertex` (gemini-4-hydrogen) via the AI Gateway.** glm's first resumed case failed `provider-unavailable` after 18 minutes (3 × 180s timeouts against NIM queue latency — the same failure mode that disabled it), while vertex had just passed its smoke 1/1 in 30s. glm's 11 recorded buyer cases remain committed comparison evidence; vertex completes buyer 15 + adversarial 10 as the canonical set. The canonical rule itself (one model, both suites, committed traces) is unchanged.

Each item enters the runner only through a small, reviewed change — the protocol is documented here first so the resumption is a decision, not an accident.

**Implementation status (change `add-llm-gateway-model-registry`):** items 2–4 are now enforced code, not prose — the runner paces live cases (`max(inter-case delay, 60/rpm)`, delay 45s default via `TRADEATLAS_INTER_CASE_DELAY`/`--delay`), classifies transport failures (429/quota/timeout/connection) with up to 3 linear-backoff retries then skip-and-continue (`provider-unavailable`, resumable via `--case-ids`), and projects each entry's daily cap (`daily_limit` in the model registry: OpenRouter 50/day, Groq 500/day, Workers AI 500/day; NVIDIA NIM 40 RPM) against a date-keyed usage ledger, skipping as `daily-cap`. All live LLM traffic now routes through Cloudflare AI Gateway under a checked-in model registry (enabled-only selection, per-entry params/timeout). Owner-approved revision of item 5: the timeout is now **per-entry** (registry-declared, 300s default) instead of a constant — a slow stack declares its window in its own entry, and is disabled rather than tuned around. A per-model evidence ledger (`evals/results/run_ledger.jsonl`, `--history`) records duration/touches/outcome per case so the next run can decide what to drop.
