"""Controlled transport tests; no Gemini network request or live qualification."""
import asyncio
import hashlib
import json
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
    provider = GeminiProvider(config(), ledger)
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
