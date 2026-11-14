"""Reproducible scientific projection of authoritative DB-SC-1 application input.

The API owns application DTO validation and approval. This module does not
provide competing transport models. It binds the API's complete normalized
bodies, checks the narrower scientific admission rules, and records the exact
projection policy so an offline verifier can repeat the transformation.
"""

from __future__ import annotations

from copy import deepcopy
import re

from .errors import AdapterError
from .exact import canonical_bytes, parse_rational, rational_text, semantic_digest
from .models import (CHECKED_POLICY, DESIGN_PROFILE, MODEL, NUMERICAL_POLICY,
                     PROBLEM_PROFILE, digest_value, normalize_design,
                     normalize_problem)

MAPPING_POLICY = "DB-SC-1-to-groundwork-v1"
DESIGN_MAPPING_POLICY = "DB-SC-1-design-to-groundwork-v2"
APPLICATION_BINDING = "counterdex.application-binding.v1"
DESIGN_BINDING = "counterdex.application-design-binding.v1"
APPLICATION_BODY_CAP = 1024 * 1024
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")


def _error(code: str, message: str, path: str) -> AdapterError:
    return AdapterError(code, message, (path,))


def _object(value: object, path: str) -> dict:
    if type(value) is not dict:
        raise _error("invalid_input", "Expected an application object.", path)
    return value


def _get(value: dict, key: str, path: str) -> object:
    if key not in value:
        raise _error("invalid_input", "The normalized application field is required.", path + "/" + key)
    return value[key]


def _identifier(value: object, path: str) -> str:
    if type(value) is not str or _IDENTIFIER.fullmatch(value) is None:
        raise _error("invalid_input", "Expected an application identifier.", path)
    return value


def _exact(value: object, path: str, *, positive: bool = False, nonnegative: bool = False) -> str:
    fraction = parse_rational(value, path)
    if rational_text(fraction) != value:
        raise _error("invalid_input", "Supply the application's normalized rational spelling.", path)
    if (positive and fraction <= 0) or (nonnegative and fraction < 0):
        raise _error("invalid_input", "The exact application value is outside its admitted range.", path)
    return value


def _record(value: object, kind: str) -> dict:
    record = _object(value, kind)
    if record.get("kind", kind) != kind:
        raise _error("wrong_specification_binding", "The application record has a different kind.", kind)
    identifier = _identifier(_get(record, "id", kind), kind + "/id")
    digest = digest_value(_get(record, "digest", kind), kind + "/digest")
    body = _object(_get(record, "body", kind), kind + "/body")
    if len(canonical_bytes(body)) > APPLICATION_BODY_CAP:
        raise _error("resource_exhaustion", "Application body exceeds the admitted byte cap.", kind + "/body")
    if body.get("schema_version") != "DB-SC-1":
        raise _error("unsupported_model", "Only normalized DB-SC-1 application bodies are supported.", kind + "/body/schema_version")
    if semantic_digest(kind, body) != digest:
        raise _error("wrong_specification_binding", "Application body differs from its expected record digest.", kind + "/digest")
    return deepcopy({"id": identifier, "digest": digest, "body": body})


def project_application(problem_record: dict, dataset_record: dict) -> dict:
    """Bind full application bodies and return the admitted scientific payload.

    Record envelopes may include server bookkeeping. The immutable binding
    retains id/digest/body; authorization and workspace membership remain the
    server's responsibility. No metadata is squeezed into scientific text caps.
    """
    problem = _record(problem_record, "problem")
    dataset = _record(dataset_record, "dataset")
    p, d = problem["body"], dataset["body"]
    if p.get("dataset_id") != dataset["id"] or p.get("dataset_digest") != dataset["digest"]:
        raise _error("wrong_specification_binding", "Problem must bind the supplied dataset identity.", "problem/body/dataset_digest")
    supported = {"model": "two_rate_concentration", "initial_concentration": "0/1",
                 "observable": "concentration", "time_unit": "h",
                 "concentration_unit": "mg/L", "rate_unit": "1/h"}
    for key, expected in supported.items():
        if p.get(key) != expected:
            raise _error("unsupported_model", "Application model, initial state and units must match the fixed template.", "problem/body/" + key)
    origin = d.get("origin")
    if origin not in ("actual", "hypothetical", "synthetic"):
        raise _error("unsupported_model", "Declare the application dataset origin.", "dataset/body/origin")
    rows = _get(d, "rows", "dataset/body")
    if type(rows) is not list or not 3 <= len(rows) <= 128:
        raise _error("unsupported_model", "This scientific profile admits 3 to 128 rows without dropping excluded rows.", "dataset/body/rows")
    domain = _object(_get(p, "domain", "problem/body"), "problem/body/domain")
    if domain.get("rate_order") != "ke_lt_ka":
        raise _error("unsupported_model", "The fixed model requires the reviewed ke < ka order.", "problem/body/domain/rate_order")
    box = {}
    for name in ("A", "ke", "ka"):
        bounds = _object(_get(domain, name, "problem/body/domain"), "problem/body/domain/" + name)
        box[name] = [_exact(_get(bounds, endpoint, "problem/body/domain/" + name),
                            "problem/body/domain/" + name + "/" + endpoint, positive=True)
                     for endpoint in ("lower", "upper")]
        if parse_rational(box[name][0]) >= parse_rational(box[name][1]):
            raise _error("unsupported_model", "The scientific profile requires positive-width parameter domains.", "problem/body/domain/" + name)
    if parse_rational(box["ke"][1]) >= parse_rational(box["ka"][0]):
        raise _error("unsupported_model", "This scientific profile requires upper(ke) < lower(ka).", "problem/body/domain")
    target = _object(_get(p, "target", "problem/body"), "problem/body/target")
    if target.get("parameter") != "ke" or target.get("closed") is not True:
        raise _error("unsupported_model", "Only the reviewed closed ke interval is admitted.", "problem/body/target")
    claim = [_exact(_get(target, endpoint, "problem/body/target"), "problem/body/target/" + endpoint)
             for endpoint in ("lower", "upper")]
    projected_rows = []
    for index, source in enumerate(rows):
        path = f"dataset/body/rows/{index}"
        row = _object(source, path)
        row_id = _identifier(_get(row, "id", path), path + "/id")
        asset_id = _get(row, "source_asset_id", path)
        if asset_id is not None:
            _identifier(asset_id, path + "/source_asset_id")
        included = _get(row, "included", path)
        if type(included) is not bool:
            raise _error("invalid_input", "Row inclusion must be an explicit boolean.", path + "/included")
        row_origin = "hypothetical" if origin != "actual" else "transcription" if asset_id is not None else "actual"
        projected_rows.append({
            "id": row_id, "time": _exact(_get(row, "time", path), path + "/time", nonnegative=True),
            "value": _exact(_get(row, "concentration", path), path + "/concentration", nonnegative=True),
            "allowance": _exact(_get(row, "hard_allowance", path), path + "/hard_allowance", positive=True),
            "included": included, "allowance_origin": "Reviewed DB-SC-1 row hard_allowance",
            "origin": row_origin, "notes": _get(row, "notes", path),
            "provenance": f"DB-SC-1 dataset {dataset['digest']}; row {row_id}; complete source in binding envelope",
        })
    if len({row["time"] for row in projected_rows if row["included"]}) < 3:
        raise _error("unsupported_model", "At least three distinct included elapsed times are required.", "dataset/body/rows")
    scientific = normalize_problem({
        "schema_version": PROBLEM_PROFILE, "model": MODEL, "model_revision": 1,
        "units": {"time": "h", "concentration": "mg/L", "rate": "1/h"},
        "initial_conditions": {"x": "1/1", "c": "0/1"},
        "time_origin": _get(d, "time_origin", "dataset/body"),
        "dataset_kind": "actual" if origin == "actual" else "hypothetical",
        "domain": box, "claim": {"parameter": "ke", "interval": claim},
        "observations": projected_rows, "notes": _get(d, "change_reason", "dataset/body"),
        "provenance": f"{MAPPING_POLICY}; application problem {problem['digest']}; dataset {dataset['digest']}; original origin {origin}",
    })
    binding = {"schema_version": APPLICATION_BINDING, "mapping_policy": MAPPING_POLICY,
               "dataset": dataset, "problem": problem, "dataset_origin": origin,
               "projection_digest": scientific.digest}
    return {"binding": binding, "problem": scientific.to_payload(), "projection_digest": scientific.digest}


def verify_application_binding(binding: dict) -> dict:
    """Reproduce a stored mapping; an internally consistent binding is not approval."""
    b = _object(binding, "binding")
    if b.get("schema_version") != APPLICATION_BINDING or b.get("mapping_policy") != MAPPING_POLICY:
        raise _error("unsupported_model", "Unsupported application projection policy.", "binding/mapping_policy")
    projected = project_application(_get(b, "problem", "binding"), _get(b, "dataset", "binding"))
    if projected["binding"] != b:
        raise _error("wrong_specification_binding", "Stored application projection differs from fresh mapping.", "binding")
    return projected


def _candidate_vector(value: object, path: str) -> dict:
    vector = _object(value, path)
    if set(vector) != {"A", "ke", "ka"}:
        raise _error("candidate_mismatch", "A complete fixed vector is required.", path)
    return {name: _exact(vector[name], path + "/" + name, positive=True) for name in ("A", "ke", "ka")}


def _design_policy(request: dict, scientific_problem, times: list[str], budget: dict, expected: str) -> tuple:
    """Keep legacy replay stable while binding every explicit reviewed choice."""
    sources = request.get("source_artifact_ids", [])
    if type(sources) is not list or len(sources) > 2:
        raise _error("invalid_input", "Supply at most two source artifact identifiers.", "request/source_artifact_ids")
    for index, source in enumerate(sources):
        _identifier(source, f"request/source_artifact_ids/{index}")
    if len(set(sources)) != len(sources):
        raise _error("invalid_input", "Source artifact identifiers must be unique.", "request/source_artifact_ids")
    profile = request.get("scientific_profile")
    explicit_fields = ("requested_tier", "allowance_origin", "maximum_horizon")
    if profile is None:
        if sources or any(request.get(field) is not None for field in explicit_fields):
            raise _error("invalid_input", "Explicit scientific choices require the counterdex.v1 profile.", "request/scientific_profile")
        horizon = max(scientific_problem.horizon, *(parse_rational(time) for time in times))
        return (MAPPING_POLICY, "checked_pair_separation",
                {"kind": "reviewed_hard_bound", "description": f"Approved DB-SC-1 design request {expected}; future_hard_allowance"},
                rational_text(horizon))
    if profile != "counterdex.v1":
        raise _error("unsupported_model", "Unsupported application scientific profile.", "request/scientific_profile")
    for field in explicit_fields:
        if request.get(field) is None:
            raise _error("invalid_input", "Review this scientific design choice explicitly.", "request/" + field)
    tier = request["requested_tier"]
    if tier not in ("numerical_guidance", "checked_pair_separation"):
        raise _error("invalid_input", "Select an admitted scientific design tier.", "request/requested_tier")
    origin = _object(request["allowance_origin"], "request/allowance_origin")
    if set(origin) != {"kind", "description"} or origin.get("kind") not in ("hypothetical", "reviewed_hard_bound"):
        raise _error("invalid_input", "Declare the reviewed allowance kind and description.", "request/allowance_origin")
    description = origin["description"]
    if type(description) is not str or not 1 <= len(description) <= 2000:
        raise _error("invalid_input", "Supply the reviewed allowance description.", "request/allowance_origin/description")
    horizon = _exact(request["maximum_horizon"], "request/maximum_horizon", positive=True)
    if parse_rational(horizon) < scientific_problem.horizon or any(parse_rational(time) > parse_rational(horizon) for time in times):
        raise _error("unavailable_horizon", "The reviewed horizon must cover included history and every approved time.", "request/maximum_horizon")
    if tier == "checked_pair_separation" and budget["pair_verifications"] < 2:
        raise _error("invalid_input", "Checked design requires initial checking and fresh pair replay.", "request/budget/pair_verifications")
    if sources:
        raise _error("unsupported_artifact_reuse", "Prospective certificate reuse is not supported by this application bridge.", "request/source_artifact_ids")
    return DESIGN_MAPPING_POLICY, tier, origin, horizon


def project_design(request: dict, *, expected_request_digest: str, projection: dict,
                   historical_evidence: dict, native_candidate_results: list[dict]) -> dict:
    """Project the approved design after the bridge freshly replays its history.

    ``historical_evidence`` is the actual evidence body stored by Workflow.
    ``native_candidate_results`` must come from fresh native certificate replay,
    never directly from a stored valid flag. The wrapper verifies raw artifacts
    and their source/scenario bindings before calling this projection function.
    """
    current = verify_application_binding(_get(_object(projection, "projection"), "binding", "projection"))
    if projection != current:
        raise _error("wrong_specification_binding", "The supplied scientific projection was changed.", "projection")
    request = deepcopy(_object(request, "request"))
    if len(canonical_bytes(request)) > APPLICATION_BODY_CAP:
        raise _error("resource_exhaustion", "Application request exceeds its byte cap.", "request")
    expected = digest_value(expected_request_digest, "expected_request_digest")
    if request.get("schema_version") != "DB-SC-1" or semantic_digest("design-request", request) != expected:
        raise _error("wrong_specification_binding", "Design request differs from the independently supplied digest.", "request")
    binding = current["binding"]
    app_problem = binding["problem"]
    if request.get("problem_id") != app_problem["id"] or request.get("problem_digest") != app_problem["digest"]:
        raise _error("wrong_specification_binding", "Design must bind the supplied application problem.", "request/problem_digest")
    if request.get("observable") != "concentration":
        raise _error("unsupported_model", "The design observable must be concentration.", "request/observable")
    evidence = deepcopy(_object(historical_evidence, "historical_evidence"))
    for field, expected_value in (("run_id", request.get("historical_run_id")), ("scenario_id", request.get("scenario_id")),
                                  ("problem_id", app_problem["id"]), ("expected_problem_digest", app_problem["digest"])):
        if field in {"run_id", "scenario_id", "problem_id"}:
            _identifier(expected_value, "request/" + field)
        if evidence.get(field) != expected_value:
            raise _error("wrong_specification_binding", "Historical evidence belongs to a different approved scope.", "historical_evidence/" + field)
    result = _object(_get(evidence, "result", "historical_evidence"), "historical_evidence/result")
    if result.get("problem_id") != app_problem["id"] or result.get("problem_digest") != app_problem["digest"] or result.get("expected_binding") != "matches":
        raise _error("wrong_specification_binding", "Historical result must match the reviewed application problem.", "historical_evidence/result")
    ids, vectors = request.get("candidate_ids"), request.get("candidate_vectors")
    if type(ids) is not list or type(vectors) is not list or len(ids) != 2 or len(vectors) != 2:
        raise _error("missing_second_witness", "Pair design requires exactly two selected candidates.", "request/candidate_ids")
    if type(native_candidate_results) is not list:
        raise _error("incomplete_export", "Fresh native candidate results are required.", "native_candidate_results")
    app_candidates = result.get("candidates")
    if type(app_candidates) is not list:
        raise _error("incomplete_export", "Historical application candidate references are missing.", "historical_evidence/result/candidates")
    selected = []
    for index, (cid, vector) in enumerate(zip(ids, vectors)):
        _identifier(cid, f"request/candidate_ids/{index}")
        vector = _candidate_vector(vector, f"request/candidate_vectors/{index}")
        refs = [item for item in app_candidates if type(item) is dict and item.get("id") == cid]
        checked = [item for item in native_candidate_results if type(item) is dict and item.get("candidate_id") == cid]
        if len(refs) != 1 or len(checked) != 1:
            raise _error("candidate_mismatch", "Each selected candidate must occur once in application and native history.", f"request/candidate_ids/{index}")
        ref, native = refs[0], checked[0]
        if (ref.get("parameter_vector") != vector or ref.get("problem_id") != app_problem["id"]
                or ref.get("problem_digest") != app_problem["digest"] or ref.get("observable") != "concentration"
                or native.get("parameters") != vector):
            raise _error("candidate_mismatch", "The selected fixed vector differs from its historical evidence.", f"request/candidate_vectors/{index}")
        # Native baseline certificates are historical evidence, not reusable
        # prospective analytic-pair certificates. Construction stays explicit.
        selected.append({"id": cid, "problem_digest": current["projection_digest"],
                         "parameters": vector, "source_artifact_digest": None})
    if ids[0] == ids[1] or vectors[0] == vectors[1]:
        raise _error("candidate_mismatch", "The selected pair requires distinct IDs and exact vectors.", "request/candidate_ids")
    times = request.get("feasible_times")
    if type(times) is not list or not 1 <= len(times) <= 64:
        raise _error("invalid_input", "Review between one and 64 prospective times.", "request/feasible_times")
    times = [_exact(time, f"request/feasible_times/{i}", positive=True) for i, time in enumerate(times)]
    if len(set(times)) != len(times):
        raise _error("invalid_input", "Approved prospective times must be distinct.", "request/feasible_times")
    allowance = _exact(request.get("future_hard_allowance"), "request/future_hard_allowance", positive=True)
    construction, extension = request.get("allow_construction"), request.get("allow_continuation")
    if type(construction) is not bool or type(extension) is not bool:
        raise _error("invalid_input", "Construction and continuation choices must be explicit booleans.", "request/allow_construction")
    if extension and not construction:
        raise _error("unsupported_model", "Continuation requires separately authorized construction.", "request/allow_continuation")
    budget = _object(request.get("budget"), "request/budget")
    caps = {"wall_seconds": (1, 120), "fixed_vector_constructions": (0, 2),
            "pair_verifications": (0, 2), "bundle_bytes": (1, 4 * 1024 * 1024)}
    for key, (lo, hi) in caps.items():
        value = budget.get(key)
        if type(value) is not int or not lo <= value <= hi:
            raise _error("invalid_input", "Design resource budget exceeds the scientific profile.", "request/budget/" + key)
    scientific_problem = normalize_problem(current["problem"])
    mapping_policy, tier, allowance_origin, horizon = _design_policy(request, scientific_problem, times, budget, expected)
    design = normalize_design({
        "schema_version": DESIGN_PROFILE, "problem_digest": current["projection_digest"],
        "scenario_id": request["scenario_id"], "candidates": selected,
        "grid": [{"time": time, "feasible": True, "reason": "Reviewed application feasible time"} for time in times],
        "time_origin": scientific_problem.time_origin, "observable": "c", "future_allowance": allowance,
        "allowance_origin": allowance_origin,
        "requested_tier": tier,
        "horizon_policy": {"allow_construction": construction, "allow_extension": extension, "maximum_horizon": horizon},
        "numerical_policy": NUMERICAL_POLICY, "checked_policy": CHECKED_POLICY,
        "limits": {"wall_seconds": budget["wall_seconds"], "max_times": len(times),
                   "max_constructions": budget["fixed_vector_constructions"], "max_pair_verifications": budget["pair_verifications"],
                   "max_bundle_bytes": budget["bundle_bytes"], "max_certificate_bytes": min(2 * 1024 * 1024, budget["bundle_bytes"])},
    }, scientific_problem)
    design_binding = {"schema_version": DESIGN_BINDING, "mapping_policy": mapping_policy,
                      "application": binding, "request": request, "request_digest": expected,
                      "historical_evidence": evidence, "design_digest": design.digest,
                      "approved_grid_order": times}
    return {"binding": design_binding, "design": design.to_payload(), "design_digest": design.digest,
            "approved_grid_order": times}


def verify_design_binding(binding: dict, *, native_candidate_results: list[dict]) -> dict:
    b = _object(binding, "binding")
    if b.get("schema_version") != DESIGN_BINDING or b.get("mapping_policy") not in (MAPPING_POLICY, DESIGN_MAPPING_POLICY):
        raise _error("unsupported_model", "Unsupported application design mapping policy.", "binding/mapping_policy")
    projection = verify_application_binding(_get(b, "application", "binding"))
    result = project_design(_get(b, "request", "binding"), expected_request_digest=_get(b, "request_digest", "binding"),
                            projection=projection, historical_evidence=_get(b, "historical_evidence", "binding"),
                            native_candidate_results=native_candidate_results)
    if result["binding"] != b:
        raise _error("wrong_specification_binding", "Stored design projection differs from fresh mapping.", "binding")
    return result


def restore_approved_grid(options: list[dict], approved_grid_order: list[str]) -> list[dict]:
    """Retain every option/reason while undoing the scientific grid sort."""
    if type(options) is not list or type(approved_grid_order) is not list:
        raise _error("invalid_input", "Expected approved grid and option arrays.", "options")
    approved_grid_order = [_exact(time, "approved_grid_order", positive=True) for time in approved_grid_order]
    indexed = {}
    for option in options:
        item = _object(option, "options")
        time = item.get("time")
        if type(time) is not str or time in indexed:
            raise _error("wrong_specification_binding", "Scientific options contain duplicate or absent times.", "options")
        indexed[time] = item
    if len(set(approved_grid_order)) != len(approved_grid_order) or set(indexed) != set(approved_grid_order):
        raise _error("wrong_specification_binding", "Scientific options must retain every approved time exactly once.", "options")
    return [deepcopy(indexed[time]) for time in approved_grid_order]
