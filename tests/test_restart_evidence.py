"""Ordinary worker restart keeps real scientific evidence and accepted job IDs.

Only measurements and the interruption point are controlled. Candidate discovery,
checking, native publication, API reads and installed CLI replay run for real.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from fastapi.testclient import TestClient

from bean_api.main import PREFIX, create_app
import test_baseline_workflow as baseline
import test_scientific_http as scientific_http
from test_scientific_http import ROOT, post, prepare_approved_history

scientific_client = scientific_http.scientific_client
replay_python = baseline.replay_python


def worker_env(settings):
    # Explicit isolated configuration: never inherit model credentials or a real
    # auth file from the developer environment into the child process.
    return {"PATH": os.defpath, "LANG": "C.UTF-8", "PYTHONPATH": str(ROOT / "apps/api"),
        "BEAN_DATABASE_PATH": settings.database_path, "BEAN_BLOB_DIR": settings.blob_dir,
        "BEAN_ARTIFACT_DIR": settings.artifact_dir, "BEAN_COUNTERDEX_PYTHON": settings.counterdex_python,
        "BEAN_AUTH_TOKENS_JSON": "{}", "BEAN_AUTH_FILE": str(Path(settings.database_path).with_suffix(".no-auth"))}


def worker_cli(settings, option):
    completed = subprocess.run([sys.executable, "-m", "bean_api.worker", option],
        cwd=ROOT, env=worker_env(settings), capture_output=True, text=True, timeout=30)
    assert completed.returncode == 0, completed.stderr
    return completed


PAUSE_AFTER_EVIDENCE = '''
import json, sys, time
from pathlib import Path
from bean_api.config import Settings
from bean_api.store import Store
from bean_api.workflow import Workflow
from bean_api.worker import Worker

def main():
    settings = Settings.from_env()
    workflow = Workflow(Store(settings.database_path))
    complete = workflow.complete_scenario
    def pause(*args, **kwargs):
        evidence = complete(*args, **kwargs)
        Path(sys.argv[1]).write_text(json.dumps({"evidence_id": evidence["id"]}))
        time.sleep(300)
        return evidence
    workflow.complete_scenario = pause
    Worker(workflow, settings=settings).tick()

if __name__ == "__main__":
    main()
'''


def wait_for_evidence(process, ready):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if ready.exists():
            try:
                return json.loads(ready.read_text())["evidence_id"]
            except (ValueError, KeyError):
                pass  # The writer may still be completing the tiny barrier file.
        if process.poll() is not None:
            _, error = process.communicate()
            raise AssertionError("Worker exited before committing evidence: " + error)
        time.sleep(0.025)
    raise AssertionError("Actual science did not reach the post-publication interruption point")


def artifact_snapshot(client, record):
    reference = record["body"]["result"]["artifacts"][0]
    response = client.get(PREFIX + f"/artifacts/{reference['id']}")
    assert response.status_code == 200
    assert response.headers["X-Artifact-SHA256"] == reference["sha256"]
    anchor = client.get(PREFIX + f"/artifacts/{reference['id']}/anchor?download=true")
    assert anchor.status_code == 200
    return reference, response.content, anchor.json()


def test_restart_after_real_evidence_preserves_downloads_and_never_redispatches(
        scientific_client, replay_python, tmp_path):
    client = scientific_client
    workspace, _, _, plan, approval, run, _ = prepare_approved_history(client)
    settings = client.app.state.settings
    script, ready = tmp_path / "pause_after_evidence.py", tmp_path / "evidence-ready.json"
    script.write_text(PAUSE_AFTER_EVIDENCE)
    process = subprocess.Popen([sys.executable, str(script), str(ready)], cwd=ROOT,
        env=worker_env(settings), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        evidence_id = wait_for_evidence(process, ready)
        before = client.get(PREFIX + f"/runs/{run['id']}").json()
        assert before["state"] == "running" and before["result_id"] is None
        assert before["scenarios"][0]["state"] == "completed"
        assert before["scenarios"][0]["result_id"] == evidence_id
        record = client.get(PREFIX + f"/records/{evidence_id}").json()
        result = record["body"]["result"]
        assert result["scientific_outcome"] == "certified_counterexample"
        assert result["verification"] == "valid" and result["replay"] == "passed"
        assert result["baseline_search"]["attempted_count"] > 0 and result["candidates"]
        reference, content, anchors = artifact_snapshot(client, record)
        retained = client.get(PREFIX + f"/workspaces/{workspace}/records?kind=native_artifact").json()
        process.kill()  # SIGKILL bypasses Worker.execute's normal exception path.
        process.wait(timeout=10)
    finally:
        if process.poll() is None:
            process.kill()
        process.communicate(timeout=10)

    first = json.loads(worker_cli(settings, "--recover").stdout)
    assert first["jobs"] == 1 and first["scenarios"] == 0
    assert first["provider_attempts"] == 0
    second = json.loads(worker_cli(settings, "--recover").stdout)
    assert not any(second.values()), second
    worker_cli(settings, "--once")

    # A new API/store instance demonstrates durable reopening, not warm memory.
    with TestClient(create_app(settings)) as reopened:
        reopened.headers["Authorization"] = "Bearer " + "a" * 40
        recovered = reopened.get(PREFIX + f"/runs/{run['id']}").json()
        assert recovered["state"] == "interrupted" and recovered["error_code"] == "worker_restart"
        assert recovered["scientific_reservations"] == 1
        assert recovered["scenarios"] == before["scenarios"]
        assert recovered["result_id"] is None
        assert reopened.get(PREFIX + f"/records/{evidence_id}").json() == record
        assert artifact_snapshot(reopened, record) == (reference, content, anchors)
        assert reopened.get(PREFIX + f"/workspaces/{workspace}/records?kind=native_artifact").json() == retained
        assert post(reopened, f"/plans/{plan['id']}/runs", {
            "approval_id": approval["id"], "expected_plan_digest": plan["digest"]}, "after-restart-retry")["id"] == run["id"]
        assert reopened.get(PREFIX + f"/workspaces/{workspace}/provider-attempts").json() == []
    process, fresh = baseline.replay_cli(replay_python, tmp_path, content, anchors)
    assert process.returncode == 0, fresh
    assert fresh["integrity"] == fresh["replay"] == "passed"
    assert fresh["verification"] == "valid" and fresh["expected_binding"] == "matches"
    assert fresh["search_replayed"] is False and fresh["anchors"] == anchors


def test_restart_acknowledges_unstarted_cancellation_and_preserves_queued_work(scientific_client):
    client = scientific_client
    cancelled_workspace, _, _, cancelled_plan, cancelled_approval, cancelled, _ = prepare_approved_history(client)
    post(client, f"/runs/{cancelled['id']}/cancel", {}, "queued-cancel")
    workspace, _, _, plan, approval, queued, _ = prepare_approved_history(client)
    settings = client.app.state.settings
    counts = json.loads(worker_cli(settings, "--recover").stdout)
    assert counts["scenarios"] == counts["provider_attempts"] == 0
    stopped = client.get(PREFIX + f"/runs/{cancelled['id']}").json()
    assert stopped["state"] == "cancelled" and stopped["started_at"] is None
    assert stopped["scenarios"] == [] and stopped["scientific_reservations"] == 0
    untouched = client.get(PREFIX + f"/runs/{queued['id']}").json()
    assert untouched["state"] == "queued" and untouched["scenarios"] == []
    assert post(client, f"/plans/{cancelled_plan['id']}/runs", {
        "approval_id": cancelled_approval["id"], "expected_plan_digest": cancelled_plan["digest"]}, "retry-cancelled")["id"] == cancelled["id"]
    assert not any(json.loads(worker_cli(settings, "--recover").stdout).values())
    worker_cli(settings, "--once")
    finished = client.get(PREFIX + f"/runs/{queued['id']}").json()
    assert finished["state"] == "completed" and finished["scientific_reservations"] == 1
    assert finished["scenarios"][0]["state"] == "completed"
    assert post(client, f"/plans/{plan['id']}/runs", {
        "approval_id": approval["id"], "expected_plan_digest": plan["digest"]}, "retry-queued")["id"] == queued["id"]
    worker_cli(settings, "--once")
    for wid in (workspace, cancelled_workspace):
        assert client.get(PREFIX + f"/workspaces/{wid}/provider-attempts").json() == []
