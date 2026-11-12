# TradeAtlas Domain Glossary

Domain concepts and canonical terminology for agricultural commodity procurement intelligence and decision support in India.

## Commodity and Processing

**Edible Oilseeds Complex**:
The collective commodity scope encompassing Groundnut, Soybean, and Mustard/Rapeseed, representing over 85% of domestic Indian vegetable oil crushing and meal extraction.
_Avoid_: Oil crops, seed basket, mixed commodities

**Pod**:
Groundnut in its unshelled form containing the seeds within the pod shell as received from farm harvests.
_Avoid_: In-shell groundnut, raw unhulled peanut, unpeeled groundnut

**Kernel**:
The shelled groundnut seed obtained after decorticating pods, used by oil crushers and processors.
_Avoid_: Shelled peanut, groundnut seed, nut

**Shelling Outturn**:
The percentage by weight of kernels yielded from raw pods during decortication, benchmarked at 70%.
_Avoid_: Peeling ratio, hulling percentage, shelling fraction

**Kernel Equivalent Benchmark**:
The theoretical price of kernels derived from raw pod wholesale prices, calculated as `(Pod Price / 0.70) + Decortication Allowance`.
_Avoid_: Converted price, adjusted market price, synthetic kernel price

## Geography and Markets

**5-State Oilseed Corridor**:
The contiguous western and central agricultural production and processing hinterland spanning Gujarat, Rajasthan, Madhya Pradesh, Maharashtra, and Haryana.
_Avoid_: Western belt, farm states, northern region

**Benchmark Hub Mandi**:
A designated high-liquidity APMC market exhibiting continuous daily reporting, significant trade volume, and regional price-discovery authority within a state (e.g., Rajkot and Gondal in Gujarat; Bikaner and Kota in Rajasthan; Indore and Ujjain in Madhya Pradesh; Latur in Maharashtra; Rewari in Haryana).
_Avoid_: Target yard, active market, top mandi

## Pricing, Cost, and Support

**Delivered Cost**:
The total landed procurement cost per tonne at the buyer's facility, combining base price, freight, and ancillary charges.
_Avoid_: Landed price, all-in price, purchase total

**State Spread**:
The difference in monthly benchmark wholesale prices between Gujarat and Rajasthan for a matched calendar period.
_Avoid_: Price gap, inter-state arbitrage, basis differential

**Freight Buffer**:
The minimum inter-state transportation cost per unit required to justify sourcing from an out-of-state producing region.
_Avoid_: Transport spread, shipping margin, haulage allowance

**Full-Lot Quote**:
A supplier quotation offering available volume equal to or exceeding the buyer's total requested requirement.
_Avoid_: Complete order, bulk quote, single-ticket offer

**Ancillary Charges**:
Mandatory statutory or operational costs incurred during procurement, such as mandi cess, loading/unloading, weighment, and brokerage.
_Avoid_: Hidden fees, extra expenses, handling charges

**MSP Spread**:
The numerical difference between the prevailing mandi modal price and the official central Minimum Support Price (`Modal Price - MSP`). A negative spread indicates trading at a discount to MSP, signaling localized supply gluts or farmer distress sales.
_Avoid_: MSP delta, government gap, support discount

## Data and Reporting

**Macro Supply Context**:
Regional crop production and seasonal timing estimates from UPAg used to evaluate macro harvest scale, distinct from liquid trade inventory.
_Avoid_: Inventory data, market supply, purchasable stock

**Macro Supply Balance**:
The percentage variance between a crop season's latest advance production estimate from UPAg and its 3-year historical baseline, indicating regional harvest surplus or deficit.
_Avoid_: Harvest ratio, production shift, yield health

**Reporting Break**:
The November 2025 structural discontinuity in AGMARKNET data resulting from the platform upgrade, preventing arrival volume aggregation across the boundary.
_Avoid_: Data anomaly, portal glitch, missing data

**Evidence Card**:
An immutable, deterministically computed statement of verified market or production observation, including coverage limits.
_Avoid_: LLM assertion, insight bullet, agent observation

**Tiered Coverage**:
The two-tier honesty guarantee for commodity scope: deep-tier commodities carry the full verification set (coverage checks, reconciliation, backtests), while thin-tier commodities are served live but explicitly labelled as unverified coverage.
_Avoid_: Full coverage, verified data, beta quality

**Golden Suite**:
A versioned set of evaluation questions with expected evidence and a scoring rubric, used to gate a milestone's exit.
_Avoid_: Test set, QA checklist, benchmark folder

**Verification Gate**:
The deterministic check that every numeric value and entity in an agent-generated briefing matches the supplied Evidence Cards before the report reaches a user.
_Avoid_: LLM self-check, hallucination filter, fact-check prompt

**Qualified Partial Report**:
A report issued with explicitly named data gaps and next verification steps when full evidence is unavailable, instead of an unsupported complete answer.
_Avoid_: Best-effort answer, partial guess, degraded report
