"""Independent sprint probes (C): quota exhaustion, provider failure after science, report content.

Lane: controlled / real-science. The application graph, routes, consent, operator
allocation, ledger, worker and Counterdex are the real ones; only the hosted SDK
is replaced by the existing offline wire fixture, which can never reach the
network. Nothing here qualifies Gemini itself.

Checklist items: ACC-06, ACC-07, ACC-08 (evaluation/coordinator/sprint-completion.v1.json).
"""
import hashlib
import json
from pathlib import Path

from google.genai import errors
import pytest

from bean_api.main import PREFIX
from bean_api.worker import Worker
import test_research_metered_application as metered
from test_research_metered_application import advance, consent, create_session, post

ROOT = Path(__file__).resolve().parents[1]
metered_app = metered.metered_app  # the existing offline-SDK application fixture


def quota_error():
    return errors.ClientError(429, {"error": {"code": 429, "status": "RESOURCE_EXHAUSTED",
                                              "message": "Synthetic offline quota response"}})


def forbid_controlled_fallback(monkeypatch):
    calls = []

    def refuse(*args, **kwargs):
        calls.append(args)
        raise AssertionError("A live session must never fall back to the controlled policy")
    monkeypatch.setattr("bean_api.research_controlled.build_controlled_research_model", refuse)
    return calls


def counts(service):
    with service.store.read() as conn:
        return {table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                for table in ("jobs", "provider_attempts", "research_actions")}


def test_acc08_provider_429_is_one_charged_attempt_with_a_clear_code_and_no_retry_or_fallback(metered_app, monkeypatch):
    client, service, worker, wire = metered_app
    session = create_session(client)
    consent(client, session)
    service.allocate_provider("alice", session["id"], {"physical_requests": 4, "input_tokens": 48_000,
                                                       "output_tokens": 1024, "accepted": True}, "c-sprint-grant")

    def exhausted():
        raise quota_error()
    wire.before_request = exhausted
    assert advance(client, session).status_code == 200
    worker.research.tick()
    current = service.get("alice", session["id"])
    attempts = client.app.state.ledger.list_attempts("alice", session["workspace_id"])
    # Exactly one dispatched request and one charged attempt; nothing else.
    assert len(wire.constructions) == 1, wire.constructions
    assert len(attempts) == 1 and current["usage"]["physical_calls"] == 1
    assert attempts[0]["state"] in {"failed", "unknown_outcome"}
    assert current["action"]["error_code"] == "provider_rate_limited", current["action"]
    assert current["state"] in {"failed", "paused", "needs_reconciliation"}, current["state"]
    assert counts(service)["jobs"] == 0
    # Further worker passes neither retry nor switch model.
    for _ in range(2):
        Worker(service.workflow, settings=client.app.state.settings, provider_config=worker.config,
               ledger=client.app.state.ledger).tick()
    assert len(wire.constructions) == 1
    assert len(client.app.state.ledger.list_attempts("alice", session["workspace_id"])) == 1
    assert forbid_controlled_fallback(monkeypatch) == []


def test_acc08_exhausted_session_allocation_refuses_before_any_request(metered_app, monkeypatch):
    client, service, worker, wire = metered_app
    fallback = forbid_controlled_fallback(monkeypatch)
    session = create_session(client)
    consent(client, session)
    service.allocate_provider("alice", session["id"], {"physical_requests": 1, "input_tokens": 24_000,
                                                       "output_tokens": 512, "accepted": True}, "c-sprint-grant")
    assert advance(client, session).status_code == 200
    worker.research.tick()
    current = service.get("alice", session["id"])
    # The second turn is refused by the ledger before the SDK sees it.
    assert len(wire.requests) == 1
    assert current["action"]["error_code"] == "provider_budget_exhausted"
    again = post(client, f"/research-sessions/{session['id']}/advance", {"expected_revision": current["revision"]}, "again")
    assert again.status_code in {409, 403}, again.text
    assert again.json()["code"] in {"research_provider_allocation_exhausted", "research_not_advanceable"}, again.json()
    assert len(wire.requests) == 1 and fallback == [] and counts(service)["jobs"] == 0


@pytest.mark.parametrize("metered_app", ["native"], indirect=True)
def test_acc07_acc06_provider_failure_after_real_science_keeps_evidence_and_report_content(metered_app, monkeypatch, tmp_path):
    """Baseline science completes through the live path, then the next provider turn hits a 429."""
    client, service, worker, wire = metered_app
    wire.research_policy = True
    fixture = json.loads((ROOT / "packages/groundwork_adapter/fixtures/decision/hero-baseline.request.json").read_text())

    def accepted(path, body, key):
        response = post(client, path, body, key)
        assert response.status_code in {200, 201, 202}, response.text
        return response.json()

    workspace = accepted("/workspaces", {"name": "C sprint: failure after science"}, "workspace")["id"]
    dataset = accepted(f"/workspaces/{workspace}/datasets", {
        "experiment_id": "c-sprint-synthetic", "time_origin": fixture["dataset"]["body"]["time_origin"],
        "origin": "hypothetical", "change_reason": "Public synthetic fixture readings",
        "rows": fixture["dataset"]["body"]["rows"]}, "dataset")
    problem = accepted(f"/workspaces/{workspace}/problems", {
        "dataset_id": dataset["id"], "dataset_digest": dataset["digest"],
        "domain": fixture["problem"]["body"]["domain"], "target": fixture["problem"]["body"]["target"]}, "problem")
    session = accepted(f"/workspaces/{workspace}/research-sessions", {
        "objective": "Do the reviewed measurements challenge this range, and what should I do next?", "mode": "live",
        "problem_id": problem["id"], "expected_problem_digest": problem["digest"]}, "session")
    consent(client, session)
    service.allocate_provider("alice", session["id"], {"physical_requests": 8, "input_tokens": 64_000,
                                                       "output_tokens": 4096, "accepted": True}, "c-sprint-grant")
    assert advance(client, session).status_code == 200
    worker.tick()
    waiting = service.get("alice", session["id"])
    assert waiting["state"] == "waiting_review" and not waiting["children"]
    accepted(f"/research-sessions/{session['id']}/decisions", {
        "expected_revision": waiting["revision"], "pending_review_id": waiting["pending_review"]["id"],
        "expected_review_digest": waiting["pending_review_digest"], "decision": "approve", "accepted": True}, "approve")

    # Let the approved child run, then fail the first provider turn after evidence exists.
    def fail_after_science():
        with service.store.read() as conn:
            done = conn.execute("SELECT count(*) FROM jobs WHERE state='completed'").fetchone()[0]
        if done:
            raise quota_error()
    wire.before_request = fail_after_science
    for _ in range(4):
        Worker(service.workflow, settings=client.app.state.settings, provider_config=worker.config,
               ledger=client.app.state.ledger).tick()
        current = service.get("alice", session["id"])
        if current["state"] != "waiting_child":
            break
    assert current["action"]["error_code"] == "provider_rate_limited", current
    assert len(current["children"]) == 1 and current["children"][0]["state"] == "completed"
    requests_after_failure = len(wire.requests)
    evidence_id = current["children"][0]["scenarios"][0]["result_id"]
    evidence = client.get(PREFIX + "/records/" + evidence_id)
    assert evidence.status_code == 200
    result = evidence.json()["body"]["result"]
    assert result["scientific_outcome"] == "certified_counterexample"
    for ref in result["artifacts"]:
        native = client.get(PREFIX + "/artifacts/" + ref["id"])
        anchor = client.get(PREFIX + "/artifacts/" + ref["id"] + "/anchor?download=true")
        assert native.status_code == anchor.status_code == 200
        assert len(native.content) == ref["byte_size"]
        assert hashlib.sha256(native.content).hexdigest() == ref["sha256"]
    # ACC-08 within ACC-07: the failure is not retried by later passes.
    Worker(service.workflow, settings=client.app.state.settings, provider_config=worker.config,
           ledger=client.app.state.ledger).tick()
    assert len(wire.requests) == requests_after_failure


@pytest.mark.xfail(strict=True, reason="F-SPRINT-REPORT-COMMENTARY (A, PR #60): the downloaded research report omits the "
                   "agent's validated explanation and recommendation; remove this marker when it passes")
@pytest.mark.parametrize("metered_app", ["native"], indirect=True)
def test_acc06_downloaded_report_carries_the_validated_explanation_and_recommendation(metered_app):
    """Complete a baseline through the live path and download the research report."""
    client, service, worker, wire = metered_app
    wire.research_policy = True
    fixture = json.loads((ROOT / "packages/groundwork_adapter/fixtures/decision/hero-baseline.request.json").read_text())

    def accepted(path, body, key):
        response = post(client, path, body, key)
        assert response.status_code in {200, 201, 202}, response.text
        return response.json()

    workspace = accepted("/workspaces", {"name": "C sprint: report content"}, "workspace")["id"]
    dataset = accepted(f"/workspaces/{workspace}/datasets", {
        "experiment_id": "c-sprint-report", "time_origin": fixture["dataset"]["body"]["time_origin"],
        "origin": "hypothetical", "change_reason": "Public synthetic fixture readings",
        "rows": fixture["dataset"]["body"]["rows"]}, "dataset")
    problem = accepted(f"/workspaces/{workspace}/problems", {
        "dataset_id": dataset["id"], "dataset_digest": dataset["digest"],
        "domain": fixture["problem"]["body"]["domain"], "target": fixture["problem"]["body"]["target"]}, "problem")
    session = accepted(f"/workspaces/{workspace}/research-sessions", {
        "objective": "Do the reviewed measurements challenge this range, and what should I do next?", "mode": "live",
        "problem_id": problem["id"], "expected_problem_digest": problem["digest"]}, "session")
    consent(client, session)
    service.allocate_provider("alice", session["id"], {"physical_requests": 6, "input_tokens": 64_000,
                                                       "output_tokens": 3072, "accepted": True}, "c-sprint-grant")
    assert advance(client, session).status_code == 200
    worker.tick()
    waiting = service.get("alice", session["id"])
    accepted(f"/research-sessions/{session['id']}/decisions", {
        "expected_revision": waiting["revision"], "pending_review_id": waiting["pending_review"]["id"],
        "expected_review_digest": waiting["pending_review_digest"], "decision": "approve", "accepted": True}, "approve")
    for _ in range(4):
        Worker(service.workflow, settings=client.app.state.settings, provider_config=worker.config,
               ledger=client.app.state.ledger).tick()
        final = service.get("alice", session["id"])
        if final["state"] != "waiting_child":
            break
    assert final["state"] == "completed" and final["reports"], final
    download = client.get(PREFIX + f"/reports/{final['reports'][-1]}/download")
    assert download.status_code == 200
    body = json.loads(download.content)["body"]
    evidence_ids = {item["id"] for item in body["evidence"]}
    text = json.dumps(body)
    # ACC-06: the agent's validated explanation and recommendation must be in the downloaded report,
    # bound to evidence the report contains, and never presented as scientific authority.
    commentary = body.get("agent_commentary") or body.get("explanation") or body.get("recommendations")
    assert commentary, f"Downloaded report has no agent explanation or recommendation; fields: {sorted(body)}"
    cited = set(json.dumps(commentary).split('"')) & evidence_ids
    assert cited, "The explanation cites no evidence contained in the report"
    assert "proof" not in text.lower().replace("not proof", "").replace("no proof", "")
