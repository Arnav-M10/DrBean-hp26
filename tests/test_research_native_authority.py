"""B authority + actual Counterdex operations, not parent/browser qualification.

Only input measurements and a declared hypothetical follow-up are controlled.
Every candidate, design, feedback result and native artifact is genuinely computed.
"""
import asyncio
from fractions import Fraction
import json


from bean_api.main import PREFIX
from bean_api.research import ResearchService
from bean_api.research_tools import ApplicationResearchPorts
from bean_api.worker import Worker
import test_baseline_workflow as baseline
import test_scientific_http as scientific_http
from test_scientific_http import ROOT, post

scientific_client = scientific_http.scientific_client

replay_python = baseline.replay_python


def run(value):
    return asyncio.run(value)


def reviewed_inputs(client, *, target=None):
    fixture = json.loads((ROOT / "packages/groundwork_adapter/fixtures/decision/hero-baseline.request.json").read_text())
    workspace = post(client, "/workspaces", {"name": "Controlled durable authority, real scientific children"}, "workspace")["id"]
    dataset = post(client, f"/workspaces/{workspace}/datasets", {
        "experiment_id": "synthetic-research-authority", "time_origin": fixture["dataset"]["body"]["time_origin"], "origin": "hypothetical",
        "change_reason": "Explicit synthetic measurement control; candidates are not fixtures",
        "rows": fixture["dataset"]["body"]["rows"]}, "dataset")
    problem = post(client, f"/workspaces/{workspace}/problems", {
        "dataset_id": dataset["id"], "dataset_digest": dataset["digest"],
        "domain": fixture["problem"]["body"]["domain"], "target": target or fixture["problem"]["body"]["target"]}, "problem")
    return workspace, dataset, problem


def constraints(allowance="1/5"):
    return {"feasible_times": ["8/1", "6/1"], "future_hard_allowance": allowance, "maximum_horizon": "8/1",
        "allowance_origin": {"kind": "hypothetical", "description": "Explicitly reviewed synthetic prospective hard bound"},
        "requested_tier": "checked_pair_separation", "allow_construction": True, "allow_continuation": True}


def begin(client):
    workspace, dataset, problem = reviewed_inputs(client)
    service = ResearchService(client.app.state.workflow)
    session = service.create("alice", workspace, {"objective": "Which measurements would challenge this range, and which original candidates survive a new reading?",
        "problem_id": problem["id"], "expected_problem_digest": problem["digest"], "design_constraints": constraints()}, "research")
    queued = service.advance("alice", session["id"], {"expected_revision": session["revision"]}, "advance")
    context = service.acquire("alice", queued["action"]["id"], "authority-harness")
    return service, context, ApplicationResearchPorts(service, context), dataset, problem


def approve(service, context, ports, prepared, key):
    assert run(ports.require_review(prepared["review_id"], prepared["review_digest"]))["decision"] == "pending"
    service.release(context, "waiting_review")
    current = service.get("alice", context.research_session_id)
    body = {"expected_revision": current["revision"], "pending_review_id": prepared["review_id"],
        "expected_review_digest": prepared["review_digest"], "accepted": True, "decision": "approve"}
    queued = service.decide("alice", current["id"], body, key)
    assert service.decide("alice", current["id"], body, key) == queued
    new = service.acquire("alice", queued["action"]["id"], "authority-harness-next")
    return new, ApplicationResearchPorts(service, new)


def execute(client, ports, prepared):
    first = run(ports.execute_child(prepared["review_id"], prepared["review_digest"]))
    assert first["state"] == "pending"
    worker = Worker(client.app.state.workflow, settings=client.app.state.settings)
    assert worker.tick() == 1
    done = run(ports.execute_child(prepared["review_id"], prepared["review_digest"]))
    assert done["state"] == "completed", done
    assert done["job_id"] == first["job_id"] and len(done["evidence_ids"]) == 1
    record = client.get(PREFIX + "/records/" + done["evidence_ids"][0]).json()
    observed = run(ports.read_evidence(record["id"]))
    assert observed == record
    fact = {"id": record["id"], **record["body"].get("result", record["body"])}
    return done, record, fact


def assert_native_replay(client, record, replay_python, path):
    path.mkdir()
    result = record["body"].get("result", record["body"])
    ref = result["artifacts"][0]
    content = client.get(PREFIX + "/artifacts/" + ref["id"])
    anchor = client.get(PREFIX + "/artifacts/" + ref["id"] + "/anchor?download=true")
    assert content.status_code == anchor.status_code == 200
    process, replay = baseline.replay_cli(replay_python, path, content.content, anchor.json())
    assert process.returncode == 0, replay
    assert replay["replay"] == "passed" and replay["expected_binding"] == "matches", replay
    return content.content


def test_real_children_separate_reviews_new_reading_snapshot_updates_and_replay(scientific_client, replay_python, tmp_path):
    client = scientific_client
    service, context, ports, dataset, problem = begin(client)
    prepared = run(ports.prepare_investigation())
    context, ports = approve(service, context, ports, prepared, "approve-baseline")
    baseline_job, baseline_record, baseline_fact = execute(client, ports, prepared)
    assert baseline_fact["scientific_outcome"] == "certified_counterexample"
    first_bytes = assert_native_replay(client, baseline_record, replay_python, tmp_path / "baseline")
    before = run(ports.publish_report())
    before_record = client.get(PREFIX + "/reports/" + before["id"]).json()
    assert len(before["evidence_ids"]) == 1
    design = run(ports.prepare_design(constraints()))
    context, ports = approve(service, context, ports, design, "approve-design")
    design_job, design_record, design_fact = execute(client, ports, design)
    assert design_fact["design_tier"] == "checked_pair_separation"
    assert_native_replay(client, design_record, replay_python, tmp_path / "design")
    after = run(ports.publish_report())
    assert after["id"] != before["id"] and len(after["evidence_ids"]) == 2
    assert run(ports.publish_report()) == after
    assert client.get(PREFIX + "/reports/" + before["id"]).json() == before_record
    altered = run(ports.prepare_design(constraints("100/1")))
    assert altered["review_id"] != design["review_id"] and altered["review_digest"] != design["review_digest"]
    assert altered["approval_id"] is None

    wait = run(ports.request_clarification(["new_observation"], "Review a separately acquired or explicitly hypothetical new reading."))
    service.release(context, "waiting_observation")
    current = service.get("alice", context.research_session_id)
    assert current["action"]["state"] == "waiting_observation"
    native = design_record["body"]["native_replay"]["fresh_checked"]
    selected = next(row for row in native["rows"] if row["time"] == design_record["body"]["selected_time"])
    cid = design_record["body"]["candidate_ids"][0]
    value = Fraction(format(float(Fraction(selected["centers"][cid])), ".6f"))
    reading = {"dataset_id": dataset["id"], "experiment_id": dataset["body"]["experiment_id"], "origin": "hypothetical",
        "row": {"id": "reviewed-new-reading", "time": selected["time"], "concentration": f"{value.numerator}/{value.denominator}",
            "hard_allowance": design_record["body"]["future_hard_allowance"], "included": True},
        "source_description": "Explicit hypothetical follow-up derived from the actual computed design center",
        "change_reason": "Check only the two original candidates against this separately reviewed reading",
        "generating_choices": {"method": "Six-decimal computed first-candidate prediction center", "design_job_id": design_job["job_id"]}}
    body = {"expected_revision": current["revision"], "pending_review_id": wait["id"], "expected_review_digest": wait["review_digest"], "observation": reading, "accepted": True}
    adopted = post(client, f"/research-sessions/{current['id']}/observations", body, "review-reading")
    assert post(client, f"/research-sessions/{current['id']}/observations", body, "review-reading") == adopted
    context = service.acquire("alice", adopted["action"]["id"], "authority-followup")
    ports = ApplicationResearchPorts(service, context)
    followup = run(ports.prepare_followup())
    plan = client.get(PREFIX + "/records/" + followup["review_id"]).json()
    assert plan["body"]["followup"]["design_result_id"] == design_record["id"]
    assert plan["body"]["provider_disclosure"]["provider"] == "none"
    assert service.get("alice", current["id"])["usage"]["child_count"] == 2
    revised = client.get(PREFIX + "/records/" + plan["body"]["dataset_id"]).json()
    assert revised["body"]["rows"][:-1] == dataset["body"]["rows"]
    assert revised["body"]["rows"][-1]["concentration"] == reading["row"]["concentration"]
    context, ports = approve(service, context, ports, followup, "approve-recheck")
    _, followup_record, followup_fact = execute(client, ports, followup)
    assert {c["id"]: c["parameter_vector"] for c in followup_fact["candidates"]} == {c["id"]: c["parameter_vector"] for c in baseline_fact["candidates"]}
    assert any(row["candidate_id"] == cid and row["verification"] == "valid" for row in followup_fact["candidate_results"])
    assert_native_replay(client, followup_record, replay_python, tmp_path / "followup")
    final = run(ports.publish_report())
    assert len(final["evidence_ids"]) == 3 and final["id"] not in {before["id"], after["id"]}
    assert client.get(PREFIX + f"/reports/{final['id']}/download").status_code == 200
    assert client.get(PREFIX + "/artifacts/" + baseline_record["body"]["result"]["artifacts"][0]["id"]).content == first_bytes
    assert service.get("alice", current["id"])["usage"]["child_count"] == 3


def test_real_no_separation_remains_negative(scientific_client):
    client = scientific_client
    service, context, ports, _, _ = begin(client)
    prepared = run(ports.prepare_investigation())
    context, ports = approve(service, context, ports, prepared, "approve-baseline")
    execute(client, ports, prepared)
    design = run(ports.prepare_design(constraints("100/1")))
    context, ports = approve(service, context, ports, design, "approve-design")
    _, _, fact = execute(client, ports, design)
    assert fact["design_tier"] == "no_separation_established"
    assert fact["selected_time"] is None
    assert all(Fraction(row["exact_margin"]) <= 0 for row in fact["options"] if row["state"] == "evaluated")
