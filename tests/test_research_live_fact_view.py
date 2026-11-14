"""Offline model-view checks against retained typed scientific record shapes.

These check projection fidelity, not a new engine run or live-model qualification.
The full canonical facts remain the publication validator's inputs.
"""
from copy import deepcopy
import json
import socket

import pytest

from bean_api.ai_prompts import commentary_rejection
from bean_api.coordinator import _safe_fact
from bean_api.research_coordinator import _model_fact
from bean_api.research_fact_view import live_fact
from bean_api.research_integration import _evidence_fact
from test_research_integration import entity, retained_result


@pytest.fixture(autouse=True)
def no_provider_or_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Fact-view checks cannot dispatch a provider or network request")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr("google.genai.Client", denied)


def fact(kind):
    name = "hero-baseline.response.json" if kind == "evidence" else "hero-design.response.json"
    record = entity(kind, retained_result(name))
    return _safe_fact(_evidence_fact(record, record["id"], record["workspace_id"]))


def leaves(value):
    if isinstance(value, dict):
        return set().union(*(leaves(item) for item in value.values())) if value else set()
    if isinstance(value, list):
        return set().union(*(leaves(item) for item in value)) if value else set()
    return {json.dumps(value)}


@pytest.mark.parametrize("kind", ["evidence", "suggestion"])
def test_live_view_keeps_canonical_identity_science_scope_and_exact_values(kind):
    source = fact(kind)
    model_view = _model_fact(source)
    before = deepcopy(model_view)
    view = live_fact(model_view)
    assert source == fact(kind) and model_view == before
    # The only leaf values allowed to vanish altogether are these explicit
    # storage/codec/projection labels. Scientific identities and hashes remain.
    metadata = {json.dumps(before[key]) for key in (
        "workspace_id", "fact_projection_version", "projection_version", "fact_view", "source_fact_digest") if key in before}
    metadata.update(json.dumps(item[key]) for item in before["artifacts"] for key in ("byte_size", "media_type") if key in item)
    if "packet_profile" in before["native_replay"]:
        metadata.add(json.dumps(before["native_replay"]["packet_profile"]))
    assert leaves(before) - metadata <= leaves(view)
    assert len(json.dumps(view)) < len(json.dumps(before))
    for key in ("id", "evidence_digest", "problem_id", "problem_digest", "scientific_problem_digest",
                "scientific_design_digest", "native_suggestion_digest", "run_id", "scenario_id", "parent_id",
                "kind", "fact_projection", "scientific_outcome", "design_tier", "verification", "expected_binding",
                "replay", "reason_code", "dataset_origin", "candidates", "candidate_ids", "candidate_results",
                "baseline_search", "selected_time", "selected_option", "future_hard_allowance", "options", "algorithm"):
        if key in before:
            assert view[key] == before[key], key
    assert [(item["id"], item["sha256"]) for item in view["artifacts"]] == [
        (item["id"], item["sha256"]) for item in before["artifacts"]]
    assert view["verification_record"]["proposition"] == before["verification_record"]["proposition"]
    assert view["native_replay"]["integrity"] == before["native_replay"]["integrity"]
    for key in view["native_replay"].get("same_as_fact", []):
        assert before["native_replay"][key] == view[key]
    if kind == "evidence":
        assert view["native_replay"]["outcome"]["scope"] == before["native_replay"]["outcome"]["scope"]
        assert view["native_replay"]["search_replayed"] is False
        assert [item["parameter_vector"] for item in view["candidates"]] == [item["parameter_vector"] for item in source["candidates"]]
    else:
        assert view["native_replay"]["scope"] == before["native_replay"]["scope"]


@pytest.mark.parametrize("kind", ["evidence", "suggestion"])
@pytest.mark.parametrize("path,value", [
    (("verification_record", "observed_problem_digest"), "9" * 64),
    (("verification_record", "observed_scientific_problem_digest"), "8" * 64),
    (("verification_record", "artifact_sha256"), "7" * 64),
    (("verification_record", "verification"), "invalid"),
    (("verification_record", "expected_binding"), "mismatch"),
    (("native_replay", "verification"), "inconclusive"),
    (("native_replay", "replay"), "failed"),
    (("native_replay", "expected_binding"), "mismatch"),
    (("native_replay", "dataset_origin"), "actual"),
    (("native_replay", "anchors", "artifact_sha256"), "6" * 64),
    (("native_replay", "anchors", "problem_digest"), "5" * 64),
    (("native_replay", "anchors", "projection_digest"), "4" * 64),
    (("native_replay", "anchors", "run_id"), "another-run"),
    (("native_replay", "anchors", "scenario_id"), "another-scenario"),
])
def test_conflicting_check_and_anchor_copies_are_never_replaced_by_agreement(kind, path, value):
    source = fact(kind)
    changed = source
    for key in path[:-1]:
        changed = changed[key]
    changed[path[-1]] = value
    before = deepcopy(source)
    view = live_fact(_model_fact(source))
    observed = view
    for key in path:
        observed = observed[key]
    assert observed == value
    assert source == before
    assert view["id"] == source["id"] and view["evidence_digest"] == source["evidence_digest"]
    assert view["verification"] == source["verification"]
    assert view["expected_binding"] == source["expected_binding"]


@pytest.mark.parametrize("key,value", [
    ("scientific_outcome", "inconclusive"), ("compatible_candidate_ids", ["foreign-candidate"]),
    ("counterexample_ids", []), ("reason_code", "unresolved_check"),
])
def test_disagreeing_replay_outcome_remains_visible(key, value):
    source = fact("evidence")
    source["native_replay"]["outcome"][key] = value
    view = live_fact(_model_fact(source))
    assert view["native_replay"]["outcome"][key] == value
    assert key not in view["native_replay"]["outcome"].get("same_as_fact_and_candidates", [])
    assert view["scientific_outcome"] == "certified_counterexample"


def test_numerical_guidance_with_artifact_and_no_named_check_cannot_gain_checked_separation():
    result = retained_result("hero-design.response.json")
    result.update(design_tier="numerical_guidance", verification="not_checked", verification_record=None,
                  reason_code="numerical_only")
    result["native_replay"].update(verification="not_checked", scope="numerical")
    record = entity("suggestion", result)
    source = _safe_fact(_evidence_fact(record, record["id"], record["workspace_id"]))
    view = live_fact(_model_fact(source))
    assert view["design_tier"] == "numerical_guidance" and view["verification"] == "not_checked"
    assert view["verification_record"] is None and view["replay"] == "passed"
    assert view["options"] == result["options"] and view["candidate_ids"] == result["candidate_ids"]
    assert commentary_rejection("This design establishes checked pair separation.", [source]) == "unsupported_claim"
    assert commentary_rejection("This design establishes checked pair separation.", [view]) == "unsupported_claim"


def test_inconclusive_and_empty_checks_survive_successful_replay_without_claim_upgrade():
    result = retained_result("hero-baseline.response.json")
    result.update(scientific_outcome="inconclusive", verification="inconclusive", verification_record=None,
                  candidates=[], candidate_results=[], reason_code="bounded_search_inconclusive")
    result["native_replay"].update(verification="inconclusive", anchors=None,
        outcome={"scientific_outcome": "inconclusive", "counterexample_ids": [], "compatible_candidate_ids": [],
                 "scope": "A bounded search with no completeness claim."})
    record = entity("evidence", result)
    source = _safe_fact(_evidence_fact(record, record["id"], record["workspace_id"]))
    view = live_fact(_model_fact(source))
    assert view["scientific_outcome"] == view["verification"] == "inconclusive"
    assert view["replay"] == "passed" and view["candidates"] == []
    assert view["verification_record"] is None and view["native_replay"]["anchors"] is None
    assert view["native_replay"]["outcome"] == source["native_replay"]["outcome"]
    assert commentary_rejection("The claim is proved.", [source]) == "unsupported_claim"
    assert commentary_rejection("The claim is proved.", [view]) == "unsupported_claim"


def test_missing_root_fact_is_not_agreement_with_an_explicit_unknown_replay_value():
    result = {"design_tier": "numerical_guidance", "verification": "not_checked", "replay": "passed",
        "reason_code": "numerical_only", "selected_time": "8/1", "candidate_ids": ["reference", "outside"],
        "future_hard_allowance": "1/5", "algorithm": "controlled_numerical", "artifacts": [],
        "options": [{"time": "8/1", "state": "evaluated", "reason_code": "numerical_only", "exact_margin": "1/10"}],
        "candidate_results": [], "native_replay": {"replay": "passed", "verification": "not_checked",
            "expected_binding": None, "suggestion_digest": None, "scope": "numerical"}}
    record = entity("suggestion", result)
    source = _safe_fact(_evidence_fact(record, record["id"], record["workspace_id"]))
    assert "expected_binding" not in source and "native_suggestion_digest" not in source
    view = live_fact(source)
    assert view["native_replay"]["expected_binding"] is None
    assert "expected_binding" not in view["native_replay"].get("same_as_fact", [])
    assert "suggestion_digest" in view["native_replay"] and view["native_replay"]["suggestion_digest"] is None
