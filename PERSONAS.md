# TradeAtlas Personas

Three personas share one deterministic evidence core ([ADR 0006](docs/adr/0006-persona-expansion-and-reconciled-roadmap.md)). All are **synthetic design fictions** — they keep every feature honest against a real decision, not a demographic simulation. A real-buyer recruitment gate exists for the buyer trial phase (see Buyer, below).

**Primary persona rule:** when lenses conflict, the Buyer decides. Shared features are justified by the buyer first. The recruitment gate is Buyer-specific by design; the other personas remain synthetic-only throughout.

---

## 1. Buyer — procurement lead, edible-oil processing plant 🎯 PRIMARY

> *"We need 100 tonnes of groundnut. Which sourcing regions should we investigate over the next three months?"*

| | |
| --- | --- |
| **Decision they face** | Where and when to seek quotes for a fixed-volume, fixed-window requirement — and what to verify before committing. |
| **Questions they ask** | Which states/mandis have comparable historical prices and arrivals? What is the delivered cost on a like-for-like basis? Is the market firm or distressed relative to MSP? What can't this data tell me? |
| **Served by** | State/market comparisons, benchmark hub summaries, MSP spread, macro supply balance, delivered-cost calculator, agent investigations (M3), Market Explorer + quote calculator UI (M5). |
| **Success signal** | Prepares a usable quote request (quantity, product form, grade, destination, window) with evidence and next verification steps attached. |
| **Hard honesty rules** | Arrivals are not sales; production is not purchasable inventory; recommendations state that quantities, grades, supplier availability, and freight still need direct confirmation. Kernel requirements use the 70% shelling-outturn benchmark with a visible caveat. |
| **Recruitment gate** | The buyer trial (real contact, matched-task comparison) proceeds only if a real procurement contact is recruited; otherwise the persona stays synthetic and the docs say so. |
| **Scope exclusions** | Split-order optimization, monitoring alerts, e-NAM selling, international trade context. |

## 2. Sell-side — farmer / FPO (Farmer Producer Organisation) / small trader

> *"Is now a good time to sell, and what's a fair price at my nearest hub mandi?"*

| | |
| --- | --- |
| **Decision they face** | When to sell, and whether an offered price is fair relative to the official support price and recent local trade. |
| **Questions they ask** | Is my mandi trading below MSP (distress signal)? Which months historically average the highest modal price for my crop? What have my state's hub mandis been paying? |
| **Served by** | MSP-spread/distress view, sell-timing seasonality, fair-price reference for hub mandis (M4). |
| **Success signal** | Times the sale with a historical reference in hand and knows the MSP floor context. |
| **Hard honesty rules** | Historical seasonality is not a prediction; MSP spread signals local market conditions, not a guarantee of procurement at MSP; no advice on *whether* to sell — only evidence for *when/where* to investigate. |
| **Scope exclusions** | Buyer matching, logistics, e-NAM (electronic National Agriculture Market) selling, weather/advisory. |

## 3. Analyst — market researcher / quant

> *"What does this corridor's data actually support, and where does it break?"*

| | |
| --- | --- |
| **Decision they face** | Which methods and claims the data sustains — coverage, seasonality, forecast error, anomalies. |
| **Questions they ask** | What is the forecast error at each horizon against honest baselines? Where are reporting gaps, structural breaks, and anomalies? How do units, vintages, and coverage limits constrain comparisons? |
| **Served by** | Productized backtest harness (MASE/MAE, 1–3 month horizons), anomaly and coverage detection, methodology notes — notebooks and API, no UI (M2). |
| **Success signal** | Reproduces every published figure from package code and can state exactly where the data is unusable. |
| **Hard honesty rules** | Baselines are scored before any ML model is admitted (stage gate); error is only reported on comparable held-out months; the November 2025 reporting break is never crossed in aggregation ([ADR 0001](docs/adr/0001-november-2025-reporting-break.md)). |
| **Scope exclusions** | No UI, no ML models before the stage gate passes, no commercial advice. |

---

## Why these three

The persona set is chosen to exercise every discipline the project exists to demonstrate: the **Buyer** drives agentic investigation and product design; the **Sell-side** lens tests translating the same evidence for the opposite decision direction; the **Analyst** anchors data-science and machine-learning rigor. One core, three lenses — no feature ships that none of the three would use.
