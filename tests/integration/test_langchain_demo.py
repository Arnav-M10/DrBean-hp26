"""C (independent): the narrow LangChain demo profile, claims DEMO-01..10.

Profile: evaluation/coordinator/demo-profile.langchain-narrow-demo.v1.json. Passing these checks never implies full
coordinator release qualification.

Everything runs through the actual launched API and worker, actual Counterdex and the DB-RESEARCH-1 routes, with the
coordinator in controlled mode (lane controlled_science: controlled model decisions, actual science). No provider is
contacted, and every check reports NOT_AVAILABLE while research dispatch is not enabled.

Three sessions run once per module:
- witness: the hero claim, with reviewed design constraints;
- no_witness: the claim widened to the whole admitted ke domain;
- missing_constraints: the hero claim without design constraints.

Next actions are graded as acceptable sets, never as exact text.
"""
from __future__ import annotations

import hashlib
import json
import time

import pytest

from drbean_support import REPO, launcher, load_packet, other_actor, reviewer
from drbean_eval import native
from drbean_eval import science_flow as sf
from drbean_eval.http_client import ApiFailure

pytestmark = [pytest.mark.real_stack, pytest.mark.real_science]

HERO = load_packet("hero-v2")
OBJECTIVE = "Do these reviewed measurements admit a compatible ke outside the claimed range, and what should I measure next?"
MOVING = {"queued", "running", "waiting_child"}
REVIEW = HERO["design_review"]
CONSTRAINTS = {"feasible_times": REVIEW["feasible_times"], "future_hard_allowance": REVIEW["future_hard_allowance"],
               "maximum_horizon": REVIEW["maximum_horizon"], "requested_tier": "checked_pair_separation",
               "allowance_origin": {"kind": "hypothetical", "description": REVIEW["allowance_description"]},
               "allow_construction": bool(REVIEW["allow_construction"]),
               "allow_continuation": bool(REVIEW["allow_continuation"])}


def settle(client, session_id, timeout=300.0):
    deadline = time.monotonic() + timeout
    while True:
        snapshot = client.get(f"/research-sessions/{session_id}")
        if snapshot["state"] not in MOVING:
            return snapshot
        if time.monotonic() > deadline:
            raise AssertionError(f"research session still {snapshot['state']} after {timeout:.0f} s")
        time.sleep(0.5)


def events(client, session_id):
    page = client.get(f"/research-sessions/{session_id}/events?after=-1")
    return page["items"] if isinstance(page, dict) else page


def next_action(snapshot) -> str:
    """The coordinator's next permitted action, as an acceptable-set label."""
    if snapshot["state"] == "waiting_review":
        return "review:" + str((snapshot.get("pending_review") or {}).get("kind"))
    if snapshot["state"] == "waiting_observation":
        return "clarification_or_observation"
    if snapshot.get("reports"):
        return "report"
    return "state:" + snapshot["state"]


def run_session(client, label, *, widen=False, constraints=True):
    workspace = client.post("/workspaces", {"name": f"C demo {label}"}, label=f"{label}-ws")["id"]
    dataset = client.post(f"/workspaces/{workspace}/datasets", HERO["dataset"], label=f"{label}-dataset")
    body = {**HERO["problem"], "dataset_id": dataset["id"], "dataset_digest": dataset["digest"]}
    if widen:
        parameter = HERO["problem"]["target"]["parameter"]
        domain = HERO["problem"]["domain"][parameter]
        body["target"] = {**HERO["problem"]["target"], "lower": domain["lower"], "upper": domain["upper"]}
    problem = client.post(f"/workspaces/{workspace}/problems", body, label=f"{label}-problem")
    request = {"schema_version": "DB-RESEARCH-1", "objective": OBJECTIVE, "problem_id": problem["id"],
               "expected_problem_digest": problem["digest"], "mode": "controlled"}
    if constraints:
        request["design_constraints"] = CONSTRAINTS
    created = client.post(f"/workspaces/{workspace}/research-sessions", request, label=f"{label}-session")
    client.post(f"/research-sessions/{created['id']}/advance", {"expected_revision": created["revision"]},
                label=f"{label}-advance")
    first = settle(client, created["id"])
    record = {"workspace": workspace, "problem": problem, "created": created, "first": first,
              "first_events": events(client, created["id"])}
    review = first.get("pending_review") or {}
    if first["state"] == "waiting_review" and review.get("kind") == "plan":
        decision = {"expected_revision": first["revision"], "pending_review_id": review["id"],
                    "expected_review_digest": first["pending_review_digest"], "decision": "approve", "accepted": True}
        key = f"c-demo-{label}-decision"
        record["decision"] = (decision, key, client.post(f"/research-sessions/{created['id']}/decisions", decision,
                                                         key=key))
        record["second"] = settle(client, created["id"])
        record["second_events"] = events(client, created["id"])
    return record


@pytest.fixture(scope="module")
def demo(module_stack):
    client, other = reviewer(module_stack), other_actor(module_stack)
    capabilities = client.get("/capabilities").get("deepagents") or {}
    if capabilities.get("dispatch_enabled") is not True or capabilities.get("execution_mode") != "controlled":
        return {"unavailable": f"research dispatch is not enabled in controlled mode on this build "
                               f"({capabilities.get('unavailable_reason')!r})"}
    runs = {name: run_session(client, name, **options) for name, options in (
        ("witness", {}), ("no_witness", {"widen": True}), ("missing_constraints", {"constraints": False}))}
    return {"client": client, "other": other, "capabilities": capabilities, "runs": runs, "stack": module_stack}


def available(demo):
    if demo.get("unavailable"):
        pytest.xfail("NOT_AVAILABLE: " + demo["unavailable"])
    return demo


def approved(run):
    if "second" not in run:
        raise AssertionError(f"no canonical investigation review was reached: state {run['first']['state']}, "
                             f"next action {next_action(run['first'])}")
    return run


def evidence_of(client, snapshot):
    """Evidence records of every completed child job, in order."""
    found = []
    for child in snapshot.get("children") or []:
        for scenario in client.get(f"/runs/{child['id']}").get("scenarios") or []:
            if scenario.get("result_id"):
                found.append(client.get(f"/records/{scenario['result_id']}"))
    return found


def test_demo_01_graph_and_planning_execute(demo):
    run = available(demo)["runs"]["witness"]
    first, trail = run["first"], run["first_events"]
    tools = [event["summary"] for event in trail if event["event_type"] == "tool_requested"]
    assert any("write_todos" in summary for summary in tools), tools
    assert "plan_updated" in {event["event_type"] for event in trail}
    plan = first.get("plan") or {}
    assert plan.get("body") and (plan["body"].get("steps") or plan["body"].get("todos")), plan
    assert first["graph_version"] == "research-graph.v1" and first["mode"] == "controlled"
    assert all(event["mode"] == "controlled" for event in trail)


def test_demo_02_approval_binds_the_dispatched_operation(demo):
    run = approved(available(demo)["runs"]["witness"])
    first, second = run["first"], run["second"]
    review = first["pending_review"]
    assert first["children"] == [] and first["usage"]["child_count"] == 0  # nothing dispatched before the decision
    assert len(second["children"]) >= 1, second
    child = second["children"][0]
    assert child.get("plan_id") == review["id"], (child.get("plan_id"), review["id"])
    approval = demo["client"].get(f"/records/{child['approval_id']}")
    assert json.dumps(approval).count(first["pending_review_digest"]) >= 1, "the approval does not bind the review digest"


def test_demo_03_counterdex_evidence_reaches_the_agent(demo):
    run = approved(available(demo)["runs"]["witness"])
    records = evidence_of(demo["client"], run["second"])
    assert records, "no completed child evidence"
    result = records[0]["body"]["result"]
    assert result["scientific_outcome"] == "certified_counterexample" and result["verification"] == "valid"
    assert result.get("artifacts"), "no native evidence"
    referenced = {ref for event in run["second_events"] for ref in event.get("reference_ids") or []}
    referenced |= set(json.dumps(run["second"].get("plan") or {}).split('"'))
    assert records[0]["id"] in referenced, "the agent never referenced the actual evidence"
    assert {"child_linked", "evidence_observed"} <= {event["event_type"] for event in run["second_events"]}


def test_demo_04_changed_evidence_changes_the_next_action(demo):
    runs = available(demo)["runs"]
    witness, no_witness = approved(runs["witness"]), approved(runs["no_witness"])
    outcome = evidence_of(demo["client"], no_witness["second"])[0]["body"]["result"]["scientific_outcome"]
    assert outcome in {"no_counterexample_found", "inconclusive"}, outcome
    a, b = next_action(witness["second"]), next_action(no_witness["second"])
    assert a == "review:design_plan", f"witness case next action {a}"           # may propose a pair design
    assert b in {"report", "clarification_or_observation"}, f"no-witness case next action {b}"  # no pair design
    assert a != b


def test_demo_05_inconclusive_results_are_reported_honestly(demo):
    runs = available(demo)["runs"]
    client = demo["client"]
    no_witness = approved(runs["no_witness"])
    bodies = [client.get(f"/records/{report}") for report in no_witness["second"].get("reports") or []]
    texts = bodies + [no_witness["second"].get("pending_review") or {}] + no_witness["second_events"]
    assert not sf._overclaims(texts), sf._overclaims(texts)
    missing = runs["missing_constraints"]
    final = missing.get("second") or missing["first"]  # asking before or after investigating are both honest
    action = next_action(final)
    assert action != "review:design_plan", "a design was proposed without reviewed design constraints"
    assert action in {"clarification_or_observation", "report", "review:plan"}, action


def test_demo_06_report_and_native_downloads_replay(demo, tmp_path):
    runs = available(demo)["runs"]
    client = demo["client"]
    reported = [run for run in runs.values() if (run.get("second") or {}).get("reports")]
    assert reported, "no research report was published"
    run = reported[0]
    snapshot = run["second"]
    report = client.get(f"/records/{snapshot['reports'][0]}")
    evidence_ids = {record["id"] for record in evidence_of(client, snapshot)}
    assert OBJECTIVE in json.dumps(report), "the report does not keep the exact question"
    assert evidence_ids and evidence_ids <= set(json.dumps(report).split('"')), "the report does not bind its evidence"
    download = client.raw("GET", f"/reports/{snapshot['reports'][0]}/download")
    assert download.status == 200 and json.loads(download.data)
    science = launcher.science_python()
    for record in evidence_of(client, snapshot):
        result = record["body"]["result"]
        for artifact in result.get("artifacts") or []:
            data = client.raw("GET", f"/artifacts/{artifact['id']}").data
            assert hashlib.sha256(data).hexdigest() == artifact["sha256"] and len(data) == artifact["byte_size"]
            anchor = client.get(f"/artifacts/{artifact['id']}/anchor?download=true")
            replayed = native.replay(science, str(REPO / "packages" / "groundwork_adapter"), data, {},
                                     application_anchor=anchor)
            body = replayed.get("report") or {}
            assert replayed["status"] == "passed" and body.get("expected_binding") == "matches", replayed
            assert (body.get("outcome") or {}).get("scientific_outcome") == result["scientific_outcome"]


def test_demo_07_duplicate_decisions_do_not_duplicate_science(demo):
    run = approved(available(demo)["runs"]["witness"])
    client = demo["client"]
    session = run["created"]["id"]
    decision, key, first_response = run["decision"]
    before = client.get(f"/research-sessions/{session}")
    again = client.post(f"/research-sessions/{session}/decisions", decision, key=key)   # same request replayed
    assert again == first_response
    with pytest.raises(ApiFailure) as refused:                                            # same decision, new key
        client.post(f"/research-sessions/{session}/decisions", decision, key=key + "-retry")
    assert refused.value.status == 409
    with pytest.raises(ApiFailure):                                                       # stale advance
        client.post(f"/research-sessions/{session}/advance", {"expected_revision": decision["expected_revision"]})
    after = client.get(f"/research-sessions/{session}")
    assert len(after["children"]) == len(before["children"]) and after["usage"] == before["usage"]


def test_demo_08_research_and_credentials_stay_private(demo):
    available(demo)
    client, other = demo["client"], demo["other"]
    run = approved(demo["runs"]["witness"])
    session = run["created"]["id"]
    targets = [f"/research-sessions/{session}", f"/research-sessions/{session}/events?after=-1"]
    targets += [f"/records/{report}" for report in run["second"].get("reports") or []]
    for record in evidence_of(client, run["second"]):
        targets += [f"/records/{record['id']}"] + [f"/artifacts/{a['id']}" for a in record["body"]["result"]["artifacts"]]
    for path in targets:
        assert other.raw("GET", path).status == 404, path
    visible = json.dumps([run["first"], run["second"], run["first_events"], run["second_events"]])
    for marker in ("DRBEAN-DUMMY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "api_key", "thread_id"):
        assert marker not in visible, marker


def test_demo_09_model_failure_preserves_completed_evidence():
    """Covered at present by tests/integration/test_post_science_failure_independent.py (actual Worker, actual
    Counterdex). The research-runner variant needs the integrated controlled factory; it is added once it lands."""
    pytest.xfail("NOT_AVAILABLE: research-runner model-failure variant pending the integrated controlled factory")


def test_demo_10_controlled_runs_are_labelled_controlled(demo):
    available(demo)
    client = demo["client"]
    assert demo["capabilities"].get("live_qualification") in ("not_run", None)
    for run in demo["runs"].values():
        snapshot = run.get("second") or run["first"]
        assert snapshot["mode"] == "controlled" and snapshot["usage"]["physical_calls"] == 0
        assert all(event["mode"] == "controlled" for event in run["first_events"] + run.get("second_events", []))
        attempts = client.get(f"/workspaces/{run['workspace']}/provider-attempts")
        items = attempts["items"] if isinstance(attempts, dict) else attempts
        assert all((item.get("provider") or item.get("body", {}).get("provider")) != "gemini" for item in items), items
