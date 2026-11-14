"""Mocked provider controls, separate from any claimed live-model evaluation."""
import asyncio
from types import SimpleNamespace

import pytest

from bean_api.contracts import AssistantTurnRequest
from bean_api.conversation import AssistantResponseRecordBody, ConversationService
from bean_api.providers import ProviderFailure, ProviderResult
from bean_api.store import Store
from bean_api.workflow import DomainError, Workflow


@pytest.fixture
def setup(tmp_path):
    workflow = Workflow(Store(tmp_path / "conversation.sqlite"))
    workspace = workflow.create_workspace("alice", "Synthetic web conversation")
    return workflow, workspace["id"]


class FakeProvider:
    config = SimpleNamespace(model="fixture-model")

    def __init__(self, output=None, failure=None):
        self.output, self.failure, self.calls, self.prompts = output, failure, 0, []

    async def generate(self, operation, prompt, schema, **kwargs):
        self.calls += 1
        self.prompts.append(prompt)
        if self.failure:
            raise ProviderFailure(self.failure)
        return ProviderResult(schema.model_validate(self.output), "fixture_attempt", "fixture-model", None, "STOP")


def request(key="turn1", operation="explain", text="Explain the selected result.", revision=0, consent=True, **kwargs):
    return AssistantTurnRequest(
        operation=operation, client_operation_id=key, expected_conversation_revision=revision,
        text=text, consent={"provider": "gemini", "model": "fixture-model", "source_asset_ids": [],
                            "include_notes": True, "include_existing_values": True, "accepted": True} if consent else None,
        **kwargs,
    )


def output(text="Review the selected evidence before new work.", **kwargs):
    return {"explanation": {"fact_ids": [], "text": text, "next_action": "clarify"}, **kwargs}


def test_chat_yes_never_approves_or_dispatches(setup):
    workflow, workspace = setup
    provider = FakeProvider()
    response = asyncio.run(ConversationService(workflow, provider).submit("alice", workspace, request(text="yes"), "turn1"))
    assert provider.calls == 0
    assert response["body"]["author"] == "server"
    assert response["body"]["next_action"] == "review_plan"
    assert response["body"]["execution_approved"] is False
    assert workflow.list_records("alice", workspace, "plan") == []


def test_no_consent_manual_fallback_is_durable(setup):
    workflow, workspace = setup
    provider = FakeProvider()
    service = ConversationService(workflow, provider)
    req = request(consent=False)
    result = asyncio.run(service.submit("alice", workspace, req, "turn1"))
    assert result["body"]["code"] == "provider_consent_required"
    assert asyncio.run(service.submit("alice", workspace, req, "turn1"))["id"] == result["id"]
    assert provider.calls == 0


def test_duplicate_and_stale_turns_do_not_redeliver_model_calls(setup):
    workflow, workspace = setup
    provider = FakeProvider(output())
    service = ConversationService(workflow, provider)
    req = request()
    original = asyncio.run(service.submit("alice", workspace, req, "turn1"))
    repeated = asyncio.run(service.submit("alice", workspace, req, "turn1"))
    assert repeated["id"] == original["id"] and provider.calls == 1
    with pytest.raises(DomainError) as exc:
        asyncio.run(service.submit("alice", workspace, request(text="different"), "turn1"))
    assert exc.value.code == "idempotency_conflict"
    with pytest.raises(DomainError) as exc:
        asyncio.run(service.submit("alice", workspace, request(key="turn2", revision=0), "turn2"))
    assert exc.value.code == "stale_conversation"
    assert provider.calls == 1


def test_failed_model_preserves_turn_and_never_retries_silently(setup):
    workflow, workspace = setup
    provider = FakeProvider(failure="provider_timeout_unknown_outcome")
    service = ConversationService(workflow, provider)
    req = request()
    result = asyncio.run(service.submit("alice", workspace, req, "turn1"))
    assert result["body"]["code"] == "provider_timeout_unknown_outcome"
    assert result["body"]["author"] == "server"
    assert result["body"]["model_commentary"] is None
    assert len(workflow.list_records("alice", workspace, "user_turn")) == 1
    asyncio.run(service.submit("alice", workspace, req, "turn1"))
    assert provider.calls == 1


def test_design_constraints_are_unaccepted_and_missing_context_is_explicit(setup):
    workflow, workspace = setup
    provider = FakeProvider(output("Review the proposed times and allowance.", design_draft={
        "feasible_times": ["6/1", "8/1"], "future_hard_allowance": "1/5", "allowance_unit": "mg/L",
        "elapsed_time_confirmed": True, "hard_bound_confirmed": True, "availability_confirmed": True,
    }))
    response = asyncio.run(ConversationService(workflow, provider).submit(
        "alice", workspace, request(operation="interpret_design", text="I can sample at 6 or 8 elapsed hours with a hard allowance of 0.2 mg/L."), "turn1"))
    proposal = response["body"]["proposal"]
    assert proposal["body"]["draft"]["future_hard_allowance"] == "1/5"
    assert proposal["body"]["review_state"] == "unaccepted"
    paths = {d["field_path"] for d in proposal["body"]["diagnostics"]}
    assert {"historical_run_id", "experiment_id", "candidate_ids"} <= paths
    assert workflow.list_records("alice", workspace, "design_plan") == []
    assert response["body"]["execution_approved"] is False


def test_ambiguous_observation_requires_time_unit_allowance_and_origin(setup):
    workflow, workspace = setup
    provider = FakeProvider(output(observation_draft={"concentration": "51/10"}))
    response = asyncio.run(ConversationService(workflow, provider).submit(
        "alice", workspace, request(operation="interpret_observation", text="The value is 5.1 now."), "turn1"))
    proposal = response["body"]["proposal"]["body"]
    paths = {d["field_path"] for d in proposal["diagnostics"]}
    assert {"elapsed_time", "concentration_unit", "hard_allowance", "origin", "experiment_id"} <= paths
    assert workflow.list_records("alice", workspace, "dataset") == []


def test_hypothetical_request_cannot_silently_become_measured_history(setup):
    workflow, workspace = setup
    provider = FakeProvider(output(observation_draft={"origin": "actual", "concentration": "51/10"}))
    response = asyncio.run(ConversationService(workflow, provider).submit(
        "alice", workspace, request(operation="interpret_observation", text="What if the value were 5.1?"), "turn1"))
    assert any(d["field_path"] == "origin" for d in response["body"]["proposal"]["body"]["diagnostics"])
    assert workflow.list_records("alice", workspace, "observation_proposal") == []


def test_arbitrary_evidence_reference_and_nested_operation_are_rejected(setup):
    workflow, workspace = setup
    malformed = output()
    malformed["explanation"]["fact_ids"] = ["other_workspace:valid"]
    response = asyncio.run(ConversationService(workflow, FakeProvider(malformed)).submit("alice", workspace, request(), "turn1"))
    assert response["body"]["code"] == "invalid_fact_reference"
    assert response["body"]["provider_attempt_id"] == "fixture_attempt"
    validation = workflow.list_records("alice", workspace, "provider_validation")[0]["body"]
    assert validation["validation_outcome"] == "rejected" and validation["attempt_id"] == "fixture_attempt"
    assert response["body"]["author"] == "server"
    response2 = asyncio.run(ConversationService(workflow, FakeProvider(output(design_draft={}))).submit(
        "alice", workspace, request(key="turn2", revision=1), "turn2"))
    assert response2["body"]["code"] == "operation_scope_mismatch"


def test_wrong_workspace_record_is_hidden_before_provider_call(setup):
    workflow, workspace = setup
    other = workflow.create_workspace("alice", "Other experiment")
    suggestion = workflow.create_record("alice", other["id"], "suggestion", {"tier": "numerical_guidance"}, "s1")
    provider = FakeProvider(output())
    with pytest.raises(DomainError) as exc:
        asyncio.run(ConversationService(workflow, provider).submit(
            "alice", workspace, request(suggestion_id=suggestion["id"]), "turn1"))
    assert exc.value.status == 404 and provider.calls == 0


def test_critical_fact_card_is_server_owned_and_unsupported_prose_suppressed(setup):
    workflow, workspace = setup
    evidence = workflow.create_record("alice", workspace, "suggestion", {"tier": "numerical_guidance", "verification": "not_checked", "expected_binding": "matches"}, "evidence")
    provider = FakeProvider(output("This proves the interval and identifies the true parameter."))
    response = asyncio.run(ConversationService(workflow, provider).submit(
        "alice", workspace, request(suggestion_id=evidence["id"]), "turn1"))
    assert response["body"]["model_commentary"] is None
    assert response["body"]["commentary_status"] == "suppressed"
    assert "numerical guidance" in response["body"]["critical_statements"][0]


def test_new_model_numbers_are_withheld(setup):
    workflow, workspace = setup
    response = asyncio.run(ConversationService(workflow, FakeProvider(output("The margin is 999/1."))).submit(
        "alice", workspace, request(), "turn1"))
    assert response["body"]["commentary_suppression_reason"] == "unsupported_numeric_claim"


def test_real_workflow_evidence_envelope_supplies_outcome_and_candidate_scope(setup):
    from test_workflow import completed_pair
    workflow, workspace = setup
    _, problem, _, _, run = completed_pair(setup)
    provider = FakeProvider(output("Review this numerical candidate pair.", design_draft={
        "experiment_id": "experiment_synthetic", "feasible_times": ["6/1", "8/1"],
        "future_hard_allowance": "1/5", "allowance_unit": "mg/L", "elapsed_time_confirmed": True,
        "hard_bound_confirmed": True, "availability_confirmed": True,
        "candidate_ids": ["candidate_a", "candidate_b"],
    }))
    response = asyncio.run(ConversationService(workflow, provider).submit(
        "alice", workspace, request(operation="interpret_design", run_id=run["id"], problem_id=problem["id"],
            text="For experiment_synthetic I can sample at 6 or 8 elapsed hours with a future hard allowance of 0.2 mg/L; use candidate_a and candidate_b."), "turn1"))
    assert "not checked evidence" in response["body"]["critical_statements"][0]
    facts = response["body"]["facts"]
    assert any(f["field"] == "scientific_outcome" and f["value"] == "numerical_candidate" for f in facts)
    assert any(f["field"] == "candidate_ids" and f["value"] == ["candidate_a", "candidate_b"] for f in facts)
    proposal = response["body"]["proposal"]["body"]
    assert not any(d["field_path"] == "candidate_ids" for d in proposal["diagnostics"])
    assert proposal["review_state"] == "unaccepted"


def test_checked_suggestion_uses_binding_from_its_verification_record(setup):
    from bean_api.contracts import DesignResult
    workflow, workspace = setup
    # Schema-valid synthetic evidence oracle, not an assertion of a live checker execution.
    body = DesignResult.model_validate({
        "design_tier": "checked_pair_separation", "verification": "valid", "replay": "passed",
        "reason_code": "synthetic_test_fixture", "selected_time": "6/1",
        "options": [{"time": "6/1", "state": "evaluated", "reason_code": "positive_margin", "exact_margin": "1/10"}],
        "candidate_ids": ["candidate_a", "candidate_b"], "future_hard_allowance": "1/5", "algorithm": "synthetic_margin_v1",
        "artifacts": [{"id": "artifact_fixture", "sha256": "a" * 64, "byte_size": 12, "media_type": "application/json"}],
        "verification_record": {"checker_name": "synthetic_checker", "checker_version": "fixture-v1", "artifact_id": "artifact_fixture",
            "artifact_sha256": "a" * 64, "proposition": "Synthetic fixture proposition", "verification": "valid",
            "expected_binding": "matches", "expected_problem_digest": "b" * 64, "observed_problem_digest": "b" * 64},
    }).model_dump()
    suggestion = workflow.create_record("alice", workspace, "suggestion", body, "synthetic-suggestion")
    response = asyncio.run(ConversationService(workflow, FakeProvider(output())).submit(
        "alice", workspace, request(suggestion_id=suggestion["id"]), "turn1"))
    assert any("No future reading can fit both selected fixed candidates" in statement for statement in response["body"]["critical_statements"])
    assert any(f["field"] == "expected_binding" and f["value"] == "matches" for f in response["body"]["facts"])


@pytest.mark.parametrize("lane", ["manual", "model", "proposal", "provider_failure"])
def test_returned_assistant_records_match_the_published_server_schema(setup, lane):
    workflow, workspace = setup
    provider = FakeProvider(
        output(observation_draft={"concentration": "51/10"}) if lane == "proposal" else output(),
        failure="provider_timeout_unknown_outcome" if lane == "provider_failure" else None,
    )
    req = request(consent=lane != "manual", operation="interpret_observation" if lane == "proposal" else "explain")
    response = asyncio.run(ConversationService(workflow, provider).submit("alice", workspace, req, "turn1"))
    parsed = AssistantResponseRecordBody.model_validate(response["body"])
    assert parsed.model_dump(exclude_unset=True) == response["body"]
    assert parsed.execution_approved is False and parsed.review_required is True
    if lane == "proposal":
        assert parsed.proposal is not None
        assert parsed.proposal.body.kind == "observation"
        assert parsed.proposal_id == parsed.proposal.id
