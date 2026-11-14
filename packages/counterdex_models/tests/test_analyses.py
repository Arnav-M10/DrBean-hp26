import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from counterdex_models import (Budget, DetectionThreshold, ModelError, NoiseModel, Observation, Observations,  # noqa: E402
                               SINGLE_EXPONENTIAL as S, TWO_COMPONENT_MIXTURE as M, compare_scenarios, monte_carlo,
                               rank_grid, sensitivity)

TRUTH = {"A1": 6.0, "k1": 0.9, "A2": 2.0, "k2": 0.06}


class SensitivityTests(unittest.TestCase):
    def test_local_log_sensitivities_match_the_analytic_values(self):
        times = [0.5, 2.0, 10.0]
        result = sensitivity(S, {"A": 5.0, "k": 0.3}, times, points=5)
        for value in result["local_log_sensitivity"]["A"]:
            self.assertAlmostEqual(value, 1.0, places=6)
        for t, value in zip(times, result["local_log_sensitivity"]["k"]):
            self.assertAlmostEqual(value, -0.3 * t, places=5)
        self.assertEqual([d["parameter"] for d in result["most_sensitive_parameter"]], ["A", "A", "k"])

    def test_sweeps_cover_the_bounds_geometrically_for_log_parameters(self):
        result = sensitivity(S, {"A": 5.0, "k": 0.3}, [1.0], points=3)
        k = next(s for s in result["sweeps"] if s["parameter"] == "k")
        self.assertEqual([round(p["value"], 9) for p in k["points"]], [0.001, round(math.sqrt(0.001 * 10), 9), 10.0])
        with self.assertRaises(ModelError):
            sensitivity(S, {"A": 5.0, "k": 30.0}, [1.0])
        with self.assertRaises(ModelError):
            sensitivity(S, {"A": 5.0, "k": 0.3}, [1.0], ranges={"k": (0.0001, 1.0)})


class ScenarioTests(unittest.TestCase):
    def test_preferred_model_can_change_with_noise_and_threshold(self):
        times = [0.25, 0.5, 1, 1.5, 2, 3, 4, 6, 8, 12, 24]
        data = Observations("h", "mg/L", tuple(Observation(t, y) for t, y in zip(times, M.evaluate(TRUTH, times))))
        result = compare_scenarios([S, M], data, [("precise", NoiseModel(0.02, 0.03), None),
                                                  ("very noisy", NoiseModel(0.8, 0.5), None),
                                                  ("high threshold", NoiseModel(0.02, 0.03), DetectionThreshold(2.5))])
        preferred = {s["label"]: s["preferred_model"] for s in result["scenarios"]}
        self.assertEqual(preferred["precise"], M.id)
        self.assertEqual(preferred["very noisy"], S.id)
        self.assertEqual(preferred["high threshold"], S.id)
        self.assertFalse(result["preferred_model_stable"])
        self.assertGreater(result["scenarios"][2]["censored_count"], 0)
        with self.assertRaises(ModelError):
            compare_scenarios([S], data, [("same", NoiseModel(0.1), None), ("same", NoiseModel(0.2), None)])


class MonteCarloTests(unittest.TestCase):
    times = [0.25, 0.5, 1, 2, 4, 8]

    def run_mc(self, **kwargs):
        options = dict(replicates=20, seed=5, starts=2, max_iterations=60)
        options.update(kwargs)
        return monte_carlo(M, TRUTH, [S, M], self.times, NoiseModel(0.05, 0.08), DetectionThreshold(0.1), **options)

    def test_seeded_runs_are_reproducible_and_seed_sensitive(self):
        first, again, other = self.run_mc(), self.run_mc(), self.run_mc(seed=6)
        self.assertEqual(first["candidates"], again["candidates"])
        self.assertNotEqual(first["candidates"], other["candidates"])
        self.assertEqual(first["inputs"]["rng"], "python-mt19937-box-muller.v1")
        self.assertEqual(sum(c["selected"] for c in first["candidates"]), first["replicates_completed"])

    def test_completed_replicates_do_not_depend_on_the_requested_count(self):
        # Each replicate has its own stream, so the first 5 of 20 equal a run of 5.
        five = self.run_mc(replicates=5)
        stopped = self.run_mc(replicates=20, budget=Budget(max_evaluations=five["budget"]["evaluations_used"]))
        self.assertEqual(stopped["execution"], "stopped:evaluation_limit")
        self.assertEqual(stopped["replicates_completed"], 5)
        self.assertEqual(stopped["candidates"], five["candidates"])

    def test_bounds_are_enforced(self):
        with self.assertRaises(ModelError):
            self.run_mc(replicates=10_000)
        with self.assertRaises(ModelError):
            self.run_mc(seed=-1)


class GridRankingTests(unittest.TestCase):
    def test_scores_rank_ties_and_threshold(self):
        a = ("slow", S, {"A": 10.0, "k": 0.1})
        b = ("fast", S, {"A": 10.0, "k": 0.2})
        noise = NoiseModel(0.5)
        result = rank_grid([a, b], [1, 5, 10, 60], noise)
        rows = {r["time"]: r for r in result["rows"]}
        expected = abs(10 * math.exp(-0.5) - 10 * math.exp(-1.0)) / 0.5
        self.assertAlmostEqual(rows[5]["score"], expected)
        self.assertEqual(result["ranked_times"][0], 5)
        self.assertIn("not a globally optimal design", result["interpretation"])
        thresholded = rank_grid([a, b], [1, 5, 10, 60], noise, DetectionThreshold(1.0))
        late = next(r for r in thresholded["rows"] if r["time"] == 60)
        self.assertEqual(late["score"], 0.0)
        self.assertEqual(late["pairs"][0]["below_threshold"], ["slow", "fast"])

    def test_identical_hypotheses_tie_and_validation(self):
        same = rank_grid([("x", S, {"A": 1.0, "k": 0.1}), ("y", S, {"A": 1.0, "k": 0.1})], [1, 2], NoiseModel(0.1))
        self.assertTrue(all(r["rank"] == 1 and r["tied"] for r in same["rows"]))
        with self.assertRaises(ModelError):
            rank_grid([("x", S, {"A": 1.0, "k": 0.1})], [1], NoiseModel(0.1))
        with self.assertRaises(ModelError):
            rank_grid([("x", S, {"A": 1.0, "k": 0.1}), ("y", S, {"A": 1.0, "k": 0.1})], [1, 1], NoiseModel(0.1))

    def test_multiple_hypotheses_use_the_least_separated_pair(self):
        hyps = [("a", S, {"A": 10.0, "k": 0.1}), ("b", S, {"A": 10.0, "k": 0.11}), ("c", M, TRUTH)]
        result = rank_grid(hyps, [2.0], NoiseModel(0.1))
        row = result["rows"][0]
        self.assertEqual(row["score"], min(p["standardized_difference"] for p in row["pairs"]))
        self.assertEqual(row["limiting_pair"], ["a", "b"])


if __name__ == "__main__":
    unittest.main()
