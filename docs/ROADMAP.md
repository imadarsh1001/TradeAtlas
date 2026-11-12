# TradeAtlas Roadmap

**Single source of truth for execution order.** Milestone-driven — no calendar dates, no demo deadlines. Supersedes the MVP plan's Milestones 0–5 (§7) and the concepts brief's four analysis stages as the execution roadmap; both remain as historical context ([ADR 0006](adr/0006-persona-expansion-and-reconciled-roadmap.md)).

**Purpose:** portfolio-first — demoable, documented, reproducible, defensible. Learning is the explicit byproduct. **Personas:** one evidence core, three lenses, [Buyer primary](../PERSONAS.md).

**Operating principles**

1. Deterministic code owns 100% of arithmetic, filtering, and evidence; LLMs parse queries and write briefings only ([ADR 0002](adr/0002-deterministic-evidence-and-citation-verification.md)).
2. Every milestone ends with a verifiable exit condition and its own golden eval suite — evaluation is built at exit gates, never deferred.
3. Tiered depth: groundnut is deep-tier in its proof states, Gujarat and Rajasthan (full guarantees); soybean and mustard are thin-tier (live data, labelled unverified coverage); groundnut queried outside the proof states is also thin-tier ([ADR 0006](adr/0006-persona-expansion-and-reconciled-roadmap.md)).
4. Official, compliant data access only ([ADR 0004](adr/0004-live-mandi-data-ingestion-architecture.md)).

---

## Milestones

### M0 — Foundations ✅ (done)

| | |
| --- | --- |
| **Deliverables** *(retrospective)* | Groundnut data proof, price backtest with November 2025 reporting-break isolation ([ADR 0001](adr/0001-november-2025-reporting-break.md)), agent benchmark (fixed report vs. single agent vs. LangGraph specialists) in `experiments/`; live MCP server with 5 deterministic tools (`tradeatlas_mcp.py`); DuckDB cache with 6 h TTL; benchmark hub configuration ([ADR 0004](adr/0004-live-mandi-data-ingestion-architecture.md), [ADR 0005](adr/0005-edible-oilseeds-expansion-and-mcp-ingestion.md)) |
| **Exit condition** | Met retrospectively: experiments reproduce from a clean checkout; the 5 tools return live data; decisions recorded in ADRs. |
| **Skills shown** | Data science, data engineering |

### M1 — Core stabilization & evidence retrofit ✅ (done)

| | |
| --- | --- |
| **Deliverables** | Evidence-card-shaped outputs from all 5 MCP tools: observation date vs. retrieval date, coverage counts and denominator where known, caveats, deep/thin tier labels. Pytest coverage for the deterministic core (calculator, cache TTL/upsert/fallback, hub matching, supply balance) using recorded fixtures — no live calls in tests. Source manifest: pinned file hashes, revisions, retrieval dates, terms for `data/raw/` and `config/`. Hygiene: remove `verify=False` from HTTP clients; timezone-aware UTC in cache timestamps. [ADR 0006](adr/0006-persona-expansion-and-reconciled-roadmap.md) |
| **Exit condition** | `uv run pytest` green; every tool output is self-describing (age, coverage, tier). |
| **Skills shown** | Architecture, engineering rigor |

### M2 — Analyst lens

| | |
| --- | --- |
| **Deliverables** | Backtest harness productized from `experiments/groundnut_price_backtest.py` into the package (last-observed naive, same-month-last-year, linear trend; MASE — Mean Absolute Scaled Error — and MAE — Mean Absolute Error — at 1–3 month horizons; reporting-break isolation preserved). Deterministic anomaly detection and coverage/gap-detection tools. Methodology notes. Stage gate: one ML model only after the baseline harness passes. |
| **Exit condition** | Reproducible MASE/MAE backtest report generated from package code; anomaly and coverage tools return evidence cards. Analyst golden suite passes. |
| **Skills shown** | Data science, machine learning |

### M3 — Agent layer

| | |
| --- | --- |
| **Deliverables** | **Two builds with a promotion gate.** Build 1 — single agent over the evidence-card tools: structured-output routing (never prose parsing), Pydantic-validated tool arguments (no silent commodity/date substitution), untrusted-data hygiene for live API payloads. Build 2 — LangGraph planner + market/production specialists + deterministic evidence verifier ([ADR 0002](adr/0002-deterministic-evidence-and-citation-verification.md)) with retry budget and partial-result preservation; ordered after M2 because specialists consume forecasting and anomaly tools. Human-in-the-loop clarification (pods vs. kernels, quantity, delivery window) via `interrupt()` + checkpointer — persistence also buys resume and an audit trail. Observability: run records (tokens, latency, tool calls, retries per stage; pinned model and prompt versions) and offline replay. Benchmark re-run including failure and sparse-data cases. Methodology RAG (stretch goal, cuttable): glossary/ADR/methodology-note retrieval with a keyword baseline and a citation-accuracy metric; numeric questions hard-routed to deterministic tools. |
| **Exit condition** | Golden buyer cases answered with zero unverified figures; single- vs. multi-agent comparison measured — specialists promoted only on better evidence fidelity at acceptable cost/latency; HITL clarification demoable; run records produced for every benchmark run. |
| **Skills shown** | AI agents, architecture |

### M4 — Sell-side lens

| | |
| --- | --- |
| **Deliverables** | MSP-spread/distress view (re-presentation of the existing core signal), sell-timing seasonality ("historically, month X averages the highest modal price in your hub mandis"), fair-price reference for hub mandis. 2–3 new tools; no new computation beyond seasonality aggregation. |
| **Exit condition** | Sell-side golden cases pass. |
| **Skills shown** | Product design |

### M5 — Buyer demo UI

| | |
| --- | --- |
| **Deliverables** | React + Vite + shadcn/ui: market explorer, investigation workspace, delivered-cost quote calculator. |
| **Exit condition** | Flagship scenario ("100 MT groundnut, where to seek quotes over the next three months") demoable end-to-end. |
| **Skills shown** | Product design, frontend |

### M6 — Evals & release

| | |
| --- | --- |
| **Deliverables** | Final golden suites, regression tests, historical forecasting backtests, single- vs. multi-agent comparison, adversarial/abstention results, deployment, final README and demo script. |
| **Exit condition** | Results reproducible; benefits and limitations of the architecture measured and written up. |
| **Skills shown** | Eval engineering |

---

## Evaluation suites (built at exit gates)

Versioned JSON will live in `evals/golden/`, with results in `evals/results/`. Rubric: numeric exactness, evidence fidelity, abstention correctness.

| Suite | Questions | Added at |
| --- | --- | --- |
| Buyer | 15 | M3 (investigation), extended M5 (UI flow) |
| Analyst | 10 | M2 |
| Sell-side | 10 | M4 |
| Cross-persona adversarial / abstention | 10 | M3, extended M6 |

---

## Beyond M6 (long-term direction)

The corridor is the beachhead, not the boundary. The standing ambition — recorded so anyone reading this repo knows where TradeAtlas intends to go:

| Direction | What it unlocks | Gate before adoption |
| --- | --- | --- |
| **Daily arrival volumes** | The known data gap: sizing procurement against real market throughput, not prices alone | e-NAM (electronic National Agriculture Market) traded quantities or CEDA `/agmarknet/quantities`; verified coverage, units, terms ([ADR 0004](adr/0004-live-mandi-data-ingestion-architecture.md)) |
| **Pan-India geography** | From the 5-state corridor to all major producing states, rising to mandi-level detail nationwide | Per-state portability checks; verified market-daily grade data before any unstratified mandi rankings ([ADR 0003](adr/0003-state-level-sourcing-scope.md), [ADR 0006](adr/0006-persona-expansion-and-reconciled-roadmap.md)) |
| **More commodities** | Beyond the Big 3 (e.g., chickpea, castor, cottonseed) into the same pipeline | The same data-proof discipline per commodity; thin-tier first, deep-tier only after reconciliation passes |
| **International trade context** | UN Comtrade import/export pressure and supplier concentration around the oilseeds complex | Reporter/partner coverage, classification and quantity alignment (MVP plan §11) |
| **Knowledge graph retrieval** | Multi-hop evidence linkage (mill → mandi → district → crop-year chains) if such questions emerge | Formally deferred: revisit only when a real question requires traversal that SQL handles poorly — the plan's original gate, still unmet |
| **Official methodology & policy corpus** | Domain-real RAG: AGMARKNET methodology/help pages, UPAg documentation, CACP/MSP framework documents, e-NAM operation guidelines, APMC act summaries, CEDA/data.gov.in terms — grounds the M3 methodology-RAG stretch goal in heterogeneous official documents instead of first-party markdown alone | Per-document terms/licence check; pin download date and hash in the source manifest; corpus stays at tens of documents so citation evaluation remains hand-verifiable |
| **Value-chain & alignment sources** | The graph-shaped problems already latent in the data: cross-source mandi/commodity alias alignment (the same mandi named differently across AGMARKNET, data.gov.in, e-NAM), the edible-oil value chain (seed → crusher → oil/meal → deficit states), district-boundary changes over time | Alias crosswalks built relationally first; KG adoption stays gated by the revisit condition above — acquisition follows questions, never precedes them |
| **Product surface** | Opportunity-discovery cards, forecast & decision lab, monitoring alerts | Analyst-lens baselines passing first; MASE-backed forecast targets before any forecast-led feature |

Each item enters the milestone plan only through its gate — the roadmap above stays the single source of truth, and this table is ambition, not commitment.

---

## Current status

**M0 and M1 are complete. M2 — Analyst lens — is next.** M1 shipped via the OpenSpec change `core-stabilization-evidence-retrofit` (evidence-card envelopes on all 5 tools, 33-test offline suite, source manifest, TLS/UTC hygiene). Sequencing, not dates, governs; no milestone carries a calendar commitment.
