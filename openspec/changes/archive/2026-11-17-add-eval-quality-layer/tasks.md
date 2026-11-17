# Tasks: add-eval-quality-layer

## 1. Suite bundle (buyer.json + scorer semantics)

- [x] 1.1 Runner: summary-signal satisfaction helper accepting `str | list[str]` (any-of, case-insensitive); update `_validate_agent_case` to accept both shapes; unit tests for both forms and the neither-alternative failure
- [x] 1.2 buyer.json: `["quintal","qtl"]` on buyer-daily-price-gujarat; apply the documented anomaly-rubric revision to buyer-anomaly-flag-gujarat (presence-only figures + recency acceptance per findings §4)
- [x] 1.3 buyer.json: add the 9 missing `trace` bindings; verify committed traces load through the standard loader
- [x] 1.4 buyer.json: pin `expected_calls` (tool + canonical arguments) on the 5 numeric-fidelity cases; verify each pinned call matches the committed traces' executed calls

## 2. Trajectory layer

- [x] 2.1 Runner: `_trajectory_checks(record, expected)` — duplicate-call invariant over successful calls by (tool, schema-canonical args); `expected_calls` assertions; `efficiency_budget` recorded with `calibration: pending` marker (non-gating); wire into the agent-kind scoring branch
- [x] 2.2 Tests: duplicate identical successful calls fail; rejected-then-corrected retry passes; missing pinned call fails; satisfied pinned call passes; budget exceedance recorded without flipping pass/fail

## 3. Statistical layer

- [x] 3.1 ledger: bootstrap 95% CI (seeded, deterministic) + Wilson score interval on pass rate over executed runs; `ci95` rendered in `format_history`; unit tests with pinned closed-form checks (8/10 → known Wilson bounds; n=3 → wide bounds)

## 4. Judged quality layer

- [x] 4.1 Add `deepeval` to the dev dependency group; `uv lock`
- [x] 4.2 `evals/quality.py`: `GatewayJudgeModel(DeepEvalBaseLLM)` wrapping a registry-resolved model (`TRADEATLAS_JUDGE_MODEL` → resolve → build; deepeval imported at module scope in quality.py, which the runner imports only under --quality); judged metrics (summary relevance G-Eval, answer-vs-evidence faithfulness vs executed tool payloads); per-case scores written to `evals/quality/` paired with the deterministic outcome; CLI `--quality` flag; non-gating by construction (results computed before the layer runs)
- [x] 4.3 Tests with a fake judge (no network): scores recorded and paired; judged scores cannot alter the results payload; unknown/disabled judge selector fails with a named error; pytest/replay never construct a judge

## 5. Observability

- [x] 5.1 Runner: replay mode force-disables tracing for its duration (scoped env, restored); live mode inherits operator env; `.env.example` gains LANGSMITH_TRACING / LANGSMITH_API_KEY / LANGSMITH_PROJECT names
- [x] 5.2 Test: replay with tracing env set emits zero langsmith client runs (monkeypatch tripwire)
- [x] 5.3 Fix `docs/LEARNINGS.md` stale plugin-flag name (`-p no:langsmith` → `-p no:langsmith_plugin`)

## 6. Docs + governance

- [x] 6.1 ADR 0007: two-layer policy, calibration path, framework placements (deepeval now / promptfoo M6 / ragas RAG stretch), LangSmith telemetry-not-scoring, trajectory metrics as Gate Layer
- [x] 6.2 GLOSSARY: Gate Layer + Quality Layer terms
- [x] 6.3 BENCHMARK_METHODOLOGY sections (Trajectory metrics / Quality layer / Observability); ROADMAP (M6 promptfoo action item, methodology-RAG ragas action item, M3-d plan-adherence/quality note); README evals line

## 7. Gate

- [x] 7.1 Full gate green: pytest (PIPESTATUS), analyst 10/10, uv lock --check, openspec validate --strict; replay buyer shows 11 scored cases with honest outcomes
- [x] 7.2 Post-apply review (karpathy lens + EGM axes); fix findings
