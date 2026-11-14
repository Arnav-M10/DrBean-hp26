"""Offline reproduction of live reference omission through the real metered graph.

The SDK response is substituted. These tests qualify contract enforcement and
retained context only, never Gemini comprehension or a successful live workflow.
"""
from copy import deepcopy
import json

import pytest

from bean_api.providers import LIVE_MODEL
from bean_api.worker import Worker
from research_efficient_wire import efficient_response
from test_research_metered_application import metered_app, consent, advance
from test_research_native_authority import reviewed_inputs
from test_scientific_http import post

__all__ = ["metered_app"]


@pytest.mark.parametrize("metered_app", ["native"], indirect=True)
@pytest.mark.parametrize("empty_references", [True, False])
def test_proposal_references_survive_intervening_plan_and_empty_list_never_gets_autofilled(
        metered_app, monkeypatch, empty_references):
    client, service, worker, wire = metered_app
    workspace, dataset, problem = reviewed_inputs(client)
    session = post(client, f"/workspaces/{workspace}/research-sessions", {
        "objective": "Review whether the supplied concentration measurements challenge the closed range.",
        "mode": "live", "problem_id": problem["id"], "expected_problem_digest": problem["digest"]}, "session")
    consent(client, session)
    allocation = {"physical_requests": 6, "input_tokens": 64_000, "output_tokens": 3072}
    service.allocate_provider("alice", session["id"], {**allocation, "accepted": True}, "offline-reference-admission")
    observed_contexts, calls, prepared_bindings = [], [], []

    async def proposal_from_context(**kwargs):
        wire.requests.append(kwargs)
        current = json.loads(kwargs["contents"][0].parts[0].text)
        reviewed, snapshot = current["reviewed_context"], current["canonical_snapshot"]
        observed_contexts.append(deepcopy(current))
        # The production context carries the actual reviewed identity before
        # and after planning; the fixture chooses its reference from that wire.
        assert reviewed["dataset"]["id"] == dataset["id"]
        assert reviewed["dataset"]["digest"] == dataset["digest"]
        assert reviewed["problem"]["body"]["dataset_id"] == reviewed["dataset"]["id"]
        results = {part.function_response.name: part.function_response.response["output"]
                   for content in kwargs["contents"] for part in content.parts if part.function_response is not None}
        if len(wire.requests) == 1:
            assert snapshot["completed_tools_in_action"] == []
            name, args = "write_todos", {"todos": [{"content": "Prepare the reviewed investigation for human approval.",
                                                    "status": "in_progress"}]}
        elif len(wire.requests) == 2:
            assert snapshot["completed_tools_in_action"] == ["write_todos"]
            assert results["write_todos"]
            signed_plan = next(part for content in kwargs["contents"] for part in content.parts
                               if part.function_call is not None)
            assert signed_plan.thought_signature == b"DRBEAN-DUMMY-signature"
            assert signed_plan.function_call.id == calls[0]["id"]
            name, args = "prepare_scientific_proposal", {
                "kind": "investigation", "reference_ids": [] if empty_references else [reviewed["dataset"]["id"]]}
        else:
            assert not empty_references and len(wire.requests) == 3
            proposal = results["prepare_scientific_proposal"]
            assert proposal["accepted"] is False
            args = {key: proposal[key] for key in ("proposal_id", "proposal_digest", "review_id", "review_digest")}
            prepared_bindings.append(deepcopy(args))
            name = "run_scientific_operation"
        call = {"name": name, "args": args, "id": f"DRBEAN-DUMMY-reference-{len(wire.requests)}", "type": "tool_call"}
        calls.append(deepcopy(call))
        return efficient_response([call], LIVE_MODEL)

    monkeypatch.setattr(wire, "generate", proposal_from_context)
    assert advance(client, session).status_code == 200
    assert worker.tick() == 1
    final = service.get("alice", session["id"])
    attempts = deepcopy(client.app.state.ledger.list_attempts("alice", workspace))
    expected_requests = 2 if empty_references else 3
    assert len(attempts) == len(wire.requests) == final["usage"]["physical_calls"] == expected_requests
    assert final["provider_allocation"] == allocation
    assert final["children"] == [] and final["reports"] == []
    assert final["usage"]["child_count"] == 0
    assert final["provider_usage"]["reported_input_tokens"] == 20 * expected_requests
    assert final["provider_usage"]["reported_output_tokens"] == 6 * expected_requests
    assert final["provider_usage"]["unresolved_attempts"] == 0
    if empty_references:
        # This exact omission used to reach research_references_invalid inside
        # the tool. The admitted SDK schema now rejects it before invocation;
        # it still consumes the physical attempt and cannot gain a reference.
        assert final["state"] == "failed" and final["pending_review"] is None
        assert final["action"]["error_code"] == "provider_malformed_tool_call"
        assert calls[-1]["args"]["reference_ids"] == [] and prepared_bindings == []
        assert attempts[-1]["state"] == "failed"
        assert attempts[-1]["response_metadata"]["validation_detail"] == {
            "reason": "schema_constraint", "tool_name": "prepare_scientific_proposal"}
        with service.store.read() as conn:
            assert conn.execute("SELECT count(*) FROM research_effects WHERE session_id=?", (session["id"],)).fetchone()[0] == 0
    else:
        assert final["state"] == "waiting_review" and final["pending_review"]["kind"] == "plan"
        assert final["action"]["error_code"] is None
        assert calls[1]["args"]["reference_ids"] == [observed_contexts[1]["reviewed_context"]["dataset"]["id"]]
        assert len(prepared_bindings) == 1
        assert final["pending_review"]["id"] == prepared_bindings[0]["review_id"]
        assert final["pending_review_digest"] == prepared_bindings[0]["review_digest"]
        assert all(attempt["state"] == "completed" for attempt in attempts)
    for request in wire.requests:
        declaration = next(declaration for tool in request["config"].tools for declaration in tool.function_declarations
                           if declaration.name == "prepare_scientific_proposal")
        assert "reviewed_context.dataset.id" in declaration.description and "Never empty" in declaration.description
        schema = declaration.parameters_json_schema["properties"]["reference_ids"]
        # The existing live-wire grammar moves numeric bounds into guidance;
        # local original-schema enforcement is proved by the refused [] above.
        assert "minItems=1" in schema["description"] and "maxItems=16" in schema["description"]
    replacement = Worker(service.workflow, settings=client.app.state.settings,
                         provider_config=worker.config, ledger=client.app.state.ledger)
    assert replacement.tick() == 0
    assert len(wire.requests) == expected_requests
    assert client.app.state.ledger.list_attempts("alice", workspace) == attempts
