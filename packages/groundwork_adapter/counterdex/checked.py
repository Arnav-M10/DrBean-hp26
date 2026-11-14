"""Fresh, bounded certificates for the explicit analytic kinetics template only.

Certificate fields are claims to recompute, never executable code or cached
verdicts. A valid pair means both fixed vectors fit the historical hard bounds.
The explicit solution provides continuation; only the listed points have stored
enclosures. No general ODE, universal-set or global-design claim is made.
"""
from dataclasses import dataclass
from fractions import Fraction

from .analytical import EXP_POLICY, concentration_interval
from .arithmetic import pair_margin
from .errors import AdapterError
from .exact import artifact_digest, canonical_bytes, rational_text, strict_json_loads
from .models import (MODEL, PARAMETERS, DesignInput, HistoricalProblem, digest_value,
                     fields, revalidate_inputs, rational, text_value)
from .resource import ExecutionContext

PAIR_PROFILE = "groundwork.analytic-pair.v1"


@dataclass(frozen=True)
class CheckedResult:
    report: dict
    pair_bytes: bytes | None


def _stop(context: ExecutionContext, wall_seconds: int) -> None:
    if type(context) is not ExecutionContext:
        raise AdapterError("invalid_input", "Expected a bounded execution context.", ("context",))
    reason = context.stop_reason(wall_seconds)
    if reason:
        raise AdapterError(reason, "Scientific work stopped before the next bounded step.")


def _inputs(problem: HistoricalProblem, design: DesignInput) -> tuple[HistoricalProblem, DesignInput]:
    return revalidate_inputs(problem, design)


def _times(problem: HistoricalProblem, design: DesignInput) -> tuple[Fraction, ...]:
    return tuple(sorted({r.time for r in problem.observations if r.included} |
                        {r.time for r in design.grid if r.feasible}))


def bind_artifacts(design: DesignInput, artifacts: dict[str, bytes]) -> None:
    """Bounded supplied content only. References never resolve paths or URLs."""
    if not isinstance(artifacts, dict) or len(artifacts) > 2:
        raise AdapterError("invalid_input", "Supply at most two candidate artifact payloads.", ("artifacts",))
    required = {c.source_artifact_digest for c in design.candidates if c.source_artifact_digest is not None}
    if set(artifacts) != required:
        raise AdapterError("incomplete_export", "The supplied artifact set must match the candidate references exactly.", ("artifacts",))
    total = 0
    for digest, content in artifacts.items():
        digest_value(digest, "artifacts/digest")
        if type(content) is not bytes or len(content) > design.limits.max_certificate_bytes:
            raise AdapterError("resource_exhaustion", "Artifact exceeds the certificate byte limit.", ("artifacts",))
        total += len(content)
        if artifact_digest(content) != digest:
            raise AdapterError("artifact_mismatch", "Artifact bytes do not match their recorded digest.", ("artifacts",))
    if total > design.limits.max_bundle_bytes:
        raise AdapterError("resource_exhaustion", "Combined artifact bytes exceed the bundle limit.", ("artifacts",))


def construct_pair(problem: HistoricalProblem, design: DesignInput, context: ExecutionContext,
                   *, _usage: dict | None = None) -> bytes:
    """Exactly one fixed-settings enclosure construction for each selected vector."""
    problem, design = _inputs(problem, design)
    if design.requested_tier != "checked_pair_separation":
        raise AdapterError("invalid_input", "A numerical request does not include exact construction scope.")
    if not design.allow_construction or design.limits.max_constructions < 2:
        raise AdapterError("missing_second_witness", "Two fixed-vector constructions were not included in the supplied scope.")
    if design.maximum_horizon > problem.horizon and not design.allow_extension:
        raise AdapterError("unavailable_horizon", "Later-horizon construction is outside the supplied scope.")
    if any(t > design.maximum_horizon for t in _times(problem, design)):
        raise AdapterError("unavailable_horizon", "The permitted horizon does not cover all requested points.")
    members = []
    for candidate in design.candidates:
        _stop(context, design.limits.wall_seconds)
        if _usage is not None:
            _usage["construction_attempts"] += 1
        samples = []
        for t in _times(problem, design):
            _stop(context, design.limits.wall_seconds)
            lower, upper = concentration_interval(*candidate.parameters, t)
            samples.append({"time": rational_text(t), "lower": rational_text(lower), "upper": rational_text(upper)})
        members.append({"id": candidate.id, "parameters": candidate.to_payload()["parameters"], "samples": samples})
    content = canonical_bytes({"schema_version": PAIR_PROFILE, "proof_rule": EXP_POLICY, "model": MODEL,
        "problem_digest": problem.digest, "horizon": rational_text(design.maximum_horizon), "candidates": members})
    if len(content) > min(design.limits.max_certificate_bytes, design.limits.max_bundle_bytes):
        raise AdapterError("resource_exhaustion", "Constructed pair exceeds the certificate byte limit.")
    return content


def verify_pair(content: bytes, problem: HistoricalProblem, design: DesignInput,
                context: ExecutionContext | None = None) -> dict:
    """Recompute from stored bytes and independently supplied expected inputs.

    This is one full pair pass. Its exact enclosures directly feed the margin
    derivation; no stored verdict, badge, polynomial, scale, or result is trusted.
    """
    problem, design = _inputs(problem, design)
    context = context or ExecutionContext(design.limits.wall_seconds)
    _stop(context, design.limits.wall_seconds)
    p = fields(strict_json_loads(content, max_bytes=design.limits.max_certificate_bytes),
        {"schema_version", "proof_rule", "model", "problem_digest", "horizon", "candidates"}, "pair")
    if p["schema_version"] != PAIR_PROFILE or p["proof_rule"] != EXP_POLICY or p["model"] != MODEL:
        raise AdapterError("unsupported_model", "This checker accepts only its named analytic-template proof rule.", ("pair/schema_version",))
    if digest_value(p["problem_digest"], "pair/problem_digest") != problem.digest:
        raise AdapterError("wrong_specification_binding", "Pair evidence is for a different historical problem.", ("pair/problem_digest",))
    horizon = rational(p["horizon"], "pair/horizon", nonnegative=True)
    if horizon < max(_times(problem, design)) or horizon > design.maximum_horizon:
        raise AdapterError("unavailable_horizon", "Pair horizon does not cover the requested points within the permitted horizon.", ("pair/horizon",))
    members = p["candidates"]
    if not isinstance(members, list) or len(members) != 2:
        raise AdapterError("missing_second_witness", "Pair evidence must contain two distinct fixed candidates.", ("pair/candidates",))
    expected = {c.id: c for c in design.candidates}
    all_bounds = {}
    compatibility = []
    for index, member in enumerate(members):
        _stop(context, design.limits.wall_seconds)
        path = f"pair/candidates/{index}"
        m = fields(member, {"id", "parameters", "samples"}, path)
        cid = text_value(m["id"], path + "/id", identifier=True)
        if cid not in expected or cid in all_bounds:
            raise AdapterError("candidate_mismatch", "Pair candidate IDs do not match one-to-one.", (path + "/id",))
        candidate = expected[cid]
        params = fields(m["parameters"], set(PARAMETERS), path + "/parameters")
        if tuple(rational(params[key], path + "/parameters/" + key) for key in PARAMETERS) != candidate.parameters:
            raise AdapterError("candidate_mismatch", "Pair parameter vector differs from the selected candidate.", (path + "/parameters",))
        if not isinstance(m["samples"], list) or len(m["samples"]) != len(_times(problem, design)):
            raise AdapterError("invalid_certificate", "Pair samples must cover exactly the reviewed historical and feasible times.", (path + "/samples",))
        bounds = {}
        for index, (sample, time) in enumerate(zip(m["samples"], _times(problem, design))):
            _stop(context, design.limits.wall_seconds)
            sp = f"{path}/samples/{index}"
            s = fields(sample, {"time", "lower", "upper"}, sp)
            if rational(s["time"], sp + "/time") != time:
                raise AdapterError("invalid_certificate", "Pair samples are missing or out of exact time order.", (sp + "/time",))
            claimed = rational(s["lower"], sp + "/lower"), rational(s["upper"], sp + "/upper")
            actual = concentration_interval(*candidate.parameters, time)
            if claimed != actual:
                raise AdapterError("exact_check_failure", "Stored enclosure differs from fresh exact computation.", (sp,))
            bounds[time] = actual
        all_bounds[cid] = bounds
        violations, unresolved = [], []
        for row in problem.observations:
            if not row.included:
                continue
            lower, upper = bounds[row.time]
            if upper < row.value - row.allowance or lower > row.value + row.allowance:
                violations.append(row.id)
            elif lower < row.value - row.allowance or upper > row.value + row.allowance:
                unresolved.append(row.id)
        verdict = "invalid" if violations else "inconclusive" if unresolved else "valid"
        compatibility.append({"candidate_id": cid, "verification": verdict,
            "reason_code": "measurement_incompatible" if violations else "insufficient_enclosure" if unresolved else None,
            "violating_observation_ids": violations, "unresolved_observation_ids": unresolved,
            "outside_closed_claim": candidate.is_outside(problem),
            "is_counterexample": verdict == "valid" and candidate.is_outside(problem)})
    # Evidence is attached to IDs; display permutation cannot swap its errors.
    compatibility.sort(key=lambda row: row["candidate_id"])
    valid = all(row["verification"] == "valid" for row in compatibility)
    rows = []
    for point in design.grid:
        _stop(context, design.limits.wall_seconds)
        row = {"time": rational_text(point.time), "status": "unavailable", "reason_code": None,
               "centers": None, "errors": None, "bands": None, "gap": None, "raw_score": None,
               "margin": None, "separated": False}
        if not point.feasible:
            row.update(status="skipped", reason_code="not_feasible")
        elif not valid:
            row["reason_code"] = "historical_compatibility_unresolved"
        else:
            intervals = [all_bounds[c.id][point.time] for c in design.candidates]
            centers = [(lo + hi) / 2 for lo, hi in intervals]
            errors = [(hi - lo) / 2 for lo, hi in intervals]
            ar = pair_margin(centers[0], centers[1], errors[0], errors[1], design.future_allowance)
            row.update(status="evaluated", centers={c.id: rational_text(v) for c, v in zip(design.candidates, centers)},
                errors={c.id: rational_text(v) for c, v in zip(design.candidates, errors)},
                bands={c.id: [rational_text(centers[i] - errors[i] - design.future_allowance),
                              rational_text(centers[i] + errors[i] + design.future_allowance)]
                       for i, c in enumerate(design.candidates)},
                gap=rational_text(ar.gap), raw_score=rational_text(ar.raw_score), margin=rational_text(ar.margin), separated=ar.separated)
        rows.append(row)
    ranked = sorted((r for r in rows if r["status"] == "evaluated"),
                    key=lambda r: (not r["separated"], -Fraction(r["margin"]), Fraction(r["time"])))
    selected = next((r["time"] for r in ranked if r["separated"]), None)
    return {"schema_version": "groundwork.checked-grid.v1", "proof_rule": EXP_POLICY,
        "verification": "valid" if valid else "invalid" if any(c["verification"] == "invalid" for c in compatibility) else "inconclusive",
        "expected_binding": "matches", "pair_digest": artifact_digest(content),
        "common_checked_horizon": rational_text(horizon) if valid else None,
        "candidate_results": compatibility, "rows": rows, "ranked_times": [r["time"] for r in ranked],
        "selected_time": selected,
        "tier": "checked_pair_separation" if selected is not None else "no_separation_established" if valid else "unavailable",
        "reason_code": None if selected is not None else "no_separating_time" if valid else "historical_compatibility_unresolved"}


def checked_design(problem: HistoricalProblem, design: DesignInput, artifacts: dict[str, bytes],
                   context: ExecutionContext | None = None) -> CheckedResult:
    problem, design = _inputs(problem, design)
    if design.requested_tier != "checked_pair_separation":
        raise AdapterError("invalid_input", "A numerical request does not include checked-design scope.")
    context = context or ExecutionContext(design.limits.wall_seconds)
    bind_artifacts(design, artifacts)
    if design.limits.max_pair_verifications < 1:
        raise AdapterError("resource_exhaustion", "No pair verification pass is included in the supplied scope.")
    _stop(context, design.limits.wall_seconds)
    digests = {c.source_artifact_digest for c in design.candidates}
    if digests != {None} and (None in digests or len(digests) != 1):
        raise AdapterError("missing_second_witness", "Reuse requires both selected members of one matching analytic pair artifact.")
    usage = {"construction_attempts": 0, "pair_verification_passes": 0}
    try:
        if None not in digests:
            content = artifacts[next(iter(digests))]
        else:
            content = construct_pair(problem, design, context, _usage=usage)
        _stop(context, design.limits.wall_seconds)
        usage["pair_verification_passes"] = 1
        # The published derivation always comes from parsed serialized evidence.
        report = verify_pair(content, problem, design, context)
    except AdapterError as error:
        error.usage = usage
        raise
    report.update(usage)
    return CheckedResult(report, content)
