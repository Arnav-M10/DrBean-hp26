"""Scientific work only: frozen input in, bounded immutable evidence bytes out."""
import base64

from .checked import bind_artifacts, checked_design
from .errors import AdapterError
from .exact import artifact_digest, canonical_bytes, semantic_digest
from .identity import implementation_identity
from .models import digest_value, fields, normalize_design, normalize_problem, text_value
from .numerical import compare_grid
from .resource import ExecutionContext

BUNDLE_PROFILE = "groundwork.suggestion-bundle.v1"
WORKFLOW_FIELDS = {"plan_id", "approval_id", "operation_id", "execution_id"}


def create_suggestion(problem_payload: dict, design_payload: dict, *, expected_problem_digest: str,
                      expected_design_digest: str, workflow: dict, context: ExecutionContext | None = None,
                      artifacts: dict[str, bytes] | None = None) -> bytes:
    """Consume already-authorized scope; workflow IDs confer no authority here.

    The backend validates approval/revision/workspace state and supervises a hard
    wall clock. This function checks scientific binding, budgets and cancellation.
    Only the returned complete bytes may be atomically published as evidence.
    """
    problem = normalize_problem(problem_payload)
    design = normalize_design(design_payload, problem)
    if digest_value(expected_problem_digest, "expected_problem_digest") != problem.digest:
        raise AdapterError("wrong_specification_binding", "Expected problem identity does not match the supplied inputs.")
    if digest_value(expected_design_digest, "expected_design_digest") != design.digest:
        raise AdapterError("wrong_specification_binding", "Expected design identity does not match the supplied inputs.")
    flow = fields(workflow, WORKFLOW_FIELDS, "workflow")
    flow = {key: text_value(value, "workflow/" + key, identifier=True) for key, value in flow.items()}
    implementation = implementation_identity()
    context = context or ExecutionContext(design.limits.wall_seconds)
    if type(context) is not ExecutionContext:
        raise AdapterError("invalid_input", "Expected a bounded execution context.", ("context",))
    if artifacts is not None and type(artifacts) is not dict:
        raise AdapterError("invalid_input", "Supply artifact bytes in a digest-keyed mapping.", ("artifacts",))
    source = {} if artifacts is None else dict(artifacts)
    bind_artifacts(design, source)
    numerical = compare_grid(problem, design, context)
    checked = {"tier": "unavailable", "verification": "not_checked", "expected_binding": "not_supplied",
               "reason_code": "not_requested", "pair_digest": None,
               "construction_attempts": 0, "pair_verification_passes": 0}
    if design.requested_tier == "checked_pair_separation":
        try:
            result = checked_design(problem, design, source, context)
        except AdapterError as error:
            checked.update(verification="inconclusive" if error.code in ("cancelled", "resource_exhaustion", "construction_range", "missing_second_witness", "unavailable_horizon") else "failed",
                           expected_binding="mismatch" if error.code in ("candidate_mismatch", "wrong_specification_binding") else "not_supplied",
                           reason_code=error.code, error=error.to_dict())
            checked.update(getattr(error, "usage", {}))
        else:
            checked = result.report
            source[artifact_digest(result.pair_bytes)] = result.pair_bytes
    stop = context.stop_reason(design.limits.wall_seconds)
    # If stopped before publication, preserve numerical rows but publish no new
    # checked derivation. Source evidence remains immutable and can be replayed.
    if stop and checked.get("verification") == "valid":
        checked = {"tier": "unavailable", "verification": "inconclusive", "expected_binding": "matches",
                   "reason_code": stop, "pair_digest": None,
                   "construction_attempts": checked["construction_attempts"],
                   "pair_verification_passes": checked["pair_verification_passes"]}
        source = {} if artifacts is None else dict(artifacts)
    tier = checked["tier"] if checked["tier"] != "unavailable" else "numerical_guidance" if numerical["evaluated_count"] else "unavailable"
    report = {"schema_version": "groundwork.suggestion-report.v1", "problem_digest": problem.digest,
              "design_digest": design.digest, "scenario_id": design.scenario_id,
              "execution": "cancelled" if stop == "cancelled" else "interrupted" if stop else "completed",
              "tier": tier, "numerical": numerical, "checked": checked,
              "units": {"time": "h", "concentration": "mg/L", "score": "dimensionless"},
              "source_artifact_status": "content_consistent; scientific status requires fresh pair replay"}
    body = {"schema_version": BUNDLE_PROFILE, "problem": problem.to_payload(), "design": design.to_payload(),
            "workflow": flow, "report": report, "implementation": implementation,
            "artifacts": [{"digest": digest, "encoding": "base64", "content": base64.b64encode(content).decode("ascii")}
                          for digest, content in sorted(source.items())]}
    # Named TOP-LEVEL projection: exclude only suggestion_digest itself.
    body["suggestion_digest"] = semantic_digest("suggestion", body)
    encoded = canonical_bytes(body)
    if len(encoded) > design.limits.max_bundle_bytes:
        raise AdapterError("resource_exhaustion", "Complete suggestion and embedded evidence exceed the approved bundle limit.")
    return encoded
