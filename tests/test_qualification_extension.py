"""Offline qualification-only extension admission; no provider configuration."""
import builtins
import copy
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "qualification_operator_grant", Path(__file__).resolve().parents[1] / "evaluation/live/operator_grant.py")
operator_grant = importlib.util.module_from_spec(spec)
spec.loader.exec_module(operator_grant)


def historical_budget():
    return {"ceiling": 12,
            "grants": [{"research_session_id": "first", "physical_requests": 6},
                       {"research_session_id": "deleted-first", "physical_requests": 4},
                       {"research_session_id": "deleted-second", "physical_requests": 4},
                       {"research_session_id": "second", "physical_requests": 4}],
            "released": [{"research_session_id": "deleted-first", "physical_requests": 4},
                         {"research_session_id": "deleted-second", "physical_requests": 4}],
            "physical_requests_used": {"first": 5, "deleted-first": 0, "deleted-second": 0, "second": 3},
            "sprint_physical_requests_total": 8,
            "qualification_extensions": [copy.deepcopy(operator_grant.QUALIFICATION_EXTENSION_POLICY)]}


def test_default_ceiling_stays_twelve_even_with_an_authorization_receipt():
    budget = historical_budget()
    assert operator_grant.check_grant(budget, 2) == {"sprint_granted_total": 12, "ceiling": 12}
    with pytest.raises(SystemExit, match="exceed"):
        operator_grant.check_grant(budget, 6)


def test_explicit_six_request_extension_preserves_all_historical_counts_and_records():
    budget = historical_budget()
    before = copy.deepcopy(budget)
    policy_id = operator_grant.QUALIFICATION_EXTENSION_POLICY["id"]
    assert operator_grant.check_grant(budget, 6, policy_id) == {
        "sprint_granted_total": 16, "ceiling": 16, "qualification_extension": policy_id}
    assert budget == before


@pytest.mark.parametrize("key,value", [("previous_ceiling", 13), ("ceiling", 17), ("max_new_requests", 7),
                                      ("max_runs", True), ("max_runs", 2), ("actor", "another-caller"),
                                      ("authorization", "unrecorded"), ("id", "another-authorization")])
def test_changed_authorization_fields_refuse(key, value):
    budget = historical_budget()
    budget["qualification_extensions"][0][key] = value
    with pytest.raises(SystemExit, match="receipt"):
        operator_grant.check_grant(budget, 6, operator_grant.QUALIFICATION_EXTENSION_POLICY["id"])


@pytest.mark.parametrize("physical", [0, -1, True, 7, 9, "6"])
def test_invalid_or_oversized_extension_grant_refuses(physical):
    with pytest.raises(SystemExit):
        operator_grant.check_grant(historical_budget(), physical, operator_grant.QUALIFICATION_EXTENSION_POLICY["id"])


@pytest.mark.parametrize("released", [False, True])
def test_extension_cannot_be_reused_even_after_a_failed_or_released_run(released):
    budget = historical_budget()
    policy_id = operator_grant.QUALIFICATION_EXTENSION_POLICY["id"]
    grant = {"research_session_id": "extension", "physical_requests": 6, "qualification_extension": policy_id}
    budget["grants"].append(grant)
    if released:
        budget["released"].append({"research_session_id": "extension", "physical_requests": 6})
    with pytest.raises(SystemExit, match="already been used"):
        operator_grant.check_grant(budget, 1, policy_id)


@pytest.mark.parametrize("change", ["no_receipt", "duplicate_receipt", "missing_counts", "reset_used", "release_history", "raise_base"])
def test_missing_or_reset_history_and_malformed_receipts_fail_closed(change):
    budget = historical_budget()
    if change == "no_receipt":
        budget.pop("qualification_extensions")
    elif change == "duplicate_receipt":
        budget["qualification_extensions"] *= 2
    elif change == "missing_counts":
        budget.pop("physical_requests_used")
    elif change == "reset_used":
        budget["sprint_physical_requests_total"] = 0
    elif change == "release_history":
        budget["released"].append({"physical_requests": 2})
    else:
        budget["ceiling"] = 16
    with pytest.raises(SystemExit):
        operator_grant.check_grant(budget, 6, operator_grant.QUALIFICATION_EXTENSION_POLICY["id"])


def test_refusal_happens_before_any_application_import_or_store_creation(tmp_path, monkeypatch):
    budget_path = tmp_path / "budget.json"
    budget_path.write_text(json.dumps(historical_budget()))
    before = budget_path.read_bytes()
    monkeypatch.setattr(operator_grant, "BUDGET", budget_path)
    monkeypatch.delenv("LIVE_QUALIFICATION_EXTENSION", raising=False)
    original_import = builtins.__import__

    def no_application(name, *args, **kwargs):
        if name.startswith("bean_api"):
            raise AssertionError("Refusal must precede importing the application or opening its store")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_application)
    with pytest.raises(SystemExit, match="exceed"):
        operator_grant.main([str(tmp_path / "never-created.sqlite3"), "session", "6", "64000", "3072", "offline-refusal"])
    assert budget_path.read_bytes() == before
    assert not (tmp_path / "never-created.sqlite3").exists()


def test_authorized_extension_tags_one_real_operator_grant_without_mutating_history(tmp_path, monkeypatch, capsys):
    from bean_api.research import ResearchService
    from bean_api.store import Store
    from bean_api.workflow import Workflow

    db = tmp_path / "isolated-qualification.sqlite3"
    workflow = Workflow(Store(db))
    workspace = workflow.create_workspace("fixture-actor", "No-provider allocation regression")["id"]
    service = ResearchService(workflow, live_enabled=True)
    session = service.create("fixture-actor", workspace, {"objective": "Inspect a bounded workflow", "mode": "live"}, "create")
    history = historical_budget()
    budget_path = tmp_path / "budget.json"
    budget_path.write_text(json.dumps(history))
    monkeypatch.setattr(operator_grant, "BUDGET", budget_path)
    policy_id = operator_grant.QUALIFICATION_EXTENSION_POLICY["id"]
    monkeypatch.setenv("LIVE_QUALIFICATION_EXTENSION", policy_id)
    arguments = [str(db), session["id"], "6", "64000", "3072", "offline-regression"]
    assert operator_grant.main(arguments) == 0
    returned = json.loads(capsys.readouterr().out)
    assert returned["qualification_extension"] == policy_id and returned["sprint_granted_total"] == 16
    retained = json.loads(budget_path.read_text())
    assert retained["grants"][:-1] == history["grants"]
    assert {key: value for key, value in retained.items() if key != "grants"} == {
        key: value for key, value in history.items() if key != "grants"}
    assert retained["grants"][-1]["qualification_extension"] == policy_id
    assert retained["grants"][-1]["allocation_record"] == returned["allocation_record"]
    assert service.get("fixture-actor", session["id"])["provider_allocation"] == {
        "physical_requests": 6, "input_tokens": 64000, "output_tokens": 3072}
    with pytest.raises(SystemExit, match="already been used"):
        operator_grant.main(arguments)
    assert json.loads(budget_path.read_text()) == retained
    with workflow.store.read() as conn:
        assert conn.execute("SELECT count(*) FROM provider_attempts").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM research_actions").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM entities WHERE kind='research_provider_allocation'").fetchone()[0] == 1


def test_committed_authorization_receipt_matches_the_explicit_policy():
    # Public receipt only; this test never reads configuration or credentials.
    budget = json.loads((Path(__file__).resolve().parents[1] / "evaluation/results/sprint/live-budget.json").read_text())
    policy = operator_grant.QUALIFICATION_EXTENSION_POLICY
    receipt = budget["qualification_extensions"][0]
    assert {key: receipt[key] for key in policy} == policy
