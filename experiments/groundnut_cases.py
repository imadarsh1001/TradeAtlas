from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from groundnut_evidence import Quote, SourcingRequest


@dataclass(frozen=True)
class Case:
    name: str
    question: str
    request: SourcingRequest
    required_ids: frozenset[str]
    unavailable_tool: Literal["market", "production"] | None = None


CASES = (
    Case(
        "matched-state-months",
        "Compare Gujarat and Rajasthan groundnut prices and reported arrivals from "
        "January through March 2026. Give the 2025–26 production estimates as context.",
        SourcingRequest("2026-01", "2026-03", "2025-26"),
        frozenset({
            "market.gujarat", "market.rajasthan", "market.spread", "market.coverage",
            "production.gujarat", "production.rajasthan",
        }),
    ),
    Case(
        "unsupported-mandi-ranking",
        "Which individual mandi should I contact for groundnut based on January "
        "through March 2026? If the data only supports a state comparison, give that.",
        SourcingRequest("2026-01", "2026-03", "2025-26", requested_grain="mandi"),
        frozenset({"market.coverage", "market.spread"}),
    ),
    Case(
        "reversing-price-lead",
        "Did the same state have a lower monthly groundnut price throughout June "
        "to August 2026? Explain what the price differences show.",
        SourcingRequest("2026-06", "2026-08", "2025-26"),
        frozenset({"market.spread", "market.coverage"}),
    ),
    Case(
        "outside-source-coverage",
        "Can you compare reported prices and arrivals for January to March 2027 "
        "and show the crop-year 2026–27 production for both states?",
        SourcingRequest("2027-01", "2027-03", "2026-27"),
        frozenset({"market.coverage", "production.coverage"}),
    ),
    Case(
        "partial-final-month",
        "Compare state groundnut prices from August through October 2026 and "
        "explain how many complete months support the result.",
        SourcingRequest("2026-08", "2026-10", "2025-26"),
        frozenset({"market.coverage", "market.spread"}),
    ),
    Case(
        "market-tool-failure",
        "Compare January through March 2026 market data and give the 2025–26 "
        "production estimates. Say which evidence you could retrieve.",
        SourcingRequest("2026-01", "2026-03", "2025-26"),
        frozenset({"market.unavailable", "production.gujarat", "production.rajasthan"}),
        unavailable_tool="market",
    ),
    Case(
        "complete-quote",
        "For a 100-tonne groundnut order, a supplier quotes INR 7,000 per quintal "
        "and freight of INR 2,000 per tonne. The supplier confirms 100 tonnes "
        "are available. What is the delivered cost for the order?",
        SourcingRequest(
            "2026-01", "2026-03", "2025-26",
            quote=Quote(Decimal("7000"), Decimal("2000"), Decimal("100")),
        ),
        frozenset({"quote.total"}),
    ),
    Case(
        "missing-quote-freight",
        "For a 100-tonne groundnut order, a supplier quotes INR 7,000 per quintal "
        "and confirms 100 tonnes are available. Freight is still unquoted. "
        "What delivered cost can I calculate from this information?",
        SourcingRequest(
            "2026-01", "2026-03", "2025-26",
            quote=Quote(Decimal("7000"), None, Decimal("100")),
        ),
        frozenset({"quote.incomplete"}),
    ),
)
