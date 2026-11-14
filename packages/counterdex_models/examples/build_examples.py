"""Regenerate the public synthetic readings and every example request.

    python3.11 packages/counterdex_models/examples/build_examples.py [out_dir]

Readings are drawn once from a stated two-component mixture with a fixed seed
and rounded to 3 decimals. They are synthetic and describe no real compound.
The grid-ranking hypotheses are the parameter vectors fitted to the early
readings, rounded to 6 significant figures.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from counterdex_models import (Budget, NoiseModel, Observation, Observations, SINGLE_EXPONENTIAL,  # noqa: E402
                               TWO_COMPONENT_MIXTURE, fit_models)

SEED = 20261114
TRUTH = {"A1": 6.0, "k1": 0.9, "A2": 2.0, "k2": 0.06}
TIMES = [0.25, 0.5, 1, 1.5, 2, 3, 4, 6, 8, 12, 24]
EARLY = [t for t in TIMES if t <= 4]
NOISE = {"absolute_sd": 0.05, "relative_sd": 0.08, "label": "Stated synthetic assay noise (standard deviation)"}
THRESHOLD = {"value": 0.1, "label": "Stated synthetic detection threshold"}
CANDIDATE_TIMES = [6, 8, 10, 12, 16, 24, 36, 48]
REQUEST = "counterdex-models.request.v1"
MODELS = ["public.single-exponential", "public.two-exponential-mixture"]


def readings() -> dict:
    rng = random.Random(SEED)
    noise = NoiseModel(NOISE["absolute_sd"], NOISE["relative_sd"])
    rows = []
    for t, mu in zip(TIMES, TWO_COMPONENT_MIXTURE.evaluate(TRUTH, TIMES)):
        u1, u2 = rng.random(), rng.random()
        z = math.sqrt(-2 * math.log(1 - u1)) * math.cos(2 * math.pi * u2)
        rows.append({"time": t, "value": f"{mu + noise.sd(mu) * z:.3f}"})
    return {"time_unit": "h", "response_unit": "mg/L", "rows": rows,
            "provenance": f"Public synthetic example: two-component mixture {TRUTH}, noise {NOISE['absolute_sd']} mg/L "
                          f"+ {NOISE['relative_sd']}·y SD, seed {SEED}, rounded to 3 decimals. Not real data."}


def _sig(x: float) -> float:
    return float(f"{x:.6g}")


def build(out: Path) -> list[Path]:
    data = readings()
    early = {**data, "rows": [r for r in data["rows"] if r["time"] <= 4],
             "provenance": data["provenance"] + " Early readings (t ≤ 4 h) only."}
    obs = Observations("h", "mg/L", tuple(Observation(r["time"], float(r["value"])) for r in early["rows"]))
    fitted = fit_models([SINGLE_EXPONENTIAL, TWO_COMPONENT_MIXTURE], obs, NoiseModel(NOISE["absolute_sd"], NOISE["relative_sd"]),
                        budget=Budget())
    vectors = {f["model"]["id"]: {k: _sig(v) for k, v in f["parameters"].items()} for f in fitted["fits"]}
    files = {
        "synthetic_readings.json": data,
        "fit_early.request.json": {"schema_version": REQUEST, "analysis": "fit", "observations": early, "models": MODELS,
                                   "noise": NOISE, "fit": {"starts": 8, "max_iterations": 200}},
        "fit_full.request.json": {"schema_version": REQUEST, "analysis": "fit", "observations": data, "models": MODELS,
                                  "noise": NOISE, "detection_threshold": THRESHOLD},
        "scenarios.request.json": {"schema_version": REQUEST, "analysis": "scenarios", "observations": data, "models": MODELS,
                                   "scenarios": [
                                       {"label": "stated assay", "noise": NOISE},
                                       {"label": "noisier assay", "noise": {"absolute_sd": 0.3, "relative_sd": 0.3}},
                                       {"label": "stated noise, threshold 0.6 mg/L", "noise": NOISE, "detection_threshold": {"value": 0.6}},
                                       {"label": "stated noise, threshold 1.5 mg/L", "noise": NOISE, "detection_threshold": {"value": 1.5}}]},
        "sensitivity.request.json": {"schema_version": REQUEST, "analysis": "sensitivity", "model": "public.two-exponential-mixture",
                                     "parameters": TRUTH, "times": TIMES + [36, 48], "points": 9},
        "grid_ranking.request.json": {"schema_version": REQUEST, "analysis": "grid_ranking",
                                      "note": "Hypotheses are the vectors fitted to the early readings (fit_early).",
                                      "hypotheses": [{"label": "single exponential (early fit)", "model": MODELS[0], "parameters": vectors[MODELS[0]]},
                                                     {"label": "mixture (early fit)", "model": MODELS[1], "parameters": vectors[MODELS[1]]}],
                                      "times": CANDIDATE_TIMES, "noise": NOISE, "detection_threshold": THRESHOLD},
        "monte_carlo_early.request.json": {"schema_version": REQUEST, "analysis": "monte_carlo",
                                           "truth": {"model": MODELS[1], "parameters": TRUTH}, "candidates": MODELS,
                                           "times": EARLY, "noise": NOISE, "detection_threshold": THRESHOLD,
                                           "replicates": 200, "seed": 1, "fit": {"starts": 4, "max_iterations": 100}},
        "monte_carlo_early_plus_8h.request.json": {"schema_version": REQUEST, "analysis": "monte_carlo",
                                                   "truth": {"model": MODELS[1], "parameters": TRUTH}, "candidates": MODELS,
                                                   "times": EARLY + [8], "noise": NOISE, "detection_threshold": THRESHOLD,
                                                   "replicates": 200, "seed": 1, "fit": {"starts": 4, "max_iterations": 100}},
    }
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for name, value in files.items():
        path = out / ("requests" if name.endswith(".request.json") else "") / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        written.append(path)
    return written


if __name__ == "__main__":
    for path in build(Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent):
        print(path)
