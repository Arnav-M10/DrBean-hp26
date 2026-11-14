"""Strict JSON requests for the analyses (``counterdex-models.request.v1``).

Requests name registered models; they cannot supply code. Unknown fields are
refused, and any field naming an allowance is refused explicitly because hard
allowances belong to the exact Counterdex checker.
"""
from __future__ import annotations

import hashlib
import json

from . import analysis
from .interface import (Budget, DetectionThreshold, ModelError, ModelRegistry, NoiseModel, Observation, Observations,
                        to_float)

REQUEST_SCHEMA = "counterdex-models.request.v1"
MAX_REQUEST_BYTES = 1024 * 1024


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def sha256(value) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _refuse_allowances(value, path="") -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if "allowance" in str(key).lower():
                raise ModelError("hard_allowance_not_accepted", "Hard allowances belong to the exact Counterdex checker. "
                                 "Supply a noise standard deviation and, separately, any detection threshold.", f"{path}/{key}")
            _refuse_allowances(item, f"{path}/{key}")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            _refuse_allowances(item, f"{path}/{i}")


def _obj(value, path, required, optional=()) -> dict:
    if not isinstance(value, dict):
        raise ModelError("invalid_input", "Expected an object.", path)
    unknown = set(value) - set(required) - set(optional)
    missing = set(required) - set(value)
    if unknown:
        raise ModelError("invalid_input", f"Unknown fields: {sorted(unknown)}.", path)
    if missing:
        raise ModelError("invalid_input", f"Missing fields: {sorted(missing)}.", path)
    return value


def _int(value, path) -> int:
    if type(value) is not int:
        raise ModelError("invalid_input", "Expected an integer.", path)
    return value


def _text(value, path, limit=500) -> str:
    if not isinstance(value, str) or len(value) > limit:
        raise ModelError("invalid_input", f"Expected text of at most {limit} characters.", path)
    return value


def _noise(value, path="noise") -> NoiseModel:
    v = _obj(value, path, (), ("absolute_sd", "relative_sd", "label"))
    return NoiseModel(to_float(v.get("absolute_sd", 0), f"{path}/absolute_sd"),
                      to_float(v.get("relative_sd", 0), f"{path}/relative_sd"), _text(v.get("label", ""), f"{path}/label"))


def _threshold(value, path="detection_threshold") -> DetectionThreshold | None:
    if value is None:
        return None
    v = _obj(value, path, ("value",), ("label",))
    return DetectionThreshold(to_float(v["value"], f"{path}/value"), _text(v.get("label", ""), f"{path}/label"))


def _observations(value, path="observations") -> Observations:
    v = _obj(value, path, ("time_unit", "response_unit", "rows"), ("provenance",))
    if not isinstance(v["rows"], list):
        raise ModelError("invalid_input", "rows must be a list.", f"{path}/rows")
    rows = []
    for i, row in enumerate(v["rows"]):
        r = _obj(row, f"{path}/rows/{i}", ("time",), ("value", "censored"))
        censored = r.get("censored", False)
        if type(censored) is not bool:
            raise ModelError("invalid_input", "censored must be true or false.", f"{path}/rows/{i}/censored")
        value_ = None if censored and r.get("value") is None else to_float(r.get("value"), f"{path}/rows/{i}/value")
        rows.append(Observation(to_float(r["time"], f"{path}/rows/{i}/time"), value_, censored))
    return Observations(_text(v["time_unit"], f"{path}/time_unit", 40), _text(v["response_unit"], f"{path}/response_unit", 40),
                        tuple(rows), _text(v.get("provenance", ""), f"{path}/provenance", 2000))


def _params(value, path) -> dict:
    if not isinstance(value, dict):
        raise ModelError("invalid_input", "Expected parameter values by name.", path)
    return {k: to_float(x, f"{path}/{k}") for k, x in value.items()}


def _times(value, path="times") -> list[float]:
    if not isinstance(value, list):
        raise ModelError("invalid_input", "Expected a list of times.", path)
    return [to_float(t, f"{path}/{i}") for i, t in enumerate(value)]


def _models(registry, value, path="models"):
    if not isinstance(value, list) or not all(isinstance(x, str) for x in value):
        raise ModelError("invalid_input", "Expected a list of registered model ids.", path)
    return [registry.get(x) for x in value]


def _fit_options(value) -> dict:
    v = _obj(value or {}, "fit", (), ("starts", "max_iterations"))
    return {k: _int(x, f"fit/{k}") for k, x in v.items()}


def run_request(request: dict, registry: ModelRegistry) -> dict:
    """Validate and run one request; refusals raise ``ModelError``."""
    _refuse_allowances(request)
    common = ("schema_version", "analysis", "limits", "note")
    if not isinstance(request, dict) or request.get("schema_version") != REQUEST_SCHEMA:
        raise ModelError("invalid_input", f"schema_version must be {REQUEST_SCHEMA}.", "schema_version")
    kind = request.get("analysis")
    limits = _obj(request.get("limits", {}), "limits", (), ("max_evaluations", "wall_seconds"))
    budget = Budget(max_evaluations=_int(limits.get("max_evaluations", 2_000_000), "limits/max_evaluations"),
                    wall_seconds=to_float(limits.get("wall_seconds", 60), "limits/wall_seconds"))
    if kind == "fit":
        r = _obj(request, "", common[:2] + ("observations", "models", "noise"), common[2:] + ("detection_threshold", "fit"))
        result = analysis.fit_models(_models(registry, r["models"]), _observations(r["observations"]), _noise(r["noise"]),
                                     _threshold(r.get("detection_threshold")), budget=budget, **_fit_options(r.get("fit")))
    elif kind == "sensitivity":
        r = _obj(request, "", common[:2] + ("model", "parameters", "times"), common[2:] + ("points", "ranges"))
        ranges = {}
        if not isinstance(r.get("ranges", {}), dict):
            raise ModelError("invalid_input", "ranges must map parameter names to [low, high].", "ranges")
        for name, span in r.get("ranges", {}).items():
            if not isinstance(span, list) or len(span) != 2:
                raise ModelError("invalid_input", "A range is [low, high].", f"ranges/{name}")
            ranges[name] = (to_float(span[0], f"ranges/{name}/0"), to_float(span[1], f"ranges/{name}/1"))
        result = analysis.sensitivity(registry.get(_text(r["model"], "model", 80)), _params(r["parameters"], "parameters"),
                                      _times(r["times"]), points=_int(r.get("points", 11), "points"), ranges=ranges, budget=budget)
    elif kind == "scenarios":
        r = _obj(request, "", common[:2] + ("observations", "models", "scenarios"), common[2:] + ("fit",))
        if not isinstance(r["scenarios"], list):
            raise ModelError("invalid_input", "scenarios must be a list.", "scenarios")
        scenarios = []
        for i, s in enumerate(r["scenarios"]):
            s = _obj(s, f"scenarios/{i}", ("label", "noise"), ("detection_threshold",))
            scenarios.append((_text(s["label"], f"scenarios/{i}/label", 120), _noise(s["noise"], f"scenarios/{i}/noise"),
                              _threshold(s.get("detection_threshold"), f"scenarios/{i}/detection_threshold")))
        result = analysis.compare_scenarios(_models(registry, r["models"]), _observations(r["observations"]), scenarios,
                                            budget=budget, **_fit_options(r.get("fit")))
    elif kind == "monte_carlo":
        r = _obj(request, "", common[:2] + ("truth", "candidates", "times", "noise", "replicates", "seed"),
                 common[2:] + ("detection_threshold", "fit"))
        truth = _obj(r["truth"], "truth", ("model", "parameters"))
        result = analysis.monte_carlo(registry.get(_text(truth["model"], "truth/model", 80)), _params(truth["parameters"], "truth/parameters"),
                                      _models(registry, r["candidates"], "candidates"), _times(r["times"]), _noise(r["noise"]),
                                      _threshold(r.get("detection_threshold")), replicates=_int(r["replicates"], "replicates"),
                                      seed=_int(r["seed"], "seed"), budget=budget, **_fit_options(r.get("fit")))
    elif kind == "grid_ranking":
        r = _obj(request, "", common[:2] + ("hypotheses", "times", "noise"), common[2:] + ("detection_threshold",))
        if not isinstance(r["hypotheses"], list):
            raise ModelError("invalid_input", "hypotheses must be a list.", "hypotheses")
        hypotheses = []
        for i, h in enumerate(r["hypotheses"]):
            h = _obj(h, f"hypotheses/{i}", ("label", "model", "parameters"))
            hypotheses.append((_text(h["label"], f"hypotheses/{i}/label", 120), registry.get(_text(h["model"], f"hypotheses/{i}/model", 80)),
                               _params(h["parameters"], f"hypotheses/{i}/parameters")))
        result = analysis.rank_grid(hypotheses, _times(r["times"]), _noise(r["noise"]), _threshold(r.get("detection_threshold")), budget=budget)
    else:
        raise ModelError("invalid_input", "analysis must be fit, sensitivity, scenarios, monte_carlo or grid_ranking.", "analysis")
    result["request_sha256"] = sha256(request)
    result["result_sha256"] = sha256(result)  # over everything above, including request_sha256
    return result
