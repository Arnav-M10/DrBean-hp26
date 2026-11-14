"""Atomic B admission + actual A gateway with substituted transport. No live calls."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import socket

import pytest

from bean_api.gemini_chat_gateway import GeminiChatGateway
from bean_api.ledger import LedgerBudgetExceeded, ProviderLedger
from bean_api.providers import ProviderConfig
from bean_api.research import ResearchService
from bean_api.research_ledger import ResearchLedger, ResearchModelContext
from bean_api.research_tools import ApplicationResearchPorts
from bean_api.store import Store
from bean_api.workflow import DomainError, Workflow
from test_gemini_chat_gateway import Wire
from test_gemini_chat_model import response


@pytest.fixture(autouse=True)
def no_provider(monkeypatch):
    def refused(*args, **kwargs):
        raise AssertionError("This test must not contact a model or network")
    monkeypatch.setattr(socket.socket, "connect", refused)
    monkeypatch.setattr(socket.socket, "connect_ex", refused)
    monkeypatch.setattr("google.genai.Client", refused)


@pytest.fixture
def lane(tmp_path):
    flow = Workflow(Store(tmp_path / "explicit-offline-physical-ledger.sqlite3"))
    workspace = flow.create_workspace("alice", "Explicit offline transport test")["id"]
    service = ResearchService(flow, allocation_actor="alice")
    session = service.create("alice", workspace, {"objective": "Explain a supported scope without inventing assumptions"}, "create")
    consent = service.consent("alice", session["id"], {"model": "controlled-model", "expected_context_digest": session["provider_disclosure"]["context_digest"], "accepted": True}, "consent")
    return service, session, consent


def active(lane, *, requests=2):
    service, session, consent = lane
    grant = {"physical_requests": requests, "input_tokens": 16_000, "output_tokens": 1024, "accepted": True}
    first = service.allocate_provider("alice", session["id"], grant, "explicit-offline-grant")
    assert service.allocate_provider("alice", session["id"], grant, "explicit-offline-grant") == first
    queued = service.advance("alice", session["id"], {"expected_revision": session["revision"]}, "advance")
    context = service.acquire("alice", queued["action"]["id"], "worker-ledger-test")
    scope = service.get("alice", session["id"])["provider_disclosure"]
    identity = ResearchModelContext(context, consent["id"], "controlled-model", scope["root_input_digest"], scope["context_digest"])
    base = ProviderLedger(service.store, request_cap=3)
    ledger = ResearchLedger(base, service, context, model="controlled-model", controlled_transport=True)
    return service, context, identity, base, ledger


def test_default_zero_allocation_and_operator_only_grant(lane):
    service, session, _ = lane
    assert session["provider_allocation"] == {"physical_requests": 0, "input_tokens": 0, "output_tokens": 0}
    ordinary = ResearchService(service.workflow)
    with pytest.raises(DomainError) as error:
        ordinary.allocate_provider("alice", session["id"], {"physical_requests": 1, "input_tokens": 1000, "output_tokens": 100, "accepted": True}, "forged")
    assert error.value.code == "research_allocation_operator_required"


def test_shared_ledger_rejects_research_context_omission(lane):
    service, context, identity, base, ledger = active(lane)
    omitted = {key: value for key, value in identity.checked_dict().items() if key in {"actor_id", "workspace_id", "operation_id"}}
    with pytest.raises(LedgerBudgetExceeded):
        base.begin_attempt(omitted, {"reserved_input_tokens": 1000, "reserved_output_tokens": 100})
    assert base.diagnostics()["historical_attempts"] == 0
    with pytest.raises(LedgerBudgetExceeded):
        ledger.begin_attempt(identity.checked_dict(), {"reserved_input_tokens": 1000, "reserved_output_tokens": 100})
    asyncio.run(ApplicationResearchPorts(service, context).admit_model())
    forged = {**identity.checked_dict(), "context_digest": "0" * 64}
    with pytest.raises(LedgerBudgetExceeded):
        ledger.begin_attempt(forged, {"reserved_input_tokens": 1000, "reserved_output_tokens": 100})


def test_atomic_single_physical_charge_and_real_gateway_cleanup(lane):
    service, context, identity, base, ledger = active(lane)
    asyncio.run(ApplicationResearchPorts(service, context).admit_model())
    wire = Wire(response({"text": "controlled response"}))
    def already_reserved():
        assert base.diagnostics()["historical_attempts"] == 1
    wire.before_request = already_reserved
    gateway = GeminiChatGateway(ProviderConfig(model="controlled-model", max_output_tokens=128), ledger, client_factory=wire.factory)
    exchange = asyncio.run(gateway.dispatch(operation="agent", contents=[{"role": "user", "parts": [{"text": "Bounded controlled input"}]}],
        context=identity, validator=lambda result: "validated controlled output", text_budget_bytes=24, output_tokens=128))
    assert exchange.execution_mode == "controlled" and exchange.value == "validated controlled output"
    assert len(wire.calls) == wire.closed == 1
    attempts = base.list_attempts("alice", context.workspace_id)
    assert len(attempts) == 1 and attempts[0]["response_metadata"]["external_provider_calls"] == 0
    assert service.get("alice", context.research_session_id)["usage"]["physical_calls"] == 1
    # A second request for the same logical turn is denied, despite unused grant.
    with pytest.raises(LedgerBudgetExceeded):
        ledger.begin_attempt(identity.checked_dict(), {"reserved_input_tokens": 1000, "reserved_output_tokens": 100})


def test_concurrent_physical_requests_cannot_overspend_one_logical_turn(lane):
    service, context, identity, base, ledger = active(lane)
    asyncio.run(ApplicationResearchPorts(service, context).admit_model())
    def reserve(_):
        try:
            return ledger.begin_attempt(identity.checked_dict(), {"reserved_input_tokens": 1000, "reserved_output_tokens": 100})
        except LedgerBudgetExceeded:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(reserve, range(2)))
    assert sum(result is not None for result in results) == 1
    assert base.diagnostics()["historical_attempts"] == 1


def test_malformed_usage_worker_loss_and_unknown_remain_reserved(lane):
    service, context, identity, base, ledger = active(lane)
    asyncio.run(ApplicationResearchPorts(service, context).admit_model())
    attempt = ledger.begin_attempt(identity.checked_dict(), {"reserved_input_tokens": 1000, "reserved_output_tokens": 100})
    with pytest.raises(ValueError):
        ledger.finish_attempt(attempt, {"usage": {"input_tokens": -1}})
    assert base.list_attempts("alice", context.workspace_id)[0]["state"] == "reserved"
    service.recover(force=True)
    assert base.list_attempts("alice", context.workspace_id)[0]["state"] == "unknown_outcome"
    current = service.get("alice", context.research_session_id)
    with pytest.raises(DomainError) as error:
        service.reconcile("alice", current["id"], {"expected_revision": current["revision"], "acknowledged_unknown_outcome": True}, "recover")
    assert error.value.code == "provider_outcome_unknown"
    assert base.diagnostics()["remaining"]["requests"] == 2
    assert base.diagnostics()["remaining"]["input_tokens"] == base.input_token_cap - 1000
    wrong_fence = ResearchLedger(base, service, replace(context, lease_epoch=99), model="controlled-model", controlled_transport=True)
    with pytest.raises(LedgerBudgetExceeded):
        wrong_fence.begin_attempt(identity.checked_dict(), {"reserved_input_tokens": 1000, "reserved_output_tokens": 100})
