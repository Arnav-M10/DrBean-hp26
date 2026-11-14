"""Offline policy decisions are observations, not scientific acceptance tests."""
import copy
import json
import socket

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
import pytest

from bean_api.coordinator import CoordinatorFailure
from bean_api.research_controlled import _next_step, build_controlled_research_model
from bean_api.research_coordinator import _model_context


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


def test_model_context_preserves_complete_scientific_bodies_and_changed_problem():
    body = {"rows": [{"time": "3/7", "hard_allowance": "1/19", "included": False}],
        "time_origin": "reviewed origin", "target": {"lower": "1/10", "upper": "17/100"},
        "source": {"id": "source", "digest": "text", "kind": "raw", "body": {},
                   "created_by": "user-supplied source meaning must remain"}}
    record = {"id": "problem", "digest": "digest", "kind": "problem", "body": body,
        "parent_id": "parent", "created_at": "timestamp", "created_by": "actor", "workspace_id": "workspace"}
    context = {"problem": record, "current_problem": copy.deepcopy(record), "dataset": copy.deepcopy(record)}
    before = copy.deepcopy(context)
    projected = _model_context(context)
    assert context == before
    assert projected["problem"]["body"] == projected["dataset"]["body"] == body
    assert projected["problem"]["parent_id"] == "parent"
    assert projected["current_problem"] == {"id": "problem", "digest": "digest", "same_as": "problem"}
    assert "created_by" not in projected["problem"]
    context["current_problem"]["digest"] = "changed"
    context["current_problem"]["body"]["rows"][0]["hard_allowance"] = "1/23"
    projected = _model_context(context)
    assert projected["current_problem"]["body"]["rows"][0]["hard_allowance"] == "1/23"
    assert projected["problem"]["body"]["rows"][0]["hard_allowance"] == "1/19"


@pytest.mark.parametrize("margin,tier,verification,next_action", [
    ("1/20", "checked_pair_separation", "valid", "review_observation"),
    ("0/1", "checked_pair_separation", "valid", "clarify"),
    ("-1/20", "no_separation_established", "valid", "clarify"),
    ("1/20", "numerical_guidance", "not_checked", "clarify"),
])
def test_design_next_action_requires_a_strictly_positive_checked_margin(margin, tier, verification, next_action):
    fact = {"design_tier": tier, "verification": verification, "expected_binding": "matches", "replay": "passed",
        "selected_time": "8/1", "selected_option": {"time": "8/1", "exact_margin": margin}}
    assert _next_step(fact)[0] == next_action
    fact["selected_option"]["time"] = "6/1"
    assert _next_step(fact)[0] == "clarify"


def test_advance_uses_reread_current_baseline_preserves_todos_and_reports_both_records():
    model = build_controlled_research_model()
    fact = {**checked_fact(), "problem_id": "problem", "problem_digest": "digest"}
    todos = [{"content": "Investigate", "status": "completed"}, {"content": "Review design", "status": "pending"}]
    prior = [("write_todos", {"todos": todos}, None), ("publish_research_report", {},
        {"id": "report", "evidence_ids": ["fact"], "agent_commentary": {"next_action": "review_design"}})]
    context = {"problem": {"id": "problem", "digest": "digest"}, "design_constraints": {"reviewed": True}}
    assert model._choose(context, [], prior) == ("read_research_evidence", {"evidence_id": "fact"})
    observed = [("read_research_evidence", {"evidence_id": "fact"}, fact)]
    assert model._choose(context, observed, prior) == (
        "prepare_scientific_proposal", {"kind": "design", "reference_ids": ["fact"]})
    design = {"id": "design", "design_tier": "no_separation_established"}
    observed += [("run_scientific_operation", {}, {"state": "completed", "evidence_ids": ["design"]}),
                 ("read_research_evidence", {"evidence_id": "design"}, design)]
    tool, update = model._choose(context, observed, prior)
    assert tool == "write_todos" and todos[0] in update["todos"]
    observed.append((tool, update, None))
    tool, report = model._choose(context, observed, prior)
    assert tool == "publish_research_report" and report["evidence_ids"] == ["fact", "design"]
    assert report["next_action"] == "clarify"
    context["problem"]["digest"] = "changed-assumptions"
    assert model._choose(context, observed[:1], prior)[0] == "request_clarification"
    assert model._choose({"problem": context["problem"]}, [], prior)[0] == "request_clarification"
