"""Real approved hypothetical follow-up, fixed-pair feedback and offline replay.

Only the new reading is generated from the computed design for this control.
Candidate vectors always originate in the actual baseline search.
"""
import base64
from copy import deepcopy
from fractions import Fraction
import hashlib
import json

import pytest

from bean_api.contracts import PlanBody
from bean_api.main import PREFIX
from bean_api.worker import Worker
import test_baseline_workflow as baseline
import test_native_design_workflow as design
from test_scientific_http import post

scientific_client = design.scientific_client
computed_history = design.computed_history
replay_python = baseline.replay_python


@pytest.fixture
def computed_design(computed_history):
    history = computed_history
    plan = design.propose(history, design.design_request(history), "followup-design")
    job, approval, result, content, anchors = design.approve_start_and_download(history, plan, "followup-design")
    assert result["design_tier"] == "checked_pair_separation"
    finished = history["client"].get(PREFIX + f"/design-jobs/{job['id']}").json()
    record = history["client"].get(PREFIX + f"/records/{finished['result_id']}").json()
    return {**history, "design_plan": plan, "design_job": finished, "design_approval": approval,
            "design_result": result, "design_record": record, "design_content": content, "design_anchors": anchors}


def reading_for(history, choice):
    result = history["design_result"]
    row = next(row for row in result["native_replay"]["fresh_checked"]["rows"]
               if row["time"] == result["selected_time"])
    ids = result["candidate_ids"]
    centers = [Fraction(row["centers"][cid]) for cid in ids]
    reading = centers[choice] if choice < 2 else sum(centers) / 2
    # Explicitly generate a six-decimal hypothetical instrument reading, not a
    # copied candidate oracle or an actual acquisition claim.
    value = Fraction(format(float(reading), ".6f"))
    return f"{value.numerator}/{value.denominator}", {ids[choice]} if choice < 2 else set()


def revised_inputs(history, value, *, origin="hypothetical", time=None, allowance=None):
    client, workspace = history["client"], history["workspace"]
    result = history["design_result"]
    body = {"dataset_id": history["dataset"]["id"], "experiment_id": history["dataset"]["body"]["experiment_id"],
        "origin": origin, "row": {"id": "hypothetical_followup", "time": time or result["selected_time"],
            "concentration": value, "hard_allowance": allowance or result["future_hard_allowance"], "included": True,
            "notes": "Explicit hypothetical control, not an acquired measurement"},
        "source_description": "Generated from the selected computed design for an explicit hypothetical control",
        "change_reason": "Review what this proposed new reading would imply for the original selected pair"}
    if origin == "hypothetical":
        body["generating_choices"] = {"design_job_id": history["design_job"]["id"],
            "method": "Six-decimal reading from computed prediction center or midpoint"}
    proposal = post(client, f"/workspaces/{workspace}/observation-proposals", body, "followup-observation")
    dataset = post(client, f"/observation-proposals/{proposal['id']}/review", {
        "proposal_digest": proposal["digest"], "parent_dataset_id": history["dataset"]["id"],
        "accepted": True}, "followup-observation-review")
    problem = post(client, f"/workspaces/{workspace}/problems", {
        **history["problem"]["body"], "dataset_id": dataset["id"], "dataset_digest": dataset["digest"]}, "followup-problem")
    followup = {"design_job_id": history["design_job"]["id"], "design_result_id": history["design_record"]["id"],
        "design_result_digest": history["design_record"]["digest"], "observation_proposal_id": proposal["id"],
        "source_artifact_id": result["artifacts"][0]["id"]}
    plan = PlanBody(problem_id=problem["id"], problem_digest=problem["digest"], dataset_id=dataset["id"],
        scientific_profile="counterdex.v1", objective={"question": "Which original candidates survive this hypothetical reading?",
            "success_criterion": "Retain candidate-specific checked feedback without making a global claim."},
        scenarios=[{"id": "followup", "kind": "baseline", "label": "Recheck original pair, no new discovery",
            "problem_id": problem["id"], "problem_digest": problem["digest"]}], followup=followup).model_dump(mode="json")
    return proposal, dataset, problem, plan


@pytest.mark.parametrize("choice", [0, 1, 2], ids=["first_survives", "second_survives", "both_excluded"])
def test_hypothetical_followup_rechecks_original_pair_with_new_approval_and_portable_history(
        computed_design, replay_python, tmp_path, choice):
    history, client = computed_design, computed_design["client"]
    value, survivors = reading_for(history, choice)
    proposal, dataset, problem, plan_body = revised_inputs(history, value)
    assert dataset["body"]["origin"] == "hypothetical"
    assert dataset["body"]["parent_id"] == history["dataset"]["id"]
    assert dataset["body"]["rows"][:-1] == history["dataset"]["body"]["rows"]
    plan = post(client, f"/workspaces/{history['workspace']}/plans", {
        "expected_current_revision_id": problem["id"], "plan": plan_body}, "followup-plan")
    for previous in (history["approval"], history["design_approval"]):
        rejected = client.post(PREFIX + f"/plans/{plan['id']}/runs", json={
            "approval_id": previous["id"], "expected_plan_digest": plan["digest"]},
            headers={"Idempotency-Key": "old-approval-" + previous["id"]})
        assert rejected.status_code == 403, rejected.text
        assert rejected.json()["code"] == "approval_required"
    assert Worker(client.app.state.workflow, settings=client.app.state.settings).tick() == 0
    approval = post(client, f"/plans/{plan['id']}/approvals", {
        "expected_current_revision_id": problem["id"], "expected_plan_digest": plan["digest"],
        "accepted": True}, "followup-approval")
    start = {"approval_id": approval["id"], "expected_plan_digest": plan["digest"]}
    run = post(client, f"/plans/{plan['id']}/runs", start, "followup-start")
    assert Worker(client.app.state.workflow, settings=client.app.state.settings).tick() == 1
    finished = client.get(PREFIX + f"/runs/{run['id']}").json()
    assert finished["state"] == "completed", finished
    evidence = client.get(PREFIX + f"/records/{finished['scenarios'][0]['result_id']}").json()
    result = evidence["body"]["result"]
    assert result["problem_id"] == problem["id"] and result["problem_digest"] == problem["digest"]
    original_vectors = dict(zip(history["design_result"]["candidate_ids"],
                                history["design_plan"]["body"]["request"]["candidate_vectors"], strict=True))
    assert {c["id"]: c["parameter_vector"] for c in result["candidates"]} == original_vectors
    assert {c["candidate_id"] for c in result["candidate_results"] if c["verification"] == "valid"} == survivors
    excluded = [c for c in result["candidate_results"] if c["verification"] == "invalid"]
    assert len(excluded) == 2 - len(survivors)
    assert all(c["violating_observation_ids"] == ["hypothetical_followup"] for c in excluded)
    assert result.get("baseline_search") is None
    assert result["replay"] == "passed" and result["expected_binding"] == "matches"
    if not survivors:
        assert result["scientific_outcome"] == "inconclusive"
        assert result["verification"] == "valid"
        assert result["native_replay"]["historical_compatibility"] == "invalid"
        assert not any(c["is_counterexample"] for c in result["candidate_results"])

    reference = result["artifacts"][0]
    download = client.get(PREFIX + f"/artifacts/{reference['id']}")
    assert download.status_code == 200
    assert len(download.content) == reference["byte_size"]
    assert hashlib.sha256(download.content).hexdigest() == reference["sha256"] == download.headers["X-Artifact-SHA256"]
    anchors = client.get(PREFIX + f"/artifacts/{reference['id']}/anchor?download=true").json()
    packet = download.json()
    assert packet["operation"] == "review"
    assert packet["binding"]["dataset"]["body"] == dataset["body"]
    assert packet["binding"]["problem"]["body"] == problem["body"]
    assert base64.b64decode(packet["history"]["bytes_base64"], validate=True) == history["design_content"]
    assert packet["history"]["anchors"] == history["design_anchors"]
    native = json.loads(base64.b64decode(packet["scientific"]["bytes_base64"], validate=True))
    assert native["operation"] == "fixed_candidate_review" and native["search"] is None
    assert {c["id"]: c["parameters"] for c in native["candidates"]} == original_vectors
    assert native["workflow"] == {"plan_id": plan["id"], "approval_id": approval["id"],
        "operation_id": run["id"], "execution_id": run["id"]}
    process, fresh = baseline.replay_cli(replay_python, tmp_path, download.content, anchors)
    assert process.returncode == 0, fresh
    assert fresh["integrity"] == fresh["replay"] == "passed" and fresh["expected_binding"] == "matches"
    assert fresh["operation"] == "review" and fresh["dataset_origin"] == "hypothetical"
    assert fresh["verification"] == result["verification"]
    assert {c["candidate_id"] for c in fresh["candidate_results"] if c["verification"] == "valid"} == survivors
    process, failure = baseline.replay_cli(replay_python, tmp_path, download.content,
        {**anchors, "problem_digest": history["problem"]["digest"]})
    assert process.returncode == 2 and failure["error"]["code"] == "wrong_specification_binding"
    assert post(client, f"/plans/{plan['id']}/runs", start, "followup-retry")["id"] == run["id"]
    assert Worker(client.app.state.workflow, settings=client.app.state.settings).tick() == 0
    design.assert_preserved_history(history)
    assert client.get(PREFIX + f"/artifacts/{history['design_result']['artifacts'][0]['id']}").content == history["design_content"]
    assert client.get(PREFIX + f"/records/{history['design_record']['id']}").json() == history["design_record"]
    assert client.get(PREFIX + f"/records/{proposal['id']}").json() == proposal
    report = post(client, f"/runs/{run['id']}/reports", {}, "followup-report")
    lineage = report["body"]["followup"]
    assert lineage["observation_proposal"] == proposal
    assert lineage["observation_review"]["body"]["dataset_id"] == dataset["id"]
    assert lineage["dataset"] == history["dataset"] and lineage["revised_dataset"] == dataset
    assert lineage["design_result"] == history["design_record"]
    assert lineage["artifact"]["metadata"]["anchor"] == history["design_anchors"]
    assert not {"blob_key", "storage_path", "signed_url", "content_base64"} & lineage["artifact"]["metadata"].keys()
    assert client.get(PREFIX + f"/artifacts/{reference['id']}", headers={"Authorization": "Bearer " + "b" * 40}).status_code == 404


@pytest.mark.parametrize("origin,time,allowance,code", [
    ("actual", None, None, "followup_origin_unsupported"),
    ("hypothetical", "79/10", None, "followup_lineage_mismatch"),
    ("hypothetical", None, "1/10", "followup_lineage_mismatch"),
])
def test_followup_admission_rejects_unimplemented_observation_scope(computed_design, origin, time, allowance, code):
    history, client = computed_design, computed_design["client"]
    value, _ = reading_for(history, 0)
    _, _, problem, body = revised_inputs(history, value, origin=origin, time=time, allowance=allowance)
    response = client.post(PREFIX + f"/workspaces/{history['workspace']}/plans", json={
        "expected_current_revision_id": problem["id"], "plan": body}, headers={"Idempotency-Key": "unsupported-followup"})
    assert response.status_code == 422, response.text
    assert response.json()["code"] == code
    assert Worker(client.app.state.workflow, settings=client.app.state.settings).tick() == 0
    design.assert_preserved_history(history)


def test_followup_plan_rejects_changed_design_identity(computed_design):
    history, client = computed_design, computed_design["client"]
    value, _ = reading_for(history, 0)
    _, _, problem, body = revised_inputs(history, value)
    changed = deepcopy(body)
    changed["followup"]["design_result_digest"] = "0" * 64
    response = client.post(PREFIX + f"/workspaces/{history['workspace']}/plans", json={
        "expected_current_revision_id": problem["id"], "plan": changed}, headers={"Idempotency-Key": "wrong-design-digest"})
    assert response.status_code == 422 and response.json()["code"] == "binding_mismatch", response.text
    assert Worker(client.app.state.workflow, settings=client.app.state.settings).tick() == 0


@pytest.mark.parametrize("stop", ["cancel", "expire"])
def test_completed_followup_cannot_publish_after_authority_ends(computed_design, monkeypatch, stop):
    import bean_api.worker as worker_module

    history, client = computed_design, computed_design["client"]
    value, _ = reading_for(history, 0)
    _, _, problem, body = revised_inputs(history, value)
    plan = post(client, f"/workspaces/{history['workspace']}/plans", {
        "expected_current_revision_id": problem["id"], "plan": body}, "late-followup-plan")
    approval = post(client, f"/plans/{plan['id']}/approvals", {
        "expected_current_revision_id": problem["id"], "expected_plan_digest": plan["digest"],
        "accepted": True}, "late-followup-approval")
    run = post(client, f"/plans/{plan['id']}/runs", {
        "approval_id": approval["id"], "expected_plan_digest": plan["digest"]}, "late-followup-start")
    real_run = worker_module.run_bounded

    def complete_then_end_scope(*args, **kwargs):
        result = real_run(*args, **kwargs)
        assert result.get("native_replay", {}).get("operation") == "review", result
        assert result["verification"] == "valid" and result["replay"] == "passed"
        if stop == "cancel":
            post(client, f"/runs/{run['id']}/cancel", {}, "late-followup-cancel")
        else:
            monkeypatch.setattr("bean_api.workflow.utc_now", lambda: "2100-01-01T00:00:00.000Z")
        return result

    monkeypatch.setattr(worker_module, "run_bounded", complete_then_end_scope)
    assert Worker(client.app.state.workflow, settings=client.app.state.settings).tick() == 1
    finished = client.get(PREFIX + f"/runs/{run['id']}").json()
    assert finished["state"] == ("cancelled" if stop == "cancel" else "failed")
    assert finished["error_code"] == ("job_not_active" if stop == "cancel" else "approval_expired")
    assert all(scenario["result_id"] is None for scenario in finished["scenarios"])
    retained = client.get(PREFIX + f"/workspaces/{history['workspace']}/records?kind=native_artifact").json()
    assert {item["id"] for item in retained} == {
        history["result"]["artifacts"][0]["id"], history["design_result"]["artifacts"][0]["id"]}
    design.assert_preserved_history(history)
