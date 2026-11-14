"""Offline exact replay. This module never imports the numerical producer."""
import base64
import binascii
import re

from .checked import bind_artifacts, verify_pair
from .errors import AdapterError
from .exact import artifact_digest, semantic_digest, strict_json_loads
from .identity import implementation_identity
from .models import boolean, counter, digest_value, fields, normalize_design, normalize_problem, text_value
from .resource import ExecutionContext


def replay_bundle(data: bytes, *, expected_problem_digest: str, expected_suggestion_digest: str,
                  context: ExecutionContext | None = None) -> dict:
    """Replay against external trust anchors, never a self-asserted badge.

    A numeric-only bundle has integrity but no exact scientific replay. Stored
    diagnostics stay recorded diagnostics; this does not rerun transcendental
    floating-point work or claim cross-platform numerical bit equality.
    """
    b = fields(strict_json_loads(data), {"schema_version", "problem", "design", "workflow", "report",
                                       "implementation", "artifacts", "suggestion_digest"}, "bundle")
    if b["schema_version"] != "groundwork.suggestion-bundle.v1":
        raise AdapterError("unsupported_model", "Unsupported suggestion bundle profile.")
    body = {key: value for key, value in b.items() if key != "suggestion_digest"}
    digest = semantic_digest("suggestion", body)
    if (digest_value(expected_suggestion_digest, "expected_suggestion_digest") != digest
        or digest_value(b["suggestion_digest"], "suggestion_digest") != digest):
        raise AdapterError("artifact_mismatch", "Suggestion identity differs from its expected trust anchor.")
    problem = normalize_problem(b["problem"])
    design = normalize_design(b["design"], problem)
    if digest_value(expected_problem_digest, "expected_problem_digest") != problem.digest:
        raise AdapterError("wrong_specification_binding", "Suggestion belongs to another historical problem.")
    if len(data) > design.limits.max_bundle_bytes:
        raise AdapterError("resource_exhaustion", "Complete suggestion exceeds the reviewed bundle limit.")
    flow = fields(b["workflow"], {"plan_id", "approval_id", "operation_id", "execution_id"}, "workflow")
    for key, value in flow.items():
        text_value(value, "workflow/" + key, identifier=True)
    report = fields(b["report"], {"schema_version", "problem_digest", "design_digest", "scenario_id", "execution",
                                   "tier", "numerical", "checked", "units", "source_artifact_status"}, "report")
    if (report["schema_version"] != "groundwork.suggestion-report.v1" or report["problem_digest"] != problem.digest
        or report["design_digest"] != design.digest or report["scenario_id"] != design.scenario_id):
        raise AdapterError("wrong_specification_binding", "Recorded report identities differ from its problem/design.")
    if not isinstance(report["checked"], dict):
        raise AdapterError("invalid_input", "Expected recorded checked-result fields.", ("report/checked",))
    counters = report["checked"]
    counter(counters.get("construction_attempts"), "report/checked/construction_attempts", 0, design.limits.max_constructions)
    counter(counters.get("pair_verification_passes"), "report/checked/pair_verification_passes", 0, design.limits.max_pair_verifications)
    implementation = fields(b["implementation"], {"adapter_version", "python", "runtime", "canonicalization_profile", "source_manifest", "source_digest"}, "implementation")
    actual = implementation_identity()
    if any(implementation[key] != actual[key] for key in ("adapter_version", "runtime", "canonicalization_profile", "source_manifest", "source_digest")):
        raise AdapterError("unsupported_runtime", "Install the prepared adapter source version named by this record; artifacts cannot select a runtime.")
    if not isinstance(implementation["python"], str) or re.fullmatch(r"3\.11\.[0-9]{1,3}", implementation["python"]) is None:
        raise AdapterError("unsupported_runtime", "Recorded runtime must be a qualified CPython 3.11 patch version.")
    if report["units"] != {"time": "h", "concentration": "mg/L", "score": "dimensionless"}:
        raise AdapterError("invalid_input", "Recorded units do not match the admitted template.")
    if report["execution"] not in ("completed", "cancelled", "interrupted"):
        raise AdapterError("invalid_input", "Invalid recorded execution status.")
    if report["source_artifact_status"] != "content_consistent; scientific status requires fresh pair replay":
        raise AdapterError("invalid_input", "Invalid recorded evidence scope.")
    from .replay_numeric import validate_numerical_record
    validate_numerical_record(report["numerical"], design)
    if report["numerical"]["execution"] != "completed" and report["execution"] != report["numerical"]["execution"]:
        raise AdapterError("recorded_result_mismatch", "The outer execution cannot undo a recorded numerical stop.")
    items = b["artifacts"]
    if not isinstance(items, list) or len(items) > 3:
        raise AdapterError("resource_exhaustion", "Suggestion contains too many evidence artifacts.")
    artifacts = {}
    total = 0
    for index, item in enumerate(items):
        a = fields(item, {"digest", "encoding", "content"}, f"artifacts/{index}")
        key = digest_value(a["digest"], f"artifacts/{index}/digest")
        if key in artifacts or a["encoding"] != "base64" or not isinstance(a["content"], str):
            raise AdapterError("invalid_input", "Invalid or duplicate embedded evidence entry.")
        if len(a["content"]) > 4 * ((design.limits.max_certificate_bytes + 2) // 3):
            raise AdapterError("resource_exhaustion", "Embedded artifact exceeds the certificate limit.")
        try:
            content = base64.b64decode(a["content"], validate=True)
        except (binascii.Error, ValueError):
            raise AdapterError("invalid_input", "Evidence content is not valid base64.") from None
        if len(content) > design.limits.max_certificate_bytes:
            raise AdapterError("resource_exhaustion", "Embedded artifact exceeds the certificate limit.")
        if artifact_digest(content) != key:
            raise AdapterError("artifact_mismatch", "Embedded evidence bytes differ from their digest.")
        total += len(content)
        artifacts[key] = content
    if total > design.limits.max_bundle_bytes:
        raise AdapterError("resource_exhaustion", "Aggregate evidence bytes exceed the approved limit.")
    references = {c.source_artifact_digest for c in design.candidates if c.source_artifact_digest is not None}
    bind_artifacts(design, {key: value for key, value in artifacts.items() if key in references})
    pair_digest = report["checked"].get("pair_digest")
    if pair_digest is None:
        if set(artifacts) != references:
            raise AdapterError("invalid_input", "Bundle contains unexpected unbound evidence.")
        fields(report["checked"], {"tier", "verification", "expected_binding", "reason_code", "pair_digest",
                                   "construction_attempts", "pair_verification_passes"} | ({"error"} if "error" in report["checked"] else set()), "report/checked")
        if (report["checked"]["tier"] != "unavailable" or report["checked"]["verification"] not in ("not_checked", "inconclusive", "failed")
            or report["tier"] != ("numerical_guidance" if report["numerical"]["evaluated_count"] else "unavailable")):
            raise AdapterError("recorded_result_mismatch", "A record without pair evidence cannot carry a checked verdict.")
        if report["checked"]["expected_binding"] not in ("matches", "mismatch", "not_supplied"):
            raise AdapterError("invalid_input", "Unknown recorded binding status.")
        text_value(report["checked"]["reason_code"], "report/checked/reason_code", identifier=True)
        if "error" in report["checked"]:
            error = fields(report["checked"]["error"], {"code", "message", "field_paths", "retryable"}, "report/checked/error")
            if error["code"] != report["checked"]["reason_code"]:
                raise AdapterError("recorded_result_mismatch", "Error reason does not match the recorded outcome.")
            text_value(error["message"], "report/checked/error/message")
            boolean(error["retryable"], "report/checked/error/retryable")
            if not isinstance(error["field_paths"], list) or len(error["field_paths"]) > 16:
                raise AdapterError("invalid_input", "Invalid error field paths.")
            for path in error["field_paths"]:
                text_value(path, "report/checked/error/field_paths", empty=True)
        return {"replay": "unsupported", "scope": "numerical_record_integrity", "integrity": "passed",
                "verification": "not_checked", "expected_binding": "matches",
                "reason_code": "incomplete_export" if design.requested_tier == "checked_pair_separation" else "numerical_only",
                "suggestion_digest": digest, "message": "This record has no complete analytic pair evidence for fresh scientific replay."}
    digest_value(pair_digest, "report/checked/pair_digest")
    if design.requested_tier != "checked_pair_separation":
        raise AdapterError("recorded_result_mismatch", "Numerical-only scope cannot publish a checked producer record.")
    if pair_digest not in artifacts:
        raise AdapterError("incomplete_export", "Pair evidence is missing; exact replay is unavailable.")
    if set(artifacts) != references | {pair_digest}:
        raise AdapterError("invalid_input", "Bundle contains unexpected unbound evidence.")
    if references:
        if any(candidate.source_artifact_digest != pair_digest for candidate in design.candidates):
            raise AdapterError("candidate_mismatch", "Reused evidence must associate both selected candidates with the same checked pair.")
    elif not design.allow_construction or (design.maximum_horizon > problem.horizon and not design.allow_extension):
        raise AdapterError("recorded_result_mismatch", "Recorded new pair construction exceeds its declared scientific scope.")
    if counters["pair_verification_passes"] != 1 or counters["construction_attempts"] != (0 if references else 2):
        raise AdapterError("recorded_result_mismatch", "Recorded work counts differ from this fixed producer profile.")
    context = context or ExecutionContext(design.limits.wall_seconds)
    fresh = verify_pair(artifacts[pair_digest], problem, design, context)
    recorded = {key: value for key, value in report["checked"].items()
                if key not in ("construction_attempts", "pair_verification_passes")}
    expected_tier = fresh["tier"] if fresh["tier"] != "unavailable" else "numerical_guidance" if report["numerical"]["evaluated_count"] else "unavailable"
    matches = recorded == fresh and report["tier"] == expected_tier and report["execution"] == "completed"
    # A freshly invalid/inconclusive pair is retained as such, never a pass.
    return {"replay": "passed" if fresh["verification"] == "valid" and matches else "failed",
            "scope": "analytic_fixed_pair", "integrity": "passed", "verification": fresh["verification"],
            "expected_binding": "matches", "recorded_result_matches": matches,
            "reason_code": fresh["reason_code"] if matches else "recorded_result_mismatch", "suggestion_digest": digest,
            "fresh_checked": fresh}
