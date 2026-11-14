"""Durable restart state controls; these fixtures make no scientific claims."""
import pytest

from bean_api.store import Store
from bean_api.workflow import Workflow
from test_workflow import prepared
from test_worker import queued_design


@pytest.fixture
def flow(tmp_path):
    workflow = Workflow(Store(tmp_path / "restart.sqlite3"))
    return workflow, workflow.create_workspace("alice", "Restart state control")["id"]


@pytest.mark.parametrize("kind", ["run", "design_job"])
def test_restart_acknowledges_never_started_cancellation_without_dispatch(flow, kind):
    workflow, _ = flow
    if kind == "run":
        _, _, plan, approval = prepared(flow)
        job = workflow.start_run("alice", plan["id"], approval["id"], "start")
    else:
        _, _, job = queued_design(flow)
    workflow.cancel_run("alice", job["id"], "cancel")
    reopened = Workflow(Store(workflow.store.path))
    counts = reopened.recover_interrupted()
    current = reopened.get_run("alice", job["id"]) if kind == "run" else reopened.get_design_job("alice", job["id"])
    assert counts["queued_cancellations"] == counts["jobs"] == 1
    assert current["state"] == "cancelled" and current["started_at"] is None
    assert current["scenarios"] == [] and current["scientific_reservations"] == 0
    assert current["error_code"] is None and current["result_id"] is None
    assert reopened.queued_jobs() == []
    assert all(value == 0 for value in reopened.recover_interrupted().values())


def test_restart_preserves_queued_work_and_interrupts_started_cancellation(flow):
    workflow, workspace = flow
    _, _, plan, approval = prepared(flow)
    job = workflow.start_run("alice", plan["id"], approval["id"], "start")
    assert workflow.recover_interrupted()["jobs"] == 0
    assert [item["id"] for item in workflow.queued_jobs()] == [job["id"]]
    workflow.mark_running("alice", job["id"], "old-worker")
    workflow.reserve_scenario("alice", job["id"], "baseline")
    workflow.cancel_run("alice", job["id"], "cancel")
    counts = workflow.recover_interrupted()
    current = workflow.get_run("alice", job["id"])
    assert counts["queued_cancellations"] == 0 and counts["jobs"] == counts["scenarios"] == 1
    assert current["state"] == current["scenarios"][0]["state"] == "interrupted"
    assert current["error_code"] == "worker_restart"
    assert workflow.queued_jobs() == []
    assert workflow.list_records("alice", workspace, "evidence") == []
