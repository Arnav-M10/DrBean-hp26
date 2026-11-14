"""Approved-scope and fresh-fact checks for native application design packets.

Counterdex owns mathematical projection and checking. These guards compare its
export with the immutable application records and independently retained history.
"""
from __future__ import annotations

import base64
from fractions import Fraction
import hashlib

from .baseline_evidence import MAPPING_POLICY, NATIVE_PROFILE, expected_baseline_anchor
from .canonical import parse_json_strict, semantic_digest
from .workflow import DomainError

DESIGN_BINDING = "counterdex.application-design-binding.v1"
CHECKED_POLICY = "positive-margin-descending-time-ids.v1"
NUMERICAL_POLICY = "pair-gap-over-allowance-12sig-half-even.v1"
NATIVE_LIMIT = 4 * 1024 * 1024


def _require(condition, message):
    if not condition:
        raise DomainError("binding_mismatch", message)


def expected_design_anchor(projection, *, problem, dataset, job, request,
                           request_digest, scientific_design_digest):
    anchor = expected_baseline_anchor(projection, problem=problem, dataset=dataset,
                                      job=job, scenario_id=request["scenario_id"])
    _require(semantic_digest("design-request", request) == request_digest
             and request["problem_id"] == problem["id"]
             and request["problem_digest"] == problem["digest"],
             "The native design must bind the exact approved request and historical problem.")
    return {**anchor, "app_request_digest": request_digest, "design_digest": scientific_design_digest}


def _decode(encoded, digest):
    raw = base64.b64decode(encoded, validate=True)
    _require(bool(raw) and len(raw) <= NATIVE_LIMIT and hashlib.sha256(raw).hexdigest() == digest,
             "Native evidence bytes do not match their independently retained identity.")
    value = parse_json_strict(raw, max_bytes=NATIVE_LIMIT)
    _require(isinstance(value, dict), "Native evidence must contain a structured packet.")
    return raw, value


def _approved_scientific_scope(design, *, projection, request, request_digest):
    """Compare declared constraints, never compute an experimental-design score."""
    problem = projection["problem"]
    expected_candidates = [{"id": identity, "parameters": vector,
                            "problem_digest": projection["projection_digest"], "source_artifact_digest": None}
                           for identity, vector in zip(request["candidate_ids"], request["candidate_vectors"], strict=True)]
    expected_grid = [{"time": time, "feasible": True, "reason": "Reviewed application feasible time"}
                     for time in sorted(request["feasible_times"], key=Fraction)]
    horizon = max([Fraction(row["time"]) for row in problem["observations"] if row["included"]]
                  + [Fraction(time) for time in request["feasible_times"]])
    budget = request["budget"]
    expected_limits = {"wall_seconds": budget["wall_seconds"], "max_times": len(expected_grid),
                       "max_constructions": budget["fixed_vector_constructions"],
                       "max_pair_verifications": budget["pair_verifications"],
                       "max_bundle_bytes": budget["bundle_bytes"],
                       "max_certificate_bytes": min(2 * 1024 * 1024, budget["bundle_bytes"])}
    _require(design.get("schema_version") == "groundwork.design.v1"
             and design.get("problem_digest") == projection["projection_digest"]
             and design.get("scenario_id") == request["scenario_id"]
             and design.get("candidates") == expected_candidates
             and design.get("grid") == expected_grid
             and design.get("observable") == "c" and design.get("time_origin") == problem["time_origin"]
             and design.get("future_allowance") == request["future_hard_allowance"]
             and design.get("allowance_origin") == {"kind": "reviewed_hard_bound",
                 "description": f"Approved DB-SC-1 design request {request_digest}; future_hard_allowance"}
             and design.get("requested_tier") == request["requested_tier"] == "checked_pair_separation"
             and design.get("checked_policy") == CHECKED_POLICY
             and design.get("numerical_policy") == NUMERICAL_POLICY
             and design.get("limits") == expected_limits
             and horizon <= Fraction(request["maximum_horizon"])
             and design.get("horizon_policy") == {"allow_construction": request["allow_construction"],
                 "allow_extension": request["allow_continuation"], "maximum_horizon": str(horizon.numerator) + "/" + str(horizon.denominator)},
             "The scientific design changes the approved pair, grid, allowance, policy, horizon or resource scope.")


def _faithful_result(result, science, request):
    fresh = result.get("native_replay") or {}
    checked = fresh.get("fresh_checked") or {}
    verified = checked.get("verification") == "valid" and fresh.get("replay") == "passed"
    report = science["report"]
    rows = checked["rows"] if verified else report["numerical"]["rows"]
    by_time = {row["time"]: row for row in rows}
    _require(len(by_time) == len(rows) == len(request["feasible_times"])
             and set(by_time) == set(request["feasible_times"]),
             "The retained design must account for every approved time exactly once.")
    options = [{"time": time, "state": by_time[time]["status"],
                "reason_code": by_time[time].get("reason_code") or ("exact_margin_checked" if verified else "numerical_only"),
                "exact_margin": by_time[time].get("margin") if verified else None}
               for time in request["feasible_times"]]
    expected = {"design_tier": checked["tier"] if verified else report["tier"],
                "verification": fresh["verification"], "replay": fresh["replay"],
                "reason_code": (checked.get("reason_code") or "strict_positive_margin") if verified else fresh["reason_code"],
                "selected_time": checked["selected_time"] if verified else report["numerical"]["selected_time"],
                "options": options, "algorithm": CHECKED_POLICY if verified else NUMERICAL_POLICY,
                "candidate_ids": request["candidate_ids"], "future_hard_allowance": request["future_hard_allowance"],
                "candidate_results": fresh.get("candidate_results", [])}
    _require(all(result.get(key) == value for key, value in expected.items()),
             "Published design facts must match the retained fresh replay and approved grid order.")


def validate_design_packet(content, anchor, *, projection, job, request, request_digest,
                           historical_evidence, historical_artifact, result):
    try:
        packet = parse_json_strict(content, max_bytes=NATIVE_LIMIT)
        binding = packet["binding"]
        _, science = _decode(packet["scientific"]["bytes_base64"], packet["scientific"]["sha256"])
        raw_parent, parent = _decode(historical_artifact["bytes_base64"], historical_artifact["sha256"])
        design_digest = semantic_digest("design-request", science["design"])
        suggestion_digest = semantic_digest("suggestion", {k: v for k, v in science.items() if k != "suggestion_digest"})
        expected = expected_design_anchor(projection, problem=projection["binding"]["problem"],
            dataset=projection["binding"]["dataset"], job=job, request=request,
            request_digest=request_digest, scientific_design_digest=design_digest)
        _require(len(content) <= request["budget"]["bundle_bytes"]
                 and anchor == {**expected, "artifact_sha256": hashlib.sha256(content).hexdigest()},
                 "The design replay anchor must exactly identify its approved scope and native bytes.")
        _require(packet.get("schema_version") == NATIVE_PROFILE and packet.get("operation") == "design"
                 and packet.get("run_id") == job["id"] and packet.get("scenario_id") == request["scenario_id"]
                 and binding == {"schema_version": DESIGN_BINDING, "mapping_policy": MAPPING_POLICY,
                     "application": projection["binding"], "request": request, "request_digest": request_digest,
                     "historical_evidence": historical_evidence, "design_digest": design_digest,
                     "approved_grid_order": request["feasible_times"]}
                 and packet.get("history") == historical_artifact
                 and science.get("problem") == projection["problem"]
                 and science.get("workflow") == {"plan_id": job["plan_id"], "approval_id": job["approval_id"],
                     "operation_id": job["id"], "execution_id": job["id"]},
                 "Native design bytes do not bind the approved job, request and original evidence.")
        expected_parent = {**expected, "run_id": request["historical_run_id"],
                           "app_request_digest": None, "design_digest": None,
                           "artifact_sha256": historical_artifact["sha256"]}
        _require(parent.get("operation") == "investigate" and parent.get("history") is None
                 and parent.get("binding") == projection["binding"]
                 and parent.get("run_id") == request["historical_run_id"]
                 and parent.get("scenario_id") == request["scenario_id"]
                 and historical_artifact["anchors"] == expected_parent
                 and historical_evidence["run_id"] == request["historical_run_id"]
                 and historical_evidence["scenario_id"] == request["scenario_id"]
                 and historical_evidence["problem_id"] == request["problem_id"]
                 and historical_evidence["expected_problem_digest"] == request["problem_digest"]
                 and request["source_artifact_ids"] == [historical_artifact["id"]]
                 and any(ref["id"] == historical_artifact["id"] and ref["sha256"] == historical_artifact["sha256"]
                         and ref["byte_size"] == len(raw_parent)
                         for ref in historical_evidence["result"]["artifacts"]),
                 "The original baseline bytes and external anchors must belong to the selected historical scenario.")
        fresh = result.get("native_replay") or {}
        record = result.get("verification_record") or {}
        _require(science.get("suggestion_digest") == suggestion_digest == result.get("native_suggestion_digest")
                 and fresh.get("suggestion_digest") == suggestion_digest
                 and result.get("scientific_design_digest") == design_digest
                 and result.get("scientific_problem_digest") == projection["projection_digest"]
                 and fresh.get("anchors") == anchor and fresh.get("packet_profile") == NATIVE_PROFILE
                 and fresh.get("operation") == "design" and fresh.get("integrity") == "passed"
                 and fresh.get("expected_binding") == record.get("expected_binding") == "matches"
                 and fresh.get("verification") == record.get("verification") == result.get("verification")
                 and record.get("expected_problem_digest") == record.get("observed_problem_digest") == request["problem_digest"]
                 and record.get("expected_scientific_problem_digest") == record.get("observed_scientific_problem_digest") == projection["projection_digest"]
                 and record.get("artifact_sha256") == anchor["artifact_sha256"]
                 and any(ref["id"] == record.get("artifact_id") and ref["sha256"] == anchor["artifact_sha256"]
                         and ref["byte_size"] == len(content) for ref in result["artifacts"]),
                 "Fresh design replay must describe these exact retained bytes and expected identities.")
        _approved_scientific_scope(science["design"], projection=projection, request=request, request_digest=request_digest)
        _faithful_result(result, science, request)
        if result["verification"] == "valid":
            _require(design_result_checked(result), "A checked design requires matching fresh mathematical facts.")
    except (KeyError, TypeError, ValueError, AttributeError):
        raise DomainError("invalid_native_artifact", "The native design packet is incomplete or malformed.") from None


def design_result_checked(result):
    """A checked label requires fresh matching facts, including no-separation."""
    try:
        return _design_result_checked(result)
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


def _design_result_checked(result):
    fresh = result.get("native_replay") or {}
    checked = fresh.get("fresh_checked") or {}
    record = result.get("verification_record") or {}
    anchors = fresh.get("anchors") or {}
    if not (result.get("projection_version") == MAPPING_POLICY
            and fresh.get("packet_profile") == NATIVE_PROFILE and fresh.get("operation") == "design"
            and fresh.get("integrity") == "passed" and fresh.get("expected_binding") == "matches"
            and result.get("replay") == fresh.get("replay") == "passed"
            and result.get("verification") == fresh.get("verification") == checked.get("verification") == record.get("verification") == "valid"
            and checked.get("expected_binding") == record.get("expected_binding") == "matches"
            and fresh.get("recorded_result_matches") is True
            and result.get("native_suggestion_digest") == fresh.get("suggestion_digest")
            and anchors.get("projection_digest") == result.get("scientific_problem_digest") == record.get("expected_scientific_problem_digest") == record.get("observed_scientific_problem_digest")
            and anchors.get("problem_digest") == record.get("expected_problem_digest") == record.get("observed_problem_digest")
            and anchors.get("design_digest") == result.get("scientific_design_digest")
            and anchors.get("artifact_sha256") == record.get("artifact_sha256")
            and checked.get("tier") == result.get("design_tier")
            and checked.get("selected_time") == result.get("selected_time")
            and (checked.get("reason_code") or "strict_positive_margin") == result.get("reason_code")
            and result.get("algorithm") == CHECKED_POLICY
            and checked.get("candidate_results") == fresh.get("candidate_results") == result.get("candidate_results")):
        return False
    rows = checked.get("rows", [])
    options = result.get("options", [])
    indexed = {row["time"]: row for row in rows}
    return (len(indexed) == len(rows) == len(options)
            and [item["candidate_id"] for item in checked.get("candidate_results", [])] == result.get("candidate_ids")
            and all(option["time"] in indexed
                    and option["state"] == indexed[option["time"]]["status"]
                    and option.get("exact_margin") == indexed[option["time"]].get("margin")
                    and option.get("reason_code") == (indexed[option["time"]].get("reason_code") or "exact_margin_checked")
                    for option in options))
