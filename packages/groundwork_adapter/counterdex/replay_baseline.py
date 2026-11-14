"""Offline historical replay; candidate discovery is never imported or rerun."""
import base64
import binascii
import re

from .errors import AdapterError
from .exact import artifact_digest, semantic_digest, strict_json_loads
from .historical import normalize_candidates, verify_historical_certificate
from .identity import implementation_identity
from .models import counter, digest_value, fields, normalize_problem, text_value
from .resource import ExecutionContext


def check_source(record: dict) -> None:
    fields(record, {"adapter_version", "python", "runtime", "canonicalization_profile", "source_manifest", "source_digest"}, "implementation")
    actual = implementation_identity()
    if any(record[key] != actual[key] for key in actual if key != "python"):
        raise AdapterError("source_version_mismatch", "Use the prepared installed source version for these evidence bytes.")
    if not isinstance(record["python"], str) or re.fullmatch(r"3\.11\.[0-9]{1,3}", record["python"]) is None:
        raise AdapterError("unsupported_runtime", "Evidence requires a qualified CPython 3.11 runtime.")


def decode_artifact(encoded: object, expected: object, maximum: int = 4 * 1024 * 1024) -> bytes:
    digest_value(expected, "artifact/sha256")
    if not isinstance(encoded, str) or len(encoded) > 4 * ((maximum + 2) // 3):
        raise AdapterError("resource_exhaustion", "Embedded native artifact exceeds the byte cap.")
    try:
        content = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error):
        raise AdapterError("invalid_input", "Native artifact encoding must be strict base64.") from None
    if len(content) > maximum:
        raise AdapterError("resource_exhaustion", "Native artifact exceeds the byte cap.")
    if artifact_digest(content) != expected:
        raise AdapterError("artifact_mismatch", "Raw native bytes differ from the expected hash.")
    return content


def replay_baseline(data: bytes, *, expected_problem_digest: str, expected_baseline_digest: str,
                    expected_scenario_id: str, context: ExecutionContext | None = None) -> dict:
    b = fields(strict_json_loads(data), {"schema_version", "operation", "problem", "scenario_id", "workflow",
        "implementation", "limits", "search", "exact_trials", "candidates", "report", "certificate", "baseline_digest"}, "baseline")
    if b["schema_version"] != "groundwork.baseline-bundle.v1" or b["operation"] not in ("bounded_discovery", "fixed_candidate_review"):
        raise AdapterError("unsupported_model", "Unsupported historical evidence profile.")
    digest = semantic_digest("report", {key: value for key, value in b.items() if key != "baseline_digest"})
    if digest_value(expected_baseline_digest, "expected_baseline_digest") != digest or b["baseline_digest"] != digest:
        raise AdapterError("artifact_mismatch", "Historical evidence differs from its external anchor.")
    problem = normalize_problem(b["problem"])
    if digest_value(expected_problem_digest, "expected_problem_digest") != problem.digest:
        raise AdapterError("wrong_specification_binding", "Historical evidence belongs to another problem.")
    if text_value(expected_scenario_id, "expected_scenario_id", identifier=True) != b["scenario_id"]:
        raise AdapterError("wrong_scenario_binding", "Historical evidence belongs to another scenario.")
    flow = fields(b["workflow"], {"plan_id", "approval_id", "operation_id", "execution_id"}, "workflow")
    for key, value in flow.items():
        text_value(value, "workflow/" + key, identifier=True)
    limits = fields(b["limits"], {"wall_seconds", "max_bundle_bytes"}, "limits")
    wall = counter(limits["wall_seconds"], "limits/wall_seconds", 1, 120)
    maximum = counter(limits["max_bundle_bytes"], "limits/max_bundle_bytes", 1, 4 * 1024 * 1024)
    if len(data) > maximum:
        raise AdapterError("resource_exhaustion", "Historical bundle exceeds its recorded byte limit.")
    if context is None:
        context = ExecutionContext(wall)
    if type(context) is not ExecutionContext:
        raise AdapterError("invalid_input", "Expected a bounded execution context.")
    check_source(b["implementation"])
    report = fields(b["report"], {"execution", "failure_reason", "outcome", "checked"}, "report")
    if report["execution"] not in ("completed", "cancelled", "interrupted"):
        raise AdapterError("invalid_input", "Invalid historical execution status.")
    failure = report["failure_reason"]
    if failure is not None:
        text_value(failure, "report/failure_reason", identifier=True)
    if report["execution"] != ("cancelled" if failure == "cancelled" else "interrupted" if failure else "completed"):
        raise AdapterError("recorded_result_mismatch", "Execution status differs from its failure reason.")
    review = b["operation"] == "fixed_candidate_review"
    if not isinstance(b["exact_trials"], list) or len(b["exact_trials"]) > 32:
        raise AdapterError("resource_exhaustion", "Historical candidate attempt count exceeds its cap.")
    for trial in b["exact_trials"]:
        fields(trial, {"candidate_id", "verification", "reason_code"}, "exact_trials")
        text_value(trial["candidate_id"], "exact_trials/candidate_id", identifier=True)
        if trial["verification"] not in ("valid", "invalid", "inconclusive"):
            raise AdapterError("invalid_input", "Unknown candidate trial state.")
    # Search numbers are retained producer diagnostics, never mathematical proof
    # or authenticated execution history. The checked claim is derived below.
    if review:
        if b["search"] is not None or b["exact_trials"]:
            raise AdapterError("invalid_input", "A fixed-vector review cannot assert discovery work.")
    elif not isinstance(b["search"], dict) or b["search"].get("problem_digest") != problem.digest:
        raise AdapterError("wrong_specification_binding", "Search diagnostics belong to another problem.")
    from .baseline import conclusion
    if b["certificate"] is None:
        if b["candidates"] or report["checked"] is not None or report["outcome"] != conclusion([], stopped=failure, review=review):
            raise AdapterError("recorded_result_mismatch", "No certificate can support a checked historical claim.")
        return {"replay": "unsupported", "integrity": "passed", "verification": "not_checked",
                "expected_binding": "matches", "reason_code": failure or "no_selected_evidence",
                "baseline_digest": digest, "candidate_results": [], "outcome": report["outcome"],
                "search_replayed": False}
    if failure is not None:
        raise AdapterError("recorded_result_mismatch", "Interrupted producer cannot publish a new checked claim.")
    certificate = fields(b["certificate"], {"sha256", "bytes_base64"}, "certificate")
    content = decode_artifact(certificate["bytes_base64"], certificate["sha256"], min(maximum, 2 * 1024 * 1024))
    candidates = normalize_candidates(problem, b["candidates"])
    checked = verify_historical_certificate(content, problem, candidates, context, wall_seconds=wall,
                                            max_bytes=min(maximum, 2 * 1024 * 1024))
    if checked != report["checked"]:
        raise AdapterError("recorded_result_mismatch", "Fresh historical computation differs from recorded results.")
    outcome = conclusion(checked["candidate_results"], review=review)
    if report["outcome"] != outcome:
        raise AdapterError("recorded_result_mismatch", "Stored outcome differs from fresh candidate checks.")
    return {"replay": "passed", "integrity": "passed", "verification": "valid", "expected_binding": "matches",
            "reason_code": "fresh_historical_check", "baseline_digest": digest,
            "candidate_results": checked["candidate_results"], "outcome": outcome,
            "historical_compatibility": checked["historical_compatibility"], "search_replayed": False}
