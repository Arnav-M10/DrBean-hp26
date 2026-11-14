"""Run every example request and print what each analysis shows.

    python3.11 packages/counterdex_models/examples/demo.py

Uses only the public synthetic models and readings. No network, no provider.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from counterdex_models import default_registry, run_request  # noqa: E402


def load(name: str) -> dict:
    return json.loads((HERE / "requests" / f"{name}.request.json").read_text(encoding="utf-8"))


def short(model_id: str) -> str:
    return {"public.single-exponential": "single exponential", "public.two-exponential-mixture": "two-component mixture"}.get(model_id, model_id)


def ranking_line(ranking: list[dict]) -> str:
    return "; ".join(f"{short(r['model_id'])} Δ{ {'aicc': 'AICc', 'aic': 'AIC'}[r['criterion']]} {r['delta']:.1f} (weight {r['relative_weight']:.2f})" for r in ranking)


def main() -> None:
    registry = default_registry()
    results = {name: run_request(load(name), registry) for name in
               ("fit_early", "fit_full", "scenarios", "sensitivity", "grid_ranking", "monte_carlo_early", "monte_carlo_early_plus_8h")}
    print("Synthetic readings drawn from a two-component mixture (public example, not real data).\n")

    early = results["fit_early"]
    print("1. Fit both models to the early readings (t ≤ 4 h)")
    for f in early["fits"]:
        bound = f" — at bound: {', '.join(f['parameters_at_bounds'])}" if f["parameters_at_bounds"] else ""
        print(f"   {short(f['model']['id'])}: {f['parameter_count']} parameters, χ² {f['chi_square']:.2f}, "
              f"{', '.join(f'{k}={v:.3g}' for k, v in f['parameters'].items())}{bound}")
    print(f"   Ranking: {ranking_line(early['ranking'])}")
    print("   The mixture fits more closely, yet the single exponential is preferred: the early readings cannot")
    print("   support two components. The data were in fact drawn from the mixture — preference is not truth.\n")

    grid = results["grid_ranking"]
    print("2. Rank the supplied later times for telling the two early fits apart (noise SD, threshold 0.1 mg/L)")
    for row in sorted(grid["rows"], key=lambda r: (r["rank"], r["time"]))[:5]:
        print(f"   rank {row['rank']}: {row['time']:g} h, predicted difference / noise SD = {row['score']:.2f}")
    print("   Only these times and these two vectors are ranked; this is not an optimal or certified design.\n")

    a, b = results["monte_carlo_early"], results["monte_carlo_early_plus_8h"]
    freq = lambda r: next(c for c in r["candidates"] if c["model_id"] == "public.two-exponential-mixture")["selection_frequency"]
    print("3. Monte Carlo (200 seeded replicates) if the stated mixture were true")
    print(f"   Early design: mixture preferred in {freq(a):.0%} of replicates")
    print(f"   Early design plus one 8 h reading: mixture preferred in {freq(b):.0%}")
    print("   These frequencies hold only under the simulated truth, noise and threshold.\n")

    full = results["fit_full"]
    print("4. All readings (to 24 h)")
    print(f"   Ranking: {ranking_line(full['ranking'])}\n")

    print("5. The same readings under different noise and threshold assumptions")
    for s in results["scenarios"]["scenarios"]:
        print(f"   {s['label']}: censored {s['censored_count']}, preferred {short(s['preferred_model'])} — {ranking_line(s['ranking'])}")
    print(f"   {results['scenarios']['interpretation'].split('. ')[0]}.\n")

    sens = results["sensitivity"]
    print("6. Which mixture parameter moves the prediction most at each time (local log-sensitivity)")
    print("   " + ", ".join(f"{d['time']:g} h: {d['parameter']}" for d in sens["most_sensitive_parameter"]))

    print("\nEvery result above is numerical analysis (certification: none) with zero provider calls.")
    used = sum(r["budget"]["evaluations_used"] for r in results.values())
    print(f"Model evaluations used: {used:,}. Result digests:")
    for name, r in results.items():
        print(f"   {name}: {r['result_sha256'][:16]}…")


if __name__ == "__main__":
    main()
