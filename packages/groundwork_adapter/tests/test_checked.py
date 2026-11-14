"""Fresh analytic-template checking and hostile evidence controls.

All fixtures are independently constructed hypothetical inputs. Assertions
exercise fresh computation and binding, not a stored positive badge.
"""

from copy import deepcopy
from fractions import Fraction as Q
import unittest
from unittest.mock import patch

from counterdex.analytical import concentration_interval
from counterdex.checked import checked_design, construct_pair, verify_pair
from counterdex.errors import AdapterError
from counterdex.exact import artifact_digest, canonical_bytes, strict_json_loads
from counterdex.models import normalize_design, normalize_problem
from counterdex.resource import ExecutionContext

from helpers import synthetic_design_payload, synthetic_inputs, synthetic_problem_payload


class CheckedControls(unittest.TestCase):
    def setUp(self):
        self.problem, self.design = synthetic_inputs()
        self.content = construct_pair(self.problem, self.design, ExecutionContext())

    def assert_code(self, code, function, *args, **kwargs):
        with self.assertRaises(AdapterError) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)
        return caught.exception

    def changed_pair(self, change):
        payload = strict_json_loads(self.content)
        change(payload)
        return canonical_bytes(payload)

    def changed_design(self, change):
        payload = self.design.to_payload()
        change(payload)
        return normalize_design(payload, self.problem)

    def test_fresh_pair_and_selected_grid(self):
        result = checked_design(self.problem, self.design, {})
        report = result.report
        self.assertEqual(result.pair_bytes, self.content)
        self.assertEqual(report["verification"], "valid")
        self.assertEqual(report["tier"], "checked_pair_separation")
        self.assertEqual(report["selected_time"], "6/1")
        self.assertEqual(report["common_checked_horizon"], "8/1")
        self.assertEqual(report["construction_attempts"], 2)
        self.assertEqual(report["pair_verification_passes"], 1)
        self.assertEqual(report["pair_digest"], artifact_digest(result.pair_bytes))
        self.assertTrue(all(row["separated"] for row in report["rows"]))
        self.assertEqual([row["time"] for row in report["rows"]], ["6/1", "8/1"])
        candidates = {row["candidate_id"]: row for row in report["candidate_results"]}
        self.assertEqual(candidates["endpoint-candidate"]["verification"], "valid")
        self.assertFalse(candidates["endpoint-candidate"]["is_counterexample"])
        self.assertTrue(candidates["outside-candidate"]["is_counterexample"])

    def test_different_full_problem_identity_cannot_borrow_pair(self):
        payload = self.problem.to_payload()
        payload["notes"] += " changed review note"
        foreign_problem = normalize_problem(payload)
        foreign_design = normalize_design(synthetic_design_payload(foreign_problem), foreign_problem)
        self.assert_code("wrong_specification_binding", verify_pair, self.content, foreign_problem, foreign_design)
        self.assert_code("wrong_specification_binding", normalize_design, self.design.to_payload(), foreign_problem)

    def test_changed_parameter_vector_cannot_borrow_enclosure(self):
        content = self.changed_pair(lambda p: p["candidates"][1]["parameters"].__setitem__("ke", "1/3"))
        self.assert_code("candidate_mismatch", verify_pair, content, self.problem, self.design)

    def test_changed_times_and_omitted_samples_fail(self):
        content = self.changed_pair(lambda p: p["candidates"][0]["samples"][3].__setitem__("time", "7/1"))
        self.assert_code("invalid_certificate", verify_pair, content, self.problem, self.design)
        content = self.changed_pair(lambda p: p["candidates"][0]["samples"].pop())
        self.assert_code("invalid_certificate", verify_pair, content, self.problem, self.design)

    def test_forged_bound_is_exact_check_failure(self):
        content = self.changed_pair(lambda p: p["candidates"][0]["samples"][3].__setitem__("lower", "0/1"))
        self.assert_code("exact_check_failure", verify_pair, content, self.problem, self.design)

    def test_unknown_positive_badge_and_unsupported_rule_fail(self):
        content = self.changed_pair(lambda p: p.__setitem__("separated", True))
        self.assert_code("invalid_input", verify_pair, content, self.problem, self.design)
        content = self.changed_pair(lambda p: p.__setitem__("proof_rule", "unqualified-rule.v1"))
        self.assert_code("unsupported_model", verify_pair, content, self.problem, self.design)

    def test_missing_or_duplicate_candidate_fails_one_to_one_association(self):
        content = self.changed_pair(lambda p: p["candidates"].pop())
        self.assert_code("missing_second_witness", verify_pair, content, self.problem, self.design)
        content = self.changed_pair(lambda p: p["candidates"].__setitem__(1, deepcopy(p["candidates"][0])))
        self.assert_code("candidate_mismatch", verify_pair, content, self.problem, self.design)

    def test_candidate_permutation_moves_its_own_evidence(self):
        original = verify_pair(self.content, self.problem, self.design)
        content = self.changed_pair(lambda p: p["candidates"].reverse())
        design = self.changed_design(lambda d: d["candidates"].reverse())
        permuted = verify_pair(content, self.problem, design)
        self.assertNotEqual(artifact_digest(content), artifact_digest(self.content))
        self.assertNotEqual(design.digest, self.design.digest)
        for key in ("candidate_results", "rows", "ranked_times", "selected_time", "verification", "tier"):
            self.assertEqual(permuted[key], original[key], key)

    def test_common_horizon_endpoint_is_inclusive_and_step_beyond_fails(self):
        report = verify_pair(self.content, self.problem, self.design)
        self.assertEqual(report["rows"][-1]["status"], "evaluated")
        self.assertEqual(report["rows"][-1]["time"], report["common_checked_horizon"])
        payload = self.design.to_payload()
        payload["grid"][-1]["time"] = "8000000000000000000000000000001/1000000000000000000000000000000"
        self.assert_code("unavailable_horizon", normalize_design, payload, self.problem)
        for horizon in ("7/1", "9/1"):
            content = self.changed_pair(lambda p: p.__setitem__("horizon", horizon))
            self.assert_code("unavailable_horizon", verify_pair, content, self.problem, self.design)

    def test_inside_upper_endpoint_and_singleton_are_not_outside(self):
        for interval in (["1/20", "1/3"], ["1/20", "1/10"], ["1/10", "1/10"]):
            with self.subTest(interval=interval):
                payload = synthetic_problem_payload()
                payload["claim"]["interval"] = interval
                problem = normalize_problem(payload)
                design = normalize_design(synthetic_design_payload(problem), problem)
                report = checked_design(problem, design, {}).report
                endpoint = next(row for row in report["candidate_results"] if row["candidate_id"] == "endpoint-candidate")
                self.assertEqual(endpoint["verification"], "valid")
                self.assertFalse(endpoint["outside_closed_claim"])
                self.assertFalse(endpoint["is_counterexample"])
                if interval == ["1/20", "1/3"]:
                    self.assertFalse(any(row["is_counterexample"] for row in report["candidate_results"]))

    def test_heterogeneous_allowances_remain_exact_and_input_unchanged(self):
        before = self.problem.to_payload()
        report = checked_design(self.problem, self.design, {}).report
        self.assertEqual(tuple(row.allowance for row in self.problem.observations), (Q(1, 10), Q(3), Q(3)))
        self.assertEqual(self.problem.to_payload(), before)
        self.assertEqual(report["verification"], "valid")
        payload = deepcopy(before)
        payload["observations"][1]["allowance"] = "1/100"
        problem = normalize_problem(payload)
        design = normalize_design(synthetic_design_payload(problem), problem)
        checked = checked_design(problem, design, {}).report
        self.assertEqual(checked["verification"], "invalid")
        self.assertTrue(all(row["reason_code"] == "measurement_incompatible" for row in checked["candidate_results"]))

    def test_no_construction_or_extension_authority(self):
        payload = self.design.to_payload()
        payload["horizon_policy"].update(allow_construction=False, allow_extension=False)
        payload["limits"]["max_constructions"] = 0
        design = normalize_design(payload, self.problem)
        self.assert_code("missing_second_witness", checked_design, self.problem, design, {})
        payload = self.design.to_payload()
        payload["horizon_policy"]["allow_extension"] = False
        design = normalize_design(payload, self.problem)
        self.assert_code("unavailable_horizon", checked_design, self.problem, design, {})

    def test_source_pair_reuse_is_freshly_checked_without_construction(self):
        digest = artifact_digest(self.content)
        payload = self.design.to_payload()
        for candidate in payload["candidates"]:
            candidate["source_artifact_digest"] = digest
        payload["horizon_policy"].update(allow_construction=False, allow_extension=False)
        payload["limits"]["max_constructions"] = 0
        design = normalize_design(payload, self.problem)
        with patch("counterdex.checked.construct_pair", side_effect=AssertionError("unexpected construction")):
            with patch("counterdex.checked.concentration_interval", wraps=concentration_interval) as fresh:
                result = checked_design(self.problem, design, {digest: self.content})
        self.assertEqual(fresh.call_count, 10)
        self.assertEqual(result.report["construction_attempts"], 0)
        self.assertEqual(result.report["pair_verification_passes"], 1)
        self.assertEqual(result.report["verification"], "valid")
        self.assertEqual(result.pair_bytes, self.content)
        self.assert_code("incomplete_export", checked_design, self.problem, design, {})
        self.assert_code("artifact_mismatch", checked_design, self.problem, design, {digest: self.content + b" "})

    def test_no_pair_verification_budget_stops_before_computation(self):
        design = self.changed_design(lambda d: d["limits"].__setitem__("max_pair_verifications", 0))
        with patch("counterdex.checked.concentration_interval", side_effect=AssertionError("unexpected computation")):
            self.assert_code("resource_exhaustion", checked_design, self.problem, design, {})

    def test_certificate_byte_cap_applies_to_construction_and_replay(self):
        design = self.changed_design(lambda d: d["limits"].__setitem__("max_certificate_bytes", len(self.content) - 1))
        self.assert_code("resource_exhaustion", checked_design, self.problem, design, {})
        self.assert_code("resource_exhaustion", verify_pair, self.content, self.problem, design)

    def test_new_pair_also_counts_toward_bundle_cap(self):
        design = self.changed_design(lambda d: d["limits"].__setitem__("max_bundle_bytes", 1))
        self.assert_code("resource_exhaustion", checked_design, self.problem, design, {})

    def test_cancellation_prevents_additional_enclosures(self):
        calls = 0

        def stopped():
            nonlocal calls
            calls += 1
            return calls >= 4

        context = ExecutionContext(cancelled=stopped)
        with patch("counterdex.checked.concentration_interval", wraps=concentration_interval) as evaluation:
            self.assert_code("cancelled", checked_design, self.problem, self.design, {}, context)
        self.assertLessEqual(evaluation.call_count, 1)
        self.assertEqual(context.stop_reason(), "cancelled")

    def test_design_wall_limit_cannot_be_expanded_by_context(self):
        design = self.changed_design(lambda d: d["limits"].__setitem__("wall_seconds", 1))
        now = [0.0]
        context = ExecutionContext(wall_seconds=120, clock=lambda: now[0])
        now[0] = 2.0
        with patch("counterdex.checked.concentration_interval", side_effect=AssertionError("unexpected computation after approved limit")):
            self.assert_code("resource_exhaustion", checked_design, self.problem, design, {}, context)

    def test_measurement_incompatibility_is_not_a_malformed_proof(self):
        payload = synthetic_problem_payload()
        payload["observations"][0]["value"] = "1/1"
        problem = normalize_problem(payload)
        design = normalize_design(synthetic_design_payload(problem), problem)
        result = checked_design(problem, design, {})
        self.assertIsNotNone(result.pair_bytes)
        self.assertEqual(result.report["verification"], "invalid")
        self.assertEqual(result.report["tier"], "unavailable")
        self.assertIsNone(result.report["selected_time"])
        for candidate in result.report["candidate_results"]:
            self.assertEqual(candidate["reason_code"], "measurement_incompatible")
            self.assertEqual(candidate["violating_observation_ids"], ["synthetic-0"])
            self.assertFalse(candidate["is_counterexample"])
        corrupt = self.changed_pair(lambda p: p["candidates"][0]["samples"][0].__setitem__("upper", "1/1"))
        self.assert_code("exact_check_failure", verify_pair, corrupt, self.problem, self.design)

    def test_large_future_allowance_has_no_separating_time(self):
        design = self.changed_design(lambda d: d.__setitem__("future_allowance", "10/1"))
        report = verify_pair(self.content, self.problem, design)
        self.assertEqual(report["verification"], "valid")
        self.assertEqual(report["tier"], "no_separation_established")
        self.assertEqual(report["reason_code"], "no_separating_time")
        self.assertIsNone(report["selected_time"])
        self.assertTrue(all(row["status"] == "evaluated" and not row["separated"] for row in report["rows"]))


if __name__ == "__main__":
    unittest.main()
