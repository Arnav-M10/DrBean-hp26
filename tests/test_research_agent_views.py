"""Author checks (owner 5): bounded model views and evidence-bound plan completion.

These prove deterministic projection properties only. They are not live-model,
browser or independent qualification. No provider, network or science runs here.
"""
import asyncio
import copy
import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
import pytest

from bean_api.coordinator import CoordinatorFailure
from bean_api.research_coordinator import (
    FACT_VIEW_VERSION, ResearchContext, _child_view, _model_context, _model_fact, _plan_evidence, _rows_table,
)
from bean_api.research_integration import _CanonicalPorts

PROBLEM, SCIENTIFIC, ARTIFACT_SHA = "a" * 64, "b" * 64, "c" * 64


def investigation_fact():
    """The real projection shape returned for an investigation (values are synthetic)."""
    candidate = lambda ident, vector: {  # noqa: E731
        "artifact_ids": ["native_artifact_1"], "checked_horizon": "4/1", "id": ident, "observable": "concentration",
        "parameter_vector": vector, "problem_digest": PROBLEM, "problem_id": "problem_1", "verification": "valid"}
    result = lambda ident, outside: {  # noqa: E731
        "candidate_id": ident, "is_counterexample": outside, "outside_closed_claim": outside, "reason_code": None,
        "unresolved_observation_ids": [], "verification": "valid", "violating_observation_ids": []}
    return {
        "id": "evidence_1", "evidence_digest": "d" * 64, "fact_projection": "agent-evidence.v1", "run_id": "run_1",
        "scenario_id": "baseline", "scientific_outcome": "certified_counterexample", "verification": "valid",
        "expected_binding": "matches", "replay": "passed", "reason_code": "compatible_outside_witness",
        "problem_id": "problem_1", "problem_digest": PROBLEM, "projection_version": "DB-SC-1-to-groundwork-v1",
        "scientific_problem_digest": SCIENTIFIC,
        "candidates": [candidate("inside", {"A": "9/1", "ka": "446/127", "ke": "1631/12700"}),
                       candidate("outside", {"A": "87/10", "ka": "484/127", "ke": "101/1016"})],
        "candidate_results": [result("inside", False), result("outside", True)],
        "artifacts": [{"byte_size": 53805, "id": "native_artifact_1", "media_type": "application/vnd.counterdex.native+json",
                       "sha256": ARTIFACT_SHA}],
        "verification_record": {"artifact_id": "native_artifact_1", "artifact_sha256": ARTIFACT_SHA, "checker_name": "counterdex",
            "checker_version": "0.3.0", "expected_binding": "matches", "expected_problem_digest": PROBLEM,
            "expected_scientific_problem_digest": SCIENTIFIC, "observed_problem_digest": PROBLEM,
            "observed_scientific_problem_digest": SCIENTIFIC, "proposition": "No search completeness is asserted.",
            "verification": "valid"},
        "baseline_search": {"attempted_count": 16384, "execution": "completed", "partial": False,
                            "settings": {"ka_points": 128, "ke_points": 128}},
        "candidate_ids": ["inside", "outside"], "dataset_origin": "hypothetical",
        "native_replay": {"replay": "passed", "integrity": "passed", "verification": "valid", "expected_binding": "matches",
            "reason_code": "fresh_historical_check", "dataset_origin": "hypothetical", "operation": "investigate",
            "anchors": {"app_request_digest": None, "artifact_sha256": ARTIFACT_SHA, "dataset_digest": "e" * 64,
                        "design_digest": None, "problem_digest": PROBLEM, "projection_digest": SCIENTIFIC,
                        "run_id": "run_1", "scenario_id": "baseline"},
            "baseline_digest": "f" * 64, "outcome": {"scientific_outcome": "certified_counterexample",
                "counterexample_ids": ["outside"], "scope": "Selected exact vectors only."},
            "historical_compatibility": "valid", "search_replayed": False},
        "kind": "evidence", "workspace_id": "ws_1", "parent_id": None, "source_fact_digest": "0" * 64,
        "fact_projection_version": "coordinator-facts.v1"}


def leaves(value):
    if isinstance(value, dict):
        return set().union(*(leaves(item) for item in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(leaves(item) for item in value)) if value else set()
    return {json.dumps(value)}


def size(value):
    return len(json.dumps(value, separators=(",", ":")).encode())


def test_investigation_view_keeps_every_value_once_and_is_smaller():
    fact = investigation_fact()
    view = _model_fact(fact)
    assert view["fact_view"] == FACT_VIEW_VERSION and fact == investigation_fact()  # input untouched
    # Every leaf value except tenant metadata survives at least once; only repeats are removed.
    assert leaves(fact) - {json.dumps("ws_1")} <= leaves(view)
    assert size(view) < size(fact)
    for key in ("id", "evidence_digest", "run_id", "problem_id", "problem_digest", "scientific_problem_digest",
                "scientific_outcome", "verification", "expected_binding", "replay", "source_fact_digest"):
        assert view[key] == fact[key]
    assert view["artifacts"] == fact["artifacts"]
    assert [(c["id"], c["parameter_vector"], c["verification"], c["is_counterexample"]) for c in view["candidates"]] == [
        ("inside", fact["candidates"][0]["parameter_vector"], "valid", False),
        ("outside", fact["candidates"][1]["parameter_vector"], "valid", True)]
    assert view["verification_record"] == {"checker_name": "counterdex", "checker_version": "0.3.0",
                                           "proposition": "No search completeness is asserted."}
    assert view["native_replay"]["anchors"] == {"app_request_digest": None, "dataset_digest": "e" * 64, "design_digest": None}
    assert view["native_replay"]["outcome"] == fact["native_replay"]["outcome"]


@pytest.mark.parametrize("mutate", [
    lambda f: f["verification_record"].update(observed_problem_digest="9" * 64),
    lambda f: f["verification_record"].update(expected_binding="mismatch"),
    lambda f: f["candidates"][0].update(problem_id="problem_other"),
    lambda f: f["candidate_results"][1].update(verification="unresolved"),
    lambda f: f["native_replay"]["anchors"].update(run_id="run_other"),
    lambda f: f["native_replay"].update(dataset_origin="actual"),
    lambda f: f["artifacts"].append({**f["artifacts"][0], "id": "native_artifact_2"}),
    lambda f: f.update(candidate_ids=["outside", "inside"]),
    lambda f: f["candidate_results"][0].update(checked_horizon="8/1"),
    lambda f: f.pop("verification_record"),
])
def test_any_disagreeing_copy_returns_the_complete_fact(mutate):
    fact = investigation_fact()
    mutate(fact)
    assert _model_fact(fact) == fact


def test_other_projections_pass_through_unchanged():
    design = {"id": "suggestion_1", "fact_projection": "agent-design-evidence.v1", "kind": "suggestion",
              "design_tier": "no_separation_established"}
    assert _model_fact(copy.deepcopy(design)) == design
    minimal = {"id": "fact", "scientific_outcome": "certified_counterexample"}
    assert _model_fact(copy.deepcopy(minimal)) == minimal


def rows():
    base = {"hard_allowance": "1/2", "included": True, "notes": "Synthetic", "source_asset_id": None}
    return [{**base, "id": "row_0", "time": "1/4", "concentration": "24/5",
             "original_values": {"time": "0.25", "concentration": "4.80"}},
            {**base, "id": "row_1", "time": "1/2", "concentration": "36/5",
             "original_values": {"time": "0.5", "concentration": "7.20"}},
            {**base, "id": "row_2", "time": "1/1", "concentration": "8/1", "included": False, "notes": "Excluded: tube leak",
             "original_values": {"time": "1", "concentration": "8.00"}}]


def test_row_table_is_lossless_and_keeps_excluded_rows():
    original = rows()
    table = _rows_table(original)
    assert table["row_count"] == 3 and set(table["same_in_every_row"]) == {"hard_allowance", "source_asset_id"}
    rebuilt = [{**table["same_in_every_row"], **dict(zip(table["columns"], values))} for values in table["values"]]
    assert rebuilt == original == rows()


@pytest.mark.parametrize("value", [
    [{"id": "only"}],
    [{"id": "a", "time": "1/1"}, {"id": "b"}],
    [{"id": "a"}, "not-a-row"],
    "not-a-list",
])
def test_irregular_rows_are_returned_unchanged(value):
    assert _rows_table(copy.deepcopy(value)) == value


def test_row_table_distinguishes_json_types_and_tolerates_unusual_values():
    table = _rows_table([{"id": "a", "flag": True, "x": 1.5}, {"id": "b", "flag": 1, "x": -2}])
    assert "flag" in table["columns"] and table["same_in_every_row"] == {}
    rebuilt = [dict(zip(table["columns"], values)) for values in table["values"]]
    assert rebuilt[0]["flag"] is True and rebuilt[1]["flag"] == 1 and type(rebuilt[1]["flag"]) is int


def test_model_context_tables_only_dataset_rows_and_keeps_bodies_otherwise():
    dataset = {"id": "dataset_1", "digest": "d" * 64, "kind": "dataset", "workspace_id": "ws", "created_at": "t",
               "created_by": "alice", "parent_id": None, "body": {"experiment_id": "x", "rows": rows()}}
    review = {"id": "review_1", "digest": "e" * 64, "kind": "research_input_review", "workspace_id": "ws",
              "created_at": "t", "created_by": "alice", "parent_id": None, "body": {"rows": rows()}}
    projected = _model_context({"dataset": dataset, "input_reviews": [review]})
    assert projected["dataset"]["body"]["rows"] == _rows_table(rows())
    assert projected["dataset"]["body"]["experiment_id"] == "x"
    assert projected["input_reviews"][0]["body"] == {"rows": rows()}
    assert "workspace_id" not in projected["dataset"] and dataset["body"]["rows"] == rows()


def test_child_view_removes_only_verified_repeats():
    result = {"review_id": "plan_1", "review_digest": "r" * 64, "kind": "investigation", "approval_id": "approval_1",
              "decision": "approve", "scope": {"plan_id": "plan_1", "plan_digest": "r" * 64, "input_digest": "i" * 64},
              "job_id": "run_1", "state": "completed", "evidence_ids": ["evidence_1"], "result_id": "summary_1",
              "waiting": False, "proposal_id": "plan_1", "unexpected": {"kept": True}}
    view = _child_view(result, proposal_id="plan_1", proposal_digest="r" * 64, review_digest="r" * 64,
                       input_digest="i" * 64)
    assert view == {key: value for key, value in result.items() if key not in {"scope", "review_digest", "waiting"}}
    other = _child_view(result, proposal_id="plan_1", proposal_digest="r" * 64, review_digest="r" * 64,
                        input_digest="x" * 64)
    assert other["scope"] == result["scope"]


def thread(*steps):
    """Messages for (tool name, args, returned value) steps; ids are positional."""
    messages = [HumanMessage(content="{}")]
    for index, (name, args, value, status) in enumerate(steps):
        call_id = f"call-{index}"
        messages.append(AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}]))
        if value is not None:
            messages.append(ToolMessage(content=value if isinstance(value, str) else json.dumps(value),
                                        tool_call_id=call_id, status=status))
    return messages


def todos(*pairs):
    return {"todos": [{"content": content, "status": status} for content, status in pairs]}


def test_completion_binds_only_to_evidence_read_since_the_previous_plan():
    steps = [
        ("write_todos", todos(("Investigate", "in_progress"), ("Read evidence", "pending")), "Updated", "success"),
        ("run_scientific_operation", {}, {"state": "completed", "evidence_ids": ["evidence_1"]}, "success"),
        ("read_research_evidence", {"evidence_id": "evidence_1"}, {"id": "evidence_1"}, "success"),
        ("write_todos", todos(("Investigate", "completed"), ("Read evidence", "completed"), ("Design", "pending")),
         "Updated", "success"),
        # A later action rereads the baseline (already cited) and reads the design result.
        ("read_research_evidence", {"evidence_id": "evidence_1"}, {"id": "evidence_1"}, "success"),
        ("read_research_evidence", {"evidence_id": "suggestion_1"}, {"id": "suggestion_1"}, "success"),
        ("write_todos", todos(("Investigate", "completed"), ("Read evidence", "completed"), ("Design", "completed"),
                              ("New reading", "pending")), None, "success")]
    current = steps[3][:2] + (None, "success")
    assert _plan_evidence(thread(*steps[:3], current)) == {"Investigate": ["evidence_1"], "Read evidence": ["evidence_1"]}
    bound = _plan_evidence(thread(*steps))
    assert bound == {"Investigate": ["evidence_1"], "Read evidence": ["evidence_1"], "Design": ["suggestion_1"]}


def test_premature_or_unverified_completion_stays_unbound():
    premature = thread(("write_todos", todos(("Investigate", "completed")), "Updated", "success"),
                       ("read_research_evidence", {"evidence_id": "evidence_1"}, {"id": "evidence_1"}, "success"),
                       ("write_todos", todos(("Investigate", "completed"), ("Next", "pending")), None, "success"))
    assert _plan_evidence(premature) == {"Investigate": []}
    unverified = thread(("read_research_evidence", {"evidence_id": "evidence_1"}, {"id": "evidence_2"}, "success"),
                        ("read_research_evidence", {"evidence_id": "evidence_3"}, "not json", "success"),
                        ("read_research_evidence", {"evidence_id": "evidence_4"}, {"id": "evidence_4"}, "error"),
                        ("write_todos", todos(("Read", "completed")), None, "success"))
    assert _plan_evidence(unverified) == {"Read": []}


class PlanBackend:
    def __init__(self):
        self.plans = []

    def check_authority(self):
        return None

    def update_plan(self, plan):
        self.plans.append(copy.deepcopy(plan))
        return {"id": "plan_revision_1"}


def canonical_ports(references=("research_session_1", "evidence_1")):
    context = ResearchContext(workspace_id="ws_1", research_session_id="research_session_1", action_id="action_1",
                              thread_id="thread_1", input_digest="i" * 64, question="q", reviewed_context={})
    backend = PlanBackend()
    return _CanonicalPorts(backend, {"reference_ids": list(references), "reviews": []}, context, lambda event: None), backend


def plan_digest(items):
    import hashlib
    from bean_api.canonical import canonical_bytes
    return hashlib.sha256(canonical_bytes(items)).hexdigest()


def test_canonical_plan_marks_only_evidence_backed_completion_as_completed():
    ports, backend = canonical_ports()
    items = todos(("Investigate", "completed"), ("Claimed elsewhere", "completed"), ("Design", "pending"))["todos"]
    asyncio.run(ports.record_plan(items, plan_digest(items), {"Investigate": ["evidence_1"], "Claimed elsewhere": []}))
    steps = {step["title"]: step for step in backend.plans[0]["steps"]}
    assert (steps["Investigate"]["status"], steps["Investigate"]["reference_ids"]) == ("completed", ["evidence_1"])
    assert "after it read the cited checked evidence" in steps["Investigate"]["reason"]
    assert (steps["Claimed elsewhere"]["status"], steps["Claimed elsewhere"]["reference_ids"]) == ("pending", [])
    assert "Agent-proposed completion" in steps["Claimed elsewhere"]["reason"]
    assert steps["Design"]["status"] == "pending" and steps["Design"]["reason"] == "Agent-proposed research step."


@pytest.mark.parametrize("evidence,code", [
    ({"Investigate": ["evidence_out_of_scope"]}, "research_reference_out_of_scope"),
    ({"Not a completed todo": ["evidence_1"]}, "research_plan_invalid"),
    ({"Investigate": ["evidence_1", "evidence_1"]}, "research_references_invalid"),
])
def test_canonical_plan_refuses_unscoped_or_unbound_citations(evidence, code):
    ports, backend = canonical_ports()
    items = todos(("Investigate", "completed"))["todos"]
    with pytest.raises(CoordinatorFailure, match=code):
        asyncio.run(ports.record_plan(items, plan_digest(items), evidence))
    assert not backend.plans
