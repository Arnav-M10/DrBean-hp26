"""Ordinary HTTP baseline -> separate design approval -> portable native replay.

Only measurement inputs are synthetic. Candidate vectors come from actual
baseline discovery, and all histories/approvals are created through public routes.
"""
import base64
from copy import deepcopy
from fractions import Fraction
import hashlib
import json

import pytest

from bean_api.main import PREFIX
from bean_api.contracts import PlanBody
from bean_api.worker import Worker
import test_baseline_workflow as baseline
import test_scientific_http as scientific_http
from test_scientific_http import ROOT, post, prepare_approved_history

scientific_client = scientific_http.scientific_client
replay_python = baseline.replay_python


@pytest.fixture
def computed_history(scientific_client):
    client = scientific_client
    workspace, dataset, problem, _, approval, run, _ = prepare_approved_history(client)
    result, content, anchors, _ = baseline.execute_and_download(client, run)
    assert len(result["candidates"]) == 2
    assert all(candidate["verification"] == "valid" for candidate in result["candidates"])
    finished = client.get(PREFIX + f"/runs/{run['id']}").json()
    evidence = client.get(PREFIX + f"/records/{finished['scenarios'][0]['result_id']}").json()
    return {"client": client, "workspace": workspace, "dataset": dataset, "problem": problem,
            "approval": approval, "run": run, "result": result, "content": content,
            "anchors": anchors, "evidence": evidence}


def design_request(history, *, times=None, allowance="1/5"):
    candidates = history["result"]["candidates"]
    return {"historical_run_id": history["run"]["id"], "scenario_id": "baseline",
        "problem_id": history["problem"]["id"], "problem_digest": history["problem"]["digest"],
        "candidate_ids": [candidate["id"] for candidate in candidates],
        "candidate_vectors": [candidate["parameter_vector"] for candidate in candidates],
        "feasible_times": ["8/1", "6/1"] if times is None else times,
        "future_hard_allowance": allowance, "scientific_profile": "counterdex.v1",
        "requested_tier": "checked_pair_separation", "maximum_horizon": "8/1",
        "allowance_origin": {"kind": "hypothetical", "description": "Explicitly reviewed prospective synthetic hard bound"},
        "allow_construction": True, "allow_continuation": True,
        "source_artifact_ids": []}


def propose(history, request, key):
    return post(history["client"], f"/runs/{history['run']['id']}/design-proposals", request, key)


def approve_start_and_download(history, plan, key):
    client = history["client"]
    approval = post(client, f"/design-plans/{plan['id']}/approvals", {
        "expected_plan_digest": plan["digest"], "expected_current_revision_id": history["problem"]["id"],
        "accepted": True}, key + "-approval")
    start = {"approval_id": approval["id"], "expected_plan_digest": plan["digest"]}
    job = post(client, f"/design-plans/{plan['id']}/jobs", start, key + "-start")
    assert Worker(client.app.state.workflow, settings=client.app.state.settings).tick() == 1
    finished = client.get(PREFIX + f"/design-jobs/{job['id']}").json()
    assert finished["state"] == "completed", finished
    assert finished["plan_id"] == plan["id"] and finished["approval_id"] == approval["id"]
    result = client.get(PREFIX + f"/records/{finished['result_id']}").json()["body"]
    assert result["projection_version"] == "DB-SC-1-to-groundwork-v1"
    assert result["candidate_ids"] == plan["body"]["request"]["candidate_ids"]
    assert result["future_hard_allowance"] == plan["body"]["request"]["future_hard_allowance"]
    assert [row["time"] for row in result["options"]] == plan["body"]["request"]["feasible_times"]
    assert len(result["artifacts"]) == 1
    reference = result["artifacts"][0]
    downloaded = client.get(PREFIX + f"/artifacts/{reference['id']}")
    assert downloaded.status_code == 200
    assert downloaded.headers["content-type"].split(";")[0] == "application/vnd.counterdex.native+json"
    assert len(downloaded.content) == reference["byte_size"]
    assert hashlib.sha256(downloaded.content).hexdigest() == reference["sha256"] == downloaded.headers["X-Artifact-SHA256"]
    response = client.get(PREFIX + f"/artifacts/{reference['id']}/anchor?download=true")
    assert response.status_code == 200 and "attachment" in response.headers["content-disposition"]
    anchors = response.json()
    assert anchors == {"artifact_sha256": reference["sha256"], "dataset_digest": history["dataset"]["digest"],
        "problem_digest": history["problem"]["digest"], "projection_digest": history["anchors"]["projection_digest"],
        "app_request_digest": plan["body"]["request_digest"], "design_digest": result["scientific_design_digest"],
        "run_id": job["id"], "scenario_id": "baseline"}
    packet = downloaded.json()
    assert packet["schema_version"] == "counterdex.application-bundle.v1" and packet["operation"] == "design"
    assert packet["binding"]["request"] == plan["body"]["request"]
    assert packet["binding"]["mapping_policy"] == "DB-SC-1-design-to-groundwork-v2"
    assert plan["body"]["request"].get("source_artifact_ids", []) == []
    assert packet["binding"]["historical_evidence"] == history["evidence"]["body"]
    assert base64.b64decode(packet["history"]["bytes_base64"], validate=True) == history["content"]
    assert packet["history"]["anchors"] == history["anchors"]
    scientific = json.loads(base64.b64decode(packet["scientific"]["bytes_base64"], validate=True))
    assert scientific["workflow"] == {"plan_id": plan["id"], "approval_id": approval["id"],
        "operation_id": job["id"], "execution_id": job["id"]}
    assert [candidate["parameters"] for candidate in scientific["design"]["candidates"]] == plan["body"]["request"]["candidate_vectors"]
    assert scientific["design"]["allowance_origin"] == plan["body"]["request"]["allowance_origin"]
    assert scientific["design"]["horizon_policy"]["maximum_horizon"] == plan["body"]["request"]["maximum_horizon"]
    assert post(client, f"/design-plans/{plan['id']}/jobs", start, key + "-retry")["id"] == job["id"]
    assert Worker(client.app.state.workflow, settings=client.app.state.settings).tick() == 0
    return job, approval, result, downloaded.content, anchors


def assert_preserved_history(history):
    client = history["client"]
    assert client.get(PREFIX + f"/artifacts/{history['result']['artifacts'][0]['id']}").content == history["content"]
    assert client.get(PREFIX + f"/records/{history['evidence']['id']}").json() == history["evidence"]
    assert client.get(PREFIX + f"/workspaces/{history['workspace']}/provider-attempts").json() == []


def test_actual_pair_design_requires_separate_approval_and_replays_downloaded_lineage(computed_history, replay_python, tmp_path):
    history, client = computed_history, computed_history["client"]
    request = {**design_request(history), "maximum_horizon": "10/1"}
    plan = propose(history, request, "design")
    # The investigation approval grants no authority to run this new design.
    response = client.post(PREFIX + f"/design-plans/{plan['id']}/jobs", json={
        "approval_id": history["approval"]["id"], "expected_plan_digest": plan["digest"]},
        headers={"Idempotency-Key": "baseline-approval-cannot-design"})
    assert response.status_code == 403 and response.json()["code"] == "approval_required"
    assert Worker(client.app.state.workflow, settings=client.app.state.settings).tick() == 0

    job, _, result, content, anchors = approve_start_and_download(history, plan, "design")
    assert result["design_tier"] == "checked_pair_separation"
    assert result["verification"] == "valid" and result["replay"] == "passed"
    selected = next(row for row in result["options"] if row["time"] == result["selected_time"])
    assert selected["state"] == "evaluated" and Fraction(selected["exact_margin"]) > 0
    process, fresh = baseline.replay_cli(replay_python, tmp_path, content, anchors)
    assert process.returncode == 0, fresh
    assert fresh["integrity"] == fresh["replay"] == "passed"
    assert fresh["expected_binding"] == "matches" and fresh["verification"] == "valid"
    assert fresh["operation"] == "design"
    assert fresh["fresh_checked"]["tier"] == result["design_tier"]
    assert fresh["fresh_checked"]["selected_time"] == result["selected_time"]
    assert fresh["anchors"] == anchors

    for field in ("app_request_digest", "design_digest"):
        process, failure = baseline.replay_cli(replay_python, tmp_path, content, {**anchors, field: "0" * 64})
        assert process.returncode == 2 and failure["error"]["code"] == "wrong_specification_binding", failure
    process, failure = baseline.replay_cli(replay_python, tmp_path, content, {**anchors, "run_id": history["run"]["id"]})
    assert process.returncode == 2 and failure["error"]["code"] == "wrong_scenario_binding", failure
    corrupted = content[:-1] + bytes([content[-1] ^ 1])
    process, failure = baseline.replay_cli(replay_python, tmp_path, corrupted, anchors)
    assert process.returncode == 2 and failure["error"]["code"] == "artifact_mismatch", failure
    artifact_id = result["artifacts"][0]["id"]
    for path in (f"/design-jobs/{job['id']}", f"/artifacts/{artifact_id}", f"/artifacts/{artifact_id}/anchor?download=true"):
        assert client.get(PREFIX + path, headers={"Authorization": "Bearer " + "b" * 40}).status_code == 404
    assert_preserved_history(history)


def test_revised_design_needs_new_approval_and_preserves_honest_no_separation(computed_history, replay_python, tmp_path):
    history, client = computed_history, computed_history["client"]
    original_request = design_request(history)
    # Pair order is reviewed scope; checker result ordering cannot change it.
    original_request["candidate_ids"].reverse()
    original_request["candidate_vectors"].reverse()
    plan = propose(history, original_request, "initial-design")
    _, approval, original, original_bytes, original_anchors = approve_start_and_download(history, plan, "initial")
    revised_request = design_request(history, times=["6/1", "8/1"], allowance="100/1")
    revised = propose(history, revised_request, "coarse-design")
    assert revised["digest"] != plan["digest"]
    assert revised["body"]["request_digest"] != plan["body"]["request_digest"]
    response = client.post(PREFIX + f"/design-plans/{revised['id']}/jobs", json={
        "approval_id": approval["id"], "expected_plan_digest": revised["digest"]},
        headers={"Idempotency-Key": "old-design-approval-cannot-change-grid"})
    assert response.status_code == 403 and response.json()["code"] == "approval_required"
    _, _, result, content, anchors = approve_start_and_download(history, revised, "coarse")
    assert result["design_tier"] == "no_separation_established"
    assert result["verification"] == "valid" and result["replay"] == "passed"
    assert all(row["state"] == "evaluated" and Fraction(row["exact_margin"]) <= 0 for row in result["options"])
    assert anchors["app_request_digest"] != original_anchors["app_request_digest"]
    assert anchors["design_digest"] != original_anchors["design_digest"]
    assert anchors["artifact_sha256"] != original_anchors["artifact_sha256"]
    process, fresh = baseline.replay_cli(replay_python, tmp_path, content, anchors)
    assert process.returncode == 0, fresh
    assert fresh["integrity"] == fresh["replay"] == "passed" and fresh["expected_binding"] == "matches"
    assert fresh["fresh_checked"]["tier"] == "no_separation_established"
    assert client.get(PREFIX + f"/artifacts/{original['artifacts'][0]['id']}").content == original_bytes

    # A caller cannot replace a discovered vector. A separately reviewed
    # numerical request remains numerical rather than acquiring exact scope.
    invalid = deepcopy(original_request)
    invalid["candidate_vectors"][0]["A"] = "1/1"
    response = client.post(PREFIX + f"/runs/{history['run']['id']}/design-proposals", json=invalid,
                           headers={"Idempotency-Key": "invented-candidate"})
    assert response.status_code == 422
    numerical = {**original_request, "requested_tier": "numerical_guidance"}
    response = client.post(PREFIX + f"/runs/{history['run']['id']}/design-proposals", json=numerical,
                           headers={"Idempotency-Key": "reviewed-numerical-tier"})
    assert response.status_code == 201
    assert response.json()["body"]["request"]["requested_tier"] == "numerical_guidance"
    assert_preserved_history(history)


def test_explicit_numerical_design_uses_zero_pair_budget_and_retains_replayable_scope(computed_history, replay_python, tmp_path):
    history = computed_history
    request = {**design_request(history), "requested_tier": "numerical_guidance", "maximum_horizon": "10/1",
               "allow_construction": False, "allow_continuation": False,
               "budget": {"wall_seconds": 60, "fixed_vector_constructions": 0,
                          "pair_verifications": 0, "bundle_bytes": 4 * 1024 * 1024}}
    plan = propose(history, request, "explicit-numerical")
    _, _, result, content, anchors = approve_start_and_download(history, plan, "explicit-numerical")
    assert result["design_tier"] == "numerical_guidance"
    assert result["verification"] == "not_checked" and result["replay"] == "unsupported"
    science = json.loads(base64.b64decode(json.loads(content)["scientific"]["bytes_base64"]))
    assert science["report"]["checked"]["construction_attempts"] == 0
    assert science["report"]["checked"]["pair_verification_passes"] == 0
    process, replay = baseline.replay_cli(replay_python, tmp_path, content, anchors)
    assert process.returncode == 0, replay
    assert replay["integrity"] == "passed" and replay["expected_binding"] == "matches"
    assert replay["verification"] == "not_checked" and replay["replay"] == "unsupported"
    assert_preserved_history(history)


def test_native_design_refuses_prospective_reuse_during_plan_admission(computed_history):
    history = computed_history
    request = design_request(history)
    request["source_artifact_ids"] = [history["result"]["artifacts"][0]["id"]]
    response = history["client"].post(PREFIX + f"/runs/{history['run']['id']}/design-proposals", json=request,
                                     headers={"Idempotency-Key": "unsupported-prospective-reuse"})
    assert response.status_code == 422 and response.json()["code"] == "unsupported_artifact_reuse"
    assert Worker(history["client"].app.state.workflow, settings=history["client"].app.state.settings).tick() == 0
    assert_preserved_history(history)


def test_independent_hero_without_extension_exports_honest_numerical_design(scientific_client, replay_python, tmp_path):
    """Independent evaluator inputs/permissions exercise numerical fallback.

    Future times exceed history, but extension is not approved. Reuse only the
    evaluator's measurement inputs and review, never its candidate oracles.
    """
    client = scientific_client
    packet = json.loads((ROOT / "evaluation/cases/science/hero-v1.json").read_text())
    workspace = post(client, "/workspaces", {"name": "Independent hero input regression"}, "hero-workspace")["id"]
    dataset = post(client, f"/workspaces/{workspace}/datasets", packet["dataset"], "hero-dataset")
    problem = post(client, f"/workspaces/{workspace}/problems", {
        **packet["problem"], "dataset_id": dataset["id"], "dataset_digest": dataset["digest"]}, "hero-problem")
    body = PlanBody(problem_id=problem["id"], problem_digest=problem["digest"], dataset_id=dataset["id"],
        scientific_profile="counterdex.v1", objective={"question": "Challenge the reviewed synthetic interval.",
        "success_criterion": "Retain exact checked evidence or an explicit unresolved outcome."},
        scenarios=[{"id": "baseline", "kind": "baseline", "label": "Independent hero synthetic inputs",
                    "problem_id": problem["id"], "problem_digest": problem["digest"]}]).model_dump(mode="json")
    plan = post(client, f"/workspaces/{workspace}/plans", {
        "expected_current_revision_id": problem["id"], "plan": body}, "hero-plan")
    approval = post(client, f"/plans/{plan['id']}/approvals", {
        "expected_current_revision_id": problem["id"], "expected_plan_digest": plan["digest"],
        "accepted": True}, "hero-approval")
    run = post(client, f"/plans/{plan['id']}/runs", {
        "approval_id": approval["id"], "expected_plan_digest": plan["digest"]}, "hero-run")
    result, baseline_bytes, baseline_anchors, _ = baseline.execute_and_download(client, run)
    finished = client.get(PREFIX + f"/runs/{run['id']}").json()
    evidence = client.get(PREFIX + f"/records/{finished['scenarios'][0]['result_id']}").json()
    history = {"client": client, "workspace": workspace, "dataset": dataset, "problem": problem,
        "approval": approval, "run": run, "result": result, "content": baseline_bytes,
        "anchors": baseline_anchors, "evidence": evidence}
    lower, upper = (Fraction(problem["body"]["target"][side]) for side in ("lower", "upper"))
    pair = sorted(result["candidates"], key=lambda candidate:
                  not lower <= Fraction(candidate["parameter_vector"]["ke"]) <= upper)
    assert len(pair) == 2
    assert lower <= Fraction(pair[0]["parameter_vector"]["ke"]) <= upper
    assert not lower <= Fraction(pair[1]["parameter_vector"]["ke"]) <= upper
    review = packet["design_review"]
    request = {**design_request(history, times=review["feasible_times"], allowance=review["future_hard_allowance"]),
        "candidate_ids": [candidate["id"] for candidate in pair],
        "candidate_vectors": [candidate["parameter_vector"] for candidate in pair],
        "allow_construction": review["allow_construction"], "allow_continuation": review["allow_continuation"],
        "maximum_horizon": review["maximum_horizon"],
        "allowance_origin": {"kind": review["allowance_origin"], "description": review["allowance_description"]}}
    assert request["allow_construction"] is True and request["allow_continuation"] is False
    design = propose(history, request, "hero-design")
    _, _, result, content, anchors = approve_start_and_download(history, design, "hero-design")
    assert result["design_tier"] == "numerical_guidance"
    assert result["verification"] == "not_checked" and result["replay"] == "unsupported"
    assert all(option["exact_margin"] is None for option in result["options"])
    process, fresh = baseline.replay_cli(replay_python, tmp_path, content, anchors)
    assert process.returncode == 0, fresh
    assert fresh["integrity"] == "passed" and fresh["expected_binding"] == "matches"
    assert fresh["verification"] == "not_checked" and fresh["replay"] == "unsupported"
    assert_preserved_history(history)
