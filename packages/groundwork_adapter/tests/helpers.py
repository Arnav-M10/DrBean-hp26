"""New synthetic controls; no measurements from an actual experiment.

The broad historical hard allowances deliberately admit both chosen fixed
vectors. Values are elementary fixture choices, not claimed exact predictions.
"""

from counterdex.models import (
    CHECKED_POLICY, DESIGN_PROFILE, MODEL, NUMERICAL_POLICY, PROBLEM_PROFILE,
    normalize_design, normalize_problem,
)


def synthetic_problem_payload() -> dict:
    values = (("0/1", "0/1", "1/10"), ("1/1", "6/1", "3/1"), ("2/1", "6/1", "3/1"))
    return {
        "schema_version": PROBLEM_PROFILE,
        "model": MODEL,
        "model_revision": 1,
        "units": {"time": "h", "concentration": "mg/L", "rate": "1/h"},
        "initial_conditions": {"x": "1/1", "c": "0/1"},
        "time_origin": "elapsed hours from the fixed initial state",
        "dataset_kind": "hypothetical",
        "domain": {"A": ["1/1", "20/1"], "ke": ["1/20", "1/2"], "ka": ["1/1", "3/1"]},
        "claim": {"parameter": "ke", "interval": ["1/10", "1/5"]},
        "observations": [
            {"id": f"synthetic-{index}", "time": time, "value": value, "allowance": allowance,
             "included": True, "allowance_origin": "Constructed hard allowance for arithmetic controls",
             "origin": "hypothetical", "notes": "Synthetic fixture, not observed data",
             "provenance": "Independently chosen elementary values"}
            for index, (time, value, allowance) in enumerate(values)
        ],
        "notes": "Synthetic compatibility and finite-grid control",
        "provenance": "New fixture with broad hard bounds and two explicitly fixed vectors",
    }


def synthetic_design_payload(problem=None) -> dict:
    problem = problem or normalize_problem(synthetic_problem_payload())
    return {
        "schema_version": DESIGN_PROFILE,
        "problem_digest": problem.digest,
        "scenario_id": "fixture-synthetic-scenario",
        "candidates": [
            {"id": cid, "problem_digest": problem.digest,
             "parameters": {"A": "10/1", "ke": ke, "ka": "2/1"}, "source_artifact_digest": None}
            for cid, ke in (("endpoint-candidate", "1/10"), ("outside-candidate", "1/4"))
        ],
        "grid": [{"time": time, "feasible": True, "reason": "Fixture feasible time"} for time in ("6/1", "8/1")],
        "time_origin": problem.time_origin,
        "observable": "c",
        "future_allowance": "1/5",
        "allowance_origin": {"kind": "hypothetical", "description": "Constructed prospective hard allowance"},
        "requested_tier": "checked_pair_separation",
        "horizon_policy": {"allow_construction": True, "allow_extension": True, "maximum_horizon": "8/1"},
        "numerical_policy": NUMERICAL_POLICY,
        "checked_policy": CHECKED_POLICY,
        "limits": {"wall_seconds": 120, "max_times": 64, "max_constructions": 2,
                   "max_pair_verifications": 2, "max_bundle_bytes": 4 * 1024 * 1024,
                   "max_certificate_bytes": 2 * 1024 * 1024},
    }


def synthetic_inputs():
    problem = normalize_problem(synthetic_problem_payload())
    return problem, normalize_design(synthetic_design_payload(problem), problem)
