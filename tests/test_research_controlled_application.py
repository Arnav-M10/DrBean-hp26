"""Production offline policy, ordinary research routes and actual Counterdex.

Only reviewed synthetic input measurements are controlled. The default Worker
loads the shipped model factory: no model/callback override supplies scientific
results. Each worker instance reopens the application's SQLite checkpoints.
These are author integration checks, not live-model or browser qualification.
"""
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import os
import subprocess

from langchain_core.messages import AIMessage, ToolMessage
import pytest

from bean_api.main import PREFIX
from bean_api.research_checkpoints import ResearchJSON
from bean_api.worker import Worker
import test_scientific_http as scientific_http
from test_scientific_http import ROOT, post

scientific_client = scientific_http.scientific_client
QUESTION = "Do the reviewed measurements challenge this range, and what should I do next?"


def snapshot(client, session_id):
    response = client.get(PREFIX + "/research-sessions/" + session_id)
    assert response.status_code == 200, response.text
    return response.json()


def tick(client):
    # No injected model factory, adapter, provider or callback. Recreate the
    # worker so only the actual disk checkpoint carries the policy's progress.
    worker = Worker(client.app.state.workflow, settings=client.app.state.settings)
    assert worker.research.model_factory is None
    return worker.tick()


def saved_messages(client, session_id):
    # Read-only diagnostic of this test's private SQLite store. Public callers
    # never select graph threads or raw checkpoint contents.
    with client.app.state.workflow.store.read() as conn:
        row = conn.execute(
            "SELECT b.checkpoint FROM research_checkpoint_blobs b "
            "JOIN research_sessions s ON s.thread_id=b.thread_id "
            "WHERE s.id=? AND b.namespace='' ORDER BY b.checkpoint_id DESC LIMIT 1",
            (session_id,),
        ).fetchone()
    assert row is not None
    return ResearchJSON().loads(row[0])["channel_values"]["messages"]


def assert_limits_and_zero_provider(client, session):
    assert session["usage"]["physical_calls"] == 0
    assert session["provider_allocation"] == {"physical_requests": 0, "input_tokens": 0, "output_tokens": 0}
    with client.app.state.workflow.store.read() as conn:
        actions = list(conn.execute("SELECT * FROM research_actions WHERE session_id=?", (session["id"],)))
        assert conn.execute("SELECT count(*) FROM provider_attempts").fetchone()[0] == 0
    assert actions
    for action in actions:
        budget = json.loads(action["budget"])
        assert action["logical_turns"] <= budget["model_turns"] <= 4
        assert action["tool_calls"] <= budget["tool_calls"] <= 6
        assert action["child_count"] <= budget["scientific_reservations"] <= 2


def create_session(client, *, incompatible=False, missing=False, future_allowance="1/5"):
    workspace = post(client, "/workspaces", {"name": "Same offline investigation"}, "workspace")["id"]
    body = {"objective": QUESTION, "mode": "controlled"}
    dataset = problem = None
    if not missing:
        control = json.loads((ROOT / "packages/groundwork_adapter/fixtures/decision/hero-baseline.request.json").read_text())
        rows = deepcopy(control["dataset"]["body"]["rows"])
        if incompatible:
            for row in rows:
                row["concentration"] = "1000/1"
        dataset = post(client, f"/workspaces/{workspace}/datasets", {
            "experiment_id": "same-offline-investigation", "time_origin": control["dataset"]["body"]["time_origin"],
            "origin": "hypothetical", "change_reason": "Explicit synthetic measurements; no fixed candidates",
            "rows": rows}, "dataset")
        problem = post(client, f"/workspaces/{workspace}/problems", {
            "dataset_id": dataset["id"], "dataset_digest": dataset["digest"],
            "domain": control["problem"]["body"]["domain"], "target": control["problem"]["body"]["target"]}, "problem")
        body.update(problem_id=problem["id"], expected_problem_digest=problem["digest"], design_constraints={
            "feasible_times": ["6/1", "8/1"], "future_hard_allowance": future_allowance, "maximum_horizon": "8/1",
            "allowance_origin": {"kind": "hypothetical", "description": "Explicit prospective control bound"},
            "requested_tier": "checked_pair_separation", "allow_construction": True, "allow_continuation": True})
    session = post(client, f"/workspaces/{workspace}/research-sessions", body, "research")
    assert session["state"] == "ready" and not session["children"]
    caps = client.get(PREFIX + "/capabilities").json()["deepagents"]
    assert caps["execution_mode"] == "controlled" and caps["dispatch_enabled"]
    assert caps["live_qualification"] == "not_run"
    post(client, f"/research-sessions/{session['id']}/advance", {"expected_revision": session["revision"]}, "advance")
    return session, dataset, problem


def replay_current_source(client, result, tmp_path):
    ref = result["artifacts"][0]
    download = client.get(PREFIX + f"/artifacts/{ref['id']}")
    anchor = client.get(PREFIX + f"/artifacts/{ref['id']}/anchor?download=true")
    assert download.status_code == anchor.status_code == 200
    assert hashlib.sha256(download.content).hexdigest() == ref["sha256"]
    packet, anchors = tmp_path / "native.json", tmp_path / "anchors.json"
    packet.write_bytes(download.content)
    anchors.write_text(json.dumps(anchor.json()))
    # Explicit source import prevents an older installed Counterdex from being
    # mistaken for a replay of the current integration candidate.
    script = "import sys;sys.path.insert(0,sys.argv.pop(1));from counterdex.__main__ import main;raise SystemExit(main())"
    process = subprocess.run([
        client.app.state.settings.counterdex_python, "-I", "-B", "-c", script,
        str(ROOT / "packages/groundwork_adapter"), "replay-native", str(packet), "--anchors", str(anchors),
    ], capture_output=True, text=True, timeout=40, cwd=tmp_path,
        env={"PATH": os.defpath, "LANG": "C.UTF-8"})
    assert process.returncode == 0, process.stderr or process.stdout
    fresh = json.loads(process.stdout)
    assert fresh["integrity"] == "passed" and fresh["expected_binding"] == "matches"
    if "scientific_outcome" in result:
        assert fresh["outcome"]["scientific_outcome"] == result["scientific_outcome"]
    else:
        assert fresh["fresh_checked"]["tier"] == result["design_tier"]
    assert fresh["replay"] == result["replay"]
    return fresh


@pytest.mark.parametrize("incompatible,outcome,next_action", [
    (False, "certified_counterexample", "review_design"),
    (True, "no_counterexample_found", "clarify"),
])
def test_default_factory_ordinary_approved_baseline_reads_real_evidence_and_reports(
    scientific_client, tmp_path, incompatible, outcome, next_action,
):
    client = scientific_client
    session, dataset, problem = create_session(client, incompatible=incompatible)
    assert tick(client) == 1
    waiting = snapshot(client, session["id"])
    assert waiting["state"] == "waiting_review", waiting
    assert waiting["plan"] is not None and not waiting["children"]
    assert waiting["pending_review"]["kind"] == "plan"
    assert waiting["usage"]["child_count"] == 0
    with client.app.state.workflow.store.read() as conn:
        assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0
    # Reopening/repeated ticks cannot turn the pause into approval or dispatch.
    assert tick(client) == 0
    assert snapshot(client, session["id"])["pending_review"] == waiting["pending_review"]
    decision = {"expected_revision": waiting["revision"], "pending_review_id": waiting["pending_review"]["id"],
        "expected_review_digest": waiting["pending_review_digest"], "decision": "approve", "accepted": True}
    path = f"/research-sessions/{session['id']}/decisions"
    post(client, path, decision, "approve-baseline")
    post(client, path, decision, "approve-baseline")  # same acknowledged decision, no extra action/child
    for _ in range(4):
        tick(client)
        final = snapshot(client, session["id"])
        if final["state"] != "waiting_child":
            break
    assert final["state"] == "completed", final
    assert final["objective"] == QUESTION and len(final["reports"]) == len(final["children"]) == 1
    assert final["usage"]["child_count"] == 1
    child = final["children"][0]
    assert child["state"] == "completed" and child["scientific_reservations"] == 1
    evidence_id = child["scenarios"][0]["result_id"]
    evidence = client.get(PREFIX + "/records/" + evidence_id).json()
    result = evidence["body"]["result"]
    assert result["scientific_outcome"] == outcome
    assert result["baseline_search"]["attempted_count"] > 0
    assert result["problem_digest"] == problem["digest"]
    assert result["native_replay"]["operation"] == "investigate"
    messages = saved_messages(client, session["id"])
    calls = [call for message in messages if isinstance(message, AIMessage) for call in message.tool_calls]
    assert any(call["name"] == "write_todos" for call in calls)
    assert any(call["name"] == "read_research_evidence" and call["args"]["evidence_id"] == evidence_id for call in calls)
    report_call = next(call for call in reversed(calls) if call["name"] == "publish_research_report")
    assert report_call["args"]["evidence_ids"] == [evidence_id]
    assert report_call["args"]["next_action"] == next_action
    accepted = next(json.loads(message.content) for message in messages
                    if isinstance(message, ToolMessage) and message.tool_call_id == report_call["id"])
    assert accepted["id"] in final["reports"]
    assert accepted["agent_commentary"]["next_action"] == next_action
    assert accepted["agent_commentary"]["scientific_authority"] is False
    assert accepted["agent_commentary"]["authorship"] == "controlled_commentary"
    assert accepted["commentary_persisted"] is False  # checkpoint annotation is distinct from canonical report
    report = client.get(PREFIX + "/reports/" + final["reports"][0]).json()
    assert report["body"]["evidence"] == [evidence]
    assert report["body"]["root_inputs"]["dataset"] == dataset
    fresh = replay_current_source(client, result, tmp_path)
    if incompatible:
        assert result["candidates"] == [] and fresh["verification"] == "not_checked"
        assert fresh["replay"] == "unsupported"
    else:
        assert fresh["verification"] == "valid" and fresh["replay"] == "passed"
    assert_limits_and_zero_provider(client, final)
    assert tick(client) == 0


def test_default_factory_missing_reviewed_assumptions_requests_input_without_science(scientific_client):
    client = scientific_client
    session, _, _ = create_session(client, missing=True)
    assert tick(client) == 1
    waiting = snapshot(client, session["id"])
    assert waiting["state"] == "waiting_review", waiting
    assert waiting["pending_review"]["kind"] == "research_clarification"
    assert waiting["pending_review"]["body"]["fields"]
    assert not waiting["children"] and not waiting["reports"]
    assert waiting["usage"]["child_count"] == 0
    with client.app.state.workflow.store.read() as conn:
        assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0
    calls = [call for message in saved_messages(client, session["id"]) if isinstance(message, AIMessage)
             for call in message.tool_calls]
    assert calls[-1]["name"] == "request_clarification"
    assert not any(call["name"] == "run_scientific_operation" for call in calls)
    assert_limits_and_zero_provider(client, waiting)


def approve_and_finish(client, waiting, key):
    decision = {"expected_revision": waiting["revision"], "pending_review_id": waiting["pending_review"]["id"],
        "expected_review_digest": waiting["pending_review_digest"], "decision": "approve", "accepted": True}
    post(client, f"/research-sessions/{waiting['id']}/decisions", decision, key)
    for _ in range(4):
        tick(client)
        current = snapshot(client, waiting["id"])
        if current["state"] != "waiting_child":
            break
    assert current["state"] == "completed", current["action"]
    return current


@pytest.mark.parametrize("allowance,tier,next_action", [
    ("1/5", "checked_pair_separation", "review_observation"),
    ("100/1", "no_separation_established", "clarify"),
])
def test_explicit_advance_requires_separate_pair_design_review_and_retains_baseline(
    scientific_client, tmp_path, allowance, tier, next_action,
):
    client = scientific_client
    session, _, _ = create_session(client, future_allowance=allowance)
    tick(client)
    first = approve_and_finish(client, snapshot(client, session["id"]), "approve-baseline")
    assert len(first["children"]) == len(first["reports"]) == 1
    original_report = client.get(PREFIX + "/reports/" + first["reports"][0]).json()
    baseline_job = first["children"][0]
    baseline_id = baseline_job["scenarios"][0]["result_id"]
    baseline = client.get(PREFIX + "/records/" + baseline_id).json()
    vectors = {c["id"]: c["parameter_vector"] for c in baseline["body"]["result"]["candidates"]}
    assert len(vectors) == 2
    assert tick(client) == 0  # report/next-step proposal did not authorize design
    advance = client.post(PREFIX + f"/research-sessions/{session['id']}/advance",
        json={"expected_revision": first["revision"]}, headers={"Idempotency-Key": "advance-design"})
    if advance.status_code == 409 and advance.json().get("code") == "research_not_advanceable":
        pytest.xfail("B dependency: completed report cannot start an explicit next action (PR41 research.py:258); pair flow not available")
    assert advance.status_code in {200, 201, 202}, advance.text
    tick(client)
    waiting = snapshot(client, session["id"])
    assert waiting["state"] == "waiting_review", waiting["action"]
    assert waiting["pending_review"]["kind"] == "design_plan"
    assert len(waiting["children"]) == waiting["usage"]["child_count"] == 1
    request = waiting["pending_review"]["body"]["request"]
    assert dict(zip(request["candidate_ids"], request["candidate_vectors"], strict=True)) == vectors
    assert request["historical_run_id"] == baseline_job["id"]
    assert request["future_hard_allowance"] == allowance
    assert set(request["feasible_times"]) == {"6/1", "8/1"}
    assert tick(client) == 0
    final = approve_and_finish(client, waiting, "approve-design")
    assert len(final["reports"]) == len(final["children"]) == final["usage"]["child_count"] == 2
    design_job = next(child for child in final["children"] if child["kind"] == "design_job")
    design = client.get(PREFIX + "/records/" + design_job["result_id"]).json()
    result = design["body"]
    assert result["design_tier"] == tier and result["candidate_ids"] == request["candidate_ids"]
    if tier == "checked_pair_separation":
        option = next(option for option in result["options"] if option["time"] == result["selected_time"])
        assert Fraction(option["exact_margin"]) > 0
    else:
        assert result["selected_time"] is None
        assert all(Fraction(option["exact_margin"]) <= 0 for option in result["options"] if option["state"] == "evaluated")
    assert client.get(PREFIX + "/reports/" + first["reports"][0]).json() == original_report
    assert client.get(PREFIX + "/records/" + baseline_id).json() == baseline
    current_report = client.get(PREFIX + "/reports/" + final["reports"][-1]).json()
    assert [record["id"] for record in current_report["body"]["evidence"]] == [baseline_id, design["id"]]
    messages = saved_messages(client, session["id"])
    calls = [call for message in messages if isinstance(message, AIMessage) for call in message.tool_calls]
    latest = next(call for call in reversed(calls) if call["name"] == "publish_research_report")
    assert latest["args"]["evidence_ids"] == [baseline_id, design["id"]]
    assert latest["args"]["next_action"] == next_action
    fresh = replay_current_source(client, result, tmp_path)
    assert fresh["replay"] == "passed" and fresh["fresh_checked"]["tier"] == tier
    assert_limits_and_zero_provider(client, final)
    assert tick(client) == 0
