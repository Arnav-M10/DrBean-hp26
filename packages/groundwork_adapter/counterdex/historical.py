"""Native evidence for fixed candidates against reviewed historical hard bounds.

This operation needs neither a future measurement nor a prospective design
approval. Certificate bounds are recomputed from the independently supplied
problem and vectors. Correct evidence can exclude a candidate: evidence validity
and historical compatibility therefore have separate report fields.
"""

from fractions import Fraction
import math

from .analytical import EXP_POLICY, concentration_interval
from .errors import AdapterError
from .exact import artifact_digest, canonical_bytes, rational_text, strict_json_loads
from .models import (MODEL, PARAMETERS, FixedCandidate, HistoricalProblem,
                     _check_problem_object, digest_value, fields, normalize_problem,
                     rational, text_value)
from .resource import ExecutionContext

HISTORICAL_PROFILE = "groundwork.historical-candidates.v1"
HISTORICAL_CHECK_PROFILE = "groundwork.historical-check.v1"
MAX_HISTORICAL_CERTIFICATE_BYTES = 2 * 1024 * 1024


def _context(context: ExecutionContext | None, wall_seconds: float) -> ExecutionContext:
    if (type(wall_seconds) not in (int, float) or not math.isfinite(wall_seconds)
            or not 0 < wall_seconds <= 120):
        raise AdapterError("invalid_input", "Historical wall limit must be positive and at most 120 seconds.", ("wall_seconds",))
    if context is None:
        context = ExecutionContext(wall_seconds)
    if type(context) is not ExecutionContext:
        raise AdapterError("invalid_input", "Expected a bounded execution context.", ("context",))
    _stop(context, wall_seconds)
    return context


def _stop(context: ExecutionContext, wall_seconds: float) -> None:
    reason = context.stop_reason(wall_seconds)
    if reason:
        raise AdapterError(reason, "Historical checking stopped before the next bounded step.")


def _byte_limit(max_bytes: int) -> None:
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_HISTORICAL_CERTIFICATE_BYTES:
        raise AdapterError("invalid_input", "Historical certificate byte limit exceeds the admitted cap.", ("max_bytes",))


def _inputs(problem: HistoricalProblem, candidates: tuple[FixedCandidate, ...] | list[FixedCandidate]
            ) -> tuple[HistoricalProblem, tuple[FixedCandidate, ...]]:
    _check_problem_object(problem)
    problem = normalize_problem(problem.to_payload())
    if type(candidates) not in (tuple, list) or not 1 <= len(candidates) <= 2:
        raise AdapterError("candidate_mismatch", "Historical checking requires one or two distinct fixed candidates.", ("candidates",))
    validated = []
    seen_ids, seen_vectors = set(), set()
    for index, candidate in enumerate(candidates):
        path = f"candidates/{index}"
        if (type(candidate) is not FixedCandidate or type(candidate.parameters) is not tuple
                or len(candidate.parameters) != 3 or any(type(v) is not Fraction for v in candidate.parameters)):
            raise AdapterError("invalid_input", "Expected a complete immutable exact candidate.", (path,))
        cid = text_value(candidate.id, path + "/id", identifier=True)
        if digest_value(candidate.problem_digest, path + "/problem_digest") != problem.digest:
            raise AdapterError("wrong_specification_binding", "Candidate belongs to another historical problem.", (path + "/problem_digest",))
        vector = tuple(rational(rational_text(v), path + "/parameters/" + key, positive=True)
                       for key, v in zip(PARAMETERS, candidate.parameters))
        if any(not lo <= value <= hi for value, (lo, hi) in zip(vector, problem.domain)):
            raise AdapterError("candidate_mismatch", "Candidate is outside the reviewed parameter domain.", (path + "/parameters",))
        if cid in seen_ids or vector in seen_vectors:
            raise AdapterError("candidate_mismatch", "Candidate IDs and fixed vectors must be distinct.", ("candidates",))
        if candidate.source_artifact_digest is not None:
            digest_value(candidate.source_artifact_digest, path + "/source_artifact_digest")
        seen_ids.add(cid)
        seen_vectors.add(vector)
        validated.append(candidate)
    return problem, tuple(validated)


def normalize_candidates(problem: HistoricalProblem, payload: list[dict]) -> tuple[FixedCandidate, ...]:
    """Admit complete fixed-candidate payloads without a prospective design."""
    if type(payload) is not list or not 1 <= len(payload) <= 2:
        raise AdapterError("candidate_mismatch", "Supply one or two complete historical candidates.", ("candidates",))
    candidates = []
    for index, member in enumerate(payload):
        path = f"candidates/{index}"
        c = fields(member, {"id", "problem_digest", "parameters", "source_artifact_digest"}, path)
        parameters = fields(c["parameters"], set(PARAMETERS), path + "/parameters")
        vector = tuple(rational(parameters[key], path + "/parameters/" + key, positive=True) for key in PARAMETERS)
        candidates.append(FixedCandidate(c["id"], c["problem_digest"], vector, c["source_artifact_digest"]))
    return _inputs(problem, candidates)[1]


def _times(problem: HistoricalProblem) -> tuple[Fraction, ...]:
    return tuple(sorted({row.time for row in problem.observations if row.included}))


def _bounds(problem: HistoricalProblem, candidate: FixedCandidate, context: ExecutionContext,
            wall_seconds: float) -> dict[Fraction, tuple[Fraction, Fraction]]:
    bounds = {}
    for time in _times(problem):
        _stop(context, wall_seconds)
        bounds[time] = concentration_interval(*candidate.parameters, time)
    _stop(context, wall_seconds)
    return bounds


def _report(problem: HistoricalProblem, candidate: FixedCandidate,
            bounds: dict[Fraction, tuple[Fraction, Fraction]]) -> dict:
    violations, unresolved, rows = [], [], []
    for observation in problem.observations:
        row = {"observation_id": observation.id, "time": rational_text(observation.time),
               "included": observation.included, "status": "excluded", "lower": None,
               "upper": None, "measurement": rational_text(observation.value),
               "allowance": rational_text(observation.allowance),
               "residual_lower": None, "residual_upper": None}
        if observation.included:
            lower, upper = bounds[observation.time]
            if upper < observation.value - observation.allowance or lower > observation.value + observation.allowance:
                status = "incompatible"
                violations.append(observation.id)
            elif lower < observation.value - observation.allowance or upper > observation.value + observation.allowance:
                status = "unresolved"
                unresolved.append(observation.id)
            else:
                status = "compatible"
            row.update(status=status, lower=rational_text(lower), upper=rational_text(upper),
                       residual_lower=rational_text(lower - observation.value),
                       residual_upper=rational_text(upper - observation.value))
        rows.append(row)
    verdict = "invalid" if violations else "inconclusive" if unresolved else "valid"
    outside = candidate.is_outside(problem)
    return {"candidate_id": candidate.id, "parameters": candidate.to_payload()["parameters"],
            "verification": verdict,
            "reason_code": "measurement_incompatible" if violations else "insufficient_enclosure" if unresolved else None,
            "violating_observation_ids": violations, "unresolved_observation_ids": unresolved,
            "outside_closed_claim": outside, "is_counterexample": verdict == "valid" and outside,
            "rows": rows}


def evaluate_historical_candidate(problem: HistoricalProblem, candidate: FixedCandidate,
                                  context: ExecutionContext | None = None, *,
                                  wall_seconds: float = 120) -> dict:
    """Check one exact frozen vector; numerical screening alone never calls this.

    The caller counts this as one candidate check against its search budget.
    Each distinct included time is computed once; every observation retains its
    own hard allowance, provenance in the bound problem, and inclusion status.
    """
    context = _context(context, wall_seconds)
    problem, candidates = _inputs(problem, (candidate,))
    return _report(problem, candidates[0], _bounds(problem, candidates[0], context, wall_seconds))


def construct_historical_certificate(problem: HistoricalProblem,
                                     candidates: tuple[FixedCandidate, ...] | list[FixedCandidate],
                                     context: ExecutionContext | None = None, *,
                                     wall_seconds: float = 120,
                                     max_bytes: int = MAX_HISTORICAL_CERTIFICATE_BYTES) -> bytes:
    """Serialize one or two vectors and their historical enclosures, not verdicts.

    Source artifact references on an expected candidate are not imported or
    trusted: this independent construction computes from the exact vector.
    """
    context = _context(context, wall_seconds)
    _byte_limit(max_bytes)
    problem, candidates = _inputs(problem, candidates)
    members = []
    for candidate in sorted(candidates, key=lambda candidate: candidate.id):
        bounds = _bounds(problem, candidate, context, wall_seconds)
        members.append({"id": candidate.id, "parameters": candidate.to_payload()["parameters"],
                        "samples": [{"time": rational_text(time), "lower": rational_text(lo), "upper": rational_text(hi)}
                                    for time, (lo, hi) in bounds.items()]})
    content = canonical_bytes({"schema_version": HISTORICAL_PROFILE, "proof_rule": EXP_POLICY,
                               "model": MODEL, "problem_digest": problem.digest, "candidates": members})
    if len(content) > max_bytes:
        raise AdapterError("resource_exhaustion", "Historical certificate exceeds the admitted byte limit.")
    _stop(context, wall_seconds)
    return content


def _certificate_fields(value: object, required: set[str], path: str) -> dict:
    try:
        return fields(value, required, path)
    except AdapterError as error:
        raise AdapterError("invalid_certificate", "Historical certificate has missing, unknown or malformed fields.", error.field_paths) from None


def verify_historical_certificate(content: bytes, problem: HistoricalProblem,
                                  expected_candidates: tuple[FixedCandidate, ...] | list[FixedCandidate],
                                  context: ExecutionContext | None = None, *,
                                  wall_seconds: float = 120,
                                  max_bytes: int = MAX_HISTORICAL_CERTIFICATE_BYTES) -> dict:
    """One fresh bounded verification pass, anchored to independent expectations.

    A return value means all stored enclosure statements recomputed exactly.
    Candidate incompatibility and insufficient enclosure remain scientific
    outcomes in ``candidate_results``, rather than corrupted-evidence errors.
    """
    context = _context(context, wall_seconds)
    _byte_limit(max_bytes)
    problem, candidates = _inputs(problem, expected_candidates)
    try:
        parsed = strict_json_loads(content, max_bytes=max_bytes)
        p = _certificate_fields(parsed, {"schema_version", "proof_rule", "model", "problem_digest", "candidates"}, "historical")
        if p["schema_version"] != HISTORICAL_PROFILE or p["proof_rule"] != EXP_POLICY or p["model"] != MODEL:
            raise AdapterError("unsupported_model", "Historical evidence requires the named analytic-template proof rule.", ("historical/schema_version",))
        if digest_value(p["problem_digest"], "historical/problem_digest") != problem.digest:
            raise AdapterError("wrong_specification_binding", "Historical evidence belongs to another problem.", ("historical/problem_digest",))
        members = p["candidates"]
        if type(members) is not list or len(members) != len(candidates):
            raise AdapterError("candidate_mismatch", "Historical evidence must contain exactly the selected candidates.", ("historical/candidates",))
        expected = {candidate.id: candidate for candidate in candidates}
        results, seen = [], set()
        times = _times(problem)
        for index, member in enumerate(members):
            _stop(context, wall_seconds)
            path = f"historical/candidates/{index}"
            m = _certificate_fields(member, {"id", "parameters", "samples"}, path)
            cid = text_value(m["id"], path + "/id", identifier=True)
            if cid not in expected or cid in seen:
                raise AdapterError("candidate_mismatch", "Historical candidate IDs do not match one-to-one.", (path + "/id",))
            candidate = expected[cid]
            parameters = _certificate_fields(m["parameters"], set(PARAMETERS), path + "/parameters")
            if tuple(rational(parameters[key], path + "/parameters/" + key) for key in PARAMETERS) != candidate.parameters:
                raise AdapterError("candidate_mismatch", "Historical vector differs from the selected candidate.", (path + "/parameters",))
            if type(m["samples"]) is not list or len(m["samples"]) != len(times):
                raise AdapterError("invalid_certificate", "Samples must cover exactly the included historical times.", (path + "/samples",))
            bounds = {}
            for sample_index, (sample, time) in enumerate(zip(m["samples"], times)):
                _stop(context, wall_seconds)
                sp = f"{path}/samples/{sample_index}"
                s = _certificate_fields(sample, {"time", "lower", "upper"}, sp)
                if rational(s["time"], sp + "/time") != time:
                    raise AdapterError("invalid_certificate", "Historical samples are missing or out of exact time order.", (sp + "/time",))
                claimed = rational(s["lower"], sp + "/lower"), rational(s["upper"], sp + "/upper")
                actual = concentration_interval(*candidate.parameters, time)
                if claimed != actual:
                    raise AdapterError("exact_check_failure", "Stored historical enclosure differs from fresh exact computation.", (sp,))
                bounds[time] = actual
            seen.add(cid)
            results.append(_report(problem, candidate, bounds))
        _stop(context, wall_seconds)
    except AdapterError as error:
        if error.code == "invalid_input":
            raise AdapterError("invalid_certificate", "Malformed exact historical certificate content.", error.field_paths) from None
        raise
    results.sort(key=lambda row: row["candidate_id"])
    compatibility = ("invalid" if any(row["verification"] == "invalid" for row in results) else
                     "inconclusive" if any(row["verification"] == "inconclusive" for row in results) else "valid")
    return {"schema_version": HISTORICAL_CHECK_PROFILE, "proof_rule": EXP_POLICY,
            "verification": "valid", "historical_compatibility": compatibility,
            "problem_digest": problem.digest, "certificate_digest": artifact_digest(content),
            "historical_horizon": rational_text(problem.horizon), "candidate_results": results}
