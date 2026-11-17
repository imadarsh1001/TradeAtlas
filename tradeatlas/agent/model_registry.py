"""Model registry: every live-model decision in one reviewed place.

All agent LLM traffic routes through Cloudflare AI Gateway — the registry decides
WHICH models may run (enabled flags), HOW they are reached (routes, BYOK vs
explicit keys), and HOW they are called (parameters, timeout, RPM/daily limits).
Ported from the provider sandbox (experiments/llm_endpoints_test/) whose gateway
construction is wiretap-proven against the real account; the sandbox itself
stays free-form. Editing this file IS the review gate for adding, enabling, or
retiring a model — notes carry the reason, so a disabled entry explains itself.

The repo .env (git-ignored) is loaded at IMPORT time (python-dotenv) so
GatewaySettings sees real credentials in shell-less runs; tests pin their own
env values over whatever it loaded. The agent's OpenAI-compatible chat-model
subclass lives in graph.py (_AgentChatModel); the Google subclass below mirrors
its structured-output contract.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Literal, Optional

import httpx
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict
from langchain_core.runnables import RunnableLambda

ROOT_DIR = Path(__file__).resolve().parents[2]
_ENV_PATH = ROOT_DIR / ".env"
if _ENV_PATH.is_file():  # the data-side loader (ingest.get_api_key) is untouched
    load_dotenv(_ENV_PATH)

# Per-request timeout fallback for entries that declare none (BENCHMARK_FINDINGS
# discipline: a stack that cannot complete inside its window is reported, not
# tuned around — slow models declare a longer timeout in their own entry).
DEFAULT_TIMEOUT_S = 300.0

ProviderType = Literal["openai_compat", "google_ai_studio", "google_vertex"]


class GatewaySettings(BaseSettings):
    """Cloudflare AI Gateway coordinates and provider-key fallbacks from the environment."""

    model_config = SettingsConfigDict(env_file_encoding="utf-8", extra="ignore")

    cf_account_id: str
    cf_gateway_id: str
    cf_aig_token: str
    cf_wai_token: Optional[str] = None
    nvidia_api_key: Optional[str] = None
    gcp_project_id: Optional[str] = None  # Vertex-only
    gcp_region: str = "global"

    @property
    def base_gateway_url(self) -> str:
        return f"https://gateway.ai.cloudflare.com/v1/{self.cf_account_id}/{self.cf_gateway_id}"

    @property
    def gateway_headers(self) -> Dict[str, str]:
        return {"cf-aig-authorization": f"Bearer {self.cf_aig_token}"}


@dataclass(frozen=True)
class ModelEntry:
    """One sanctioned model endpoint: identity, routing, limits, call parameters.

    `params` carries per-entry call parameters (temperature, max_tokens,
    reasoning_effort, provider-specific bodies, and optionally `timeout` in
    seconds — unset falls back to DEFAULT_TIMEOUT_S).
    """

    key: str
    provider_type: ProviderType
    model: str
    route: str
    enabled: bool = True
    use_byok: bool = True
    api_key_env: Optional[str] = None
    rpm_limit: int = 30
    daily_limit: Optional[int] = None  # provider-side requests/day cap (client-tracked)
    notes: str = ""
    params: Dict[str, Any] = field(default_factory=dict)


# ==============================================================================
# EDIT MODELS, LIMITS & PARAMETERS HERE (the review gate for model changes)
# ==============================================================================
MODEL_REGISTRY: list[ModelEntry] = [
    ModelEntry(
        key="groq",
        provider_type="openai_compat",
        model="qwen/qwen3.8-27b",
        route="groq",
        enabled=True,
        rpm_limit=30,
        daily_limit=500,  # developer-tier free daily request cap
        notes="Groq developer tier; Qwen3 reasoning prefers temp 0.6. Known quirk: "
        "server-side tool-call validation 400s malformed calls unrecoverably (intermittent).",
        params={"temperature": 0.6, "max_tokens": 4096, "reasoning_effort": "medium"},
    ),
    ModelEntry(
        key="openrouter_ling_3_2",
        provider_type="openai_compat",
        model="inclusionai/ling-3.2-flash:free",
        route="openrouter",
        enabled=True,
        rpm_limit=20,
        daily_limit=50,  # OpenRouter free tier: 50 requests/day
        notes="OpenRouter free tier (20 RPM default cap, 50 requests/day)",
        params={"temperature": 0.3, "max_tokens": 4096, "extra_body": {"reasoning": {"effort": "medium"}}},
    ),
    ModelEntry(
        key="nvidia_nim_nemotron",
        provider_type="openai_compat",
        model="nvidia/nemotron-3-ultra-550b-a55b",
        route="custom-nvidia-nim",
        enabled=True,
        use_byok=False,
        api_key_env="NVIDIA_API_KEY",
        rpm_limit=40,
        notes="NVIDIA NIM 550B flagship; temp 0.6 avoids reasoning loops",
        params={
            "temperature": 0.6,
            "max_tokens": 4096,
            "timeout": 90.0,
            "extra_body": {"chat_template_kwargs": {"enable_thinking": True}},
        },
    ),
    ModelEntry(
        key="nvidia_nim_minimax_m3_1",
        provider_type="openai_compat",
        model="minimaxai/minimax-m3.1-flash",
        route="custom-nvidia-nim",
        enabled=True,
        use_byok=False,
        api_key_env="NVIDIA_API_KEY",
        rpm_limit=40,
        notes="MiniMax M3.1 Flash (428B/23B MoE) - highest AA Intelligence & Tool-Use score",
        params={"temperature": 0.4, "max_tokens": 4096, "timeout": 45.0},
    ),
    ModelEntry(
        key="nvidia_nim_mistral_large_4",
        provider_type="openai_compat",
        model="mistralai/mistral-large-4-1t-a52b",  # exact NIM API model id
        route="custom-nvidia-nim",
        enabled=False,  # 30-40s queue latency on NIM
        use_byok=False,
        api_key_env="NVIDIA_API_KEY",
        rpm_limit=40,
        notes="Mistral Large 4 1T-A52B; reasoning_effort accepts 'high' or 'none'. "
        "Disabled by default due to 30-40s queue latency on NIM.",
        params={
            "temperature": 0.3,
            "max_tokens": 4096,
            "timeout": 45.0,
            "reasoning_effort": "high",  # NIM Mistral Large 4 only accepts "high" or "none"
        },
    ),
    ModelEntry(
        key="nvidia_nim_glm_5_3",
        provider_type="openai_compat",
        model="z-ai/glm-5.3-flash",  # dot in 5.3 (hyphenated 5-3 returns 404)
        route="custom-nvidia-nim",
        enabled=True,  # canonical benchmark model — enabled for the M3 exit-gate campaign
        use_byok=False,
        api_key_env="NVIDIA_API_KEY",
        rpm_limit=40,
        notes="GLM-5.3-Flash (the 11/15-buyer-cases benchmark stack); reasoning_effort accepts "
        "'low', 'high', or 'max'. NIM queue latency 50-67s: the entry timeout (180s) covers "
        "its 1-2 min reasoning turns — do not lower it for this stack.",
        params={"temperature": 0.4, "max_tokens": 4096, "timeout": 180.0, "reasoning_effort": "low"},
    ),
    ModelEntry(
        key="nvidia_nim_deepseek_4_1",
        provider_type="openai_compat",
        model="deepseek-ai/deepseek-v4.1-flash",
        route="custom-nvidia-nim",
        enabled=False,  # 50-67s queue latency on NIM
        use_byok=False,
        api_key_env="NVIDIA_API_KEY",
        rpm_limit=40,
        notes="NVIDIA NIM DeepSeek V4.1 Flash (high latency; enable for async batch tests)",
        params={
            "temperature": 0.6,
            "max_tokens": 4096,
            "timeout": 90.0,
            "extra_body": {"chat_template_kwargs": {"thinking": True}},
        },
    ),
    ModelEntry(
        key="google_ai_studio",
        provider_type="google_ai_studio",
        model="gemini-3.5-flash-lite",
        route="google-ai-studio",
        enabled=False,  # unproved in-agent (pre-gateway it 400'd with empty messages)
        rpm_limit=15,
        notes="Gateway construction proven raw; the in-agent structured-output path is not "
        "smoke-tested yet and daily caps are unknown — enable only after a live smoke passes. "
        "Keep temperature/top_p at model defaults to avoid 400 INVALID_ARGUMENT.",
        params={"max_output_tokens": 4096},
    ),
    ModelEntry(
        key="google_vertex",
        provider_type="google_vertex",
        model="gemini-4-hydrogen",
        route="google-vertex-ai",
        enabled=True,  # owner-authorized for the rotation — protocol still gates its first SUITE on a passing smoke
        rpm_limit=60,
        notes="Vertex AI enterprise quota; supports thinking_level='medium'. Enabled by owner for "
        "the rotation; the first live smoke must pass before it runs a suite (ADR 0007).",
        params={"temperature": 0.3, "max_output_tokens": 4096, "thinking_level": "medium"},
    ),
    ModelEntry(
        key="cf_workers_ai",
        provider_type="openai_compat",
        model="@cf/zai-org/glm-4.7-flash",
        route="workers-ai/v1",
        enabled=True,
        use_byok=False,
        api_key_env="CF_WAI_TOKEN",
        rpm_limit=300,
        daily_limit=500,  # free daily neurons tier — treat ~500 requests/day as the ceiling
        notes="Cloudflare Workers AI free daily neurons tier",
        params={"temperature": 0.3, "max_tokens": 4096, "reasoning_effort": "medium"},
    ),
]


def resolve_model_entry(selector: str) -> ModelEntry:
    """Resolve a selector (registry key or raw model id) to ONE enabled entry.

    Disabled entries are rejected naming their notes (the documented reason);
    unknown selectors are rejected naming the enabled alternatives.
    """
    matches = [entry for entry in MODEL_REGISTRY if selector in (entry.key, entry.model)]
    if not matches:
        enabled = [entry.key for entry in MODEL_REGISTRY if entry.enabled]
        raise RuntimeError(
            f"Unknown model selector {selector!r}; enabled registry keys: {enabled}"
        )
    if len(matches) > 1:
        raise RuntimeError(
            f"Ambiguous model selector {selector!r} matches multiple registry entries: "
            f"{[entry.key for entry in matches]}"
        )
    entry = matches[0]
    if not entry.enabled:
        raise RuntimeError(
            f"Model entry '{entry.key}' ({entry.model}) is disabled: {entry.notes or 'no notes recorded'}"
        )
    return entry


def _strip_auth_header(request: httpx.Request) -> None:
    """Strip Authorization so Cloudflare injects the BYOK-stored provider key."""
    request.headers.pop("authorization", None)


def _resolve_provider_key(entry: ModelEntry) -> str:
    """The non-BYOK provider key strictly from the entry's named environment variable."""
    value = os.environ.get(entry.api_key_env or "") if entry.api_key_env else None
    if not value:
        raise RuntimeError(
            f"Model entry '{entry.key}' requires {entry.api_key_env or 'a provider key'} in the "
            f"environment (non-BYOK auth); set it in .env or the shell"
        )
    return value


def build_model_for_entry(entry: ModelEntry, settings: Optional[GatewaySettings] = None) -> Any:
    """Build the live chat model from a registry entry (construction only — no network).

    openai_compat entries build the agent's ChatOpenAI subclass against the
    gateway route: BYOK entries send no provider Authorization (per-model httpx
    client strips it; Cloudflare injects stored keys), non-BYOK entries carry
    the named provider key. Google entries build the Google subclass with the
    gateway endpoint; both keep the structured-output contract (non-strict
    schema + client-side validation) via their subclasses.
    """
    cfg = settings if settings is not None else GatewaySettings()
    endpoint = f"{cfg.base_gateway_url}/{entry.route}"

    if entry.provider_type == "openai_compat":
        from tradeatlas.agent.graph import _AgentChatModel  # deferred: graph imports this module

        params = dict(entry.params or {})
        timeout = float(params.pop("timeout", DEFAULT_TIMEOUT_S))
        if entry.use_byok:
            client = httpx.Client(
                event_hooks={"request": [_strip_auth_header]},
                timeout=httpx.Timeout(timeout),  # the entry's resolved timeout, not the default
            )
            api_key = "byok"  # placeholder; the gateway injects the stored key
        else:
            client = None
            api_key = _resolve_provider_key(entry)
        return _AgentChatModel(
            model=entry.model,
            base_url=endpoint,
            api_key=api_key,
            default_headers=cfg.gateway_headers,
            http_client=client,
            timeout=timeout,
            max_retries=1,
            **params,
        )

    if entry.provider_type == "google_ai_studio":
        return _GoogleAgentChatModel(
            model=entry.model,
            google_api_key="byok",
            client_options={"api_endpoint": endpoint},
            additional_headers=cfg.gateway_headers,
            **(entry.params or {}),
        )

    if entry.provider_type == "google_vertex":
        if not cfg.gcp_project_id:
            raise RuntimeError(
                f"Model entry '{entry.key}' routes through Vertex AI and requires "
                "GCP_PROJECT_ID in the environment"
            )
        return _GoogleAgentChatModel(
            model=entry.model,
            vertexai=True,
            project=cfg.gcp_project_id,
            location=cfg.gcp_region,
            client_options={"api_endpoint": endpoint},
            additional_headers=cfg.gateway_headers,
            **(entry.params or {}),
        )

    raise ValueError(f"Unsupported provider_type: {entry.provider_type}")


class _GoogleAgentChatModel(ChatGoogleGenerativeAI):
    """ChatGoogleGenerativeAI with the agent's structured-output contract.

    Mirrors graph._AgentChatModel for the Google routes (which use
    ChatGoogleGenerativeAI, not the OpenAI-compatible client). langchain-google-
    genai's default method is already 'json_schema' (Gemini's native
    responseJsonSchema); the explicit setdefault documents the contract and
    guards against default drift, and the client-side model_validate wrapper
    keeps the M3-a guarantee — an unvalidated answer is never emitted.
    """

    def with_structured_output(self, schema: Any, **kwargs: Any) -> Any:
        if isinstance(schema, type) and issubclass(schema, BaseModel):
            kwargs.setdefault("method", "json_schema")
            inner = super().with_structured_output(schema.model_json_schema(), **kwargs)
            return inner | RunnableLambda(lambda value: schema.model_validate(value))
        return super().with_structured_output(schema, **kwargs)
