import re
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

import pandas as pd

from groundnut_data import REPORTING_CHANGE, SOURCES, STATES, load_state_months, load_state_production


@dataclass(frozen=True)
class Quote:
    price_per_quintal: Decimal
    freight_per_tonne: Decimal | None
    available_tonnes: Decimal


@dataclass(frozen=True)
class SourcingRequest:
    start_month: str
    end_month: str
    crop_year: str
    quantity_tonnes: int = 100
    requested_grain: Literal["state", "mandi"] = "state"
    quote: Quote | None = None


@dataclass(frozen=True)
class Evidence:
    id: str
    statement: str


def load_evidence_tools() -> tuple[
    Callable[[SourcingRequest], list[Evidence]], Callable[[SourcingRequest], list[Evidence]]
]:
    """Load the pinned extracts once and return tools for querying their historical records."""
    prices, arrivals = load_state_months()
    production = load_state_production()
    partial_month = prices.index[-1]
    prices = prices.iloc[:-1]
    arrivals = arrivals.iloc[:-1]

    def market(request: SourcingRequest) -> list[Evidence]:
        if not all(re.fullmatch(r"[0-9]{4}-(0[1-9]|1[0-2])", month) for month in (
            request.start_month, request.end_month,
        )):
            raise ValueError("Market months must use YYYY-MM format")
        start = pd.Period(request.start_month, freq="M")
        end = pd.Period(request.end_month, freq="M")
        if start > end:
            raise ValueError("Start month must be on or before end month")

        requested_months = end.ordinal - start.ordinal + 1
        paired_prices = prices.loc[start:end, STATES].dropna()
        paired_arrivals = arrivals.loc[start:end, STATES].dropna()
        coverage = (
            f"AGMARKNET historical state-month Groundnut observations from {start} through {end} "
            f"have {len(paired_prices)} paired price months and {len(paired_arrivals)} paired arrival "
            f"months out of {requested_months} requested. The extract's potentially partial final "
            f"month ({partial_month}) is excluded. Aggregate state records support historical context. "
            "Confirm groundnut form, grade, quantity and current terms with suppliers. "
        )
        if request.requested_grain == "mandi":
            coverage += "Individual mandi rankings require verified mandi-level evidence. "
        if paired_prices.empty and paired_arrivals.empty:
            coverage += "There are no comparable state observations for the requested window. "
        if start < REPORTING_CHANGE <= end:
            coverage += "Reporting expanded in November 2025. Price summaries may reflect a change in coverage. "
        if not paired_arrivals.empty and paired_arrivals.index[0] < REPORTING_CHANGE <= paired_arrivals.index[-1]:
            paired_arrivals = paired_arrivals.iloc[0:0]
            coverage += "Use a window on one side of the reporting change to compare arrival totals. "
        evidence = [Evidence("market.coverage", coverage + SOURCES["state_monthly.csv.gz"][0])]

        for state in STATES:
            observations = []
            if not paired_prices.empty:
                observations.append(
                    f"Median reported wholesale price was INR {paired_prices[state].median():,.2f} "
                    f"per quintal over {len(paired_prices)} paired months"
                )
            if not paired_arrivals.empty:
                observations.append(
                    f"AGMARKNET reported {paired_arrivals[state].sum():,.2f} tonnes of arrivals "
                    f"over {len(paired_arrivals)} paired months"
                )
            if observations:
                statement = f"{state} ({start} to {end}). " + ". ".join(observations) + "."
                evidence.append(Evidence(f"market.{state.lower()}", statement))

        if not paired_prices.empty:
            spread = paired_prices["Gujarat"] - paired_prices["Rajasthan"]
            gujarat_lower = spread.lt(0).sum()
            rajasthan_lower = spread.gt(0).sum()
            interpretation = "The prices describe historical state aggregates."
            if gujarat_lower and rajasthan_lower:
                interpretation += " The lower-priced state changed. Seek comparable quotes from both states."
            evidence.append(Evidence(
                "market.spread",
                f"Median monthly Gujarat minus Rajasthan price was INR {spread.median():,.2f} per quintal. "
                f"Of {len(spread)} paired months ({spread.index[0]} to {spread.index[-1]}), Gujarat was "
                f"lower in {gujarat_lower}, Rajasthan was lower in {rajasthan_lower}, and "
                f"{spread.eq(0).sum()} tied. {interpretation}",
            ))
        return evidence

    def crop_production(request: SourcingRequest) -> list[Evidence]:
        rows = production.loc[production["Crop Year"].eq(request.crop_year)].dropna(
            subset=["Production (tonnes)", "Estimation Cycle"],
        )
        evidence = [Evidence(
            "production.coverage",
            f"The pinned UPAg extract contains groundnut production estimates for {len(rows)} of "
            f"{len(STATES)} requested states in crop year {request.crop_year}. These totals describe "
            f"crop production. Confirm purchasable quantities with suppliers. {SOURCES['apy_state.csv.gz'][0]}",
        )]
        for _, row in rows.sort_values("State").iterrows():
            state = row["State"]
            evidence.append(Evidence(
                f"production.{state.lower()}",
                f"UPAg estimates {state} groundnut production at {row['Production (tonnes)']:,.0f} tonnes "
                f"for crop year {request.crop_year} ({row['Estimation Cycle']}).",
            ))
        return evidence

    return market, crop_production


def quote_evidence(request: SourcingRequest) -> list[Evidence]:
    quote = request.quote
    if quote is None:
        return []

    quantity = request.quantity_tonnes
    if type(quantity) is not int or quantity <= 0:
        return [Evidence("quote.incomplete", "Enter a positive whole-tonne requirement to calculate the quote.")]
    if quote.freight_per_tonne is None:
        return [Evidence("quote.incomplete", "Enter a freight estimate to calculate the buyer-entered delivered quote.")]

    amounts = (quote.price_per_quintal, quote.freight_per_tonne, quote.available_tonnes)
    if not all(isinstance(amount, Decimal) and amount.is_finite() and amount >= 0 for amount in amounts):
        return [Evidence("quote.incomplete", "Enter finite, non-negative price, freight and available tonnes.")]
    if quote.price_per_quintal == 0 or quote.available_tonnes < quantity:
        return [Evidence("quote.incomplete", "Enter a positive price and an offer that covers the requested tonnes.")]

    delivered_per_tonne = quote.price_per_quintal * 10 + quote.freight_per_tonne
    return [Evidence(
        "quote.total",
        f"The buyer-entered price of INR {quote.price_per_quintal:,.2f} per quintal and freight of INR "
        f"{quote.freight_per_tonne:,.2f} per tonne give a delivered subtotal of INR "
        f"{delivered_per_tonne:,.2f} per tonne and INR {delivered_per_tonne * quantity:,.2f} for {quantity} tonnes. "
        "Confirm grade, quote validity and any other charges before using the subtotal.",
    )]
