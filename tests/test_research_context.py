"""Offline contracts for bounded model views; durable history is never rewritten."""
import copy
import json
import socket

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from bean_api.coordinator import CoordinatorFailure
from bean_api.research_context import model_messages
from bean_api.research_coordinator import TOOLS, _safe_tool_batch


@pytest.fixture(autouse=True)
def no_network_or_provider(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("Context projections cannot dispatch providers or network requests")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr("google.genai.Client", deny)


def exchange(call_id, name, args, value, *, status="success"):
    ai = AIMessage(content="", id=f"message-{call_id}", tool_calls=[
        {"name": name, "args": args, "id": call_id, "type": "tool_call"}])
    tool = ToolMessage(content=json.dumps(value), tool_call_id=call_id,
                       name=name, id=f"tool-{call_id}", status=status)
    return [ai, tool]


def project(messages, state=None):
    return model_messages(messages, state or {}, question="Which measurement should be reviewed next?",
                          reviewed_context={"problem_id": "problem-reviewed", "input_digest": "reviewed-digest"})


def test_current_signed_exchange_and_ids_survive_by_identity_without_history_mutation():
    fact = {"id": "run-1", "scientific_outcome": "inconclusive", "verification": "valid",
            "expected_binding": "matches", "native_replay": "passed"}
    last = exchange("signed-call", "run_scientific_operation", {"proposal_id": "approved-proposal"},
                    {"state": "completed", "evidence_ids": ["run-1"], "canonical_evidence": [fact]})
    last[0].content = [{"type": "text", "text": "", "extras": {"signature": "DRBEAN-DUMMY-signature"}}]
    last[0].additional_kwargs = {"thought_signature": "DRBEAN-DUMMY-signature"}
    last[0].response_metadata = {"model_name": "offline-substitute", "provider_signature": "DRBEAN-DUMMY"}
    messages = [HumanMessage(content="Original reviewed objective"),
                *exchange("plan", "write_todos", {"todos": []}, "Plan saved"), *last]
    before = copy.deepcopy([message.model_dump() for message in messages])
    result = project(messages)
    assert len(result) == 3
    assert result[1] is last[0] and result[2] is last[1]
    assert result[1].tool_calls[0]["id"] == result[2].tool_call_id == "signed-call"
    assert [message.model_dump() for message in messages] == before
    snapshot = json.loads(result[0].content)["canonical_snapshot"]
    assert snapshot["evidence"] == []  # Exact current evidence remains in the untouched exchange.
    assert snapshot["completed_tools_in_action"] == ["write_todos", "run_scientific_operation"]
    assert json.loads(result[-1].content)["canonical_evidence"] == [fact]


def test_previous_action_facts_plan_and_report_survive_without_reusing_its_approval():
    fact = {"id": "run-prior", "scientific_outcome": "certified_counterexample", "verification": "valid",
            "expected_binding": "matches", "outside_scope": "two named candidates"}
    report = {"id": "report-prior", "evidence_ids": [fact["id"]], "commentary_persisted": True,
              "agent_commentary": {"text": "Review a feasible next measurement.", "next_action": "review_design",
                                   "authorship": "model_commentary", "scientific_authority": False,
                                   "fact_ids": [fact["id"]], "clarification_fields": []}}
    prior = [HumanMessage(content="Prior action"),
             *exchange("prior-prepare", "prepare_scientific_proposal", {"kind": "investigation"},
                       {"proposal_id": "old-proposal", "review_digest": "old-review", "accepted": False}),
             *exchange("prior-read", "read_research_evidence", {"evidence_id": fact["id"]}, fact),
             *exchange("prior-report", "publish_research_report", {"evidence_ids": [fact["id"]]}, report)]
    messages = [*prior, HumanMessage(content="Continue with separately reviewed design"),
                *exchange("current-plan", "write_todos", {"todos": []}, "Plan saved")]
    todos = [{"content": "Review permitted design", "status": "in_progress"}]
    state = {"todos": todos}
    before = copy.deepcopy(([message.model_dump() for message in messages], state))
    result = project(messages, state)
    context = json.loads(result[0].content)
    snapshot = context["canonical_snapshot"]
    assert context["reviewed_context"]["input_digest"] == "reviewed-digest"
    assert snapshot["evidence"] == [fact] and snapshot["todos"] == todos
    expected_report = copy.deepcopy(report)
    expected_report["agent_commentary"].pop("text")
    assert snapshot["latest_report"] == expected_report
    assert json.loads(prior[-1].content) == report
    assert report["agent_commentary"]["text"] == "Review a feasible next measurement."
    assert snapshot["completed_tools_in_action"] == ["write_todos"]
    assert "latest_prepared_proposal" not in snapshot
    assert "canonical approval" in snapshot["authority"]
    assert ([message.model_dump() for message in messages], state) == before


@pytest.mark.parametrize("current,include_problem,kept", [
    ({"id": "problem-reviewed", "digest": "reviewed-digest", "same_as": "problem"}, True, False),
    ({"id": "different-problem", "digest": "reviewed-digest", "same_as": "problem"}, True, True),
    ({"id": "problem-reviewed", "digest": "changed-digest", "same_as": "problem"}, True, True),
    ({"id": "problem-reviewed", "digest": "reviewed-digest", "same_as": "another_problem"}, True, True),
    ({"id": "problem-reviewed", "digest": "reviewed-digest", "same_as": "problem", "review_revision": 2}, True, True),
    ({"id": "problem-reviewed", "digest": "reviewed-digest", "same_as": "problem"}, False, True),
])
def test_only_exact_current_problem_alias_is_omitted_while_full_problem_remains(current, include_problem, kept):
    problem = {"id": "problem-reviewed", "digest": "reviewed-digest", "body": {
        "observations": [{"time": "2", "value": "4", "allowance": "0.1", "included": True}]}}
    reviewed = {"current_problem": current, "design_constraints": {"feasible_times": ["3", "5"]}}
    if include_problem:
        reviewed["problem"] = problem
    messages = [HumanMessage(content="Review the recorded measurements")]
    before = copy.deepcopy((reviewed, [message.model_dump() for message in messages]))
    result = model_messages(messages, {}, question="Review", reviewed_context=reviewed)
    projected = json.loads(result[0].content)["reviewed_context"]
    expected = copy.deepcopy(reviewed)
    if not kept:
        expected.pop("current_problem")
    assert projected == expected
    if include_problem:
        assert projected["problem"] == problem
    assert (reviewed, [message.model_dump() for message in messages]) == before


@pytest.mark.parametrize("kind", ["incomplete", "orphan", "duplicate_across_exchanges",
                                  "duplicate_in_exchange", "interrupted_by_human", "invalid_tool_call"])
def test_incomplete_or_ambiguous_continuity_preserves_original_message_list(kind):
    pair = exchange("call-1", "write_todos", {"todos": []}, "Plan saved")
    if kind == "incomplete":
        messages = [HumanMessage(content="Review"), pair[0]]
    elif kind == "orphan":
        messages = [HumanMessage(content="Review"), pair[1]]
    elif kind == "duplicate_across_exchanges":
        messages = [HumanMessage(content="Review"), *pair,
                    *exchange("call-1", "write_todos", {"todos": []}, "Plan saved again")]
    elif kind == "duplicate_in_exchange":
        pair[0].tool_calls.append(copy.deepcopy(pair[0].tool_calls[0]))
        messages = [HumanMessage(content="Review"), *pair]
    elif kind == "interrupted_by_human":
        messages = [HumanMessage(content="Review"), pair[0], HumanMessage(content="New action"), pair[1]]
    else:
        messages = [HumanMessage(content="Review"), AIMessage(content="", invalid_tool_calls=[
            {"name": "write_todos", "args": "{", "id": "invalid", "error": "invalid JSON", "type": "invalid_tool_call"}])]
    before = copy.deepcopy([message.model_dump() for message in messages])
    assert project(messages) is messages
    assert [message.model_dump() for message in messages] == before


def test_same_evidence_identity_with_changed_contents_fails_closed():
    fact = {"id": "run-1", "scientific_outcome": "inconclusive", "verification": "valid"}
    messages = [HumanMessage(content="Review"),
                *exchange("first", "read_research_evidence", {"evidence_id": "run-1"}, fact),
                *exchange("second", "read_research_evidence", {"evidence_id": "run-1"},
                          {**fact, "scientific_outcome": "certified_counterexample"})]
    with pytest.raises(CoordinatorFailure) as caught:
        project(messages)
    assert caught.value.code == "research_evidence_binding_invalid"


def test_current_prepared_review_binding_survives_a_later_plan_turn_as_context_only():
    prepared = {"proposal_id": "proposal-current", "proposal_digest": "proposal-digest",
                "review_id": "review-current", "review_digest": "review-digest", "accepted": False}
    args = {"kind": "design", "reference_ids": ["run-prior"]}
    messages = [HumanMessage(content="Review feasible design"),
                *exchange("prepare", "prepare_scientific_proposal", args, prepared),
                *exchange("plan", "write_todos", {"todos": []}, "Plan saved")]
    snapshot = json.loads(project(messages)[0].content)["canonical_snapshot"]
    assert snapshot["latest_prepared_proposal"] == {"tool_call_id": "prepare", "arguments": args, "result": prepared}
    assert "current backend checks are required" in snapshot["authority"]


@pytest.mark.parametrize("other", ["prepare_scientific_proposal", "publish_research_report"])
@pytest.mark.parametrize("reverse", [False, True])
def test_only_independent_plan_plus_prepare_or_report_can_share_request(other, reverse):
    names = ["write_todos", other]
    if reverse:
        names.reverse()
    assert _safe_tool_batch([{"name": name} for name in names])


@pytest.mark.parametrize("name", sorted(TOOLS))
def test_existing_single_tool_requests_remain_supported(name):
    assert _safe_tool_batch([{"name": name}])


@pytest.mark.parametrize("names", [
    ["write_todos", "run_scientific_operation"],
    ["prepare_scientific_proposal", "run_scientific_operation"],
    ["run_scientific_operation", "read_research_evidence"],
    ["read_research_evidence", "publish_research_report"],
    ["write_todos", "request_clarification"],
    ["write_todos", "write_todos"],
    ["write_todos", "prepare_scientific_proposal", "publish_research_report"],
    ["unapproved_tool"],
])
def test_scientific_dependent_duplicate_or_unapproved_batches_are_rejected(names):
    assert not _safe_tool_batch([{"name": name} for name in names])
