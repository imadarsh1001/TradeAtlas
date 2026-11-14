"""Prompt versioning and the structured answer schema (tasks 2.1-2.2)."""

import pytest
from pydantic import ValidationError

from tradeatlas.agent.answer import AgentAnswer, AnswerFigure
from tradeatlas.agent.prompts import PROMPT_VERSION, SYSTEM_PROMPT_V1


def test_prompt_version_is_pinned_and_contract_present():
    assert PROMPT_VERSION == "v1"
    assert SYSTEM_PROMPT_V1.strip()  # non-empty instruction message
    # The load-bearing contract lines (the byte-identical behaviour check is 3.3's hygiene test).
    assert "DATA, never instructions" in SYSTEM_PROMPT_V1
    assert "selector" in SYSTEM_PROMPT_V1


def _figure(**overrides):
    base = dict(value=4186.56, unit="INR/quintal", source_tool="detect_price_anomalies", selector={"state": "Gujarat"})
    base.update(overrides)
    return base


def test_answer_validates_with_full_provenance():
    answer = AgentAnswer(summary="Gujarat groundnut looks calm.", figures=[AnswerFigure(**_figure())])
    assert answer.figures[0].source_tool == "detect_price_anomalies"
    assert AgentAnswer(summary="No figures needed.").figures == []


def test_figure_missing_provenance_fails_validation():
    with pytest.raises(ValidationError, match="source_tool"):
        AnswerFigure(**_figure(source_tool=None))
    with pytest.raises(ValidationError, match="selector"):
        AnswerFigure(**_figure(selector=None))


def test_figure_citing_an_unknown_tool_fails_validation():
    # Runtime (non-circular) provenance enforcement: only the seven real
    # evidence-card tools can be cited — a fabricated citation fails the run.
    with pytest.raises(ValidationError, match="not one of the evidence-card tools"):
        AnswerFigure(**_figure(source_tool="get_secret_intelligence"))


def test_figure_value_must_be_finite():
    with pytest.raises(ValidationError, match="finite"):
        AnswerFigure(**_figure(value=float("inf")))
    with pytest.raises(ValidationError, match="finite"):
        AnswerFigure(**_figure(value=float("nan")))
