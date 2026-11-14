"""A completed scientific child cannot publish after its authority has ended."""
import pytest

from bean_api.main import PREFIX
from bean_api.worker import Worker
import bean_api.worker as worker_module
import test_native_design_workflow as design_tests
from test_scientific_http import post

scientific_client = design_tests.scientific_client
computed_history = design_tests.computed_history


@pytest.mark.parametrize("stop", ["cancel", "expire"])
def test_late_native_design_is_not_published_after_scope_ends(computed_history, monkeypatch, stop):
    history = computed_history
    client = history["client"]
    workflow = client.app.state.workflow
    plan = design_tests.propose(history, design_tests.design_request(history), "late-design")
    approval = post(client, f"/design-plans/{plan['id']}/approvals", {
        "expected_plan_digest": plan["digest"], "expected_current_revision_id": history["problem"]["id"],
        "accepted": True}, "late-approval")
    job = post(client, f"/design-plans/{plan['id']}/jobs", {
        "approval_id": approval["id"], "expected_plan_digest": plan["digest"]}, "late-start")
    real_run = worker_module.run_bounded

    def complete_then_end_scope(*args, **kwargs):
        result = real_run(*args, **kwargs)
        assert result.get("design_tier") == "checked_pair_separation", result
        if stop == "cancel":
            post(client, f"/design-jobs/{job['id']}/cancel", {}, "late-cancel")
        else:
            # Move the test clock after computation; approval records are immutable.
            monkeypatch.setattr("bean_api.workflow.utc_now", lambda: "2100-01-01T00:00:00.000Z")
        return result

    monkeypatch.setattr(worker_module, "run_bounded", complete_then_end_scope)
    assert Worker(workflow, settings=client.app.state.settings).tick() == 1
    finished = client.get(PREFIX + f"/design-jobs/{job['id']}").json()
    assert finished["state"] == ("cancelled" if stop == "cancel" else "failed")
    assert finished["error_code"] == ("job_not_active" if stop == "cancel" else "approval_expired")
    assert finished["result_id"] is None
    retained = client.get(PREFIX + f"/workspaces/{history['workspace']}/records?kind=native_artifact").json()
    assert [item["id"] for item in retained] == [history["result"]["artifacts"][0]["id"]]
    design_tests.assert_preserved_history(history)
