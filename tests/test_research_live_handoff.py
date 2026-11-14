"""Canonical review handoff with signed substituted SDK decisions, never live AI."""
from copy import deepcopy
import json

import pytest

from bean_api.main import PREFIX
from bean_api.providers import LIVE_MODEL
from bean_api.worker import Worker
from research_efficient_wire import efficient_calls, efficient_response
from test_research_metered_application import metered_app, consent, advance
from test_research_native_authority import reviewed_inputs
from test_scientific_http import post

__all__ = ["metered_app"]
BINDINGS = ("proposal_id", "proposal_digest", "review_id", "review_digest")


@pytest.mark.parametrize("metered_app", ["native"], indirect=True)
@pytest.mark.parametrize("mode", ["approve", "reject", "unknown_proposal", "changed_review", "repeat_planner"])
def test_prepare_hands_off_before_more_planning_and_resume_obeys_canonical_review(metered_app, monkeypatch, mode):
    client, service, worker, wire = metered_app
    workspace, dataset, problem = reviewed_inputs(client)
    session = post(client, f"/workspaces/{workspace}/research-sessions", {
        "objective": "Test whether the reviewed concentration readings challenge the closed parameter range.",
        "mode": "live", "problem_id": problem["id"], "expected_problem_digest": problem["digest"]}, "session")
    consent(client, session)
    allocation = {"physical_requests": 6, "input_tokens": 64_000, "output_tokens": 3072}
    service.allocate_provider("alice", session["id"], {**allocation, "accepted": True}, "offline-review-admission")
    returned_proposals, dispatched_calls = [], []

    async def signed_decision(**kwargs):
        wire.requests.append(kwargs)
        sequence = len(wire.requests)
        current = json.loads(kwargs["contents"][0].parts[0].text)
        reviewed = current["reviewed_context"]
        results = {part.function_response.name: part.function_response.response["output"]
                   for content in kwargs["contents"] for part in content.parts if part.function_response is not None}
        if sequence == 1 or mode == "repeat_planner" and sequence == 3:
            name, args = "write_todos", {"todos": [{"content": "Prepare the reviewed investigation.", "status": "in_progress"}]}
        elif sequence == 2 or mode == "repeat_planner" and sequence == 4:
            name, args = "prepare_scientific_proposal", {"kind": "investigation", "reference_ids": [reviewed["dataset"]["id"]]}
        elif "prepare_scientific_proposal" in results:
            prepared = results["prepare_scientific_proposal"]
            returned_proposals.append(deepcopy(prepared))
            assert prepared["accepted"] is False
            name = prepared["next_tool"]
            if mode == "reject":
                assert prepared["review_decision"] == "rejected" and name == "request_clarification"
                args = {"fields": ["scientific_scope"], "question": "Which scope should be separately reviewed after the rejection?"}
            else:
                assert prepared["review_decision"] == "approved" and name == "run_scientific_operation"
                args = {key: prepared[key] for key in BINDINGS}
                if mode == "unknown_proposal":
                    args["proposal_id"] = "plan_unknown_scope"
                elif mode == "changed_review":
                    args["review_digest"] = "0" * 64
            signed_prepare = next(part for content in kwargs["contents"] for part in content.parts
                                  if part.function_call is not None and part.function_call.name == "prepare_scientific_proposal")
            assert signed_prepare.thought_signature == b"DRBEAN-DUMMY-signature"
            assert signed_prepare.function_call.id == dispatched_calls[1]["id"]
        elif "run_scientific_operation" in results:
            assert mode == "approve"
            # This existing offline helper chooses a report action from the
            # actual canonical scientific evidence, never from dataset names.
            calls = efficient_calls(kwargs["contents"], sequence)
            dispatched_calls.extend(deepcopy(calls))
            return efficient_response(calls, LIVE_MODEL)
        else:
            raise AssertionError("Unexpected SDK continuation; do not invent an approval or scientific result")
        call = {"name": name, "args": args, "id": f"DRBEAN-DUMMY-handoff-{sequence}", "type": "tool_call"}
        dispatched_calls.append(deepcopy(call))
        return efficient_response([call], LIVE_MODEL)

    monkeypatch.setattr(wire, "generate", signed_decision)
    assert advance(client, session).status_code == 200
    assert worker.tick() == 1
    waiting = service.get("alice", session["id"])
    assert waiting["state"] == "waiting_review" and waiting["pending_review"]["kind"] == "plan"
    assert waiting["children"] == [] and waiting["reports"] == []
    assert waiting["usage"]["physical_calls"] == waiting["usage"]["logical_turns"] == 2
    assert returned_proposals == []  # The pending tool has not returned approval-shaped data to the model.
    assert [call["name"] for call in dispatched_calls] == ["write_todos", "prepare_scientific_proposal"]
    assert waiting["pending_review"]["body"]["dataset_id"] == dataset["id"]
    attempts_before = deepcopy(client.app.state.ledger.list_attempts("alice", workspace))
    with service.store.read() as conn:
        assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM approvals").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM research_effects WHERE session_id=? AND kind='investigation'", (session["id"],)).fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM entities WHERE kind='plan'").fetchone()[0] == 1

    # Reopening/reading and malformed approval scopes never admit another turn.
    for _ in range(2):
        assert client.get(PREFIX + f"/research-sessions/{session['id']}").json() == waiting
        assert client.get(PREFIX + f"/research-sessions/{session['id']}/events?after=-1").status_code == 200
        assert worker.tick() == 0
    decision = {"expected_revision": waiting["revision"], "pending_review_id": waiting["pending_review"]["id"],
                "expected_review_digest": waiting["pending_review_digest"], "decision": "reject" if mode == "reject" else "approve", "accepted": True}
    for field, value in (("pending_review_id", "plan_unknown_scope"), ("expected_review_digest", "0" * 64)):
        refused = client.post(PREFIX + f"/research-sessions/{session['id']}/decisions", json={**decision, field: value},
                              headers={"Idempotency-Key": "wrong-scope-" + field})
        assert refused.status_code == 409 and refused.json()["code"] == "stale_review"
    assert client.app.state.ledger.list_attempts("alice", workspace) == attempts_before
    assert len(wire.requests) == 2 and service.get("alice", session["id"])["provider_allocation"] == allocation
    if mode == "repeat_planner":
        # The observed todo→prepare→todo→prepare loop cannot spend turns 3/4
        # before review: first prepare already paused the real graph.
        assert worker.tick() == 0 and len(wire.requests) == 2
        return

    approved = post(client, f"/research-sessions/{session['id']}/decisions", decision, "human-decision")
    retried = post(client, f"/research-sessions/{session['id']}/decisions", decision, "human-decision")
    assert retried["action"]["id"] == approved["action"]["id"]
    for _ in range(8):
        worker.tick()
        final = service.get("alice", session["id"])
        if final["state"] not in {"queued", "running", "waiting_child"}:
            break
    assert len(returned_proposals) == 1
    prepared = returned_proposals[0]
    assert prepared["proposal_id"] == prepared["review_id"] == waiting["pending_review"]["id"]
    assert prepared["proposal_digest"] == prepared["review_digest"] == waiting["pending_review_digest"]
    if mode == "approve":
        assert dispatched_calls[2]["args"] == {key: prepared[key] for key in BINDINGS}
        assert final["state"] == "completed" and len(final["children"]) == len(final["reports"]) == 1
        assert final["children"][0]["state"] == "completed" and final["children"][0]["scientific_reservations"] == 1
    elif mode == "reject":
        assert final["state"] == "waiting_review" and final["pending_review"]["kind"] == "research_clarification"
        assert final["children"] == [] and final["reports"] == []
    else:
        assert final["state"] == "failed" and final["children"] == []
        assert final["action"]["error_code"] == ("research_review_context_missing" if mode == "unknown_proposal" else "research_review_changed")
    attempts = deepcopy(client.app.state.ledger.list_attempts("alice", workspace))
    assert len(wire.requests) == len(attempts) == (4 if mode == "approve" else 3)
    assert final["provider_allocation"] == allocation
    for request in wire.requests:
        declaration = next(declaration for tool in request["config"].tools for declaration in tool.function_declarations
                           if declaration.name == "run_scientific_operation")
        assert "approval" in declaration.description
    replacement = Worker(service.workflow, settings=client.app.state.settings,
                         provider_config=worker.config, ledger=client.app.state.ledger)
    assert replacement.tick() == 0
    assert client.app.state.ledger.list_attempts("alice", workspace) == attempts
