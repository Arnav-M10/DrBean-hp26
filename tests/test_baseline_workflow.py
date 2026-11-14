"""Real ordinary-route baseline acceptance and separate offline CLI replay.

These tests submit synthetic measurements, never fixture candidates or internal
evidence records. The installed engine process replays downloaded bytes without
access to the API/store and does not rerun numerical discovery.
"""
from copy import deepcopy
from fractions import Fraction
import base64
import hashlib
import json
import os
import subprocess

import pytest

from bean_api.main import PREFIX
from bean_api.worker import Worker
import test_scientific_http as scientific_http
from test_scientific_http import ROOT, post, prepare_approved_history

scientific_client = scientific_http.scientific_client


@pytest.fixture
def replay_python():
    executable = os.getenv("BEAN_COUNTERDEX_REPLAY_PYTHON")
    if not executable:
        prepared = ROOT.parent / "counterdex-runtime/bin/python"
        executable = str(prepared) if prepared.is_file() else os.getenv("BEAN_COUNTERDEX_PYTHON")
    if not executable:
        pytest.skip("Prepare an installed Counterdex CPython 3.11 environment for independent CLI replay")
    probe = subprocess.run([executable, "-I", "-m", "counterdex", "capabilities"],
                           capture_output=True, timeout=10, env={"PATH": os.defpath, "LANG": "C.UTF-8"})
    if probe.returncode:
        pytest.skip("The replay interpreter must have the matching Counterdex package installed")
    return executable


def execute_and_download(client, run):
    assert Worker(client.app.state.workflow, settings=client.app.state.settings).tick() == 1
    finished = client.get(PREFIX + f"/runs/{run['id']}").json()
    assert finished["state"] == "completed", finished
    assert len(finished["scenarios"]) == 1
    scenario = finished["scenarios"][0]
    assert scenario["state"] == "completed"
    record = client.get(PREFIX + f"/records/{scenario['result_id']}").json()
    assert record["body"]["run_id"] == run["id"]
    result = record["body"]["result"]
    assert len(result["artifacts"]) == 1
    reference = result["artifacts"][0]
    response = client.get(PREFIX + f"/artifacts/{reference['id']}")
    assert response.status_code == 200
    assert response.headers["content-type"].split(";")[0] == "application/vnd.counterdex.native+json"
    assert len(response.content) == reference["byte_size"]
    assert hashlib.sha256(response.content).hexdigest() == reference["sha256"] == response.headers["X-Artifact-SHA256"]
    anchor_response = client.get(PREFIX + f"/artifacts/{reference['id']}/anchor?download=true")
    assert anchor_response.status_code == 200
    assert "attachment" in anchor_response.headers["content-disposition"]
    anchors = anchor_response.json()
    assert set(anchors) == {"artifact_sha256", "dataset_digest", "problem_digest", "projection_digest",
                            "app_request_digest", "design_digest", "scenario_id", "run_id"}
    assert anchors["artifact_sha256"] == reference["sha256"]
    assert anchors["run_id"] == run["id"] and anchors["scenario_id"] == scenario["scenario_id"]
    assert anchors["projection_digest"] == result["scientific_problem_digest"]
    packet = response.json()
    assert packet["schema_version"] == "counterdex.application-bundle.v1"
    assert packet["operation"] == "investigate" and packet["history"] is None
    assert packet["run_id"] == run["id"]
    native = json.loads(base64.b64decode(packet["scientific"]["bytes_base64"], validate=True))
    assert native["operation"] == "bounded_discovery"
    assert native["search"]["problem_digest"] == anchors["projection_digest"]
    assert native["search"]["attempted_count"] > 0
    assert native["workflow"]["plan_id"] == run["plan_id"]
    assert native["workflow"]["approval_id"] == run["approval_id"]
    assert native["workflow"]["execution_id"] == run["id"]
    return result, response.content, anchors, native


def replay_cli(python, tmp_path, content, anchors):
    packet = tmp_path / "downloaded.native.json"
    anchor = tmp_path / "downloaded.anchors.json"
    packet.write_bytes(content)
    anchor.write_text(json.dumps(anchors))
    process = subprocess.run([python, "-I", "-m", "counterdex", "replay-native", str(packet),
                              "--anchors", str(anchor)], cwd=tmp_path, capture_output=True, timeout=30,
                             env={"PATH": os.defpath, "LANG": "C.UTF-8"})
    return process, json.loads(process.stdout if process.returncode == 0 else process.stderr)


def test_downloaded_baseline_replays_offline_and_rejects_wrong_bytes_or_scope(scientific_client, replay_python, tmp_path):
    client = scientific_client
    workspace, dataset, problem, plan, approval, run, _ = prepare_approved_history(client)
    result, content, anchors, native = execute_and_download(client, run)
    assert result["scientific_outcome"] == "certified_counterexample"
    assert result["verification"] == "valid" and result["replay"] == "passed"
    assert anchors["dataset_digest"] == dataset["digest"]
    assert anchors["problem_digest"] == problem["digest"]
    assert anchors["projection_digest"] not in {problem["digest"], dataset["digest"]}
    assert anchors["app_request_digest"] is None and anchors["design_digest"] is None
    lower, upper = (Fraction(problem["body"]["target"][side]) for side in ("lower", "upper"))
    assert any(Fraction(c["parameter_vector"]["ke"]) < lower or Fraction(c["parameter_vector"]["ke"]) > upper
               for c in result["candidates"] if c["verification"] == "valid")
    assert native["certificate"] is not None
    process, fresh = replay_cli(replay_python, tmp_path, content, anchors)
    assert process.returncode == 0, fresh
    assert fresh["replay"] == fresh["integrity"] == "passed"
    assert fresh["verification"] == "valid" and fresh["expected_binding"] == "matches"
    assert fresh["search_replayed"] is False
    assert fresh["outcome"]["scientific_outcome"] == result["scientific_outcome"]
    assert {c["candidate_id"] for c in fresh["candidate_results"]} == {c["id"] for c in result["candidates"]}

    cases = [(content[:-1] + bytes([content[-1] ^ 1]), anchors, "artifact_mismatch"),
             (content, {**anchors, "problem_digest": "0" * 64}, "wrong_specification_binding"),
             (content, {**anchors, "run_id": "another_run"}, "wrong_scenario_binding")]
    for supplied, expected, code in cases:
        process, failure = replay_cli(replay_python, tmp_path, supplied, expected)
        assert process.returncode == 2, failure
        assert failure["error"]["code"] == code

    artifact_id = result["artifacts"][0]["id"]
    for suffix in ("", "/anchor?download=true"):
        response = client.get(PREFIX + f"/artifacts/{artifact_id}" + suffix,
                              headers={"Authorization": "Bearer " + "b" * 40})
        assert response.status_code == 404
    assert post(client, f"/plans/{plan['id']}/runs", {
        "approval_id": approval["id"], "expected_plan_digest": plan["digest"]}, "retry-baseline")["id"] == run["id"]
    assert Worker(client.app.state.workflow, settings=client.app.state.settings).tick() == 0
    assert client.get(PREFIX + f"/workspaces/{workspace}/provider-attempts").json() == []


def revise_and_approve(client, workspace, dataset, problem, plan, *, concentrations, key):
    body = deepcopy(dataset["body"])
    body.update(parent_id=dataset["id"], change_reason="Explicitly reviewed changed synthetic measurements")
    for row, value in zip(body["rows"], concentrations, strict=True):
        row["concentration"] = value
        row["original_values"] = {"concentration": value}
    revised_dataset = post(client, f"/workspaces/{workspace}/datasets", body, key + "-dataset")
    revised_problem = post(client, f"/workspaces/{workspace}/problems", {
        **problem["body"], "dataset_id": revised_dataset["id"], "dataset_digest": revised_dataset["digest"]}, key + "-problem")
    proposed = deepcopy(plan["body"])
    proposed.update(problem_id=revised_problem["id"], problem_digest=revised_problem["digest"],
                    dataset_id=revised_dataset["id"], parent_plan_id=plan["id"])
    proposed["scenarios"][0].update(problem_id=revised_problem["id"], problem_digest=revised_problem["digest"])
    revised_plan = post(client, f"/workspaces/{workspace}/plans", {
        "expected_current_revision_id": revised_problem["id"], "plan": proposed}, key + "-plan")
    approval = post(client, f"/plans/{revised_plan['id']}/approvals", {
        "expected_current_revision_id": revised_problem["id"], "expected_plan_digest": revised_plan["digest"],
        "accepted": True}, key + "-approval")
    run = post(client, f"/plans/{revised_plan['id']}/runs", {
        "approval_id": approval["id"], "expected_plan_digest": revised_plan["digest"]}, key + "-run")
    return revised_dataset, revised_problem, run


def test_changed_measurement_computes_new_bound_evidence_and_preserves_original(scientific_client, replay_python, tmp_path):
    client = scientific_client
    workspace, dataset, problem, plan, _, run, _ = prepare_approved_history(client)
    original, original_bytes, old_anchor, _ = execute_and_download(client, run)
    concentrations = [row["concentration"] for row in dataset["body"]["rows"]]
    concentrations[0] = "97/20"
    changed_dataset, changed_problem, changed_run = revise_and_approve(
        client, workspace, dataset, problem, plan, concentrations=concentrations, key="changed")
    changed, changed_bytes, new_anchor, native = execute_and_download(client, changed_run)
    # A changed measurement may eliminate the former witness. Require fresh,
    # correctly bound computation, not the original success or candidate pair.
    assert changed["scientific_outcome"] in {"certified_counterexample", "no_counterexample_found", "inconclusive"}
    assert changed_problem["digest"] != problem["digest"]
    assert new_anchor["projection_digest"] != old_anchor["projection_digest"]
    assert new_anchor["artifact_sha256"] != old_anchor["artifact_sha256"]
    packet = json.loads(changed_bytes)
    assert packet["binding"]["dataset"]["body"] == changed_dataset["body"]
    assert native["problem"]["observations"][0]["value"] == "97/20"
    assert client.get(PREFIX + f"/artifacts/{original['artifacts'][0]['id']}").content == original_bytes
    process, fresh = replay_cli(replay_python, tmp_path, changed_bytes, new_anchor)
    assert process.returncode == 0, fresh
    assert fresh["replay"] == changed["replay"]
    assert fresh["outcome"]["scientific_outcome"] == changed["scientific_outcome"]
    assert fresh["integrity"] == "passed" and fresh["expected_binding"] == "matches"
    assert client.get(PREFIX + f"/workspaces/{workspace}/provider-attempts").json() == []


def test_no_compatible_candidate_preserves_search_evidence_without_claiming_proof(scientific_client, replay_python, tmp_path):
    client = scientific_client
    workspace, dataset, problem, plan, _, pending, _ = prepare_approved_history(client)
    # Cancel the first unexecuted control through the public API so the worker
    # dispatches only the deliberately incompatible reviewed measurement set.
    post(client, f"/runs/{pending['id']}/cancel", {}, "cancel-original")
    assert Worker(client.app.state.workflow, settings=client.app.state.settings).tick() == 1
    _, _, run = revise_and_approve(client, workspace, dataset, problem, plan,
        concentrations=["1000/1"] * len(dataset["body"]["rows"]), key="no-candidate")
    result, content, anchors, native = execute_and_download(client, run)
    assert result["scientific_outcome"] == "no_counterexample_found"
    assert result["verification"] == "not_checked" and result["replay"] == "unsupported"
    assert result["candidates"] == [] and native["certificate"] is None
    assert result["reason_code"] == "bounded_search_no_outside_witness"
    process, fresh = replay_cli(replay_python, tmp_path, content, anchors)
    assert process.returncode == 0 and fresh["integrity"] == "passed", fresh
    assert fresh["replay"] == "unsupported" and fresh["verification"] == "not_checked"
    assert fresh["outcome"]["scientific_outcome"] == "no_counterexample_found"
    assert fresh["search_replayed"] is False
