"""Narrow ordinary API/worker gate; no injected model or fabricated science."""
from bean_api.main import PREFIX
from bean_api.providers import ProviderFailure
from bean_api.research_controlled import ControlledResearchModel
from bean_api.worker import Worker
from test_research_native_authority import assert_native_replay, reviewed_inputs
from test_scientific_http import post
import test_scientific_http as scientific_http
from test_baseline_workflow import replay_python as replay_fixture
import pytest

scientific_client = scientific_http.scientific_client
replay_python = replay_fixture


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


@pytest.mark.parametrize("error,code", [
    (ProviderFailure("controlled_post_science_model_failure"), "controlled_post_science_model_failure"),
    (RuntimeError("controlled unexpected model exception"), "research_runtime_failure"),
])
def test_model_failure_after_real_science_retains_downloadable_evidence(
    scientific_client, replay_python, tmp_path, monkeypatch, error, code,
):
    """Explicit fault injection, separate from ordinary default-factory acceptance."""
    from langchain_core.messages import ToolMessage

    class FailAfterEvidence(ControlledResearchModel):
        def _generate(self, messages, **kwargs):
            if any(isinstance(message, ToolMessage) and message.name == "read_research_evidence" for message in messages):
                raise error
            return super()._generate(messages, **kwargs)

    monkeypatch.setattr("bean_api.research_controlled.build_controlled_research_model", FailAfterEvidence)
    client = scientific_client
    workspace, _, problem = reviewed_inputs(client)
    session = post(client, f"/workspaces/{workspace}/research-sessions", {
        "objective": "Preserve actual mathematical evidence when later explanation fails",
        "problem_id": problem["id"], "expected_problem_digest": problem["digest"], "mode": "controlled",
    }, "failure-session")
    path = PREFIX + "/research-sessions/" + session["id"]
    post(client, f"/research-sessions/{session['id']}/advance", {"expected_revision": session["revision"]}, "failure-advance")
    worker = Worker(client.app.state.workflow, settings=client.app.state.settings)
    worker.tick()
    waiting = client.get(path).json()
    assert waiting["state"] == "waiting_review", waiting
    post(client, f"/research-sessions/{session['id']}/decisions", {
        "expected_revision": waiting["revision"], "pending_review_id": waiting["pending_review"]["id"],
        "expected_review_digest": waiting["pending_review_digest"], "decision": "approve", "accepted": True,
    }, "failure-approve")
    for _ in range(4):
        worker.tick()
        current = client.get(path).json()
        if current["state"] == "failed":
            break
    assert current["state"] == "failed", current
    assert current["action"]["error_code"] == code
    assert len(current["children"]) == 1 and current["children"][0]["state"] == "completed"
    child = current["children"][0]
    evidence = client.get(PREFIX + "/records/" + child["scenarios"][0]["result_id"]).json()
    assert evidence["body"]["result"]["problem_id"] == problem["id"]
    assert_native_replay(client, evidence, replay_python, tmp_path / "post-model-failure")
    assert worker.tick() == 0
    assert client.get(path).json()["children"] == current["children"]
    next_session = post(client, f"/workspaces/{workspace}/research-sessions", {
        "objective": "The worker remains available to a separately reviewed investigation",
        "problem_id": problem["id"], "expected_problem_digest": problem["digest"], "mode": "controlled",
    }, "after-failure-session")
    post(client, f"/research-sessions/{next_session['id']}/advance", {"expected_revision": next_session["revision"]}, "after-failure-advance")
    assert worker.tick() == 1
    assert client.get(PREFIX + "/research-sessions/" + next_session["id"]).json()["state"] == "waiting_review"
