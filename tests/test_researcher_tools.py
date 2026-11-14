"""Researcher tools use actual computed evidence and ordinary authenticated routes."""
from copy import deepcopy
from pathlib import Path
import hashlib
import io
import json
import zipfile

import pytest

from bean_api.main import PREFIX
from bean_api.worker import Worker
import test_baseline_workflow as baseline
import test_scientific_http as science
from test_scientific_http import post, prepare_approved_history

scientific_client = science.scientific_client
replay_python = baseline.replay_python


@pytest.fixture
def computed(scientific_client):
    client = scientific_client
    workspace, dataset, problem, plan, approval, run, _ = prepare_approved_history(client)
    assert Worker(client.app.state.workflow, settings=client.app.state.settings).tick() == 1
    finished = client.get(PREFIX + f"/runs/{run['id']}").json()
    assert finished["state"] == "completed", finished
    result = client.get(PREFIX + f"/records/{finished['scenarios'][0]['result_id']}").json()["body"]["result"]
    assert result["scientific_outcome"] == "certified_counterexample"
    return client, workspace, dataset, problem, plan, run, result


def package(client, report):
    response = client.get(PREFIX + f"/reports/{report['id']}/package")
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert hashlib.sha256(response.content).hexdigest() == response.headers["X-Artifact-SHA256"]
    return response.content


def test_reviewer_zip_contains_exact_native_bytes_and_fresh_replay(computed, replay_python, tmp_path):
    client, workspace, dataset, _, _, run, result = computed
    report = post(client, f"/runs/{run['id']}/reports", {}, "report")
    content = package(client, report)
    assert package(client, report) == content  # stable frozen snapshot
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        assert len(archive.namelist()) == len(set(archive.namelist()))
        assert all(not name.startswith('/') and '..' not in name.split('/') for name in archive.namelist())
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["report_digest"] == report["digest"]
        assert json.loads(archive.read("report.json")) == report
        assert json.loads(archive.read("approvals/1.json"))["id"] == report["body"]["run"]["approval_id"]
        assert json.loads(archive.read("measurements/1.json")) == dataset
        assert b"hard_allowance_mg_L" in archive.read("measurements/1.csv")
        assert b"No witness found does not prove" in archive.read("README.md")
        for reference in manifest["files"]:
            data = archive.read(reference["path"])
            assert len(data) == reference["byte_size"]
            assert hashlib.sha256(data).hexdigest() == reference["sha256"]
        artifact = manifest["native_artifacts"][0]
        native = archive.read(artifact["native_file"])
        anchors = json.loads(archive.read(artifact["anchor_file"]))
        assert native == client.get(PREFIX + f"/artifacts/{result['artifacts'][0]['id']}").content
        process, fresh = baseline.replay_cli(replay_python, tmp_path, native, anchors)
        assert process.returncode == 0, fresh
        assert fresh["integrity"] == fresh["replay"] == "passed"
        assert fresh["expected_binding"] == "matches"
    assert client.get(PREFIX + f"/workspaces/{workspace}/provider-attempts").json() == []
    client.headers["Authorization"] = "Bearer " + "b" * 40
    assert client.get(PREFIX + f"/reports/{report['id']}/package").status_code == 404


def test_comparison_reports_exact_edits_and_typed_outcomes_without_dispatch(computed):
    client, workspace, dataset, problem, original_plan, run, _ = computed
    same = client.get(PREFIX + f"/workspaces/{workspace}/investigations/compare", params={
        "left_run_id": run["id"], "right_run_id": run["id"]}).json()
    assert same["input_changes"] == same["result_changes"] == []
    changed = deepcopy(dataset["body"])
    changed.update(parent_id=dataset["id"], change_reason="Reviewed allowance sensitivity")
    changed["rows"][0]["hard_allowance"] = "1/4"
    new_data = post(client, f"/workspaces/{workspace}/datasets", changed, "changed-data")
    new_problem = post(client, f"/workspaces/{workspace}/problems", {**problem["body"],
        "dataset_id": new_data["id"], "dataset_digest": new_data["digest"],
        "target": {"lower": problem["body"]["domain"]["ke"]["lower"], "upper": problem["body"]["domain"]["ke"]["upper"]}}, "changed-problem")
    body = deepcopy(original_plan["body"])
    body.update(problem_id=new_problem["id"], problem_digest=new_problem["digest"], dataset_id=new_data["id"])
    body["scenarios"][0].update(problem_id=new_problem["id"], problem_digest=new_problem["digest"])
    plan = post(client, f"/workspaces/{workspace}/plans", {"expected_current_revision_id": new_problem["id"], "plan": body}, "new-plan")
    approval = post(client, f"/plans/{plan['id']}/approvals", {"expected_plan_digest": plan["digest"],
        "expected_current_revision_id": new_problem["id"], "accepted": True}, "new-approval")
    second = post(client, f"/plans/{plan['id']}/runs", {"approval_id": approval["id"], "expected_plan_digest": plan["digest"]}, "new-run")
    # The right run is still queued: comparison must expose missing results honestly.
    path = PREFIX + f"/workspaces/{workspace}/investigations/compare"
    params = {"left_run_id": run["id"], "right_run_id": second["id"]}
    queued = client.get(path, params=params).json()
    assert queued["right"]["results"]["baseline"]["state"] == "not_started"
    assert queued["same_experiment_and_model"]
    changes = {item["path"]: item for item in queued["input_changes"]}
    assert changes["/scenarios/baseline/dataset/rows/" + dataset["body"]["rows"][0]["id"] + "/hard_allowance"]["after"] == "1/4"
    assert any("/problem/target/" in path for path in changes)
    assert Worker(client.app.state.workflow, settings=client.app.state.settings).tick() == 1
    compared = client.get(path, params=params).json()
    assert compared["right"]["results"]["baseline"]["result"]["scientific_outcome"] == "no_counterexample_found"
    assert any(item["path"].endswith("/scientific_outcome") for item in compared["result_changes"])
    assert client.app.state.workflow.queued_jobs() == []
    other = post(client, "/workspaces", {"name": "Other workspace"}, "other")
    assert client.get(PREFIX + f"/workspaces/{other['id']}/investigations/compare", params=params).status_code == 404


def test_templates_are_durable_defaults_and_grant_no_authority(computed):
    client, workspace, dataset, problem, _, _, _ = computed
    payload = {"name": "Repeated experiment", "problem_id": problem["id"], "problem_digest": problem["digest"],
               "default_hard_allowance": "1/5", "allowance_origin": "Instrument bound to review for each experiment", "methods": "Reconfirm calibration"}
    path = f"/workspaces/{workspace}/experiment-templates"
    template = post(client, path, payload, "template")
    assert post(client, path, payload, "template")["id"] == template["id"]
    preview = client.get(PREFIX + f"/experiment-templates/{template['id']}/draft").json()
    assert preview["requires_review"] and preview["defaults"]["requires_review"]
    assert not {"dataset_id", "dataset_digest", "rows", "approval_id"}.intersection(preview["defaults"]["problem_inputs"])
    assert preview["defaults"]["problem_inputs"]["domain"] == problem["body"]["domain"]
    assert len(client.get(PREFIX + path).json()) == 1
    assert client.get(PREFIX + f"/workspaces/{workspace}").json()["current_dataset_id"] == dataset["id"]
    rejected = client.post(PREFIX + path, json={**payload, "problem_digest": "0" * 64}, headers={"Idempotency-Key": "wrong-template"})
    assert rejected.status_code == 422
    assert client.post(PREFIX + path, json={**payload, "default_hard_allowance": "-1/1"}, headers={"Idempotency-Key": "bad-bound"}).status_code == 422
    assert client.post(PREFIX + f"/plans/{template['id']}/runs", json={"approval_id": template["id"], "expected_plan_digest": template["digest"]},
                       headers={"Idempotency-Key": "template-cannot-run"}).status_code == 404
    client.headers["Authorization"] = "Bearer " + "b" * 40
    assert client.get(PREFIX + path).status_code == 404
    assert client.get(PREFIX + f"/experiment-templates/{template['id']}/draft").status_code == 404


def test_package_fails_closed_for_missing_bytes_and_size_cap(computed, monkeypatch):
    client, _, _, _, _, run, result = computed
    report = post(client, f"/runs/{run['id']}/reports", {}, "report")
    monkeypatch.setattr("bean_api.reviewer_package.MAX_PACKAGE_BYTES", 100)
    assert client.get(PREFIX + f"/reports/{report['id']}/package").status_code == 413
    monkeypatch.setattr("bean_api.reviewer_package.MAX_PACKAGE_BYTES", 12 * 1024 * 1024)
    record = client.app.state.workflow.get("alice", result["artifacts"][0]["id"], "native_artifact")
    path = Path(client.app.state.settings.artifact_dir) / record["body"]["blob_key"]
    path.write_bytes(b"corrupt")
    response = client.get(PREFIX + f"/reports/{report['id']}/package")
    assert response.status_code == 409 and response.json()["code"] == "artifact_integrity_failed"
    path.unlink()
    assert client.get(PREFIX + f"/reports/{report['id']}/package").status_code == 409
