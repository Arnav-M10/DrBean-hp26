"""Offline policy decisions are observations, not scientific acceptance tests."""
import copy
import json
import socket

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
import pytest

from bean_api.coordinator import CoordinatorFailure
from bean_api.research_controlled import build_controlled_research_model


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Offline fixture attempted network access")
    monkeypatch.setattr(socket.socket, "connect", denied)


def history(fact):
    messages = [HumanMessage(content=json.dumps({"question": "Same objective, arbitrary dataset name",
        "reviewed_context": {"problem": {"id": "problem"}}}))]
    observed = [
        ("write_todos", {"todos": [{"content": "Investigate", "status": "in_progress"}]}, None),
        ("prepare_scientific_proposal", {"kind": "investigation", "reference_ids": ["problem"]},
         {"accepted": False, "proposal_id": "p", "proposal_digest": "pd", "review_id": "r", "review_digest": "rd"}),
        ("run_scientific_operation", {}, {"state": "completed", "evidence_ids": ["fact"]}),
        ("read_research_evidence", {"evidence_id": "fact"}, fact),
    ]
    for index, (name, args, value) in enumerate(observed):
        call_id = f"call-{index}"
        messages.extend([AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}]),
            ToolMessage(content="Updated todos" if value is None else json.dumps(value), tool_call_id=call_id)])
    return messages


def checked_fact():
    return {"id": "fact", "scientific_outcome": "certified_counterexample", "verification": "valid",
        "expected_binding": "matches", "replay": "passed", "candidates": [
            {"id": "reference", "verification": "valid", "parameter_vector": {"A": "1/1", "ke": "1/10", "ka": "2/1"}},
            {"id": "outside", "verification": "valid", "parameter_vector": {"A": "2/1", "ke": "1/5", "ka": "2/1"}}]}


def finish(fact):
    model = build_controlled_research_model()
    messages = history(fact)
    update = model.invoke(messages)
    call = update.tool_calls[0]
    assert call["name"] == "write_todos"
    messages += [update, ToolMessage(content="Updated todos", tool_call_id=call["id"])]
    # A fresh instance consumes the persisted transcript; no local turn counter.
    report = build_controlled_research_model().invoke(messages).tool_calls[0]
    assert report["name"] == "publish_research_report"
    assert report["args"]["evidence_ids"] == ["fact"]
    return call["args"]["todos"], report["args"]


def test_changed_actual_tool_result_changes_durable_next_step():
    positive = checked_fact()
    negative = {**positive, "scientific_outcome": "no_counterexample_found", "candidates": []}
    plan_a, report_a = finish(positive)
    plan_b, report_b = finish(negative)
    assert report_a["next_action"] == "review_design"
    assert report_b["next_action"] == "clarify"
    assert plan_a[-1]["content"] != plan_b[-1]["content"]
    assert report_a["text"] != report_b["text"]
    assert "does not prove" in report_b["text"]


@pytest.mark.parametrize("change", [
    {"verification": "not_checked"}, {"expected_binding": "mismatch"}, {"replay": "failed"},
    {"scientific_outcome": "inconclusive"}, {"candidates": []},
])
def test_replay_or_successful_execution_does_not_invent_design_eligibility(change):
    _, report = finish({**checked_fact(), **change})
    assert report["next_action"] == "clarify"


def test_same_candidate_twice_is_not_a_design_pair():
    fact = checked_fact()
    fact["candidates"][1] = copy.deepcopy(fact["candidates"][0])
    assert finish(fact)[1]["next_action"] == "clarify"


def test_missing_reviewed_problem_requests_meanings_without_fabricating_inputs():
    model = build_controlled_research_model()
    call = model.invoke([HumanMessage(content=json.dumps({"question": "Prove the range", "reviewed_context": {
        "problem": None, "sources": [{"filename": "hero-certified-counterexample.csv"}]}}))]).tool_calls[0]
    assert call["name"] == "request_clarification"
    assert call["args"]["fields"] == ["reviewed_problem"]


def test_evidence_id_substitution_fails_before_report():
    fact = checked_fact()
    fact["id"] = "different-record"
    with pytest.raises(CoordinatorFailure, match="controlled_research_evidence_invalid"):
        build_controlled_research_model().invoke(history(fact))


def test_error_response_is_not_treated_as_science():
    messages = history(checked_fact())
    messages[-1].status = "error"
    with pytest.raises(CoordinatorFailure, match="controlled_research_observation_invalid"):
        build_controlled_research_model().invoke(messages)
