"""Authority/lineage controls with explicitly seeded records, not science claims.

Real computation and downloaded replay are covered by the HTTP acceptance suite.
"""
from copy import deepcopy

import pytest
from pydantic import ValidationError

from bean_api.contracts import PlanBody
from bean_api.store import Store
from bean_api.workflow import DomainError, Workflow
from test_workflow import create_problem, dataset_body


@pytest.fixture
def scope(tmp_path):
    workflow = Workflow(Store(tmp_path / "scope.sqlite3"))
    workspace = workflow.create_workspace("alice", "Contract-only lineage control")["id"]
    dataset = workflow.create_dataset("alice", workspace, dataset_body(), "dataset")
    problem = create_problem(workflow, workspace, dataset)
    request = {"problem_id": problem["id"], "problem_digest": problem["digest"],
               "scenario_id": "baseline", "candidate_ids": ["a", "b"], "future_hard_allowance": "1/5"}
    design_plan = workflow.create_record("alice", workspace, "design_plan", {
        "request": request, "request_digest": "1" * 64}, "design-plan")
    approval = workflow.approve_design_plan("alice", design_plan["id"], problem["id"], design_plan["digest"], "approve-design")
    job = workflow.start_design_job("alice", design_plan["id"], approval["id"], "start-design")
    artifact = workflow.create_record("alice", workspace, "native_artifact", {
        "sha256": "2" * 64, "byte_size": 10, "media_type": "application/vnd.counterdex.native+json",
        "blob_key": "private-locator", "origin": {"run_id": job["id"], "scenario_id": "baseline",
            "plan_id": design_plan["id"], "approval_id": approval["id"]},
        "anchor": {"artifact_sha256": "2" * 64, "dataset_digest": dataset["digest"], "problem_digest": problem["digest"],
            "projection_digest": "3" * 64, "app_request_digest": "1" * 64, "design_digest": "4" * 64,
            "run_id": job["id"], "scenario_id": "baseline"}}, "artifact")
    result = workflow.create_record("alice", workspace, "suggestion", {
        "projection_version": "DB-SC-1-to-groundwork-v1", "design_tier": "checked_pair_separation",
        "verification": "valid", "replay": "passed", "native_replay": {"expected_binding": "matches"},
        "verification_record": {"expected_binding": "matches"}, "selected_time": "8/1", "candidate_ids": ["a", "b"],
        "future_hard_allowance": "1/5", "scientific_problem_digest": "3" * 64, "scientific_design_digest": "4" * 64,
        "artifacts": [{"id": artifact["id"], **{k: artifact["body"][k] for k in ("sha256", "byte_size", "media_type")}}]}, "result")
    # Only this isolated authority control seeds a finished scientific state.
    with workflow.store.transaction() as conn:
        conn.execute("UPDATE jobs SET state='completed',result_id=? WHERE id=?", (result["id"], job["id"]))
    observation = workflow.create_observation_proposal("alice", workspace, {
        "dataset_id": dataset["id"], "experiment_id": dataset["body"]["experiment_id"], "origin": "hypothetical",
        "row": {"id": "new", "time": "8/1", "concentration": "3/1", "hard_allowance": "1/5", "included": True},
        "source_description": "Explicit hypothetical control", "change_reason": "Test lineage",
        "generating_choices": {"value": "Hand-chosen hypothetical value"}}, "observation")
    revised = workflow.review_observation("alice", observation["id"], {
        "proposal_digest": observation["digest"], "parent_dataset_id": dataset["id"], "accepted": True}, "review")
    revised_problem = create_problem(workflow, workspace, revised, "revised-problem")
    plan = PlanBody.model_validate({"problem_id": revised_problem["id"], "problem_digest": revised_problem["digest"],
        "dataset_id": revised["id"], "scenarios": [{"id": "followup", "kind": "baseline", "label": "Check selected pair",
            "problem_id": revised_problem["id"], "problem_digest": revised_problem["digest"]}],
        "scientific_profile": "counterdex.v1", "objective": {"question": "Which selected candidate survives?",
            "success_criterion": "Check exactly the original pair against the hypothetical reading"},
        "followup": {"design_job_id": job["id"], "design_result_id": result["id"], "design_result_digest": result["digest"],
            "observation_proposal_id": observation["id"], "source_artifact_id": artifact["id"]}}).model_dump(mode="json")
    return workflow, workspace, plan, dataset, problem, observation, result, revised


def reject(code, call):
    with pytest.raises(DomainError) as caught:
        call()
    assert caught.value.code == code


def test_followup_scope_resolves_original_context_and_requires_new_approval(scope):
    workflow, workspace, body, dataset, problem, proposal, result, revised = scope
    plan = workflow.create_plan("alice", workspace, body, "followup-plan")
    context = workflow.followup_context("alice", plan["body"])
    assert context["dataset"] == dataset and context["problem"] == problem
    assert context["observation_proposal"] == proposal and context["design_result"] == result
    assert context["revised_dataset"] == revised
    reject("approval_required", lambda: workflow.start_run("alice", plan["id"], context["design_job"]["approval_id"], "wrong-approval"))
    assert workflow.get("alice", dataset["id"]) == dataset


@pytest.mark.parametrize("field,value", [("verification", "not_checked"), ("replay", "unsupported"),
                                        ("native_replay", {"expected_binding": "mismatch"}),
                                        ("verification_record", {"expected_binding": "mismatch"})])
def test_followup_requires_qualified_matching_parent(scope, field, value):
    workflow, workspace, body, _, _, _, result, _ = scope
    changed = {**result["body"], field: value}
    replacement = workflow.create_record("alice", workspace, "suggestion", changed, "unqualified-result")
    with workflow.store.transaction() as conn:
        conn.execute("UPDATE jobs SET result_id=? WHERE id=?", (replacement["id"], body["followup"]["design_job_id"]))
    body["followup"].update(design_result_id=replacement["id"], design_result_digest=replacement["digest"])
    reject("followup_design_required", lambda: workflow.create_plan("alice", workspace, body, "unqualified-followup"))


@pytest.mark.parametrize("field,value,code", [("design_result_digest", "0" * 64, "binding_mismatch"),
    ("source_artifact_id", "missing", "not_found"), ("design_result_id", "missing", "followup_design_required")])
def test_scope_cannot_swap_selected_result_or_artifact(scope, field, value, code):
    workflow, workspace, body, *_ = scope
    body["followup"][field] = value
    reject(code, lambda: workflow.create_plan("alice", workspace, body, "altered-scope"))


def test_nonreviewed_direct_dataset_copy_does_not_supply_observation_authority(scope):
    workflow, workspace, body, dataset, _, _, _, revised = scope
    copied = workflow.create_dataset("alice", workspace, revised["body"], "direct-copy")
    problem = create_problem(workflow, workspace, copied, "copy-problem")
    body.update(problem_id=problem["id"], problem_digest=problem["digest"], dataset_id=copied["id"])
    body["scenarios"][0].update(problem_id=problem["id"], problem_digest=problem["digest"])
    assert copied["body"]["parent_id"] == dataset["id"]
    reject("observation_review_required", lambda: workflow.create_plan("alice", workspace, body, "unreviewed"))


def test_followup_rejects_changed_problem_model_scope(scope):
    workflow, workspace, body, _, _, _, _, revised = scope
    old = workflow.get("alice", body["problem_id"])
    changed = deepcopy(old["body"])
    changed["target"]["upper"] = "1/4"
    problem = workflow.create_problem("alice", workspace, changed, "changed-target")
    body.update(problem_id=problem["id"], problem_digest=problem["digest"])
    body["scenarios"][0].update(problem_id=problem["id"], problem_digest=problem["digest"])
    reject("followup_lineage_mismatch", lambda: workflow.create_plan("alice", workspace, body, "changed-plan"))


def test_followup_scope_cannot_cross_workspaces(scope):
    workflow, _, body, *_ = scope
    workspace = workflow.create_workspace("alice", "Separate workspace")["id"]
    dataset = workflow.create_dataset("alice", workspace, dataset_body(), "other-dataset")
    problem = create_problem(workflow, workspace, dataset, "other-problem")
    body.update(problem_id=problem["id"], problem_digest=problem["digest"], dataset_id=dataset["id"])
    body["scenarios"][0].update(problem_id=problem["id"], problem_digest=problem["digest"])
    reject("not_found", lambda: workflow.create_plan("alice", workspace, body, "foreign-scope"))


def test_followup_is_manual_single_scenario_and_absent_on_legacy_plans(scope):
    _, _, body, *_ = scope
    body["scenarios"].append({**body["scenarios"][0], "id": "optional", "kind": "optional",
        "purpose": "Different calculation", "eligible_baseline_outcomes": ["inconclusive"]})
    with pytest.raises(ValidationError, match="one separately reviewed manual"):
        PlanBody.model_validate(body)
    body["scenarios"].pop()
    body.pop("followup")
    assert "followup" not in PlanBody.model_validate(body).model_dump(mode="json")
