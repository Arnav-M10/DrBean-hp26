"""Offline accounting controls; no provider is constructed or contacted."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from threading import Barrier

import pytest

from bean_api.ledger import LedgerBudgetExceeded, MAX_TOKEN_COUNT, ProviderLedger
from bean_api.store import Store
from bean_api.workflow import Workflow


@pytest.fixture
def accounting(tmp_path):
    store = Store(tmp_path / "isolated.sqlite3")
    flow = Workflow(store)
    workspace = flow.create_workspace("alice", "Offline usage control")
    operation = flow.begin_operation("alice", workspace["id"], "intake", "one", {})
    context = {"actor_id": "alice", "workspace_id": workspace["id"], "operation_id": operation["id"]}
    return store, ProviderLedger(store, input_token_cap=100, output_token_cap=100), context


def reserve(ledger, context):
    return ledger.begin_attempt(context, {"reserved_input_tokens": 10, "reserved_output_tokens": 10})


@pytest.mark.parametrize("usage", [{"input_tokens": -1}, {"output_tokens": True}, {"thought_tokens": 1.2},
    {"input_tokens": "10"}, {"output_tokens": MAX_TOKEN_COUNT + 1},
    {"input_tokens": MAX_TOKEN_COUNT, "output_tokens": 1},
    {"input_tokens": 3, "output_tokens": 4, "total_tokens": 6},
    {"input_tokens": 1, "total_tokens": 0}, [1, 2]])
def test_invalid_outcome_is_rejected_without_releasing_reservation(accounting, usage):
    _, ledger, context = accounting
    attempt = reserve(ledger, context)
    with pytest.raises(ValueError):
        ledger.finish_attempt(attempt, {"status": "completed", "usage": usage})
    record = ledger.list_attempts("alice", context["workspace_id"])[0]
    assert record["state"] == "reserved" and record["response_metadata"] is None
    assert ledger.diagnostics()["remaining"] == {"requests": 31, "input_tokens": 90, "output_tokens": 90}


def test_aliases_never_hide_larger_usage_and_admission_matches_diagnostics(accounting):
    _, ledger, context = accounting
    attempt = reserve(ledger, context)
    ledger.finish_attempt(attempt, {"status": "validated", "usage": {
        "input_tokens": 10, "prompt_token_count": 91, "output_tokens": 1,
        "candidates_token_count": 70, "thought_tokens": 2, "thoughts_token_count": 21}})
    assert ledger.diagnostics()["remaining"]["input_tokens"] == 9
    assert ledger.diagnostics()["remaining"]["output_tokens"] == 9
    with pytest.raises(LedgerBudgetExceeded):
        reserve(ledger, context)


def test_reported_total_without_components_is_conservatively_charged(accounting):
    _, ledger, context = accounting
    attempt = reserve(ledger, context)
    ledger.finish_attempt(attempt, {"status": "unknown_outcome", "usage": {"total_tokens": 95}})
    diagnostic = ledger.diagnostics()
    assert diagnostic["remaining"]["input_tokens"] == diagnostic["remaining"]["output_tokens"] == 5
    assert diagnostic["unknown_outcome_reservations"] == 1
    with pytest.raises(LedgerBudgetExceeded):
        reserve(ledger, context)


def test_exact_reconciliation_retry_is_idempotent_but_conflict_and_unknown_are_rejected(accounting):
    _, ledger, context = accounting
    attempt = reserve(ledger, context)
    outcome = {"status": "unknown_outcome", "usage": None}
    ledger.finish_attempt(attempt, outcome)
    before = deepcopy(ledger.list_attempts("alice", context["workspace_id"]))
    ledger.finish_attempt(attempt, dict(reversed(list(outcome.items()))))
    with pytest.raises(ValueError, match="different immutable outcome"):
        ledger.finish_attempt(attempt, {"status": "completed", "usage": {"input_tokens": 0}})
    with pytest.raises(ValueError, match="Unknown provider attempt"):
        ledger.finish_attempt("missing", outcome)
    assert ledger.list_attempts("alice", context["workspace_id"]) == before


def test_concurrent_different_reconciliations_preserve_one_outcome(accounting):
    _, ledger, context = accounting
    attempt = reserve(ledger, context)
    barrier = Barrier(2)
    def finish(status):
        barrier.wait()
        try:
            ledger.finish_attempt(attempt, {"status": status, "usage": None})
            return status
        except ValueError:
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(finish, ["completed", "unknown_outcome"]))
    winner = next(value for value in outcomes if value is not None)
    assert outcomes.count(None) == 1
    assert ledger.list_attempts("alice", context["workspace_id"])[0]["response_metadata"]["status"] == winner


@pytest.mark.parametrize("invalid", [{"usage": {"input_tokens": "bad"}}, {"usage": {"input_tokens": -5}}, []])
def test_legacy_invalid_accounting_fails_closed_without_modifying_records(accounting, invalid):
    store, ledger, context = accounting
    attempt = reserve(ledger, context)
    raw = json.dumps(invalid)
    with store.transaction() as conn:
        conn.execute("UPDATE provider_attempts SET state='completed',response_metadata=? WHERE id=?", (raw, attempt))
    diagnostic = ledger.diagnostics()
    assert diagnostic["accounting_state"] == "needs_review"
    assert diagnostic["malformed_historical_attempts"] == 1
    assert diagnostic["remaining"] == {"requests": 0, "input_tokens": 0, "output_tokens": 0}
    with pytest.raises(LedgerBudgetExceeded, match="requires review"):
        reserve(ledger, context)
    with store.read() as conn:
        assert conn.execute("SELECT response_metadata FROM provider_attempts WHERE id=?", (attempt,)).fetchone()[0] == raw


@pytest.mark.parametrize("field", ["request_cap", "input_token_cap", "output_token_cap"])
def test_boolean_configuration_is_not_a_token_cap(accounting, field):
    store, _, _ = accounting
    with pytest.raises(ValueError):
        ProviderLedger(store, **{field: True})


def test_reservation_aliases_are_validated_and_conservative(accounting):
    _, ledger, context = accounting
    with pytest.raises(LedgerBudgetExceeded):
        ledger.begin_attempt(context, {"reserved_input_tokens": 10, "input_token_reservation": -1,
                                      "reserved_output_tokens": 10})
    ledger.begin_attempt(context, {"reserved_input_tokens": 10, "input_token_reservation": 95,
                                  "reserved_output_tokens": 10})
    assert ledger.diagnostics()["remaining"]["input_tokens"] == 5
    with pytest.raises(LedgerBudgetExceeded):
        reserve(ledger, context)
