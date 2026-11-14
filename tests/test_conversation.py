"""Controlled provider boundaries and real-science conversation fact checks.

The follow-up controls execute actual approved HTTP science with synthetic input
and explicit hypothetical readings. No test qualifies live-model behavior.
"""
import asyncio
from copy import deepcopy
from types import SimpleNamespace

import pytest

from bean_api.contracts import AssistantTurnRequest
from bean_api.conversation import AssistantResponseRecordBody, ConversationService
from bean_api.providers import ProviderFailure, ProviderResult
from bean_api.store import Store
from bean_api.workflow import DomainError, Workflow
import test_native_followup_workflow as native_followup

scientific_client = native_followup.scientific_client
computed_history = native_followup.computed_history
computed_design = native_followup.computed_design


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


def test_baseline_explanation_prompt_teaches_complete_policy_templates_and_real_fact_ids(setup):
    from test_workflow import create_problem, dataset_body
    workflow, workspace = setup
    dataset = workflow.create_dataset("alice", workspace, dataset_body(), "baseline-data")
    problem = create_problem(workflow, workspace, dataset)
    target_id = f"{problem['id']}:target"
    text = ("The reviewed interval is [1/10 1/h, 1/5 1/h]. "
            "The claim lower bound is 1/10 1/h. The claim upper bound is 1/5 1/h. "
            "Compatibility does not identify the true model.")
    authored = output(text)
    authored["explanation"]["fact_ids"] = [target_id]
    provider = FakeProvider(authored)
    result = asyncio.run(ConversationService(workflow, provider).submit(
        "alice", workspace, request(problem_id=problem["id"]), "turn1"))["body"]
    assert result["model_commentary"] == text
    assert result["commentary_status"] == "unverified_model_commentary"
    prompt, = provider.prompts
    from bean_api.ai_prompts import COMMENTARY_POLICY_VERSION
    assert COMMENTARY_POLICY_VERSION in prompt
    assert "The returned design remains numerical guidance." in prompt
    assert "No separation was established on the reviewed grid." in prompt
    assert "This design is numerical guidance without checked pair separation." in prompt
    assert "The result is inconclusive." in prompt
    assert "same record has design_tier=numerical_guidance AND verification=not_checked" in prompt
    assert "never combine different records or uncited context" in prompt
    assert "The reviewed interval is [<lower> 1/h, <upper> 1/h]." in prompt
    assert "The claim lower bound is <lower> 1/h." in prompt
    assert "The claim upper bound is <upper> 1/h." in prompt
    assert "Otherwise never paraphrase scientific verdicts" in prompt
    assert "Never substitute domain bounds or candidate rates for claim bounds" in prompt
    assert "actual id strings in explanation.fact_ids" in prompt and target_id in prompt
    assert "For explain, return no drafts. For interpret_design, extract only explicitly supplied" in prompt
    assert "For interpret_observation, distinguish explicitly hypothetical from actual data" in prompt


@pytest.mark.parametrize("text,reason", [
    ("A compatible value outside your range was verified under these assumptions.", "unsupported_claim"),
    ("Without any doubt this proves the interval.", "unsupported_claim"),
    ("The claim lower bound is 1/5 1/h.", "unsupported_numeric_claim"),
    ("The reviewed interval is [1/5 1/h, 1/10 1/h].", "unsupported_numeric_claim"),
])
def test_revised_baseline_prompt_keeps_unsupported_prose_and_wrong_role_values_suppressed(setup, text, reason):
    """Authored controls, not the unretained wording from the live model response."""
    from test_workflow import create_problem, dataset_body
    workflow, workspace = setup
    dataset = workflow.create_dataset("alice", workspace, dataset_body(), "baseline-data")
    problem = create_problem(workflow, workspace, dataset)
    authored = output(text)
    authored["explanation"]["fact_ids"] = [f"{problem['id']}:target"]
    result = asyncio.run(ConversationService(workflow, FakeProvider(authored)).submit(
        "alice", workspace, request(problem_id=problem["id"]), "turn1"))["body"]
    assert result["model_commentary"] is None
    assert result["commentary_suppression_reason"] == reason
    assert result["facts"] and result["critical_statements"]
    assert result["execution_approved"] is False


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


def bound_suggestion(workflow, workspace, problem_digest, key="bound-suggestion", **changes):
    """Schema-valid synthetic checked evidence; no claim of scientific execution."""
    from bean_api.contracts import DesignResult
    body = {
        "design_tier": "checked_pair_separation", "verification": "valid", "replay": "passed",
        "reason_code": "synthetic_fixture", "selected_time": "6/1",
        "options": [{"time": "6/1", "state": "evaluated", "reason_code": "positive_margin", "exact_margin": "1/10"}],
        "candidate_ids": ["candidate_a", "candidate_b"], "future_hard_allowance": "1/5", "algorithm": "fixture_v1",
        "artifacts": [{"id": "artifact_fixture", "sha256": "a" * 64, "byte_size": 12, "media_type": "application/json"}],
        "verification_record": {"checker_name": "fixture_checker", "checker_version": "fixture_v1", "artifact_id": "artifact_fixture",
            "artifact_sha256": "a" * 64, "proposition": "Synthetic control only", "verification": "valid",
            "expected_binding": "matches", "expected_problem_digest": problem_digest, "observed_problem_digest": problem_digest},
    }
    body.update(changes)
    body["verification_record"]["verification"] = body["verification"]
    return workflow.create_record("alice", workspace, "suggestion", DesignResult.model_validate(body).model_dump(), key)


def test_suggestion_from_another_problem_revision_is_rejected_before_a_turn(setup):
    from test_workflow import completed_pair, create_problem, dataset_body
    workflow, workspace = setup
    dataset, old_problem, _, _, _ = completed_pair(setup)
    suggestion = bound_suggestion(workflow, workspace, old_problem["digest"])
    changed = workflow.create_dataset("alice", workspace, dataset_body(dataset["id"]), "changed-dataset")
    new_problem = create_problem(workflow, workspace, changed, "changed-problem")
    provider = FakeProvider(output())
    with pytest.raises(DomainError) as caught:
        asyncio.run(ConversationService(workflow, provider).submit(
            "alice", workspace, request(problem_id=new_problem["id"], suggestion_id=suggestion["id"]), "turn1"))
    assert caught.value.code == "reference_binding_mismatch"
    assert provider.calls == 0
    assert workflow.list_records("alice", workspace, "user_turn") == []


def test_matching_problem_binding_preserves_exact_facts_and_dataset_origin(setup):
    from test_workflow import completed_pair
    workflow, workspace = setup
    _, problem, _, _, _ = completed_pair(setup)
    suggestion = bound_suggestion(workflow, workspace, problem["digest"])
    response = asyncio.run(ConversationService(workflow, FakeProvider(output())).submit(
        "alice", workspace, request(problem_id=problem["id"], suggestion_id=suggestion["id"]), "turn1"))
    assert any(f["field"] == "problem_digest" and f["value"] == problem["digest"] for f in response["body"]["facts"])
    assert any(f["field"] == "origin" and f["value"] == "synthetic" for f in response["body"]["facts"])
    assert any("synthetic examples" in statement for statement in response["body"]["critical_statements"])


def test_matching_problem_is_insufficient_to_associate_a_suggestion_with_a_run(setup):
    from test_workflow import completed_pair
    workflow, workspace = setup
    _, problem, _, _, run = completed_pair(setup)
    suggestion = bound_suggestion(workflow, workspace, problem["digest"])
    provider = FakeProvider(output())
    service = ConversationService(workflow, provider)
    with pytest.raises(DomainError) as caught:
        asyncio.run(service.submit("alice", workspace, request(run_id=run["id"], suggestion_id=suggestion["id"]), "turn1"))
    assert caught.value.code == "suggestion_run_binding_unavailable"
    assert caught.value.status == 409 and provider.calls == 0
    # A refusal does not consume a conversation revision; independent inspection remains usable.
    response = asyncio.run(service.submit("alice", workspace, request(suggestion_id=suggestion["id"]), "turn1"))
    assert response["body"]["conversation_revision"] == 1
    assert any("No future reading can fit both" in statement for statement in response["body"]["critical_statements"])


def test_unbound_suggestion_cannot_be_attached_to_a_selected_problem(setup):
    from test_workflow import prepared
    workflow, workspace = setup
    _, problem, _, _ = prepared(setup)
    suggestion = workflow.create_record("alice", workspace, "suggestion", {"tier": "numerical_guidance"}, "unbound")
    provider = FakeProvider(output())
    with pytest.raises(DomainError) as caught:
        asyncio.run(ConversationService(workflow, provider).submit(
            "alice", workspace, request(problem_id=problem["id"], suggestion_id=suggestion["id"]), "turn1"))
    assert caught.value.code == "suggestion_problem_binding_unavailable"
    assert provider.calls == 0


def test_duplicate_candidate_ids_leave_a_blocking_design_clarification(setup):
    from test_workflow import completed_pair
    workflow, workspace = setup
    _, _, _, _, run = completed_pair(setup)
    provider = FakeProvider(output(design_draft={"candidate_ids": ["candidate_a", "candidate_a"]}))
    response = asyncio.run(ConversationService(workflow, provider).submit(
        "alice", workspace, request(operation="interpret_design", run_id=run["id"]), "turn1"))
    assert any(d["field_path"] == "candidate_ids" and d["blocking"] for d in response["body"]["proposal"]["body"]["diagnostics"])
    assert response["body"]["next_action"] == "clarify"
    assert workflow.list_records("alice", workspace, "design_plan") == []


@pytest.mark.parametrize("first_state", ["valid", "invalid", "inconclusive"])
def test_candidate_specific_follow_up_remains_visible_when_the_pair_is_invalid(setup, first_state):
    workflow, workspace = setup
    def candidate(identity, state):
        return {"candidate_id": identity, "verification": state, "outside_closed_claim": identity == "candidate_b",
                "is_counterexample": False, "violating_observation_ids": ["followup_row"] if state == "invalid" else [],
                "unresolved_observation_ids": ["followup_row"] if state == "inconclusive" else []}
    candidates = [candidate("candidate_a", first_state), candidate("candidate_b", "invalid")]
    suggestion = bound_suggestion(workflow, workspace, "b" * 64, design_tier="unavailable", verification="invalid", replay="failed",
        selected_time=None, candidate_results=candidates, native_replay={
            "replay": "failed", "verification": "invalid", "integrity": "passed", "recorded_result_matches": True,
            "dataset_origin": "hypothetical", "fresh_checked": {"unneeded_proof_transcript": "x" * 8000}})
    response = asyncio.run(ConversationService(workflow, FakeProvider(output())).submit(
        "alice", workspace, request(suggestion_id=suggestion["id"]), "turn1"))
    facts, statements = response["body"]["facts"], response["body"]["critical_statements"]
    assert any(f["field"] == "candidate_results" and f["value"] == suggestion["body"]["candidate_results"] for f in facts)
    assert any(f["field"] == "native_replay" and f["value"]["recorded_result_matches"] is True and "fresh_checked" not in f["value"] for f in facts)
    assert any(f["field"] == "verification" and f["value"] == "invalid" for f in facts)
    assert any("candidate_b is excluded" in statement and "all allowed assignments" in statement for statement in statements)
    assert any("hypothetical observations" in statement for statement in statements)
    expected = {"valid": "candidate_a remains compatible", "invalid": "candidate_a is excluded", "inconclusive": "candidate_a has status inconclusive"}[first_state]
    assert any(expected in statement for statement in statements)
    assert not any("No future reading can fit both" in statement for statement in statements)
    assert response["body"]["execution_approved"] is False


def test_mismatched_replay_cannot_promote_candidate_compatibility(setup):
    workflow, workspace = setup
    suggestion = bound_suggestion(workflow, workspace, "b" * 64,
        candidate_results=[{"candidate_id": "candidate_a", "verification": "valid", "outside_closed_claim": False, "is_counterexample": False}],
        native_replay={"recorded_result_matches": False, "integrity": "failed"})
    response = asyncio.run(ConversationService(workflow, FakeProvider(output())).submit(
        "alice", workspace, request(suggestion_id=suggestion["id"]), "turn1"))
    assert not any("candidate_a remains compatible" in statement for statement in response["body"]["critical_statements"])
    assert not any("No future reading can fit both" in statement for statement in response["body"]["critical_statements"])
    assert any("No checked scientific conclusion" in statement for statement in response["body"]["critical_statements"])


def test_explicit_controlled_mode_never_claims_gemini_authorship_or_a_provider_attempt(setup):
    workflow, workspace = setup
    class ControlledProvider(FakeProvider):
        def capabilities(self):
            return {"execution_mode": "controlled", "dispatch_enabled": False}

    provider = ControlledProvider(output(observation_draft={"concentration": "51/10"}))
    req = request(operation="interpret_observation")
    service = ConversationService(workflow, provider)
    response = asyncio.run(service.submit("alice", workspace, req, "turn1"))
    assert provider.calls == 0
    assert response["body"]["author"] == "server"
    assert response["body"]["provider_attempt_id"] is None
    assert response["body"]["model_commentary"] is None
    assert response["body"]["code"] == "controlled_provenance_unavailable"
    assert response["body"].get("proposal") is None
    assert workflow.list_records("alice", workspace, "assistant_proposal") == []
    assert asyncio.run(service.submit("alice", workspace, req, "turn1"))["id"] == response["id"]
    AssistantResponseRecordBody.model_validate(response["body"])


def test_many_candidate_summaries_preserve_provenance_within_response_bounds():
    records = [{"id": f"evidence_{scenario}", "body": {
        "scientific_outcome": "inconclusive", "expected_binding": "matches", "origin": "hypothetical",
        "candidate_results": [{"candidate_id": f"candidate_{scenario}_{index}", "verification": "valid"} for index in range(16)],
    }} for scenario in range(2)]
    facts, statements = ConversationService(None, None)._facts(records)
    assert len(statements) == 32
    assert any("hypothetical observations" in statement for statement in statements)
    assert any("investigation is inconclusive" in statement for statement in statements)
    assert "Additional candidate-specific results" in statements[-1]
    assert sum(len(f["value"]) for f in facts if f["field"] == "candidate_results") == 32


def test_checked_separation_statement_is_conditional_on_the_selected_time_pair_and_allowance(setup):
    workflow, workspace = setup
    suggestion = bound_suggestion(workflow, workspace, "b" * 64)
    response = asyncio.run(ConversationService(workflow, FakeProvider(output())).submit(
        "alice", workspace, request(suggestion_id=suggestion["id"]), "turn1"))
    statement, = [s for s in response["body"]["critical_statements"] if s.startswith("No future reading can fit both")]
    assert "selected fixed candidates at the selected reviewed time" in statement
    assert "under the stated future hard allowance" in statement
    assert "that fixed pair and time" in statement
    facts = {f["field"]: f["value"] for f in response["body"]["facts"]}
    assert facts["candidate_ids"] == ["candidate_a", "candidate_b"]
    assert facts["selected_time"] == "6/1"
    assert facts["future_hard_allowance"] == "1/5"


@pytest.mark.parametrize("failure", ["problem_binding", "native_integrity"])
def test_hypothetical_origin_remains_visible_when_scientific_evidence_is_rejected(setup, failure):
    from bean_api.contracts import DesignResult
    workflow, workspace = setup
    original = bound_suggestion(workflow, workspace, "b" * 64)
    body = {**original["body"], "design_tier": "unavailable", "verification": "invalid", "replay": "failed",
            "selected_time": None, "candidate_results": [{"candidate_id": "candidate_a", "verification": "valid",
                "outside_closed_claim": False, "is_counterexample": False}],
            "native_replay": {"dataset_origin": "hypothetical", "integrity": "passed", "recorded_result_matches": True}}
    body["verification_record"] = {**body["verification_record"], "verification": "invalid"}
    if failure == "problem_binding":
        body["verification_record"].update(expected_binding="mismatch", observed_problem_digest="c" * 64)
    else:
        body["native_replay"].update(integrity="failed", recorded_result_matches=False)
    rejected = workflow.create_record("alice", workspace, "suggestion", DesignResult.model_validate(body).model_dump(), "rejected")
    response = asyncio.run(ConversationService(workflow, FakeProvider(output())).submit(
        "alice", workspace, request(suggestion_id=rejected["id"]), "turn1"))
    statements = response["body"]["critical_statements"]
    assert any("hypothetical observations" in statement for statement in statements)
    expected_warning = "expected binding mismatches" if failure == "problem_binding" else "No checked scientific conclusion"
    assert any(expected_warning in statement for statement in statements)
    assert not any("No future reading can fit both" in statement or "candidate_a remains compatible" in statement for statement in statements)
    assert any(f["field"] == "dataset_origin" and f["value"] == "hypothetical" for f in response["body"]["facts"])
    assert response["body"]["execution_approved"] is False


def complete_design_draft(**changes):
    return {"experiment_id": "experiment_synthetic", "elapsed_time_confirmed": True, "feasible_times": ["8/1"],
            "future_hard_allowance": "1/5", "allowance_unit": "mg/L", "hard_bound_confirmed": True,
            "availability_confirmed": True, "candidate_ids": ["candidate_a", "candidate_b"], **changes}


@pytest.mark.parametrize("operation", ["interpret_design", "interpret_observation"])
def test_draft_experiment_mismatch_requires_review_without_changing_the_proposal(setup, operation):
    from test_workflow import completed_pair
    workflow, workspace = setup
    _, _, _, _, run = completed_pair(setup)
    if operation == "interpret_design":
        draft = {"design_draft": complete_design_draft(experiment_id="different_experiment")}
    else:
        draft = {"observation_draft": {"experiment_id": "different_experiment", "origin": "actual", "elapsed_time": "8/1",
            "concentration": "17/5", "hard_allowance": "1/5", "time_unit": "h", "concentration_unit": "mg/L",
            "source_description": "User-declared acquired reading", "same_experiment_confirmed": True}}
    provider = FakeProvider(output(**draft, clarifications=[{
        "code": "model_note", "field_path": "experiment_id", "message": "Model-supplied note", "blocking": False}]))
    response = asyncio.run(ConversationService(workflow, provider).submit(
        "alice", workspace, request(operation=operation, run_id=run["id"]), "turn1"))
    proposal = response["body"]["proposal"]["body"]
    assert proposal["draft"]["experiment_id"] == "different_experiment"
    assert any(d["field_path"] == "experiment_id" and d["blocking"] for d in proposal["diagnostics"])
    assert response["body"]["next_action"] == "clarify"
    assert len(workflow.list_records("alice", workspace, "dataset")) == 1
    assert workflow.list_records("alice", workspace, "design_plan") == []


def test_design_pair_cannot_be_assembled_across_different_problem_results(setup):
    from bean_api.contracts import PlanBody
    from test_workflow import create_problem, dataset_body, numerical_pair, prepared
    workflow, workspace = setup
    old_dataset, old_problem, _, _ = prepared(setup)
    dataset = workflow.create_dataset("alice", workspace, dataset_body(old_dataset["id"]), "revised-dataset")
    problem = create_problem(workflow, workspace, dataset, "revised-problem")
    plan = workflow.create_plan("alice", workspace, PlanBody(
        problem_id=problem["id"], problem_digest=problem["digest"], dataset_id=dataset["id"], scenarios=[
            {"id": "baseline", "kind": "baseline", "label": "Reviewed baseline", "problem_id": problem["id"], "problem_digest": problem["digest"]},
            {"id": "comparison", "kind": "optional", "label": "Reviewed prior revision", "problem_id": old_problem["id"], "problem_digest": old_problem["digest"]},
        ]).model_dump(), "comparison-plan")
    approval = workflow.approve_plan("alice", plan["id"], problem["id"], plan["digest"], "comparison-approval")
    run = workflow.start_run("alice", plan["id"], approval["id"], "comparison-run")
    workflow.mark_running("alice", run["id"], "test-worker")
    for scenario, scenario_problem in (("baseline", problem), ("comparison", old_problem)):
        evidence = numerical_pair(scenario_problem)
        if scenario == "comparison":
            for candidate, identity in zip(evidence["candidates"], ("candidate_c", "candidate_d"), strict=True):
                candidate["id"] = identity
        workflow.reserve_scenario("alice", run["id"], scenario)
        workflow.complete_scenario("alice", run["id"], scenario, evidence)
    workflow.finish_run("alice", run["id"])
    provider = FakeProvider(output(design_draft=complete_design_draft(candidate_ids=["candidate_a", "candidate_c"])))
    response = asyncio.run(ConversationService(workflow, provider).submit(
        "alice", workspace, request(operation="interpret_design", run_id=run["id"]), "turn1"))
    proposal = response["body"]["proposal"]["body"]
    assert proposal["draft"]["candidate_ids"] == ["candidate_a", "candidate_c"]
    assert any(d["field_path"] == "candidate_ids" and d["blocking"] for d in proposal["diagnostics"])
    assert workflow.list_records("alice", workspace, "design_plan") == []


def test_design_pair_and_experiment_from_the_same_reviewed_result_remain_usable(setup):
    from test_workflow import completed_pair
    workflow, workspace = setup
    _, _, _, _, run = completed_pair(setup)
    provider = FakeProvider(output(design_draft=complete_design_draft()))
    provider.output["explanation"]["next_action"] = "review_design"
    response = asyncio.run(ConversationService(workflow, provider).submit(
        "alice", workspace, request(operation="interpret_design", run_id=run["id"]), "turn1"))
    assert response["body"]["proposal"]["body"]["diagnostics"] == []
    assert response["body"]["next_action"] == "review_design"
    assert response["body"]["execution_approved"] is False


@pytest.mark.parametrize("field,changes", [
    ("candidate_ids", {"candidate_ids": ["candidate_a23", "candidate_b"]}),
    ("scientific_problem_digest", {"scientific_problem_digest": "a123b" + "a" * 59}),
])
def test_identifier_and_digest_digits_cannot_ground_a_numerical_claim(setup, field, changes):
    workflow, workspace = setup
    suggestion = bound_suggestion(workflow, workspace, "b" * 64, **changes)
    provider = FakeProvider(output("The margin is 23."))
    provider.output["explanation"]["fact_ids"] = [f"{suggestion['id']}:{field}"]
    response = asyncio.run(ConversationService(workflow, provider).submit(
        "alice", workspace, request(suggestion_id=suggestion["id"]), "turn1"))
    assert response["body"]["commentary_suppression_reason"] == "unsupported_numeric_claim"
    assert response["body"]["model_commentary"] is None


def test_uncited_scientific_fact_cannot_ground_a_numerical_claim(setup):
    workflow, workspace = setup
    suggestion = bound_suggestion(workflow, workspace, "b" * 64)
    provider = FakeProvider(output("The future hard allowance is 1/5."))
    provider.output["explanation"]["fact_ids"] = [f"{suggestion['id']}:selected_time"]
    response = asyncio.run(ConversationService(workflow, provider).submit(
        "alice", workspace, request(suggestion_id=suggestion["id"]), "turn1"))
    assert response["body"]["commentary_suppression_reason"] == "unsupported_numeric_claim"
    assert any(f["field"] == "future_hard_allowance" and f["value"] == "1/5" for f in response["body"]["facts"])


@pytest.mark.parametrize("quantity", ["0.2 mg/L", "0.2mg/L"])
def test_equivalent_decimal_is_grounded_by_its_cited_exact_rational(setup, quantity):
    workflow, workspace = setup
    suggestion = bound_suggestion(workflow, workspace, "b" * 64)
    provider = FakeProvider(output(f"The reviewed future hard allowance is {quantity}."))
    provider.output["explanation"]["fact_ids"] = [f"{suggestion['id']}:future_hard_allowance"]
    response = asyncio.run(ConversationService(workflow, provider).submit(
        "alice", workspace, request(suggestion_id=suggestion["id"]), "turn1"))
    assert response["body"]["model_commentary"] == provider.output["explanation"]["text"]
    assert response["body"]["commentary_status"] == "unverified_model_commentary"


@pytest.mark.parametrize("prose", ["The margin is 999mg/L.", "The selected time is 999h."])
def test_attached_units_do_not_hide_unsupported_numeric_claims(setup, prose):
    workflow, workspace = setup
    response = asyncio.run(ConversationService(workflow, FakeProvider(output(prose))).submit(
        "alice", workspace, request(), "turn1"))
    assert response["body"]["commentary_suppression_reason"] == "unsupported_numeric_claim"
    assert response["body"]["model_commentary"] is None


@pytest.mark.parametrize("prose", [
    "The interval is proven.", "This is globally optimal experimental design.",
    "All alternative parameter values have been eliminated.",
])
def test_known_universal_or_global_design_overclaims_are_suppressed(setup, prose):
    workflow, workspace = setup
    response = asyncio.run(ConversationService(workflow, FakeProvider(output(prose))).submit(
        "alice", workspace, request(), "turn1"))
    assert response["body"]["commentary_suppression_reason"] == "unsupported_claim"
    assert response["body"]["model_commentary"] is None
    assert response["body"]["critical_statements"]


def complete_native_followup(history, choice):
    """Use the backend's public review/approval routes and actual fixed-pair checker."""
    from bean_api.main import PREFIX
    from bean_api.worker import Worker
    from test_scientific_http import post
    client = history["client"]
    value, survivors = native_followup.reading_for(history, choice)
    _, dataset, problem, body = native_followup.revised_inputs(history, value)
    plan = post(client, f"/workspaces/{history['workspace']}/plans", {
        "expected_current_revision_id": problem["id"], "plan": body}, "conversation-followup-plan")
    approval = post(client, f"/plans/{plan['id']}/approvals", {
        "expected_current_revision_id": problem["id"], "expected_plan_digest": plan["digest"],
        "accepted": True}, "conversation-followup-approval")
    run = post(client, f"/plans/{plan['id']}/runs", {
        "approval_id": approval["id"], "expected_plan_digest": plan["digest"]}, "conversation-followup-run")
    assert Worker(client.app.state.workflow, settings=client.app.state.settings).tick() == 1
    finished = client.get(PREFIX + f"/runs/{run['id']}").json()
    assert finished["state"] == "completed", finished
    evidence = client.get(PREFIX + f"/records/{finished['scenarios'][0]['result_id']}").json()
    return dataset, problem, finished, evidence, survivors


@pytest.mark.parametrize("choice", [0, 1, 2], ids=["first_survives", "second_survives", "both_excluded"])
def test_real_followup_explanations_preserve_individual_results_and_hypothetical_origin(computed_design, choice):
    from bean_api.main import PREFIX
    from bean_api.worker import Worker
    from test_scientific_http import post
    history, client = computed_design, computed_design["client"]
    dataset, problem, run, evidence, survivors = complete_native_followup(history, choice)
    response = post(client, f"/workspaces/{history['workspace']}/assistant-turns", {
        "operation": "explain", "client_operation_id": "explain-followup", "expected_conversation_revision": 0,
        "text": "Explain which selected candidates remain compatible after this hypothetical observation.",
        "problem_id": problem["id"], "run_id": run["id"]}, "explain-followup")["body"]
    assert response["author"] == "server" and response["provider_attempt_id"] is None
    assert response["model_commentary"] is None and response["execution_approved"] is False
    facts, statements = response["facts"], response["critical_statements"]
    result = evidence["body"]["result"]
    assert any(f["record_id"] == evidence["id"] and f["field"] == "candidate_results" and f["value"] == result["candidate_results"] for f in facts)
    assert any(f["record_id"] == dataset["id"] and f["field"] == "origin" and f["value"] == "hypothetical" for f in facts)
    assert any("hypothetical observations" in statement for statement in statements)
    for candidate_id in history["design_result"]["candidate_ids"]:
        if candidate_id in survivors:
            assert any(f"Fixed candidate {candidate_id} remains compatible" in statement and "does not identify the true model" in statement for statement in statements)
        else:
            assert any(f"Fixed candidate {candidate_id} is excluded" in statement and "does not establish that all allowed assignments are excluded" in statement for statement in statements)
    if not survivors:
        assert result["scientific_outcome"] == "inconclusive"
        assert any("investigation is inconclusive" in statement for statement in statements)
    assert client.get(PREFIX + f"/records/{evidence['id']}").json() == evidence
    assert client.get(PREFIX + f"/records/{history['design_record']['id']}").json() == history["design_record"]
    assert client.get(PREFIX + f"/artifacts/{history['design_result']['artifacts'][0]['id']}").content == history["design_content"]
    assert client.get(PREFIX + f"/workspaces/{history['workspace']}/provider-attempts").json() == []
    assert Worker(client.app.state.workflow, settings=client.app.state.settings).tick() == 0


def test_both_candidates_remaining_historically_compatible_is_valid_for_the_design(computed_design):
    from test_scientific_http import post
    history, client = computed_design, computed_design["client"]
    assert len(history["design_result"]["candidate_results"]) == 2
    assert all(item["verification"] == "valid" for item in history["design_result"]["candidate_results"])
    response = post(client, f"/workspaces/{history['workspace']}/assistant-turns", {
        "operation": "explain", "client_operation_id": "explain-design", "expected_conversation_revision": 0,
        "text": "Explain the selected pair and reviewed future measurement.",
        "suggestion_id": history["design_record"]["id"]}, "explain-design")["body"]
    assert any("selected reviewed time" in statement for statement in response["critical_statements"])
    assert response["author"] == "server" and response["provider_attempt_id"] is None


@pytest.mark.parametrize("binding,code,status", [
    ("matches", "followup_separation_contradiction", 409),
    ("not_supplied", "reference_binding_mismatch", 422),
    ("wrong_digest", "reference_binding_mismatch", 422),
])
def test_authenticated_separating_followup_cannot_report_both_selected_candidates_compatible(computed_design, monkeypatch, binding, code, status):
    from bean_api.main import PREFIX
    history, client = computed_design, computed_design["client"]
    _, problem, run, evidence, _ = complete_native_followup(history, 0)
    workflow, provider = client.app.state.workflow, client.app.state.provider
    original_get = workflow.get
    attempted_calls = []

    def corrupted_read(actor, record_id, kind=None):
        record = original_get(actor, record_id, kind)
        if record_id == evidence["id"]:
            record = deepcopy(record)
            for candidate in record["body"]["result"]["candidate_results"]:
                candidate.update(verification="valid", violating_observation_ids=[], unresolved_observation_ids=[])
            if binding == "not_supplied":
                record["body"]["result"].update(problem_digest=None, expected_binding="not_supplied")
            elif binding == "wrong_digest":
                record["body"]["result"]["problem_digest"] = "0" * 64
        return record

    async def forbidden_provider_call(*args, **kwargs):
        attempted_calls.append(True)
        raise AssertionError("Contradictory follow-up facts reached the provider")

    with monkeypatch.context() as patch:
        patch.setattr(workflow, "get", corrupted_read)
        patch.setattr(provider, "generate", forbidden_provider_call)
        response = client.post(PREFIX + f"/workspaces/{history['workspace']}/assistant-turns", json={
            "operation": "explain", "client_operation_id": "contradictory-followup", "expected_conversation_revision": 0,
            "text": "Explain the reviewed follow-up evidence.", "problem_id": problem["id"], "run_id": run["id"],
            "consent": {"provider": "gemini", "model": "fixture-model", "source_asset_ids": [],
                "include_notes": True, "include_existing_values": True, "accepted": True}},
            headers={"Idempotency-Key": "contradictory-followup"})
    assert response.status_code == status, response.text
    assert response.json()["code"] == code
    assert attempted_calls == []
    assert workflow.list_records("alice", history["workspace"], "user_turn") == []
    assert client.get(PREFIX + f"/records/{evidence['id']}").json() == evidence
    assert client.get(PREFIX + f"/runs/{run['id']}").json() == run
    assert client.get(PREFIX + f"/records/{history['design_record']['id']}").json() == history["design_record"]
    assert client.get(PREFIX + f"/workspaces/{history['workspace']}/provider-attempts").json() == []


def test_controlled_unsupported_followup_read_without_a_digest_remains_explainable(computed_design, monkeypatch):
    from bean_api.main import PREFIX
    from test_scientific_http import post
    history, client = computed_design, computed_design["client"]
    dataset, problem, run, evidence, _ = complete_native_followup(history, 0)
    workflow = client.app.state.workflow
    original_get = workflow.get

    def unsupported_read(actor, record_id, kind=None):
        record = original_get(actor, record_id, kind)
        if record_id == evidence["id"]:
            # Controlled failure projection only: the actual native evidence
            # and its authenticated reviewed lineage remain immutable.
            record = deepcopy(record)
            record["body"]["result"] = {
                "scientific_outcome": "unsupported", "verification": "unsupported", "expected_binding": "not_supplied",
                "replay": "unsupported", "reason_code": "controlled_runtime_unavailable", "problem_id": problem["id"],
                "candidates": [], "artifacts": []}
        return record

    with monkeypatch.context() as patch:
        patch.setattr(workflow, "get", unsupported_read)
        response = post(client, f"/workspaces/{history['workspace']}/assistant-turns", {
            "operation": "explain", "client_operation_id": "unsupported-followup", "expected_conversation_revision": 0,
            "text": "Explain the unavailable follow-up check and how to continue manually.",
            "problem_id": problem["id"], "run_id": run["id"]}, "unsupported-followup")["body"]
    assert response["author"] == "server" and response["provider_attempt_id"] is None
    assert any("scientific capability is unavailable" in statement for statement in response["critical_statements"])
    assert any("hypothetical observations" in statement for statement in response["critical_statements"])
    assert any(f["record_id"] == evidence["id"] and f["field"] == "verification" and f["value"] == "unsupported" for f in response["facts"])
    assert any(f["record_id"] == dataset["id"] and f["field"] == "origin" and f["value"] == "hypothetical" for f in response["facts"])
    assert client.get(PREFIX + f"/records/{evidence['id']}").json() == evidence
    assert client.get(PREFIX + f"/workspaces/{history['workspace']}/provider-attempts").json() == []


def test_http_explanation_guard_withholds_known_attacks_without_changing_real_science(computed_design, monkeypatch):
    """Authored provider payloads challenge the HTTP guard beside actual native science."""
    import socket
    from bean_api.main import PREFIX
    from test_scientific_http import post

    history, client = computed_design, computed_design["client"]

    def deny_socket(*args, **kwargs):
        pytest.fail("The local explanation fixture must never dispatch a network request")

    monkeypatch.setattr(socket.socket, "connect", deny_socket)
    monkeypatch.setattr(socket.socket, "connect_ex", deny_socket)

    class LocalAuthoredExplanationProvider(FakeProvider):
        """A local response-validation fixture, with no transport or live-model evidence."""

        async def generate(self, operation, prompt, schema, **kwargs):
            self.calls += 1
            self.prompts.append(prompt)
            return ProviderResult(schema.model_validate(self.output), f"local-authored-{self.calls}",
                                  "fixture-model", None, "STOP")

    provider = LocalAuthoredExplanationProvider()
    monkeypatch.setattr(client.app.state.provider, "generate", provider.generate)
    suggestion = history["design_record"]
    allowance_id = f"{suggestion['id']}:future_hard_allowance"
    examples = [
        ("The reviewed future hard allowance is 0.2 mg/L.", None),
        ("Without any doubt this proves the interval.", "unsupported_claim"),
        ("Sample again at 7hrs to separate them.", "unsupported_numeric_claim"),
        ("This establishes that the interval is correct.", "unsupported_claim"),
    ]
    original_records = [history[key] for key in ("dataset", "problem", "evidence", "design_record")]
    prior_facts, prior_statements = None, None
    for revision, (prose, expected_rejection) in enumerate(examples):
        provider.output = {"explanation": {"fact_ids": [allowance_id], "text": prose, "next_action": "stop"}}
        key = f"guarded-commentary-{revision}"
        body = {"operation": "explain", "client_operation_id": key, "expected_conversation_revision": revision,
                "text": "Explain only the reviewed scientific facts and their limits.",
                "problem_id": history["problem"]["id"], "suggestion_id": suggestion["id"],
                "consent": {"provider": "gemini", "model": "fixture-model", "source_asset_ids": [],
                    "include_notes": True, "include_existing_values": True, "accepted": True}}
        response = post(client, f"/workspaces/{history['workspace']}/assistant-turns", body, key)
        result = response["body"]
        assert result["execution_approved"] is False
        assert result["facts"] and result["critical_statements"]
        if expected_rejection is None:
            assert result["model_commentary"] == prose
            assert result["commentary_status"] == "unverified_model_commentary"
            prior_facts, prior_statements = result["facts"], result["critical_statements"]
        else:
            assert result["model_commentary"] is None and result["commentary_status"] == "suppressed"
            assert result["commentary_suppression_reason"] == expected_rejection
            assert result["facts"] == prior_facts and result["critical_statements"] == prior_statements
        assert client.get(PREFIX + f"/records/{response['id']}").json() == response
        assert post(client, f"/workspaces/{history['workspace']}/assistant-turns", body, key) == response
        assert provider.calls == revision + 1
        for record in original_records:
            assert client.get(PREFIX + f"/records/{record['id']}").json() == record
        assert client.get(PREFIX + f"/artifacts/{history['design_result']['artifacts'][0]['id']}").content == history["design_content"]
        assert client.get(PREFIX + f"/workspaces/{history['workspace']}/provider-attempts").json() == []
    assert len(client.get(PREFIX + f"/workspaces/{history['workspace']}/records?kind=assistant_response").json()) == len(examples)


def test_http_checked_design_narration_requires_authentic_cited_gates_and_vetoes_uncited_bad_native_state(computed_design, monkeypatch):
    """Real design facts support narration; a controlled bad-read projection vetoes it."""
    import socket
    from bean_api.main import PREFIX
    from test_scientific_http import post

    history, client = computed_design, computed_design["client"]
    suggestion = history["design_record"]
    fields = ("selected_time", "future_hard_allowance", "design_tier", "verification", "expected_binding", "replay")
    cited_ids = [f"{suggestion['id']}:{field}" for field in fields]
    design = history["design_result"]
    prose = (f"The checked design selects {design['selected_time']} h with a hard allowance of "
             f"{design['future_hard_allowance']} mg/L for this reviewed pair.")

    def deny_socket(*args, **kwargs):
        pytest.fail("The local checked-design narration fixture must not dispatch a network request")

    monkeypatch.setattr(socket.socket, "connect", deny_socket)
    monkeypatch.setattr(socket.socket, "connect_ex", deny_socket)

    class LocalCheckedDesignNarrationProvider(FakeProvider):
        """Authored explanation payload only; no model or transport is constructed."""

        async def generate(self, operation, prompt, schema, **kwargs):
            self.calls += 1
            self.prompts.append(prompt)
            return ProviderResult(schema.model_validate(self.output), f"local-checked-narration-{self.calls}",
                                  "fixture-model", None, "STOP")

    provider = LocalCheckedDesignNarrationProvider({"explanation": {
        "fact_ids": cited_ids, "text": prose, "next_action": "stop"}})
    monkeypatch.setattr(client.app.state.provider, "generate", provider.generate)

    def explain(key, revision):
        return post(client, f"/workspaces/{history['workspace']}/assistant-turns", {
            "operation": "explain", "client_operation_id": key, "expected_conversation_revision": revision,
            "text": "Describe this checked design using its cited time, allowance and evidence states.",
            "problem_id": history["problem"]["id"], "suggestion_id": suggestion["id"],
            "consent": {"provider": "gemini", "model": "fixture-model", "source_asset_ids": [],
                "include_notes": True, "include_existing_values": True, "accepted": True}}, key)

    positive = explain("supported-checked-design", 0)
    assert positive["body"]["model_commentary"] == prose
    assert positive["body"]["commentary_status"] == "unverified_model_commentary"
    actual_cited = [fact for fact in positive["body"]["facts"] if fact["id"] in cited_ids]
    assert len(actual_cited) == 6
    assert {fact["record_id"] for fact in actual_cited} == {suggestion["id"]}
    assert {fact["field"]: fact["value"] for fact in actual_cited} == {
        "selected_time": design["selected_time"], "future_hard_allowance": design["future_hard_allowance"],
        "design_tier": "checked_pair_separation", "verification": "valid", "expected_binding": "matches", "replay": "passed"}

    workflow = client.app.state.workflow
    original_get = workflow.get

    def corrupt_native_read(actor, record_id, kind=None):
        record = original_get(actor, record_id, kind)
        if record_id == suggestion["id"]:
            # All six cited fields remain unchanged. The read projection alone
            # presents a contradictory native state for this authorized record.
            record = deepcopy(record)
            record["body"]["native_replay"]["integrity"] = "failed"
        return record

    with monkeypatch.context() as patch:
        patch.setattr(workflow, "get", corrupt_native_read)
        rejected = explain("contradictory-native-design", 1)
    rejected_body = rejected["body"]
    assert rejected_body["commentary_status"] == "suppressed" and rejected_body["model_commentary"] is None
    assert rejected_body["commentary_suppression_reason"] == "unsupported_claim"
    assert rejected_body["fact_ids"] == cited_ids
    assert [fact for fact in rejected_body["facts"] if fact["id"] in cited_ids] == actual_cited
    native_fact, = [fact for fact in rejected_body["facts"] if fact["record_id"] == suggestion["id"] and fact["field"] == "native_replay"]
    assert native_fact["id"] not in cited_ids and native_fact["value"]["integrity"] == "failed"
    assert any("No checked scientific conclusion" in statement for statement in rejected_body["critical_statements"])
    assert provider.calls == 2
    for response in (positive, rejected):
        assert response["body"]["execution_approved"] is False
        assert client.get(PREFIX + f"/records/{response['id']}").json() == response
    for key in ("dataset", "problem", "evidence", "design_record"):
        record = history[key]
        assert client.get(PREFIX + f"/records/{record['id']}").json() == record
    assert client.get(PREFIX + f"/artifacts/{design['artifacts'][0]['id']}").content == history["design_content"]
    assert client.get(PREFIX + f"/workspaces/{history['workspace']}/provider-attempts").json() == []
