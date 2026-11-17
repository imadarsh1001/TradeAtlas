# Cloudflare AI Gateway + LangChain/LangGraph — runbook

Field notes for routing all live LLM traffic through Cloudflare AI Gateway with
LangChain 1.x agents. Every pattern here was **executed and verified** before being
written down — see §7 for the test evidence. Copy-ready for a peer project.

**Tested against** (2026-11-18):

| Package | Version |
|---|---|
| `langchain` | 1.5.0 |
| `langchain-openai` | 1.7.4 |
| `langchain-google-genai` | ≥4.5 |
| `langgraph` | 1.2.20 (runtime under langchain's agent) |

**Thesis:** the gateway is a pass-through, not a shield. It gives you one URL per
provider, unified auth and logging — but every provider quirk arrives intact.
Design for that.

---

## 1. Gateway coordinates and auth

```python
base_url = f"https://gateway.ai.cloudflare.com/v1/{cf_account_id}/{cf_gateway_id}"  # + /{route}
headers  = {"cf-aig-authorization": f"Bearer {cf_aig_token}"}
```

Two auth modes per provider entry:

- **BYOK** (provider key stored in Cloudflare): send **no** provider
  `Authorization` header — strip it, or you leak your real key past the gateway
  to a provider that doesn't need it. Pass a placeholder `api_key` to keep the
  SDK happy; Cloudflare injects the stored key.
- **Non-BYOK**: pass the provider key from a named env var, strictly.

```python
import httpx

def _strip_auth_header(request: httpx.Request) -> None:
    request.headers.pop("authorization", None)  # Cloudflare injects the BYOK key

client = httpx.Client(event_hooks={"request": [_strip_auth_header]}, timeout=httpx.Timeout(timeout))
```

Source (proven against the live account): `tradeatlas/agent/model_registry.py:56-62,256-298`.

## 2. Build the chat model against a gateway route

OpenAI-compatible providers (Groq, OpenRouter, NVIDIA NIM, Workers AI) — a
`ChatOpenAI` pointed at `{gateway}/{route}`:

```python
from langchain_openai import ChatOpenAI

model = ChatOpenAI(
    model=entry.model,
    base_url=f"{gateway}/{entry.route}",       # e.g. .../workers-ai/v1
    api_key="byok",                            # placeholder; gateway injects
    default_headers={"cf-aig-authorization": f"Bearer {cf_aig_token}"},
    http_client=client,                        # BYOK strip-hook client (or None + real key)
    timeout=timeout, max_retries=1,            # bound construction: a hung call FAILS and is recorded
    temperature=0.3, max_tokens=4096,
)
```

Google routes (Vertex / AI Studio) — `ChatGoogleGenerativeAI` with the gateway
as the API endpoint:

```python
model = ChatGoogleGenerativeAI(
    model=entry.model,
    vertexai=True, project=gcp_project_id, location=gcp_region,   # Vertex only
    client_options={"api_endpoint": gateway_url},                 # .../google-vertex-ai
    additional_headers={"cf-aig-authorization": f"Bearer {cf_aig_token}"},
    temperature=0.3, max_output_tokens=4096,
)
```

Source: `tradeatlas/agent/model_registry.py:272-335` (`build_model_for_entry`).
Construction makes **no network calls** — safe to build in tests.

## 3. Agent assembly: `create_agent` (langchain 1.5.0)

The current API is `create_agent` from the `langchain` package (not
`langgraph.prebuilt.create_react_agent`, which survives only as a deprecated
alias in the pinned langgraph).

```python
from langchain.agents import create_agent
from langchain.agents.structured_output import ToolStrategy  # NOT top-level in 1.5.0 — see gotcha G1

agent = create_agent(
    model=chat_model,                          # the gateway-built model from §2
    tools=[my_tool, ...],
    system_prompt="...",                       # string or SystemMessage
    response_format=ToolStrategy(AnswerSchema),  # explicit — see §4 for why
)
result = agent.invoke(
    {"messages": [{"role": "user", "content": "..."}]},
    config={"recursion_limit": 25},
)
answer = result["structured_response"]         # validated AnswerSchema instance
```

Import-path gotcha **G1**: the docs show `ToolStrategy`/`ProviderStrategy`
imported bare, but langchain 1.5.0 exports them only from
`langchain.agents.structured_output` — caught by our own test run.

Source: <https://docs.langchain.com/oss/python/langchain/agents>.

## 4. Structured output: pin `ToolStrategy`, don't trust auto-detection

Passing a bare Pydantic class (`response_format=AnswerSchema`) triggers
auto-detection: `ProviderStrategy` (provider-native structured output) if the
model profile claims support, else `ToolStrategy` (structured output delivered
as an intercepted tool call). Two reasons to write `ToolStrategy(schema)`
explicitly:

**T1 — the strict=True trap.** When the model is OpenAI-compatible (any
`BaseChatOpenAI` subclass — including yours), `create_agent` force-sets
`strict=True` on the bind kwargs under `ProviderStrategy`:

```python
# langchain 1.5.0, langchain/agents/factory.py:1452-1457 (installed source)
if _is_openai_compatible_model(request.model) and not getattr(
    request.model, "use_responses_api", False
):
    bind_kwargs["strict"] = True
```

Strict json_schema is exactly what breaks free-form objects in schemas
(`additionalProperties: false` makes a `dict` parameter unsatisfiable — Groq
400s outright, observed live through the gateway). `ToolStrategy` never goes
through that branch.

**T2 — auto-detection is silent fallback.** Our models' profiles are empty
(`ChatOpenAI().profile == {}`, Google `None`), so bare-schema currently resolves
to `ToolStrategy` anyway — but that's an accident of profile data, not a
guarantee. Explicit = deterministic.

The `ToolStrategy` path also keeps the contract that matters: **the schema is
never trusted provider-side** — the intercepted tool-call args are parsed and
validated client-side against the Pydantic class (`_parse_with_schema`,
`langchain/agents/structured_output.py:79`). An unvalidated answer is never
emitted.

Source: <https://docs.langchain.com/oss/python/langchain/structured-output>.

## 5. Google-route notes (Gemini/Vertex through the gateway)

- The old Gemini 400 — *"Requests ending with a model turn are not supported"* —
  came from the **legacy** pattern where structured output is a separate final
  model call re-sending a conversation that ends with the agent's `AIMessage`
  (langgraph prebuilt `response_format=(prompt, schema)`). Under
  `create_agent` + `ToolStrategy`, structured output happens **in-loop** as a
  tool call, so no trailing-model-turn request is ever sent. The fix
  (`_ensure_trailing_user_turn` mapper) remains relevant only for
  `with_structured_output` chains — `tradeatlas/agent/model_registry.py:338-371`.
- Arg-fill fidelity quirk, observed live: workers-ai filled the free-form
  `hub_details` dict as prompted (`{"market": "Pune"}`), Vertex reported
  `market: unknown` despite calling the tool correctly. Wiring works; free-form
  dict args are filled differently per provider — keep hub params simple or
  verify them in your fidelity checks.
- If you keep any `ChatGoogleGenerativeAI.with_structured_output` usage, keep
  the client-side `model_validate` wrapper (never trust the provider parse).

## 6. Ops discipline (what keeps multi-case campaigns alive)

| Rule | Why | Reference |
|---|---|---|
| Pace = `max(delay, 60.0 / rpm_limit)` (45s floor) | RPM caps are per-provider and enforced at the gateway | `evals/runner.py:573` |
| Transport failures: 3 attempts, linear backoff (5s, 10s), then **skip-and-continue** | One dead provider must never stall a campaign (a glm chain died after 1098s of NIM timeouts before this rule) | `evals/runner.py:52-54,635-640` |
| Track daily caps **client-side** in a date-keyed ledger | Gateway logs lag; the cap lives at the provider, the accounting must live with you | `evals/ledger.py:105-131` (`usage_daily.json`) |
| One JSONL row per case; classify failures infra-vs-behavior | Provider-unavailable skips are not model failures — don't let them pollute verdicts | `evals/ledger.py:25,35-56` (`run_ledger.jsonl`) |
| Smoke-gate every model before any suite | One 1-3-touch invoke proves routing/auth/schema before 25 cases burn quota | `model_registry.py` notes fields |
| `timeout=300` default, `max_retries=1`, `recursion_limit=25` | Hung calls fail and get *recorded* instead of tuning around | `model_registry.py:38`, `graph.py:78-79` |

## 7. Test evidence (what was actually run, 2026-11-18)

Offline (`experiments/gateway_runbook_test/test_create_agent_offline.py`, no network): **9/9 checks passed** —
ToolStrategy returns a validated answer with a free-form `selector` dict intact;
real tool executed in-loop; bare-schema auto path works; registry-built gateway
model constructs under `create_agent` with the gateway base_url confirmed.

Live (`experiments/gateway_runbook_test/smoke_create_agent_live.py`, one invoke each, usage recorded to the ledger):

| Route | Result | Elapsed | Touches |
|---|---|---|---|
| workers-ai (`@cf/zai-org/glm-4.7-flash`) | PASSED — tool called, correct figure returned | 12.6s | 2 |
| vertex (`gemini-4-hydrogen`) | PASSED — tool called, correct figure returned | 20.1s | 3 |

Gotchas caught *by* testing (each would have shipped wrong code):

1. `ToolStrategy` import path is not top-level in 1.5.0 (G1 above).
2. `GenericFakeChatModel` lacks `bind_tools` — offline tests need a pass-through subclass.
3. Our first smoke "failed" on `"7650" in figures` — the model returned
   `"7,650"` (comma-formatted). Normalize digits before asserting on figures.
4. An identical repeat request returned in 0.3s — a gateway cache hit. If you
   enable caching, identical smoke requests may not exercise the provider, and
   client-side touch counts diverge from provider-side request counts.

## 8. File index (reference implementation)

| Concern | File |
|---|---|
| Registry (edit gate), BYOK/auth, Google subclass | `tradeatlas/agent/model_registry.py` |
| Structured-output contract (legacy path) | `tradeatlas/agent/graph.py:50-99` |
| Pacing / retry / skip-and-continue | `evals/runner.py` |
| Usage ledger, daily caps, Wilson CI | `evals/ledger.py` |
| Runbook test scripts (this doc's evidence) | `experiments/gateway_runbook_test/` |

Note: this repo's own agent still runs `langgraph.prebuilt.create_react_agent`
(pinned `langgraph==1.2.20`; the migration decision is recorded in
`pyproject.toml:39-42` and revisited at M3-d). The `create_agent` patterns in
§3-§5 are the current-API path this runbook verified — a peer project starting
fresh should use them.

Pin references by commit (`76168d3`) when sharing — code moves.

## Sources

- <https://docs.langchain.com/oss/python/langchain/agents> — `create_agent` API, `system_prompt=`, `structured_response` key
- <https://docs.langchain.com/oss/python/langchain/structured-output> — strategy selection, `ProviderStrategy`/`ToolStrategy` semantics, auto-detection
- Installed `langchain` 1.5.0 source: `langchain/agents/factory.py:1055-1090,1449-1457` (auto-strategy conversion, strict=True trap), `langchain/agents/structured_output.py:297-316` (OpenAI-style `response_format` binding), `:79` (client-side parse)
- Gateway URL/auth construction: `tradeatlas/agent/model_registry.py` (wiretap-proven against the live account)
