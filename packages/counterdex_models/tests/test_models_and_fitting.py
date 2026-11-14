import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from counterdex_models import (Budget, BudgetExhausted, DetectionThreshold, Model, ModelError, ModelRegistry,  # noqa: E402
                               NoiseModel, Observation, Observations, Parameter, SINGLE_EXPONENTIAL,
                               TWO_COMPONENT_MIXTURE, default_registry, fit_model, fit_models, rank_fits)

NOISE = NoiseModel(0.01, 0.0)


def observations(model, params, times, unit=("h", "mg/L")):
    return Observations(*unit, tuple(Observation(t, v) for t, v in zip(times, model.evaluate(params, times))))


class InterfaceTests(unittest.TestCase):
    def test_model_definitions_are_validated(self):
        with self.assertRaises(ModelError):
            Parameter("k", "1/h", 0.0, 1.0, "log")
        with self.assertRaises(ModelError):
            Parameter("k", "1/h", 2.0, 1.0)
        with self.assertRaises(ModelError):
            Model("Bad Id", 1, "t", "h", "mg/L", (Parameter("a", "u", 0, 1),), lambda p, t: t)
        with self.assertRaises(ModelError):
            Model("ok.model", 1, "t", "h", "mg/L", (Parameter("a", "u", 0, 1), Parameter("a", "u", 0, 1)), lambda p, t: t)

    def test_registry_is_code_only_and_refuses_duplicates_and_unknown_ids(self):
        registry = default_registry()
        self.assertEqual(registry.ids(), ["public.single-exponential", "public.two-exponential-mixture"])
        with self.assertRaises(ModelError) as caught:
            registry.register(SINGLE_EXPONENTIAL)
        self.assertEqual(caught.exception.code, "duplicate_model")
        with self.assertRaises(ModelError) as caught:
            registry.get("plasma.not-registered")
        self.assertEqual(caught.exception.code, "unknown_model")
        with self.assertRaises(ModelError):
            ModelRegistry().register({"id": "dict.is.not.a.model"})

    def test_noise_threshold_and_units_are_distinct_validated_inputs(self):
        with self.assertRaises(ModelError):
            NoiseModel(0, 0)
        with self.assertRaises(ModelError):
            DetectionThreshold(0)
        self.assertAlmostEqual(NoiseModel(0.3, 0.1).sd(4.0), 0.5)
        data = Observations("h", "mg/L", (Observation(1, None, True),))
        with self.assertRaises(ModelError):
            data.apply_threshold(None)
        with self.assertRaises(ModelError) as caught:
            fit_model(SINGLE_EXPONENTIAL, Observations("min", "mg/L", (Observation(1, 2.0),)), NOISE)
        self.assertEqual(caught.exception.code, "unit_mismatch")

    def test_non_finite_predictions_are_failures_and_wrong_lengths_are_model_errors(self):
        nan = Model("test.nan", 1, "NaN", "h", "mg/L", (Parameter("a", "mg/L", 0, 1),), lambda p, t: [math.nan] * len(t))
        self.assertIsNone(nan.evaluate({"a": 0.5}, [1.0]))
        short = Model("test.short", 1, "Short", "h", "mg/L", (Parameter("a", "mg/L", 0, 1),), lambda p, t: [])
        with self.assertRaises(ModelError):
            short.evaluate({"a": 0.5}, [1.0])

    def test_budget_stops_deterministically_on_evaluations_and_on_the_clock(self):
        budget = Budget(max_evaluations=10)
        budget.spend(10)
        with self.assertRaises(BudgetExhausted):
            budget.spend(1)
        self.assertEqual(budget.stopped, "evaluation_limit")
        ticks = iter([0.0, 0.5, 5.0])
        clocked = Budget(wall_seconds=1, clock=lambda: next(ticks))
        clocked.spend(1)
        with self.assertRaises(BudgetExhausted):
            clocked.spend(1)
        self.assertEqual(clocked.stopped, "wall_clock_limit")
        with self.assertRaises(ModelError):
            Budget(max_evaluations=10 ** 9)


class FittingTests(unittest.TestCase):
    times = [0.25, 0.5, 1, 2, 3, 4, 6, 8, 12, 16, 24]

    def test_noiseless_single_exponential_is_recovered(self):
        fit = fit_model(SINGLE_EXPONENTIAL, observations(SINGLE_EXPONENTIAL, {"A": 8.0, "k": 0.25}, self.times), NOISE)
        self.assertEqual(fit["status"], "fitted")
        self.assertAlmostEqual(fit["parameters"]["A"], 8.0, places=6)
        self.assertAlmostEqual(fit["parameters"]["k"], 0.25, places=8)
        self.assertLess(fit["chi_square"], 1e-10)
        self.assertEqual(fit["parameter_count"], 2)
        self.assertEqual(len(fit["rows"]), len(self.times))
        self.assertIsNotNone(fit["local_standard_errors"])

    def test_mixture_is_recovered_in_canonical_component_order(self):
        truth = {"A1": 6.0, "k1": 0.9, "A2": 2.0, "k2": 0.06}
        data = observations(TWO_COMPONENT_MIXTURE, truth, self.times)
        swapped = {"A1": 2.0, "k1": 0.06, "A2": 6.0, "k2": 0.9}
        fit = fit_model(TWO_COMPONENT_MIXTURE, data, NOISE, initial=swapped)
        for name, value in truth.items():
            self.assertAlmostEqual(fit["parameters"][name], value, delta=1e-5 * value)
        self.assertGreaterEqual(fit["parameters"]["k1"], fit["parameters"]["k2"])

    def test_fit_failure_is_reported_and_other_models_still_rank(self):
        broken = Model("test.always-nan", 1, "Broken", "h", "mg/L", (Parameter("a", "mg/L", 0.1, 1),), lambda p, t: [math.nan] * len(t))
        data = observations(SINGLE_EXPONENTIAL, {"A": 8.0, "k": 0.25}, self.times)
        result = fit_models([broken, SINGLE_EXPONENTIAL], data, NOISE, starts=2)
        failed = result["fits"][0]
        self.assertEqual((failed["status"], failed["failure"]), ("failed", "no_finite_prediction"))
        self.assertEqual([r["model_id"] for r in result["ranking"]], ["public.single-exponential"])
        self.assertIn("not evidence against", result["interpretation"])

    def test_censored_readings_use_the_threshold_not_a_value(self):
        truth = {"A": 8.0, "k": 0.25}
        data = observations(SINGLE_EXPONENTIAL, truth, self.times)
        fit = fit_model(SINGLE_EXPONENTIAL, data, NoiseModel(0.01, 0.02), DetectionThreshold(0.5))
        censored = [r for r in fit["rows"] if r["censored"]]
        self.assertEqual([r["time"] for r in censored], [12, 16, 24])
        self.assertTrue(all(r["observed"] is None and r["residual"] is None for r in censored))
        self.assertAlmostEqual(fit["parameters"]["k"], 0.25, places=4)
        self.assertIsNone(fit["local_standard_errors"])  # curvature SEs are only offered without censoring

    def test_parameters_pinned_at_a_bound_are_flagged(self):
        fast = Model("test.bounded", 1, "Bounded", "h", "mg/L", (Parameter("A", "mg/L", 0.1, 100, "log"), Parameter("k", "1/h", 0.01, 0.1, "log")),
                     SINGLE_EXPONENTIAL.predict)
        fit = fit_model(fast, observations(SINGLE_EXPONENTIAL, {"A": 8.0, "k": 0.5}, self.times), NOISE)
        self.assertIn("k", fit["parameters_at_bounds"])

    def test_fixed_parameters_are_held(self):
        fit = fit_model(SINGLE_EXPONENTIAL, observations(SINGLE_EXPONENTIAL, {"A": 8.0, "k": 0.25}, self.times), NOISE, fixed={"A": 7.0})
        self.assertEqual(fit["parameters"]["A"], 7.0)
        self.assertEqual(fit["parameter_count"], 1)

    def test_information_criteria_and_weights(self):
        data = observations(TWO_COMPONENT_MIXTURE, {"A1": 6.0, "k1": 0.9, "A2": 2.0, "k2": 0.06}, self.times)
        fits = [fit_model(m, data, NoiseModel(0.02, 0.03)) for m in (SINGLE_EXPONENTIAL, TWO_COMPONENT_MIXTURE)]
        ranking = rank_fits(fits)
        self.assertEqual(ranking[0]["model_id"], "public.two-exponential-mixture")
        self.assertAlmostEqual(sum(r["relative_weight"] for r in ranking), 1.0)
        for f in fits:
            n, k = f["observation_count"], f["parameter_count"]
            self.assertAlmostEqual(f["aicc"] - f["aic"], 2 * k * (k + 1) / (n - k - 1))
        tiny = observations(SINGLE_EXPONENTIAL, {"A": 8.0, "k": 0.25}, [1, 2, 3])
        three = [fit_model(m, tiny, NOISE) for m in (SINGLE_EXPONENTIAL, TWO_COMPONENT_MIXTURE)]
        self.assertIsNone(three[1]["aicc"])
        self.assertEqual(rank_fits(three)[0]["criterion"], "aic")

    def test_fits_are_deterministic(self):
        data = observations(TWO_COMPONENT_MIXTURE, {"A1": 6.0, "k1": 0.9, "A2": 2.0, "k2": 0.06}, self.times)
        first = fit_models([SINGLE_EXPONENTIAL, TWO_COMPONENT_MIXTURE], data, NoiseModel(0.02, 0.03))
        second = fit_models([SINGLE_EXPONENTIAL, TWO_COMPONENT_MIXTURE], data, NoiseModel(0.02, 0.03))
        self.assertEqual(first["fits"], second["fits"])

    def test_evaluation_cap_stops_fitting_without_raising(self):
        data = observations(SINGLE_EXPONENTIAL, {"A": 8.0, "k": 0.25}, self.times)
        result = fit_models([SINGLE_EXPONENTIAL, TWO_COMPONENT_MIXTURE], data, NOISE, budget=Budget(max_evaluations=200))
        self.assertEqual(result["execution"], "stopped:evaluation_limit")
        self.assertTrue(all(f["stopped"] == "evaluation_limit" for f in result["fits"]))


if __name__ == "__main__":
    unittest.main()
