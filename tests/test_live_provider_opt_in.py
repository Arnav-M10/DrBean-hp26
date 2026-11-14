"""Live-path controls with a substituted SDK transport. No network or real key."""
import asyncio
import hashlib
import json
import os
from typing import Annotated

from fastapi.testclient import TestClient
import pytest
from pydantic import BaseModel, ConfigDict, Field

from bean_api.config import Settings
from bean_api.main import PREFIX, create_app, provider_config_from_env
from bean_api.providers import GeminiProvider, LIVE_MODEL, ProviderConfig, ProviderFailure, live_wire_schema
from test_intake import png
from test_provider import Answer, Client, Ledger, context, response


def live_config(**overrides):
    return ProviderConfig(**{
        "mode": "live", "model": LIVE_MODEL, "api_key": "AIza" + "a" * 35,
        "account_gate_passed": True, "account_decision_id": "explicit-local-test-opt-in",
        "free_tier_user_asserted": True, "image_token_upper_bound": 8192,
        "max_input_tokens": 24000, "max_output_tokens": 4096, **overrides,
    })


def enable_env(monkeypatch):
    for key, value in {
        "BEAN_AI_MODE": "live_opt_in", "BEAN_GEMINI_FREE_TIER_ONLY": "1",
        "GEMINI_API_KEY": "AIza" + "a" * 35, "GEMINI_MODEL": LIVE_MODEL,
        "BEAN_GEMINI_ACCOUNT_GATE": "approved", "BEAN_GEMINI_ACCOUNT_DECISION_ID": "test-user-assertion",
    }.items():
        monkeypatch.setenv(key, value)


@pytest.mark.parametrize("mode,free_tier", [(None, "1"), ("placeholder", "1"), ("live_opt_in", None)])
def test_no_explicit_live_free_tier_opt_in_does_not_read_key(monkeypatch, mode, free_tier):
    for key, value in (("BEAN_AI_MODE", mode), ("BEAN_GEMINI_FREE_TIER_ONLY", free_tier)):
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    original = os.getenv
    def guarded(key, default=None):
        assert key not in {"GEMINI_API_KEY", "GOOGLE_API_KEY"}
        return original(key, default)
    monkeypatch.setattr(os, "getenv", guarded)
    assert provider_config_from_env().api_key is None


@pytest.mark.parametrize("change,code", [
    ({"model": "gemini-pro-paid"}, "provider_live_model_not_allowed"),
    ({"free_tier_user_asserted": False}, "provider_free_tier_assertion_required"),
    ({"api_key": "PLACEHOLDER"}, "provider_key_format_invalid"),
    ({"account_gate_passed": False}, "provider_account_gate_unmet"),
    ({"max_output_tokens": 8192}, "provider_budget_invalid"),
    ({"max_input_tokens": 64000}, "provider_budget_invalid"),
])
def test_live_gates_reject_before_reservation_or_sdk(monkeypatch, change, code):
    def forbidden(**kwargs):
        pytest.fail("Invalid live opt-in cannot construct the SDK")
    monkeypatch.setattr("google.genai.Client", forbidden)
    ledger = Ledger()
    with pytest.raises(ProviderFailure, match=code):
        asyncio.run(GeminiProvider(live_config(**change), ledger).generate("explanation", "Test", Answer, context=context()))
    assert ledger.attempts == []


@pytest.mark.parametrize("model", ["gemini-2.5-flash-lite", "gemini-3.5-flash-lite"])
@pytest.mark.parametrize("key", ["AIza" + "a" * 35, "AQ." + "a" * 50])
def test_live_transport_has_one_request_bound_endpoint_thinking_and_real_usage(monkeypatch, model, key):
    ledger, clients = Ledger(), []
    def factory(**kwargs):
        assert len(ledger.attempts) == 1 and ledger.attempts[0]["result"] is None
        client = Client(response(usage={"prompt_token_count": 100, "candidates_token_count": 12,
                                       "thoughts_token_count": 2, "total_token_count": 114}), **kwargs)
        clients.append(client)
        return client
    monkeypatch.setattr("google.genai.Client", factory)
    provider = GeminiProvider(live_config(model=model, api_key=key), ledger)
    result = asyncio.run(provider.generate("explanation", "Test", Answer, context=context()))
    client, = clients
    call, = client.calls
    assert client.kwargs["api_key"] == key
    options = client.kwargs["http_options"]
    assert options.base_url == "https://generativelanguage.googleapis.com"
    assert options.retry_options.attempts == 1 and options.api_version == "v1beta"
    assert call["config"].automatic_function_calling.disable is True
    assert call["config"].max_output_tokens == 1024 and call["config"].candidate_count == 1
    thinking = call["config"].thinking_config
    assert thinking.include_thoughts is False
    assert (thinking.thinking_budget == 0) if model.startswith("gemini-2.5") else (thinking.thinking_level == "MINIMAL")
    assert result.execution_mode == "live" and result.simulated_usage is None
    assert result.usage["input_tokens"] == 100 and client.closed
    attempt, = ledger.attempts
    assert attempt["metadata"]["provider"] == "gemini"
    assert attempt["metadata"]["billing_verified"] is False
    assert attempt["result"]["provider_request_id"] == "safe-request-id"
    assert attempt["result"]["external_provider_calls"] == 1
    assert key not in json.dumps(attempt)


@pytest.mark.parametrize("key", ["AQ.short", "AQ." + "a" * 254, "AQ." + "a" * 49 + "\n",
    "AQ." + "a" * 49 + " ", "AQ." + "a" * 49 + "/", "auth_tokens/abcdef", "Bearer " + "a" * 50])
def test_live_key_format_rejects_unbounded_or_header_unsafe_values(key):
    with pytest.raises(ProviderFailure, match="provider_key_format_invalid"):
        live_config(api_key=key).check_ready()


def test_wire_schema_keeps_shape_and_original_local_schema_unchanged():
    from bean_api.contracts import IntakeProposalBody
    original = IntakeProposalBody.model_json_schema()
    before = json.dumps(original, sort_keys=True)
    wire = live_wire_schema(original)
    assert original["properties"]["fields"]["maxItems"] == 50
    assert "maxItems" not in wire["properties"]["fields"]
    assert "maxItems=50" in wire["properties"]["fields"]["description"]
    coordinates = wire["$defs"]["SourceLocator"]["properties"]["bbox"]["anyOf"][0]
    assert "maximum" not in coordinates["items"]
    assert "maximum=12000000" in coordinates["items"]["description"]
    assert wire["$defs"]["SourceLocator"]["properties"]["page"]["const"] == 1
    assert wire["$defs"]["IntakeField"]["properties"]["candidate_exact"]["anyOf"][0]["pattern"]
    assert wire["required"] == original["required"]
    assert json.dumps(original, sort_keys=True) == before


class BoundedOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    values: list[Annotated[int, Field(ge=0, le=10)]] = Field(min_length=1, max_length=2)


@pytest.mark.parametrize("values", [[], [1, 2, 3], [-1], [11]])
def test_simplified_wire_never_relaxes_server_array_or_numeric_validation(monkeypatch, values):
    client, ledger = Client(response(text=json.dumps({"values": values}))), Ledger()
    monkeypatch.setattr("google.genai.Client", lambda **kwargs: client)
    with pytest.raises(ProviderFailure, match="provider_malformed_output"):
        asyncio.run(GeminiProvider(live_config(), ledger).generate("explanation", "Test", BoundedOutput, context=context()))
    assert len(client.calls) == len(ledger.attempts) == 1
    wire = client.calls[0]["config"].response_json_schema
    assert "maxItems" not in wire["properties"]["values"]
    assert "maximum" not in wire["properties"]["values"]["items"]
    assert ledger.attempts[0]["result"]["status"] == "failed"


def test_live_timeout_is_one_unknown_charged_attempt_without_retry(monkeypatch):
    client, ledger = Client(failure=TimeoutError("do not expose provider details")), Ledger()
    monkeypatch.setattr("google.genai.Client", lambda **kwargs: client)
    with pytest.raises(ProviderFailure, match="provider_timeout_unknown_outcome"):
        asyncio.run(GeminiProvider(live_config(), ledger).generate("explanation", "Test", Answer, context=context()))
    assert len(client.calls) == len(ledger.attempts) == 1
    assert ledger.attempts[0]["result"]["status"] == "unknown_outcome"
    assert ledger.attempts[0]["result"]["external_provider_calls"] == 1


def test_different_returned_live_model_is_rejected_without_fallback(monkeypatch):
    observed = response(usage={"prompt_token_count": 100, "candidates_token_count": 12, "total_token_count": 112})
    observed.model_version = "gemini-some-other-model"
    client, ledger = Client(observed), Ledger()
    monkeypatch.setattr("google.genai.Client", lambda **kwargs: client)
    with pytest.raises(ProviderFailure, match="provider_model_version_mismatch"):
        asyncio.run(GeminiProvider(live_config(), ledger).generate("explanation", "Test", Answer, context=context()))
    assert len(client.calls) == len(ledger.attempts) == 1
    assert ledger.attempts[0]["result"]["usage"]["total_tokens"] == 112


def test_matching_live_model_version_is_recorded(monkeypatch):
    observed = response()
    observed.model_version = LIVE_MODEL + "-001"
    client, ledger = Client(observed), Ledger()
    monkeypatch.setattr("google.genai.Client", lambda **kwargs: client)
    result = asyncio.run(GeminiProvider(live_config(), ledger).generate("explanation", "Test", Answer, context=context()))
    assert result.model_version == LIVE_MODEL + "-001"
    assert ledger.attempts[0]["result"]["observed_model_version"] == result.model_version


def test_live_image_dimension_cap_precedes_any_reservation(monkeypatch):
    def forbidden(**kwargs):
        pytest.fail("Oversize image cannot dispatch")
    monkeypatch.setattr("google.genai.Client", forbidden)
    raw, ledger = png((1601, 10)), Ledger()
    with pytest.raises(ProviderFailure, match="provider_image_dimensions_exceeded"):
        asyncio.run(GeminiProvider(live_config(), ledger).generate("intake", "Test", Answer,
            context=context(source_digests=(hashlib.sha256(raw).hexdigest(),)), image_bytes=raw, mime_type="image/png"))
    assert ledger.attempts == []


def test_live_api_source_consent_idempotency_accounting_and_separate_scientific_authority(tmp_path, monkeypatch):
    enable_env(monkeypatch)
    sdk = Client()
    monkeypatch.setattr("google.genai.Client", lambda **kwargs: sdk)
    settings = Settings(database_path=str(tmp_path / "store.sqlite"), blob_dir=str(tmp_path / "sources"),
        artifact_dir=str(tmp_path / "artifacts"), auth_tokens={"alice": "a" * 40}, science_adapter="unavailable")
    with TestClient(create_app(settings)) as client:
        client.headers["Authorization"] = "Bearer " + "a" * 40
        caps = client.get(PREFIX + "/capabilities").json()
        assert caps["gemini"]["dispatch_enabled"] and caps["source_intake"]["execution_mode"] == "live"
        assert caps["ai_mode"] == "live_opt_in" and caps["deepagents"]["dispatch_enabled"] is False
        assert caps["gemini"]["billing_verified"] is False
        workspace = client.post(PREFIX + "/workspaces", json={"name": "Live path controlled SDK"}).json()["id"]
        endpoint = PREFIX + f"/workspaces/{workspace}"
        source = client.post(endpoint + "/source-assets?origin=synthetic&retention=retain", content=png(),
            headers={"Content-Type": "image/png", "Idempotency-Key": "source"}).json()
        sdk.response = response(text=json.dumps({"source_asset_id": source["id"], "source_digest": source["body"]["sha256"],
            "fields": [{"field_path": "rows[0].concentration", "original_value": "0.5", "candidate_exact": "1/2", "unit": "mg/L",
                "source_asset_id": source["id"], "locator": {"page": 1, "label": "Concentration", "excerpt": "0.5 mg/L"},
                "method": "gemini_vision", "grounding": "unreviewed_visual", "ambiguity": None}], "diagnostics": []}),
            usage={"prompt_token_count": 300, "candidates_token_count": 200, "total_token_count": 500})
        body = {"source_id": source["id"], "consent": {"provider": "gemini", "model": LIVE_MODEL,
            "source_asset_ids": [source["id"]], "include_notes": False, "include_existing_values": False, "accepted": True}}
        first = client.post(endpoint + "/intake-proposals", json=body, headers={"Idempotency-Key": "extract"})
        assert first.status_code == 201, first.text
        second = client.post(endpoint + "/intake-proposals", json=body, headers={"Idempotency-Key": "extract"})
        assert second.json() == first.json() and len(sdk.calls) == 1
        assert first.json()["body"]["review_state"] == "unaccepted"
        attempts = client.get(endpoint + "/provider-attempts").json()
        assert len(attempts) == 1 and attempts[0]["metadata"]["execution_mode"] == "live"
        budget = client.get(endpoint + "/provider-budget").json()
        assert budget["caps"] == {"requests": 8, "input_tokens": 64000, "output_tokens": 16000}
        assert budget["remaining"]["requests"] == 7 and budget["dispatch_enabled"]
        with client.app.state.workflow.store.read() as conn:
            assert conn.execute("SELECT count(*) FROM approvals").fetchone()[0] == 0
        assert client.get(endpoint + "/records?kind=dataset").json() == []
