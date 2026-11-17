# ADR 0007: Evaluation Quality Layer, Framework Policy, and Run Observability

- **Status:** Accepted (2026-11-17)
- **Supersedes:** nothing — extends the evaluation governance of ADR 0002 (which governs the *synthesis pipeline*, not evaluation tooling) and ADR 0006 (exit-gate suites)
- **Driver:** the eval-engineering portfolio goal, the benchmark campaign's evidence needs, and the agentic-eval taxonomy review

## Context

The hand-rolled harness (golden suites + deterministic runner + run records + ledger) gates milestones and needs no external judge: agent fidelity is scored by selector agreement against checked-in literals. Two pressures shaped this decision: (1) the owner's direction that eval engineering be showcased at industry depth — framework skills included, nothing mediocre; (2) the agentic-eval taxonomy review (task completion, step efficiency, argument correctness, tool correctness, plan adherence/quality, answer correctness) which showed the deterministic layer could be strengthened and that some dimensions (subjective quality) genuinely need judged scoring.

## Decision

**Two evaluation layers, one gate.**

1. **Gate Layer (deterministic, unchanged authority).** Golden suites scored by the deterministic runner — numeric literals, selector agreement, abstention signals, injection resistance, plus new deterministic **trajectory metrics** (duplicate-call invariant, `expected_calls` pins, efficiency budgets once calibrated). This layer alone decides milestone gates. Nothing in this ADR weakens ADR 0002.
2. **Quality Layer (judged, never gating).** deepeval metrics score live-run evidence (summary relevance via G-Eval; answer-vs-evidence faithfulness against bounded tool-result excerpts). Scores are recorded *paired* with deterministic outcomes (`evals/results/quality/`, git-ignored) — that pairing is the calibration dataset. **Judged metrics may gate only after a future reviewed change demonstrates judge-vs-deterministic agreement on the calibration data** (ADR 0007 amendment). Until then the layer cannot change any gate result — the results payload is computed and written before the layer runs and never re-read.

**Framework placements** (adopted vs registered):

| Framework | Placement | Why |
|---|---|---|
| deepeval | **Adopted now** — dev dependency; judged quality layer; judges route through the model registry (enabled entries, gateway-routed) | pytest-native; real immediate use case (judged dimensions over live evidence); judges inherit registry governance |
| promptfoo | **Action item at M6** — red-team extension of the adversarial suite (jailbreak, prompt extraction, excessive-agency probes) | Its unique value here is red-teaming; the matrix/comparison UI duplicates the registry + ledger + `--history` |
| ragas | **Action item at the methodology-RAG stretch goal** | Canonical for RAG metrics (context precision/recall); TradeAtlas has no RAG system yet; its faithfulness would duplicate deepeval's |
| LangSmith | **Adopted now as telemetry** — env-driven opt-in tracing for live runs; replay and CI are provably trace-free | Observability is telemetry about runs, not scoring; the zero-network CI guarantee extends to it |

**Trajectory metrics are Gate Layer.** Step efficiency, argument-correctness expectations, and waste detection (duplicate identical calls) are deterministic judgments over the run record — they gate where pinned. Per-case efficiency budgets record non-gating until calibrated from campaign data. Plan adherence and plan quality are **not evaluable before M3-d** (no planner artifact exists to grade) and are pinned to M3-d's exit-gate additions.

## Consequences

- The results payload's pass/fail is structurally immune to judge output (byte-identical with the layer on or off — tested).
- Every judged score carries its deterministic pairing, so calibration evidence accumulates automatically with each benchmark run.
- `deepeval` joins the dev dependency group only; production dependencies and CI stay network-free and judge-free.
- LangSmith tracing is zero-code for live runs and structurally impossible in replay (scoped env override, tripwire-tested).
- Future readers see why a "deterministic evidence" project carries judge metrics: reported depth, not delegated authority.
