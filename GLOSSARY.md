# TradeAtlas Domain Glossary

Domain concepts and canonical terminology for agricultural commodity procurement intelligence and decision support in India.

## Commodity and Processing

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

## Pricing and Cost

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

## Data and Reporting

**Macro Supply Context**:
Regional crop production and seasonal timing estimates from UPAg used to evaluate macro harvest scale, distinct from liquid trade inventory.
_Avoid_: Inventory data, market supply, purchasable stock

**Reporting Break**:
The November 2025 structural discontinuity in AGMARKNET data resulting from the platform upgrade, preventing arrival volume aggregation across the boundary.
_Avoid_: Data anomaly, portal glitch, missing data

**Evidence Card**:
An immutable, deterministically computed statement of verified market or production observation, including coverage limits.
_Avoid_: LLM assertion, insight bullet, agent observation
