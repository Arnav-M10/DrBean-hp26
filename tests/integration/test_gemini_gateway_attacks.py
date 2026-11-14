"""Metered Gemini gateway attacks (categories 5, 6 and 10), CONTROLLED: the transport is authored by this file.

Each test drives the application's metered gateway in controlled mode, using a local transport object and a
recording attempt ledger. The tests check the outcome the gateway actually records:
- exactly one reservation precedes exactly one transport call;
- no hidden retry happens;
- a failure ends in one recorded, accounted outcome;
- an uncertain outcome is never reported as a clean, refundable failure;
- nothing is dispatched when the mode, context or binding is wrong.

No network, provider or credential is involved. The session egress guard would refuse and log any real client.
These tests are NOT Gemini evidence: they say nothing about live behaviour. If the candidate has no metered gateway,
each test is an explicit NOT_AVAILABLE xfail.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time
from types import SimpleNamespace

import pytest

pytestmark = [pytest.mark.controlled_app]
MODEL = "gemini-controlled-test-model"


def _gateway_module():
    try:
        from bean_api import providers
    except ImportError:
        pytest.xfail("NOT_AVAILABLE: bean_api.providers is not importable")
    if not hasattr(providers, "MeteredGeminiGateway") or not hasattr(providers, "SessionCallContext"):
        pytest.xfail("NOT_AVAILABLE: this candidate has no metered Gemini gateway (Owner 3's adapter is not merged)")
    return providers


class RecordingLedger:
    """Minimal attempt ledger: records every reservation and outcome in order."""

    def __init__(self):
        self.events: list[tuple] = []

    def begin_attempt(self, context, metadata):
        attempt = f"att_{len(self.events) + 1}"
        self.events.append(("begin", attempt, metadata.get("operation"), metadata.get("execution_mode"),
                            metadata.get("reserved_input_tokens"), metadata.get("reserved_output_tokens")))
        return attempt

    def finish_attempt(self, attempt_id, metadata):
        self.events.append(("finish", attempt_id, metadata.get("status"), metadata.get("code")))

    def kinds(self):
        return [event[0] for event in self.events]


class Transport:
    """Local stand-in for the SDK's async models API; counts calls and runs one scripted behaviour."""

    def __init__(self, behaviour):
        self.behaviour, self.calls, self.closed = behaviour, 0, False
        self.aio = SimpleNamespace(models=SimpleNamespace(generate_content=self._generate), aclose=self._aclose)

    async def _generate(self, *, model, contents, config):
        self.calls += 1
        return await self.behaviour(model, contents, config)

    async def _aclose(self):
        self.closed = True

    def close(self):
        pass


class Factory:
    def __init__(self, transport):
        self.transport, self.constructed = transport, 0

    def __call__(self, **kwargs):
        self.constructed += 1
        return self.transport


def response(text='{"answer": "ok"}', *, reason="STOP", usage=(100, 20, 120), version=MODEL):
    metadata = None if usage is None else SimpleNamespace(prompt_token_count=usage[0], candidates_token_count=usage[1],
                                                          total_token_count=usage[2], thoughts_token_count=None)
    return SimpleNamespace(text=text, usage_metadata=metadata, candidates=[SimpleNamespace(finish_reason=reason)],
                           model_version=version, response_id="controlled-response-1")


def returns(value):
    async def behaviour(model, contents, config):
        return value
    return behaviour


def raises(exc):
    async def behaviour(model, contents, config):
        raise exc
    return behaviour


class HttpError(Exception):
    def __init__(self, code):
        super().__init__(f"status {code}")
        self.code = code


def setup(behaviour, *, mode="controlled", timeout=5, **config):
    providers = _gateway_module()
    from pydantic import BaseModel

    class Answer(BaseModel):
        answer: str

    transport = Transport(behaviour)
    factory = Factory(transport)
    ledger = RecordingLedger()
    gateway = providers.MeteredGeminiGateway(
        providers.ProviderConfig(mode=mode, model=MODEL, request_timeout_seconds=timeout, **config), ledger,
        client_factory=factory)
    context = providers.SessionCallContext(actor_id="eval-reviewer", workspace_id="ws_eval", operation_id="op_eval",
                                           consent_id="consent_eval", research_session_id="rs_eval",
                                           action_id="act_eval", model=MODEL)
    return providers, gateway, context, ledger, transport, factory, Answer


def run(coro):
    return asyncio.run(coro)


def test_success_is_one_reservation_one_call_one_validated_outcome():
    providers, gateway, context, ledger, transport, factory, Answer = setup(returns(response()))
    result = run(gateway.generate("explanation", "Explain.", Answer, context=context))
    assert result.value.answer == "ok"
    assert ledger.kinds() == ["begin", "finish"] and ledger.events[1][2] == "validated"
    assert transport.calls == 1 and transport.closed
    assert result.execution_mode == "controlled"


@pytest.mark.parametrize("name,behaviour,code,status", [
    ("invalid JSON", returns(response(text="{not json")), "provider_malformed_output", "failed"),
    ("schema-valid but wrong shape", returns(response(text='{"other": 1}')), "provider_malformed_output", "failed"),
    ("refusal", returns(response(reason="SAFETY")), "provider_refused", "failed"),
    ("truncated output", returns(response(reason="MAX_TOKENS")), "provider_output_truncated", "failed"),
    ("rate limited (429)", raises(HttpError(429)), "provider_rate_limited", "unknown_outcome"),
    ("unavailable model (404)", raises(HttpError(404)), "provider_model_unavailable", "unknown_outcome"),
    ("server error (503)", raises(HttpError(503)), "provider_unavailable_unknown_outcome", "unknown_outcome"),
    ("interrupted connection", raises(ConnectionResetError()), "provider_request_failed_unknown_outcome",
     "unknown_outcome"),
    ("usage above the reservation", returns(response(usage=(10 ** 6, 20, 10 ** 6 + 20))),
     "provider_usage_exceeded_reservation", "failed"),
    ("negative usage", returns(response(usage=(-5, 20, 15))), "provider_usage_invalid", "unknown_outcome"),
    ("unexpected model version", returns(response(version="gemini-some-other-model")),
     "provider_model_version_mismatch", "failed"),
])
def test_each_failure_is_one_accounted_outcome_without_retry(name, behaviour, code, status):
    providers, gateway, context, ledger, transport, factory, Answer = setup(behaviour)
    with pytest.raises(providers.ProviderFailure) as raised:
        run(gateway.generate("explanation", "Explain.", Answer, context=context))
    assert raised.value.code == code, name
    assert ledger.kinds() == ["begin", "finish"], name
    assert ledger.events[1][2] == status, (name, ledger.events[1])
    assert transport.calls == 1, f"{name}: hidden retry or extra call"
    assert transport.closed, f"{name}: transport left open"


def test_timeout_is_bounded_and_recorded_as_unknown_outcome():
    async def slow(model, contents, config):
        await asyncio.sleep(30)
    providers, gateway, context, ledger, transport, factory, Answer = setup(slow, timeout=1)
    started = time.monotonic()
    with pytest.raises(providers.ProviderFailure) as raised:
        run(gateway.generate("explanation", "Explain.", Answer, context=context))
    assert time.monotonic() - started < 5
    assert raised.value.code == "provider_timeout_unknown_outcome"
    assert ledger.events[-1][2] == "unknown_outcome" and transport.calls == 1


def test_cancellation_mid_call_is_recorded_and_never_refunded():
    async def scenario(gateway, context, Answer):
        entered = asyncio.Event()

        async def hang(model, contents, config):
            entered.set()
            await asyncio.sleep(30)
        gateway._client_factory.transport.behaviour = hang
        task = asyncio.create_task(gateway.generate("explanation", "Explain.", Answer, context=context))
        await asyncio.wait_for(entered.wait(), 5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    providers, gateway, context, ledger, transport, factory, Answer = setup(returns(response()))
    run(scenario(gateway, context, Answer))
    assert ledger.kinds() == ["begin", "finish"]
    assert ledger.events[1][2:] == ("unknown_outcome", "provider_cancelled_unknown_outcome")
    assert transport.calls == 1


def test_missing_usage_keeps_the_value_but_records_unknown_usage():
    providers, gateway, context, ledger, transport, factory, Answer = setup(returns(response(usage=None)))
    result = run(gateway.generate("explanation", "Explain.", Answer, context=context))
    assert result.value.answer == "ok"
    assert ledger.events[1][2:] == ("unknown_outcome", "provider_usage_unknown")
    assert result.usage is None and result.simulated_usage is None


@pytest.mark.parametrize("name,mutate,code", [
    ("disabled mode", {"mode": "disabled"}, "provider_dispatch_disabled"),
    ("live mode with a dummy key but no atomic session accounting",
     {"mode": "live", "api_key": "DRBEAN-DUMMY-KEY-0001", "account_gate_passed": True,
      "account_decision_id": "DRBEAN-DUMMY-DECISION-0001"}, "provider_session_accounting_unavailable"),
])
def test_no_reservation_and_no_transport_when_dispatch_is_not_permitted(name, mutate, code):
    mode = mutate.pop("mode")
    providers, gateway, context, ledger, transport, factory, Answer = setup(returns(response()), mode=mode, **mutate)
    with pytest.raises(providers.ProviderFailure) as raised:
        run(gateway.generate("explanation", "Explain.", Answer, context=context))
    assert raised.value.code == code, name
    assert ledger.events == [] and factory.constructed == 0 and transport.calls == 0, name


def test_context_model_mismatch_and_unbound_pdf_bytes_are_refused_before_any_reservation():
    providers, gateway, context, ledger, transport, factory, Answer = setup(returns(response()))
    from dataclasses import replace
    with pytest.raises(providers.ProviderFailure) as raised:
        run(gateway.generate("explanation", "Explain.", Answer, context=replace(context, model="gemini-other")))
    assert raised.value.code == "provider_model_mismatch"
    pdf = b"%PDF-1.4 controlled bytes"
    bound = replace(context, source_digests=(hashlib.sha256(pdf).hexdigest(),))
    with pytest.raises(providers.ProviderFailure) as raised:
        run(gateway.generate("explanation", "Explain.", Answer, context=bound, image_bytes=pdf,
                             mime_type="application/pdf"))
    assert raised.value.code == "provider_page_disclosure_required"
    with pytest.raises(providers.ProviderFailure) as raised:
        run(gateway.generate("explanation", "Explain.", Answer, context=context, image_bytes=pdf,
                             mime_type="application/pdf"))
    assert raised.value.code == "provider_source_binding_mismatch"
    assert ledger.events == [] and factory.constructed == 0 and transport.calls == 0


def test_hosted_sdk_transport_is_refused_in_controlled_mode_without_constructing_it():
    providers = _gateway_module()
    try:
        from google.genai import Client
    except ImportError:
        pytest.xfail("NOT_AVAILABLE: google-genai is not installed")
    ledger = RecordingLedger()
    gateway = providers.MeteredGeminiGateway(providers.ProviderConfig(mode="controlled", model=MODEL), ledger,
                                             client_factory=Client)
    context = providers.SessionCallContext(actor_id="eval-reviewer", workspace_id="ws_eval", operation_id="op_eval",
                                           consent_id="consent_eval", research_session_id="rs_eval",
                                           action_id="act_eval", model=MODEL)
    from pydantic import BaseModel

    class Answer(BaseModel):
        answer: str
    with pytest.raises(providers.ProviderFailure) as raised:
        run(gateway.generate("explanation", "Explain.", Answer, context=context))
    assert raised.value.code == "provider_controlled_transport_required"
    assert ledger.events == []


def test_agent_chat_model_has_no_hidden_retry_and_forbids_invocation_overrides():
    try:
        from bean_api.gemini_chat_model import GeminiChatModel
    except ImportError:
        pytest.xfail("NOT_AVAILABLE: this candidate has no metered agent chat model")
    from langchain_core.messages import HumanMessage
    providers, gateway, context, ledger, transport, factory, Answer = setup(raises(HttpError(429)))
    chat = GeminiChatModel(gateway=gateway, context=context)
    with pytest.raises(providers.ProviderFailure) as raised:
        run(chat.ainvoke([HumanMessage(content="Choose the next permitted action.")]))
    assert raised.value.code == "provider_rate_limited"
    assert transport.calls == 1 and ledger.kinds() == ["begin", "finish"]
    with pytest.raises(providers.ProviderFailure) as raised:
        run(chat.ainvoke([HumanMessage(content="x")], stop=["y"]))
    assert raised.value.code == "provider_invocation_override_forbidden"
    assert transport.calls == 1, "an override attempt must not reach the transport"
    with pytest.raises(providers.ProviderFailure):
        chat.invoke([HumanMessage(content="sync calls are refused")])
    assert transport.calls == 1
    assert json.dumps(ledger.events)  # the record is plain data
