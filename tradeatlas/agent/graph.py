"""Single-agent graph: create_react_agent over the seven evidence-card tools (ADR 0002 Build 1).

The structured response validates or raises — a non-conforming final output fails the
run (recorded) and is never emitted as an answer; retry machinery belongs to M3-d's
retry budget and is deliberately absent here. Model id comes from pinned configuration.
"""

import os
from typing import Any, List, Optional, Tuple

from langchain_openai import ChatOpenAI
from langgraph.prebuilt import create_react_agent

from tradeatlas.agent.answer import AgentAnswer
from tradeatlas.agent.prompts import PROMPT_VERSION, SYSTEM_PROMPT_V1
from tradeatlas.agent.run_records import (
    RunRecord,
    build_tool_call_records,
    code_version,
    new_run_id,
    sum_token_usage,
    write_run_record,
)
from tradeatlas.agent.tools import ToolCallRecorder, build_agent_tools
from tradeatlas.models import utc_now_iso

MODEL_ENV_VAR = "TRADEATLAS_AGENT_MODEL"

# Explicit react-loop bound (graph steps; ~2 per model↔tool cycle). LangGraph raises
# GraphRecursionError at the limit, which run_agent records as a failure — the bound
# is a stated property of Build 1, not an implicit framework default.
RECURSION_LIMIT = 25


def get_model_id() -> str:
    """The pinned chat-model id from configuration; clear error naming the variable when unset."""
    model_id = os.environ.get(MODEL_ENV_VAR)
    if not model_id:
        raise RuntimeError(
            f"Set {MODEL_ENV_VAR} to the chat model id for live agent runs "
            f"(e.g. 'gpt-4.1-mini'); offline tests use scripted replay instead."
        )
    return model_id


def build_chat_model(model_id: Optional[str] = None) -> ChatOpenAI:
    """Build the live chat model for the pinned id (requires provider credentials)."""
    return ChatOpenAI(model=model_id or get_model_id())


def build_agent(chat_model: Any, recorder: Optional[ToolCallRecorder] = None) -> Any:
    """Assemble the single agent: pinned prompt, seven tools, validated AgentAnswer output.

    The response format uses the (prompt, schema) tuple form so the structured-response
    call — a separate model touch after the loop — is instructed by the same pinned
    prompt as the loop calls; no model touch ever happens without it.
    """
    return create_react_agent(
        chat_model,
        build_agent_tools(recorder),
        prompt=SYSTEM_PROMPT_V1,
        response_format=(SYSTEM_PROMPT_V1, AgentAnswer),
    )


def run_agent(
    question: str,
    chat_model: Optional[Any] = None,
    model_id: Optional[str] = None,
    runs_dir: Optional[Any] = None,
) -> Tuple[Optional[AgentAnswer], RunRecord]:
    """Answer one question, write a run record (success or failure), return (answer, record)."""
    recorder = ToolCallRecorder()
    started = utc_now_iso()
    state_messages: List[Any] = []
    answer: Optional[AgentAnswer] = None
    failure: Optional[str] = None
    try:
        model = chat_model if chat_model is not None else build_chat_model()
        agent = build_agent(model, recorder)
        state = agent.invoke(
            {"messages": [("user", question)]},
            config={"recursion_limit": RECURSION_LIMIT},
        )
        state_messages = state.get("messages", [])
        structured = state.get("structured_response")
        answer = structured if isinstance(structured, AgentAnswer) else AgentAnswer.model_validate(structured)
    except Exception as exc:  # recorded, never raised past the run boundary
        failure = f"{type(exc).__name__}: {exc}"

    if model_id is None:
        if chat_model is not None:
            model_id = getattr(chat_model, "model_name", None) or "unspecified-chat-model"
        else:
            try:
                model_id = get_model_id()
            except RuntimeError:
                model_id = f"unset:{MODEL_ENV_VAR}"  # failure_reason already records the cause
    record = RunRecord(
        run_id=new_run_id(),
        started_at=started,
        ended_at=utc_now_iso(),
        model_id=model_id,
        prompt_version=PROMPT_VERSION,
        code_version=code_version(),
        answer=answer.model_dump(mode="json") if answer is not None else None,
        failure_reason=failure,
        tool_calls=build_tool_call_records(state_messages, recorder),
        token_usage=sum_token_usage(state_messages),
    )
    write_run_record(record, runs_dir)
    return answer, record
