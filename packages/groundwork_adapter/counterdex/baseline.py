"""Bounded discovery followed by independent exact historical checking.

The floating-point producer proposes vectors; only the serialized historical
certificate's fresh verifier decides compatibility and strict counterexamples.
"""
import base64

from .errors import AdapterError
from .exact import artifact_digest, canonical_bytes, semantic_digest
from .historical import (construct_historical_certificate, evaluate_historical_candidate,
                         verify_historical_certificate)
from .identity import implementation_identity
from .models import counter, digest_value, fields, normalize_problem, text_value
from .resource import ExecutionContext

BASELINE_PROFILE = "groundwork.baseline-bundle.v1"


def conclusion(results: list[dict], *, stopped: str | None = None, review: bool = False) -> dict:
    """Derive the narrow claim from fresh individual results, never stored flags."""
    valid = [item for item in results if item["verification"] == "valid"]
    outside = [item for item in valid if item["is_counterexample"]]
    return {
        "scientific_outcome": "certified_counterexample" if outside else "inconclusive" if stopped or review else "no_counterexample_found",
        "reason_code": "compatible_outside_witness" if outside else stopped or (
            "selected_candidates_checked" if review else "bounded_search_no_outside_witness"),
        "pair_available": len(valid) == 2 and len(results) == 2,
        "compatible_candidate_ids": [item["candidate_id"] for item in valid],
        "counterexample_ids": [item["candidate_id"] for item in outside],
        "scope": "Selected exact vectors under the supplied model and hard bounds; no completeness or whole-model conclusion.",
    }


def create_baseline(problem_payload: dict, *, expected_problem_digest: str, scenario_id: str,
                    workflow: dict, settings: dict | None = None,
                    context: ExecutionContext | None = None, max_bundle_bytes: int = 4 * 1024 * 1024,
                    frozen_candidates: tuple | None = None) -> bytes:
    """Discover from this input, or check explicitly supplied fixed vectors.

    ``frozen_candidates`` is a separately labeled historical review operation;
    callers must bind its lineage. It never reports a new candidate search.
    """
    from .search import normalize_search_settings, search_candidates
    problem = normalize_problem(problem_payload)
    if digest_value(expected_problem_digest, "expected_problem_digest") != problem.digest:
        raise AdapterError("wrong_specification_binding", "Historical problem differs from the external anchor.")
    scenario = text_value(scenario_id, "scenario_id", identifier=True)
    flow = fields(workflow, {"plan_id", "approval_id", "operation_id", "execution_id"}, "workflow")
    flow = {key: text_value(value, "workflow/" + key, identifier=True) for key, value in flow.items()}
    maximum = counter(max_bundle_bytes, "max_bundle_bytes", 1, 4 * 1024 * 1024)
    policy = normalize_search_settings(settings) if settings is not None else normalize_search_settings({})
    if context is None:
        context = ExecutionContext(policy.wall_seconds)
    if type(context) is not ExecutionContext:
        raise AdapterError("invalid_input", "Expected a bounded execution context.")
    identity = implementation_identity()
    review = frozen_candidates is not None
    trials, selected, search = [], [], None
    if review:
        if type(frozen_candidates) is not tuple or not 1 <= len(frozen_candidates) <= 2:
            raise AdapterError("invalid_input", "Historical review requires one or two fixed candidates.")
        selected = list(frozen_candidates)
    else:
        produced = search_candidates(problem, settings=policy, context=context)
        search = produced.report
        compatible = []
        for candidate in produced.candidates:
            stop = context.stop_reason(policy.wall_seconds)
            if stop:
                break
            try:
                checked = evaluate_historical_candidate(problem, candidate, context, wall_seconds=policy.wall_seconds)
            except AdapterError as error:
                trials.append({"candidate_id": candidate.id, "verification": "inconclusive", "reason_code": error.code})
                if error.code in ("cancelled", "resource_exhaustion"):
                    break
                continue
            trials.append({"candidate_id": candidate.id, "verification": checked["verification"], "reason_code": checked["reason_code"]})
            if checked["verification"] == "valid":
                compatible.append(candidate)
            if any(c.is_outside(problem) for c in compatible) and any(not c.is_outside(problem) for c in compatible):
                break
        inside = next((c for c in compatible if not c.is_outside(problem)), None)
        outside = next((c for c in compatible if c.is_outside(problem)), None)
        selected = [c for c in (inside, outside) if c is not None]
        # A second actually checked vector is useful even when both lie on the
        # same side. Never create an artificial partner for a lone witness.
        if len(selected) == 1:
            selected += [c for c in compatible if c.id != selected[0].id][:1]
    certificate, checked, failure = None, None, context.stop_reason(policy.wall_seconds)
    if selected and not failure:
        try:
            certificate = construct_historical_certificate(problem, tuple(selected), context,
                wall_seconds=policy.wall_seconds, max_bytes=min(maximum, 2 * 1024 * 1024))
            checked = verify_historical_certificate(certificate, problem, tuple(selected), context,
                wall_seconds=policy.wall_seconds, max_bytes=min(maximum, 2 * 1024 * 1024))
        except AdapterError as error:
            failure = error.code
            certificate, checked = None, None
    stop = context.stop_reason(policy.wall_seconds)
    if stop:
        failure, certificate, checked = stop, None, None
    if checked is None:
        selected = []
    outcome = conclusion(checked["candidate_results"] if checked else [], stopped=failure, review=review)
    body = {"schema_version": BASELINE_PROFILE, "operation": "fixed_candidate_review" if review else "bounded_discovery",
        "problem": problem.to_payload(), "scenario_id": scenario, "workflow": flow,
        "implementation": identity, "limits": {"wall_seconds": policy.wall_seconds, "max_bundle_bytes": maximum},
        "search": search, "exact_trials": trials, "candidates": [c.to_payload() for c in selected],
        "report": {"execution": "cancelled" if stop == "cancelled" else "interrupted" if failure else "completed",
                   "failure_reason": failure, "outcome": outcome, "checked": checked},
        "certificate": None if certificate is None else {"sha256": artifact_digest(certificate),
                    "bytes_base64": base64.b64encode(certificate).decode("ascii")}}
    body["baseline_digest"] = semantic_digest("report", body)
    content = canonical_bytes(body)
    if len(content) > maximum:
        raise AdapterError("resource_exhaustion", "Complete historical evidence exceeds its approved byte cap.")
    return content
