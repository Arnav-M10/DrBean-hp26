"""Narrow ordinary API/worker gate; no injected model or fabricated science."""
from bean_api.main import PREFIX
from bean_api.worker import Worker
from test_research_native_authority import reviewed_inputs
from test_scientific_http import post

scientific_client = __import__("test_scientific_http").scientific_client


def test_ordinary_worker_reaches_canonical_investigation_review(scientific_client):
    client = scientific_client
    workspace, _, problem = reviewed_inputs(client)
    session = post(client, f"/workspaces/{workspace}/research-sessions", {
        "objective": "Does the reviewed target range survive these measurements?",
        "problem_id": problem["id"], "expected_problem_digest": problem["digest"],
        "mode": "controlled",
    }, "ordinary-research")
    path = PREFIX + "/research-sessions/" + session["id"]
    response = client.post(path + "/advance", json={"expected_revision": session["revision"]},
        headers={"Idempotency-Key": "ordinary-advance"})
    assert response.status_code == 200, response.text
    worker = Worker(client.app.state.workflow, settings=client.app.state.settings)
    assert worker.tick() == 1
    current = client.get(path).json()
    assert current["state"] == "waiting_review", current
    assert current["plan"] and current["plan"]["body"]["steps"], current
    review = current["pending_review"]
    assert review["kind"] == "plan", review
    assert review["body"]["problem_id"] == problem["id"]
    assert review["body"]["problem_digest"] == problem["digest"]
    with client.app.state.workflow.store.read() as conn:
        assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM provider_attempts").fetchone()[0] == 0
