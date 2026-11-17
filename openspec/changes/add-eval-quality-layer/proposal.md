# Proposal: add-eval-quality-layer

## Why

The benchmark harness scores substance correctly but three gaps remain: the committed live evidence is only partially wired into replay (9 of 11 traces unbound; one documented rubric revision never applied), the agentic-eval taxonomy is under-covered (no trajectory checks — step efficiency, argument correctness via expected calls, duplicate-call waste — and no uncertainty quantification on pass rates), and the repo deliberately uses zero eval frameworks or observability while claiming eval-engineering as a showcased skill. Owner decision after review: adopt a **two-layer evaluation policy** — the deterministic Gate Layer stays the only milestone gate, a judged Quality Layer (deepeval) runs as non-gating evidence, and judged gating may come later only after judge-vs-deterministic calibration. Observability (LangSmith) is telemetry, not scoring, and stays off in CI.

## What Changes

- **MODIFIED `golden-evals`**:
  - Evidence-fidelity summary signals gain **any-of semantics** (`str` or `list[str]` of alternatives) — `["quintal","qtl"]` accepts both spellings without breaking the committed glm replay.
  - **NEW trajectory requirement**: deterministic checks derived from the run record — *duplicate-call invariant* (two successful calls with identical tool + schema-canonical arguments fail the case; universal), optional per-case `expected_calls` rubric (required executed calls, checked tool + canonical arguments, gating where present), optional per-case `efficiency_budget` (max model touches — recorded non-gating until calibrated from campaign data).
  - **NEW judged quality-layer requirement**: a pytest-integrated framework layer (deepeval) scoring live-run evidence (summary relevance, answer-vs-evidence faithfulness); scores recorded separately under `evals/quality/`; SHALL NOT affect any gate pass/fail; judge LLMs SHALL resolve through the model registry (enabled entries only, gateway-routed); judges run only on live evidence, never in CI or replay.
  - Ledger per-model summary gains **bootstrap 95% CI + Wilson interval** on pass rate (executed runs only).
  - `buyer.json` fixes: any-of signal on the daily-price case; the documented anomaly-rubric revision applied (`buyer-anomaly-flag-gujarat`); 9 missing `trace` bindings added; `expected_calls` pinned on the 5 numeric-fidelity cases.
- **NEW capability `run-observability`**: live benchmark runs MAY emit LangSmith traces on operator opt-in (env vars); replay and CI SHALL NOT emit traces even when tracing env vars are set.
- **NEW `docs/adr/0007`**: records the two-layer policy (Gate Layer / Quality Layer), the calibration path to judge-gating, framework placements (deepeval now; promptfoo → M6 red-team action item; ragas → methodology-RAG stretch action item), LangSmith as telemetry-not-scoring, and trajectory metrics as Gate Layer.
- Dev dependency `deepeval` added to the dev group; CLI gains `--quality`; `--history` gains `ci95`.

## Capabilities

### New Capabilities
- `run-observability`: opt-in LangSmith tracing for live runs; hard-off in replay/CI.

### Modified Capabilities
- `golden-evals`: any-of signals; trajectory checks (duplicate-call invariant, `expected_calls`, `efficiency_budget`); judged quality layer (non-gating, registry-routed judges); statistical intervals in the per-model summary.

## Impact

- Code: `evals/runner.py` (signal semantics, trajectory checks), `evals/ledger.py` (intervals), `evals/quality.py` (new), `evals/golden/buyer.json` (signals, rubric fix, bindings, expected_calls), CLI flags.
- Dependencies: `deepeval` (dev group only — CI stays network-free).
- Env: `TRADEATLAS_JUDGE_MODEL` (registry selector for judges), `LANGSMITH_TRACING`/`LANGSMITH_API_KEY`/`LANGSMITH_PROJECT` (names in `.env.example`).
- Docs: ADR 0007 (new), GLOSSARY (Gate Layer / Quality Layer), BENCHMARK_METHODOLOGY (trajectory metrics, quality layer, observability sections), ROADMAP (M6 promptfoo action item, methodology-RAG ragas action item, M3-d plan-adherence/plan-quality rubrics note), README, LEARNINGS (stale plugin-flag name fix).
- Out of scope: promptfoo/ragas integrations (action items), the judge-gating flip (awaits calibration), efficiency-budget calibration (awaits campaign data), plan adherence/quality rubrics (M3-d — no planner exists to grade), benchmark resumption (still gated on protocol-v2 approval).
