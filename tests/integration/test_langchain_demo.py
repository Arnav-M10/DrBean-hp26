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


def next_step(snapshot) -> str:
    """The evidence-dependent next step the agent added to its maintained plan (the last plan step's title)."""
    steps = ((snapshot.get("plan") or {}).get("body") or {}).get("steps") or []
    return steps[-1]["title"] if steps else ""


def run_session(client, label, *, widen=False, constraints=True, problem=True):
    workspace = client.post("/workspaces", {"name": f"C demo {label}"}, label=f"{label}-ws")["id"]
    dataset = client.post(f"/workspaces/{workspace}/datasets", HERO["dataset"], label=f"{label}-dataset")
    body = {**HERO["problem"], "dataset_id": dataset["id"], "dataset_digest": dataset["digest"]}
    if widen:
        parameter = HERO["problem"]["target"]["parameter"]
        domain = HERO["problem"]["domain"][parameter]
        body["target"] = {**HERO["problem"]["target"], "lower": domain["lower"], "upper": domain["upper"]}
    problem = client.post(f"/workspaces/{workspace}/problems", body, label=f"{label}-problem") if problem else None
    request = {"schema_version": "DB-RESEARCH-1", "objective": OBJECTIVE, "mode": "controlled"}
    if problem_bound := problem:
        request.update(problem_id=problem_bound["id"], expected_problem_digest=problem_bound["digest"])
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
        ("witness", {}), ("no_witness", {"widen": True}), ("missing_constraints", {"constraints": False}),
        ("missing_inputs", {"problem": False}))}
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
    client = demo["client"]
    assert client.get(f"/records/{review['id']}")["digest"] == first["pending_review_digest"]
    decisions = [event for event in run["second_events"] if event["event_type"] == "decision_recorded"]
    assert decisions, "no decision event"
    decision = client.get(f"/records/{decisions[0]['reference_ids'][0]}")
    assert decision["kind"] == "research_decision" and decision["body"]["decision"] == "approve"
    assert decision["body"]["pending_review_id"] == review["id"]
    assert decision["body"]["expected_review_digest"] == first["pending_review_digest"]
    assert decision["body"]["approval_id"] == child["approval_id"]  # the approval it created is the one dispatched


def test_demo_03_counterdex_evidence_reaches_the_agent(demo):
    run = approved(available(demo)["runs"]["witness"])
    records = evidence_of(demo["client"], run["second"])
    assert records, "no completed child evidence"
    result = records[0]["body"]["result"]
    assert result["scientific_outcome"] == "certified_counterexample" and result["verification"] == "valid"
    assert result.get("artifacts"), "no native evidence"
    observed = {ref for event in run["second_events"] if event["event_type"] == "evidence_observed"
                for ref in event.get("reference_ids") or []}
    assert records[0]["id"] in observed, "the agent never read the actual evidence"
    assert all(child["state"] == "completed" for child in run["second"]["children"])


def test_demo_04_changed_evidence_changes_the_next_action(demo):
    runs = available(demo)["runs"]
    witness, no_witness = approved(runs["witness"]), approved(runs["no_witness"])
    outcome = evidence_of(demo["client"], no_witness["second"])[0]["body"]["result"]["scientific_outcome"]
    assert outcome in {"no_counterexample_found", "inconclusive"}, outcome
    witness_outcome = evidence_of(demo["client"], witness["second"])[0]["body"]["result"]["scientific_outcome"]
    assert witness_outcome == "certified_counterexample"
    a, b = next_step(witness["second"]), next_step(no_witness["second"])
    assert "pair design" in a.lower(), f"witness case next step {a!r}"               # may propose a pair design
    assert "pair design" not in b.lower() and b, f"no-witness case next step {b!r}"  # proposes no pair design
    assert a != b
    for run in (witness, no_witness):  # a next step is a proposal only: no design was created or approved
        assert next_action(run["second"]) != "review:design_plan" or run is witness
        assert all(child["kind"] == "run" for child in run["second"]["children"])


def test_demo_05_inconclusive_results_are_reported_honestly(demo):
    runs = available(demo)["runs"]
    client = demo["client"]
    no_witness = approved(runs["no_witness"])
    bodies = [client.get(f"/records/{report}") for report in no_witness["second"].get("reports") or []]
    assert bodies, "the inconclusive investigation published no report"
    limitations = " ".join(bodies[0]["body"].get("limitations") or []).lower()
    assert "does not prove" in limitations, bodies[0]["body"].get("limitations")
    texts = bodies + no_witness["second_events"] + [no_witness["second"].get("plan") or {}]
    assert not sf._overclaims(texts), sf._overclaims(texts)
    missing = runs["missing_constraints"]   # design constraints were never supplied: none may be invented
    final = missing.get("second") or missing["first"]
    assert next_action(final) != "review:design_plan", "a design was proposed without reviewed design constraints"
    inputs = runs["missing_inputs"]          # no reviewed problem at all: clarify, never compute
    final = inputs.get("second") or inputs["first"]
    assert final["children"] == [] and final["usage"]["child_count"] == 0, final["children"]
    assert next_action(final) in {"review:research_clarification", "clarification_or_observation", "report",
                                  "state:completed", "state:ready", "state:paused"}, next_action(final)
    assert not sf._overclaims([final, inputs["first_events"]])


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
    assert again["id"] == first_response["id"] == session
    with pytest.raises(ApiFailure) as refused:                                            # same decision, new key
        client.post(f"/research-sessions/{session}/decisions", decision, key=key + "-retry")
    assert refused.value.status == 409
    with pytest.raises(ApiFailure):                                                       # stale advance
        client.post(f"/research-sessions/{session}/advance", {"expected_revision": decision["expected_revision"]})
    after = client.get(f"/research-sessions/{session}")
    assert [child["id"] for child in after["children"]] == [child["id"] for child in before["children"]]
    assert after["usage"] == before["usage"] and after["revision"] == before["revision"]
    assert len(before["children"]) == 1  # one approved review, one scientific child


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


def test_demo_09_model_failure_preserves_completed_evidence(tmp_path, monkeypatch):
    """The ordinary in-process Worker runs the research graph; its controlled model fails, as the metered gateway
    reports a provider failure, once the approved child has completed. Evidence, native bytes and replay survive.
    (An exception outside the runner's handled types instead escapes the worker: F-RESEARCH-WORKER-UNGUARDED.)"""
    import importlib
    try:
        controlled = importlib.import_module("bean_api.research_controlled")
    except ImportError:
        pytest.xfail("NOT_AVAILABLE: no controlled research factory (bean_api.research_controlled) in this build")
    from fastapi.testclient import TestClient
    from langchain_core.messages import ToolMessage
    from bean_api.config import Settings
    from bean_api.main import PREFIX, create_app
    from bean_api.providers import ProviderFailure
    from bean_api.worker import Worker

    class FailsAfterChild(controlled.ControlledResearchModel):
        def _generate(self, messages, stop=None, run_manager=None, **kwargs):
            if any(isinstance(m, ToolMessage) and '"state": "completed"' in str(m.content).replace('":"', '": "')
                   and "evidence_" in str(m.content) for m in messages):
                raise ProviderFailure("provider_request_failed_unknown_outcome")  # as the metered gateway reports
            return super()._generate(messages, stop=stop, run_manager=run_manager, **kwargs)
    monkeypatch.setattr(controlled, "build_controlled_research_model", lambda: FailsAfterChild())
    science = launcher.science_python()
    settings = Settings(database_path=str(tmp_path / "db.sqlite3"), blob_dir=str(tmp_path / "sources"),
                        artifact_dir=str(tmp_path / "artifacts"), auth_file=str(tmp_path / "none.json"),
                        counterdex_python=science, auth_tokens={"alice": "d" * 40})
    with TestClient(create_app(settings)) as http:
        http.headers["Authorization"] = "Bearer " + "d" * 40
        def post(path, body, key):
            response = http.post(PREFIX + path, json=body, headers={"Idempotency-Key": key})
            assert response.status_code in (200, 201, 202), (path, response.text)
            return response.json()
        if not (http.get(PREFIX + "/capabilities").json().get("deepagents") or {}).get("dispatch_enabled"):
            pytest.xfail("NOT_AVAILABLE: research dispatch is not enabled in this build")
        workspace = post("/workspaces", {"name": "C demo model failure"}, "ws")["id"]
        dataset = post(f"/workspaces/{workspace}/datasets", HERO["dataset"], "ds")
        problem = post(f"/workspaces/{workspace}/problems", {**HERO["problem"], "dataset_id": dataset["id"],
                                                              "dataset_digest": dataset["digest"]}, "pr")
        session = post(f"/workspaces/{workspace}/research-sessions", {"schema_version": "DB-RESEARCH-1",
                       "objective": OBJECTIVE, "problem_id": problem["id"], "expected_problem_digest": problem["digest"],
                       "mode": "controlled"}, "session")
        post(f"/research-sessions/{session['id']}/advance", {"expected_revision": session["revision"]}, "advance")
        worker = Worker(http.app.state.workflow, settings=http.app.state.settings)
        def drive():
            for _ in range(40):
                worker.tick()
                snapshot = http.get(PREFIX + f"/research-sessions/{session['id']}").json()
                if snapshot["state"] not in MOVING:
                    return snapshot
            raise AssertionError(f"research session still {snapshot['state']}")
        first = drive()
        assert first["state"] == "waiting_review", first["state"]
        post(f"/research-sessions/{session['id']}/decisions", {"expected_revision": first["revision"],
             "pending_review_id": first["pending_review"]["id"], "expected_review_digest": first["pending_review_digest"],
             "decision": "approve", "accepted": True}, "decision")
        final = drive()
        assert final["state"] == "failed", final["state"]                                    # an honest failure
        assert final["action"]["error_code"] == "provider_request_failed_unknown_outcome"
        # Oracle revision R1 (sprint, 2026-11-14): the frozen DEMO-09 predicate requires an honest failure, not
        # the absence of every report. A deterministic failure report is accepted only if it is honest: no model
        # commentary, backend authorship without scientific authority, the same failure code and the original outcome.
        for report_id in final["reports"]:
            body = json.loads(http.get(PREFIX + f"/reports/{report_id}/download").content)["body"]
            assert body.get("agent_commentary") is None and body.get("commentary_status") == "unavailable", body.get("commentary_status")
            summary = body["deterministic_summary"]
            assert summary["authorship"] == "deterministic_backend" and summary["scientific_authority"] is False
            assert body["model_failure"]["code"] == final["action"]["error_code"]
            assert {row["scientific_outcome"] for row in summary["results"]} == {"certified_counterexample"}
        child = final["children"][0]
        assert child["state"] == "completed" and child.get("result_id")
        run = http.get(PREFIX + f"/runs/{child['id']}").json()
        evidence = http.get(PREFIX + f"/records/{run['scenarios'][0]['result_id']}").json()
        result = evidence["body"]["result"]
        assert result["scientific_outcome"] == "certified_counterexample" and result["verification"] == "valid"
        artifact = result["artifacts"][0]
        data = http.get(PREFIX + f"/artifacts/{artifact['id']}").content
        assert hashlib.sha256(data).hexdigest() == artifact["sha256"]
        anchor = http.get(PREFIX + f"/artifacts/{artifact['id']}/anchor?download=true").json()
        replayed = native.replay(science, str(REPO / "packages" / "groundwork_adapter"), data, {},
                                 application_anchor=anchor)
        assert replayed["status"] == "passed"
        assert (replayed.get("report") or {}).get("outcome", {}).get("scientific_outcome") == "certified_counterexample"
        assert final["usage"]["physical_calls"] == 0


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
