from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from bean_api.ledger import LedgerBudgetExceeded, ProviderLedger
from bean_api.store import Store
from bean_api.workflow import Workflow


def test_provider_reservations_are_atomic_and_unknown_outcome_is_not_refunded(tmp_path):
    store = Store(tmp_path / "db.sqlite3")
    workflow = Workflow(store)
    workspace = workflow.create_workspace("alice", "Budget test")
    operation = workflow.begin_operation("alice", workspace["id"], "intake", "one", {})
    ledger = ProviderLedger(store, request_cap=1)
    context = {"actor_id": "alice", "workspace_id": workspace["id"], "operation_id": operation["id"], "consent_id": "consent"}
    barrier = Barrier(2)
    def reserve(_):
        barrier.wait()
        try:
            return ledger.begin_attempt(context, {"reserved_input_tokens": 100, "reserved_output_tokens": 20})
        except LedgerBudgetExceeded:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        attempts = list(pool.map(reserve, range(2)))
    assert sum(item is not None for item in attempts) == 1
    attempt_id = next(item for item in attempts if item is not None)
    ledger.finish_attempt(attempt_id, {"status": "unknown_outcome", "usage": None})
    with pytest.raises(LedgerBudgetExceeded):
        ledger.begin_attempt(context, {"reserved_input_tokens": 100, "reserved_output_tokens": 20})
    assert ledger.list_attempts("alice", workspace["id"])[0]["state"] == "unknown_outcome"


def test_actual_overrun_exhausts_shared_budget(tmp_path):
    store = Store(tmp_path / "db.sqlite3")
    workflow = Workflow(store)
    workspace = workflow.create_workspace("alice", "Budget test")
    operation = workflow.begin_operation("alice", workspace["id"], "intake", "one", {})
    ledger = ProviderLedger(store, output_token_cap=100)
    context = {"actor_id": "alice", "workspace_id": workspace["id"], "operation_id": operation["id"], "consent_id": "consent"}
    attempt = ledger.begin_attempt(context, {"reserved_input_tokens": 100, "reserved_output_tokens": 20})
    ledger.finish_attempt(attempt, {"status": "failed", "usage": {"output_tokens": 40, "thought_tokens": 70}})
    with pytest.raises(LedgerBudgetExceeded):
        ledger.begin_attempt(context, {"reserved_input_tokens": 1, "reserved_output_tokens": 1})
