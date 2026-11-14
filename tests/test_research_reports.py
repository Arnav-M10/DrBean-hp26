"""Immutable research reports and offline model-failure evidence retention."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from bean_api.main import PREFIX
from bean_api.research_reports import validated_commentary
from bean_api.research_tools import ApplicationResearchPorts
from bean_api.worker import Worker
from bean_api.workflow import DomainError
from test_research_agent_conditions import start, settle, approve
from test_research_controlled_application import replay_current_source, snapshot, tick
from test_research_metered_application import metered_app, consent, advance
from test_scientific_http import scientific_client, post

__all__ = ["metered_app", "scientific_client"]


def test_report_repeated_ack_is_idempotent_and_new_recommendation_is_new_snapshot(scientific_client, monkeypatch):
    client = scientific_client
    publish = ApplicationResearchPorts.publish_report
    retained = []

    async def two_recommendations(self, *, evidence_ids=None, commentary=None, **kwargs):
        if commentary is None:
            return await publish(self, evidence_ids=evidence_ids, **kwargs)
        first = await publish(self, evidence_ids=evidence_ids, commentary=commentary)
        first_record = self.workflow.get(self.runtime.actor_id, first["id"])
        first_plan = self.workflow.get(self.runtime.actor_id, first_record["body"]["research_plan_revision_id"])
        # A sibling todo tool may commit while the report acknowledgement is
        # lost. Replaying that identical report must not publish a new snapshot.
        next_plan = deepcopy(first_plan["body"])
        next_plan["steps"][0]["reason"] = "The retained evidence has been reviewed."
        revised_plan = await self.update_plan(next_plan)
        assert revised_plan["id"] != first_plan["id"]
        repeat = await publish(self, evidence_ids=evidence_ids, commentary=commentary)
        assert repeat == first
        assert self.workflow.get(self.runtime.actor_id, first["id"]) == first_record
        assert self.workflow.get(self.runtime.actor_id, first_plan["id"]) == first_plan
        changed = {**commentary, "next_action": "review_plan"}
        second = await publish(self, evidence_ids=evidence_ids, commentary=changed)
        assert second["id"] != first["id"] and second["report_digest"] != first["report_digest"]
        assert self.workflow.get(self.runtime.actor_id, first["id"]) == first_record
        assert self.workflow.get(self.runtime.actor_id, second["id"])["body"]["research_plan_revision_id"] == revised_plan["id"]
        # Lost acknowledgement after publication keeps validated commentary.
        assert await publish(self, _fallback_error="research_runtime_failure") == second
        retained.extend([first_record, self.workflow.get(self.runtime.actor_id, second["id"])])
        return first

    monkeypatch.setattr(ApplicationResearchPorts, "publish_report", two_recommendations)
    session = start(client)
    waiting = settle(client, session)
    done = approve(client, waiting, "approve")
    assert done["state"] == "completed", done["action"]
    assert set(done["reports"]) == {item["id"] for item in retained}
    assert len(done["children"]) == 1 and done["usage"]["child_count"] == 1
    first, second = [item["body"] for item in retained]
    assert first["evidence"] == second["evidence"]
    assert first["native_evidence"] == second["native_evidence"]
    assert first["agent_commentary"]["next_action"] == "review_design"
    assert second["agent_commentary"]["next_action"] == "review_plan"
    assert first["agent_commentary"]["scientific_authority"] is False
    assert first["agent_commentary"]["authorship"] == "controlled_commentary"
    assert first["commentary_status"] == second["commentary_status"] == "validated"
    assert first["deterministic_summary"] == second["deterministic_summary"]
    assert done["interaction"]["results"]["commentary_available"] is True
    assert done["interaction"]["results"]["deterministic_summary_available"] is True
    expected_support = [{"evidence_id": row["id"], "evidence_digest": row["digest"], "kind": row["kind"]} for row in first["evidence"]]
    assert first["commentary_support"] == second["commentary_support"] == expected_support
    assert tick(client) == 0
    assert snapshot(client, session)["reports"] == done["reports"]


def test_persistence_independently_refuses_unbound_or_upgraded_commentary(scientific_client, monkeypatch):
    client = scientific_client
    publish = ApplicationResearchPorts.publish_report

    async def attacking(self, *, evidence_ids=None, commentary=None, **kwargs):
        evidence = [self.workflow.get(self.runtime.actor_id, ref) for ref in evidence_ids]
        attacks = [
            {**commentary, "fact_ids": ["foreign-evidence"]},
            {**commentary, "scientific_authority": True},
            {**commentary, "authorship": "model_commentary"},
            {**commentary, "text": "Every possible model is excluded. The claim is proved."},
            {**commentary, "text": "The exact measurement is 9999999999 mg/L."},
            {**commentary, "unvalidated": "extra"},
        ]
        for attack in attacks:
            with pytest.raises(DomainError) as error:
                await publish(self, evidence_ids=evidence_ids, commentary=attack)
            assert error.value.code == "research_commentary_invalid"
        with pytest.raises(DomainError) as error:
            await publish(self, evidence_ids=["foreign-evidence"], commentary=commentary)
        assert error.value.code == "research_report_binding_invalid"
        with self.service.store.read() as conn:
            assert conn.execute("SELECT count(*) FROM entities WHERE kind='report' AND parent_id=?", (self.runtime.research_session_id,)).fetchone()[0] == 0
        assert validated_commentary(commentary, evidence, "controlled") == commentary
        return await publish(self, evidence_ids=evidence_ids, commentary=commentary)

    monkeypatch.setattr(ApplicationResearchPorts, "publish_report", attacking)
    session = start(client)
    done = approve(client, settle(client, session), "approve")
    assert done["state"] == "completed" and len(done["reports"]) == 1, done


@pytest.mark.parametrize("metered_app", ["native"], indirect=True)
def test_uncertain_substituted_gemini_after_science_keeps_summary_downloads_and_reservation(metered_app, monkeypatch, tmp_path):
    """Real gateway/ledger, substituted SDK only; zero live provider calls."""
    client, service, worker, wire = metered_app
    wire.research_policy = True
    root = Path(__file__).resolve().parents[1]
    fixture = json.loads((root / "packages/groundwork_adapter/fixtures/decision/hero-baseline.request.json").read_text())
    workspace = post(client, "/workspaces", {"name": "Offline narration loss"}, "workspace")["id"]
    dataset = post(client, f"/workspaces/{workspace}/datasets", {
        "experiment_id": "offline-report-failure", "time_origin": fixture["dataset"]["body"]["time_origin"],
        "origin": "hypothetical", "change_reason": "Public synthetic fixture", "rows": fixture["dataset"]["body"]["rows"]}, "dataset")
    problem = post(client, f"/workspaces/{workspace}/problems", {
        "dataset_id": dataset["id"], "dataset_digest": dataset["digest"],
        "domain": fixture["problem"]["body"]["domain"], "target": fixture["problem"]["body"]["target"]}, "problem")
    session = post(client, f"/workspaces/{workspace}/research-sessions", {
        "objective": "Investigate the reviewed parameter range.", "mode": "live",
        "problem_id": problem["id"], "expected_problem_digest": problem["digest"]}, "session")
    consent(client, session)
    service.allocate_provider("alice", session["id"], {"physical_requests": 6, "input_tokens": 64_000,
        "output_tokens": 3072, "accepted": True}, "offline-admission")
    generate = wire.generate

    async def uncertain_report(**kwargs):
        result = await generate(**kwargs)
        if wire.policy_calls[-1]["name"] == "publish_research_report":
            raise ConnectionError("Offline substituted SDK lost the report response")
        return result

    monkeypatch.setattr(wire, "generate", uncertain_report)
    assert advance(client, session).status_code == 200
    worker.tick()
    waiting = service.get("alice", session["id"])
    assert waiting["state"] == "waiting_review" and not waiting["children"]
    post(client, f"/research-sessions/{session['id']}/decisions", {
        "expected_revision": waiting["revision"], "pending_review_id": waiting["pending_review"]["id"],
        "expected_review_digest": waiting["pending_review_digest"], "decision": "approve", "accepted": True}, "approve")
    for _ in range(6):
        worker.tick()
        final = service.get("alice", session["id"])
        if final["state"] not in {"queued", "running", "waiting_child"}:
            break
    assert final["state"] in {"failed", "needs_reconciliation"}, final
    assert len(final["children"]) == len(final["reports"]) == 1
    assert final["interaction"]["results"]["available"] is True
    assert final["interaction"]["results"]["commentary_available"] is False
    assert final["interaction"]["results"]["deterministic_summary_available"] is True
    child = final["children"][0]
    assert child["state"] == "completed" and child["scientific_reservations"] == 1
    evidence_id = child["scenarios"][0]["result_id"]
    evidence = client.get(PREFIX + "/records/" + evidence_id).json()
    report = client.get(PREFIX + "/reports/" + final["reports"][0]).json()
    body = report["body"]
    assert body["agent_commentary"] is None and body["commentary_status"] == "unavailable"
    assert body["commentary_support"] == [] and body["evidence"] == [evidence]
    assert body["model_failure"]["code"] == final["action"]["error_code"]
    assert body["deterministic_summary"]["authorship"] == "deterministic_backend"
    assert body["deterministic_summary"]["results"][0]["scientific_outcome"] == evidence["body"]["result"]["scientific_outcome"]
    assert body["native_evidence"]
    fresh = replay_current_source(client, evidence["body"]["result"], tmp_path)
    assert fresh["replay"] == "passed" and fresh["expected_binding"] == "matches"
    attempts = deepcopy(client.app.state.ledger.list_attempts("alice", workspace))
    assert attempts[-1]["state"] == "unknown_outcome"
    assert attempts[-1]["response_metadata"]["status"] == "unknown_outcome", (final["action"], wire.policy_calls, [item["response_metadata"] for item in attempts])
    requests = len(wire.requests)
    replacement = Worker(service.workflow, settings=client.app.state.settings,
        provider_config=worker.config, ledger=client.app.state.ledger)
    assert replacement.tick() == 0
    assert len(wire.requests) == requests
    assert client.app.state.ledger.list_attempts("alice", workspace) == attempts
    assert client.get(PREFIX + "/reports/" + report["id"]).json() == report
