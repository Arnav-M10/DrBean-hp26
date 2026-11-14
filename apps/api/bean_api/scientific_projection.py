"""Versioned lossless application-to-Counterdex mapping, never a scientific checker."""
from __future__ import annotations

from fractions import Fraction
import json

from .canonical import semantic_digest, validate_rational
from .workflow import DomainError

PROJECTION_VERSION = "bean-to-counterdex.v1"


def _fail(message: str, path: str) -> None:
    raise DomainError("scientific_admission", message, 422, [path])


def _exact(value: str, path: str) -> Fraction:
    try:
        validate_rational(value)
        number = Fraction(value)
    except (ValueError, TypeError, ZeroDivisionError):
        _fail("Supply a canonical exact rational.", path)
    if max(number.numerator.bit_length(), number.denominator.bit_length()) > 256:
        _fail("Counterdex checked arithmetic admits at most 256-bit rational components.", path)
    return number


def _text_json(value: dict, path: str) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(text) > 4096:
        _fail("Source provenance exceeds the scientific projection's text limit; it cannot be truncated.", path)
    return text


def _bounded_text(value: str, path: str, *, empty: bool = False) -> None:
    if not isinstance(value, str) or len(value) > 4096 or (not empty and not value.strip()):
        _fail("Supply bounded scientific text without losing the reviewed content.", path)
    if any(0xD800 <= ord(character) <= 0xDFFF for character in value):
        _fail("Scientific text must contain valid Unicode scalars.", path)


def admit_problem(problem: dict, dataset: dict) -> None:
    """Admit the exact reviewed scope before dispatch; never repair/narrow input."""
    p, d = problem.get("body", problem), dataset.get("body", dataset)
    for envelope, kind in ((problem, "problem"), (dataset, "dataset")):
        if "body" in envelope and envelope.get("digest") != semantic_digest(kind, envelope["body"]):
            raise DomainError("binding_mismatch", "Immutable application content does not match its digest.", 422)
    if "id" in dataset and (p["dataset_id"] != dataset["id"] or p["dataset_digest"] != dataset["digest"]):
        raise DomainError("binding_mismatch", "Problem and dataset identities do not match.", 422)
    if p.get("model") != "two_rate_concentration" or p.get("initial_concentration") != "0/1":
        _fail("Counterdex only supports the fixed initial two-rate model.", "model")
    if any(p.get(k) != v for k, v in {"observable": "concentration", "time_unit": "h", "concentration_unit": "mg/L", "rate_unit": "1/h"}.items()):
        _fail("Counterdex requires concentration in mg/L, elapsed hours and rates per hour.", "units")
    _bounded_text(d["time_origin"], "time_origin")
    _bounded_text(d["change_reason"], "change_reason", empty=True)
    rows = d["rows"]
    if not 3 <= len(rows) <= 128:
        _fail("Counterdex requires 3–128 historical rows, including excluded rows.", "rows")
    times = set()
    for i, row in enumerate(rows):
        _bounded_text(row.get("notes", ""), f"rows[{i}].notes", empty=True)
        for name in ("time", "concentration", "hard_allowance"):
            value = _exact(row[name], f"rows[{i}].{name}")
            if name == "time" and value < 0:
                _fail("Elapsed time must be nonnegative.", f"rows[{i}].time")
            if name == "hard_allowance" and value <= 0:
                _fail("Historical hard allowance must be positive.", f"rows[{i}].hard_allowance")
        if row["included"]:
            times.add(Fraction(row["time"]))
    if len(times) < 3:
        _fail("Counterdex requires three distinct included observation times.", "rows")
    for name in ("A", "ke", "ka"):
        box = p["domain"][name]
        lo, hi = (_exact(box[k], f"domain.{name}.{k}") for k in ("lower", "upper"))
        if not 0 < lo < hi:
            _fail("Counterdex parameter intervals must be positive and strictly ordered.", f"domain.{name}")
    if Fraction(p["domain"]["ke"]["upper"]) >= Fraction(p["domain"]["ka"]["lower"]):
        _fail("Counterdex requires upper(ke) < lower(ka); no narrowing is performed.", "domain")
    for name in ("lower", "upper"):
        _exact(p["target"][name], "target." + name)


def project_problem(problem: dict, dataset: dict) -> dict:
    admit_problem(problem, dataset)
    p, d = problem.get("body", problem), dataset.get("body", dataset)
    application_origin = d["origin"]
    engine_origin = "actual" if application_origin == "actual" else "hypothetical"
    observations = []
    for i, row in enumerate(d["rows"]):
        provenance = {"application_origin": application_origin,
                      "source_asset_id": row.get("source_asset_id"),
                      "original_values": row.get("original_values", {})}
        for key in ("intake_review_id", "review_decision_id", "observation_proposal_id"):
            if key in row:
                provenance[key] = row[key]
        observations.append({"id": row["id"], "time": row["time"], "value": row["concentration"],
            "allowance": row["hard_allowance"], "included": row["included"],
            "allowance_origin": "Reviewed application row.hard_allowance, a hard absolute bound",
            "origin": engine_origin, "notes": row.get("notes", ""),
            "provenance": _text_json(provenance, f"rows[{i}].original_values")})
    return {"schema_version": "groundwork.problem.v1", "model": "two_rate_kinetics_v1", "model_revision": 1,
        "units": {"time": "h", "concentration": "mg/L", "rate": "1/h"},
        "initial_conditions": {"x": "1/1", "c": "0/1"}, "time_origin": d["time_origin"],
        "dataset_kind": engine_origin, "domain": {key: [p["domain"][key]["lower"], p["domain"][key]["upper"]] for key in ("A", "ke", "ka")},
        "claim": {"parameter": "ke", "interval": [p["target"]["lower"], p["target"]["upper"]]},
        "observations": observations, "notes": d["change_reason"],
        "provenance": _text_json({"projection_version": PROJECTION_VERSION, "application_problem_id": problem.get("id"),
            "application_problem_digest": problem.get("digest", semantic_digest("problem", p)),
            "application_dataset_id": dataset.get("id"), "application_dataset_digest": dataset.get("digest", semantic_digest("dataset", d)),
            "experiment_id": d["experiment_id"], "application_origin": application_origin}, "provenance")}


def project_design(request: dict, projection: dict, source_digests: list[str | None]) -> dict:
    """Preserve an explicit approved grid; engine sorting is mapped back by exact time."""
    required = {"requested_tier", "allowance_origin", "maximum_horizon"}
    for field in required:
        if request.get(field) is None:
            _fail("Review this scientific design field explicitly before execution.", field)
    for i, time in enumerate(request["feasible_times"]):
        if _exact(time, f"feasible_times[{i}]") <= 0:
            _fail("Future elapsed times must be positive.", f"feasible_times[{i}]")
    if _exact(request["future_hard_allowance"], "future_hard_allowance") <= 0:
        _fail("Future hard allowance must be positive.", "future_hard_allowance")
    _bounded_text(request["allowance_origin"]["description"], "allowance_origin.description")
    for i, vector in enumerate(request["candidate_vectors"]):
        for name in ("A", "ke", "ka"):
            value = _exact(vector[name], f"candidate_vectors[{i}].{name}")
            lower, upper = map(Fraction, projection["domain"][name])
            if not lower <= value <= upper:
                _fail("The fixed candidate must be inside the complete reviewed domain.", f"candidate_vectors[{i}].{name}")
    if request["candidate_vectors"][0] == request["candidate_vectors"][1]:
        _fail("Select two distinct fixed parameter vectors.", "candidate_vectors")
    horizon = _exact(request["maximum_horizon"], "maximum_horizon")
    if horizon < max(Fraction(r["time"]) for r in projection["observations"] if r["included"]):
        _fail("Maximum horizon must cover the included reviewed history.", "maximum_horizon")
    if request["requested_tier"] == "checked_pair_separation" and any(Fraction(t) > horizon for t in request["feasible_times"]):
        _fail("Every checked future time must fit the approved maximum horizon.", "maximum_horizon")
    if len(source_digests) != 2:
        _fail("Each fixed candidate needs an explicit source binding or null for approved construction.", "source_artifact_ids")
    budget = request["budget"]
    if request["requested_tier"] == "checked_pair_separation" and budget["pair_verifications"] < 2:
        _fail("Checked output requires two pair verifications: initial checking and fresh native replay.", "budget.pair_verifications")
    digest = semantic_digest("problem", projection)
    return {"schema_version": "groundwork.design.v1", "problem_digest": digest,
        "scenario_id": request["scenario_id"], "candidates": [
            {"id": identity, "parameters": vector, "problem_digest": digest, "source_artifact_digest": source}
            for identity, vector, source in zip(request["candidate_ids"], request["candidate_vectors"], source_digests, strict=True)],
        "grid": [{"time": t, "feasible": True, "reason": "Explicit reviewed application feasible time"} for t in request["feasible_times"]],
        "time_origin": projection["time_origin"], "observable": "c",
        "future_allowance": request["future_hard_allowance"], "allowance_origin": request["allowance_origin"],
        "requested_tier": request["requested_tier"],
        "horizon_policy": {"maximum_horizon": request["maximum_horizon"], "allow_construction": request["allow_construction"], "allow_extension": request["allow_continuation"]},
        "numerical_policy": "pair-gap-over-allowance-12sig-half-even.v1", "checked_policy": "positive-margin-descending-time-ids.v1",
        "limits": {"wall_seconds": budget["wall_seconds"], "max_times": len(request["feasible_times"]),
            "max_constructions": budget["fixed_vector_constructions"], "max_pair_verifications": budget["pair_verifications"],
            "max_bundle_bytes": budget["bundle_bytes"], "max_certificate_bytes": 2 * 1024 * 1024}}
