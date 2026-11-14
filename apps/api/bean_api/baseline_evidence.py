"""Application-scope checks for the engine's native baseline packet.

This boundary validates identities and faithful mapping of fresh checker facts;
Counterdex remains the mathematical checker. No numerical search lives here.
"""
from __future__ import annotations

import base64
import hashlib
import json

from .canonical import semantic_digest
from .contracts import CandidateResult
from .workflow import DomainError

MAPPING_POLICY = "DB-SC-1-to-groundwork-v1"
NATIVE_PROFILE = "counterdex.application-bundle.v1"
NATIVE_MEDIA_TYPE = "application/vnd.counterdex.native+json"


def expected_baseline_anchor(projection, *, problem, dataset, job, scenario_id):
    if not isinstance(projection, dict):
        raise DomainError("binding_mismatch", "Baseline output needs its admitted application projection.")
    binding = projection.get("binding") or {}
    for kind, expected in (("problem", problem), ("dataset", dataset)):
        if binding.get(kind) != {key: expected[key] for key in ("id", "digest", "body")}:
            raise DomainError("binding_mismatch", "Native baseline input differs from the approved immutable record.")
        if semantic_digest(kind, expected["body"]) != expected["digest"]:
            raise DomainError("binding_mismatch", "The immutable input digest is inconsistent.")
    digest = semantic_digest("problem", projection["problem"])
    if (binding.get("mapping_policy") != MAPPING_POLICY or binding.get("projection_digest") != digest
            or projection.get("projection_digest") != digest or binding.get("dataset_origin") != dataset["body"]["origin"]):
        raise DomainError("binding_mismatch", "Native baseline projection does not match its declared mapping.")
    return {"dataset_digest": dataset["digest"], "problem_digest": problem["digest"],
            "projection_digest": digest, "app_request_digest": None, "design_digest": None,
            "run_id": job["id"], "scenario_id": scenario_id}


def validate_baseline_packet(content, anchor, *, projection, job, scenario_id, result):
    try:
        packet = json.loads(content)
        scientific_ref = packet["scientific"]
        raw_science = base64.b64decode(scientific_ref["bytes_base64"], validate=True)
        science = json.loads(raw_science)
    except (ValueError, TypeError, KeyError):
        raise DomainError("invalid_native_artifact", "The native baseline packet is incomplete.") from None
    if (packet.get("schema_version") != NATIVE_PROFILE or packet.get("operation") != "investigate"
            or packet.get("history") is not None or packet.get("binding") != projection["binding"]
            or packet.get("run_id") != job["id"] or packet.get("scenario_id") != scenario_id
            or hashlib.sha256(raw_science).hexdigest() != scientific_ref["sha256"]
            or science.get("problem") != projection["problem"]
            or science.get("scenario_id") != scenario_id
            or science.get("workflow") != {"plan_id": job["plan_id"], "approval_id": job["approval_id"],
                "operation_id": job["id"], "execution_id": job["id"]}):
        raise DomainError("binding_mismatch", "Native baseline bytes do not bind the approved run and scenario.")
    fresh = result.get("native_replay") or {}
    if fresh.get("anchors") != anchor:
        raise DomainError("binding_mismatch", "Fresh replay must use the retained external anchor.")
    search = science.get("search") or {}
    summary = result.get("baseline_search") or {}
    if (any(summary.get(k) != search.get(k) for k in summary if k != "exact_attempts")
            or summary.get("exact_attempts") != len(science.get("exact_trials", []))):
        raise DomainError("binding_mismatch", "The search summary must describe the retained computed evidence.")


def baseline_result_checked(result):
    """Require matching fresh baseline facts, never a package-presence badge."""
    fresh = result.get("native_replay") or {}
    record = result.get("verification_record") or {}
    anchors = fresh.get("anchors") or {}
    if not (fresh.get("packet_profile") == NATIVE_PROFILE and fresh.get("operation") == "investigate"
            and fresh.get("integrity") == "passed" and fresh.get("expected_binding") == "matches"
            and fresh.get("replay") == result.get("replay") == "passed"
            and fresh.get("verification") == record.get("verification") == result.get("verification") == "valid"
            and record.get("expected_binding") == result.get("expected_binding") == "matches"
            and anchors.get("problem_digest") == result.get("problem_digest") == record.get("expected_problem_digest")
            and anchors.get("projection_digest") == result.get("scientific_problem_digest")
            and record.get("expected_scientific_problem_digest") == result.get("scientific_problem_digest")
            and record.get("observed_scientific_problem_digest") == result.get("scientific_problem_digest")):
        return False
    outcome = fresh.get("outcome") or {}
    if any(outcome.get(k) != result.get(k) for k in ("scientific_outcome", "reason_code")):
        return False
    candidates = result.get("candidates", [])
    checked = fresh.get("candidate_results", [])
    if not checked or len(checked) != len(candidates):
        return False
    summaries = []
    for candidate, observed in zip(candidates, checked, strict=True):
        if (candidate["id"] != observed["candidate_id"] or candidate["parameter_vector"] != observed["parameters"]
                or candidate["verification"] != observed["verification"]):
            return False
        summaries.append(CandidateResult.model_validate({key: observed[key] for key in CandidateResult.model_fields}).model_dump(mode="json"))
    return summaries == result.get("candidate_results")
