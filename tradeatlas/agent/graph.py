"""Single-agent graph: create_agent (langchain 1.x) over the seven evidence-card tools (ADR 0002 Build 1).

The structured response validates or raises — a non-conforming final output fails the
run (recorded) and is never emitted as an answer; retry machinery belongs to M3-d's
retry budget and is deliberately absent here. Model id comes from pinned configuration.

Framework note (migrate-agent-to-create-agent): construction moved from the deprecated
langgraph.prebuilt.create_react_agent to langchain.agents.create_agent. The structured
answer is delivered by the final main-loop model call as an AgentAnswer tool call
(ToolStrategy — ProviderStrategy was rejected on installed-source evidence: create_agent
force-adds strict=True for OpenAI-compatible models, the wiretap-proven rejection path).
run_agent's extraction still validates against AgentAnswer, so an unvalidated answer is
never emitted. The replay contract (25 committed traces -> identical evidence-tool-call
sequences/outcomes) is this migration's acceptance gate.
"""

import os
from typing import Any, List, Optional, Tuple

from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy
from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI

from tradeatlas.agent.answer import AgentAnswer
from tradeatlas.agent.prompts import PROMPT_VERSION, SYSTEM_PROMPT_V4
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


def build_chat_model(model_id: Optional[str] = None) -> Any:
    """Build the live chat model for the pinned selector, through the model registry.

    The selector (registry key or raw model id) must resolve to an ENABLED
    entry; routing (Cloudflare AI Gateway), auth (BYOK vs provider key), call
    parameters, and the per-entry timeout all come from that entry — model
    choice is a reviewed registry decision, never an implicit env default.
    Construction is bounded (timeout + max_retries=1) so a hung provider call
    fails and is recorded instead of stalling a benchmark for hours.
    """
    from tradeatlas.agent.model_registry import build_model_for_entry, resolve_model_entry  # deferred: keeps the registry optional at import time

    entry = resolve_model_entry(model_id or get_model_id())
    return build_model_for_entry(entry)


def build_agent(chat_model: Any, recorder: Optional[ToolCallRecorder] = None) -> Any:
    """Assemble the single agent: pinned prompt, seven tools, validated AgentAnswer output.

    ToolStrategy(AgentAnswer) emits the structured answer as a tool call — chosen over
    ProviderStrategy after reading installed langchain 1.5.0 source: create_agent
    FORCE-adds strict=True for OpenAI-compatible models under ProviderStrategy
    ("Redundantly set strict=True..."), which is exactly the wiretap-proven rejection
    path (Groq/Gemini 400 on strict json_schema for the free-form selector).
    ToolStrategy is plain tool calling — proven across the whole rotation. run_agent
    validates the parsed answer against AgentAnswer, so an unvalidated answer is still
    never emitted.
    """
    return create_agent(
        chat_model,
        tools=build_agent_tools(recorder),
        system_prompt=SYSTEM_PROMPT_V4,
        response_format=ToolStrategy(AgentAnswer),
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
        # Under create_agent the structured answer is emitted BY the final main-loop
        # model call, so it is already among the captured messages — no separate touch
        # to count (the old create_react_agent shape counted it via a flag).
        structured = state.get("structured_response")
        answer = structured if isinstance(structured, AgentAnswer) else AgentAnswer.model_validate(structured)
    except Exception as exc:  # recorded, never raised past the run boundary
        failure = f"{type(exc).__name__}: {exc}"

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
        tool_calls=build_tool_call_records(state_messages, recorder,
                                           structured_tool_name=AgentAnswer.__name__),
        token_usage=sum_token_usage(state_messages),
        model_touches=sum(1 for m in state_messages if isinstance(m, AIMessage)),
    )
    if trace_path is not None and answer is not None:
        from tradeatlas.agent.replay import save_trace  # deferred: replay imports are loader-side

        save_trace(question, state_messages, answer, trace_path, model_id=model_id)
    write_run_record(record, runs_dir)
    return answer, record
