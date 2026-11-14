"""Bounded numerical reference coordinator for scientific adapter integration.

This implementation is explicitly distinct from Counterdex's exact kinetics
checker. It makes no provider calls and never emits an exact-verification badge.
"""
from __future__ import annotations

import hashlib
import itertools
import math
import platform
import random
from pathlib import Path

from ..canonical import canonical_bytes
from .contract import ModelComparisonRequest, ModelComparisonResult
from .models import ISOTROPIC, MODELS, predict_current


def number(value: float) -> str:
    if not math.isfinite(value):
        raise ValueError("Nonfinite numerical result")
    return format(0.0 if value == 0 else value, ".15g")


def source_digest() -> str:
    source = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
              for path in sorted(Path(__file__).parent.glob("*.py"))}
    return hashlib.sha256(canonical_bytes(source)).hexdigest()


def _rank(columns: list[list[float]]) -> int:
    """Scale-independent modified Gram-Schmidt diagnostic, not an exact rank proof."""
    basis = []
    for column in columns:
        length = math.sqrt(math.fsum(x*x for x in column))
        if length == 0:
            continue
        vector = [x / length for x in column]
        for existing in basis:
            dot = math.fsum(a*b for a, b in zip(existing, vector, strict=True))
            vector = [a - dot*b for a, b in zip(vector, existing, strict=True)]
        length = math.sqrt(math.fsum(x*x for x in vector))
        if length > 1e-7:
            basis.append([x / length for x in vector])
    return len(basis)


def _fit(request: ModelComparisonRequest, model_id: str, rows: list[tuple]) -> dict:
    temperatures = sorted(map(float, request.fit.temperature_grid_eV))
    grid = ((t,) for t in temperatures) if model_id == ISOTROPIC else itertools.product(temperatures, repeat=2)
    lower, upper = float(request.fit.density_min_m3), float(request.fit.density_max_m3)
    best = None
    evaluations = 0
    for point in grid:
        parameters = ({"temperature_eV": point[0]} if model_id == ISOTROPIC
                      else {"parallel_eV": point[0], "perpendicular_eV": point[1]})
        parameters["density_m3"] = 1.0
        basis = [predict_current(parameters, channel, request.instrument) for _, _, channel in rows]
        denominator = math.fsum((unit / float(row.sigma_A))**2 for unit, (_, row, _) in zip(basis, rows, strict=True))
        evaluations += 1
        if denominator == 0:
            continue
        numerator = math.fsum(unit * float(row.current_A) / float(row.sigma_A)**2
                              for unit, (_, row, _) in zip(basis, rows, strict=True))
        density = min(upper, max(lower, numerator / denominator))
        predictions = [density * unit for unit in basis]
        residuals = [float(row.current_A) - pred for pred, (_, row, _) in zip(predictions, rows, strict=True)]
        chi_square = math.fsum((residual / float(row.sigma_A))**2
                              for residual, (_, row, _) in zip(residuals, rows, strict=True))
        candidate = (chi_square, tuple(point), density, predictions, residuals, parameters)
        if best is None or candidate[:3] < best[:3]:
            best = candidate
    parameter_count = 2 if model_id == ISOTROPIC else 3
    if best is None:
        return {"model_id": model_id, "status": "no_finite_candidate", "parameter_count": parameter_count,
                "evaluations": evaluations, "parameters": {}, "predictions": [], "sensitivity": [],
                "rank_estimate": 0, "rank_deficient": True, "boundary_limited": False,
                "chi_square": None, "reduced_chi_square": None, "degrees_of_freedom": None,
                "rmse_A": None, "adequate_under_declared_threshold": False}
    chi_square, point, density, predictions, residuals, parameters = best
    parameters["density_m3"] = density
    degrees = len(rows) - parameter_count
    reduced = chi_square / degrees if degrees > 0 else None
    sensitivity, columns = [], []
    for name, value in parameters.items():
        plus, minus = dict(parameters), dict(parameters)
        plus[name], minus[name] = value * math.exp(1e-4), value * math.exp(-1e-4)
        derivative = [(predict_current(plus, channel, request.instrument) -
                       predict_current(minus, channel, request.instrument)) / 2e-4 for _, _, channel in rows]
        columns.append([item / float(row.sigma_A) for item, (_, row, _) in zip(derivative, rows, strict=True)])
        sensitivity.append({"parameter": name, "derivative": "d_current_d_log_parameter", "unit": "A",
                            "values": [number(value) for value in derivative], "relative_step": "0.0001"})
    rank = _rank(columns)
    adequate = reduced is not None and reduced <= float(request.fit.max_reduced_chi_square)
    return {"model_id": model_id, "status": "bounded_grid_completed", "parameter_count": parameter_count,
            "evaluations": evaluations, "parameters": {key: number(value) for key, value in parameters.items()},
            "predictions": [{"observation_index": index, "channel_id": row.channel_id,
                             "observed_A": row.current_A, "predicted_A": number(pred),
                             "residual_A": number(residual), "sigma_A": row.sigma_A}
                            for (index, row, _), pred, residual in zip(rows, predictions, residuals, strict=True)],
            "chi_square": number(chi_square), "reduced_chi_square": number(reduced) if reduced is not None else None,
            "degrees_of_freedom": degrees if degrees > 0 else None,
            "rmse_A": number(math.sqrt(math.fsum(r*r for r in residuals) / len(rows))),
            "adequate_under_declared_threshold": adequate,
            "boundary_limited": density in (lower, upper) or any(t in (temperatures[0], temperatures[-1]) for t in point),
            "sensitivity": sensitivity, "rank_estimate": rank, "rank_deficient": rank < parameter_count}


def _wilson(count: int, total: int) -> list[str]:
    z = 1.959963984540054
    fraction = count / total
    scale = 1 + z*z/total
    center = (fraction + z*z/(2*total)) / scale
    radius = z * math.sqrt(fraction*(1-fraction)/total + z*z/(4*total*total)) / scale
    return [number(max(0, center-radius)), number(min(1, center+radius))]


def _simulate(means: list[list[float]], sigma: float, z: float, draws: list[list[list[float]]]) -> list[dict]:
    """Conditional fixed-prediction rectangular-band frequencies, NOT family selection."""
    outcomes = []
    for generating, normals in enumerate(draws):
        counts = {"generating_band_only": 0, "other_band_only": 0, "both_bands": 0, "neither_band": 0}
        for sample in normals:
            values = [mu + sigma * draw for mu, draw in zip(means[generating], sample, strict=True)]
            accepted = [all(abs(y - mu) <= z*sigma for y, mu in zip(values, candidate, strict=True)) for candidate in means]
            if all(accepted):
                label = "both_bands"
            elif not any(accepted):
                label = "neither_band"
            elif accepted[generating]:
                label = "generating_band_only"
            else:
                label = "other_band_only"
            counts[label] += 1
        outcomes.append({"generating_model_id": MODELS[generating], "samples": len(normals), "failures": 0,
                         "outcomes": {key: {"count": count, "frequency": number(count / len(normals)),
                                            "wilson_95": _wilson(count, len(normals))} for key, count in counts.items()}})
    return outcomes


def compute_comparison(request: ModelComparisonRequest) -> dict:
    if not isinstance(request, ModelComparisonRequest):
        request = ModelComparisonRequest.model_validate(request)
    raw = request.model_dump(mode="json")
    result = {"schema_version": "DB-MODEL-COMPARISON-RESULT-1", "status": "completed", "request": raw,
              "input_digest": hashlib.sha256(canonical_bytes(raw)).hexdigest(), "source_digest": source_digest(),
              "numerical_backend": "drbean_bounded_grid_reference.v1", "exact_verification": "not_performed",
              "simulation_seed": request.noise.seed, "simulation_samples": request.noise.samples,
              "methods": {"fit": "bounded temperature grid with analytic clipped WLS density profile",
                          "sensitivity": "central differences with log-parameter step 0.0001; numerical rank tolerance 1e-7",
                          "simulation": "conditional fixed-prediction independent Gaussian rectangular bands; no parameter refit",
                          "random": "CPython random.Random.gauss; common standardized draws across sweep cases",
                          "interval": "Wilson 95% interval for Monte Carlo sampling frequency only",
                          "runtime": platform.python_implementation() + " " + platform.python_version()},
              "model_ids": list(MODELS),
              "units": {"current": "A (electron magnitude)", "density": "m^-3", "temperature": "eV = k_B*T/e",
                        "energy": "eV (normal kinetic energy)", "area": "m^2", "angle": "degree to parallel axis"},
              "fits": [], "settings": [], "noise_sweep": [], "failures": [], "decision": "",
              "limitations": [
                  "Idealized synthetic planar normal-energy instrument; no calibration to MRX, PPPL, an EEA or a real Langmuir probe.",
                  "Zero drift, nonrelativistic electrons, fixed known area/efficiency, full tangential acceptance and sharp energy edges; no sheath or background model.",
                  "A completed bounded grid is not a continuous/global optimum. Fit residuals alone never identify a true model; the anisotropic family has an additional parameter.",
                  "Monte Carlo conditions on fitted parameter vectors; it does not refit model families or propagate parameter-estimation uncertainty.",
                  "Frequencies describe the specified simulation and Wilson intervals describe finite Monte Carlo sampling only; neither is a probability a model is true.",
                  "Rectangular per-channel bands have no automatic simultaneous or multiple-comparison error guarantee; feasible-grid ranking is a point-prediction heuristic.",
                  "A single collector angle sees only projected temperature; parallel/perpendicular temperatures may be unidentifiable.",
                  "All fits and sensitivity are floating-point numerical calculations. No exact Counterdex verification or native mathematical certificate is produced."]}
    def finish(status, code, message):
        result["status"] = status
        result["failures"].append({"code": code, "message": message})
        result["decision"] = message
        return ModelComparisonResult.model_validate(result).model_dump(mode="json")
    if request.instrument is None:
        return finish("unsupported", "missing_instrument_response", "An explicit response, acceptance, area, efficiency and current convention are required.")
    channels = {item.id: item for item in request.channels}
    rows = [(index, row, channels[row.channel_id]) for index, row in enumerate(request.observations)
            if row.channel_id in request.selected_channel_ids]
    grid_size = len(request.fit.temperature_grid_eV)
    fit_evaluations = grid_size + grid_size*grid_size
    simulation_work = 2 * request.noise.samples * len(request.noise.sigma_grid_A) * len(request.noise.z_thresholds) * (len(rows) + len(request.feasible_settings))
    if fit_evaluations > request.fit.max_evaluations or fit_evaluations*len(rows) > 50000 or simulation_work > 262144:
        return finish("budget_exceeded", "declared_or_service_work_limit", "The requested fit/simulation exceeds the declared or service work budget; reduce the grid or sample count.")
    result["fits"] = [_fit(request, model, rows) for model in MODELS]
    if any(not fit["parameters"] for fit in result["fits"]):
        return finish("fit_failed", "no_finite_candidate", "No usable candidate was found within the supplied numerical grid.")
    if not any(fit["adequate_under_declared_threshold"] for fit in result["fits"]):
        return finish("fit_failed", "bounded_fit_inadequate", "Neither bounded fit meets the declared fit-adequacy threshold; this does not rule out all parameter values or other models.")
    parameters = [{key: float(value) for key, value in fit["parameters"].items()} for fit in result["fits"]]
    selected_means = [[float(row["predicted_A"]) for row in fit["predictions"]] for fit in result["fits"]]
    for setting in request.feasible_settings:
        means = [predict_current(p, setting, request.instrument) for p in parameters]
        result["settings"].append({"setting": setting.model_dump(mode="json"),
                                   "predictions_A": {model: number(value) for model, value in zip(MODELS, means, strict=True)},
                                   "absolute_difference_A": number(abs(means[1] - means[0]))})
    rng = random.Random(request.noise.seed)
    selected_draws = [[[rng.gauss(0, 1) for _ in rows] for _ in range(request.noise.samples)] for _ in MODELS]
    setting_draws = [[[rng.gauss(0, 1)] for _ in range(request.noise.samples)] for _ in MODELS]
    for sigma_text in request.noise.sigma_grid_A:
        sigma = float(sigma_text)
        for threshold_text in request.noise.z_thresholds:
            threshold = float(threshold_text)
            maximum_gap = max(abs(a-b) for a, b in zip(*selected_means, strict=True))
            separated = maximum_gap > 2 * threshold * sigma
            comparisons = []
            for setting in result["settings"]:
                means = [[float(setting["predictions_A"][model])] for model in MODELS]
                gap = float(setting["absolute_difference_A"])
                comparisons.append({"setting_id": setting["setting"]["id"], "signal_to_noise": number(gap / sigma),
                                    "numerical_band_margin_A": number(gap - 2*threshold*sigma),
                                    "conditional_simulations": _simulate(means, sigma, threshold, setting_draws)})
            best = max(comparisons, key=lambda entry: (float(entry["numerical_band_margin_A"]), entry["setting_id"]))
            result["noise_sweep"].append({"sigma_A": sigma_text, "z_threshold": threshold_text,
                                         "selected_channel_bands_separated_numerically": separated,
                                         "decision": "The selected fitted predictions have disjoint numerical bands in at least one reviewed channel." if separated else "These measurements do not distinguish the selected models under the declared noise and band threshold.",
                                         "selected_channel_simulations": _simulate(selected_means, sigma, threshold, selected_draws),
                                         "settings": comparisons,
                                         "suggested_setting_id": best["setting_id"] if float(best["numerical_band_margin_A"]) > 0 else None})
    result["decision"] = ("Selected fitted predictions are numerically distinguishable in some declared noise cases; this does not establish a correct model."
                          if any(case["selected_channel_bands_separated_numerically"] for case in result["noise_sweep"])
                          else "These measurements do not distinguish the selected models under the declared noise and band thresholds.")
    return ModelComparisonResult.model_validate(result).model_dump(mode="json")
