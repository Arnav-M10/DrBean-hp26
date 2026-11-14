"""Actual frozen-pair review: no fixture candidates and no second discovery."""
import base64
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import math

import pytest

from bean_api.canonical import semantic_digest
from bean_api.contracts import ScientificResult
from bean_api.followup_evidence import followup_result_checked, validate_followup_packet
from bean_api.workflow import DomainError
import test_native_design_adapter as design_test

native_design_history = design_test.native_design_history


def rational(value):
    value = Fraction(value)
    return f"{value.numerator}/{value.denominator}"


@pytest.fixture(scope="module")
def native_reviews(native_design_history):
    adapter, history, design_request = native_design_history
    design = adapter.design(design_request, history)
    assert "worker_error" not in design, design
    art = design["_native_artifacts"][0]
    original = {"id": art["id"], "sha256": art["sha256"], "bytes_base64": art["content_base64"], "anchors": art["anchor"]}
    time = Fraction(design["selected_time"])
    readings = []
    # These are synthetic new observations only, computed from the actually
    # discovered pair; the production adapter still checks exact native facts.
    for vector in design_request["candidate_vectors"]:
        a, ke, ka = (float(Fraction(vector[k])) for k in ("A", "ke", "ka"))
        value = a * ka / (ka - ke) * (math.exp(-ke * float(time)) - math.exp(-ka * float(time)))
        readings.append(Fraction(format(value, ".6f")))
    cases = {}
    for name, value in (("first", readings[0]), ("second", readings[1]), ("neither", sum(readings) / 2)):
        problem, dataset = deepcopy(history["problem"]), deepcopy(history["dataset"])
        old_id = dataset["id"]
        dataset["id"] = "followup_dataset_" + name
        dataset["body"].update(parent_id=old_id, origin="hypothetical", change_reason="Explicit hypothetical fixed-pair check")
        dataset["body"]["rows"].append({"id": "followup_" + name, "time": design["selected_time"],
            "concentration": rational(value), "hard_allowance": design_request["future_hard_allowance"],
            "included": True, "original_values": {"concentration": rational(value)}, "source_asset_id": None,
            "notes": "Synthetic hypothetical reading; not acquired"})
        dataset["digest"] = semantic_digest("dataset", dataset["body"])
        problem["id"] = "followup_problem_" + name
        problem["body"].update(dataset_id=dataset["id"], dataset_digest=dataset["digest"])
        problem["digest"] = semantic_digest("problem", problem["body"])
        run_id = "followup_run_" + name
        context = {"run_id": run_id, "scenario_id": "baseline", "workflow": {
            "plan_id": "followup_plan_" + name, "approval_id": "followup_approval_" + name,
            "operation_id": run_id, "execution_id": run_id}, "historical_artifact": original, "design_request": design_request}
        result = adapter.review(problem, dataset, {"scientific_wall_seconds": 60}, context)
        assert "worker_error" not in result, result
        public = ScientificResult.model_validate({key: val for key, val in result.items() if not key.startswith("_")}).model_dump(mode="json")
        artifact = result["_native_artifacts"][0]
        cases[name] = {"adapter": adapter, "problem": problem, "dataset": dataset, "context": context,
                      "result": public, "artifact": artifact, "projection": result["_application_projection"]}
    return cases


def validation(case):
    context = case["context"]
    return {"content": base64.b64decode(case["artifact"]["content_base64"], validate=True),
        "anchor": case["artifact"]["anchor"], "projection": case["projection"],
        "job": {"id": context["run_id"], "plan_id": context["workflow"]["plan_id"], "approval_id": context["workflow"]["approval_id"]},
        "scenario_id": context["scenario_id"], "result": case["result"],
        "historical_artifact": context["historical_artifact"], "design_request": context["design_request"]}


@pytest.mark.parametrize("name,index", [("first", 0), ("second", 1), ("neither", None)])
def test_actual_followup_keeps_candidate_feedback_and_replayable_history(native_reviews, name, index):
    case = native_reviews[name]
    data = validation(case)
    validate_followup_packet(**data)
    assert followup_result_checked(case["result"])
    expected = set() if index is None else {case["context"]["design_request"]["candidate_ids"][index]}
    survivors = {row["candidate_id"] for row in case["result"]["candidate_results"] if row["verification"] == "valid"}
    assert survivors == expected
    fresh = case["adapter"].replay_native(data["content"], expected=data["anchor"])
    assert fresh == case["result"]["native_replay"]
    assert fresh["operation"] == "review" and fresh["dataset_origin"] == "hypothetical"
    assert fresh["replay"] == fresh["integrity"] == "passed" and fresh["verification"] == "valid"
    assert not fresh["search_replayed"] and "baseline_search" not in case["result"]
    packet = json.loads(data["content"])
    assert packet["history"] == case["context"]["historical_artifact"]
    science = json.loads(base64.b64decode(packet["scientific"]["bytes_base64"]))
    assert science["search"] is None and science["operation"] == "fixed_candidate_review"
    for candidate in case["result"]["candidate_results"]:
        if candidate["candidate_id"] not in expected:
            assert candidate["verification"] == "invalid"
            assert candidate["violating_observation_ids"] == ["followup_" + name]
    if name == "neither":
        assert case["result"]["scientific_outcome"] == "inconclusive"


@pytest.mark.parametrize("change", ["actual", "time", "allowance", "old_row"])
def test_native_review_rejects_unsupported_revised_inputs(native_reviews, change):
    case = deepcopy(native_reviews["first"])
    problem, dataset = case["problem"], case["dataset"]
    if change == "actual":
        dataset["body"]["origin"] = "actual"
    elif change == "old_row":
        dataset["body"]["rows"][0]["concentration"] = "999/1"
    else:
        dataset["body"]["rows"][-1]["time" if change == "time" else "hard_allowance"] = "7/1"
    dataset["digest"] = semantic_digest("dataset", dataset["body"])
    problem["body"]["dataset_digest"] = dataset["digest"]
    problem["digest"] = semantic_digest("problem", problem["body"])
    result = case["adapter"].review(problem, dataset, {"scientific_wall_seconds": 60}, case["context"])
    assert "worker_error" in result, result


@pytest.mark.parametrize("change", ["outcome", "candidate", "horizon", "exclude", "history", "approval", "anchor", "parent_anchor"])
def test_publication_rejects_mutated_followup_facts_and_scope(native_reviews, change):
    data = deepcopy(validation(native_reviews["neither"]))
    if change == "outcome":
        data["result"]["scientific_outcome"] = "no_counterexample_found"
    elif change == "candidate":
        data["result"]["candidates"][0]["parameter_vector"]["A"] = "1/1"
    elif change == "horizon":
        data["result"]["candidates"][0]["checked_horizon"] = "999/1"
    elif change == "parent_anchor":
        data["historical_artifact"]["anchors"]["design_digest"] = "0" * 64
    elif change == "exclude":
        data["result"]["candidate_results"][0]["verification"] = "valid"
    elif change == "history":
        data["historical_artifact"]["id"] = "other_design"
    elif change == "approval":
        data["job"]["approval_id"] = "another_approval"
    else:
        data["anchor"]["run_id"] = "other_run"
    with pytest.raises(DomainError):
        validate_followup_packet(**data)


def test_rehashed_followup_cannot_swap_selected_vectors(native_reviews):
    data = deepcopy(validation(native_reviews["first"]))
    packet = json.loads(data["content"])
    science = json.loads(base64.b64decode(packet["scientific"]["bytes_base64"]))
    science["candidates"][0]["parameters"] = science["candidates"][1]["parameters"]
    science["baseline_digest"] = semantic_digest("report", {key: val for key, val in science.items() if key != "baseline_digest"})
    raw = json.dumps(science, separators=(",", ":")).encode()
    packet["scientific"] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes_base64": base64.b64encode(raw).decode()}
    data["content"] = json.dumps(packet, separators=(",", ":")).encode()
    data["anchor"]["artifact_sha256"] = hashlib.sha256(data["content"]).hexdigest()
    with pytest.raises(DomainError, match="candidate IDs and vectors"):
        validate_followup_packet(**data)
