"""Finite discovery controls: exact acceptance is a separate operation."""
from copy import deepcopy
from dataclasses import replace
from decimal import Context, localcontext
from fractions import Fraction
from unittest.mock import patch
import unittest

from counterdex.errors import AdapterError
from counterdex.exact import canonical_bytes, strict_json_loads
from counterdex.historical import evaluate_historical_candidate
from counterdex.models import normalize_problem
from counterdex.resource import ExecutionContext
from counterdex.search import SearchSettings, normalize_search_settings, search_candidates


def hero_payload():
    """Synthetic reviewed observations, never production candidate vectors."""
    return {"schema_version": "groundwork.problem.v1", "model": "two_rate_kinetics_v1", "model_revision": 1,
            "units": {"time": "h", "concentration": "mg/L", "rate": "1/h"},
            "initial_conditions": {"x": "1", "c": "0"}, "time_origin": "synthetic single dose at elapsed zero",
            "dataset_kind": "hypothetical",
            "domain": {"A": ["0.001", "30"], "ke": ["0.015", "0.35"], "ka": ["0.4", "8"]},
            "claim": {"parameter": "ke", "interval": ["0.10", "0.17"]},
            "observations": [
                {"id": f"synthetic-{index}", "time": time, "value": value, "allowance": "0.50",
                 "included": True, "allowance_origin": "reviewed synthetic hard allowance",
                 "origin": "hypothetical", "notes": "", "provenance": "synthetic decision-loop control"}
                for index, (time, value) in enumerate(zip(
                    ("0.25", "0.5", "1", "2", "4"), ("4.80", "7.20", "8.00", "6.80", "5.70")))],
            "notes": "Clearly synthetic model experiment; not experimentally collected.",
            "provenance": "synthetic integration control"}


def broad_payload():
    payload = hero_payload()
    payload["domain"] = {"A": ["1", "10"], "ke": ["1", "2"], "ka": ["3", "4"]}
    payload["claim"]["interval"] = ["1", "2"]
    payload["observations"] = payload["observations"][:3]
    for index, row in enumerate(payload["observations"]):
        row.update(time=str(index), value="0", allowance="100")
    return payload


def small_settings(**changes):
    return replace(SearchSettings(), ke_points=2, ka_points=2, **changes)


class SearchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hero = normalize_problem(hero_payload())
        cls.hero_result = search_candidates(cls.hero)

    def test_real_hero_discovery_and_independent_exact_acceptance(self):
        result = self.hero_result
        self.assertEqual(result.report["attempted_count"], 128 * 128)
        self.assertEqual(result.report["evaluated_count"], 128 * 128)
        self.assertEqual(result.report["execution"], "completed")
        self.assertFalse(result.report["partial"])
        self.assertEqual(len(result.candidates), 32)
        self.assertFalse(result.candidates[0].is_outside(self.hero))
        self.assertTrue(result.candidates[1].is_outside(self.hero))
        inside = evaluate_historical_candidate(self.hero, result.candidates[0])
        outside = evaluate_historical_candidate(self.hero, result.candidates[1])
        self.assertEqual(inside["verification"], "valid")
        self.assertEqual(outside["verification"], "valid")
        self.assertFalse(inside["is_counterexample"])
        self.assertTrue(outside["is_counterexample"])
        self.assertGreater(result.report["feasible_count"], result.report["retained_count"])

    def test_producer_never_invokes_exact_verification(self):
        problem = normalize_problem(broad_payload())
        with patch("counterdex.historical.evaluate_historical_candidate", side_effect=AssertionError("producer crossed proof boundary")):
            result = search_candidates(problem, settings=small_settings())
        self.assertEqual(result.report["outcome"], "numerical_candidates")
        self.assertNotIn("verification", result.report)
        self.assertNotIn("is_counterexample", result.report)
        self.assertTrue(all(type(value) is Fraction for c in result.candidates for value in c.parameters))

    def test_vectors_and_ids_are_distinct_and_bound_to_input(self):
        candidates = self.hero_result.candidates
        self.assertEqual(len({c.id for c in candidates}), len(candidates))
        self.assertEqual(len({c.parameters for c in candidates}), len(candidates))
        self.assertTrue(all(c.problem_digest == self.hero.digest for c in candidates))
        self.assertTrue(all(c.source_artifact_digest is None for c in candidates))
        for candidate in candidates:
            self.assertTrue(all(lo <= value <= hi for value, (lo, hi) in zip(candidate.parameters, self.hero.domain)))

    def test_modified_measurements_change_actual_search_and_identity(self):
        payload = hero_payload()
        for row in payload["observations"]:
            row["value"] = str(Fraction(row["value"]) / 2)
            row["allowance"] = "0.25"
        altered = normalize_problem(payload)
        result = search_candidates(altered)
        self.assertNotEqual(altered.digest, self.hero.digest)
        self.assertEqual(result.report["attempted_count"], self.hero_result.report["attempted_count"])
        self.assertNotEqual(result.candidates[0].id, self.hero_result.candidates[0].id)
        self.assertNotEqual(result.candidates[0].parameters, self.hero_result.candidates[0].parameters)
        self.assertTrue(any(candidate.is_outside(altered) for candidate in result.candidates))
        self.assertEqual(evaluate_historical_candidate(altered, result.candidates[0])["verification"], "valid")

    def test_closed_endpoints_are_inside_and_no_outside_is_not_a_proof(self):
        problem = normalize_problem(broad_payload())
        result = search_candidates(problem, settings=small_settings())
        self.assertEqual({c.parameters[1] for c in result.candidates}, set(problem.claim))
        self.assertTrue(all(not c.is_outside(problem) for c in result.candidates))
        self.assertTrue(all(p["claim_position"] == "inside" for p in result.report["candidates"]))
        self.assertEqual(result.report["outcome"], "numerical_candidates")
        self.assertNotIn("claim_valid", result.report)

    def test_one_attempt_keeps_one_candidate_without_fabricating_pair(self):
        result = search_candidates(normalize_problem(broad_payload()), settings=small_settings(max_rate_pairs=1))
        self.assertEqual(len(result.candidates), 1)
        self.assertEqual(result.report["attempted_count"], 1)
        self.assertEqual(result.report["reason_code"], "rate_pair_cap")
        self.assertTrue(result.report["partial"])
        self.assertEqual(result.report["settings"]["ke_points"], 2)

    def test_single_retained_slot_prefers_outside(self):
        payload = broad_payload()
        payload["claim"]["interval"] = ["1", "1"]
        problem = normalize_problem(payload)
        result = search_candidates(problem, settings=small_settings(max_candidates=1))
        self.assertEqual(len(result.candidates), 1)
        self.assertTrue(result.candidates[0].is_outside(problem))

    def test_all_impossible_screenings_report_bounded_empty_result(self):
        payload = broad_payload()
        for row in payload["observations"]:
            row.update(time=str(Fraction(row["time"]) + 1), value="100", allowance="0.01")
        result = search_candidates(normalize_problem(payload), settings=small_settings())
        self.assertEqual(result.candidates, ())
        self.assertEqual(result.report["outcome"], "no_numerical_candidate_found")
        self.assertEqual(result.report["attempted_count"], 4)
        self.assertEqual(result.report["evaluated_count"], 4)
        self.assertEqual(result.report["failure_counts"]["amplitude_infeasible"], 4)
        self.assertFalse(result.report["partial"])

    def test_incompatible_initial_reading_is_rejected_exactly(self):
        payload = broad_payload()
        payload["observations"][0].update(value="0.100000000000000000000000000001", allowance="0.1")
        result = search_candidates(normalize_problem(payload), settings=small_settings())
        self.assertFalse(result.candidates)
        self.assertEqual(result.report["failure_counts"]["amplitude_infeasible"], 4)

    def test_heterogeneous_allowances_change_result_and_diagnostic_denominators(self):
        payload = broad_payload()
        payload["observations"][1]["allowance"] = "0.1"
        problem = normalize_problem(payload)
        result = search_candidates(problem, settings=small_settings())
        self.assertGreater(result.report["failure_counts"]["amplitude_infeasible"], 0)
        for candidate, diagnostic in zip(result.candidates, result.report["candidates"]):
            maximum = max(abs(float(residual)) / float(row.allowance)
                          for residual, row in zip(diagnostic["residual_approximations"], problem.observations))
            self.assertAlmostEqual(float(diagnostic["maximum_normalized_residual_approximation"]), maximum)
            self.assertEqual(evaluate_historical_candidate(problem, candidate)["verification"], "valid")

    def test_excluded_rows_never_constrain_search_and_keep_original_order(self):
        payload = broad_payload()
        original = normalize_problem(payload)
        unbounded = deepcopy(payload["observations"][0])
        unbounded.update(id="excluded-unrepresentable", time="1" + "0" * 400 + "/1",
                         value="1" + "0" * 400 + "/1", allowance="1/1" + "0" * 400, included=False)
        payload["observations"].insert(1, unbounded)
        problem = normalize_problem(payload)
        result = search_candidates(problem, settings=small_settings())
        original_result = search_candidates(original, settings=small_settings())
        self.assertEqual([c.parameters for c in result.candidates], [c.parameters for c in original_result.candidates])
        self.assertEqual(result.report["observation_ids"][1], "excluded-unrepresentable")
        self.assertFalse(result.report["included"][1])
        self.assertTrue(all(row["residual_approximations"][1] is None for row in result.report["candidates"]))
        self.assertNotEqual(result.candidates[0].id, original_result.candidates[0].id)

    def test_cancel_before_search_has_no_attempts(self):
        context = ExecutionContext(cancelled=lambda: True, clock=lambda: 0)
        result = search_candidates(self.hero, context=context)
        self.assertEqual(result.report["execution"], "cancelled")
        self.assertEqual(result.report["reason_code"], "cancelled")
        self.assertEqual(result.report["attempted_count"], 0)
        self.assertEqual(result.candidates, ())

    def test_cancel_after_first_preserves_partial_proposal_and_stops(self):
        calls = []
        def cancelled():
            calls.append(True)
            return len(calls) > 1
        context = ExecutionContext(cancelled=cancelled, clock=lambda: 0)
        result = search_candidates(normalize_problem(broad_payload()), settings=small_settings(), context=context)
        self.assertEqual(len(calls), 2)
        self.assertEqual(result.report["attempted_count"], 1)
        self.assertEqual(result.report["execution"], "cancelled")
        self.assertEqual(len(result.candidates), 1)
        # Reusing the context cannot undo its latched stop or start new work.
        again = search_candidates(self.hero, context=context)
        self.assertEqual(again.report["attempted_count"], 0)
        self.assertEqual(len(calls), 2)

    def test_smaller_request_wall_limit_wins(self):
        ticks = iter((0, 0, 2))
        context = ExecutionContext(wall_seconds=120, clock=lambda: next(ticks))
        result = search_candidates(normalize_problem(broad_payload()), settings=small_settings(wall_seconds=1), context=context)
        self.assertEqual(result.report["attempted_count"], 1)
        self.assertEqual(result.report["reason_code"], "resource_exhaustion")
        self.assertEqual(result.report["execution"], "interrupted")
        self.assertEqual(len(result.candidates), 1)

    def test_nonrepresentable_rows_fail_explicitly_not_as_fabricated_zero(self):
        payload = broad_payload()
        for index, row in enumerate(payload["observations"]):
            row["time"] = str(10000 + index)
        result = search_candidates(normalize_problem(payload), settings=small_settings())
        self.assertEqual(result.candidates, ())
        self.assertEqual(result.report["failure_counts"]["numerical_range_limitation"], 4)
        self.assertEqual(result.report["evaluated_count"], 0)
        self.assertTrue(result.report["partial"])

    def test_report_is_json_safe_bounded_and_elapsed_is_diagnostic_text(self):
        encoded = canonical_bytes(self.hero_result.report)
        self.assertEqual(strict_json_loads(encoded), self.hero_result.report)
        self.assertIsInstance(self.hero_result.report["elapsed_seconds"], str)
        self.assertGreaterEqual(float(self.hero_result.report["elapsed_seconds"]), 0)
        # Worst admitted row count and retained proposals remain below the
        # strict JSON parser's node cap without recording every grid attempt.
        payload = broad_payload()
        payload["observations"] = [dict(payload["observations"][i % 3], id=f"row-{i}") for i in range(128)]
        result = search_candidates(normalize_problem(payload), settings=SearchSettings(8, 8, 64, 32, 120))
        self.assertEqual(len(result.candidates), 32)
        self.assertEqual(strict_json_loads(canonical_bytes(result.report)), result.report)

    def test_direct_bad_dataclasses_and_settings_are_revalidated(self):
        with self.assertRaises(AdapterError):
            search_candidates(replace(self.hero, domain=self.hero.domain + ((Fraction(1), Fraction(2)),)))
        with self.assertRaises(AdapterError):
            search_candidates(self.hero, settings=replace(SearchSettings(), max_rate_pairs=16385))
        with self.assertRaises(AdapterError):
            search_candidates(self.hero, settings=replace(SearchSettings(), max_candidates=True))
        with self.assertRaises(AdapterError):
            search_candidates(self.hero, context=object())

    def test_settings_reject_unknown_and_partial_fields_and_accept_empty_defaults(self):
        self.assertEqual(normalize_search_settings({}), SearchSettings())
        self.assertEqual(normalize_search_settings(SearchSettings().to_payload()), SearchSettings())
        for payload in ({"ke_points": 8}, dict(SearchSettings().to_payload(), seed=42),
                        dict(SearchSettings().to_payload(), policy="unreviewed-refinement")):
            with self.subTest(payload=payload), self.assertRaises(AdapterError):
                normalize_search_settings(payload)

    def test_repeatable_vectors_and_scores_ignore_ambient_decimal_context(self):
        problem = normalize_problem(broad_payload())
        before = problem.to_payload()
        first = search_candidates(problem, settings=small_settings())
        with localcontext(Context(prec=3)):
            second = search_candidates(problem, settings=small_settings())
        self.assertEqual(first.candidates, second.candidates)
        self.assertEqual(first.report["candidates"], second.report["candidates"])
        self.assertEqual(problem.to_payload(), before)

    def test_rounding_midpoint_keeps_exact_amplitude_domain(self):
        payload = broad_payload()
        payload["domain"]["A"] = ["1.00000000000000000000000001", "1.00000000000000000000000002"]
        problem = normalize_problem(payload)
        result = search_candidates(problem, settings=small_settings())
        self.assertTrue(result.candidates)
        self.assertTrue(all(problem.domain[0][0] <= c.parameters[0] <= problem.domain[0][1] for c in result.candidates))


if __name__ == "__main__":
    unittest.main()
