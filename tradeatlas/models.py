"""Evidence envelope: the self-describing output contract for every TradeAtlas tool.

Every tool output is wrapped in an EvidenceEnvelope (see the evidence-cards spec):
observation date(s) vs. retrieval time, coverage statement, deep/thin tier label,
and caveats — so no consumer can mistake stale, thin-tier, or gapped data for
verified intelligence (ADR 0002 discipline applied to the live layer).
"""

from datetime import datetime, timezone
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field


class EvidenceEnvelope(BaseModel):
    """Flat, self-describing wrapper for tool output. One model for every tool."""

    payload: Any
    coverage: str
    tier: Literal["deep", "thin"]
    retrieved_at: str
    observation_dates: List[str] = Field(default_factory=list)
    cached_as_of: Optional[str] = None
    caveats: List[str] = Field(default_factory=list)
    no_data: bool = False


def utc_now_iso() -> str:
    """Current UTC time as an ISO-8601 string (the only clock the package exposes)."""
    return datetime.now(timezone.utc).isoformat()
