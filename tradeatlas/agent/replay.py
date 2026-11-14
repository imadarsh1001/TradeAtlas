"""Offline replay: drive the agent graph with a recorded model trace — no network, no live model.

The trace holds the model's messages only (content, tool calls, usage metadata); the
agent's tools execute for real against the test environment's hermetic fixtures, so a
replay exercises the whole graph. Recording real runs (a save path) arrives with M3-b.
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from pydantic import Field

TRACE_VERSION = 1
TRACES_DIR = Path(__file__).resolve().parents[2] / "evals" / "traces"


def load_trace(path: Any) -> Dict[str, Any]:
    """Load and validate a trace fixture (versioned like the golden suites)."""
    trace = json.loads(Path(path).read_text(encoding="utf-8"))
    if trace.get("version") != TRACE_VERSION:
        raise ValueError(
            f"Unsupported trace version {trace.get('version')!r} in {path} (expected {TRACE_VERSION})"
        )
    return trace


def save_trace(
    question: str, model_messages: List[Any], structured_response: Any, path: Any, model_id: Optional[str] = None
) -> Path:
    """Export a run as a trace file the loader reads (completes the M3-a load-only format).

    `model_messages` is the run's model messages (AIMessages: content, tool calls,
    usage metadata); anything else in the transcript (human/tool messages) is
    replay-executed, not recorded. `model_id` records what produced the trace —
    committed replay sets stay attributable.
    """
    entries = []
    for message in model_messages:
        if type(message).__name__ != "AIMessage":
            continue
        entries.append(
            {
                "role": "ai",
                "content": message.content if isinstance(message.content, str) else str(message.content),
                "tool_calls": [
                    {"name": call["name"], "args": call["args"], "id": call["id"], "type": "tool_call"}
                    for call in (getattr(message, "tool_calls", None) or [])
                ],
                "usage_metadata": getattr(message, "usage_metadata", None),
            }
        )
    if not entries:
        raise ValueError("save_trace: no model messages to record")
    answer = structured_response
    if hasattr(answer, "model_dump"):
        answer = answer.model_dump(mode="json")
    trace = {"version": TRACE_VERSION, "question": question, "model_id": model_id, "model_messages": entries, "structured_response": answer}
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(trace, indent=2), encoding="utf-8")
    return destination


def trace_messages(trace: Dict[str, Any]) -> List[AIMessage]:
    """Reconstruct the recorded model messages in order."""
    messages: List[AIMessage] = []
    for entry in trace["model_messages"]:
        if entry.get("role") != "ai":
            raise ValueError(f"Trace messages must be model ('ai') messages, got {entry.get('role')!r}")
        messages.append(
            AIMessage(
                content=entry.get("content", ""),
                tool_calls=entry.get("tool_calls") or [],
                usage_metadata=entry.get("usage_metadata"),
            )
        )
    return messages


class ScriptedChatModel(BaseChatModel):
    """Returns the next recorded message per invocation; structured output comes from the trace."""

    recorded: List[AIMessage]
    structured_response: Dict[str, Any]
    index: int = 0
    received_messages: List[List[Any]] = Field(default_factory=list)

    def _generate(self, messages: List[Any], stop: Optional[List[str]] = None,
                  run_manager: Optional[Any] = None, **kwargs: Any) -> ChatResult:
        self.received_messages.append(list(messages))
        if self.index >= len(self.recorded):
            raise RuntimeError(f"Trace exhausted: model invoked more than {len(self.recorded)} times")
        message = self.recorded[self.index]
        self.index += 1
        return ChatResult(generations=[ChatGeneration(message=message)])

    def bind_tools(self, *args: Any, **kwargs: Any) -> "ScriptedChatModel":
        return self  # scripted: tool binding is a no-op

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        def _answer(_messages: Any) -> Any:
            self.received_messages.append(list(_messages) if isinstance(_messages, list) else [_messages])
            return schema.model_validate(self.structured_response)  # validates or raises

        return RunnableLambda(_answer)

    @property
    def _llm_type(self) -> str:
        return "scripted-trace"


def scripted_model(trace: Dict[str, Any]) -> ScriptedChatModel:
    """A scripted model replaying this trace (and recording every message it receives)."""
    return ScriptedChatModel(
        recorded=trace_messages(trace),
        structured_response=trace["structured_response"],
    )
