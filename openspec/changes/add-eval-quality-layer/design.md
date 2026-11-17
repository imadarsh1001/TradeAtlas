# Design: add-eval-quality-layer

## Context

The harness (M2/M3-b + the gateway change) scores deterministically from run records; 11 live glm traces are committed but only 2 cases carry `trace` bindings, and one documented rubric revision (findings §4) was never applied to the committed suite. Agent-eval taxonomy gaps: no trajectory judgment (step efficiency, explicit argument expectations), no uncertainty on small-n pass rates, no judged dimension, no observability. Frameworks researched: deepeval (pytest-native, judge metrics call a configurable LLM), promptfoo (red-team + matrix UI), ragas (RAG metrics needing context pipelines). LangSmith is env-driven zero-code tracing; the repo references none of it and suppresses its pytest plugin.

## Goals / Non-Goals

**Goals:** close the rubric/binding debt; add a deterministic trajectory layer; quantify uncertainty in comparisons; stand up the judged Quality Layer with gateway-routed judges; wire opt-in observability; record the whole policy in ADR 0007.

**Non-Goals:** judge-gating (awaits calibration evidence); efficiency-budget gating (awaits campaign data); promptfoo/ragas integrations (action items); plan adherence/quality rubrics (M3-d — no planner exists to grade); benchmark resumption; any change to deterministic figure/value scoring semantics.

## Decisions

- **D1 — Two layers, one gate.** Gate Layer = the existing deterministic scorers (unchanged semantics except any-of signals); Quality Layer = judged metrics, recorded never gating. The results payload's pass/fail is computed before the quality layer runs and is not re-read afterwards — structural non-gating, testable by byte-identical results.
- **D2 — Calibration path.** Judged scores are recorded PAIRED with deterministic outcomes per case (`evals/quality/`); the future gating flip is a reviewed change requiring agreement evidence on that pairing. No threshold invented now.
- **D3 — Any-of signals via a satisfaction helper.** A signal is `str` (must appear) or `list[str]` (any alternative appears). The list form is necessary because the AND-semantics of the signals list cannot express "quintal OR qtl", and a naive swap would break the committed glm trace's replay.
- **D4 — Trajectory checks are canonical-args-based.** Duplicate detection compares successful calls by (tool, schema-canonical arguments) — a schema-rejected attempt followed by a corrected call has no canonical form for the rejected attempt and different canonical args after correction, so the retry pattern does not false-positive. `expected_calls` compares canonical forms on both sides (registry lesson: raw args are coerced before invoke). `efficiency_budget` is recorded with an explicit `calibration: pending` marker — recording without gating avoids inventing thresholds from 25 cases.
- **D5 — Judges through the registry.** `TRADEATLAS_JUDGE_MODEL` resolves via `resolve_model_entry` → `build_model_for_entry`, wrapped in a `DeepEvalBaseLLM` subclass so deepeval metrics call gateway-routed, enabled-only models. Judge selection is deliberately separate from `TRADEATLAS_AGENT_MODEL` so the cheapest enabled entry can judge while a stronger entry answers.
- **D6 — CI isolation by construction.** `evals/quality.py` imports deepeval lazily (inside functions); the pytest suite tests the wiring with a fake judge and monkeypatches the resolution seam — no judge model is ever constructed in tests. deepeval is a dev-group dependency, never imported at module scope.
- **D7 — LangSmith: env-driven, scoped-off in replay.** Live runs inherit operator env (documented `LANGSMITH_TRACING`/`LANGSMITH_API_KEY`/`LANGSMITH_PROJECT`, project convention `tradeatlas`); replay mode force-clears the toggle for its duration and restores it — the zero-trace guarantee is tested with a tripwire mirroring the forbidden-live-model pattern.
- **D8 — Intervals over executed runs only.** Bootstrap (seeded, deterministic) + Wilson closed-form both computed on executed outcomes; skipped rows (daily-cap, provider-unavailable) are not measurements. Wilson is reported alongside the bootstrap point estimate so tiny-n claims ("3/3") show honest bounds.

## Risks / Trade-offs

- [deepeval drags heavy transitive deps into the dev venv] → dev-group only; production package deps untouched; CI never imports it.
- [Judge metrics call live models → cost/latency] → opt-in flag; judges inherit registry daily-cap awareness only via operator discipline for now (judge runs are manual, one-suite-at-a-time); documented.
- [Any-of signals weaken fidelity] → alternatives must be literal substrings checked case-insensitively; the pairing with numeric/figure expectations stays strict.
- [Duplicate-call invariant vs legitimate repeats] → canonical-args identity means a genuinely identical repeat IS waste under the evidence-card model (same inputs, same deterministic output); documented in the methodology.

## Migration Plan

Ship code + tests → rerun replay (honest outcomes with bindings) → ADR 0007 + docs → the manual quality-layer run is user-triggered. Rollback: revert the commit; `evals/quality/` and ledger rows are additive, git-ignored.
