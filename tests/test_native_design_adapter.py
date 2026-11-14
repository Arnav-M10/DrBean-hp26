"""Actual discovered-pair design through the application-bound bridge.

Synthetic observations are input controls. No saved candidate pair or scientific
response is supplied to production design; every module fixture computes anew.
"""
import base64
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import os
import shutil

import pytest

from bean_api.canonical import semantic_digest
from bean_api.contracts import DesignRequestBody, DesignResult, ScientificResult
from bean_api.counterdex_adapter import CounterdexAdapter
from test_counterdex_adapter import reviewed_history


@pytest.fixture(scope="module")
def native_design_history():
    executable = os.getenv("BEAN_COUNTERDEX_PYTHON") or shutil.which("python3.11")
    if not executable:
        pytest.skip("A prepared Counterdex CPython 3.11 interpreter is required")
    adapter = CounterdexAdapter(executable)
    history = reviewed_history()
    baseline = adapter.investigate(history["problem"], history["dataset"], {"scientific_wall_seconds": 60},
        {"run_id": "computed_baseline", "scenario_id": "baseline", "workflow": history["workflow"]})
    assert "worker_error" not in baseline, baseline
    public = ScientificResult.model_validate({k: v for k, v in baseline.items() if not k.startswith("_")}).model_dump(mode="json")
    assert len(public["candidates"]) == 2
    artifact = baseline["_native_artifacts"][0]
    history.update(evidence={"id": "actual_evidence", "body": {
        "run_id": "computed_baseline", "scenario_id": "baseline", "problem_id": history["problem"]["id"],
        "expected_problem_digest": history["problem"]["digest"], "result": public}},
        historical_artifact={"id": artifact["id"], "sha256": artifact["sha256"],
            "bytes_base64": artifact["content_base64"], "anchors": artifact["anchor"]},
        workflow={"plan_id": "reviewed_design_plan", "approval_id": "separate_design_approval",
            "operation_id": "design_job", "execution_id": "design_job"},
        run_id="design_job", remaining_wall_seconds=60)
    request = DesignRequestBody(historical_run_id="computed_baseline", scenario_id="baseline",
        problem_id=history["problem"]["id"], problem_digest=history["problem"]["digest"],
        candidate_ids=[candidate["id"] for candidate in public["candidates"]],
        candidate_vectors=[candidate["parameter_vector"] for candidate in public["candidates"]],
        feasible_times=["8/1", "6/1"], future_hard_allowance="1/5", maximum_horizon="10/1",
        scientific_profile="counterdex.v1", requested_tier="checked_pair_separation",
        allowance_origin={"kind": "hypothetical", "description": "Explicit synthetic precision for a separately reviewed design"},
        allow_construction=True, allow_continuation=True, source_artifact_ids=[]).model_dump(mode="json")
    history["expected_request_digest"] = semantic_digest("design-request", request)
    return adapter, history, request


def decode(result):
    artifact = result["_native_artifacts"][0]
    content = base64.b64decode(artifact["content_base64"], validate=True)
    packet = json.loads(content)
    scientific = json.loads(base64.b64decode(packet["scientific"]["bytes_base64"], validate=True))
    return artifact, content, packet, scientific


def test_computed_pair_design_preserves_approved_grid_history_and_fresh_replay(native_design_history):
    adapter, history, request = native_design_history
    result = adapter.design(request, history)
    assert "worker_error" not in result, result
    DesignResult.model_validate({k: v for k, v in result.items() if not k.startswith("_")})
    assert result["design_tier"] == "checked_pair_separation"
    assert result["verification"] == "valid" and result["replay"] == "passed"
    assert result["candidate_ids"] == request["candidate_ids"]
    assert [option["time"] for option in result["options"]] == request["feasible_times"]
    assert result["selected_time"] == "8/1"
    assert all(Fraction(option["exact_margin"]) > 0 for option in result["options"])
    artifact, content, packet, scientific = decode(result)
    assert packet["binding"]["request"] == request
    assert packet["binding"]["mapping_policy"] == "DB-SC-1-design-to-groundwork-v2"
    assert scientific["design"]["allowance_origin"] == request["allowance_origin"]
    assert scientific["design"]["horizon_policy"]["maximum_horizon"] == "10/1"
    assert request.get("source_artifact_ids", []) == []
    assert packet["history"] == history["historical_artifact"]
    assert packet["binding"]["historical_evidence"] == history["evidence"]["body"]
    assert scientific["workflow"] == history["workflow"]
    assert packet["run_id"] == "design_job"
    assert artifact["anchor"]["app_request_digest"] == history["expected_request_digest"]
    assert artifact["anchor"]["design_digest"] == semantic_digest("design-request", scientific["design"])
    assert artifact["sha256"] == hashlib.sha256(content).hexdigest()
    fresh = adapter.replay_native(content, expected=artifact["anchor"])
    assert fresh == result["native_replay"]
    assert fresh["fresh_checked"]["selected_time"] == result["selected_time"]


@pytest.mark.parametrize("allowance,construction,continuation,tier,replay", [
    ("100/1", True, True, "no_separation_established", "passed"),
    ("1/5", False, False, "numerical_guidance", "unsupported"),
    ("1/5", True, False, "numerical_guidance", "unsupported"),
])
def test_checked_design_retains_no_separation_and_numerical_fallback(native_design_history, allowance, construction, continuation, tier, replay):
    adapter, history, request = deepcopy(native_design_history)
    request.update(future_hard_allowance=allowance, allow_construction=construction, allow_continuation=continuation)
    history["expected_request_digest"] = semantic_digest("design-request", request)
    result = adapter.design(request, history)
    assert "worker_error" not in result, result
    DesignResult.model_validate({k: v for k, v in result.items() if not k.startswith("_")})
    assert result["design_tier"] == tier and result["replay"] == replay
    if tier == "no_separation_established":
        assert result["selected_time"] is None
        assert all(Fraction(option["exact_margin"]) < 0 for option in result["options"])
    else:
        assert result["verification"] == "not_checked"
        assert all(option["exact_margin"] is None for option in result["options"])
    artifact, content, _, _ = decode(result)
    fresh = adapter.replay_native(content, expected=artifact["anchor"])
    assert fresh["integrity"] == "passed" and fresh["replay"] == replay


def test_reversed_approved_pair_preserves_vectors_and_allows_canonical_checker_order(native_design_history):
    adapter, history, request = deepcopy(native_design_history)
    request["candidate_ids"].reverse()
    request["candidate_vectors"].reverse()
    history["expected_request_digest"] = semantic_digest("design-request", request)
    result = adapter.design(request, history)
    assert "worker_error" not in result, result
    DesignResult.model_validate({k: v for k, v in result.items() if not k.startswith("_")})
    assert result["design_tier"] == "checked_pair_separation" and result["replay"] == "passed"
    assert result["candidate_ids"] == request["candidate_ids"]
    assert [item["candidate_id"] for item in result["candidate_results"]] == sorted(request["candidate_ids"])
    artifact, content, packet, scientific = decode(result)
    assert [item["id"] for item in scientific["design"]["candidates"]] == request["candidate_ids"]
    assert [item["parameters"] for item in scientific["design"]["candidates"]] == request["candidate_vectors"]
    assert packet["binding"]["request"] == request
    assert adapter.replay_native(content, expected=artifact["anchor"])["replay"] == "passed"


@pytest.mark.parametrize("field", ["expected_request_digest", "source_artifact_ids", "requested_tier"])
def test_native_design_does_not_replace_reviewed_scope(native_design_history, field):
    adapter, history, request = deepcopy(native_design_history)
    if field == "expected_request_digest":
        history[field] = "0" * 64
    else:
        request[field] = [history["historical_artifact"]["id"]] if field == "source_artifact_ids" else "unsupported_tier"
        history["expected_request_digest"] = semantic_digest("design-request", request)
    result = adapter.design(request, history)
    assert result["worker_error"] in {"binding_mismatch", "unsupported_artifact_reuse", "unsupported_design_tier"}


def test_native_design_rejects_prospective_reuse_before_any_child_computation(native_design_history, monkeypatch):
    adapter, history, request = deepcopy(native_design_history)
    request["source_artifact_ids"] = [history["historical_artifact"]["id"]]
    history["expected_request_digest"] = semantic_digest("design-request", request)
    monkeypatch.setattr(adapter, "_run", lambda *_: pytest.fail("Unsupported reuse must be rejected before dispatch"))
    assert adapter.design(request, history) == {"worker_error": "unsupported_artifact_reuse"}


def test_explicit_numerical_request_keeps_tier_provenance_horizon_and_zero_pair_budget(native_design_history):
    adapter, history, request = deepcopy(native_design_history)
    request.update(requested_tier="numerical_guidance", allow_construction=False, allow_continuation=False)
    request["budget"].update(fixed_vector_constructions=0, pair_verifications=0)
    history["expected_request_digest"] = semantic_digest("design-request", request)
    result = adapter.design(request, history)
    assert "worker_error" not in result, result
    DesignResult.model_validate({k: v for k, v in result.items() if not k.startswith("_")})
    _, content, packet, scientific = decode(result)
    assert result["design_tier"] == "numerical_guidance"
    assert result["verification"] == "not_checked" and result["replay"] == "unsupported"
    assert packet["binding"]["request"] == request
    assert scientific["design"]["requested_tier"] == "numerical_guidance"
    assert scientific["design"]["horizon_policy"]["maximum_horizon"] == "10/1"
    assert scientific["design"]["allowance_origin"] == request["allowance_origin"]
    assert scientific["report"]["checked"]["construction_attempts"] == 0
    assert scientific["report"]["checked"]["pair_verification_passes"] == 0
    assert adapter.replay_native(content, expected=result["_native_artifacts"][0]["anchor"])["integrity"] == "passed"


def test_genuine_legacy_native_request_keeps_its_original_mapping(native_design_history):
    adapter, history, request = deepcopy(native_design_history)
    for field in ("scientific_profile", "requested_tier", "maximum_horizon", "allowance_origin"):
        request.pop(field)
    history["expected_request_digest"] = semantic_digest("design-request", request)
    result = adapter.design(request, history)
    assert "worker_error" not in result, result
    _, _, packet, scientific = decode(result)
    assert packet["binding"]["mapping_policy"] == "DB-SC-1-to-groundwork-v1"
    assert scientific["design"]["horizon_policy"]["maximum_horizon"] == "8/1"
    assert scientific["design"]["allowance_origin"]["kind"] == "reviewed_hard_bound"
    assert result["design_tier"] == "checked_pair_separation" and result["replay"] == "passed"


def test_capabilities_report_observed_runtime_and_admitted_operations(native_design_history):
    adapter, _, _ = native_design_history
    capabilities = adapter.capabilities()
    assert capabilities["adapter_version"] == capabilities["runtime"]["adapter_version"] == "0.3.0"
    assert capabilities["native_recheck"] is True
    assert capabilities["native_followup"]["hypothetical_only"] is False
    assert capabilities["native_design_requested_tiers"] == ["numerical_guidance", "checked_pair_separation"]


@pytest.fixture(scope="module")
def computed_design_transport(native_design_history):
    adapter, history, request = native_design_history
    projection = adapter.admission_projection(history["problem"], history["dataset"])
    design = adapter._native_design_projection(request, projection, history["expected_request_digest"])
    response = adapter._run({"protocol": "counterdex.bridge.v1", "operation": "design", "problem": history["problem"],
        "dataset": history["dataset"], "run_id": history["run_id"], "workflow": history["workflow"], "request": request,
        "expected_request_digest": history["expected_request_digest"], "historical_evidence": history["evidence"]["body"],
        "historical_artifact": history["historical_artifact"]}, 60)
    assert "worker_error" not in response, response
    return response, projection, design


@pytest.mark.parametrize("tamper", ["sha", "anchor", "history", "workflow", "grid", "selected_time", "candidate", "fresh_margin"])
def test_native_design_transport_cannot_upgrade_or_rebind_computation(native_design_history, computed_design_transport, tamper):
    adapter, history, request = native_design_history
    response, projection, design = deepcopy(computed_design_transport)
    if tamper == "sha":
        response["native_artifacts"][0]["sha256"] = "0" * 64
    elif tamper == "anchor":
        response["anchors"]["run_id"] = "another_design"
    elif tamper == "selected_time":
        response["result"]["selected_time"] = "6/1"
    elif tamper == "candidate":
        response["result"]["candidate_ids"] = list(reversed(request["candidate_ids"]))
    elif tamper == "fresh_margin":
        response["details"]["fresh_replay"]["fresh_checked"]["rows"][0]["margin"] = "999/1"
        response["result"]["options"][1]["exact_margin"] = "999/1"
    else:
        artifact = response["native_artifacts"][0]
        packet = json.loads(base64.b64decode(artifact["bytes_base64"]))
        if tamper == "history":
            packet["history"]["id"] = "different_baseline_artifact"
        elif tamper == "grid":
            packet["binding"]["approved_grid_order"].reverse()
        else:
            scientific = json.loads(base64.b64decode(packet["scientific"]["bytes_base64"]))
            scientific["workflow"]["approval_id"] = "different_approval"
            raw = json.dumps(scientific, sort_keys=True, separators=(",", ":")).encode()
            packet["scientific"] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes_base64": base64.b64encode(raw).decode()}
        content = json.dumps(packet, sort_keys=True, separators=(",", ":")).encode()
        digest = hashlib.sha256(content).hexdigest()
        artifact.update(sha256=digest, byte_size=len(content), bytes_base64=base64.b64encode(content).decode())
        response["anchors"]["artifact_sha256"] = digest
    result = adapter._native_design_output(response, request, history, projection, design)
    assert result["worker_error"] in {"binding_mismatch", "artifact_mismatch"}
