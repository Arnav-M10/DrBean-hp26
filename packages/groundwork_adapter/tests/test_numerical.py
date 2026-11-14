"""Analytic and operational controls for the numerical diagnostic lane."""
from copy import deepcopy
from dataclasses import replace
from fractions import Fraction
import math
import unittest

from counterdex.errors import AdapterError
from counterdex.exact import canonical_bytes
from counterdex.models import CHECKED_POLICY, NUMERICAL_POLICY, normalize_design, normalize_problem
from counterdex.numerical import ExecutionContext, compare_grid


def problem_payload():
    return {"schema_version": "groundwork.problem.v1", "model": "two_rate_kinetics_v1", "model_revision": 1,
            "units": {"time": "h", "concentration": "mg/L", "rate": "1/h"},
            "initial_conditions": {"x": "1", "c": "0"}, "time_origin": "test experiment start",
            "dataset_kind": "hypothetical", "domain": {"A": ["1", "10"], "ke": ["0.5", "1.5"], "ka": ["1.6", "3"]},
            "claim": {"parameter": "ke", "interval": ["0.8", "1.2"]},
            "observations": [{"id": f"row-{i}", "time": str(i), "value": "1", "allowance": "100",
                              "included": True, "allowance_origin": "arithmetic control", "origin": "hypothetical",
                              "notes": "", "provenance": "new constructed fixture"} for i in range(3)],
            "notes": "", "provenance": "new constructed fixture; no compatibility asserted"}


def design_payload(problem, times=("1", "2", "3")):
    return {"schema_version": "groundwork.design.v1", "problem_digest": problem.digest, "scenario_id": "test-scenario",
            "candidates": [{"id": key, "problem_digest": problem.digest, "parameters": {"A": a, "ke": "1", "ka": "2"},
                            "source_artifact_digest": None} for key, a in (("first", "4"), ("second", "8"))],
            "grid": [{"time": t, "feasible": True, "reason": "reviewed synthetic time"} for t in times],
            "time_origin": problem.time_origin, "observable": "c", "future_allowance": "0.1",
            "allowance_origin": {"kind": "hypothetical", "description": "explicit synthetic allowance"},
            "requested_tier": "numerical_guidance", "horizon_policy": {"allow_construction": False, "allow_extension": False, "maximum_horizon": "3"},
            "numerical_policy": NUMERICAL_POLICY, "checked_policy": CHECKED_POLICY,
            "limits": {"wall_seconds": 120, "max_times": 64, "max_constructions": 0, "max_pair_verifications": 0,
                       "max_bundle_bytes": 4194304, "max_certificate_bytes": 2097152}}


class NumericalTests(unittest.TestCase):
    def setUp(self):
        self.problem = normalize_problem(problem_payload())

    def run_grid(self, payload, context=None):
        return compare_grid(self.problem, normalize_design(payload, self.problem), context)

    def test_analytic_initial_and_half_life_values(self):
        # exp(-ln2)=1/2, exp(-2ln2)=1/4, hence A=4 predicts 1.
        payload = design_payload(self.problem, ("0", "0.6931471805599453"))
        report = self.run_grid(payload)
        first, second = report["rows"]
        self.assertEqual(first["predictions"], {"first": "0.0", "second": "0.0"})
        self.assertAlmostEqual(float(second["predictions"]["first"]), 1, places=14)
        self.assertAlmostEqual(float(second["predictions"]["second"]), 2, places=14)
        self.assertAlmostEqual(float(second["score_approximation"]), 10, places=13)
        self.assertEqual(report["selected_time"], second["time"])
        self.assertEqual(report["outcome"], "numerical_guidance")
        self.assertFalse(report["partial"])
        canonical_bytes(report)  # Approximate diagnostics must not be JSON floats.

    def test_zero_gap_is_useful_empty_result(self):
        report = self.run_grid(design_payload(self.problem, ("0",)))
        self.assertEqual(report["outcome"], "no_useful_suggestion")
        self.assertIsNone(report["selected_time"])
        self.assertEqual(report["ranked_times"], ["0/1"])

    def test_cancel_after_one_preserves_every_time(self):
        calls = []
        def cancelled():
            calls.append(1)
            return len(calls) >= 2
        context = ExecutionContext(cancelled=cancelled, clock=lambda: 0)
        report = self.run_grid(design_payload(self.problem), context)
        self.assertEqual([r["status"] for r in report["rows"]], ["evaluated", "skipped", "skipped"])
        self.assertEqual(report["execution"], "cancelled")
        self.assertTrue(report["partial"])
        self.assertEqual(len(calls), 2)
        self.assertEqual(report["ranked_times"], ["1/1"])
        self.assertEqual(report["selected_time"], "1/1")

    def test_smaller_request_wall_limit_wins(self):
        times = iter((0, 0, 2))
        context = ExecutionContext(wall_seconds=120, clock=lambda: next(times))
        payload = design_payload(self.problem)
        payload["limits"]["wall_seconds"] = 1
        report = self.run_grid(payload, context)
        self.assertEqual(report["execution"], "interrupted")
        self.assertEqual(report["evaluated_count"], 1)
        self.assertEqual(report["rows"][1]["reason_code"], "resource_exhaustion")

    def test_infeasibility_is_visible_and_not_partial(self):
        payload = design_payload(self.problem)
        payload["grid"][1].update(feasible=False, reason="instrument unavailable")
        report = self.run_grid(payload)
        self.assertEqual(report["rows"][1]["reason_code"], "infeasible_time")
        self.assertEqual(report["rows"][1]["feasibility_reason"], "instrument unavailable")
        self.assertEqual(report["evaluated_count"], 2)
        self.assertFalse(report["partial"])

    def test_exp_underflow_is_failed_and_never_a_fake_zero(self):
        report = self.run_grid(design_payload(self.problem, ("1", "1000")))
        self.assertEqual(report["rows"][1]["status"], "failed")
        self.assertEqual(report["rows"][1]["reason_code"], "numerical_range_limitation")
        self.assertIsNone(report["rows"][1]["predictions"]["first"])
        self.assertTrue(report["partial"])
        self.assertEqual(report["ranked_times"], ["1/1"])

    def test_score_overflow_is_reported(self):
        payload = design_payload(self.problem, ("1",))
        payload["future_allowance"] = "1/" + "1" + "0" * 400
        report = self.run_grid(payload)
        self.assertEqual(report["outcome"], "unavailable")
        self.assertEqual(report["rows"][0]["reason_code"], "numerical_range_limitation")

    def test_display_score_ties_are_explicit_and_use_exact_time(self):
        payload = design_payload(self.problem, ("1.00000000000001", "1"))
        report = self.run_grid(payload)
        self.assertEqual(report["rows"][0]["ranking_score"], report["rows"][1]["ranking_score"])
        self.assertTrue(all(row["tied"] for row in report["rows"]))
        self.assertEqual([r["rank"] for r in report["rows"]], [1, 1])
        self.assertEqual(report["selected_time"], "1/1")

    def test_candidate_permutation_keeps_identity_and_predictions_together(self):
        payload = design_payload(self.problem)
        report1 = self.run_grid(payload)
        payload["candidates"].reverse()
        report2 = self.run_grid(payload)
        self.assertEqual(report1, report2)

    def test_no_mutation_of_frozen_input_or_historical_rows(self):
        payload = design_payload(self.problem)
        original = deepcopy(payload)
        historical = self.problem.to_payload()
        self.run_grid(payload)
        self.assertEqual(payload, original)
        self.assertEqual(self.problem.to_payload(), historical)

    def test_directly_constructed_bad_dataclass_is_revalidated(self):
        design = normalize_design(design_payload(self.problem), self.problem)
        with self.assertRaises(AdapterError):
            compare_grid(self.problem, replace(design, future_allowance=Fraction(-1)))
        candidate = replace(design.candidates[0], parameters=design.candidates[0].parameters + (Fraction(5),))
        with self.assertRaises(AdapterError):
            compare_grid(self.problem, replace(design, candidates=(candidate, design.candidates[1])))

    def test_close_rates_do_not_cancel_to_zero(self):
        pp = problem_payload()
        scale = 10 ** 20
        pp["domain"]["ke"] = ["0.5", "1"]
        pp["domain"]["ka"] = [f"{scale + 1}/{scale}", "2"]
        problem = normalize_problem(pp)
        payload = design_payload(problem, ("1",))
        for candidate in payload["candidates"]:
            candidate["parameters"]["ka"] = f"{scale + 2}/{scale}"
        report = compare_grid(problem, normalize_design(payload, problem))
        prediction = float(report["rows"][0]["predictions"]["first"])
        self.assertGreater(prediction, 0)
        # For tiny u, 1-exp(-u) ~ u; relative error here is far below 1e-14.
        self.assertAlmostEqual(prediction / (4 * math.exp(-1) * 2e-20), 1, places=14)

    def test_context_admission_and_latched_stop(self):
        for invalid in (0, -1, 121, float("nan"), float("inf"), True):
            with self.subTest(value=invalid), self.assertRaises(AdapterError):
                ExecutionContext(wall_seconds=invalid)
        flags = iter((True, False))
        context = ExecutionContext(wall_seconds=0.01, cancelled=lambda: next(flags), clock=lambda: 0)
        self.assertEqual(context.stop_reason(), "cancelled")
        self.assertEqual(context.stop_reason(), "cancelled")


if __name__ == "__main__":
    unittest.main()
