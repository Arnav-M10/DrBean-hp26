"""Scientific admission and identity controls using newly constructed inputs."""

from copy import deepcopy
from dataclasses import replace
from fractions import Fraction as Q
import unittest
from unittest.mock import patch

from counterdex.analytical import concentration_interval
from counterdex.checked import checked_design, construct_pair
from counterdex.errors import AdapterError
from counterdex.exact import artifact_digest, canonical_bytes, rational_text, strict_json_loads
from counterdex.models import (
    CHECKED_POLICY, NUMERICAL_POLICY, normalize_design, normalize_problem, normalize_times, revalidate_inputs,
)
from counterdex.resource import ExecutionContext


def problem_input():
    return {
        "schema_version": "groundwork.problem.v1", "model": "two_rate_kinetics_v1", "model_revision": 1,
        "units": {"time": "h", "concentration": "mg/L", "rate": "1/h"},
        "initial_conditions": {"x": "1", "c": "0"}, "time_origin": "synthetic experiment zero",
        "dataset_kind": "hypothetical", "domain": {"A": ["1", "20"], "ke": ["0.1", "0.5"], "ka": ["1", "2"]},
        "claim": {"parameter": "ke", "interval": ["0.2", "0.3"]},
        "observations": [
            {"id": f"measurement-{i}", "time": str(i), "value": str(i), "allowance": allowance,
             "included": True, "allowance_origin": f"reviewed hard bound {i}", "origin": "hypothetical",
             "notes": "", "provenance": "event-authored synthetic admission control"}
            for i, allowance in enumerate(("1/10", "1/5", "3/10"))
        ],
        "notes": "", "provenance": "event-authored synthetic admission control",
    }


def design_input(problem):
    return {
        "schema_version": "groundwork.design.v1", "problem_digest": problem.digest, "scenario_id": "synthetic-scenario",
        "candidates": [
            {"id": identity, "problem_digest": problem.digest,
             "parameters": {"A": amplitude, "ke": rate, "ka": "1.5"}, "source_artifact_digest": None}
            for identity, amplitude, rate in (("lower-endpoint", "4", "0.2"), ("upper-endpoint", "8", "0.3"))
        ],
        "grid": [{"time": t, "feasible": True, "reason": "reviewed synthetic availability"} for t in ("4", "3")],
        "time_origin": problem.time_origin, "observable": "c", "future_allowance": "1/5",
        "allowance_origin": {"kind": "hypothetical", "description": "explicit assumed hard bound"},
        "requested_tier": "numerical_guidance",
        "horizon_policy": {"allow_construction": False, "allow_extension": False, "maximum_horizon": "4"},
        "numerical_policy": NUMERICAL_POLICY, "checked_policy": CHECKED_POLICY,
        "limits": {"wall_seconds": 120, "max_times": 64, "max_constructions": 0,
                   "max_pair_verifications": 0, "max_bundle_bytes": 4194304, "max_certificate_bytes": 2097152},
    }


class ProblemAdmissionTests(unittest.TestCase):
    def test_heterogeneous_allowances_and_excluded_rows_survive_exactly(self):
        payload = problem_input()
        excluded = deepcopy(payload["observations"][0])
        excluded.update(id="excluded", time="1000", allowance="7/50", included=False, notes="retained")
        payload["observations"].insert(1, excluded)
        problem = normalize_problem(payload)
        self.assertEqual([row.allowance for row in problem.observations], [Q(1, 10), Q(7, 50), Q(1, 5), Q(3, 10)])
        self.assertEqual([row.id for row in problem.observations], ["measurement-0", "excluded", "measurement-1", "measurement-2"])
        self.assertEqual(problem.horizon, Q(2))
        self.assertEqual(problem.to_payload()["observations"][1]["notes"], "retained")
        self.assertFalse(problem.to_payload()["observations"][1]["included"])

    def test_exact_lexemes_and_portable_roundtrip(self):
        original = problem_input()
        changed = deepcopy(original)
        changed["domain"]["ke"][0] = "100e-3"
        changed["initial_conditions"]["x"] = "2/2"
        changed["observations"][0]["allowance"] = "0.1000"
        first, second = normalize_problem(original), normalize_problem(changed)
        self.assertEqual(first.digest, second.digest)
        self.assertEqual(first.to_payload(), second.to_payload())
        decoded = strict_json_loads(canonical_bytes(first.to_payload()))
        self.assertEqual(normalize_problem(decoded), first)
        self.assertEqual(original["initial_conditions"]["x"], "1")

    def test_full_problem_identity_preserves_order_notes_and_excluded_data(self):
        base = problem_input()
        expected = normalize_problem(base).digest
        for mutate in (
            lambda p: p.update(notes="new note"),
            lambda p: p["observations"].reverse(),
            lambda p: p["observations"][0].update(provenance="different source"),
        ):
            payload = deepcopy(base)
            mutate(payload)
            self.assertNotEqual(normalize_problem(payload).digest, expected)

    def test_positive_strict_parameter_intervals_and_rate_order(self):
        for field, bounds in (("A", ["0", "20"]), ("A", ["1", "1"]),
                              ("ke", ["0.5", "0.1"]), ("ke", ["0.1", "1"]),
                              ("ka", ["0.5", "2"]), ("ka", ["-1", "2"])):
            payload = problem_input()
            payload["domain"][field] = bounds
            with self.subTest(field=field, bounds=bounds), self.assertRaises(AdapterError):
                normalize_problem(payload)

    def test_three_distinct_included_times_and_unique_ids_required(self):
        for mutate in (
            lambda p: p["observations"][1].update(time="0.0"),
            lambda p: p["observations"][1].update(included=False),
            lambda p: p["observations"][1].update(id="measurement-0"),
            lambda p: p["observations"][1].update(time="-1"),
            lambda p: p["observations"][1].update(allowance="0"),
            lambda p: p.update(observations=p["observations"][:2]),
        ):
            payload = problem_input()
            mutate(payload)
            with self.assertRaises(AdapterError) as caught:
                normalize_problem(payload)
            self.assertTrue(caught.exception.field_paths)

    def test_unsupported_model_units_reset_and_correlation_fail(self):
        for mutate in (
            lambda p: p.update(model="another_model"),
            lambda p: p["units"].update(time="s"),
            lambda p: p["initial_conditions"].update(x="2"),
            lambda p: p.update(shared_calibration_offset="1/10"),
            lambda p: p["observations"][0].update(covariance="1/10"),
            lambda p: p["claim"].update(parameter="A"),
        ):
            payload = problem_input()
            mutate(payload)
            with self.assertRaises(AdapterError):
                normalize_problem(payload)

    def test_unknown_fields_rejected_at_every_normative_level(self):
        for location in ((), ("domain",), ("claim",), ("initial_conditions",), ("units",), ("observations", 0)):
            payload = problem_input()
            target = payload
            for key in location:
                target = target[key]
            target["unknown"] = "unexpected"
            with self.subTest(location=location), self.assertRaises(AdapterError):
                normalize_problem(payload)

    def test_json_numbers_and_booleans_cannot_be_scientific_scalars(self):
        for value in (1, 0.1, True, None):
            payload = problem_input()
            payload["observations"][0]["allowance"] = value
            with self.subTest(value=value), self.assertRaises(AdapterError):
                normalize_problem(payload)
        payload = problem_input()
        payload["model_revision"] = True
        with self.assertRaises(AdapterError):
            normalize_problem(payload)

    def test_hypothetical_rows_cannot_enter_actual_dataset(self):
        payload = problem_input()
        payload["dataset_kind"] = "actual"
        with self.assertRaises(AdapterError):
            normalize_problem(payload)
        for row in payload["observations"]:
            row["origin"] = "transcription"
        self.assertEqual(normalize_problem(payload).dataset_kind, "actual")


class DesignAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.problem = normalize_problem(problem_input())

    def test_closed_claim_endpoints_and_degenerate_claim(self):
        design = normalize_design(design_input(self.problem), self.problem)
        self.assertFalse(design.candidates[0].is_outside(self.problem))
        self.assertFalse(design.candidates[1].is_outside(self.problem))
        payload = problem_input()
        payload["claim"]["interval"] = ["0.2", "1/5"]
        problem = normalize_problem(payload)
        design = normalize_design(design_input(problem), problem)
        self.assertFalse(design.candidates[0].is_outside(problem))
        self.assertTrue(design.candidates[1].is_outside(problem))

    def test_grid_normalization_before_review_and_duplicate_rejection_after(self):
        self.assertEqual(normalize_times(["2", "1.0", "2/2", "0"]), ("0/1", "1/1", "2/1"))
        payload = design_input(self.problem)
        result = normalize_design(payload, self.problem)
        self.assertEqual([row.time for row in result.grid], [Q(3), Q(4)])
        self.assertEqual(payload["grid"][0]["time"], "4")
        payload["grid"][1]["time"] = "4.0"
        with self.assertRaises(AdapterError):
            normalize_design(payload, self.problem)

    def test_missing_or_nonpositive_future_allowance_is_never_inferred(self):
        for allowance in (None, "0", "-1/100", 0.2, True):
            payload = design_input(self.problem)
            payload["future_allowance"] = allowance
            with self.subTest(allowance=allowance), self.assertRaises(AdapterError):
                normalize_design(payload, self.problem)
        payload = design_input(self.problem)
        del payload["future_allowance"]
        with self.assertRaises(AdapterError):
            normalize_design(payload, self.problem)

    def test_wrong_problem_and_candidate_binding_are_typed(self):
        for location in ("problem", "candidate"):
            payload = design_input(self.problem)
            if location == "problem":
                payload["problem_digest"] = "0" * 64
            else:
                payload["candidates"][0]["problem_digest"] = "0" * 64
            with self.assertRaises(AdapterError) as caught:
                normalize_design(payload, self.problem)
            self.assertEqual(caught.exception.code, "wrong_specification_binding")

    def test_candidate_ids_vectors_and_domains_are_bound(self):
        for mutate in (
            lambda p: p["candidates"][1].update(id=p["candidates"][0]["id"]),
            lambda p: p["candidates"][1].update(parameters=deepcopy(p["candidates"][0]["parameters"])),
            lambda p: p["candidates"][0]["parameters"].update(ke="0.9"),
            lambda p: p["candidates"][0]["parameters"].update(extra="1"),
            lambda p: p.update(candidates=p["candidates"][:1]),
        ):
            payload = design_input(self.problem)
            mutate(payload)
            with self.assertRaises(AdapterError):
                normalize_design(payload, self.problem)

    def test_semantic_identity_tracks_allowance_artifacts_order_and_limits(self):
        payload = design_input(self.problem)
        baseline = normalize_design(payload, self.problem)
        equivalent = deepcopy(payload)
        equivalent["future_allowance"] = "0.2000"
        self.assertEqual(normalize_design(equivalent, self.problem).digest, baseline.digest)
        for mutate in (
            lambda p: p.update(future_allowance="0.21"),
            lambda p: p["candidates"].reverse(),
            lambda p: p["candidates"][0].update(source_artifact_digest="a" * 64),
            lambda p: p["limits"].update(wall_seconds=119),
        ):
            changed = deepcopy(payload)
            mutate(changed)
            self.assertNotEqual(normalize_design(changed, self.problem).digest, baseline.digest)

    def test_checked_horizon_endpoint_and_one_rational_step_beyond(self):
        payload = design_input(self.problem)
        payload["requested_tier"] = "checked_pair_separation"
        self.assertEqual(normalize_design(payload, self.problem).maximum_horizon, Q(4))
        payload["grid"][0]["time"] = "400000000000000000001/100000000000000000000"
        with self.assertRaises(AdapterError) as caught:
            normalize_design(payload, self.problem)
        self.assertEqual(caught.exception.code, "unavailable_horizon")

    def test_resource_caps_and_boolean_counters(self):
        for key, value in (("wall_seconds", 121), ("max_times", 65), ("max_constructions", 3),
                           ("max_pair_verifications", 3), ("max_bundle_bytes", 4194305),
                           ("max_certificate_bytes", 2097153), ("wall_seconds", True)):
            payload = design_input(self.problem)
            payload["limits"][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(AdapterError):
                normalize_design(payload, self.problem)
        payload = design_input(self.problem)
        payload["limits"]["max_times"] = 1
        with self.assertRaises(AdapterError):
            normalize_design(payload, self.problem)

    def test_unsupported_observable_origin_allowance_and_extension(self):
        for mutate in (
            lambda p: p.update(observable="x"),
            lambda p: p.update(time_origin="different batch"),
            lambda p: p["allowance_origin"].update(kind="standard_deviation"),
            lambda p: p["horizon_policy"].update(allow_extension=True),
            lambda p: p.update(fake_future_observation={"value": "2"}),
            lambda p: p.update(numerical_policy="unreviewed-search.v2"),
        ):
            payload = design_input(self.problem)
            mutate(payload)
            with self.assertRaises(AdapterError):
                normalize_design(payload, self.problem)


class ExactBoundaryControls(unittest.TestCase):
    """Fresh scientific evidence must not bypass request/type/resource gates."""

    def setUp(self):
        payload = problem_input()
        for row in payload["observations"]:
            row["allowance"] = "100"
        self.problem = normalize_problem(payload)
        self.design = self.checked_input(self.problem)

    @staticmethod
    def checked_input(problem):
        payload = design_input(problem)
        payload["requested_tier"] = "checked_pair_separation"
        payload["horizon_policy"].update(allow_construction=True, allow_extension=True)
        payload["limits"].update(max_constructions=2, max_pair_verifications=1)
        return normalize_design(payload, problem)

    def test_direct_objects_require_immutable_complete_vectors(self):
        p, d = self.problem, self.design
        bad_problems = (
            replace(p, domain=list(p.domain)), replace(p, domain=p.domain + (p.domain[0],)),
            replace(p, domain=(p.domain[0] + (Q(30),),) + p.domain[1:]),
            replace(p, claim=p.claim + (Q(1),)), replace(p, observations=list(p.observations)),
        )
        for problem in bad_problems:
            with self.assertRaises(AdapterError):
                revalidate_inputs(problem, d)
        bad_candidate = replace(d.candidates[0], parameters=d.candidates[0].parameters + (Q(7),))
        for design in (replace(d, candidates=list(d.candidates)), replace(d, grid=list(d.grid)),
                       replace(d, candidates=(bad_candidate, d.candidates[1])),
                       replace(d, future_allowance=Q(-1))):
            with self.assertRaises(AdapterError):
                checked_design(p, design, {})

    def test_numerical_request_cannot_gain_checked_scope(self):
        design = replace(self.design, requested_tier="numerical_guidance")
        with patch("counterdex.checked.concentration_interval") as evaluator:
            with self.assertRaises(AdapterError) as caught:
                checked_design(self.problem, design, {})
            self.assertEqual(caught.exception.code, "invalid_input")
            with self.assertRaises(AdapterError):
                construct_pair(self.problem, design, ExecutionContext(clock=lambda: 0))
            evaluator.assert_not_called()

    def test_construction_and_verification_authority_is_not_expanded(self):
        for design, reason in (
            (replace(self.design, allow_construction=False, allow_extension=False), "missing_second_witness"),
            (replace(self.design, limits=replace(self.design.limits, max_constructions=1)), "missing_second_witness"),
            (replace(self.design, allow_extension=False), "unavailable_horizon"),
            (replace(self.design, limits=replace(self.design.limits, max_pair_verifications=0)), "resource_exhaustion"),
        ):
            with patch("counterdex.checked.concentration_interval") as evaluator:
                with self.assertRaises(AdapterError) as caught:
                    checked_design(self.problem, design, {})
                self.assertEqual(caught.exception.code, reason)
                evaluator.assert_not_called()

    def test_cancellation_and_smaller_request_wall_cap_precede_evaluation(self):
        ticks = iter((0, 2))
        cases = (
            (self.design, ExecutionContext(cancelled=lambda: True, clock=lambda: 0), "cancelled"),
            (replace(self.design, limits=replace(self.design.limits, wall_seconds=1)),
             ExecutionContext(wall_seconds=120, clock=lambda: next(ticks)), "resource_exhaustion"),
        )
        for design, context, reason in cases:
            with patch("counterdex.checked.concentration_interval") as evaluator:
                with self.assertRaises(AdapterError) as caught:
                    checked_design(self.problem, design, {}, context)
                self.assertEqual(caught.exception.code, reason)
                evaluator.assert_not_called()

    def test_pair_reuse_needs_no_new_construction_but_does_fresh_check(self):
        result = checked_design(self.problem, self.design, {})
        digest = artifact_digest(result.pair_bytes)
        design = replace(self.design,
            candidates=tuple(replace(c, source_artifact_digest=digest) for c in self.design.candidates),
            allow_construction=False, allow_extension=False,
            limits=replace(self.design.limits, max_constructions=0))
        fresh = checked_design(self.problem, design, {digest: result.pair_bytes})
        self.assertEqual(fresh.report["verification"], "valid")
        self.assertEqual(fresh.report["construction_attempts"], 0)
        self.assertEqual(fresh.report["pair_verification_passes"], 1)
        self.assertEqual(fresh.report["rows"], result.report["rows"])

    def test_foreign_pair_artifact_cannot_borrow_new_problem_binding(self):
        result = checked_design(self.problem, self.design, {})
        digest = artifact_digest(result.pair_bytes)
        payload = self.problem.to_payload()
        payload["notes"] = "a separately reviewed problem record"
        problem = normalize_problem(payload)
        design = self.checked_input(problem)
        design = replace(design, candidates=tuple(replace(c, source_artifact_digest=digest) for c in design.candidates))
        with self.assertRaises(AdapterError) as caught:
            checked_design(problem, design, {digest: result.pair_bytes})
        self.assertEqual(caught.exception.code, "wrong_specification_binding")

    def test_historical_band_endpoint_is_closed_but_disjointness_is_strict(self):
        payload = self.problem.to_payload()
        # Both candidates predict exactly zero at t=0; the allowed band [0,2]
        # contains that boundary point. A positive rational shift excludes it.
        payload["observations"][0].update(value="1/1", allowance="1/1")
        problem = normalize_problem(payload)
        valid = checked_design(problem, self.checked_input(problem), {}).report
        self.assertEqual(valid["verification"], "valid")
        payload["observations"][0]["value"] = "100000000000000000001/100000000000000000000"
        problem = normalize_problem(payload)
        invalid = checked_design(problem, self.checked_input(problem), {}).report
        self.assertEqual(invalid["verification"], "invalid")
        self.assertTrue(all(c["reason_code"] == "measurement_incompatible" for c in invalid["candidate_results"]))
        self.assertTrue(all(not c["is_counterexample"] for c in invalid["candidate_results"]))
        self.assertTrue(all(row["status"] == "unavailable" for row in invalid["rows"]))

    def test_overlapping_insufficient_enclosures_are_inconclusive(self):
        payload = self.problem.to_payload()
        lower, upper = concentration_interval(Q(4), Q(1, 5), Q(3, 2), Q(1))
        payload["observations"][1].update(value=rational_text((lower + upper) / 2),
                                            allowance=rational_text((upper - lower) / 4))
        problem = normalize_problem(payload)
        design = self.checked_input(problem)
        second = replace(design.candidates[1], parameters=(Q(4) + Q(1, 10**50), Q(1, 5), Q(3, 2)))
        design = replace(design, candidates=(design.candidates[0], second))
        result = checked_design(problem, design, {}).report
        self.assertEqual(result["verification"], "inconclusive")
        self.assertEqual(result["tier"], "unavailable")
        self.assertTrue(all(c["reason_code"] == "insufficient_enclosure" for c in result["candidate_results"]))
        self.assertTrue(all(not c["is_counterexample"] for c in result["candidate_results"]))


if __name__ == "__main__":
    unittest.main()
