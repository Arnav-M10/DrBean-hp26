"""Actual prepared Counterdex computations; candidate constants are test oracles only."""
import base64
import copy
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import shutil

import pytest

from bean_api.canonical import semantic_digest
from bean_api.contracts import DatasetBody, DesignRequestBody, DesignResult, ProblemBody
from bean_api.counterdex_adapter import CounterdexAdapter, create_science_adapter
from bean_api.scientific_projection import admit_problem, project_design, project_problem
from bean_api.workflow import DomainError


def rational(value):
    exact = Fraction(value)
    return f"{exact.numerator}/{exact.denominator}"


def envelope(kind, body, identifier):
    return {"id": identifier, "digest": semantic_digest(kind, body), "body": body}


def reviewed_history(followup=None):
    rows = [{"id": f"r{i}", "time": rational(t), "concentration": rational(value),
             "hard_allowance": "1/2", "included": True,
             "original_values": {"time": t, "concentration": value}}
            for i, (t, value) in enumerate(zip(["0.25", "0.5", "1", "2", "4"], ["4.80", "7.20", "8.00", "6.80", "5.70"]))]
    if followup:
        rows.append({"id": "hypothetical_followup", "time": "8/1", "concentration": rational(followup),
                     "hard_allowance": "1/5", "included": True, "notes": "Explicit hypothetical test fork"})
    dataset = envelope("dataset", DatasetBody(experiment_id="synthetic_hero", time_origin="elapsed from synthetic t=0",
        rows=rows, origin="hypothetical" if followup else "synthetic", change_reason="Explicit synthetic integration control").model_dump(mode="json"), "dataset")
    problem = envelope("problem", ProblemBody(dataset_id=dataset["id"], dataset_digest=dataset["digest"],
        domain={"A": {"lower": "1/1000", "upper": "30/1"}, "ke": {"lower": "3/200", "upper": "7/20"},
                "ka": {"lower": "2/5", "upper": "8/1"}}, target={"lower": "1/10", "upper": "17/100"}).model_dump(mode="json"), "problem")
    return {"problem": problem, "dataset": dataset, "workflow": {"plan_id": "test_plan", "approval_id": "test_approval", "operation_id": "test_operation", "execution_id": "test_execution"}}


def request(history, *, times=None, allowance="1/5"):
    return DesignRequestBody(historical_run_id="run", scenario_id="baseline", problem_id="problem",
        problem_digest=history["problem"]["digest"], candidate_ids=["reference", "outside"], candidate_vectors=[
            {"A": rational("9.041075603155"), "ke": rational("0.122"), "ka": rational("3.54")},
            {"A": rational("8.267973235218"), "ke": rational("0.074"), "ka": rational("4.17")}],
        feasible_times=times or ["8/1", "6/1"], future_hard_allowance=allowance,
        scientific_profile="counterdex.v1", requested_tier="checked_pair_separation",
        allowance_origin={"kind": "hypothetical", "description": "Reviewed test allowance, not inherited from history"},
        maximum_horizon="8/1", allow_construction=True, allow_continuation=True).model_dump(mode="json")


@pytest.fixture
def adapter():
    executable = os.getenv("BEAN_COUNTERDEX_PYTHON") or shutil.which("python3.11")
    if not executable:
        candidate = Path("/workspace/.python/cpython-3.11-linux-x86_64-gnu/bin/python3.11")
        executable = str(candidate) if candidate.exists() else None
    if executable is None:
        pytest.skip("Prepared Counterdex CPython3.11 runtime is required for these actual scientific controls")
    return CounterdexAdapter(executable)


def test_missing_runtime_is_infrastructure_failure():
    adapter = create_science_adapter("/not-installed/python3.11")
    assert adapter.capabilities()["reason"] == "scientific_runtime_missing"
    history = reviewed_history()
    assert adapter.investigate(history["problem"], history["dataset"], {"scientific_wall_seconds": 3}) == {"worker_error": "scientific_runtime_missing"}


def test_projection_preserves_identity_origin_order_and_spellings():
    history = reviewed_history()
    projected = project_problem(history["problem"], history["dataset"])
    assert projected["dataset_kind"] == "hypothetical"
    assert '"application_origin":"synthetic"' in projected["provenance"]
    assert '"concentration":"4.80"' in projected["observations"][0]["provenance"]
    assert [row["id"] for row in projected["observations"]] == [f"r{i}" for i in range(5)]
    assert semantic_digest("problem", projected) != history["problem"]["digest"]
    changed = copy.deepcopy(history)
    changed["dataset"]["body"]["rows"][0]["original_values"]["concentration"] = "4.800"
    changed["dataset"]["digest"] = semantic_digest("dataset", changed["dataset"]["body"])
    changed["problem"]["body"]["dataset_digest"] = changed["dataset"]["digest"]
    changed["problem"]["digest"] = semantic_digest("problem", changed["problem"]["body"])
    assert semantic_digest("problem", project_problem(changed["problem"], changed["dataset"])) != semantic_digest("problem", projected)


@pytest.mark.parametrize("mutate,path", [
    (lambda p, d: d.update(rows=d["rows"][:2]), "rows"),
    (lambda p, d: p["domain"]["ka"].update(lower="1/10"), "domain"),
    (lambda p, d: p["domain"]["A"].update(lower="30/1"), "domain.A"),
    (lambda p, d: d["rows"][0].update(time=f"{2**257}/1"), "rows[0].time"),
])
def test_engine_admission_rejects_without_silent_repair(mutate, path):
    history = reviewed_history()
    p, d = history["problem"]["body"], history["dataset"]["body"]
    mutate(p, d)
    with pytest.raises(DomainError) as error:
        admit_problem(p, d)
    assert path in error.value.field_paths


@pytest.mark.parametrize("mutate,path", [
    (lambda req: req["budget"].update(pair_verifications=1), "budget.pair_verifications"),
    (lambda req: req["candidate_vectors"][0].update(A="31/1"), "candidate_vectors[0].A"),
    (lambda req: req["candidate_vectors"][0].update(A=f"1/{2**257}"), "candidate_vectors[0].A"),
    (lambda req: req.update(candidate_vectors=[req["candidate_vectors"][0]] * 2), "candidate_vectors"),
    (lambda req: req["allowance_origin"].update(description="  "), "allowance_origin.description"),
])
def test_design_admission_precedes_scientific_execution(mutate, path):
    history = reviewed_history()
    reviewed = request(history)
    mutate(reviewed)
    with pytest.raises(DomainError) as error:
        project_design(reviewed, project_problem(history["problem"], history["dataset"]), [None, None])
    assert path in error.value.field_paths


def test_excluded_future_observation_retained_without_extending_checked_horizon(adapter):
    history = reviewed_history()
    dataset = history["dataset"]["body"]
    dataset["rows"].append({**dataset["rows"][0], "id": "excluded_future", "time": "30/1", "included": False})
    history["dataset"]["digest"] = semantic_digest("dataset", dataset)
    history["problem"]["body"]["dataset_digest"] = history["dataset"]["digest"]
    history["problem"]["digest"] = semantic_digest("problem", history["problem"]["body"])
    result = adapter.design(request(history), history)
    assert result["verification"] == "valid"
    native = json.loads(base64.b64decode(result["_native_artifacts"][0]["content_base64"]))
    assert native["problem"]["observations"][-1]["id"] == "excluded_future"
    assert native["problem"]["observations"][-1]["included"] is False


def test_reuses_complete_native_pair_without_new_construction(adapter):
    history = reviewed_history()
    first = adapter.design(request(history), history)
    bundle = json.loads(base64.b64decode(first["_native_artifacts"][0]["content_base64"]))
    pair = bundle["artifacts"][0]
    history["native_artifacts"] = [{"id": "approved_pair", "sha256": pair["digest"], "content_base64": pair["content"]}]
    reviewed = request(history)
    reviewed.update(source_artifact_ids=["approved_pair"], allow_construction=False, allow_continuation=False)
    result = adapter.design(reviewed, history)
    assert result["native_replay"]["replay"] == "passed"
    native = json.loads(base64.b64decode(result["_native_artifacts"][0]["content_base64"]))
    assert native["report"]["checked"]["construction_attempts"] == 0
    history["native_artifacts"][0]["content_base64"] = base64.b64encode(b"changed native bytes").decode()
    assert adapter.design(reviewed, history)["worker_error"] == "artifact_mismatch"


def test_numerical_scope_does_not_inherit_checked_label(adapter):
    history = reviewed_history()
    reviewed = request(history)
    reviewed.update(requested_tier="numerical_guidance", allow_construction=False, allow_continuation=False)
    reviewed["budget"].update(pair_verifications=0, fixed_vector_constructions=0)
    result = adapter.design(reviewed, history)
    assert result["design_tier"] == "numerical_guidance"
    assert result["verification"] == "not_checked"
    assert result["verification_record"] is None
    assert result["native_replay"]["replay"] == "unsupported"
    assert result["native_replay"]["integrity"] == "passed"
    assert [option["time"] for option in result["options"]] == reviewed["feasible_times"]


@pytest.mark.parametrize("change,error", [
    ("design_digest", "scientific_projection_mismatch"),
    ("suggestion_digest", "artifact_mismatch"),
    ("workflow", "scientific_projection_mismatch"),
])
def test_native_output_cannot_replace_independently_expected_scope(adapter, monkeypatch, change, error):
    real_run = adapter._run

    def changed_response(payload, wall_seconds):
        result = real_run(payload, wall_seconds)
        if change in {"design_digest", "suggestion_digest"}:
            result[change] = "f" * 64
        else:
            # A replacement packet with consistent byte hashes still cannot
            # change the workflow IDs supplied by the approved parent scope.
            bundle = json.loads(base64.b64decode(result["content_base64"]))
            bundle["workflow"]["plan_id"] = "other_plan"
            bundle["suggestion_digest"] = semantic_digest("suggestion", {key: value for key, value in bundle.items() if key != "suggestion_digest"})
            content = json.dumps(bundle, sort_keys=True, separators=(",", ":")).encode()
            result.update(content_base64=base64.b64encode(content).decode(), byte_size=len(content),
                          sha256=hashlib.sha256(content).hexdigest(), suggestion_digest=bundle["suggestion_digest"])
        return result

    monkeypatch.setattr(adapter, "_run", changed_response)
    history = reviewed_history()
    assert adapter.design(request(history), history) == {"worker_error": error}


def test_real_design_native_bytes_and_fresh_replay(adapter):
    history = reviewed_history()
    result = adapter.design(request(history), history)
    assert "worker_error" not in result, result
    native = result.pop("_native_artifacts")[0]
    validated = DesignResult.model_validate(result)
    assert validated.design_tier == "checked_pair_separation"
    assert validated.selected_time == "8/1"
    assert [option.time for option in validated.options] == ["8/1", "6/1"]
    assert validated.replay == "passed"
    assert all(row.verification == "valid" for row in validated.candidate_results)
    assert Fraction(validated.options[0].exact_margin) > 0
    content = base64.b64decode(native["content_base64"])
    assert hashlib.sha256(content).hexdigest() == native["sha256"]
    anchors = native["anchor"]
    assert anchors["scientific_problem_digest"] != anchors["application_problem_digest"]
    fresh = adapter.replay(content, expected_problem_digest=anchors["scientific_problem_digest"], expected_suggestion_digest=anchors["native_suggestion_digest"])
    assert fresh["replay"] == "passed"
    corrupted = adapter.replay(content.replace(b'"test_plan"', b'"evil_plan"'), expected_problem_digest=anchors["scientific_problem_digest"], expected_suggestion_digest=anchors["native_suggestion_digest"])
    assert corrupted["worker_error"] == "artifact_mismatch"
    wrong_anchor = adapter.replay(content, expected_problem_digest="0" * 64, expected_suggestion_digest=anchors["native_suggestion_digest"])
    assert wrong_anchor["worker_error"] == "wrong_specification_binding"


@pytest.mark.parametrize("times,allowance,selected,tier", [(["6/1"], "1/5", "6/1", "checked_pair_separation"), (["6/1", "8/1"], "3/5", None, "no_separation_established")])
def test_real_constraint_changes_compute_new_result(adapter, times, allowance, selected, tier):
    history = reviewed_history()
    result = adapter.design(request(history, times=times, allowance=allowance), history)
    assert result["design_tier"] == tier, result
    assert result["selected_time"] == selected
    assert result["replay"] == "passed"


@pytest.mark.parametrize("value,excluded", [("3.4", {"outside"}), ("4.57", {"reference"}), ("4.0", {"reference", "outside"})])
def test_actual_fixed_candidate_exclusion_remains_scientific_feedback(adapter, value, excluded):
    history = reviewed_history(value)
    result = adapter.design(request(history), history)
    assert "worker_error" not in result, result
    result.pop("_native_artifacts")
    DesignResult.model_validate(result)
    assert {row["candidate_id"] for row in result["candidate_results"] if row["verification"] == "invalid"} == excluded
    assert result["native_replay"]["integrity"] == "passed"
    assert result["native_replay"]["recorded_result_matches"] is True
    assert result["verification"] == "invalid" and result["replay"] == "failed"


def test_baseline_requires_server_owned_execution_scope(adapter):
    history = reviewed_history()
    result = adapter.investigate(history["problem"], history["dataset"], {"scientific_wall_seconds": 3})
    assert result == {"worker_error": "scientific_scope_required"}
