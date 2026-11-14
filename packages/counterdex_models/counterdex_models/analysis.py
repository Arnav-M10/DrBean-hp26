"""Model comparison analyses built on the registered-model interface.

Every result is a plain JSON-ready dict with ``certification: "none"``, the
inputs used, the budget consumed and an interpretation that states its limits.
"""
from __future__ import annotations

from decimal import Context, Decimal, ROUND_HALF_EVEN
import itertools
import math
import platform
import random
from typing import Mapping, Sequence

from .fitting import METHOD, fit_model, rank_fits
from .interface import (CAPS, INTERFACE_VERSION, Budget, BudgetExhausted, DetectionThreshold, Model, ModelError,
                        NoiseModel, Observation, Observations)

PACKAGE_VERSION = "0.1.0"
RNG = "python-mt19937-box-muller.v1"

NOT_PROOF = ("A better fit or higher rank is relative support under the stated noise assumption among these "
             "registered models only. It is not proof that any model is true and is not a Counterdex certificate.")


def _runtime() -> dict:
    return {"package": "counterdex-models", "version": PACKAGE_VERSION, "interface": INTERFACE_VERSION,
            "python": platform.python_version(), "implementation": platform.python_implementation(),
            "fit_method": METHOD, "provider_calls": 0}


def _envelope(analysis: str, inputs: dict, body: dict, budget: Budget, interpretation: str) -> dict:
    return {"schema_version": f"counterdex-models.{analysis}.v1", "analysis": analysis, "certification": "none",
            "execution": "completed" if budget.stopped is None else f"stopped:{budget.stopped}",
            "interpretation": interpretation, "inputs": inputs, **body, "budget": budget.to_dict(), "runtime": _runtime()}


def _check_params(model: Model, params: Mapping[str, float], path: str) -> dict:
    missing = set(model.parameter_names) - set(params)
    extra = set(params) - set(model.parameter_names)
    if missing or extra:
        raise ModelError("invalid_input", f"{model.id} needs exactly {sorted(model.parameter_names)}.", path)
    for p in model.parameters:
        v = params[p.name]
        if not (isinstance(v, (int, float)) and math.isfinite(v) and p.lower <= v <= p.upper):
            raise ModelError("invalid_input", f"{p.name} must be within [{p.lower}, {p.upper}] {p.unit}.", f"{path}/{p.name}")
    return {name: float(params[name]) for name in model.parameter_names}


def _check_times(times: Sequence[float], cap: int, path: str) -> list[float]:
    times = [float(t) for t in times]
    if not 1 <= len(times) <= cap or not all(math.isfinite(t) for t in times):
        raise ModelError("invalid_input", f"Supply 1-{cap} finite times.", path)
    if len(set(times)) != len(times):
        raise ModelError("invalid_input", "Times must be unique.", path)
    return times


def _check_models(models: Sequence[Model]) -> list[Model]:
    if not 1 <= len(models) <= CAPS["models_per_request"]:
        raise ModelError("invalid_input", f"Compare 1-{CAPS['models_per_request']} models.", "models")
    if len({m.id for m in models}) != len(models):
        raise ModelError("invalid_input", "Each model may appear once.", "models")
    return list(models)


def _inputs(observations: Observations, noise: NoiseModel, threshold: DetectionThreshold | None, **extra) -> dict:
    return {"observations": observations.to_dict(), "noise": noise.to_dict(),
            "detection_threshold": threshold.to_dict() if threshold else None, **extra}


# -- 1. bounded fitting of several models to the same observations -------------

def fit_models(models: Sequence[Model], observations: Observations, noise: NoiseModel,
               threshold: DetectionThreshold | None = None, *, starts: int = 8, max_iterations: int = 200,
               budget: Budget | None = None) -> dict:
    models, budget = _check_models(models), budget or Budget()
    fits = [fit_model(m, observations, noise, threshold, starts=starts, max_iterations=max_iterations, budget=budget)
            for m in models]
    ranking = rank_fits(fits)
    failed = [f["model"]["id"] for f in fits if f["status"] == "failed"]
    note = NOT_PROOF
    if failed:
        note += f" Fit failures ({', '.join(failed)}) are numerical outcomes, not evidence against those models."
    return _envelope("fit", _inputs(observations, noise, threshold, models=[m.id for m in models],
                                    fit={"starts": starts, "max_iterations": max_iterations}),
                     {"fits": fits, "ranking": ranking, "preferred_model": ranking[0]["model_id"] if ranking else None},
                     budget, note)


# -- 2. parameter-sensitivity sweeps --------------------------------------------

def _sweep_values(p, points: int, span: tuple[float, float] | None) -> list[float]:
    lo, hi = span or (p.lower, p.upper)
    if not p.lower <= lo < hi <= p.upper:
        raise ModelError("invalid_input", f"Sweep range for {p.name} must lie within its bounds.", f"ranges/{p.name}")
    if points == 1:
        return [lo]
    if p.scale == "log":
        a, b = math.log(lo), math.log(hi)
        return [math.exp(a + (b - a) * i / (points - 1)) for i in range(points)]
    return [lo + (hi - lo) * i / (points - 1) for i in range(points)]


def sensitivity(model: Model, params: Mapping[str, float], times: Sequence[float], *, points: int = 11,
                ranges: Mapping[str, tuple[float, float]] | None = None, budget: Budget | None = None) -> dict:
    """One-at-a-time sweeps and local log-sensitivities d ln y / d ln θ."""
    params, times, budget = _check_params(model, params, "parameters"), _check_times(times, CAPS["grid_times"], "times"), budget or Budget()
    if not 1 <= points <= CAPS["sweep_points"]:
        raise ModelError("invalid_input", f"points must be 1-{CAPS['sweep_points']}.", "points")
    sweeps, local = [], {}
    try:
        base = model.evaluate(params, times, budget)
        if base is None:
            raise ModelError("numerical_failure", "The reference parameters give non-finite predictions.", "parameters")
        for p in model.parameters:
            rows = []
            for v in _sweep_values(p, points, (ranges or {}).get(p.name)):
                pred = model.evaluate({**params, p.name: v}, times, budget)
                rows.append({"value": v, "predictions": pred, "status": "evaluated" if pred else "numerical_failure"})
            sweeps.append({"parameter": p.name, "unit": p.unit, "scale": p.scale, "points": rows})
            h = 1e-4 * abs(params[p.name]) or 1e-8
            up, down = min(params[p.name] + h, p.upper), max(params[p.name] - h, p.lower)
            hi = model.evaluate({**params, p.name: up}, times, budget)
            lo = model.evaluate({**params, p.name: down}, times, budget)
            local[p.name] = [None if hi is None or lo is None or y == 0 or params[p.name] == 0
                             else (a - b) / (up - down) * params[p.name] / y for a, b, y in zip(hi, lo, base)]
    except BudgetExhausted:
        base = base if "base" in locals() else None
    dominant = []
    for i, t in enumerate(times):
        values = {name: s[i] for name, s in local.items() if s[i] is not None}
        dominant.append({"time": t, "parameter": max(values, key=lambda n: (abs(values[n]), n)) if values else None})
    return _envelope("sensitivity", {"model": model.id, "parameters": params, "times": times, "points": points,
                                     "ranges": {k: list(v) for k, v in (ranges or {}).items()}},
                     {"model": model.describe(), "reference_predictions": base, "sweeps": sweeps,
                      "local_log_sensitivity": local, "most_sensitive_parameter": dominant},
                     budget, "Sensitivities describe this model's predictions near and across the supplied values. "
                             "They do not show that a parameter is identifiable from real data.")


# -- 3. comparison across noise assumptions and detection thresholds -------------

def compare_scenarios(models: Sequence[Model], observations: Observations,
                      scenarios: Sequence[tuple[str, NoiseModel, DetectionThreshold | None]], *, starts: int = 8,
                      max_iterations: int = 200, budget: Budget | None = None) -> dict:
    models, budget = _check_models(models), budget or Budget()
    if not 1 <= len(scenarios) <= CAPS["scenarios"]:
        raise ModelError("invalid_input", f"Supply 1-{CAPS['scenarios']} scenarios.", "scenarios")
    if len({s[0] for s in scenarios}) != len(scenarios):
        raise ModelError("invalid_input", "Scenario labels must be unique.", "scenarios")
    results = []
    for label, noise, threshold in scenarios:
        fits = [fit_model(m, observations, noise, threshold, starts=starts, max_iterations=max_iterations, budget=budget) for m in models]
        ranking = rank_fits(fits)
        results.append({"label": label, "noise": noise.to_dict(), "detection_threshold": threshold.to_dict() if threshold else None,
                        "censored_count": fits[0].get("censored_count"),
                        "preferred_model": ranking[0]["model_id"] if ranking else None, "ranking": ranking,
                        "fits": [{k: f.get(k) for k in ("status", "parameters", "parameters_at_bounds", "chi_square",
                                                         "reduced_chi_square", "aicc", "parameter_count", "failure")}
                                 | {"model_id": f["model"]["id"]} for f in fits]})
    preferred = {r["preferred_model"] for r in results}
    note = ("The preferred model is the same in every scenario." if len(preferred) == 1 else
            "The preferred model depends on the assumed noise or detection threshold, so the data alone do not settle the comparison.")
    return _envelope("scenarios", {"observations": observations.to_dict(), "models": [m.id for m in models],
                                   "fit": {"starts": starts, "max_iterations": max_iterations}},
                     {"scenarios": results, "preferred_model_stable": len(preferred) == 1}, budget, f"{note} {NOT_PROOF}")


# -- 4. reproducible, bounded Monte Carlo ---------------------------------------

def _gauss(rng: random.Random) -> float:
    u1, u2 = rng.random(), rng.random()
    return math.sqrt(-2.0 * math.log(1.0 - u1)) * math.cos(2.0 * math.pi * u2)


def _quantile(sorted_values: list[float], q: float) -> float:
    pos = q * (len(sorted_values) - 1)
    lo = math.floor(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    return sorted_values[lo] + (sorted_values[hi] - sorted_values[lo]) * (pos - lo)


def monte_carlo(truth: Model, truth_params: Mapping[str, float], candidates: Sequence[Model], times: Sequence[float],
                noise: NoiseModel, threshold: DetectionThreshold | None = None, *, replicates: int = 100, seed: int = 0,
                starts: int = 4, max_iterations: int = 100, budget: Budget | None = None) -> dict:
    """Simulate readings from a stated truth, refit every candidate, tally selection.

    Replicate ``i`` draws from its own stream seeded by ``(seed, i)``, so a
    stopped run's completed replicates equal those of a full run.
    """
    candidates, budget = _check_models(candidates), budget or Budget()
    truth_params = _check_params(truth, truth_params, "truth_parameters")
    times = _check_times(times, CAPS["observations"], "times")
    if not 1 <= replicates <= CAPS["monte_carlo_replicates"]:
        raise ModelError("invalid_input", f"replicates must be 1-{CAPS['monte_carlo_replicates']}.", "replicates")
    if type(seed) is not int or not 0 <= seed < 2 ** 32:
        raise ModelError("invalid_input", "seed must be an integer in [0, 2^32).", "seed")
    for m in candidates:
        if (m.time_unit, m.response_unit) != (truth.time_unit, truth.response_unit):
            raise ModelError("unit_mismatch", f"{m.id} and {truth.id} use different units.", "candidates")
    mean = truth.evaluate(truth_params, times, budget)
    if mean is None:
        raise ModelError("numerical_failure", "The truth parameters give non-finite predictions.", "truth_parameters")
    selected = {m.id: 0 for m in candidates}
    failures = {m.id: 0 for m in candidates}
    estimates = {m.id: {p: [] for p in m.parameter_names} for m in candidates}
    completed, all_censored = 0, 0
    for i in range(replicates):
        rng = random.Random(seed * 1_000_003 + i)
        rows = []
        for t, mu in zip(times, mean):
            y = mu + noise.sd(mu) * _gauss(rng)
            rows.append(Observation(t, None, True) if threshold and y < threshold.value else Observation(t, y))
        if all(r.censored for r in rows):
            all_censored += 1
            completed += 1
            continue
        data = Observations(truth.time_unit, truth.response_unit, tuple(rows), f"simulated replicate {i}")
        try:
            fits = [fit_model(m, data, noise, threshold, starts=starts, max_iterations=max_iterations, budget=budget) for m in candidates]
        except BudgetExhausted:
            break
        if budget.stopped:
            break
        for f in fits:
            if f["status"] == "failed":
                failures[f["model"]["id"]] += 1
            else:
                for name, value in f["parameters"].items():
                    estimates[f["model"]["id"]][name].append(value)
        ranking = rank_fits(fits)
        if ranking:
            selected[ranking[0]["model_id"]] += 1
        completed += 1
    summary = []
    for m in candidates:
        p = selected[m.id] / completed if completed else None
        params = {}
        for name, values in estimates[m.id].items():
            if values:
                s = sorted(values)
                params[name] = {"q05": _quantile(s, 0.05), "median": _quantile(s, 0.5), "q95": _quantile(s, 0.95),
                                "truth": truth_params.get(name) if m.id == truth.id else None}
        summary.append({"model_id": m.id, "parameter_count": len(m.parameters), "selected": selected[m.id],
                        "selection_frequency": p,
                        "selection_frequency_standard_error": math.sqrt(p * (1 - p) / completed) if completed else None,
                        "fit_failures": failures[m.id], "parameter_estimates": params})
    return _envelope("monte_carlo", {"truth_model": truth.id, "truth_parameters": truth_params,
                                     "candidates": [m.id for m in candidates], "times": times, "noise": noise.to_dict(),
                                     "detection_threshold": threshold.to_dict() if threshold else None,
                                     "replicates": replicates, "seed": seed, "rng": RNG,
                                     "fit": {"starts": starts, "max_iterations": max_iterations}},
                     {"replicates_completed": completed, "replicates_all_censored": all_censored, "candidates": summary},
                     budget, "Selection frequencies describe how often each registered model was preferred on data simulated "
                             "from the stated truth, noise and threshold. They are not the probability that a model is true "
                             "for real data and depend on every simulation assumption.")


# -- 5. ranking a supplied finite measurement grid ---------------------------------

def _rank_key(score: float) -> str:
    return "0" if score == 0 else str(Context(prec=12, rounding=ROUND_HALF_EVEN).create_decimal_from_float(score))


def rank_grid(hypotheses: Sequence[tuple[str, Model, Mapping[str, float]]], times: Sequence[float], noise: NoiseModel,
              threshold: DetectionThreshold | None = None, *, budget: Budget | None = None) -> dict:
    """Rank supplied times by the smallest pairwise predicted difference / noise SD.

    For each pair the noise SD is the larger of the two hypotheses' SDs at that
    time. Predictions below the detection threshold are read as the threshold,
    since such readings would only report "below threshold".
    """
    budget = budget or Budget()
    if not 2 <= len(hypotheses) <= CAPS["hypotheses"]:
        raise ModelError("invalid_input", f"Supply 2-{CAPS['hypotheses']} hypotheses.", "hypotheses")
    labels = [h[0] for h in hypotheses]
    if len(set(labels)) != len(labels):
        raise ModelError("invalid_input", "Hypothesis labels must be unique.", "hypotheses")
    units = {(h[1].time_unit, h[1].response_unit) for h in hypotheses}
    if len(units) != 1:
        raise ModelError("unit_mismatch", "All hypotheses must use the same units.", "hypotheses")
    times = _check_times(times, CAPS["grid_times"], "times")
    vectors = [(label, model, _check_params(model, params, f"hypotheses/{label}")) for label, model, params in hypotheses]
    predictions = {}
    for label, model, params in vectors:
        pred = model.evaluate(params, times, budget)
        if pred is None:
            raise ModelError("numerical_failure", f"Hypothesis {label} gives non-finite predictions.", f"hypotheses/{label}")
        predictions[label] = pred
    floor = threshold.value if threshold else None
    rows = []
    for i, t in enumerate(times):
        pairs = []
        for a, b in itertools.combinations(labels, 2):
            pa, pb = predictions[a][i], predictions[b][i]
            ea, eb = (max(pa, floor), max(pb, floor)) if floor is not None else (pa, pb)
            sd = max(noise.sd(ea), noise.sd(eb))
            below = [h for h, p in ((a, pa), (b, pb)) if floor is not None and p < floor]
            pairs.append({"pair": [a, b], "difference": abs(pa - pb), "detectable_difference": abs(ea - eb),
                          "noise_sd": sd, "standardized_difference": abs(ea - eb) / sd, "below_threshold": below})
        worst = min(pairs, key=lambda p: (p["standardized_difference"], p["pair"]))
        rows.append({"time": t, "predictions": {h: predictions[h][i] for h in labels},
                     "score": worst["standardized_difference"], "limiting_pair": worst["pair"], "pairs": pairs})
    ordered = sorted(rows, key=lambda r: (-Decimal(_rank_key(r["score"])), r["time"]))
    rank, previous = 0, None
    keys = [_rank_key(r["score"]) for r in ordered]
    for r, key in zip(ordered, keys):
        if key != previous:
            rank += 1
        r["rank"], r["tied"], previous = rank, keys.count(key) > 1, key
    return _envelope("grid_ranking", {"hypotheses": [{"label": l, "model": m.id, "parameters": p} for l, m, p in vectors],
                                      "times": times, "noise": noise.to_dict(),
                                      "detection_threshold": threshold.to_dict() if threshold else None},
                     {"score": "minimum over hypothesis pairs of |predicted difference| / noise SD",
                      "rows": rows, "ranked_times": [r["time"] for r in ordered]},
                     budget, "Ranks only the supplied times, for these fixed parameter vectors and this noise assumption. "
                             "Parameter uncertainty is ignored. It is not a globally optimal design and not certified "
                             "discrimination; a top-ranked time can still fail to tell the models apart.")
