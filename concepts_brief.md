# TradeAtlas — Groundnut sourcing intelligence

**Author** Pending confirmation  
**Date** 2026-11-11  
**Status** Goldfish review complete. Conceptual review and grilling aligned with domain model and architectural decisions.

## Overview

TradeAtlas helps Indian agricultural traders, procurement teams, and food processors decide where and when to seek groundnut quotes in Gujarat and Rajasthan. It combines wholesale prices and reported arrivals from AGMARKNET with crop production estimates and seasonal context from UPAg, the Unified Portal for Agricultural Statistics. A mandi is a wholesale market. Reported arrivals describe quantities received at reporting markets. Crop estimates describe production over a crop season or year. Buyers need direct confirmation of saleable quantity, grade, quote validity, and freight. [Government mandi price catalog](https://www.data.gov.in/catalog/current-daily-price-various-commodities-various-markets-mandi), [UPAg estimates](https://www.upag.gov.in/primary-estimate-report), [UPAg crop calendar](https://upag.gov.in/national-calendar)

Use the plan's Gujarat edible-oil processor as the proposed first test user. For a 100-tonne requirement over the next three months, the buyer should be able to identify where to ask for quotes, when historical evidence suggests an inquiry may be useful, and what to verify before acting. Check which comparisons the data support. Milestone 1 restricts sourcing recommendations to state-level intelligence; individual mandi rankings are deferred to Milestone 2 when verified market-daily data is integrated. If the states cannot be compared, show what can be verified next. When the buyer supplies comparable quotes, calculate delivered costs using those inputs.

The hypothesis reviewed here guides the proposed first release. The original plan provides the scenario, data candidates, and longer roadmap. Groundnut data coverage, live refresh access, and buyer demand still need testing. [Original MVP plan](TradeAtlas_India_Agricultural_Intelligence_MVP_Plan.md), [Domain Glossary](GLOSSARY.md), [ADR Index](docs/adr/)

The immediate goal is to practice data science, machine learning, and AI on the groundnut scenario. Start with Python files that run from the command line and can be explored in a notebook. Each exercise should produce an inspectable result that the next exercise can reuse. Use the resulting evidence and workflow to guide the later buyer interface.

The first exercise profiles state-month coverage and paired prices and checks crop-year production estimates using pinned extracts. [Groundnut data proof](groundnut_data_proof.py)

The second exercise scores two baselines and a fitted linear trend at one-, two-, and three-month horizons. The results show error and the number of scored months on either side of the November 2025 reporting change. [Groundnut price backtest](groundnut_price_backtest.py)

The third exercise compares a fixed report, a single evidence selector, and market and production specialists in LangGraph. All three use the same pinned evidence. The default run replays available evidence to check the graph, evidence validation, and quote calculation. A model-backed run tests which evidence the model selects and records model calls and tokens. [Groundnut agent benchmark](groundnut_agent_benchmark.py)

From the TradeAtlas directory, run `uv sync --locked` to install the pinned environment. Run `uv run --locked python -m marimo edit groundnut_lab.py` to open the notebook, or use `./run-tradeatlas.ps1` as a PowerShell shortcut. The notebook runs its cells when the editor opens. Keep the terminal running while you use the editor. [Groundnut lab](groundnut_lab.py)

The project pins Python 3.12.14 in `.python-version`. With this exact version, `uv` uses the standard CPython virtual-environment launcher on this Windows setup. If an older TradeAtlas environment still has the blocked launcher, refresh it in place with `uv venv --allow-existing --python 3.12.14 .venv` using the same installed Python version.

```powershell
uv run --locked python groundnut_data_proof.py
uv run --locked python groundnut_price_backtest.py
uv run --locked python groundnut_agent_benchmark.py
```

Add `--case unsupported-mandi-ranking` to the benchmark to inspect one set of reports. To run with a model, configure `OPENAI_API_KEY` in your environment and pass `--model` with a model ID that supports structured output.

## Analysis

### Which evidence can support a sourcing lead?

The prepared extract publisher describes a weighted state-month price and a market-day sample taken every sixth day. Use each measure at its own reporting level. The collector requests state prices and arrivals separately and matches the records by commodity name. It exports only market rows marked as reported and omits variety and grade fields from those rows. Reference lists of grades and varieties cannot establish the grade of a sampled price. An absent row has an unknown meaning unless a separate source establishes the expected market and date. The collector defaults to ending the latest state month on day 23. Check the actual cutoff for the pinned run before comparing a partial month to full months. [Publisher data notes](https://github.com/herrrickshaw/india-mandi-arrivals/blob/main/DATA_SOURCES.md), [State collector](https://github.com/herrrickshaw/india-mandi-arrivals/blob/main/collectors/agmarknet_collect.py#L64-L88), [Market collector](https://github.com/herrrickshaw/india-mandi-arrivals/blob/main/collectors/agmarknet_collect.py#L91-L104), [Collector defaults](https://github.com/herrrickshaw/india-mandi-arrivals/blob/main/collectors/agmarknet_collect.py#L123-L127)

Profile each measure by product form, grade or variety where known, units, market coverage, and period. Record unsampled dates, missing reports, reported zeroes, and unknown cases distinctly where the source supports that distinction. Check whether an apparent lead survives matched periods and a consistent set of reporting markets where that can be reconstructed. The government confirmed the AGMARKNET upgrade in November 2025. Test for a change in groundnut reporting around that date. TradeAtlas strictly isolates pre-break and post-break periods; arrival volume aggregation across the November 2025 reporting break is prohibited to prevent false seasonal signals [ADR 0001](docs/adr/0001-november-2025-reporting-break.md). The publisher found different district and market arrival totals for a wheat example, which motivates a groundnut reconciliation check. Keep reported market totals and official area, production, and yield estimates at their published levels. Compare production by crop year and season and retain its estimate status and release date. [Government AGMARKNET announcement](https://www.pib.gov.in/PressReleasePage.aspx?PRID=2204750&lang=2&reg=48), [Publisher endpoint comparison](https://github.com/herrrickshaw/india-mandi-arrivals/blob/main/docs/agmarknet_api.md), [UPAg reports](https://www.upag.gov.in/primary-estimate-report)

Deterministic checks determine which comparisons the workflow can recommend. LangGraph uses that result to route the investigation. The proposed outcomes below distinguish data gaps from a lack of a meaningful difference between the states. The precise rules remain open until the data proof.

| Outcome | Buyer gets |
| --- | --- |
| Supported state lead | A state and historical periods worth investigating when the median price spread exceeds the freight buffer (₹150–₹250/quintal transport cost), with evidence for the lead and the limits on market detail. |
| Comparable state evidence with no clear preference | A side-by-side view when the state spread is within the freight buffer or leadership oscillates, with usable measures and checks that could resolve the decision. |
| Insufficient comparable state evidence | The usable facts, the specific gap that prevents ranking, and how to verify it. |
| Comparable mandi evidence *(Deferred to Milestone 2)* | Named markets worth contacting. Explicitly deferred until verified market-daily samples or direct mandi APIs are integrated [ADR 0003](docs/adr/0003-state-level-sourcing-scope.md). |

Use comparable prices, arrivals, seasonality, and historical price variation where available. Present crop estimates as context and show the basis of each figure, including product, units, period, source, and aggregation. Show observation dates independently of retrieval dates. A dated historical pattern can inform planning, and a live sourcing lead needs evidence current enough for the buyer's decision window. The report should show which type of evidence supports each action.

### What changes for the buyer?

CEDA already offers price and arrivals exploration, and the extract publisher offers seasonality and market summaries. A buyer can combine views like these with their own spreadsheet and supplier calls. TradeAtlas needs to demonstrate that checking comparable evidence, surfacing gaps, and preparing the next quote request makes that task easier. The processor example is a starting hypothesis for buyer research. [CEDA Agri-Market Data](https://agmarknet.ceda.ashoka.edu.in/), [Prepared extract insights](https://github.com/herrrickshaw/india-mandi-arrivals/blob/main/reports/INSIGHTS.md)

Show the interpreted commodity, product form, geography, and time window when a buyer moves from exploration to investigation. A proposed interaction asks one focused question when an input changes the result, requiring the buyer to declare whether the requirement is for pods or kernels. For kernel requirements, calculate an equivalent benchmark using a standardized 70% shelling outturn (Pod Price / 0.70 + Decortication Allowance) with a visible caveat before comparing with historical pod data. Keep historical findings that remain valid and identify the assumptions the buyer can correct. Agree how the user's wording and selected filters interact when they conflict.

A usable quote request includes the required quantity, product form and grade, destination, and delivery window. Ask suppliers for price, available quantity and validity, and carriers for freight. For comparison, a proposed first case uses two quotes that can each cover the full requirement on the same delivery and quality basis. Show buyer-entered prices and their units, freight, included charges and any additional material costs, with per-tonne and order totals. A missing charge is distinct from zero. Flag incomplete costs, inadequate volume, and mismatched specifications, and show what to fix before comparing. A lower historical price offers only potential headroom. For illustration, ₹200 per quintal equals ₹2,000 per tonne, since one quintal is 100 kg. A freight or quality cost of that size would use up the difference for like-for-like product. Delivered cost is canonically calculated as (Base Price × 10) + Freight + Ancillary Charges per tonne. Milestone 1 restricts evaluation to full-lot quotes covering the full requirement; split-order optimization remains deferred.

### Can specialists improve the same investigation?

Use one set of deterministic DuckDB calculations and evidence checks across a fixed report, a single agent, and a LangGraph workflow with market and production specialists. Deterministic code generates immutable evidence cards and owns 100% of arithmetic and filtering, while agents handle query parsing and executive briefing. A deterministic verification check confirms all figures in the agent briefing match the evidence cards [ADR 0002](docs/adr/0002-deterministic-evidence-and-citation-verification.md). Each specialist can interpret evidence from its source. The same checks govern coverage, units, quote arithmetic, and the findings allowed in the final report. This lets the benchmark test whether specialists improve synthesis while keeping those rules consistent. Keeping a shared contract takes work to version and test when source definitions change. Specialist runs also add coordination, model calls, and peak load, even when independent calls can run in parallel.

Proposed evidence and run records include the source revision, requested and applied filters, observation dates, coverage counts and denominator where known, threshold version, failure reason, calculation version, and record references behind each recommendation. Link each report to its run and record tool arguments, results, model and prompt versions, and verifier outcomes. This should let a developer reproduce the calculations and diagnose a decision after a refresh. Test whether a verified report can still be generated from available evidence when one branch fails. Preserve checked results during a retry, and track elapsed time, retry count, and failure reason by stage. Set limits for recoverable retries, run time, and tool and model calls before the experiment. Keep commercial details out of routine logs and use synthetic quotes in evaluation. The retention and sharing policy for real quotes remains open.

### Can the data support a live pilot?

Pin exact extract revisions and record hashes, observation dates, terms, and metric definitions for a reproducible historical demonstration. The extract publisher describes its government-data licence as presumed. Check terms for the exact releases before external distribution. CEDA documents price and quantity endpoints and terms for non-commercial use with attribution. UPAg documents authenticated state and district endpoints. Prove one approved refresh path with representative groundnut responses, coverage, age, repeatability, request volume, and measured limits. [Extract source notes](https://github.com/herrrickshaw/india-mandi-arrivals/blob/main/DATA_SOURCES.md), [CEDA API](https://api.ceda.ashoka.edu.in/documentation/), [CEDA API terms](https://ceda.ashoka.edu.in/api-terms-conditions/), [UPAg API](https://data.upag.gov.in/docs)

A proposed refresh design validates a new snapshot before publishing it and pins each investigation to one snapshot. Test that a partial fetch, a changed source schema, or a refresh during an investigation keeps the report on a single validated version. Retain the last validated snapshot for recovery with visible observation dates and status. Track the last successful and attempted refresh independently of the latest usable observations. A dated demonstration can continue while access is resolved. Maintaining a fallback adds testing and upkeep, and the report becomes less useful as observations age. A live pilot depends on repeatable, authorized refresh and agreed observation-age limits.

## Goals and deferred work

- **Initial learning milestone** Produce a reproducible groundnut data profile for Gujarat and Rajasthan from pinned extracts. Use Python to practice schema inspection, missingness, unit checks, and source reconciliation. A learner should be able to rerun the profile, trace one result to source rows, and explain what those rows support.
- **Specialist investigation** Benchmark the fixed report, single agent, and collaboration between market and production specialists over the same evidence and calculations. Compare evidence quality, handling of sparse data, cost, and response time. Evaluate buyer value with the later buyer trial.
- **Buyer release** Let a buyer explore groundnut evidence, get a sourcing lead or qualified state comparison, ask a plain-language sourcing question, and compare delivered quotes entered on the same basis. Provide evidence and next verification steps in every report. Build the interface once the report and its evidence checks work from Python.
- **Separate learning experiments** Try one Model Context Protocol tool in a second client, one reusable procedure for checking comparable evidence, and a small methodology retrieval test against keyword search. Test forecasting separately against simple price baselines. Test optimization with buyer-supplied costs and constraints and a knowledge graph only when a concrete question and a SQL comparison justify it.
- **Expansion candidates** Consider soybean for portability after the groundnut proof. The original plan's additional workflows, specialist roles, broader markets, fresh alerts, e-NAM, and global trade extensions remain future work.

## Alternatives weighed

| Approach | What it tests | Trade-off or reason to stage it |
| --- | --- | --- |
| Current buyer process and simple same-data dashboard with quote worksheet | Whether buyers already have a fast route to a supportable decision | Use these as buyer baselines and observe where the work takes time. |
| Fixed, reproducible report | Whether combined evidence improves the next quote request | Provides a reference for the agents. It supports a defined set of questions and inputs. |
| Single agent over shared tools | Whether flexible questions and clarification improve the result | Adds model latency, cost, and evidence-verification work. |
| LangGraph with market and production specialists | Whether separate evidence gathering improves the same investigation | Adds coordination and model calls. Keep it in the experiment until it meets the promotion criteria. |
| Forecast-led demo or original four-workflow build | Whether predictions or a larger product improve the sourcing decision | Defer while testing comparable coverage and basic buyer value. Forecasts need a validated target and historical backtest. |

## Key decisions and staging for next steps

1. **Data science.** Pin and profile the groundnut extracts for both states. Record the source revision, file hashes, grain, units, and coverage. Check record keys, duplicates, placeholders, mismatched units and product forms, overlapping seasonal totals, and partial months. Independently reconcile representative price, arrival, and crop production figures. Use a notebook for exploration and move repeated calculations into Python functions as they stabilize. The milestone is complete when a fresh run reproduces the profile and figures, and the evidence supports an explicit decision about which state or mandi comparisons can be made.
2. **Statistics and machine learning.** Choose a state-month price series that passes the data proof. Plot seasonality and test whether missing periods and reporting changes affect the series. Use rolling historical cutoffs to compare a simple candidate model with the last observed price and the same month last year at one-, two-, and three-month horizons. Use only information available at each cutoff. Omit production revisions when the historical estimate vintage is unavailable. Record error on the same held-out months for each model. Document what the experiment can establish if too few comparable periods remain.
3. **AI and agent benchmark.** Start with a fixed report using the profiled data and verified calculations. Give the same functions and pinned snapshot to a single agent and then to a LangGraph workflow with market and production specialists. Use the same model in both agent variants and compare at a matched budget or record the difference. Include adequate and sparse mandi data, conflicting state signals, missing comparable evidence, stale data, failed tools, and complete and incomplete buyer quotes. Score reference arithmetic, evidence fidelity, supported next actions, and unsupported claims. Record latency, calls, tokens, retries, and cost. Agree scoring and promotion thresholds before scoring the agents.
4. **Buyer interface and trial.** Build a small interface around the proven report, evidence checks, and quote calculation. Give buyers matched sourcing cases across their usual tools, a simple dashboard with quote worksheet, and TradeAtlas. Vary the order and measure time to a supported action, correctness, and whether buyers can prepare a usable quote request. Set targets after measuring the baseline and before judging TradeAtlas.

Pinned historical extracts are sufficient to begin the learning exercises. A live buyer pilot depends on repeatable authorized refresh, agreed observation-age limits, and usage terms. Scope the pilot effort and budget after the data proof. Before implementation of each phase, agree on its inputs, observable outputs, error handling, files, and test fixtures.

## Goldfish review coverage

| Lens | Status |
| --- | --- |
| Design | Completed |
| Codebase details | Completed |
| Zoom out | Completed |
| Comprehension | Completed |
| Implementation readiness | Completed |
| Structural | Completed |
| Inventive catalyst | Completed. The shared checks and qualified fallback already address the trade-offs the lens examined. |
