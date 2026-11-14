"""Controlled transport tests; no Gemini network request or live qualification."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ConfigDict

from bean_api.providers import AttemptContext, GeminiProvider, ProviderConfig, ProviderFailure


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    value: str


class Ledger:
    def __init__(self):
        self.attempts = []
    def begin_attempt(self, context, metadata):
        self.attempts.append({"context": context, "metadata": metadata, "result": None})
        return str(len(self.attempts))
    def finish_attempt(self, attempt_id, metadata):
        self.attempts[int(attempt_id) - 1]["result"] = metadata


class Client:
    def __init__(self, response=None, failure=None, **kwargs):
        self.response, self.failure, self.kwargs = response, failure, kwargs
        self.aio = SimpleNamespace(models=SimpleNamespace(generate_content=self.generate), aclose=self.close)
        self.calls = []
        self.closed = False
    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        if self.failure:
            raise self.failure
        return self.response
    async def close(self):
        self.closed = True


def config(**kwargs):
    return ProviderConfig(api_key="test-only-secret", model="explicit-controlled-model", account_gate_passed=True,
                          account_decision_id="test-policy", **kwargs)


def context(**kwargs):
    return AttemptContext("actor", "workspace", "operation", "consent", **kwargs)


def response(text='{"value":"1/2"}', reason="STOP", usage=None):
    return SimpleNamespace(text=text, candidates=[SimpleNamespace(finish_reason=reason)],
                           usage_metadata=usage, response_id="safe-request-id")


def test_missing_configuration_never_reserves_or_calls():
    ledger = Ledger()
    provider = GeminiProvider(ProviderConfig(), ledger)
    with pytest.raises(ProviderFailure, match="provider_not_configured"):
        asyncio.run(provider.generate("explanation", "Test", Answer, context=context()))
    assert ledger.attempts == []
    assert provider.capabilities()["verified_in_environment"] is False


def test_account_gate_is_distinct_from_key_presence():
    provider = GeminiProvider(ProviderConfig(api_key="exists", model="named"), Ledger())
    with pytest.raises(ProviderFailure, match="provider_account_gate_unmet"):
        asyncio.run(provider.generate("explanation", "Test", Answer, context=context()))


@pytest.mark.parametrize("operation", ["intake", "explanation", "design_proposal", "observation_proposal"])
def test_ready_credentials_and_old_account_decision_cannot_enable_live_dispatch(monkeypatch, operation):
    from google import genai
    constructors = []

    def deny_client(**kwargs):
        constructors.append(True)
        raise AssertionError("Offline mode must reject before constructing an SDK client")

    monkeypatch.setattr(genai, "Client", deny_client)
    ledger = Ledger()
    provider = GeminiProvider(config(), ledger)
    # Repeated requests cannot turn a disabled operation into a live retry.
    for _ in range(2):
        with pytest.raises(ProviderFailure, match="provider_dispatch_disabled"):
            asyncio.run(provider.generate(operation, "A previously consented request", Answer, context=context()))
    assert constructors == [] and ledger.attempts == []
    capabilities = provider.capabilities()
    assert capabilities["configured"] is True
    assert capabilities["execution_mode"] == "disabled"
    assert capabilities["dispatch_enabled"] is False
    assert capabilities["unavailable_reason"] == "provider_dispatch_disabled"
    assert capabilities["transport_provenance"] == "not_observed"
    assert capabilities["live_qualification"] == "not_run"


def test_disclosed_assistant_image_uses_one_existing_turn_budget():
    data = b"controlled-transport-image"
    ledger = Ledger()
    client = Client(response())
    provider = GeminiProvider(config(image_token_upper_bound=100), ledger, client_factory=lambda **k: client)
    result = asyncio.run(provider.generate("observation_proposal", "Interpret this disclosed source", Answer,
        context=context(source_digests=(hashlib.sha256(data).hexdigest(),)), image_bytes=data, mime_type="image/png"))
    assert result.value.value == "1/2"
    assert len(client.calls) == len(ledger.attempts) == 1
    assert ledger.attempts[0]["metadata"]["operation"] == "observation_proposal"
    assert ledger.attempts[0]["metadata"]["timeout_seconds"] <= 30


def test_valid_output_is_unaccepted_and_sdk_retries_are_disabled():
    ledger = Ledger()
    created = []
    def factory(**kwargs):
        assert ledger.attempts and ledger.attempts[0]["result"] is None
        client = Client(response(), **kwargs)
        created.append(client)
        return client
    result = asyncio.run(GeminiProvider(config(), ledger, client_factory=factory).generate(
        "explanation", "Return a proposed value", Answer, context=context()))
    assert result.value.value == "1/2"
    assert created[0].kwargs["http_options"].retry_options.attempts == 1
    assert len(created[0].calls) == 1 and created[0].closed
    assert ledger.attempts[0]["result"]["validation_outcome"] == "schema_valid_unaccepted"
    assert "test-only-secret" not in json.dumps(ledger.attempts)
    assert ledger.attempts[0]["result"]["usage"] is None
    assert ledger.attempts[0]["metadata"]["provider"] == "controlled"
    assert ledger.attempts[0]["metadata"]["actual_model_tokens"] == 0
    assert ledger.attempts[0]["result"]["provider_request_id"] is None
    assert ledger.attempts[0]["result"]["simulated_provider_request_id"] == "safe-request-id"
    assert created[0].kwargs["api_key"] == "nonsecret-controlled-placeholder"
    assert result.execution_mode == "controlled"


@pytest.mark.parametrize("text", ['{"value":0.5}', '{"value":"a","value":"b"}', '{"value":"a","valid":true}', 'bad json'])
def test_malformed_or_authority_fields_fail_without_hidden_repair(text):
    ledger = Ledger()
    client = Client(response(text))
    with pytest.raises(ProviderFailure):
        asyncio.run(GeminiProvider(config(), ledger, client_factory=lambda **k: client).generate(
            "explanation", "Test", Answer, context=context()))
    assert len(client.calls) == 1 and len(ledger.attempts) == 1
    assert ledger.attempts[0]["result"]["status"] == "failed"


@pytest.mark.parametrize("reason,code", [("SAFETY", "provider_refused"), ("MAX_TOKENS", "provider_output_truncated")])
def test_refusal_and_truncation_remain_distinct(reason, code):
    ledger = Ledger()
    client = Client(response(reason=reason))
    with pytest.raises(ProviderFailure, match=code):
        asyncio.run(GeminiProvider(config(), ledger, client_factory=lambda **k: client).generate(
            "intake", "Test", Answer, context=context()))
    assert ledger.attempts[0]["result"]["code"] == code


def test_timeout_is_unknown_outcome_not_safe_automatic_retry():
    ledger = Ledger()
    client = Client(failure=TimeoutError("private context and secret must not escape"))
    with pytest.raises(ProviderFailure, match="provider_timeout_unknown_outcome") as error:
        asyncio.run(GeminiProvider(config(), ledger, client_factory=lambda **k: client).generate(
            "explanation", "Test", Answer, context=context()))
    assert error.value.retryable is False
    assert len(client.calls) == 1
    assert ledger.attempts[0]["result"]["status"] == "unknown_outcome"
    assert "secret must not escape" not in json.dumps(ledger.attempts)


def test_image_requires_bound_digest_and_explicit_token_reservation():
    data = b"controlled-image-transport-only"
    ledger = Ledger()
    def forbidden_factory(**kwargs):
        pytest.fail("Invalid image context must be rejected before controlled transport construction")
    provider = GeminiProvider(config(), ledger, client_factory=forbidden_factory)
    with pytest.raises(ProviderFailure, match="source_binding_mismatch"):
        asyncio.run(provider.generate("intake", "Test", Answer, context=context(), image_bytes=data, mime_type="image/png"))
    with pytest.raises(ProviderFailure, match="image_token_bound_required"):
        asyncio.run(provider.generate("intake", "Test", Answer,
            context=context(source_digests=(hashlib.sha256(data).hexdigest(),)), image_bytes=data, mime_type="image/png"))
    assert ledger.attempts == []


def test_usage_overrun_is_retained_and_output_not_accepted():
    ledger = Ledger()
    client = Client(response(usage={"prompt_token_count": 99_999, "candidates_token_count": 20, "thoughts_token_count": 1}))
    with pytest.raises(ProviderFailure, match="provider_usage_exceeded_reservation"):
        asyncio.run(GeminiProvider(config(), ledger, client_factory=lambda **k: client).generate(
            "explanation", "Test", Answer, context=context()))
    assert ledger.attempts[0]["result"]["usage"]["input_tokens"] == 99_999


def test_offline_preflight_runs_from_any_directory_and_accounts_for_both_branches(tmp_path):
    probe = Path(__file__).resolve().parents[1] / "scripts" / "ai" / "probe.py"
    process = subprocess.run([sys.executable, str(probe)], cwd=tmp_path,
        env={"PATH": os.defpath, "LANG": "C.UTF-8"}, capture_output=True, text=True, timeout=15)
    assert process.returncode == 0, process.stdout
    report = json.loads(process.stdout)
    assert report["offline_preflight_passed"] is True
    assert report["external_dispatch_attempts"] == report["actual_model_tokens"] == 0
    assert report["live_qualification"] == "not_run"
    assert report["evidence_level"] == "controlled_graph_with_controlled_tools"
    branches = report["branches"]
    assert [(b["executed"], b["skipped"]) for b in branches] == [
        (["baseline"], ["optional"]), (["baseline", "optional"], [])]
    assert all(b["result"]["runtime"]["tool_inventory"] for b in branches)
    assert all(b["result"]["explanation"]["authorship"] == "controlled_commentary" for b in branches)


def test_known_hosted_factory_is_rejected_before_construction_or_reservation():
    class HostedFactory:
        __module__ = "google.genai.client"

        def __call__(self, **kwargs):
            pytest.fail("A hosted factory must never be constructed in offline mode")

    ledger = Ledger()
    with pytest.raises(ProviderFailure, match="provider_dispatch_disabled"):
        asyncio.run(GeminiProvider(config(), ledger, client_factory=HostedFactory()).generate(
            "explanation", "Test", Answer, context=context()))
    assert ledger.attempts == []


def test_injected_factory_cannot_return_an_inherited_hosted_client():
    class HostedClient(Client):
        __module__ = "google.genai.client"

    class LocalSubclass(HostedClient):
        pass

    ledger, client = Ledger(), LocalSubclass(response())
    with pytest.raises(ProviderFailure, match="provider_dispatch_disabled"):
        asyncio.run(GeminiProvider(config(), ledger, client_factory=lambda **_: client).generate(
            "explanation", "Test", Answer, context=context()))
    assert client.calls == []
    assert ledger.attempts[0]["result"]["code"] == "provider_dispatch_disabled"


def test_simulated_usage_is_distinct_from_observed_provider_billing():
    client = Client(response(usage={"prompt_token_count": 100, "candidates_token_count": 10}))
    result = asyncio.run(GeminiProvider(config(), Ledger(), client_factory=lambda **_: client).generate(
        "explanation", "Test", Answer, context=context()))
    assert result.execution_mode == "controlled"
    assert result.usage is None
    assert result.simulated_usage["input_tokens"] == 100
