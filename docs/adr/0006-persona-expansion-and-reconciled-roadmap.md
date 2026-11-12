# Persona Expansion, Reconciled Roadmap, and Scope Supersessions

## Status
Accepted

## Context
A structured grilling review (design-tree interview over the full doc set and codebase) surfaced tensions that three coexisting planning documents could not resolve on their own:

1. **Purpose ambiguity.** The MVP plan describes a "demonstrable, tested portfolio project"; the concepts brief states "the immediate goal is to practice data science, machine learning, and AI"; ADR 0005 frames the work as a "functional procurement intelligence MVP". Each framing implies different next steps and a different definition of done.
2. **Persona insufficiency.** The single buyer persona does not exercise the full skill set the project is intended to demonstrate (data science, machine learning, AI agents, architecture, product design), and the buyer trial remains unfalsifiable while no real buyer is reachable.
3. **Roadmap drift.** The MVP plan's Milestones 0–5, the brief's four phases, and the de-facto ADR 0005 live-ingestion work all describe different orderings. The repo state matches none of them exactly.
4. **Scope supersession in practice.** ADR 0003 deferred individual mandi references to Milestone 2, but ADR 0005 subsequently shipped curated benchmark hub mandi summaries. The accepted record no longer matched accepted reality.
5. **Evidence-discipline gap.** ADR 0002 mandates deterministic evidence and strict citation verification, but the five live MCP tools return raw dictionaries with no observation age or scope caveats; only the hub summary exposes coverage counts.

## Decision
1. **Purpose: portfolio-first.** TradeAtlas is a portfolio piece that must be demoable, documented, reproducible, and defensible. Learning is the explicit byproduct; product operation (live users, SLAs) is out of scope.
2. **One core, three lenses, buyer remains north star.** A single deterministic data/evidence core serves three personas: **Buyer** (primary), **Sell-side** (farmer/FPO/small trader, secondary), and **Analyst** (secondary). Shared features are justified by the buyer first. See [PERSONAS.md](../../PERSONAS.md).
3. **Sell-side lens is scoped to three features**: MSP-spread/distress signal view, sell-timing seasonality, and fair-price reference for hub mandis. Buyer matching, logistics, e-NAM selling, and advisories are out of scope.
4. **Analyst lens is scoped to**: productized forecasting backtests, anomaly and coverage detection, and methodology notes — delivered via notebooks and API, no UI. Machine learning is staged: one ML model may be added only after the baseline harness (seasonal naive, same-month-last-year, linear trend) passes with MASE/MAE scoring.
5. **Tiered depth.** Groundnut (Gujarat, Rajasthan) carries the full guarantee set — coverage checks, reconciliation, backtests. Soybean and Mustard across the 5-state corridor are served live but explicitly labelled as thin (unverified coverage) in tool outputs. No tool output may present thin-tier intelligence with deep-tier confidence.
6. **Evidence retrofit before agent productization.** All live MCP tools are wrapped to emit evidence-card-shaped outputs (observation date vs. retrieval date, coverage counts, caveats, tier labels) and the deterministic core gains pytest coverage before the LangGraph agent layer is built into the package.
7. **Single-source-of-truth roadmap.** [docs/ROADMAP.md](../ROADMAP.md) (milestone-driven, no calendar dates) supersedes the MVP plan's Milestones 0–5 and the brief's four analysis stages as the execution roadmap. The MVP plan and concepts brief remain as historical context.
8. **[ADR 0003](0003-state-level-sourcing-scope.md) superseded in part.** Curated benchmark hub mandi references are permitted *with coverage caveats* because they are named liquidity centres with explicit reporting status, not rankings computed from unstratified data. Full mandi-level rankings on unstratified extracts remain deferred until verified market-daily grade data exists — the original risk ADR 0003 identified still stands.
9. **M5 UI stack**: React + Vite + shadcn/ui, per the original plan.
10. **Evaluation at exit gates.** Per-persona golden suites (buyer 15, sell-side 10, analyst 10, cross-persona adversarial/abstention 10) are built incrementally at each milestone's exit gate, stored as versioned JSON in `evals/golden/` with results in `evals/results/`.

## Consequences
- **Positive**: One roadmap removes drift; persona expansion exercises DS, ML, AI-agent, architecture, and product-design skills against one shared core; the ADR record matches the shipped reality; evidence discipline extends from experiments to the live layer before agents depend on it.
- **Negative**: Three lenses multiply documentation and evaluation surface even with a shared core; the tiered-depth labels must be maintained in every tool output or the honesty guarantee erodes; portfolio-first means some product-hardening work (retention policy, refresh SLA) is deliberately deferred and must be labelled as such.
