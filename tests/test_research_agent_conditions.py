"""Author checks (owner 5): the frozen controlled conditions through the ordinary application.

Real routes, Worker, Deep Agents graph, backend ports and Counterdex run here;
only the planning model is the shipped controlled fixture. Expected branches
come from docs/agent/controlled-conditions.v1.json, committed before the
recorded run. These are not live-model, browser or independent qualification.
"""
from fractions import Fraction
import json

from langchain_core.messages import AIMessage

from bean_api.main import PREFIX
import test_scientific_http as scientific_http
from test_research_controlled_application import replay_current_source, saved_messages, snapshot, tick
from test_scientific_http import ROOT, post

scientific_client = scientific_http.scientific_client
CONDITIONS = json.loads((ROOT / "docs/agent/controlled-conditions.v1.json").read_text())
HERO = json.loads((ROOT / "packages/groundwork_adapter/fixtures/decision/hero-baseline.request.json").read_text())
INPUTS = CONDITIONS["inputs"]


def expect(condition_id):
    return next(item["expect"] for item in CONDITIONS["conditions"] if item["id"] == condition_id)


def start(client, *, claim="reviewed_claim", constraints="design_constraints", problem=True):
    workspace = post(client, "/workspaces", {"name": "Agent condition"}, "workspace")["id"]
    body = {"objective": INPUTS["objective"], "mode": "controlled"}
    if problem:
        dataset = post(client, f"/workspaces/{workspace}/datasets", {
            "experiment_id": "agent-condition", "time_origin": HERO["dataset"]["body"]["time_origin"],
            "origin": "hypothetical", "change_reason": "Synthetic reviewed measurements; no fixed candidates",
            "rows": HERO["dataset"]["body"]["rows"]}, "dataset")
        target = {key: INPUTS[claim][key] for key in ("parameter", "lower", "upper", "closed")}
        reviewed = post(client, f"/workspaces/{workspace}/problems", {
            "dataset_id": dataset["id"], "dataset_digest": dataset["digest"],
            "domain": HERO["problem"]["body"]["domain"], "target": target}, "problem")
        body.update(problem_id=reviewed["id"], expected_problem_digest=reviewed["digest"])
    if constraints:
        body["design_constraints"] = INPUTS[constraints]
    session = post(client, f"/workspaces/{workspace}/research-sessions", body, "research")
    advance(client, session["id"], "advance-1")
    return session["id"]


def advance(client, session_id, key):
    current = snapshot(client, session_id)
    return post(client, f"/research-sessions/{session_id}/advance", {"expected_revision": current["revision"]}, key)


def settle(client, session_id):
    for _ in range(6):
        tick(client)
        current = snapshot(client, session_id)
        if current["state"] not in {"queued", "running", "waiting_child"}:
            return current
    raise AssertionError(f"research did not settle: {current['state']}")


def approve(client, current, key):
    review = current["pending_review"]
    post(client, f"/research-sessions/{current['id']}/decisions", {
        "expected_revision": current["revision"], "pending_review_id": review["id"],
        "expected_review_digest": current["pending_review_digest"], "decision": "approve", "accepted": True}, key)
    return settle(client, current["id"])


def record(client, ref):
    response = client.get(PREFIX + "/records/" + ref)
    assert response.status_code == 200, response.text
    return response.json()


def calls(client, session_id, name):
    return [call for message in saved_messages(client, session_id) if isinstance(message, AIMessage)
            for call in message.tool_calls if call["name"] == name]


def baseline(client, current):
    child = next(job for job in current["children"] if job["kind"] == "run")
    evidence_id = child["scenarios"][0]["result_id"]
    return evidence_id, record(client, evidence_id)["body"]["result"]


def plan(current):
    return current["plan"]["body"]["steps"]


def job_count(client):
    with client.app.state.workflow.store.read() as conn:
        return conn.execute("SELECT count(*) FROM jobs").fetchone()[0]


def investigated(client, **options):
    session_id = start(client, **options)
    waiting = settle(client, session_id)
    assert waiting["state"] == "waiting_review" and waiting["pending_review"]["kind"] == "plan", waiting
    assert waiting["children"] == [] and job_count(client) == 0  # nothing runs before the exact approval
    done = approve(client, waiting, "approve-investigation")
    assert done["state"] == "completed" and len(done["children"]) == len(done["reports"]) == 1, done
    return done


def test_c1_witness_evidence_drives_a_separately_approved_checked_design(scientific_client, tmp_path):
    client, want = scientific_client, expect("C1-supported-witness")
    done = investigated(client)
    evidence_id, result = baseline(client, done)
    for key, value in want["baseline"].items():
        if key != "distinct_checked_candidates":
            assert result[key] == value, (key, result[key])
    candidates = result["candidates"]
    assert len({c["id"] for c in candidates if c["verification"] == "valid"}) == want["baseline"]["distinct_checked_candidates"]
    steps = plan(done)
    assert (steps[-1]["title"], steps[-1]["status"]) == (want["next_step_title"], "pending")
    completed = [step for step in steps if step["status"] == "completed"]
    assert completed and all(step["reference_ids"] == [evidence_id] for step in completed)
    report = calls(client, done["id"], "publish_research_report")[-1]["args"]
    assert (report["next_action"], report["evidence_ids"]) == (want["report_next_action"], [evidence_id])

    advance(client, done["id"], "advance-design")
    review = settle(client, done["id"])
    request = review["pending_review"]["body"]["request"]
    assert review["state"] == "waiting_review" and review["pending_review"]["kind"] == want["design_review"]["pending_review_kind"]
    assert len(review["children"]) == want["design_review"]["children_before_approval"]
    assert set(request["candidate_ids"]) == {c["id"] for c in candidates}
    assert request["candidate_vectors"] == [next(c["parameter_vector"] for c in candidates if c["id"] == ref)
                                            for ref in request["candidate_ids"]]
    for key in ("feasible_times", "future_hard_allowance", "maximum_horizon"):
        assert request[key] == want["design_review"][key]
    assert request["historical_run_id"] == done["children"][0]["id"]

    final = approve(client, review, "approve-design")
    design_job = next(job for job in final["children"] if job["kind"] == "design_job")
    design = record(client, design_job["result_id"])["body"]
    assert design["design_tier"] == want["design"]["design_tier"]
    selected = next(option for option in design["options"] if option["time"] == design["selected_time"])
    assert selected["state"] == "evaluated" and Fraction(selected["exact_margin"]) > 0
    assert plan(final)[-1]["title"] == want["after_design_next_step_title"]
    assert calls(client, final["id"], "publish_research_report")[-1]["args"]["evidence_ids"] == [evidence_id, design_job["result_id"]]
    for checked in (result, design):
        fresh = replay_current_source(client, checked, tmp_path)
        assert fresh["integrity"] == "passed" and fresh["expected_binding"] == "matches"


def test_c2_changed_claim_changes_the_disposition_and_the_recommendation(scientific_client):
    client, want = scientific_client, expect("C2-changed-claim")
    done = investigated(client, claim="widened_claim")
    _, result = baseline(client, done)
    assert result["scientific_outcome"] == want["baseline"]["scientific_outcome"]
    assert plan(done)[-1]["title"] == want["next_step_title"]
    report = calls(client, done["id"], "publish_research_report")[-1]["args"]
    assert report["next_action"] == want["report_next_action"] and want["agent_report_text_contains"] in report["text"]
    before = job_count(client)
    advance(client, done["id"], "advance-after-miss")
    current = settle(client, done["id"])
    assert current["pending_review"]["kind"] == want["next_advance"]["pending_review_kind"]
    assert current["pending_review"]["body"]["fields"] == want["next_advance"]["fields"]
    assert job_count(client) - before == want["next_advance"]["new_children"] and len(current["children"]) == 1


def test_c3_missing_inputs_ask_for_review_without_science(scientific_client):
    client, want = scientific_client, expect("C3-missing-inputs")
    session_id = start(client, problem=False, constraints=None)
    current = settle(client, session_id)
    assert current["state"] == "waiting_review"
    assert current["pending_review"]["kind"] == want["pending_review_kind"]
    assert current["pending_review"]["body"]["fields"] == want["fields"]
    assert len(current["children"]) == want["children"] and job_count(client) == want["jobs"]


def test_c3b_missing_design_constraints_ask_before_any_design(scientific_client):
    client, want = scientific_client, expect("C3b-missing-design-constraints")
    done = investigated(client, constraints=None)
    assert baseline(client, done)[1]["scientific_outcome"] == want["baseline"]["scientific_outcome"]
    before = job_count(client)
    advance(client, done["id"], "advance-without-constraints")
    current = settle(client, done["id"])
    assert current["pending_review"]["kind"] == want["next_advance"]["pending_review_kind"]
    assert current["pending_review"]["body"]["fields"] == want["next_advance"]["fields"]
    assert job_count(client) - before == want["next_advance"]["new_children"]


def test_c4_wide_allowance_reports_no_separation_and_a_different_next_step(scientific_client):
    client, want = scientific_client, expect("C4-no-separating-time")
    done = investigated(client, constraints="wide_allowance_constraints")
    assert baseline(client, done)[1]["scientific_outcome"] == want["baseline"]["scientific_outcome"]
    advance(client, done["id"], "advance-design")
    review = settle(client, done["id"])
    assert review["pending_review"]["kind"] == "design_plan"
    final = approve(client, review, "approve-design")
    design_job = next(job for job in final["children"] if job["kind"] == "design_job")
    design = record(client, design_job["result_id"])["body"]
    assert design["design_tier"] == want["design"]["design_tier"], design["design_tier"]
    assert plan(final)[-1]["title"] == want["after_design_next_step_title"]
    assert calls(client, final["id"], "publish_research_report")[-1]["args"]["next_action"] == want["report_next_action"]
