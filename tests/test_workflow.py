"""Deterministic application-authority controls; no live provider or science claims."""

from concurrent.futures import ThreadPoolExecutor
import sqlite3
from threading import Barrier

import pytest

from bean_api.contracts import DatasetBody, PlanBody, ProblemBody
from bean_api.store import Store
from bean_api.workflow import DomainError, Workflow


@pytest.fixture
def flow(tmp_path):
    workflow = Workflow(Store(tmp_path / "bean.sqlite3"))
    workspace = workflow.create_workspace("alice", "Synthetic test workspace")
    return workflow, workspace["id"]


def dataset_body(parent_id=None, origin="synthetic"):
    return DatasetBody(experiment_id="experiment_synthetic", time_origin="elapsed hours since synthetic dose",
                       rows=[{"id": "r1", "time": "1/1", "concentration": "3/1", "hard_allowance": "1/10", "included": True},
                             {"id": "r2", "time": "2/1", "concentration": "4/1", "hard_allowance": "1/5", "included": False}],
                       parent_id=parent_id, change_reason="Synthetic authority control", origin=origin).model_dump(mode="json")


def create_problem(workflow, workspace, dataset, key="problem"):
    body = ProblemBody(dataset_id=dataset["id"], dataset_digest=dataset["digest"],
                       domain={"A": {"lower": "1/1", "upper": "20/1"},
                               "ke": {"lower": "1/100", "upper": "1/1"},
                               "ka": {"lower": "1/10", "upper": "4/1"}},
                       target={"lower": "1/10", "upper": "1/5"}).model_dump(mode="json")
    return workflow.create_problem("alice", workspace, body, key)


def prepared(flow, optional=False, disclosure=None, tools=None):
    workflow, workspace = flow
    dataset = workflow.create_dataset("alice", workspace, dataset_body(), "dataset")
    problem = create_problem(workflow, workspace, dataset)
    scenarios = [{"id": "baseline", "kind": "baseline", "label": "Reviewed baseline",
                  "problem_id": problem["id"], "problem_digest": problem["digest"]}]
    if optional:
        scenarios.append({**scenarios[0], "id": "optional", "kind": "optional", "label": "Explicitly listed comparison"})
    body = PlanBody(problem_id=problem["id"], problem_digest=problem["digest"], dataset_id=dataset["id"], scenarios=scenarios).model_dump(mode="json")
    if disclosure:
        body["provider_disclosure"] = disclosure
    if tools is not None:
        body["permitted_tools"] = tools
    plan = workflow.create_plan("alice", workspace, body, "plan")
    approval = workflow.approve_plan("alice", plan["id"], problem["id"], plan["digest"], "approval")
    return dataset, problem, plan, approval


def unsupported(problem):
    return {"scientific_outcome": "unsupported", "verification": "unsupported", "expected_binding": "not_supplied",
            "replay": "unsupported", "reason_code": "fixture_no_adapter", "problem_id": problem["id"], "candidates": [], "artifacts": []}


def numerical_pair(problem):
    return {"scientific_outcome": "numerical_candidate", "verification": "not_checked", "expected_binding": "matches",
            "replay": "not_run", "reason_code": "synthetic_fixture_only", "problem_id": problem["id"], "problem_digest": problem["digest"],
            "candidates": [
                {"id": "candidate_a", "parameter_vector": {"A": "10/1", "ke": "1/10", "ka": "2/1"}, "problem_id": problem["id"], "problem_digest": problem["digest"]},
                {"id": "candidate_b", "parameter_vector": {"A": "11/1", "ke": "3/10", "ka": "2/1"}, "problem_id": problem["id"], "problem_digest": problem["digest"]}],
            "artifacts": []}


def completed_pair(flow):
    workflow, _ = flow
    dataset, problem, plan, approval = prepared(flow)
    run = workflow.start_run("alice", plan["id"], approval["id"], "start")
    workflow.mark_running("alice", run["id"], "test-worker")
    workflow.reserve_scenario("alice", run["id"], "baseline")
    workflow.complete_scenario("alice", run["id"], "baseline", numerical_pair(problem))
    workflow.finish_run("alice", run["id"])
    return dataset, problem, plan, approval, run


def design_body(run, problem):
    return {"historical_run_id": run["id"], "scenario_id": "baseline", "problem_id": problem["id"], "problem_digest": problem["digest"],
            "candidate_ids": ["candidate_a", "candidate_b"], "candidate_vectors": [
                {"A": "10/1", "ke": "1/10", "ka": "2/1"}, {"A": "11/1", "ke": "3/10", "ka": "2/1"}],
            "feasible_times": ["6/1", "8/1"], "future_hard_allowance": "1/5"}


def assert_code(code, fn):
    with pytest.raises(DomainError) as caught:
        fn()
    assert caught.value.code == code


def test_workspace_scoped_records_and_opaque_identifiers(flow):
    workflow, workspace = flow
    dataset = workflow.create_dataset("alice", workspace, dataset_body(), "dataset")
    workflow.create_workspace("bob", "Other workspace")
    assert_code("not_found", lambda: workflow.get("bob", dataset["id"]))
    assert_code("not_found", lambda: workflow.list_records("bob", workspace, "dataset"))
    assert_code("not_found", lambda: workflow.create_dataset("bob", workspace, dataset_body(), "attack"))


def test_same_key_returns_exact_record_changed_body_conflicts(flow):
    workflow, workspace = flow
    first = workflow.create_dataset("alice", workspace, dataset_body(), "dataset")
    assert workflow.create_dataset("alice", workspace, dataset_body(), "dataset") == first
    changed = {**dataset_body(), "change_reason": "Changed content"}
    assert_code("idempotency_conflict", lambda: workflow.create_dataset("alice", workspace, changed, "dataset"))


def test_concurrent_fresh_keys_reserve_one_parent(flow):
    workflow, _ = flow
    _, _, plan, approval = prepared(flow)
    barrier = Barrier(2)
    def submit(index):
        barrier.wait()
        return workflow.start_run("alice", plan["id"], approval["id"], f"race-{index}")
    with ThreadPoolExecutor(max_workers=2) as pool:
        runs = list(pool.map(submit, range(2)))
    assert runs[0]["id"] == runs[1]["id"]
    assert len(workflow.queued_jobs()) == 1
    with workflow.store.read() as conn:
        assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1


def test_stale_edit_blocks_new_start_but_not_accepted_run(flow):
    workflow, workspace = flow
    dataset, problem, plan, approval = prepared(flow)
    run = workflow.start_run("alice", plan["id"], approval["id"], "start")
    workflow.create_dataset("alice", workspace, dataset_body(dataset["id"]), "edited")
    child = workflow.reserve_scenario("alice", run["id"], "baseline")
    assert child["created_new"] is True
    assert workflow.start_run("alice", plan["id"], approval["id"], "fresh-key")["id"] == run["id"]
    assert workflow.get("alice", problem["id"])["digest"] == problem["digest"]


def test_stale_edit_before_reservation_is_rejected(flow):
    workflow, workspace = flow
    dataset, _, plan, approval = prepared(flow)
    workflow.create_dataset("alice", workspace, dataset_body(dataset["id"]), "edited")
    assert_code("stale_revision", lambda: workflow.start_run("alice", plan["id"], approval["id"], "start"))
    assert workflow.queued_jobs() == []


def test_missing_or_wrong_actor_approval_never_reserves(flow):
    workflow, _ = flow
    _, _, plan, _ = prepared(flow)
    assert_code("approval_required", lambda: workflow.start_run("alice", plan["id"], "made-up", "start"))
    assert workflow.queued_jobs() == []


def test_baseline_order_scope_and_duplicate_child_race(flow):
    workflow, _ = flow
    _, problem, plan, approval = prepared(flow, optional=True)
    run = workflow.start_run("alice", plan["id"], approval["id"], "start")
    assert_code("baseline_required", lambda: workflow.reserve_scenario("alice", run["id"], "optional"))
    assert_code("baseline_required", lambda: workflow.skip_scenario("alice", run["id"], "optional", "sufficient_evidence"))
    assert_code("scenario_not_approved", lambda: workflow.reserve_scenario("alice", run["id"], "third"))
    barrier = Barrier(2)
    def reserve(_):
        barrier.wait()
        return workflow.reserve_scenario("alice", run["id"], "baseline")
    with ThreadPoolExecutor(max_workers=2) as pool:
        children = list(pool.map(reserve, range(2)))
    assert children[0]["id"] == children[1]["id"]
    assert sum(child["created_new"] for child in children) == 1
    assert workflow.get_run("alice", run["id"])["scientific_reservations"] == 1
    workflow.complete_scenario("alice", run["id"], "baseline", unsupported(problem))
    skipped = workflow.skip_scenario("alice", run["id"], "optional", "capability_unavailable")
    assert skipped["state"] == "skipped"
    assert_code("skip_not_allowed", lambda: workflow.skip_scenario("alice", run["id"], "baseline", "capability_unavailable"))


def test_tool_allowlist_enforced_inside_authority(flow):
    workflow, _ = flow
    _, _, plan, approval = prepared(flow, tools=["read_scoped_evidence"])
    run = workflow.start_run("alice", plan["id"], approval["id"], "start")
    assert_code("tool_not_approved", lambda: workflow.reserve_scenario("alice", run["id"], "baseline"))


def test_cancellation_preserves_late_evidence_until_worker_acknowledges(flow):
    workflow, _ = flow
    _, problem, plan, approval = prepared(flow)
    run = workflow.start_run("alice", plan["id"], approval["id"], "start")
    workflow.mark_running("alice", run["id"], "worker")
    workflow.reserve_scenario("alice", run["id"], "baseline")
    workflow.mark_scenario_running("alice", run["id"], "baseline")
    assert workflow.cancel_run("alice", run["id"], "cancel")["state"] == "cancel_requested"
    assert_code("worker_not_reconciled", lambda: workflow.finish_run("alice", run["id"], "cancelled"))
    evidence = workflow.complete_scenario("alice", run["id"], "baseline", unsupported(problem))
    assert evidence["body"]["arrived_after_cancel"] is True
    assert workflow.get_run("alice", run["id"])["state"] == "cancel_requested"
    assert workflow.finish_run("alice", run["id"], "cancelled")["state"] == "cancelled"
    assert workflow.read_evidence("alice", run["id"], evidence["id"])["id"] == evidence["id"]


def test_completion_race_honors_cancel_and_retains_result(flow):
    workflow, _ = flow
    _, problem, plan, approval = prepared(flow, optional=True)
    run = workflow.start_run("alice", plan["id"], approval["id"], "start")
    workflow.reserve_scenario("alice", run["id"], "baseline")
    evidence = workflow.complete_scenario("alice", run["id"], "baseline", unsupported(problem))
    workflow.cancel_run("alice", run["id"], "cancel-after-evidence")
    finished = workflow.finish_run("alice", run["id"], "completed", {"explanation": "Preserved controlled result"})
    assert finished["state"] == "cancelled"
    assert workflow.get("alice", finished["result_id"], "run_summary")["body"]["explanation"] == "Preserved controlled result"
    assert workflow.read_evidence("alice", run["id"], evidence["id"])["id"] == evidence["id"]


def test_restart_never_redispatches_running_child(flow):
    workflow, _ = flow
    _, _, plan, approval = prepared(flow)
    run = workflow.start_run("alice", plan["id"], approval["id"], "start")
    workflow.mark_running("alice", run["id"], "worker")
    workflow.reserve_scenario("alice", run["id"], "baseline")
    recovered = Workflow(Store(workflow.store.path))
    counts = recovered.recover_interrupted()
    assert counts["jobs"] == counts["scenarios"] == 1
    assert recovered.get_run("alice", run["id"])["state"] == "interrupted"
    assert_code("job_not_active", lambda: recovered.reserve_scenario("alice", run["id"], "baseline"))
    assert recovered.start_run("alice", plan["id"], approval["id"], "retry")["id"] == run["id"]
    assert recovered.queued_jobs() == []


def test_provider_unknown_outcome_survives_restart(flow):
    from bean_api.ledger import ProviderLedger
    workflow, workspace = flow
    operation = workflow.begin_operation("alice", workspace, "intake", "one", {"source": "synthetic"})
    ledger = ProviderLedger(workflow.store)
    ledger.begin_attempt({"actor_id": "alice", "workspace_id": workspace, "operation_id": operation["id"]}, {"reserved_input_tokens": 10, "reserved_output_tokens": 10})
    counts = workflow.recover_interrupted()
    assert counts["provider_attempts"] == counts["operations"] == 1
    assert ledger.list_attempts("alice", workspace)[0]["state"] == "unknown_outcome"
    duplicate = workflow.begin_operation("alice", workspace, "intake", "one", {"source": "synthetic"})
    assert duplicate["created_new"] is False and duplicate["state"] == "interrupted"


def test_design_requires_separate_approval_and_keeps_historical_binding(flow):
    workflow, workspace = flow
    dataset, problem, _, old_approval, run = completed_pair(flow)
    body = design_body(run, problem)
    plan = workflow.create_design_plan("alice", run["id"], body, "design")
    assert_code("approval_required", lambda: workflow.start_design_job("alice", plan["id"], old_approval["id"], "start"))
    workflow.create_dataset("alice", workspace, dataset_body(dataset["id"]), "new-data")
    approval = workflow.approve_design_plan("alice", plan["id"], problem["id"], plan["digest"], "design-approval")
    job = workflow.start_design_job("alice", plan["id"], approval["id"], "start-design")
    assert job["plan_id"] == plan["id"] and job["kind"] == "design_job"
    assert workflow.start_design_job("alice", plan["id"], approval["id"], "fresh-key")["id"] == job["id"]


def test_design_rejects_changed_vectors_and_unapproved_grid(flow):
    workflow, _ = flow
    _, problem, _, _, run = completed_pair(flow)
    bad = design_body(run, problem)
    bad["candidate_vectors"][0]["A"] = "12/1"
    assert_code("candidate_vector_mismatch", lambda: workflow.create_design_plan("alice", run["id"], bad, "bad"))
    plan = workflow.create_design_plan("alice", run["id"], design_body(run, problem), "design")
    approval = workflow.approve_design_plan("alice", plan["id"], problem["id"], plan["digest"], "approve")
    job = workflow.start_design_job("alice", plan["id"], approval["id"], "start")
    result = {"design_tier": "unavailable", "verification": "unsupported", "replay": "unsupported", "reason_code": "fixture_only",
              "options": [{"time": "6/1", "state": "unavailable", "reason_code": "fixture_only"}]}
    assert_code("design_grid_mismatch", lambda: workflow.finish_run("alice", job["id"], result=result))
    result["options"].append({"time": "8/1", "state": "unavailable", "reason_code": "fixture_only"})
    finished = workflow.finish_run("alice", job["id"], result=result)
    assert workflow.get("alice", finished["result_id"], "suggestion")["body"]["design_tier"] == "unavailable"


def test_design_rejects_candidate_from_unbound_problem_digest(flow):
    workflow, _ = flow
    _, problem, plan, approval = prepared(flow)
    run = workflow.start_run("alice", plan["id"], approval["id"], "start")
    workflow.reserve_scenario("alice", run["id"], "baseline")
    evidence = numerical_pair(problem)
    evidence.update(problem_digest=None, expected_binding="not_supplied")
    for candidate in evidence["candidates"]:
        candidate["problem_digest"] = "a" * 64
    workflow.complete_scenario("alice", run["id"], "baseline", evidence)
    assert_code("binding_mismatch", lambda: workflow.create_design_plan("alice", run["id"], design_body(run, problem), "design"))


def test_observation_review_creates_immutable_hypothetical_fork(flow):
    workflow, workspace = flow
    dataset, _, _, _ = prepared(flow)
    proposal = workflow.create_observation_proposal("alice", workspace, {
        "dataset_id": dataset["id"], "experiment_id": dataset["body"]["experiment_id"], "origin": "hypothetical",
        "row": {"id": "r3", "time": "31/5", "concentration": "51/10", "hard_allowance": "1/5", "included": True},
        "source_description": "Explicit what-if requested by researcher", "change_reason": "Hypothetical follow-up",
        "generating_choices": {"value": "User-supplied hypothetical 5.1 mg/L"}}, "observation")
    assert workflow.workspace("alice", workspace)["current_dataset_id"] == dataset["id"]
    review = {"proposal_digest": proposal["digest"], "parent_dataset_id": dataset["id"], "accepted": True}
    revised = workflow.review_observation("alice", proposal["id"], review, "review")
    assert revised["body"]["origin"] == "hypothetical" and revised["body"]["parent_id"] == dataset["id"]
    assert len(revised["body"]["rows"]) == 3
    assert workflow.get("alice", dataset["id"])["body"] == dataset["body"]
    assert workflow.workspace("alice", workspace)["current_problem_id"] is None
    assert workflow.review_observation("alice", proposal["id"], review, "review") == revised
    assert workflow.queued_jobs() == []


def test_conversation_cas_and_retry_deduplication(flow):
    workflow, workspace = flow
    turn = workflow.accept_turn("alice", workspace, "turn", {"text": "Can I measure at six?"}, 0)
    assert turn["body"]["conversation_revision"] == 1
    assert workflow.accept_turn("alice", workspace, "turn", {"text": "Can I measure at six?"}, 0) == turn
    assert_code("stale_conversation", lambda: workflow.accept_turn("alice", workspace, "other", {"text": "stale tab"}, 0))


def test_backup_restore_and_immutable_constraints(flow, tmp_path):
    workflow, workspace = flow
    dataset = workflow.create_dataset("alice", workspace, dataset_body(), "data")
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        with workflow.store.transaction() as conn:
            conn.execute("UPDATE entities SET body='{}' WHERE id=?", (dataset["id"],))
    destination = tmp_path / "restored.sqlite3"
    workflow.store.backup(destination)
    restored = Workflow(Store(destination))
    assert restored.get("alice", dataset["id"]) == dataset
    assert restored.workspace("alice", workspace)["current_dataset_id"] == dataset["id"]


def test_agent_plan_requires_owned_exact_provider_permission(flow):
    workflow, workspace = flow
    _, problem, plan, _ = prepared(flow)
    disclosure = {"provider": "gemini", "model": "configured-model", "source_asset_ids": [],
                  "context_fields": ["reviewed_problem", "scenario_evidence"], "permission_id": "invented"}
    plan_body = {**plan["body"], "provider_disclosure": disclosure}
    assert_code("not_found", lambda: workflow.create_plan("alice", workspace, plan_body, "fake-consent"))
    consent = workflow.create_provider_consent("alice", workspace, {**{key: value for key, value in disclosure.items() if key != "permission_id"},
        "problem_id": problem["id"], "accepted": True}, "consent")
    plan_body["provider_disclosure"]["permission_id"] = consent["id"]
    created = workflow.create_plan("alice", workspace, plan_body, "real-consent")
    assert created["body"]["provider_disclosure"]["permission_id"] == consent["id"]
    plan_body["provider_disclosure"]["context_fields"].append("unrelated_source")
    assert_code("provider_consent_mismatch", lambda: workflow.create_plan("alice", workspace, plan_body, "changed-scope"))


def test_result_binding_cannot_claim_another_problem(flow):
    workflow, _ = flow
    _, problem, plan, approval = prepared(flow)
    run = workflow.start_run("alice", plan["id"], approval["id"], "start")
    workflow.reserve_scenario("alice", run["id"], "baseline")
    bad = {**unsupported(problem), "problem_id": "other_problem"}
    assert_code("binding_mismatch", lambda: workflow.complete_scenario("alice", run["id"], "baseline", bad))


def test_direct_dataset_revision_cannot_relabel_hypothetical_history(flow):
    workflow, workspace = flow
    parent = workflow.create_dataset("alice", workspace, dataset_body(origin="hypothetical"), "hypothetical")
    assert_code("origin_mismatch", lambda: workflow.create_dataset("alice", workspace, dataset_body(parent["id"], origin="actual"), "relabel"))


def test_report_snapshot_retains_all_approved_scenarios_and_source_byte_digest(flow):
    workflow, workspace = flow
    source = workflow.create_record("alice", workspace, "source_asset", {"sha256": "f" * 64, "blob_key": "private-storage-locator", "origin": "synthetic"}, "source")
    data_body = dataset_body()
    data_body["rows"][0]["source_asset_id"] = source["id"]
    # Seed a historical reviewed source record to isolate report snapshotting.
    # New source-derived API values must use the separately tested materializer.
    with workflow.store.transaction() as conn:
        first_dataset = workflow._insert(conn, "alice", workspace, "dataset", data_body)
        conn.execute("UPDATE workspaces SET current_dataset_id=? WHERE id=?", (first_dataset["id"], workspace))
    first_problem = create_problem(workflow, workspace, first_dataset, "first-problem")
    proposal = workflow.create_record("alice", workspace, "intake_proposal", {"source_asset_id": source["id"], "source_digest": "f" * 64}, "intake-proposal")
    review = workflow.create_record("alice", workspace, "intake_review", {"proposal_id": proposal["id"], "source_asset_id": source["id"],
        "reviewed_fields": [{"field_path": "rows[0].concentration", "normalized_value": "1/1", "correction_reason": "Reviewed source transcription"}]}, "intake-review")
    materialization = workflow.create_record("alice", workspace, "intake_materialization", {"dataset_id": first_dataset["id"], "problem_id": first_problem["id"],
        "review_id": review["id"], "source_asset_id": source["id"], "field_provenance": [{"origin": "human_corrected", "reviewed_value": "1/1"}]}, "intake-materialization")
    workflow.create_record("alice", workspace, "intake_materialization", {"dataset_id": "unrelated_dataset", "problem_id": "unrelated_problem"}, "unrelated-materialization")
    second_dataset = workflow.create_dataset("alice", workspace, {**first_dataset["body"], "parent_id": first_dataset["id"]}, "second-dataset")
    second_problem = create_problem(workflow, workspace, second_dataset, "second-problem")
    plan = workflow.create_plan("alice", workspace, PlanBody(problem_id=second_problem["id"], problem_digest=second_problem["digest"], dataset_id=second_dataset["id"],
        scenarios=[{"id": "baseline", "kind": "baseline", "label": "Latest", "problem_id": second_problem["id"], "problem_digest": second_problem["digest"]},
                   {"id": "optional", "kind": "optional", "label": "Historical comparison", "problem_id": first_problem["id"], "problem_digest": first_problem["digest"]}]).model_dump(mode="json"), "plan")
    approval = workflow.approve_plan("alice", plan["id"], second_problem["id"], plan["digest"], "approve")
    run = workflow.start_run("alice", plan["id"], approval["id"], "start")
    artifact = workflow.create_record("alice", workspace, "native_artifact", {"sha256": "a" * 64, "byte_size": 12, "media_type": "application/json",
        "blob_key": "private-native-locator", "anchor": {"application_problem_id": second_problem["id"], "scientific_problem_digest": "b" * 64}}, "native-artifact")
    workflow.reserve_scenario("alice", run["id"], "baseline")
    workflow.complete_scenario("alice", run["id"], "baseline", {**unsupported(second_problem), "artifacts": [
        {"id": artifact["id"], "sha256": "a" * 64, "byte_size": 12, "media_type": "application/json"}]})
    report = workflow.create_report("alice", run["id"], "report")
    assert {item["dataset"]["id"] for item in report["body"]["scenario_inputs"]} == {first_dataset["id"], second_dataset["id"]}
    assert report["body"]["source_assets"][0]["metadata"]["sha256"] == "f" * 64
    assert "blob_key" not in report["body"]["source_assets"][0]["metadata"]
    assert [item["id"] for item in report["body"]["intake_materializations"]] == [materialization["id"]]
    assert report["body"]["intake_reviews"][0]["body"]["reviewed_fields"][0]["correction_reason"] == "Reviewed source transcription"
    assert report["body"]["intake_proposals"][0]["id"] == proposal["id"]
    assert report["body"]["native_artifacts"][0]["metadata"]["anchor"]["scientific_problem_digest"] == "b" * 64
    assert "blob_key" not in report["body"]["native_artifacts"][0]["metadata"]


def test_expired_accepted_approval_stops_new_work_without_rewriting_scope(flow, monkeypatch):
    workflow, _ = flow
    _, _, plan, approval = prepared(flow)
    run = workflow.start_run("alice", plan["id"], approval["id"], "start")
    monkeypatch.setattr("bean_api.workflow.utc_now", lambda: "2999-01-01T00:00:00.000Z")
    assert_code("approval_expired", lambda: workflow.reserve_scenario("alice", run["id"], "baseline"))
    assert workflow.get_run("alice", run["id"])["plan_id"] == plan["id"]


def test_intentional_rerun_requires_reviewed_plan_ancestry(flow):
    workflow, workspace = flow
    _, _, plan, _ = prepared(flow)
    assert_code("plan_ancestry_required", lambda: workflow.create_plan("alice", workspace, plan["body"], "new-plan"))
    new_plan = workflow.create_plan("alice", workspace, {**plan["body"], "parent_plan_id": plan["id"]}, "new-plan-with-ancestry")
    assert new_plan["body"]["parent_plan_id"] == plan["id"] and new_plan["digest"] != plan["digest"]


def test_optional_condition_and_complete_accounting_are_authoritative(flow):
    workflow, workspace = flow
    dataset, problem, original, _ = prepared(flow)
    body = {**original["body"], "parent_plan_id": original["id"], "scientific_profile": "counterdex.v1",
        "objective": {"question": "Does an allowed explanation challenge this interval?", "success_criterion": "Return checked evidence or an honest unresolved result."},
        "scenarios": [original["body"]["scenarios"][0], {
            "id": "optional", "kind": "optional", "label": "Allowed comparison", "problem_id": problem["id"],
            "problem_digest": problem["digest"], "purpose": "Investigate an unresolved baseline",
            "eligible_baseline_outcomes": ["inconclusive"]}]}
    plan = workflow.create_plan("alice", workspace, body, "conditional")
    approval = workflow.approve_plan("alice", plan["id"], problem["id"], plan["digest"], "approve-conditional")
    run = workflow.start_run("alice", plan["id"], approval["id"], "conditional-start")
    workflow.reserve_scenario("alice", run["id"], "baseline")
    workflow.complete_scenario("alice", run["id"], "baseline", unsupported(problem))
    assert_code("scenario_condition_ineligible", lambda: workflow.reserve_scenario("alice", run["id"], "optional"))
    assert_code("scenario_accounting_incomplete", lambda: workflow.finish_run("alice", run["id"]))
    workflow.skip_scenario("alice", run["id"], "optional", "capability_unavailable")
    assert workflow.finish_run("alice", run["id"])["state"] == "completed"


def test_source_derived_dataset_requires_review_materialization(flow):
    workflow, workspace = flow
    source = workflow.create_record("alice", workspace, "source_asset", {"sha256": "f" * 64}, "source")
    body = dataset_body()
    body["rows"][0]["source_asset_id"] = source["id"]
    assert_code("source_review_required", lambda: workflow.create_dataset("alice", workspace, body, "unreviewed"))
    assert workflow.workspace("alice", workspace)["current_dataset_id"] is None
    # Existing reviewed material is immutable; a later unchanged copy is allowed.
    with workflow.store.transaction() as conn:
        parent = workflow._insert(conn, "alice", workspace, "dataset", body)
    revised = workflow.create_dataset("alice", workspace, {**body, "parent_id": parent["id"]}, "unchanged-source")
    changed = {**revised["body"], "rows": [dict(row) for row in revised["body"]["rows"]], "parent_id": revised["id"]}
    changed["rows"][0]["concentration"] = "7/1"
    assert_code("source_review_required", lambda: workflow.create_dataset("alice", workspace, changed, "changed-source"))
    changed["rows"][0]["source_asset_id"] = None
    assert_code("source_review_required", lambda: workflow.create_dataset("alice", workspace, changed, "stripped-source"))


def test_scientific_design_retains_reviewed_grid_and_limits_horizon(flow):
    import json
    from pathlib import Path
    workflow, workspace = flow
    fixture = json.loads((Path(__file__).resolve().parents[1] / "shared/contracts/DB-SC-1/fixtures/counterdex-reviewed-scope.json").read_text())
    dataset = workflow.create_dataset("alice", workspace, fixture["dataset"], "scientific-dataset")
    problem = workflow.create_problem("alice", workspace, {**fixture["problem"], "dataset_id": dataset["id"], "dataset_digest": dataset["digest"]}, "scientific-problem")
    plan = workflow.create_plan("alice", workspace, {**fixture["plan"], "problem_id": problem["id"], "problem_digest": problem["digest"], "dataset_id": dataset["id"],
        "scenarios": [{"id": "baseline", "kind": "baseline", "label": "Synthetic authority control", "problem_id": problem["id"], "problem_digest": problem["digest"]}]}, "scientific-plan")
    approval = workflow.approve_plan("alice", plan["id"], problem["id"], plan["digest"], "scientific-approval")
    run = workflow.start_run("alice", plan["id"], approval["id"], "scientific-run")
    workflow.reserve_scenario("alice", run["id"], "baseline")
    workflow.complete_scenario("alice", run["id"], "baseline", numerical_pair(problem))
    workflow.finish_run("alice", run["id"])
    request = {**design_body(run, problem), "scientific_profile": "counterdex.v1", "requested_tier": "checked_pair_separation",
        "allowance_origin": {"kind": "hypothetical", "description": "Explicit synthetic future hard bound"},
        "maximum_horizon": "8/1", "allow_construction": True, "allow_continuation": True,
        "feasible_times": ["8/1", "6/1"]}
    plan = workflow.create_design_plan("alice", run["id"], request, "scientific-design")
    assert plan["body"]["request"]["feasible_times"] == ["8/1", "6/1"]
    assert plan["body"]["request"]["maximum_horizon"] == "8/1"
    assert_code("artifact_not_in_scope", lambda: workflow.create_design_plan("alice", run["id"], {**request, "source_artifact_ids": ["unrelated"]}, "wrong-source"))
    assert_code("scientific_admission", lambda: workflow.create_design_plan("alice", run["id"], {**request, "budget": {"pair_verifications": 1}}, "insufficient-checks"))


def test_source_derived_observation_cannot_bypass_intake_review(flow):
    workflow, workspace = flow
    dataset, _, _, _ = prepared(flow)
    source = workflow.create_record("alice", workspace, "source_asset", {"sha256": "f" * 64}, "source")
    body = {"dataset_id": dataset["id"], "experiment_id": dataset["body"]["experiment_id"], "origin": "actual", "source_description": "Synthetic source control",
        "change_reason": "New observation", "row": {"id": "new", "time": "8/1", "concentration": "17/5", "hard_allowance": "1/5", "included": True,
            "source_asset_id": source["id"]}}
    assert_code("source_review_required", lambda: workflow.create_observation_proposal("alice", workspace, body, "bypass"))
    # A proposal persisted by an earlier version cannot bypass the new boundary.
    old_proposal = workflow.create_record("alice", workspace, "observation_proposal", body, "historical-proposal")
    assert_code("source_review_required", lambda: workflow.review_observation("alice", old_proposal["id"], {
        "proposal_digest": old_proposal["digest"], "parent_dataset_id": dataset["id"], "accepted": True}, "bypass-review"))
