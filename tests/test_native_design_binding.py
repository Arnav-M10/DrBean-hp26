"""Adversarial publication checks against freshly computed native designs.

Only measurements are loaded from the synthetic example. Every candidate,
baseline byte and design byte below comes from the real prepared interpreter.
"""
import base64
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import shutil

import pytest

from bean_api.canonical import semantic_digest
from bean_api.contracts import DesignRequestBody
from bean_api.counterdex_adapter import CounterdexAdapter
from bean_api.design_evidence import (design_result_checked, expected_design_anchor,
                                     validate_design_packet)
from bean_api.workflow import DomainError

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def native_designs():
    executable = os.getenv("BEAN_COUNTERDEX_PYTHON") or shutil.which("python3.11")
    if executable is None:
        pytest.skip("Prepared CPython 3.11 required for real design binding controls")
    adapter = CounterdexAdapter(executable)
    source = json.loads((ROOT / "packages/groundwork_adapter/fixtures/decision/hero-baseline.request.json").read_text())
    problem, dataset = source["problem"], source["dataset"]
    projection = adapter.admission_projection(problem, dataset)
    baseline = adapter._run({**source, "run_id": "binding_baseline", "scenario_id": "baseline",
        "workflow": {"plan_id": "baseline_plan", "approval_id": "baseline_approval",
                     "operation_id": "binding_baseline", "execution_id": "binding_baseline"}}, 120)
    assert baseline.get("ok") is True, baseline
    candidates = baseline["result"]["candidates"]
    assert len(candidates) == 2
    artifact = baseline["native_artifacts"][0]
    historical_artifact = {key: artifact[key] for key in ("id", "sha256", "bytes_base64")}
    historical_artifact["anchors"] = baseline["anchors"]
    evidence = {"run_id": "binding_baseline", "scenario_id": "baseline", "problem_id": problem["id"],
                "expected_problem_digest": problem["digest"], "result": baseline["result"],
                "arrived_after_cancel": False}
    contexts = {}
    for name, allowance, construct in (("checked", "1/5", True), ("wide", "3/5", True), ("numerical", "1/5", False)):
        request = DesignRequestBody.model_validate({"historical_run_id": "binding_baseline", "scenario_id": "baseline",
            "problem_id": problem["id"], "problem_digest": problem["digest"],
            "candidate_ids": [c["id"] for c in candidates], "candidate_vectors": [c["parameter_vector"] for c in candidates],
            "feasible_times": ["8/1", "6/1"], "future_hard_allowance": allowance,
            "scientific_profile": "counterdex.v1", "requested_tier": "checked_pair_separation",
            "allowance_origin": {"kind": "reviewed_hard_bound", "description": "Explicit synthetic future allowance"},
            "maximum_horizon": "8/1", "allow_construction": construct, "allow_continuation": construct,
            "source_artifact_ids": [artifact["id"]]}).model_dump(mode="json")
        request_digest = semantic_digest("design-request", request)
        job = {"id": "binding_design_" + name, "plan_id": "design_plan_" + name, "approval_id": "design_approval_" + name}
        response = adapter._run({"protocol": "counterdex.bridge.v1", "operation": "design",
            "problem": problem, "dataset": dataset, "run_id": job["id"],
            "workflow": {"plan_id": job["plan_id"], "approval_id": job["approval_id"],
                         "operation_id": job["id"], "execution_id": job["id"]},
            "request": request, "expected_request_digest": request_digest,
            "historical_evidence": evidence, "historical_artifact": historical_artifact}, 120)
        assert response.get("ok") is True, response
        content = base64.b64decode(response["native_artifacts"][0]["bytes_base64"])
        packet = json.loads(content)
        science = json.loads(base64.b64decode(packet["scientific"]["bytes_base64"]))
        result = {**response["result"], "projection_version": "DB-SC-1-to-groundwork-v1",
            "scientific_problem_digest": projection["projection_digest"],
            "scientific_design_digest": packet["binding"]["design_digest"],
            "native_suggestion_digest": science["suggestion_digest"],
            "native_replay": response["details"]["fresh_replay"],
            "candidate_results": response["details"]["fresh_replay"].get("candidate_results", [])}
        result["verification_record"].update(expected_scientific_problem_digest=projection["projection_digest"],
                                              observed_scientific_problem_digest=projection["projection_digest"])
        contexts[name] = {"content": content, "anchor": response["anchors"], "projection": projection,
                          "job": job, "request": request, "request_digest": request_digest,
                          "historical_evidence": evidence, "historical_artifact": historical_artifact,
                          "result": result}
    return contexts


@pytest.mark.parametrize("name,tier,checked", [("checked", "checked_pair_separation", True),
                                               ("wide", "no_separation_established", True),
                                               ("numerical", "numerical_guidance", False)])
def test_actual_design_states_keep_faithful_scope_and_replay(native_designs, name, tier, checked):
    context = native_designs[name]
    validate_design_packet(**context)
    assert context["result"]["design_tier"] == tier
    assert design_result_checked(context["result"]) is checked
    assert [row["time"] for row in context["result"]["options"]] == ["8/1", "6/1"]


def test_expected_anchor_rejects_changed_reviewed_request(native_designs):
    context = deepcopy(native_designs["checked"])
    request = context["request"]
    request["future_hard_allowance"] = "1/10"
    with pytest.raises(DomainError, match="approved request"):
        expected_design_anchor(context["projection"], problem=context["projection"]["binding"]["problem"],
            dataset=context["projection"]["binding"]["dataset"], job=context["job"], request=request,
            request_digest=context["request_digest"], scientific_design_digest=context["result"]["scientific_design_digest"])


@pytest.mark.parametrize("field", ["artifact_sha256", "app_request_digest", "run_id", "scenario_id"])
def test_export_cannot_relabel_external_design_anchor(native_designs, field):
    context = deepcopy(native_designs["checked"])
    context["anchor"][field] = "0" * 64
    context["result"]["native_replay"]["anchors"][field] = "0" * 64
    with pytest.raises(DomainError, match="anchor"):
        validate_design_packet(**context)


def mutate_packet(context, mutation):
    packet = json.loads(context["content"])
    science = json.loads(base64.b64decode(packet["scientific"]["bytes_base64"]))
    mutation(packet, science)
    # Rehash every surrounding identity so rejection must be about the approved
    # external scope or fresh facts, not an accidentally stale wrapper hash.
    design_digest = semantic_digest("design-request", science["design"])
    packet["binding"]["design_digest"] = design_digest
    science["report"]["design_digest"] = design_digest
    science["suggestion_digest"] = semantic_digest("suggestion", {k: v for k, v in science.items() if k != "suggestion_digest"})
    raw = json.dumps(science, separators=(",", ":")).encode()
    packet["scientific"] = {"sha256": hashlib.sha256(raw).hexdigest(), "bytes_base64": base64.b64encode(raw).decode()}
    context["content"] = json.dumps(packet, separators=(",", ":")).encode()
    digest = hashlib.sha256(context["content"]).hexdigest()
    context["anchor"].update(artifact_sha256=digest, design_digest=design_digest)
    result = context["result"]
    result["scientific_design_digest"] = design_digest
    result["native_suggestion_digest"] = science["suggestion_digest"]
    result["native_replay"].update(anchors=deepcopy(context["anchor"]), suggestion_digest=science["suggestion_digest"])
    result["verification_record"]["artifact_sha256"] = digest
    result["artifacts"][0].update(sha256=digest, byte_size=len(context["content"]))


@pytest.mark.parametrize("mutation", ["approval", "history", "budget", "horizon", "pair", "grid"])
def test_rehashed_packet_cannot_replace_approved_context(native_designs, mutation):
    context = deepcopy(native_designs["checked"])
    def change(packet, science):
        if mutation == "approval":
            science["workflow"]["approval_id"] = "unrelated_approval"
        elif mutation == "history":
            packet["history"]["id"] = "unrelated_artifact"
        elif mutation == "budget":
            science["design"]["limits"]["max_constructions"] = 99
        elif mutation == "horizon":
            science["design"]["horizon_policy"]["maximum_horizon"] = "9/1"
        elif mutation == "pair":
            science["design"]["candidates"][0]["parameters"]["A"] = "1/1"
        else:
            science["design"]["grid"] = science["design"]["grid"][:1]
    mutate_packet(context, change)
    with pytest.raises(DomainError) as caught:
        validate_design_packet(**context)
    assert caught.value.code == "binding_mismatch"


@pytest.mark.parametrize("name,mutation", [("checked", "margin"), ("wide", "tier"), ("numerical", "margin")])
def test_result_cannot_upgrade_or_change_retained_scientific_facts(native_designs, name, mutation):
    context = deepcopy(native_designs[name])
    if mutation == "tier":
        context["result"]["design_tier"] = "checked_pair_separation"
    else:
        context["result"]["options"][0]["exact_margin"] = "100/1"
    with pytest.raises(DomainError, match="facts"):
        validate_design_packet(**context)
    assert not design_result_checked(context["result"])


def test_retained_history_bytes_must_match_independent_hash(native_designs):
    context = deepcopy(native_designs["checked"])
    context["historical_artifact"]["sha256"] = "0" * 64
    with pytest.raises(DomainError, match="independently retained"):
        validate_design_packet(**context)
