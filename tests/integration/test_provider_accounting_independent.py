"""C (independent): main's provider boundary and shared ledger under unknown outcomes, exhaustion and new scopes.

Predicates CRASH-08 (unknown outcome stays charged, no automatic reissue), METER-02 (refusal before dispatch when
the ledger cannot admit) and METER-03 (new actors, workspaces and a restarted process get no extra capacity).
The provider is the application's GeminiProvider with a substituted in-process client (controlled transport);
the ledger is the application's ProviderLedger on an isolated temporary store. Nothing contacts a network.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from pydantic import BaseModel, ConfigDict

from bean_api.ledger import LedgerBudgetExceeded, ProviderLedger
from bean_api.providers import AttemptContext, GeminiProvider, ProviderConfig, ProviderFailure
from bean_api.store import Store
from bean_api.workflow import Workflow


class Answer(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    value: str


class Transport:
    """SDK-shaped client factory that counts constructions and calls; optionally never answers in time."""

    def __init__(self, delay: float = 0.0):
        self.delay, self.constructed, self.calls = delay, 0, 0

    def __call__(self, **_):
        self.constructed += 1
        transport = self

        async def generate(**__):
            transport.calls += 1
            if transport.delay:
                await asyncio.sleep(transport.delay)
            return SimpleNamespace(text='{"value":"ok"}', candidates=[SimpleNamespace(finish_reason="STOP")],
                                   usage_metadata=None, response_id="controlled")

        async def close():
            return None

        return SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate), aclose=close))


def config(**overrides) -> ProviderConfig:
    return ProviderConfig(**{"api_key": "DRBEAN-DUMMY-NOT-A-KEY", "model": "controlled-test-model",
                             "account_gate_passed": True, "account_decision_id": "c-controlled-test",
                             "request_timeout_seconds": 30, **overrides})


def scope(workflow: Workflow, actor: str, name: str) -> AttemptContext:
    workspace = workflow.create_workspace(actor, name)["id"]
    operation = workflow.begin_operation(actor, workspace, "c-probe", f"{name}-op", {"name": name})
    return AttemptContext(actor, workspace, operation["id"], "c-consent")


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "ledger.sqlite3")


def test_unknown_outcome_stays_charged_and_is_never_reissued(store):
    """CRASH-08: a request that outlives its timeout is recorded as unknown_outcome, keeps its reservation, and
    the provider does not try again."""
    workflow, ledger = Workflow(store), ProviderLedger(store, request_cap=4)
    transport = Transport(delay=5)
    provider = GeminiProvider(config(request_timeout_seconds=1), ledger, client_factory=transport)
    before = ledger.diagnostics()["remaining"]
    with pytest.raises(ProviderFailure) as failure:
        asyncio.run(provider.generate("explanation", "Explain the retained evidence.", Answer,
                                      context=scope(workflow, "alice", "timeout")))
    assert failure.value.code == "provider_timeout_unknown_outcome" and failure.value.retryable is False
    after = ledger.diagnostics()
    assert transport.calls == 1 and transport.constructed == 1
    assert after["unknown_outcome_reservations"] == 1 and after["historical_attempts"] == 1
    assert after["remaining"]["requests"] == before["requests"] - 1
    assert after["remaining"]["input_tokens"] < before["input_tokens"]      # the reservation is not refunded


def test_an_exhausted_ledger_refuses_before_any_client_exists(store):
    """METER-02: once capacity is used, the next request is refused before a client is constructed or called."""
    workflow, ledger = Workflow(store), ProviderLedger(store, request_cap=1)
    transport = Transport()
    provider = GeminiProvider(config(), ledger, client_factory=transport)
    asyncio.run(provider.generate("explanation", "First request.", Answer, context=scope(workflow, "alice", "first")))
    assert (transport.constructed, transport.calls) == (1, 1)
    with pytest.raises(LedgerBudgetExceeded):
        asyncio.run(provider.generate("explanation", "Second request.", Answer,
                                      context=scope(workflow, "alice", "second")))
    assert (transport.constructed, transport.calls) == (1, 1)
    assert ledger.diagnostics()["historical_attempts"] == 1


def test_new_actors_workspaces_and_a_restarted_process_get_no_extra_capacity(store, tmp_path):
    """METER-03: capacity is global; another actor, another workspace or a fresh ledger instance over the same
    store (a restart) sees the same remaining capacity and cannot exceed the cap."""
    workflow, ledger = Workflow(store), ProviderLedger(store, request_cap=2)
    provider = GeminiProvider(config(), ledger, client_factory=Transport())
    asyncio.run(provider.generate("explanation", "Alice's request.", Answer, context=scope(workflow, "alice", "a")))
    remaining = ledger.diagnostics()["remaining"]
    restarted = ProviderLedger(Store(tmp_path / "ledger.sqlite3"), request_cap=2)
    assert restarted.diagnostics()["remaining"] == remaining
    other = GeminiProvider(config(), restarted, client_factory=Transport())
    asyncio.run(other.generate("explanation", "Bob's request.", Answer, context=scope(Workflow(store), "bob", "b")))
    with pytest.raises(LedgerBudgetExceeded):
        asyncio.run(other.generate("explanation", "Carol's request.", Answer,
                                   context=scope(Workflow(store), "carol", "c")))
    assert ledger.diagnostics()["historical_attempts"] == 2 and ledger.diagnostics()["remaining"]["requests"] == 0
