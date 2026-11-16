"""Single-agent graph: create_react_agent over the seven evidence-card tools (ADR 0002 Build 1).

The structured response validates or raises — a non-conforming final output fails the
run (recorded) and is never emitted as an answer; retry machinery belongs to M3-d's
retry budget and is deliberately absent here. Model id comes from pinned configuration.
"""

import os
from typing import Any, List, Optional, Tuple

from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from langchain_openai import ChatOpenAI
from pydantic import BaseModel
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
    """The pinned model selector from configuration; clear error naming the variable when unset."""
    model_id = os.environ.get(MODEL_ENV_VAR)
    if not model_id:
        raise RuntimeError(
            f"Set {MODEL_ENV_VAR} to a model registry key or id for live agent runs "
            f"(e.g. 'groq'; see tradeatlas/agent/model_registry.py); "
            f"offline tests use scripted replay instead."
        )
    return model_id


class _AgentChatModel(ChatOpenAI):
    """ChatOpenAI with the agent's structured-output contract made provider-agnostic.

    langchain-openai coerces Pydantic-class schemas to strict json_schema, which
    providers reject for the free-form `selector` object the answer contract
    requires (`additionalProperties: false` is unsatisfiable — Groq 400s outright).
    Sending the JSON-schema dict with strict=False is accepted across providers;
    the model output is then validated client-side against the Pydantic class, so
    an unvalidated answer is still never emitted (the M3-a contract). The Google
    route's mirror subclass lives in model_registry.py (_GoogleAgentChatModel).
    """

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            kwargs.setdefault("method", "json_schema")
            kwargs.setdefault("strict", False)
            inner = super().with_structured_output(schema.model_json_schema(), **kwargs)
            return inner | RunnableLambda(lambda value: schema.model_validate(value))
        return super().with_structured_output(schema, **kwargs)


def build_chat_model(model_id: Optional[str] = None) -> Any:
    """Build the live chat model for the pinned selector, through the model registry.

    The selector (registry key or raw model id) must resolve to an ENABLED
    entry; routing (Cloudflare AI Gateway), auth (BYOK vs provider key), call
    parameters, and the per-entry timeout all come from that entry — model
    choice is a reviewed registry decision, never an implicit env default.
    Construction is bounded (timeout + max_retries=1) so a hung provider call
    fails and is recorded instead of stalling a benchmark for hours.
    """
    from tradeatlas.agent.model_registry import build_model_for_entry, resolve_model_entry  # deferred: registry lazily imports this module's _AgentChatModel

    entry = resolve_model_entry(model_id or get_model_id())
    return build_model_for_entry(entry)


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
    trace_path: Optional[Any] = None,
) -> Tuple[Optional[AgentAnswer], RunRecord]:
    """Answer one question, write a run record (success or failure), return (answer, record).

    With `trace_path` set, a successful run also exports its trace (the replay
    format) — the benchmark's per-case recording seam.
    """
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
        # The structured-response touch is a real model request but never enters
        # state messages (langgraph returns it as a separate key) — runs that reach
        # it count it explicitly so usage accounting and daily caps see every request.
        structured_call_happened = True
        structured = state.get("structured_response")
        answer = structured if isinstance(structured, AgentAnswer) else AgentAnswer.model_validate(structured)
    except Exception as exc:  # recorded, never raised past the run boundary
        failure = f"{type(exc).__name__}: {exc}"
        structured_call_happened = False

    if model_id is None:
        if chat_model is not None:
            model_id = getattr(chat_model, "model_name", None) or "unspecified-chat-model"
        else:
            try:
                # built via build_chat_model → name the raw model id, not the selector key
                from tradeatlas.agent.model_registry import resolve_model_entry

                model_id = resolve_model_entry(get_model_id()).model
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
        model_touches=sum(1 for m in state_messages if isinstance(m, AIMessage))
        + (1 if structured_call_happened else 0),
    )
    if trace_path is not None and answer is not None:
        from tradeatlas.agent.replay import save_trace  # deferred: replay imports are loader-side

        save_trace(question, state_messages, answer, trace_path, model_id=model_id)
    write_run_record(record, runs_dir)
    return answer, record
