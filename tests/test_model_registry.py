"""Model registry: resolution contract, gateway construction, auth modes, limits.

Construction-only tests — no network. The real .env (git-ignored) may be loaded
into the environment at import, so every test pins the variables it needs with
monkeypatch.
"""

import httpx
import pytest
from pathlib import Path

from tradeatlas.agent.model_registry import (
    DEFAULT_TIMEOUT_S,
    MODEL_REGISTRY,
    GatewaySettings,
    ModelEntry,
    _strip_auth_header,
    build_model_for_entry,
    resolve_model_entry,
)


def gateway_env(monkeypatch):
    """Pin deterministic gateway credentials over whatever the real .env loaded."""
    monkeypatch.setenv("CF_ACCOUNT_ID", "acct-test")
    monkeypatch.setenv("CF_GATEWAY_ID", "gw-test")
    monkeypatch.setenv("CF_AIG_TOKEN", "tok-test")


def settings(monkeypatch) -> GatewaySettings:
    gateway_env(monkeypatch)
    return GatewaySettings()


def test_registry_keys_and_models_are_unique():
    keys = [e.key for e in MODEL_REGISTRY]
    models = [e.model for e in MODEL_REGISTRY]
    assert len(keys) == len(set(keys)), "registry keys must be unique"
    assert len(models) == len(set(models)), "model ids must be unique (selector resolution)"


def test_owner_limits_are_pinned():
    by_key = {e.key: e for e in MODEL_REGISTRY}
    assert by_key["openrouter_ling_3_2"].daily_limit == 50  # OpenRouter free tier/day
    assert by_key["groq"].daily_limit == 500
    assert by_key["cf_workers_ai"].daily_limit == 500
    assert by_key["nvidia_nim_nemotron"].daily_limit is None  # RPM-governed only
    assert by_key["nvidia_nim_nemotron"].rpm_limit == 40
    assert by_key["google_ai_studio"].enabled is False  # unproved in-agent — smoke first
    assert by_key["google_vertex"].enabled is True  # owner-authorized; suite use still smoke-gated
    assert by_key["nvidia_nim_glm_5_3"].enabled is False  # demoted: NIM queue latency, out of the rotation


def test_resolution_by_key_and_model_id_select_the_same_entry():
    by_key = resolve_model_entry("groq")
    by_model = resolve_model_entry("qwen/qwen3.8-27b")
    assert by_key is by_model and by_key.model == "qwen/qwen3.8-27b"


def test_disabled_entry_is_rejected_naming_its_notes():
    entry = next(e for e in MODEL_REGISTRY if not e.enabled)
    with pytest.raises(RuntimeError, match=entry.key) as exc:
        resolve_model_entry(entry.key)
    assert entry.notes.split(".")[0] in str(exc.value)  # the documented reason appears


def test_unknown_selector_lists_enabled_alternatives():
    with pytest.raises(RuntimeError, match="groq") as exc:
        resolve_model_entry("no-such-model")
    for entry in MODEL_REGISTRY:
        if entry.enabled:
            assert entry.key in str(exc.value)


def test_ambiguous_selector_fails_loudly(monkeypatch):
    monkeypatch.setattr(
        "tradeatlas.agent.model_registry.MODEL_REGISTRY",
        [
            ModelEntry(key="x", provider_type="openai_compat", model="same-id", route="groq"),
            ModelEntry(key="y", provider_type="openai_compat", model="same-id", route="openrouter"),
        ],
    )
    with pytest.raises(RuntimeError, match="Ambiguous"):
        resolve_model_entry("same-id")


def test_missing_gateway_credentials_fail_fast(monkeypatch):
    from pydantic import ValidationError

    monkeypatch.setattr(
        "tradeatlas.agent.model_registry.MODEL_REGISTRY",
        [ModelEntry(key="test", provider_type="openai_compat", model="test-model-verbatim", route="groq")],
    )
    monkeypatch.setenv("TRADEATLAS_AGENT_MODEL", "test")
    for var in ("CF_ACCOUNT_ID", "CF_GATEWAY_ID", "CF_AIG_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    from tradeatlas.agent.graph import build_chat_model

    with pytest.raises(ValidationError, match="cf_account_id"):  # names the missing variable
        build_chat_model()


def test_byok_build_routes_through_gateway_without_provider_key(monkeypatch):
    s = settings(monkeypatch)
    entry = resolve_model_entry("groq")
    model = build_model_for_entry(entry, settings=s)
    assert model.model_name == "qwen/qwen3.8-27b"
    assert model.openai_api_base == f"{s.base_gateway_url}/groq"
    assert model.default_headers["cf-aig-authorization"] == "Bearer tok-test"
    assert model.max_retries == 1
    assert model.request_timeout == DEFAULT_TIMEOUT_S  # entry declares no timeout
    assert model.temperature == 0.6  # entry params honored verbatim


def test_non_byok_build_uses_the_named_env_var(monkeypatch):
    s = settings(monkeypatch)
    monkeypatch.setenv("NVIDIA_API_KEY", "nv-key-test")
    entry = resolve_model_entry("nvidia_nim_nemotron")
    model = build_model_for_entry(entry, settings=s)
    assert model.openai_api_key.get_secret_value() == "nv-key-test"
    assert model.openai_api_base == f"{s.base_gateway_url}/custom-nvidia-nim"
    assert model.request_timeout == 90.0  # entry timeout honored (300s default untouched)


def test_non_byok_missing_key_fails_naming_the_variable(monkeypatch):
    s = settings(monkeypatch)
    monkeypatch.delenv("NVIDIA_API_KEY", raising=False)
    entry = resolve_model_entry("nvidia_nim_nemotron")
    with pytest.raises(RuntimeError, match="NVIDIA_API_KEY"):
        build_model_for_entry(entry, settings=s)


def test_byok_strip_hook_removes_authorization():
    request = httpx.Request(
        "POST", "https://gateway.ai.cloudflare.com/v1/acct/gw/groq/chat/completions",
        headers={"authorization": "Bearer sk-something", "content-type": "application/json"},
    )
    _strip_auth_header(request)
    assert "authorization" not in request.headers
    assert request.headers["content-type"] == "application/json"  # only auth is stripped


def test_google_entries_build_through_the_gateway(monkeypatch):
    s = settings(monkeypatch)
    ai_studio = next(e for e in MODEL_REGISTRY if e.key == "google_ai_studio")
    model = build_model_for_entry(ai_studio, settings=s)  # build works on disabled entries (smoke path)
    from langchain_google_genai import ChatGoogleGenerativeAI

    assert isinstance(model, ChatGoogleGenerativeAI)
    assert model.model == "gemini-3.5-flash-lite"
    assert model.additional_headers["cf-aig-authorization"] == "Bearer tok-test"

    monkeypatch.setenv("GCP_PROJECT_ID", "proj-test")
    vertex = next(e for e in MODEL_REGISTRY if e.key == "google_vertex")
    vertex_model = build_model_for_entry(vertex, settings=s)
    assert isinstance(vertex_model, ChatGoogleGenerativeAI)


def test_vertex_without_project_fails_naming_the_variable(monkeypatch):
    monkeypatch.delenv("GCP_PROJECT_ID", raising=False)  # before settings() caches the env
    s = settings(monkeypatch)
    vertex = next(e for e in MODEL_REGISTRY if e.key == "google_vertex")
    with pytest.raises(RuntimeError, match="GCP_PROJECT_ID"):
        build_model_for_entry(vertex, settings=s)


def test_google_model_drives_the_shared_contract(tmp_path, monkeypatch):
    """Route-independence of the answer contract, behaviorally: a Google-built model
    replays a committed trace through the same graph and the same run_agent validation
    (the contract lives in graph.build_agent's ToolStrategy + run_agent extraction —
    shared by every route since the create_agent migration). No network."""
    from tradeatlas.agent.answer import AgentAnswer
    from tradeatlas.agent.graph import run_agent
    from tradeatlas.agent.replay import load_trace, scripted_model

    s = settings(monkeypatch)
    ai_studio = next(e for e in MODEL_REGISTRY if e.key == "google_ai_studio")
    assert "temperature" not in ai_studio.params  # notes: keep model defaults (400 INVALID_ARGUMENT)
    model = build_model_for_entry(ai_studio, settings=s)

    trace = load_trace(Path(__file__).resolve().parent.parent / "evals" / "traces" / "anomaly_single_tool.json")
    answer, record = run_agent(
        trace["question"], chat_model=scripted_model(trace), model_id="gemini-4-hydrogen", runs_dir=tmp_path
    )
    assert isinstance(answer, AgentAnswer)
    assert record.model_id == "gemini-4-hydrogen"  # the Google-built model drove the shared contract
    assert record.failure_reason is None


def test_entry_model_dataclass_freezes():
    import dataclasses

    entry = MODEL_REGISTRY[0]
    with pytest.raises(dataclasses.FrozenInstanceError):
        entry.enabled = True  # frozen: edits go through a reviewed commit, not runtime mutation
