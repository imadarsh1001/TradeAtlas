"""Structured final answer: every figure carries its provenance (source tool + selector)."""

import math
from typing import Any, Dict, List

from pydantic import BaseModel, Field, field_validator


class AnswerFigure(BaseModel):
    """One numeric figure, traceable to the envelope that produced it.

    Runtime-enforced provenance: the cited source tool must be one of the seven
    evidence-card tools, and the value must be finite (no NaN/inf in records).
    Cross-checking the citation against the tools actually invoked this run is
    the M3-d verifier's job.
    """

    value: float
    unit: str
    source_tool: str
    selector: Dict[str, Any]

    @field_validator("value")
    @classmethod
    def _finite_value(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("figure value must be finite")
        return v

    @field_validator("source_tool")
    @classmethod
    def _known_tool(cls, v: str) -> str:
        from tradeatlas.agent.tools import AGENT_TOOL_NAMES  # deferred: tools imports services

        if v not in AGENT_TOOL_NAMES:
            raise ValueError(f"source_tool {v!r} is not one of the evidence-card tools")
        return v


class AgentAnswer(BaseModel):
    """Deliver the final answer to the user's question.

    Call this tool EXACTLY ONCE, when your evidence gathering is complete. Pass the
    buyer-facing summary and every figure the evidence supports — each figure naming
    its source tool and the exact selector arguments that produced it. When the
    evidence is unavailable or reports no data, call it anyway with an EMPTY figures
    list and a summary naming what is missing and the latest available facts with
    their observation dates. Never invent figures; never restate another tool's data
    as a different metric."""

    summary: str
    figures: List[AnswerFigure] = Field(default_factory=list)
