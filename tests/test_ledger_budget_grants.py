"""Owner budget grants: explicit, append-only, hash-chained and immutable; history is never erased."""
import json
import sqlite3

import pytest

from bean_api.ledger import GRANT_CEILINGS, LedgerBudgetExceeded, ProviderLedger, _main, record_grant
from bean_api.main import PREFIX
from bean_api.providers import LIVE_MODEL
from bean_api.store import Store
from bean_api.workflow import Workflow
from general_research_support import SOIL_CSV, analysis_body, analyze, output, upload, workspace
from test_general_research_api import attempts, exhaust, live_app


def ledger_with_history(tmp_path, made=5):
    store = Store(tmp_path / "db.sqlite3")
    workflow = Workflow(store)
    w = workflow.create_workspace("alice", "w")["id"]
    ledger = ProviderLedger(store, request_cap=8)
    for number in range(made):
        operation = workflow.begin_operation("alice", w, "x", f"k{number}", {"n": number})
        attempt = ledger.begin_attempt({"actor_id": "alice", "workspace_id": w, "operation_id": operation["id"],
                                        "consent_id": "c"}, {"reserved_input_tokens": 12_000, "reserved_output_tokens": 3_000})
        ledger.finish_attempt(attempt, {"status": "unknown_outcome" if number == 2 else "validated"})
    return store, workflow, w, ledger


def grant(store, decision="owner-2026-11-14-a", **amounts):
    values = {"requests": 2, "input_tokens": 30_000, "output_tokens": 8_000, **amounts}
    return record_grant(store, decision_id=decision, granted_by="server owner", reason="Bounded public-data smoke test",
                        **values)


def test_defaults_are_unchanged_and_no_table_is_created_without_a_grant(tmp_path):
    store, _, _, ledger = ledger_with_history(tmp_path)
    diagnostic = ledger.diagnostics()
    assert diagnostic["effective_caps"] == {"requests": 8, "input_tokens": 64_000, "output_tokens": 16_000}
    assert diagnostic["budget_grants"]["count"] == 0
    with store.read() as conn:
        assert conn.execute("SELECT name FROM sqlite_master WHERE name='provider_budget_grants'").fetchone() is None


def test_a_grant_adds_capacity_and_preserves_every_attempt(tmp_path):
    store, workflow, w, ledger = ledger_with_history(tmp_path)
    before = ledger.list_attempts("alice", w)
    assert ledger.diagnostics()["remaining"] == {"requests": 3, "input_tokens": 4_000, "output_tokens": 1_000}
    recorded = grant(store)
    assert recorded["sequence"] == 1 and recorded["previous_grant_sha256"] is None
    assert ledger.diagnostics()["remaining"] == {"requests": 5, "input_tokens": 34_000, "output_tokens": 9_000}
    assert ledger.list_attempts("alice", w) == before            # history untouched, nothing refunded
    second = grant(store, decision="owner-2026-11-14-b", requests=0, input_tokens=1_000, output_tokens=0)
    assert second["previous_grant_sha256"] == recorded["grant_sha256"]
    assert ledger.diagnostics()["budget_grants"]["decision_ids"] == ["owner-2026-11-14-a", "owner-2026-11-14-b"]


def test_grants_are_immutable_and_a_broken_chain_fails_closed(tmp_path):
    store, workflow, w, ledger = ledger_with_history(tmp_path)
    grant(store)
    with sqlite3.connect(store.path) as conn:
        for statement in ("UPDATE provider_budget_grants SET requests=100", "DELETE FROM provider_budget_grants"):
            with pytest.raises(sqlite3.DatabaseError, match="immutable budget grant"):
                conn.execute(statement)
    with sqlite3.connect(store.path) as conn:   # an attacker who drops the trigger and edits a row
        conn.execute("DROP TRIGGER provider_budget_grants_no_update")
        conn.execute("UPDATE provider_budget_grants SET input_tokens=999999")
    diagnostic = ledger.diagnostics()
    assert diagnostic["accounting_state"] == "needs_review" and diagnostic["remaining"]["requests"] == 0
    operation = workflow.begin_operation("alice", w, "x", "after-tamper", {})
    with pytest.raises(LedgerBudgetExceeded, match="grant history"):
        ledger.begin_attempt({"actor_id": "alice", "workspace_id": w, "operation_id": operation["id"],
                              "consent_id": "c"}, {"reserved_input_tokens": 10, "reserved_output_tokens": 10})
    with pytest.raises(ValueError, match="invalid"):
        grant(store, decision="owner-2026-11-14-c")


@pytest.mark.parametrize("change,message", [
    ({"decision_id": "x"}, "decision id"),
    ({"reason": "short"}, "reason"),
    ({"requests": -1}, "nonnegative"),
    ({"requests": 0, "input_tokens": 0, "output_tokens": 0}, "positive"),
    ({"input_tokens": GRANT_CEILINGS["input_tokens"] + 1}, "ceilings"),
])
def test_grant_validation(tmp_path, change, message):
    store, *_ = ledger_with_history(tmp_path, made=0)
    values = {"decision_id": "owner-decision-1", "granted_by": "owner", "reason": "A sufficiently long reason",
              "requests": 1, "input_tokens": 1, "output_tokens": 1, **change}
    with pytest.raises(ValueError, match=message):
        record_grant(store, **values)


def test_a_decision_id_grants_once(tmp_path):
    store, *_ = ledger_with_history(tmp_path, made=0)
    grant(store)
    with pytest.raises(ValueError, match="already"):
        grant(store)


def test_owner_cli_requires_explicit_confirmation(tmp_path, capsys):
    store, *_ = ledger_with_history(tmp_path)
    with pytest.raises(SystemExit):
        _main(["grant", "--database", store.path, "--decision-id", "owner-cli-1", "--granted-by", "owner",
               "--reason", "Testing the command line", "--requests", "1"])
    assert _main(["grant", "--database", store.path, "--decision-id", "owner-cli-1", "--granted-by", "owner",
                  "--reason", "Testing the command line", "--requests", "1", "--confirm-owner-decision"]) == 0
    printed = capsys.readouterr().out
    assert '"decision_id": "owner-cli-1"' in printed and '"requests": 4' in printed
    assert _main(["status", "--database", store.path]) == 0


def test_a_grant_admits_a_live_analysis_that_the_exhausted_ledger_refused(tmp_path, monkeypatch):
    app, clients, client = live_app(tmp_path, monkeypatch, output())
    w = workspace(client)
    exhaust(app, w)
    soil = upload(client, w, SOIL_CSV, "text/csv")
    assert analyze(client, w, analysis_body([soil], model=LIVE_MODEL), expect=409)["code"] == "provider_budget_exhausted"
    record_grant(app.state.workflow.store, decision_id="owner-general-smoke", granted_by="owner",
                 reason="Allow one bounded general analysis", requests=0, input_tokens=20_000, output_tokens=0)
    budget = client.get(PREFIX + f"/workspaces/{w}/provider-budget").json()
    assert budget["effective_caps"]["input_tokens"] == 84_000 and budget["remaining"]["input_tokens"] == 24_568
    result = analyze(client, w, analysis_body([soil], model=LIVE_MODEL, operation="op-after-grant"))
    assert result["status"] == "completed" and len(clients) == 1 and len(attempts(app)) == 6
    assert json.loads(attempts(app)[-1]["metadata"])["operation"] == "general_analysis"
