"""Actual registered DTO/read/decision boundaries, with computation unavailable."""
import json

from fastapi.testclient import TestClient
import pytest

from bean_api.config import Settings
from bean_api.main import PREFIX, create_app
from bean_api.research_contracts import ResearchEventsPage, ResearchSnapshot


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("BEAN_AI_MODE", "placeholder")
    settings = Settings(database_path=str(tmp_path / "bean.sqlite3"), blob_dir=str(tmp_path / "sources"),
        artifact_dir=str(tmp_path / "artifacts"), auth_tokens={"alice": "a"*40, "bob": "b"*40}, science_adapter="unavailable")
    with TestClient(create_app(settings)) as client:
        client.headers["Authorization"] = "Bearer " + "a"*40
        yield client


def saved(client):
    workspace = client.post(PREFIX + "/workspaces", json={"name": "HTTP research DTO checks"}).json()["id"]
    body = {"objective": "Which meanings and model are missing?", "mode": "controlled"}
    path = PREFIX + f"/workspaces/{workspace}/research-sessions"
    response = client.post(path, json=body, headers={"Idempotency-Key": "create-research"})
    assert response.status_code == 200, response.text
    ResearchSnapshot.model_validate(response.json())
    return workspace, response.json(), path, body


def test_actual_openapi_and_read_only_snapshot_are_typed(client):
    workspace, session, path, body = saved(client)
    spec = client.get("/openapi.json").json()
    assert spec["paths"][path.replace(workspace, "{workspace_id}")]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("/ResearchSnapshot")
    for _ in range(2):
        read = client.get(PREFIX + "/research-sessions/" + session["id"])
        assert read.status_code == 200
        assert "thread" not in read.text.lower()
        ResearchSnapshot.model_validate(read.json())
        ResearchEventsPage.model_validate(client.get(PREFIX + f"/research-sessions/{session['id']}/events").json())
    with client.app.state.workflow.store.read() as conn:
        assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM provider_attempts").fetchone()[0] == 0


def test_empty_cancel_body_and_safe_event_cursor_are_explicit(client):
    _, session, _, _ = saved(client)
    path = PREFIX + "/research-sessions/" + session["id"]
    assert client.post(path + "/cancel", json={"command": {"resume": True}}, headers={"Idempotency-Key": "forged"}).status_code == 422
    assert client.get(path + "/events?after=9999999999999999999999").status_code == 422
    stopped = client.post(path + "/cancel", json={}, headers={"Idempotency-Key": "cancel"})
    assert stopped.status_code == 200 and stopped.json()["state"] == "cancelled"
    client.headers["Authorization"] = "Bearer " + "b"*40
    assert client.get(path).status_code == 404


def test_retry_old_ack_returns_current_snapshot_without_rewriting_accepted_history(client):
    _, session, path, body = saved(client)
    # Deliberate offline compatibility fixture: an older cached mutable snapshot,
    # not altered accepted inputs or fabricated scientific results.
    old = {key: value for key, value in session.items() if key != "session_limits_policy"}
    with client.app.state.workflow.store.transaction() as conn:
        conn.execute("UPDATE operations SET response=? WHERE operation='create:research'", (json.dumps(old),))
    response = client.post(path, json=body, headers={"Idempotency-Key": "create-research"})
    assert response.status_code == 200, response.text
    assert response.json()["id"] == session["id"]
    assert response.json()["session_limits_policy"] == "research-session-limits.v2"
    with client.app.state.workflow.store.read() as conn:
        assert json.loads(conn.execute("SELECT response FROM operations WHERE operation='create:research'").fetchone()[0]) == old
        assert conn.execute("SELECT count(*) FROM research_sessions").fetchone()[0] == 1
