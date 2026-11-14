"""Offline narration regression: real graph/science, substituted signed SDK.

No live-model qualification is inferred. The fixture changes only report prose;
planning and next-action decisions consume the actual retained scientific facts.
"""
from copy import deepcopy
import hashlib

import pytest

from bean_api.main import PREFIX
from bean_api.worker import Worker
from test_research_metered_application import metered_app, consent, advance
from test_research_native_authority import reviewed_inputs
from test_scientific_http import post

__all__ = ["metered_app"]
CAPTION = "The evidence has a conditional scope."


@pytest.mark.parametrize("metered_app", ["native"], indirect=True)
@pytest.mark.parametrize("caption,accepted", [
    ("ke near 0.2 lies outside 0.10 to 0.17", False),
    (CAPTION, True),
])
def test_narration_restriction_preserves_science_and_never_retries(metered_app, monkeypatch, caption, accepted):
    client, service, worker, wire = metered_app
    wire.research_policy = True
    workspace, dataset, problem = reviewed_inputs(client)
    session = post(client, f"/workspaces/{workspace}/research-sessions", {
        "objective": "Do the reviewed measurements challenge the range, and what should be reviewed next?",
        "mode": "live", "problem_id": problem["id"], "expected_problem_digest": problem["digest"]}, "session")
    consent(client, session)
    allocation = {"physical_requests": 6, "input_tokens": 64_000, "output_tokens": 3072}
    service.allocate_provider("alice", session["id"], {**allocation, "accepted": True}, "offline-admission")
    generate = wire.generate
    before_narration = []

    async def report_prose(**kwargs):
        response = await generate(**kwargs)
        for part in response.candidates[0].content.parts:
            call = part.function_call
            if call is None or call.name != "publish_research_report":
                continue
            # The response retains its actual call ID/signature and evidence-
            # dependent next action; no scientific result is manufactured.
            assert call.args["next_action"] == "review_design"
            assert part.thought_signature == b"DRBEAN-DUMMY-signature"
            before_narration.extend(deepcopy(service.workflow.get("alice", ref)) for ref in call.args["evidence_ids"])
            call.args["text"] = caption
        return response

    monkeypatch.setattr(wire, "generate", report_prose)
    assert advance(client, session).status_code == 200
    assert worker.tick() == 1
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
    assert final["state"] == ("completed" if accepted else "failed"), final
    assert len(final["children"]) == len(final["reports"]) == len(before_narration) == 1
    child = final["children"][0]
    assert child["state"] == "completed" and child["scientific_reservations"] == 1
    evidence = client.get(PREFIX + "/records/" + child["scenarios"][0]["result_id"]).json()
    assert evidence == before_narration[0]
    assert evidence["body"]["result"]["scientific_outcome"] == "certified_counterexample"
    assert evidence["body"]["result"]["problem_digest"] == problem["digest"]
    report = client.get(PREFIX + "/reports/" + final["reports"][0]).json()
    body = report["body"]
    assert body["evidence"] == [evidence] and body["root_inputs"]["dataset"] == dataset
    assert body["deterministic_summary"]["results"][0]["scientific_outcome"] == "certified_counterexample"
    assert final["interaction"]["results"]["available"] is True
    assert final["interaction"]["results"]["commentary_available"] is accepted
    assert final["interaction"]["results"]["deterministic_summary_available"] is True
    if accepted:
        assert body["model_failure"] is None and body["commentary_status"] == "validated"
        assert body["agent_commentary"] == {"fact_ids": [evidence["id"]], "text": CAPTION,
            "next_action": "review_design", "clarification_fields": [], "scientific_authority": False,
            "authorship": "model_commentary"}
        assert body["commentary_support"] == [{"evidence_id": evidence["id"], "evidence_digest": evidence["digest"], "kind": "evidence"}]
    else:
        assert final["action"]["error_code"] == "explanation_unsupported_number"
        assert body["model_failure"] == {"code": "explanation_unsupported_number"}
        assert body["agent_commentary"] is None and body["commentary_status"] == "unavailable"
        assert body["commentary_support"] == []
    assert body["native_evidence"]
    for artifact in body["native_evidence"]:
        downloaded = client.get(artifact["download_path"])
        assert downloaded.status_code == 200
        assert hashlib.sha256(downloaded.content).hexdigest() == artifact["artifact"]["sha256"]
        assert client.get(artifact["anchor_path"]).status_code == 200
    for request in wire.requests:
        tools = {declaration.name: declaration for tool in request["config"].tools for declaration in tool.function_declarations}
        description = tools["publish_research_report"].description
        assert CAPTION in description and "exact" in description.lower()
        system = str(request["config"].system_instruction)
        assert CAPTION in system and "exact" in system.lower()
    attempts = deepcopy(client.app.state.ledger.list_attempts("alice", workspace))
    assert len(wire.requests) == len(attempts) == final["usage"]["physical_calls"] == 3
    assert final["provider_allocation"] == allocation
    assert all(attempt["state"] == "completed" for attempt in attempts)
    replacement = Worker(service.workflow, settings=client.app.state.settings,
        provider_config=worker.config, ledger=client.app.state.ledger)
    assert replacement.tick() == 0
    assert len(wire.requests) == 3
    assert client.app.state.ledger.list_attempts("alice", workspace) == attempts
    assert client.get(PREFIX + "/reports/" + report["id"]).json() == report
