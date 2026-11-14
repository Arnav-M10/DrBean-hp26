"""Historical evidence controls; fixed realistic vectors exist only as test oracles."""

from copy import deepcopy
from dataclasses import replace
from decimal import Decimal, localcontext
from fractions import Fraction as Q
import json
import unittest
from unittest.mock import patch

from counterdex.analytical import concentration_interval
from counterdex.errors import AdapterError
from counterdex.exact import canonical_bytes, rational_text
from counterdex.historical import (HISTORICAL_PROFILE, construct_historical_certificate,
                                  evaluate_historical_candidate, normalize_candidates,
                                  verify_historical_certificate)
from counterdex.models import FixedCandidate, normalize_problem
from counterdex.resource import ExecutionContext
from helpers import synthetic_inputs, synthetic_problem_payload


def realistic_problem():
    payload = synthetic_problem_payload()
    payload["domain"] = {"A": ["0.001", "30"], "ke": ["0.015", "0.35"], "ka": ["0.4", "8"]}
    payload["claim"]["interval"] = ["0.10", "0.17"]
    source = payload["observations"][0]
    payload["observations"] = [
        dict(source, id=f"controlled-{index}", time=time, value=value, allowance="0.5")
        for index, (time, value) in enumerate((("0.25", "4.8"), ("0.5", "7.2"),
                                             ("1", "8.0"), ("2", "6.8"), ("4", "5.7")))
    ]
    payload["notes"] = "Controlled synthetic experiment; no claim of observed or literature measurements"
    return normalize_problem(payload)


def oracle_candidates(problem):
    return tuple(FixedCandidate(cid, problem.digest, tuple(map(Q, vector)), None)
                 for cid, vector in (("reference", ("9.041075603155", "0.122", "3.54")),
                                     ("outside", ("8.267973235218", "0.074", "4.17"))))


def rebind(candidates, problem):
    return tuple(replace(candidate, problem_digest=problem.digest) for candidate in candidates)


class HistoricalEvidenceTests(unittest.TestCase):
    def assert_code(self, code, callback, *args, **kwargs):
        with self.assertRaises(AdapterError) as caught:
            callback(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def test_realistic_exact_oracles_and_independent_decimal_diagnostics(self):
        problem = realistic_problem()
        candidates = oracle_candidates(problem)
        certificate = construct_historical_certificate(problem, candidates)
        report = verify_historical_certificate(certificate, problem, candidates)
        self.assertEqual(report["verification"], "valid")
        self.assertEqual(report["historical_compatibility"], "valid")
        self.assertEqual(json.loads(certificate)["schema_version"], HISTORICAL_PROFILE)
        self.assertEqual(set(json.loads(certificate)), {"schema_version", "proof_rule", "model", "problem_digest", "candidates"})
        by_id = {row["candidate_id"]: row for row in report["candidate_results"]}
        self.assertTrue(by_id["outside"]["is_counterexample"])
        self.assertFalse(by_id["reference"]["outside_closed_claim"])
        with localcontext() as context:
            context.prec = 100
            for candidate in candidates:
                A, ke, ka = (Decimal(x.numerator) / Decimal(x.denominator) for x in candidate.parameters)
                for observed, checked in zip(problem.observations, by_id[candidate.id]["rows"]):
                    time = Decimal(observed.time.numerator) / Decimal(observed.time.denominator)
                    prediction = A * ((-ke * time).exp() - (-ka * time).exp())
                    lo, hi = Q(checked["lower"]), Q(checked["upper"])
                    self.assertLessEqual(Decimal(lo.numerator) / Decimal(lo.denominator), prediction)
                    self.assertGreaterEqual(Decimal(hi.numerator) / Decimal(hi.denominator), prediction)
                    measurement = Decimal(observed.value.numerator) / Decimal(observed.value.denominator)
                    self.assertLessEqual(abs(prediction - measurement), Decimal("0.5"))
                    self.assertEqual(checked["status"], "compatible")
                    self.assertEqual(Q(checked["residual_lower"]), lo - observed.value)
                    self.assertEqual(Q(checked["residual_upper"]), hi - observed.value)

    def test_one_candidate_needs_no_design_and_ke_endpoints_are_inside(self):
        problem, design = synthetic_inputs()
        for ke in problem.claim:
            candidate = replace(design.candidates[0], parameters=(Q(10), ke, Q(2)))
            report = evaluate_historical_candidate(problem, candidate)
            self.assertEqual(report["verification"], "valid")
            self.assertFalse(report["outside_closed_claim"])
            self.assertFalse(report["is_counterexample"])
            certificate = construct_historical_certificate(problem, [candidate])
            self.assertEqual(len(verify_historical_certificate(certificate, problem, [candidate])["candidate_results"]), 1)

    def test_heterogeneous_allowances_and_excluded_rows_are_preserved(self):
        problem, design = synthetic_inputs()
        payload = problem.to_payload()
        payload["observations"].append(dict(payload["observations"][1], id="excluded", time="1000000", value="999999", allowance="1/1000000", included=False))
        payload["observations"][2]["value"] = "1/1"
        payload["observations"][2]["allowance"] = "1/1000"
        changed = normalize_problem(payload)
        candidate = rebind(design.candidates, changed)[0]
        report = evaluate_historical_candidate(changed, candidate)
        self.assertEqual(report["reason_code"], "measurement_incompatible")
        self.assertEqual(report["violating_observation_ids"], ["synthetic-2"])
        self.assertEqual(report["rows"][-1]["status"], "excluded")
        self.assertIsNone(report["rows"][-1]["lower"])
        self.assertEqual(report["rows"][-1]["allowance"], "1/1000000")
        certificate = construct_historical_certificate(changed, [candidate])
        self.assertEqual(len(json.loads(certificate)["candidates"][0]["samples"]), 3)
        verified = verify_historical_certificate(certificate, changed, [candidate])
        self.assertEqual(verified["verification"], "valid")
        self.assertEqual(verified["historical_compatibility"], "invalid")

    def test_duplicate_times_keep_individual_row_constraints(self):
        problem, design = synthetic_inputs()
        payload = problem.to_payload()
        payload["observations"].append(dict(payload["observations"][1], id="same-time-tight", value="1", allowance="0.01"))
        changed = normalize_problem(payload)
        candidate = rebind(design.candidates, changed)[0]
        report = evaluate_historical_candidate(changed, candidate)
        self.assertEqual(report["violating_observation_ids"], ["same-time-tight"])
        certificate = construct_historical_certificate(changed, [candidate])
        self.assertEqual(len(json.loads(certificate)["candidates"][0]["samples"]), 3)

    def test_hard_measurement_endpoint_equality_is_compatible(self):
        problem, design = synthetic_inputs()
        payload = problem.to_payload()
        payload["observations"][0].update(value="-1", allowance="1")
        changed = normalize_problem(payload)
        report = evaluate_historical_candidate(changed, rebind(design.candidates, changed)[0])
        self.assertEqual(report["verification"], "valid")
        self.assertEqual(report["rows"][0]["upper"], "0/1")

    def test_inconclusive_enclosure_is_distinct_from_incompatibility(self):
        problem, design = synthetic_inputs()
        lower, upper = concentration_interval(*design.candidates[0].parameters, Q(1))
        self.assertLess(lower, upper)
        payload = problem.to_payload()
        payload["observations"][1].update(value=rational_text((lower + upper) / 2),
                                          allowance=rational_text((upper - lower) / 4))
        changed = normalize_problem(payload)
        candidate = rebind(design.candidates, changed)[0]
        report = evaluate_historical_candidate(changed, candidate)
        self.assertEqual(report["verification"], "inconclusive")
        self.assertEqual(report["reason_code"], "insufficient_enclosure")
        self.assertEqual(report["unresolved_observation_ids"], ["synthetic-1"])
        self.assertEqual(report["violating_observation_ids"], [])
        self.assertFalse(report["is_counterexample"])
        verified = verify_historical_certificate(construct_historical_certificate(changed, [candidate]), changed, [candidate])
        self.assertEqual(verified["verification"], "valid")
        self.assertEqual(verified["historical_compatibility"], "inconclusive")

    def test_hypothetical_followup_one_survives_or_both_excluded(self):
        original = realistic_problem()
        candidates = oracle_candidates(original)
        for value, expected in (("3.4", {"reference": "valid", "outside": "invalid"}),
                                ("4.57", {"reference": "invalid", "outside": "valid"}),
                                ("4.0", {"reference": "invalid", "outside": "invalid"})):
            with self.subTest(value=value):
                payload = original.to_payload()
                payload["observations"].append(dict(payload["observations"][0], id="followup-8h", time="8", value=value,
                                                     allowance="0.2", origin="hypothetical"))
                changed = normalize_problem(payload)
                self.assertNotEqual(changed.digest, original.digest)
                selected = rebind(candidates, changed)
                report = verify_historical_certificate(construct_historical_certificate(changed, selected), changed, selected)
                self.assertEqual(report["verification"], "valid")
                self.assertEqual({r["candidate_id"]: r["verification"] for r in report["candidate_results"]}, expected)
                for row in report["candidate_results"]:
                    if row["verification"] == "invalid":
                        self.assertEqual(row["violating_observation_ids"], ["followup-8h"])
        self.assertEqual(len(original.observations), 5)

    def test_wrong_problem_and_changed_excluded_metadata_do_not_replay(self):
        problem, design = synthetic_inputs()
        certificate = construct_historical_certificate(problem, design.candidates)
        changed = replace(problem, notes="A different reviewed specification")
        self.assert_code("wrong_specification_binding", evaluate_historical_candidate, changed, design.candidates[0])
        self.assert_code("wrong_specification_binding", verify_historical_certificate, certificate, changed, rebind(design.candidates, changed))
        payload = problem.to_payload()
        payload["observations"].append(dict(payload["observations"][0], id="unused", included=False))
        excluded = normalize_problem(payload)
        bound = rebind(design.candidates, excluded)
        certificate = construct_historical_certificate(excluded, bound)
        payload["observations"][-1]["notes"] = "Reviewed exclusion reason changed"
        changed = normalize_problem(payload)
        self.assert_code("wrong_specification_binding", verify_historical_certificate, certificate, changed, rebind(bound, changed))

    def test_altered_bounds_are_failed_evidence_not_excluded_candidates(self):
        problem, design = synthetic_inputs()
        certificate = json.loads(construct_historical_certificate(problem, design.candidates))
        certificate["candidates"][0]["samples"][1]["lower"] = "0/1"
        self.assert_code("exact_check_failure", verify_historical_certificate, canonical_bytes(certificate), problem, design.candidates)

    def test_expected_candidate_ids_vectors_and_count_are_independent_anchors(self):
        problem, design = synthetic_inputs()
        certificate = construct_historical_certificate(problem, design.candidates)
        changes = ((replace(design.candidates[0], id="other-id"), design.candidates[1]),
                   (replace(design.candidates[0], parameters=(Q(11), Q("0.1"), Q(2))), design.candidates[1]),
                   (design.candidates[0],))
        for selected in changes:
            self.assert_code("candidate_mismatch", verify_historical_certificate, certificate, problem, selected)
        parsed = json.loads(certificate)
        parsed["candidates"][1] = deepcopy(parsed["candidates"][0])
        self.assert_code("candidate_mismatch", verify_historical_certificate, canonical_bytes(parsed), problem, design.candidates)

    def test_malformed_or_incomplete_certificates_never_produce_a_verdict(self):
        problem, design = synthetic_inputs()
        original = json.loads(construct_historical_certificate(problem, design.candidates))
        variants = []
        for mutate in (lambda p: p.update(verdict="valid"),
                       lambda p: p["candidates"][0]["samples"].pop(),
                       lambda p: p["candidates"][0]["samples"].reverse(),
                       lambda p: p["candidates"][0]["samples"][0].update(lower="not an exact value")):
            altered = deepcopy(original)
            mutate(altered)
            variants.append(canonical_bytes(altered))
        variants.extend((b"", b'{"duplicate":1,"duplicate":2}', b'{"value":0.5}'))
        for content in variants:
            self.assert_code("invalid_certificate", verify_historical_certificate, content, problem, design.candidates)

    def test_certificate_profile_and_proof_rule_are_pinned(self):
        problem, design = synthetic_inputs()
        certificate = json.loads(construct_historical_certificate(problem, design.candidates))
        for key in ("schema_version", "proof_rule", "model"):
            altered = dict(certificate, **{key: "another-rule"})
            self.assert_code("unsupported_model", verify_historical_certificate, canonical_bytes(altered), problem, design.candidates)

    def test_actual_and_hypothetical_labels_change_the_expected_binding(self):
        hypothetical, design = synthetic_inputs()
        certificate = construct_historical_certificate(hypothetical, design.candidates)
        payload = hypothetical.to_payload()
        payload["dataset_kind"] = "actual"
        self.assert_code("unsupported_model", normalize_problem, payload)
        for row in payload["observations"]:
            row["origin"] = "actual"
        actual = normalize_problem(payload)
        selected = rebind(design.candidates, actual)
        self.assert_code("wrong_specification_binding", verify_historical_certificate, certificate, actual, selected)
        fresh = verify_historical_certificate(construct_historical_certificate(actual, selected), actual, selected)
        self.assertEqual(fresh["historical_compatibility"], "valid")

    def test_arithmetic_range_failure_is_not_compatibility_or_bad_certificate(self):
        problem, design = synthetic_inputs()
        payload = problem.to_payload()
        payload["observations"][2]["time"] = "1000"
        changed = normalize_problem(payload)
        selected = rebind(design.candidates, changed)
        self.assert_code("construction_range", evaluate_historical_candidate, changed, selected[0])

    def test_candidate_admission_rejects_ambiguity_and_malformed_direct_objects(self):
        problem, design = synthetic_inputs()
        candidates = design.candidates
        self.assertEqual(normalize_candidates(problem, [c.to_payload() for c in candidates]), candidates)
        for selected in ((), candidates + (candidates[0],), (candidates[0], candidates[0]),
                         (candidates[0], replace(candidates[0], id="duplicate-vector"))):
            self.assert_code("candidate_mismatch", construct_historical_certificate, problem, selected)
        for candidate in (replace(candidates[0], parameters=(Q(1), Q(2))),
                          replace(candidates[0], parameters=(10, Q("0.1"), Q(2))),
                          replace(candidates[0], parameters=[Q(10), Q("0.1"), Q(2)])):
            self.assert_code("invalid_input", evaluate_historical_candidate, problem, candidate)
        self.assert_code("candidate_mismatch", evaluate_historical_candidate, problem,
                         replace(candidates[0], parameters=(Q(30), Q("0.1"), Q(2))))
        self.assert_code("invalid_input", evaluate_historical_candidate, replace(problem, domain=problem.domain + (problem.domain[0],)), candidates[0])
        payload = [candidates[0].to_payload()]
        payload[0]["source_artifact_digest"] = "file:///not-a-digest"
        self.assert_code("invalid_input", normalize_candidates, problem, payload)

    def test_cancellation_stops_before_remaining_exact_samples(self):
        problem, design = synthetic_inputs()
        visits = [0]
        def cancel():
            visits[0] += 1
            return visits[0] >= 3
        context = ExecutionContext(cancelled=cancel)
        with patch("counterdex.historical.concentration_interval", wraps=concentration_interval) as compute:
            self.assert_code("cancelled", evaluate_historical_candidate, problem, design.candidates[0], context)
            self.assertEqual(compute.call_count, 1)
            self.assert_code("cancelled", construct_historical_certificate, problem, design.candidates, context)
            self.assertEqual(compute.call_count, 1)

    def test_verification_cancellation_and_elapsed_wall_limit_are_distinct(self):
        problem, design = synthetic_inputs()
        certificate = construct_historical_certificate(problem, design.candidates)
        self.assert_code("cancelled", verify_historical_certificate, certificate, problem, design.candidates,
                         ExecutionContext(cancelled=lambda: True))
        ticks = iter((0.0, 0.2, 0.8, 1.1))
        context = ExecutionContext(wall_seconds=120, clock=lambda: next(ticks))
        self.assert_code("resource_exhaustion", evaluate_historical_candidate, problem, design.candidates[0], context, wall_seconds=1)
        self.assert_code("resource_exhaustion", construct_historical_certificate, problem, design.candidates, context)

    def test_byte_and_wall_caps_are_enforced(self):
        problem, design = synthetic_inputs()
        certificate = construct_historical_certificate(problem, design.candidates)
        self.assert_code("resource_exhaustion", construct_historical_certificate, problem, design.candidates, max_bytes=1)
        self.assert_code("resource_exhaustion", verify_historical_certificate, certificate, problem, design.candidates, max_bytes=len(certificate) - 1)
        for wall_seconds in (True, 0, 121, float("nan")):
            self.assert_code("invalid_input", evaluate_historical_candidate, problem, design.candidates[0], wall_seconds=wall_seconds)
        for max_bytes in (True, 0, 2 * 1024 * 1024 + 1):
            self.assert_code("invalid_input", construct_historical_certificate, problem, design.candidates, max_bytes=max_bytes)

    def test_canonical_construction_is_independent_of_candidate_display_order(self):
        problem, design = synthetic_inputs()
        first = construct_historical_certificate(problem, design.candidates)
        second = construct_historical_certificate(problem, tuple(reversed(design.candidates)))
        self.assertEqual(first, second)
        report = verify_historical_certificate(first, problem, tuple(reversed(design.candidates)))
        self.assertEqual([row["candidate_id"] for row in report["candidate_results"]], sorted(c.id for c in design.candidates))


if __name__ == "__main__":
    unittest.main()
