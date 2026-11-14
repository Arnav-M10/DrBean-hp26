"""Independent sprint probe (C): ACC-05 interruption recovery without duplicate science.

Lane: real-science (controlled model policy, zero provider requests, actual
Counterdex). The worker process "dies" right after the approved child is
dispatched (an uncaught BaseException, like SIGKILL, so no runner cleanup
runs). Recovery then uses only supported mechanisms: the worker's --recover
step, the user's explicit reconcile request and fresh Worker objects that
reopen the disk checkpoint. Pass: the same action completes, with exactly one
scientific child and one reservation, and a duplicate reconcile changes nothing.
"""
import pytest

from bean_api.main import PREFIX
from bean_api.research import ResearchService
import test_research_controlled_application as controlled
from test_research_controlled_application import create_session, snapshot, tick
from test_scientific_http import post

scientific_client = controlled.scientific_client


class WorkerKilled(BaseException):
    """Not an Exception: nothing in the runner may catch and tidy it, as with SIGKILL."""


def test_acc05_worker_loss_after_child_dispatch_recovers_one_child(scientific_client, monkeypatch):
    client = scientific_client
    session, _, _ = create_session(client)
    assert tick(client) == 1
    waiting = snapshot(client, session["id"])
    assert waiting["state"] == "waiting_review" and waiting["pending_review"]["kind"] == "plan"
    post(client, f"/research-sessions/{session['id']}/decisions", {
        "expected_revision": waiting["revision"], "pending_review_id": waiting["pending_review"]["id"],
        "expected_review_digest": waiting["pending_review_digest"], "decision": "approve", "accepted": True}, "approve")

    original = ResearchService.release
    killed = []

    def die_once(self, context, state, **kwargs):
        if state == "waiting_child" and not killed:
            killed.append(kwargs.get("waiting_job_id"))
            raise WorkerKilled()
        return original(self, context, state, **kwargs)
    monkeypatch.setattr(ResearchService, "release", die_once)
    with pytest.raises(WorkerKilled):
        tick(client)
    assert killed, "The probe must interrupt after the child was dispatched"

    workflow = client.app.state.workflow
    with workflow.store.read() as conn:
        jobs_before = conn.execute("SELECT count(*) FROM jobs").fetchone()[0]
    assert jobs_before == 1
    # Supported recovery: what `python -m bean_api.worker --recover` does after a crash.
    workflow.recover_interrupted()
    ResearchService(workflow).recover(force=True)
    interrupted = snapshot(client, session["id"])
    assert interrupted["state"] == "needs_reconciliation", interrupted["state"]
    assert len(interrupted["children"]) == 1

    body = {"expected_revision": interrupted["revision"], "acknowledged_unknown_outcome": True}
    path = f"/research-sessions/{session['id']}/reconcile"
    first = client.post(PREFIX + path, json=body, headers={"Idempotency-Key": "reconcile"})
    assert first.status_code == 200, first.text
    again = client.post(PREFIX + path, json=body, headers={"Idempotency-Key": "reconcile"})
    assert again.status_code == 200 and again.json() == first.json()
    other = client.post(PREFIX + path, json=body, headers={"Idempotency-Key": "reconcile-again"})
    assert other.status_code == 409, other.text

    for _ in range(6):
        tick(client)
        final = snapshot(client, session["id"])
        if final["state"] not in {"waiting_child", "queued"}:
            break
    assert final["state"] == "completed", (final["state"], final["action"])
    with workflow.store.read() as conn:
        assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == jobs_before
    assert len(final["children"]) == 1
    assert final["children"][0]["scientific_reservations"] == 1
    assert final["usage"]["child_count"] == 1 and final["usage"]["physical_calls"] == 0
    assert final["reports"]
