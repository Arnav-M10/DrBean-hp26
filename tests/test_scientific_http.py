"""Authenticated real-science boundary tests; no discovery or model simulation claims.

The design control seeds explicitly named regression candidate records through
the internal workflow. It tests new fixed-pair construction/check/replay, never
pretends those vectors came from the unavailable baseline producer.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket

from fastapi.testclient import TestClient
import pytest

from bean_api.artifacts import ArtifactService
from bean_api.config import Settings
from bean_api.contracts import PlanBody
from bean_api.main import PREFIX, create_app
from bean_api.worker import Worker

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def scientific_client(tmp_path, monkeypatch):
    executable = os.getenv("BEAN_COUNTERDEX_PYTHON") or shutil.which("python3.11")
    prepared = ROOT.parent / ".python/cpython-3.11-linux-x86_64-gnu/bin/python3.11"
    if executable is None and prepared.is_file():
        executable = str(prepared)
    if executable is None:
        pytest.skip("Prepared CPython 3.11 required for real Counterdex HTTP controls")

    def forbidden_connect(self, address):
        raise AssertionError("The local HTTP harness must not dispatch a network request")

    monkeypatch.setattr(socket.socket, "connect", forbidden_connect)
    settings = Settings(database_path=str(tmp_path / "science.sqlite3"), blob_dir=str(tmp_path / "sources"),
                        artifact_dir=str(tmp_path / "artifacts"), counterdex_python=executable,
                        auth_tokens={"alice": "a" * 40, "bob": "b" * 40})
    with TestClient(create_app(settings)) as client:
        client.headers["Authorization"] = "Bearer " + "a" * 40
        capabilities = client.get(PREFIX + "/capabilities").json()
        assert capabilities["science"]["available"], capabilities
        assert capabilities["ai_mode"] == "disabled_placeholder"
        yield client


def post(client, path, body, key):
    response = client.post(PREFIX + path, json=body, headers={"Idempotency-Key": key})
    assert response.status_code in {200, 201, 202}, response.text
    return response.json()


def prepare_approved_history(client):
    fixture = json.loads((ROOT / "packages/groundwork_adapter/fixtures/checked_success.request.json").read_text())
    p = fixture["problem"]
    workspace = post(client, "/workspaces", {"name": "Explicit synthetic scientific control"}, "workspace")["id"]
    dataset = post(client, f"/workspaces/{workspace}/datasets", {
        "experiment_id": "synthetic-http-control", "time_origin": p["time_origin"], "origin": "synthetic",
        "change_reason": "Regression inputs; these observations are not actual measurements",
        "rows": [{"id": row["id"], "time": row["time"], "concentration": row["value"],
                  "hard_allowance": row["allowance"], "included": row["included"], "notes": row["notes"]}
                 for row in p["observations"]]}, "dataset")
    problem = post(client, f"/workspaces/{workspace}/problems", {
        "dataset_id": dataset["id"], "dataset_digest": dataset["digest"],
        "domain": {name: {"lower": pair[0], "upper": pair[1]} for name, pair in p["domain"].items()},
        "target": {"lower": p["claim"]["interval"][0], "upper": p["claim"]["interval"][1]}}, "problem")
    body = PlanBody(problem_id=problem["id"], problem_digest=problem["digest"], dataset_id=dataset["id"],
                    scientific_profile="counterdex.v1", objective={
                        "question": "Can the reviewed synthetic bounds exclude the claimed parameter interval?",
                        "success_criterion": "Retain honest checked evidence or explicit unavailable status."},
                    scenarios=[{"id": "baseline", "kind": "baseline", "label": "Synthetic baseline control",
                                "problem_id": problem["id"], "problem_digest": problem["digest"]}]).model_dump(mode="json")
    plan = post(client, f"/workspaces/{workspace}/plans", {
        "expected_current_revision_id": problem["id"], "plan": body}, "plan")
    approval = post(client, f"/plans/{plan['id']}/approvals", {
        "expected_current_revision_id": problem["id"], "expected_plan_digest": plan["digest"], "accepted": True}, "approval")
    run = post(client, f"/plans/{plan['id']}/runs", {
        "approval_id": approval["id"], "expected_plan_digest": plan["digest"]}, "run")
    return workspace, dataset, problem, plan, approval, run, fixture


def test_ordinary_http_baseline_is_honestly_blocked_without_a_producer(scientific_client):
    client = scientific_client
    workspace, dataset, problem, plan, approval, run, _ = prepare_approved_history(client)
    assert Worker(client.app.state.workflow, settings=client.app.state.settings).tick() == 1
    finished = client.get(PREFIX + f"/runs/{run['id']}").json()
    assert finished["state"] == "completed"
    evidence = client.get(PREFIX + f"/records/{finished['scenarios'][0]['result_id']}").json()["body"]["result"]
    assert evidence["scientific_outcome"] == evidence["verification"] == evidence["replay"] == "unsupported"
    assert evidence["reason_code"] == "baseline_producer_unavailable"
    assert evidence["candidates"] == evidence["artifacts"] == []
    assert evidence["problem_digest"] == problem["digest"]
    assert evidence["scientific_problem_digest"] not in {problem["digest"], dataset["digest"]}
    assert post(client, f"/plans/{plan['id']}/runs", {
        "approval_id": approval["id"], "expected_plan_digest": plan["digest"]}, "retry")["id"] == run["id"]
    assert Worker(client.app.state.workflow, settings=client.app.state.settings).tick() == 0
    assert client.get(PREFIX + f"/workspaces/{workspace}/provider-attempts").json() == []


def test_normal_counterdex_http_requires_reviewed_scientific_profile(scientific_client):
    client = scientific_client
    workspace, _, problem, plan, _, run, fixture = prepare_approved_history(client)
    legacy_plan = {key: value for key, value in plan["body"].items() if key not in {"scientific_profile", "objective"}}
    candidates = fixture["design"]["candidates"]
    legacy_design = {"historical_run_id": run["id"], "scenario_id": "baseline", "problem_id": problem["id"],
        "problem_digest": problem["digest"], "candidate_ids": [c["id"] for c in candidates],
        "candidate_vectors": [c["parameters"] for c in candidates], "feasible_times": ["8/1"], "future_hard_allowance": "1/5"}
    for profile in ({}, {"scientific_profile": None}):
        response = client.post(PREFIX + f"/workspaces/{workspace}/plans", json={
            "expected_current_revision_id": problem["id"], "plan": {**legacy_plan, **profile}},
            headers={"Idempotency-Key": "missing-profile"})
        assert response.status_code == 422
        assert response.json()["code"] == "scientific_profile_required"
        assert response.json()["field_paths"] == ["plan.scientific_profile"]
        response = client.post(PREFIX + f"/runs/{run['id']}/design-proposals", json={**legacy_design, **profile},
                               headers={"Idempotency-Key": "missing-design-profile"})
        assert response.status_code == 422
        assert response.json()["code"] == "scientific_profile_required"
        assert response.json()["field_paths"] == ["scientific_profile"]
    assert client.app.state.workflow.list_records("alice", workspace, "design_plan") == []


def test_explicit_seed_pair_real_design_download_and_independent_replay(scientific_client):
    client = scientific_client
    workspace, dataset, problem, _, _, historical, fixture = prepare_approved_history(client)
    workflow = client.app.state.workflow
    candidates = fixture["design"]["candidates"]
    # Internal control setup only: no public route can fabricate these records.
    workflow.mark_running("alice", historical["id"], "explicit-regression-seed")
    workflow.reserve_scenario("alice", historical["id"], "baseline")
    workflow.complete_scenario("alice", historical["id"], "baseline", {
        "scientific_outcome": "numerical_candidate", "verification": "not_checked", "expected_binding": "matches",
        "replay": "not_run", "reason_code": "explicit_regression_seed_not_discovery",
        "problem_id": problem["id"], "problem_digest": problem["digest"], "artifacts": [],
        "candidates": [{"id": c["id"], "parameter_vector": c["parameters"],
                        "problem_id": problem["id"], "problem_digest": problem["digest"]} for c in candidates]})
    workflow.finish_run("alice", historical["id"])
    request = {"historical_run_id": historical["id"], "scenario_id": "baseline",
        "problem_id": problem["id"], "problem_digest": problem["digest"],
        "candidate_ids": [c["id"] for c in candidates], "candidate_vectors": [c["parameters"] for c in candidates],
        "feasible_times": ["8/1", "6/1"], "future_hard_allowance": "1/5",
        "scientific_profile": "counterdex.v1", "requested_tier": "checked_pair_separation",
        "allowance_origin": {"kind": "hypothetical", "description": "Explicit prospective synthetic hard bound"},
        "maximum_horizon": "8/1", "allow_construction": True, "allow_continuation": True}
    plan = post(client, f"/runs/{historical['id']}/design-proposals", request, "design")
    approval = post(client, f"/design-plans/{plan['id']}/approvals", {
        "expected_plan_digest": plan["digest"], "expected_current_revision_id": problem["id"], "accepted": True}, "design-approval")
    start = {"approval_id": approval["id"], "expected_plan_digest": plan["digest"]}
    job = post(client, f"/design-plans/{plan['id']}/jobs", start, "design-start")
    assert Worker(workflow, settings=client.app.state.settings).tick() == 1
    finished = client.get(PREFIX + f"/design-jobs/{job['id']}").json()
    assert finished["state"] == "completed", finished
    result = client.get(PREFIX + f"/records/{finished['result_id']}").json()["body"]
    assert result["design_tier"] == "checked_pair_separation"
    assert result["verification"] == "valid" and result["replay"] == "passed"
    assert [option["time"] for option in result["options"]] == request["feasible_times"]
    reference = result["artifacts"][0]
    downloaded = client.get(PREFIX + f"/artifacts/{reference['id']}")
    assert downloaded.status_code == 200
    assert len(downloaded.content) == reference["byte_size"]
    assert hashlib.sha256(downloaded.content).hexdigest() == reference["sha256"] == downloaded.headers["X-Artifact-SHA256"]
    assert downloaded.json()["schema_version"] == "groundwork.suggestion-bundle.v1"
    assert downloaded.json()["problem"]["dataset_kind"] == "hypothetical"
    assert "synthetic" in downloaded.json()["problem"]["provenance"]
    anchor = client.get(PREFIX + f"/artifacts/{reference['id']}/anchor").json()["anchor"]
    assert anchor["application_problem_digest"] == problem["digest"]
    assert anchor["application_dataset_digest"] == dataset["digest"]
    assert anchor["scientific_problem_digest"] == result["scientific_problem_digest"]
    assert anchor["scientific_design_digest"] == result["scientific_design_digest"]
    assert anchor["native_suggestion_digest"] == result["native_suggestion_digest"]
    assert anchor["scientific_problem_digest"] != problem["digest"]
    adapter = client.app.state.adapter
    expected = {"expected_problem_digest": anchor["scientific_problem_digest"],
                "expected_suggestion_digest": anchor["native_suggestion_digest"]}
    assert adapter.replay(downloaded.content, **expected)["replay"] == "passed"
    wrong = adapter.replay(downloaded.content, **{**expected, "expected_problem_digest": "0" * 64})
    assert wrong["worker_error"] == "wrong_specification_binding"
    wrong = adapter.replay(downloaded.content, **{**expected, "expected_suggestion_digest": "0" * 64})
    assert wrong["worker_error"] == "artifact_mismatch"
    changed_byte = downloaded.content[:-1] + bytes([downloaded.content[-1] ^ 1])
    assert "worker_error" in adapter.replay(changed_byte, **expected)
    assert client.get(PREFIX + f"/artifacts/{reference['id']}", headers={"Authorization": "Bearer " + "b" * 40}).status_code == 404
    assert "blob_key" not in client.get(PREFIX + f"/records/{reference['id']}").json()["body"]
    assert post(client, f"/design-plans/{plan['id']}/jobs", start, "design-retry")["id"] == job["id"]
    assert Worker(workflow, settings=client.app.state.settings).tick() == 0
    assert client.get(PREFIX + f"/workspaces/{workspace}/provider-attempts").json() == []

    # Exercise retained source evidence through the worker's full historical
    # payload as well. This remains explicit internal seeding, not discovery.
    bundle = downloaded.json()
    pair_digest = bundle["report"]["checked"]["pair_digest"]
    pair = next(item for item in bundle["artifacts"] if item["digest"] == pair_digest)
    packet = ArtifactService(workflow, client.app.state.settings.artifact_dir).publish(
        "alice", workspace, base64.b64decode(pair["content"], validate=True), media_type="application/json",
        anchor=anchor, key="explicit-reuse-control-packet")
    packet_ref = {"id": packet["id"], **{key: packet["body"][key] for key in ("sha256", "byte_size", "media_type")}}
    old_plan = workflow.get("alice", historical["plan_id"], "plan")
    reuse_history_plan = post(client, f"/workspaces/{workspace}/plans", {
        "expected_current_revision_id": problem["id"],
        "plan": {**old_plan["body"], "parent_plan_id": old_plan["id"]}}, "reuse-history-plan")
    reuse_history_approval = post(client, f"/plans/{reuse_history_plan['id']}/approvals", {
        "expected_current_revision_id": problem["id"], "expected_plan_digest": reuse_history_plan["digest"],
        "accepted": True}, "reuse-history-approval")
    reuse_history = post(client, f"/plans/{reuse_history_plan['id']}/runs", {
        "approval_id": reuse_history_approval["id"], "expected_plan_digest": reuse_history_plan["digest"]}, "reuse-history")
    workflow.mark_running("alice", reuse_history["id"], "explicit-regression-seed")
    workflow.reserve_scenario("alice", reuse_history["id"], "baseline")
    workflow.complete_scenario("alice", reuse_history["id"], "baseline", {
        "scientific_outcome": "numerical_candidate", "verification": "not_checked", "expected_binding": "matches",
        "replay": "not_run", "reason_code": "explicit_regression_seed_not_discovery",
        "problem_id": problem["id"], "problem_digest": problem["digest"], "artifacts": [packet_ref],
        "candidates": [{"id": c["id"], "parameter_vector": c["parameters"], "artifact_ids": [packet["id"]],
                        "problem_id": problem["id"], "problem_digest": problem["digest"]} for c in candidates]})
    workflow.finish_run("alice", reuse_history["id"])
    reuse_request = {**request, "historical_run_id": reuse_history["id"], "source_artifact_ids": [packet["id"]],
                     "allow_construction": False, "allow_continuation": False,
                     "budget": {"fixed_vector_constructions": 0}}
    reuse_plan = post(client, f"/runs/{reuse_history['id']}/design-proposals", reuse_request, "reuse-design")
    reuse_approval = post(client, f"/design-plans/{reuse_plan['id']}/approvals", {
        "expected_plan_digest": reuse_plan["digest"], "expected_current_revision_id": problem["id"],
        "accepted": True}, "reuse-design-approval")
    reuse_job = post(client, f"/design-plans/{reuse_plan['id']}/jobs", {
        "approval_id": reuse_approval["id"], "expected_plan_digest": reuse_plan["digest"]}, "reuse-design-start")
    assert Worker(workflow, settings=client.app.state.settings).tick() == 1
    reused = client.get(PREFIX + f"/design-jobs/{reuse_job['id']}").json()
    assert reused["state"] == "completed", reused
    reused_result = client.get(PREFIX + f"/records/{reused['result_id']}").json()["body"]
    assert reused_result["design_tier"] == "checked_pair_separation"
    reused_bundle = client.get(PREFIX + f"/artifacts/{reused_result['artifacts'][0]['id']}").json()
    assert reused_bundle["report"]["checked"]["construction_attempts"] == 0
    assert reused_bundle["report"]["checked"]["pair_verification_passes"] == 1
    assert {c["source_artifact_digest"] for c in reused_bundle["design"]["candidates"]} == {pair_digest}
    assert client.get(PREFIX + f"/workspaces/{workspace}/provider-attempts").json() == []
