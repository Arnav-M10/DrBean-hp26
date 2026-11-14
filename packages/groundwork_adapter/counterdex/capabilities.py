"""Capability metadata scoped to this adapter and its qualified native runtime."""
import platform
import sys

from .analytical import (DYADIC_BITS, EXP_POLICY, MAX_ARGUMENT_BITS,
                         MAX_REDUCTIONS, TAYLOR_EVEN_DEGREE)
from .exact import CANONICALIZATION_PROFILE
from .models import CHECKED_POLICY, DESIGN_PROFILE, MODEL, NUMERICAL_POLICY, PROBLEM_PROFILE

VERSION = "0.1.0"


def capabilities() -> dict:
    """Return fresh metadata; availability is never a verdict on supplied data."""
    qualified_runtime = sys.implementation.name == "cpython" and sys.version_info[:2] == (3, 11)
    native_reason = None if qualified_runtime else "unsupported_runtime"
    return {
        "schema_version": "groundwork.capabilities.v1",
        "adapter": {"name": "counterdex", "version": VERSION, "runtime_dependencies": []},
        "canonicalization_profile": CANONICALIZATION_PROFILE,
        "scientific_profiles": {"problem": PROBLEM_PROFILE, "design": DESIGN_PROFILE,
                                "pair": "groundwork.analytic-pair.v1"},
        "model": {"id": MODEL, "revision": 1, "observable": "c",
                  "units": {"time": "h", "concentration": "mg/L", "rate": "1/h"}},
        "runtime": {"implementation": sys.implementation.name, "version": platform.python_version(),
                    "qualified": qualified_runtime, "qualified_versions": ["CPython 3.11"]},
        "capabilities": {
            "numerical_fixed_pair_guidance": {"supported": qualified_runtime, "reason_code": native_reason,
                "policy": NUMERICAL_POLICY, "scope": "Two fixed vectors on the supplied finite feasible grid; no compatibility proof."},
            "checked_fixed_pair_separation": {"supported": qualified_runtime, "reason_code": native_reason,
                "proof_rule": EXP_POLICY, "selection_policy": CHECKED_POLICY,
                "scope": "This analytic template only; two freshly compatible candidates and a strict positive exact margin."},
            "later_horizon_construction": {"supported": qualified_runtime, "reason_code": native_reason,
                "proof_rule": EXP_POLICY,
                "scope": "Fixed analytic-template candidates only, within supplied construction/extension scope and arithmetic caps."},
            "native_suggestion_replay": {"supported": qualified_runtime, "reason_code": native_reason,
                "pair_profile": "groundwork.analytic-pair.v1",
                "scope": "Complete supplied analytic-pair evidence and independently supplied expected identities."},
            "browser_suggestion_replay": {"supported": False, "reason_code": "browser_not_qualified",
                "scope": "No browser runtime, worker, assets or protocol has been qualified."},
        },
        "hard_caps": {"fixed_candidates": 2, "observables": 1, "historical_rows": 128,
                      "unique_times": 64, "wall_seconds": 120, "construction_attempts": 2,
                      "pair_verification_passes": 2, "certificate_bytes": 2 * 1024 * 1024,
                      "bundle_bytes": 4 * 1024 * 1024},
        "analytic_policy": {"proof_rule": EXP_POLICY, "input_rational_bits": MAX_ARGUMENT_BITS,
                            "maximum_exponential_argument": "1024/1", "maximum_range_reductions": MAX_REDUCTIONS,
                            "taylor_even_degree": TAYLOR_EVEN_DEGREE, "dyadic_fraction_bits": DYADIC_BITS,
                            "adaptive_refinement": False},
        "limitations": [
            "Historical compatibility requires full exact enclosure containment in every included row's hard allowance.",
            "A failed enclosure construction or an inconclusive check does not establish measurement incompatibility.",
            "Numerical scores are finite-grid diagnostics, not probabilities or checked discrimination.",
            "Positive separation concerns only the two selected candidates; a later datum may exclude either or both.",
            "No global identifiability, universal forecast, global optimum, model adequacy or instrument precision is established.",
            "Generic ODE models, interventions, resets, shared offsets, correlated errors and nonlinear observables are unsupported.",
            "Runtime capability metadata does not certify a particular artifact or qualify an external service.",
        ],
        "external_qualification": {"provider": "not_performed", "browser": "not_performed", "deployment": "not_performed"},
    }
