"""HTTP-to-storage-to-process tests; all inputs synthetic, no live provider."""

import hashlib
import json
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from bean_api.config import Settings
from bean_api.main import create_app, PREFIX
from bean_api.worker import Worker

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    settings = Settings(database_path=str(tmp_path / "db.sqlite3"), blob_dir=str(tmp_path / "sources"),
                        auth_tokens={"alice": "a" * 40, "bob": "b" * 40}, science_adapter="unavailable", artifact_dir=str(tmp_path / "artifacts"))
    with TestClient(create_app(settings)) as active:
        active.headers["Authorization"] = "Bearer " + "a" * 40
        yield active


def post(client, path, body, key):
    response = client.post(PREFIX + path, json=body, headers={"Idempotency-Key": key})
    assert response.status_code in {200, 201, 202}, response.text
    return response.json()


def prepared(client):
    fixture = json.loads((ROOT / "shared/contracts/DB-SC-1/fixtures/synthetic-workflow.json").read_text())
    workspace = post(client, "/workspaces", {"name": "Synthetic API integration"}, "workspace")
    w = workspace["id"]
    dataset = post(client, f"/workspaces/{w}/datasets", fixture["dataset"], "dataset")
    problem = post(client, f"/workspaces/{w}/problems", {
        **fixture["problem"], "dataset_id": dataset["id"], "dataset_digest": dataset["digest"]}, "problem")
    plan_body = {**fixture["plan"], "dataset_id": dataset["id"], "problem_id": problem["id"], "problem_digest": problem["digest"],
                 "scenarios": [{**fixture["plan"]["scenarios"][0], "problem_id": problem["id"], "problem_digest": problem["digest"]}]}
    plan = post(client, f"/workspaces/{w}/plans", {"expected_current_revision_id": problem["id"], "plan": plan_body}, "plan")
    approval = post(client, f"/plans/{plan['id']}/approvals", {
        "expected_plan_digest": plan["digest"], "expected_current_revision_id": problem["id"], "accepted": True}, "approval")
    return w, dataset, problem, plan, approval


def test_manual_http_approval_worker_and_exact_export(client):
    w, dataset, problem, plan, approval = prepared(client)
    body = {"approval_id": approval["id"], "expected_plan_digest": plan["digest"]}
    run = post(client, f"/plans/{plan['id']}/runs", body, "run")
    assert post(client, f"/plans/{plan['id']}/runs", body, "different-retry-key")["id"] == run["id"]
    assert Worker(client.app.state.workflow, adapter=client.app.state.adapter, settings=client.app.state.settings).tick() == 1
    finished = client.get(PREFIX + f"/runs/{run['id']}").json()
    assert finished["state"] == "completed"
    evidence = client.get(PREFIX + f"/records/{finished['scenarios'][0]['result_id']}").json()
    assert evidence["body"]["result"]["scientific_outcome"] == "unsupported"
    assert evidence["body"]["result"]["verification"] == "unsupported"
    report = post(client, f"/runs/{run['id']}/reports", {}, "export")
    download = client.get(PREFIX + f"/reports/{report['id']}/download")
    assert hashlib.sha256(download.content).hexdigest() == download.headers["X-Artifact-SHA256"]
    assert download.json()["body"]["dataset"]["id"] == dataset["id"]
    assert client.get(PREFIX + f"/workspaces/{w}/activity").status_code == 200
    assert client.get(PREFIX + f"/workspaces/{w}/provider-attempts").json() == []


def test_authorization_origin_and_strict_wire_parser(client):
    w, _, _, plan, approval = prepared(client)
    assert client.get(PREFIX + f"/workspaces/{w}", headers={"Authorization": "Bearer " + "b" * 40}).status_code == 404
    assert client.get(PREFIX + f"/workspaces/{w}", headers={"Authorization": "Bearer invalid"}).status_code == 401
    assert client.get(PREFIX + f"/workspaces/{w}", headers={"Origin": "https://untrusted.example"}).status_code == 403
    for raw in [b'{"value":"0.05","value":"0.5"}', b'{"value":0.05}', b'{"value":"\\ud800"}']:
        response = client.post(PREFIX + "/exact/decimal", content=raw, headers={"Content-Type": "application/json"})
        assert response.status_code == 422
        assert response.json()["code"] == "invalid_json"
        assert response.json()["request_id"] == response.headers["X-Request-ID"]
    assert post(client, "/exact/decimal", {"value": "0.05"}, "decimal")["exact"] == "1/20"
    numeric_approval = client.post(PREFIX + f"/plans/{plan['id']}/approvals", json={
        "expected_plan_digest": plan["digest"], "expected_current_revision_id": "anything", "accepted": 1},
        headers={"Idempotency-Key": "attack"})
    assert numeric_approval.status_code == 422


def test_upload_is_private_exact_and_does_not_call_provider(client):
    workspace = post(client, "/workspaces", {"name": "Image intake"}, "workspace")
    raw = (ROOT / "fixtures/intake/clean.png").read_bytes()
    uploaded = client.post(PREFIX + f"/workspaces/{workspace['id']}/source-assets?origin=synthetic&retention=retain",
        content=raw, headers={"Content-Type": "image/png", "Idempotency-Key": "upload"})
    assert uploaded.status_code == 201, uploaded.text
    source = uploaded.json()
    assert "blob_key" not in source["body"]
    assert "blob_key" not in client.get(PREFIX + f"/records/{source['id']}").json()["body"]
    downloaded = client.get(PREFIX + f"/source-assets/{source['id']}/content")
    assert downloaded.content == raw
    assert client.get(PREFIX + f"/source-assets/{source['id']}/content", headers={"Authorization": "Bearer " + "b" * 40}).status_code == 404
    assert client.get(PREFIX + f"/workspaces/{workspace['id']}/provider-attempts").json() == []


def test_cancel_queued_job_waits_for_worker_acknowledgement(client):
    _, _, _, plan, approval = prepared(client)
    run = post(client, f"/plans/{plan['id']}/runs", {"approval_id": approval["id"], "expected_plan_digest": plan["digest"]}, "run")
    cancelled = post(client, f"/runs/{run['id']}/cancel", {}, "cancel")
    assert cancelled["state"] == "cancel_requested"
    Worker(client.app.state.workflow, adapter=client.app.state.adapter, settings=client.app.state.settings).tick()
    assert client.get(PREFIX + f"/runs/{run['id']}").json()["state"] == "cancelled"


def test_manual_conversation_yes_never_approves(client):
    workspace = post(client, "/workspaces", {"name": "Conversation"}, "workspace")
    response = post(client, f"/workspaces/{workspace['id']}/assistant-turns", {
        "operation": "interpret_design", "client_operation_id": "turn1", "expected_conversation_revision": 0,
        "text": "yes, go ahead"}, "turn1")
    assert response
    with client.app.state.workflow.store.read() as conn:
        assert conn.execute("SELECT count(*) FROM approvals").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0


def test_capabilities_do_not_claim_live_qualification(client):
    response = client.get(PREFIX + "/capabilities", headers={"Authorization": ""})
    assert response.status_code == 200
    data = response.json()
    assert data["gemini"]["verified_in_environment"] is False
    assert data["science"]["implemented"] is False
    assert data["deepagents"]["verified_in_environment"] is False


def test_openapi_exposes_flat_design_request(client):
    schema = client.get("/openapi.json").json()
    assert schema["components"]["securitySchemes"]["BearerToken"] == {"type": "http", "scheme": "bearer"}
    assert schema["components"]["securitySchemes"]["BrowserSession"] == {"type": "apiKey", "in": "cookie", "name": "__Host-bean_session"}
    assert schema["paths"][PREFIX + "/workspaces"]["get"]["security"] == [{"BearerToken": []}, {"BrowserSession": []}]
    body = schema["paths"][PREFIX + "/runs/{run_id}/design-proposals"]["post"]["requestBody"]
    assert body["content"]["application/json"]["schema"]["$ref"].endswith("DesignRequestBody")
