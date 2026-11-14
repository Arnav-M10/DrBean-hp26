"""Scientific projections, not application routes, approvals, or transport DTOs.

Every public loader validates unknown fields before calculating an identity.
"""
from dataclasses import dataclass
from fractions import Fraction
import re
from typing import Any

from .errors import AdapterError
from .exact import canonical_bytes, parse_rational, rational_text, semantic_digest

MODEL = "two_rate_kinetics_v1"
PROBLEM_PROFILE = "groundwork.problem.v1"
DESIGN_PROFILE = "groundwork.design.v1"
NUMERICAL_POLICY = "pair-gap-over-allowance-12sig-half-even.v1"
CHECKED_POLICY = "positive-margin-descending-time-ids.v1"
PARAMETERS = ("A", "ke", "ka")


def fields(value: Any, required: set[str], path: str) -> dict:
    if not isinstance(value, dict):
        raise AdapterError("invalid_input", "Expected an object.", (path,))
    if set(value) != required:
        raise AdapterError("invalid_input", "Missing or unknown fields in this version.", (path,))
    return value


def text_value(value: Any, path: str, *, identifier: bool = False, empty: bool = False) -> str:
    limit = 128 if identifier else 4096
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        raise AdapterError("invalid_input", "Expected bounded text.", (path,))
    if any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise AdapterError("invalid_input", "Text contains an invalid Unicode scalar.", (path,))
    if identifier and any(not 32 <= ord(c) <= 126 for c in value):
        raise AdapterError("invalid_input", "This adapter profile requires printable ASCII identifiers.", (path,))
    return value


def boolean(value: Any, path: str) -> bool:
    if type(value) is not bool:
        raise AdapterError("invalid_input", "Expected a boolean.", (path,))
    return value


def counter(value: Any, path: str, lower: int, upper: int) -> int:
    if type(value) is not int or not lower <= value <= upper:
        raise AdapterError("invalid_input", "Structural integer is outside the admitted limit.", (path,))
    return value


def digest_value(value: Any, path: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        raise AdapterError("invalid_input", "Expected a lowercase SHA-256 digest.", (path,))
    return value


def rational(value: Any, path: str, *, positive: bool = False, nonnegative: bool = False) -> Fraction:
    result = parse_rational(value, path)
    if (positive and result <= 0) or (nonnegative and result < 0):
        raise AdapterError("invalid_input", "Exact value is outside the admitted range.", (path,))
    return result


def interval(value: Any, path: str, *, domain: bool = False) -> tuple[Fraction, Fraction]:
    if not isinstance(value, list) or len(value) != 2:
        raise AdapterError("invalid_input", "Expected two exact endpoints.", (path,))
    lo, hi = (rational(x, f"{path}/{i}", positive=domain) for i, x in enumerate(value))
    if lo > hi or (domain and lo == hi):
        raise AdapterError("invalid_input", "Interval endpoints are not ordered.", (path,))
    return lo, hi


@dataclass(frozen=True)
class Observation:
    id: str
    time: Fraction
    value: Fraction
    allowance: Fraction
    included: bool
    allowance_origin: str
    origin: str
    notes: str
    provenance: str

    def to_payload(self) -> dict:
        return {"id": self.id, "time": rational_text(self.time), "value": rational_text(self.value),
                "allowance": rational_text(self.allowance), "included": self.included,
                "allowance_origin": self.allowance_origin, "origin": self.origin,
                "notes": self.notes, "provenance": self.provenance}


@dataclass(frozen=True)
class HistoricalProblem:
    time_origin: str
    dataset_kind: str
    domain: tuple[tuple[Fraction, Fraction], ...]
    claim: tuple[Fraction, Fraction]
    observations: tuple[Observation, ...]
    notes: str
    provenance: str

    @property
    def horizon(self) -> Fraction:
        return max(row.time for row in self.observations if row.included)

    @property
    def digest(self) -> str:
        return semantic_digest("problem", self.to_payload())

    def to_payload(self) -> dict:
        return {"schema_version": PROBLEM_PROFILE, "model": MODEL, "model_revision": 1,
                "units": {"time": "h", "concentration": "mg/L", "rate": "1/h"},
                "initial_conditions": {"x": "1/1", "c": "0/1"},
                "time_origin": self.time_origin, "dataset_kind": self.dataset_kind,
                "domain": {key: [rational_text(x) for x in bounds]
                           for key, bounds in zip(PARAMETERS, self.domain)},
                "claim": {"parameter": "ke", "interval": [rational_text(x) for x in self.claim]},
                "observations": [row.to_payload() for row in self.observations],
                "notes": self.notes, "provenance": self.provenance}


def normalize_problem(payload: dict) -> HistoricalProblem:
    p = fields(payload, {"schema_version", "model", "model_revision", "units", "initial_conditions",
                         "time_origin", "dataset_kind", "domain", "claim", "observations", "notes", "provenance"}, "problem")
    if p["schema_version"] != PROBLEM_PROFILE:
        raise AdapterError("unsupported_model", "Only the declared Counterdex problem profile is supported.", ("problem/schema_version",))
    if p["model"] != MODEL or type(p["model_revision"]) is not int or p["model_revision"] != 1:
        raise AdapterError("unsupported_model", "Only the fixed two-rate kinetics template is supported.", ("problem/model",))
    if p["units"] != {"time": "h", "concentration": "mg/L", "rate": "1/h"}:
        raise AdapterError("unsupported_model", "The template requires hours, mg/L and inverse hours.", ("problem/units",))
    initial = fields(p["initial_conditions"], {"x", "c"}, "problem/initial_conditions")
    if rational(initial["x"], "problem/initial_conditions/x") != 1 or rational(initial["c"], "problem/initial_conditions/c") != 0:
        raise AdapterError("unsupported_model", "The template requires x(0)=1 and c(0)=0; resets and new doses need another model.", ("problem/initial_conditions",))
    if p["dataset_kind"] not in ("actual", "hypothetical"):
        raise AdapterError("invalid_input", "Declare actual or hypothetical data explicitly.", ("problem/dataset_kind",))
    box = fields(p["domain"], set(PARAMETERS), "problem/domain")
    domain = tuple(interval(box[key], f"problem/domain/{key}", domain=True) for key in PARAMETERS)
    if domain[1][1] >= domain[2][0]:
        raise AdapterError("unsupported_model", "The template requires upper(ke) < lower(ka).", ("problem/domain",))
    claim = fields(p["claim"], {"parameter", "interval"}, "problem/claim")
    if claim["parameter"] != "ke":
        raise AdapterError("unsupported_model", "Only a closed interval claim about ke is supported.", ("problem/claim/parameter",))
    claim_bounds = interval(claim["interval"], "problem/claim/interval")
    rows = p["observations"]
    if not isinstance(rows, list) or not 3 <= len(rows) <= 128:
        raise AdapterError("invalid_input", "Supply 3 to 128 historical observation rows.", ("problem/observations",))
    observations = []
    identifiers = set()
    for i, row in enumerate(rows):
        path = f"problem/observations/{i}"
        r = fields(row, {"id", "time", "value", "allowance", "included", "allowance_origin", "origin", "notes", "provenance"}, path)
        identity = text_value(r["id"], path + "/id", identifier=True)
        if identity in identifiers:
            raise AdapterError("invalid_input", "Observation IDs must be unique.", (path + "/id",))
        identifiers.add(identity)
        if r["origin"] not in ("actual", "transcription", "hypothetical") or (p["dataset_kind"] == "actual" and r["origin"] == "hypothetical"):
            raise AdapterError("unsupported_model", "Hypothetical rows require a separate hypothetical problem.", (path + "/origin",))
        observations.append(Observation(identity, rational(r["time"], path + "/time", nonnegative=True),
            rational(r["value"], path + "/value"), rational(r["allowance"], path + "/allowance", positive=True),
            boolean(r["included"], path + "/included"), text_value(r["allowance_origin"], path + "/allowance_origin"),
            r["origin"], text_value(r["notes"], path + "/notes", empty=True), text_value(r["provenance"], path + "/provenance", empty=True)))
    if len({row.time for row in observations if row.included}) < 3:
        raise AdapterError("invalid_input", "At least three distinct included historical times are required.", ("problem/observations",))
    result = HistoricalProblem(text_value(p["time_origin"], "problem/time_origin"), p["dataset_kind"], domain,
        claim_bounds, tuple(observations), text_value(p["notes"], "problem/notes", empty=True),
        text_value(p["provenance"], "problem/provenance", empty=True))
    canonical_bytes(result.to_payload())
    return result


@dataclass(frozen=True)
class FixedCandidate:
    id: str
    problem_digest: str
    parameters: tuple[Fraction, Fraction, Fraction]
    source_artifact_digest: str | None

    def to_payload(self) -> dict:
        return {"id": self.id, "problem_digest": self.problem_digest,
                "parameters": {key: rational_text(value) for key, value in zip(PARAMETERS, self.parameters)},
                "source_artifact_digest": self.source_artifact_digest}

    def is_outside(self, problem: HistoricalProblem) -> bool:
        """Exact location only; this says nothing about historical compatibility."""
        return self.parameters[1] < problem.claim[0] or self.parameters[1] > problem.claim[1]


@dataclass(frozen=True)
class GridTime:
    time: Fraction
    feasible: bool
    reason: str

    def to_payload(self) -> dict:
        return {"time": rational_text(self.time), "feasible": self.feasible, "reason": self.reason}


@dataclass(frozen=True)
class Limits:
    wall_seconds: int
    max_times: int
    max_constructions: int
    max_pair_verifications: int
    max_bundle_bytes: int
    max_certificate_bytes: int

    def to_payload(self) -> dict:
        return dict(self.__dict__)


@dataclass(frozen=True)
class DesignInput:
    problem_digest: str
    scenario_id: str
    candidates: tuple[FixedCandidate, FixedCandidate]
    grid: tuple[GridTime, ...]
    time_origin: str
    future_allowance: Fraction
    allowance_kind: str
    allowance_description: str
    requested_tier: str
    allow_construction: bool
    allow_extension: bool
    maximum_horizon: Fraction
    limits: Limits

    @property
    def digest(self) -> str:
        return semantic_digest("design-request", self.to_payload())

    def to_payload(self) -> dict:
        return {"schema_version": DESIGN_PROFILE, "problem_digest": self.problem_digest,
                "scenario_id": self.scenario_id, "candidates": [c.to_payload() for c in self.candidates],
                "grid": [row.to_payload() for row in self.grid], "time_origin": self.time_origin,
                "observable": "c", "future_allowance": rational_text(self.future_allowance),
                "allowance_origin": {"kind": self.allowance_kind, "description": self.allowance_description},
                "requested_tier": self.requested_tier,
                "horizon_policy": {"allow_construction": self.allow_construction, "allow_extension": self.allow_extension,
                                   "maximum_horizon": rational_text(self.maximum_horizon)},
                "numerical_policy": NUMERICAL_POLICY, "checked_policy": CHECKED_POLICY,
                "limits": self.limits.to_payload()}


def normalize_times(values: list[str]) -> tuple[str, ...]:
    """Preapproval helper only. The caller retains source spellings as provenance."""
    if not isinstance(values, list) or not 1 <= len(values) <= 64:
        raise AdapterError("invalid_input", "Preview 1 to 64 times before approval.", ("times",))
    return tuple(rational_text(t) for t in sorted({rational(v, "times", nonnegative=True) for v in values}))


def normalize_design(payload: dict, problem: HistoricalProblem) -> DesignInput:
    _check_problem_object(problem)
    problem = normalize_problem(problem.to_payload())
    p = fields(payload, {"schema_version", "problem_digest", "scenario_id", "candidates", "grid", "time_origin",
                         "observable", "future_allowance", "allowance_origin", "requested_tier", "horizon_policy",
                         "numerical_policy", "checked_policy", "limits"}, "design")
    if p["schema_version"] != DESIGN_PROFILE:
        raise AdapterError("invalid_input", "Unsupported scientific design profile.", ("design/schema_version",))
    expected = digest_value(p["problem_digest"], "design/problem_digest")
    if expected != problem.digest:
        raise AdapterError("wrong_specification_binding", "The design does not match the supplied historical problem.", ("design/problem_digest",))
    if p["observable"] != "c" or p["time_origin"] != problem.time_origin:
        raise AdapterError("unsupported_model", "Observable and elapsed-time origin must match the historical problem.", ("design/observable", "design/time_origin"))
    if p["numerical_policy"] != NUMERICAL_POLICY or p["checked_policy"] != CHECKED_POLICY:
        raise AdapterError("invalid_input", "Unsupported selection policy.", ("design/numerical_policy", "design/checked_policy"))
    if p["requested_tier"] not in ("numerical_guidance", "checked_pair_separation"):
        raise AdapterError("invalid_input", "Unsupported requested evidence tier.", ("design/requested_tier",))
    lp = fields(p["limits"], set(Limits.__dataclass_fields__), "design/limits")
    caps = {"wall_seconds": (1, 120), "max_times": (1, 64), "max_constructions": (0, 2),
            "max_pair_verifications": (0, 2), "max_bundle_bytes": (1, 4 * 1024 * 1024), "max_certificate_bytes": (1, 2 * 1024 * 1024)}
    limits = Limits(**{key: counter(lp[key], "design/limits/" + key, *bounds) for key, bounds in caps.items()})
    cp = p["candidates"]
    if not isinstance(cp, list) or len(cp) != 2:
        raise AdapterError("missing_second_witness", "Select exactly two fixed numerical candidates; neither is assumed checked.", ("design/candidates",))
    candidates = []
    for i, item in enumerate(cp):
        path = f"design/candidates/{i}"
        c = fields(item, {"id", "problem_digest", "parameters", "source_artifact_digest"}, path)
        if digest_value(c["problem_digest"], path + "/problem_digest") != expected:
            raise AdapterError("wrong_specification_binding", "Candidate belongs to another historical problem.", (path + "/problem_digest",))
        params = fields(c["parameters"], set(PARAMETERS), path + "/parameters")
        vector = tuple(rational(params[key], path + "/parameters/" + key, positive=True) for key in PARAMETERS)
        if any(not lo <= value <= hi for value, (lo, hi) in zip(vector, problem.domain)):
            raise AdapterError("candidate_mismatch", "Candidate is outside the reviewed parameter domain.", (path + "/parameters",))
        source = None if c["source_artifact_digest"] is None else digest_value(c["source_artifact_digest"], path + "/source_artifact_digest")
        candidates.append(FixedCandidate(text_value(c["id"], path + "/id", identifier=True), expected, vector, source))
    if candidates[0].id == candidates[1].id or candidates[0].parameters == candidates[1].parameters:
        raise AdapterError("candidate_mismatch", "Select two distinct candidate IDs and parameter vectors.", ("design/candidates",))
    gp = p["grid"]
    if not isinstance(gp, list) or not 1 <= len(gp) <= limits.max_times:
        raise AdapterError("invalid_input", "Grid exceeds the reviewed finite-time limit.", ("design/grid",))
    grid = []
    seen = set()
    for i, item in enumerate(gp):
        path = f"design/grid/{i}"
        g = fields(item, {"time", "feasible", "reason"}, path)
        t = rational(g["time"], path + "/time", nonnegative=True)
        if t in seen:
            raise AdapterError("invalid_input", "Deduplicate exact times in the preview before approving a grid.", (path + "/time",))
        seen.add(t)
        grid.append(GridTime(t, boolean(g["feasible"], path + "/feasible"), text_value(g["reason"], path + "/reason")))
    h = fields(p["horizon_policy"], {"allow_construction", "allow_extension", "maximum_horizon"}, "design/horizon_policy")
    construction = boolean(h["allow_construction"], "design/horizon_policy/allow_construction")
    extension = boolean(h["allow_extension"], "design/horizon_policy/allow_extension")
    horizon = rational(h["maximum_horizon"], "design/horizon_policy/maximum_horizon", nonnegative=True)
    if horizon < problem.horizon or (extension and not construction):
        raise AdapterError("unavailable_horizon", "Horizon policy must cover history; extension requires construction authority.", ("design/horizon_policy",))
    if p["requested_tier"] == "checked_pair_separation" and any(row.feasible and row.time > horizon for row in grid):
        raise AdapterError("unavailable_horizon", "A requested checked time exceeds the permitted horizon.", ("design/grid",))
    origin = fields(p["allowance_origin"], {"kind", "description"}, "design/allowance_origin")
    if origin["kind"] not in ("hypothetical", "reviewed_hard_bound"):
        raise AdapterError("invalid_input", "Declare a hypothetical or reviewed hard allowance; a standard deviation is not a hard bound.", ("design/allowance_origin/kind",))
    return DesignInput(expected, text_value(p["scenario_id"], "design/scenario_id", identifier=True), tuple(candidates),
        tuple(sorted(grid, key=lambda row: row.time)), problem.time_origin,
        rational(p["future_allowance"], "design/future_allowance", positive=True), origin["kind"],
        text_value(origin["description"], "design/allowance_origin/description"), p["requested_tier"],
        construction, extension, horizon, limits)


def _check_problem_object(problem: HistoricalProblem) -> None:
    if (type(problem) is not HistoricalProblem or type(problem.domain) is not tuple or len(problem.domain) != 3
        or any(type(bounds) is not tuple or len(bounds) != 2 for bounds in problem.domain)
        or type(problem.claim) is not tuple or len(problem.claim) != 2
        or type(problem.observations) is not tuple or any(type(row) is not Observation for row in problem.observations)):
        raise AdapterError("invalid_input", "Expected a complete immutable scientific problem.", ("problem",))


def revalidate_inputs(problem: HistoricalProblem, design: DesignInput) -> tuple[HistoricalProblem, DesignInput]:
    """Defend public in-process calls against unchecked dataclass constructors."""
    _check_problem_object(problem)
    if (type(design) is not DesignInput or type(design.candidates) is not tuple or len(design.candidates) != 2
        or any(type(c) is not FixedCandidate or type(c.parameters) is not tuple or len(c.parameters) != 3 for c in design.candidates)
        or type(design.grid) is not tuple or any(type(row) is not GridTime for row in design.grid)
        or type(design.limits) is not Limits):
        raise AdapterError("invalid_input", "Expected a complete immutable scientific design.", ("design",))
    p = normalize_problem(problem.to_payload())
    return p, normalize_design(design.to_payload(), p)
