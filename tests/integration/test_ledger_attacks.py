"""Accounting attacks on the backend provider ledger (master brief 2.14), isolated synthetic stores only.

The evaluator's JSONL ledger and the backend's SQLite ``ProviderLedger`` are different implementations;
these tests attack the backend one directly. Nothing is dispatched, no real ledger is touched, and no
spending allowance changes: every store is a fresh temporary SQLite file.

Safety properties that hold are ordinary regressions. Known gaps are strict xfails naming their finding.
Live dispatch is disabled today, so under-counting has no spend; it would before any live activation.
"""
from __future__ import annotations

import json
import math
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

pytestmark = [pytest.mark.controlled_app]

RESERVED = {"reserved_input_tokens": 100, "reserved_output_tokens": 20}


@pytest.fixture
def ledger_env(tmp_path):
    from bean_api.ledger import ProviderLedger
    from bean_api.store import Store
    from bean_api.workflow import Workflow
    store = Store(tmp_path / "attack-ledger.sqlite3")
    workflow = Workflow(store)
    workspace = workflow.create_workspace("eval-reviewer", "Ledger attack (synthetic)")
    operation = workflow.begin_operation("eval-reviewer", workspace["id"], "intake", "ledger-attack", {})
    context = {"actor_id": "eval-reviewer", "workspace_id": workspace["id"], "operation_id": operation["id"],
               "consent_id": "synthetic"}

    def make(**caps):
        return ProviderLedger(store, **caps)
    return make, context, store


def remaining(ledger) -> dict:
    return ledger.diagnostics()["remaining"]


@pytest.mark.parametrize("usage", [
    {"input_tokens": -500, "output_tokens": -500},
    {"input_tokens": True, "output_tokens": True},
    {"input_tokens": None, "output_tokens": None, "thought_tokens": None},
    None,
])
def test_negative_boolean_or_missing_usage_never_releases_the_reservation(ledger_env, usage):
    make, context, _ = ledger_env
    ledger = make(input_token_cap=1000, output_token_cap=1000)
    attempt = ledger.begin_attempt(context, dict(RESERVED))
    try:  # refusing malformed counts at reconciliation is stricter and fine; releasing the reservation is not
        ledger.finish_attempt(attempt, {"status": "completed", "usage": usage})
    except (ValueError, TypeError):
        assert ledger.list_attempts("eval-reviewer", context["workspace_id"])[0]["state"] == "reserved"
    left = remaining(ledger)
    assert left["input_tokens"] <= 1000 - 100 and left["output_tokens"] <= 1000 - 20, left
    assert left["requests"] == 32 - 1


@pytest.mark.parametrize("value", [math.nan, math.inf])
def test_non_finite_usage_is_refused_and_the_attempt_stays_unknown(ledger_env, value):
    make, context, _ = ledger_env
    ledger = make()
    attempt = ledger.begin_attempt(context, dict(RESERVED))
    with pytest.raises(ValueError):
        ledger.finish_attempt(attempt, {"status": "completed", "usage": {"input_tokens": value}})
    assert ledger.diagnostics()["unknown_outcome_reservations"] == 1  # still reserved, never refunded
    assert ledger.list_attempts("eval-reviewer", context["workspace_id"])[0]["state"] == "reserved"


def test_concurrent_reservations_never_exceed_the_request_cap(ledger_env):
    from bean_api.ledger import LedgerBudgetExceeded
    make, context, _ = ledger_env
    ledger = make(request_cap=3)
    barrier = Barrier(8)

    def reserve(_):
        barrier.wait()
        try:
            return ledger.begin_attempt(context, dict(RESERVED))
        except LedgerBudgetExceeded:
            return None
    with ThreadPoolExecutor(max_workers=8) as pool:
        granted = [a for a in pool.map(reserve, range(8)) if a]
    assert len(granted) == 3 and len(set(granted)) == 3
    assert remaining(ledger)["requests"] == 0


def test_reconciling_twice_or_an_unknown_id_never_rewrites_or_releases(ledger_env):
    make, context, _ = ledger_env
    ledger = make(input_token_cap=1000, output_token_cap=1000)
    attempt = ledger.begin_attempt(context, dict(RESERVED))
    ledger.finish_attempt(attempt, {"status": "unknown_outcome", "usage": None})
    before = (remaining(ledger), ledger.list_attempts("eval-reviewer", context["workspace_id"]))
    for metadata in ({"status": "completed", "usage": {"input_tokens": 0, "output_tokens": 0}},  # claims zero work
                     {"status": "unknown_outcome", "usage": None}):                                # identical replay
        try:
            ledger.finish_attempt(attempt, metadata)
        except Exception:  # an explicit refusal is fine; silently changing history is not
            pass
    try:
        ledger.finish_attempt("00000000-0000-0000-0000-000000000000", {"status": "completed", "usage": None})
    except Exception:
        pass
    after = (remaining(ledger), ledger.list_attempts("eval-reviewer", context["workspace_id"]))
    assert after == before


@pytest.mark.parametrize("reservation", [{"reserved_input_tokens": 0, "reserved_output_tokens": 20},
                                         {"reserved_input_tokens": True, "reserved_output_tokens": 20},
                                         {"reserved_input_tokens": 100.0, "reserved_output_tokens": 20},
                                         {"reserved_output_tokens": 20}])
def test_dispatch_requires_a_positive_integer_reservation(ledger_env, reservation):
    from bean_api.ledger import LedgerBudgetExceeded
    make, context, _ = ledger_env
    with pytest.raises(LedgerBudgetExceeded):
        make().begin_attempt(context, reservation)


@pytest.mark.xfail(strict=True, reason="F-LEDGER-TOTALS (P2, Owner 2): total_tokens larger than input+output+thought "
                   "tokens (e.g. tool-use prompt tokens) is ignored, so remaining capacity is overstated")
def test_a_total_larger_than_its_parts_is_charged(ledger_env):
    make, context, _ = ledger_env
    ledger = make(input_token_cap=10_000, output_token_cap=10_000)
    attempt = ledger.begin_attempt(context, dict(RESERVED))
    # Shape produced by providers.sanitize_usage from Gemini usage_metadata.
    ledger.finish_attempt(attempt, {"status": "completed", "usage": {
        "input_tokens": 100, "output_tokens": 20, "thought_tokens": 0, "total_tokens": 5_000}})
    left = remaining(ledger)
    charged = (10_000 - left["input_tokens"]) + (10_000 - left["output_tokens"])
    assert charged >= 5_000, f"charged {charged} tokens for a reported total of 5000"


@pytest.mark.xfail(strict=True, reason="F-LEDGER-MALFORMED (P2, Owner 2): reconciliation stores non-integer usage, "
                   "after which every reservation fails with a TypeError instead of an explicit accounting refusal")
def test_malformed_usage_is_refused_at_reconciliation_or_blocks_explicitly(ledger_env):
    from bean_api.ledger import LedgerBudgetExceeded
    make, context, store = ledger_env
    ledger = make(input_token_cap=10_000, output_token_cap=10_000)
    attempt = ledger.begin_attempt(context, dict(RESERVED))
    try:
        ledger.finish_attempt(attempt, {"status": "completed", "usage": {"input_tokens": "5000"}})
    except (ValueError, TypeError, LedgerBudgetExceeded):
        return  # refused at write time: the ledger never holds malformed accounting
    with store.read() as conn:
        stored = json.loads(conn.execute("SELECT response_metadata FROM provider_attempts").fetchone()[0])
    assert stored["usage"]["input_tokens"] == "5000"  # it was accepted, so the next reservation must refuse cleanly
    with pytest.raises(LedgerBudgetExceeded):
        ledger.begin_attempt(context, dict(RESERVED))


def test_malformed_history_still_fails_closed(ledger_env):
    """Whatever the error type, a malformed historical record must never admit new spending."""
    from bean_api.ledger import LedgerBudgetExceeded
    make, context, store = ledger_env
    ledger = make(input_token_cap=10_000, output_token_cap=10_000)
    attempt = ledger.begin_attempt(context, dict(RESERVED))
    with store.transaction() as conn:  # simulate a corrupted row written by an older or broken version
        conn.execute("UPDATE provider_attempts SET response_metadata=?, state='completed' WHERE id=?",
                     (json.dumps({"usage": {"input_tokens": "a lot"}}), attempt))
    with pytest.raises((LedgerBudgetExceeded, TypeError, ValueError)):
        ledger.begin_attempt(context, dict(RESERVED))
    assert len(ledger.list_attempts("eval-reviewer", context["workspace_id"])) == 1  # history untouched
