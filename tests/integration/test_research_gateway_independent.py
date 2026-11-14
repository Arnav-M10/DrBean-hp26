"""C (independent): A's metered Gemini chat gateway, at component level. Covers CRASH-08 on A's adapter and the
METER-01 and METER-02 parts that do not need integration.

Frozen predicates: evaluation/coordinator/predicates.v1.json. Controlled-callbacks lane; only C-authored ledger and
transport doubles are used.

- Live mode is exercised only on refusal paths that fire before any client exists: no session-accounting marker,
  or a transport override. The real session-accounting marker is never paired with live mode, so no hosted client
  can be built.
- The configured key is a labelled dummy, and the probes check that a controlled transport never receives it.
- No route reaches this gateway on main. Its integration through B's research ledger (one reservation per physical
  request across layers) is probed once B registers it.
- Reports NOT_AVAILABLE (xfail) where the gateway is absent.
"""
from __future__ import annotations

import asyncio
import importlib

import pytest
from google.genai import types

pytestmark = [pytest.mark.controlled_app]

DUMMY_KEY = "DRBEAN-DUMMY-c-research-gateway"
MODEL = "c-controlled-gateway-model"
PLACEHOLDER = "nonsecret-controlled-placeholder"


def gateway_module():
    try:
        module = importlib.import_module("bean_api.gemini_chat_gateway")
    except ImportError:
        module = None
    if module is None or not hasattr(module, "GeminiChatGateway"):
        pytest.xfail("NOT_AVAILABLE: no metered Gemini chat gateway (bean_api.gemini_chat_gateway) in this build")
    return module


class Context:
    """Server-resolved identifiers, as the backend would supply them."""

    def checked_dict(self):
        return {"actor_id": "c-actor", "workspace_id": "c-workspace", "operation_id": "c-operation",
                "consent_id": "c-consent", "research_session_id": "c-session", "action_id": "c-action",
                "model": MODEL}


class Ledger:
    """Records every admission and finalization; can refuse admission like an exhausted budget."""

    def __init__(self, exhausted: bool = False):
        self.begun, self.finished, self.exhausted = [], [], exhausted

    def begin_attempt(self, context, metadata):
        if self.exhausted:
            from bean_api.ledger import LedgerBudgetExceeded
            raise LedgerBudgetExceeded("C probe: the shared budget is exhausted")
        self.begun.append(metadata)
        return f"c-attempt-{len(self.begun)}"

    def finish_attempt(self, attempt_id, outcome):
        self.finished.append((attempt_id, outcome))


class Transport:
    """A controlled client factory. It counts constructions, keys and requests, and is never a hosted SDK object."""

    def __init__(self, behaviour):
        self.behaviour, self.keys, self.requests = behaviour, [], 0

    def __call__(self, *, api_key, vertexai, http_options):
        self.keys.append(api_key)
        transport = self

        class Models:
            async def generate_content(self, *, model, contents, config):
                transport.requests += 1
                return await transport.behaviour()

        class Aio:
            models = Models()

            async def aclose(self):
                return None

        class Client:
            aio = Aio()

        return Client()


async def answer():
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[types.Part(text="controlled")]),
                                    finish_reason=types.FinishReason.STOP)],
        usage_metadata=types.GenerateContentResponseUsageMetadata(prompt_token_count=10, candidates_token_count=5,
                                                                  total_token_count=15),
        model_version=MODEL)


async def connection_lost():
    raise ConnectionError("C probe: the response was lost after the request was sent")


async def cancelled():
    raise asyncio.CancelledError()


def gateway(module, ledger, *, mode="disabled", transport=None):
    from bean_api.providers import ProviderConfig
    return module.GeminiChatGateway(ProviderConfig(api_key=DUMMY_KEY, model=MODEL, mode=mode), ledger,
                                    client_factory=transport)


def dispatch(target):
    return asyncio.run(target.dispatch(operation="agent", contents=[{"role": "user", "parts": [{"text": "C probe"}]}],
                                       context=Context(), validator=lambda response: "validated"))


def test_live_mode_fails_closed_without_session_accounting_and_main_ledger_has_none():
    module = gateway_module()
    from bean_api.ledger import ProviderLedger
    from bean_api.providers import ProviderFailure
    ledger = Ledger()
    target = gateway(module, ledger, mode="live")
    capabilities = target.capabilities()
    assert capabilities["dispatch_enabled"] is False
    assert capabilities["unavailable_reason"] == "provider_session_accounting_unavailable"
    with pytest.raises(ProviderFailure) as failure:
        dispatch(target)
    assert failure.value.code == "provider_session_accounting_unavailable"
    assert ledger.begun == [] and ledger.finished == []
    assert getattr(ProviderLedger, "session_accounting_version", None) is None  # main's ledger cannot enable live


def test_live_mode_refuses_a_transport_override_before_admission():
    module = gateway_module()
    from bean_api.providers import ProviderFailure
    ledger, transport = Ledger(), Transport(answer)
    with pytest.raises(ProviderFailure) as failure:
        dispatch(gateway(module, ledger, mode="live", transport=transport))
    assert failure.value.code == "provider_live_transport_override_forbidden"
    assert ledger.begun == [] and transport.keys == [] and transport.requests == 0


def test_exhausted_ledger_refuses_before_any_client_exists():
    """METER-02 part: refused with zero transport constructions or requests."""
    module = gateway_module()
    from bean_api.providers import ProviderFailure
    transport = Transport(answer)
    with pytest.raises(ProviderFailure) as failure:
        dispatch(gateway(module, Ledger(exhausted=True), transport=transport))
    assert failure.value.code == "provider_budget_exhausted"
    assert transport.keys == [] and transport.requests == 0


def test_one_admission_per_request_and_the_transport_never_sees_the_key():
    """METER-01 part: one reservation before the request, finalized once; the controlled path holds no credential."""
    module = gateway_module()
    ledger, transport = Ledger(), Transport(answer)
    exchange = dispatch(gateway(module, ledger, transport=transport))
    assert exchange.value == "validated" and exchange.attempt_id == "c-attempt-1"
    assert len(ledger.begun) == 1 and transport.requests == 1
    assert [outcome["status"] for _, outcome in ledger.finished] == ["validated"]
    assert ledger.begun[0]["retry_policy"] == "none" and ledger.begun[0]["max_requests"] == 1
    assert transport.keys == [PLACEHOLDER] and DUMMY_KEY not in repr(ledger.begun) + repr(ledger.finished)


@pytest.mark.parametrize("behaviour, code", [(connection_lost, None), (cancelled, "provider_cancelled_unknown_outcome")],
                         ids=["response_lost", "cancelled_in_flight"])
def test_unknown_outcome_keeps_the_charge_and_is_never_retried(behaviour, code):
    """CRASH-08 on A's adapter: the reservation stays, the ambiguity is recorded and nothing is reissued."""
    module = gateway_module()
    from bean_api.providers import ProviderFailure
    ledger, transport = Ledger(), Transport(behaviour)
    expected = asyncio.CancelledError if behaviour is cancelled else ProviderFailure
    with pytest.raises(expected) as failure:
        dispatch(gateway(module, ledger, transport=transport))
    assert len(ledger.begun) == 1 and transport.requests == 1  # one request, no automatic reissue
    assert len(ledger.finished) == 1
    attempt, outcome = ledger.finished[0]
    assert attempt == "c-attempt-1" and outcome["status"] == "unknown_outcome", outcome
    if code:
        assert outcome["code"] == code
    else:
        assert failure.value.attempt_id == "c-attempt-1" and failure.value.retryable is False
