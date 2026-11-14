"""Real bounded discovery and independently anchored historical replay controls."""

import base64
from copy import deepcopy
from dataclasses import replace
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import counterdex
from counterdex.baseline import create_baseline
from counterdex.errors import AdapterError
from counterdex.exact import artifact_digest, canonical_bytes, semantic_digest, strict_json_loads
from counterdex.models import normalize_problem
from counterdex.replay_baseline import replay_baseline
from counterdex.resource import ExecutionContext
from counterdex.search import SearchSettings
from helpers import synthetic_inputs


WORKFLOW = {"plan_id": "baseline-plan", "approval_id": "baseline-approval",
            "operation_id": "baseline-operation", "execution_id": "baseline-execution"}
SCENARIO = "controlled-baseline-scenario"


class BaselineEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.problem, self.design = synthetic_inputs()
        self.settings = SearchSettings(ke_points=12, ka_points=8, max_rate_pairs=96, max_candidates=8).to_payload()
        self.packet = self.create()
        self.bundle = strict_json_loads(self.packet)

    def create(self, problem=None, **kwargs):
        problem = self.problem if problem is None else problem
        kwargs.setdefault("settings", self.settings)
        return create_baseline(problem.to_payload(), expected_problem_digest=problem.digest,
                               scenario_id=SCENARIO, workflow=WORKFLOW, **kwargs)

    def replay(self, packet=None, *, problem=None, digest=None, scenario=SCENARIO, **kwargs):
        packet = self.packet if packet is None else packet
        problem = self.problem if problem is None else problem
        expected = strict_json_loads(packet)["baseline_digest"] if digest is None else digest
        return replay_baseline(packet, expected_problem_digest=problem.digest, expected_baseline_digest=expected,
                               expected_scenario_id=scenario, **kwargs)

    def reseal(self, bundle):
        """An explicit changed diagnostic anchor lets fresh mathematical checks run."""
        bundle["baseline_digest"] = semantic_digest("report", {k: v for k, v in bundle.items() if k != "baseline_digest"})
        return canonical_bytes(bundle)

    def assert_code(self, expected, callback, *args, **kwargs):
        with self.assertRaises(AdapterError) as caught:
            callback(*args, **kwargs)
        self.assertEqual(caught.exception.code, expected)

    def test_arbitrary_supported_input_reaches_real_search_and_exact_replay(self):
        bundle = self.bundle
        self.assertEqual(bundle["operation"], "bounded_discovery")
        self.assertEqual(bundle["problem"], self.problem.to_payload())
        self.assertEqual(bundle["workflow"], WORKFLOW)
        self.assertEqual(bundle["search"]["attempted_count"], 96)
        self.assertEqual(bundle["search"]["settings"], self.settings)
        self.assertGreater(bundle["search"]["feasible_count"], 0)
        self.assertLessEqual(len(bundle["exact_trials"]), 8)
        self.assertEqual(len(bundle["candidates"]), 2)
        self.assertNotEqual(bundle["candidates"][0]["id"], bundle["candidates"][1]["id"])
        self.assertNotEqual(bundle["candidates"][0]["parameters"], bundle["candidates"][1]["parameters"])
        self.assertEqual(bundle["report"]["outcome"]["scientific_outcome"], "certified_counterexample")
        self.assertTrue(bundle["report"]["outcome"]["pair_available"])
        replay = self.replay()
        self.assertEqual(replay["replay"], "passed")
        self.assertEqual(replay["verification"], "valid")
        self.assertFalse(replay["search_replayed"])
        self.assertEqual(replay["candidate_results"], bundle["report"]["checked"]["candidate_results"])
        self.assertEqual(replay["outcome"], bundle["report"]["outcome"])

    def test_full_domain_closed_claim_yields_no_counterexample_without_completeness_claim(self):
        problem = replace(self.problem, claim=self.problem.domain[1])
        packet = self.create(problem)
        bundle = strict_json_loads(packet)
        report = bundle["report"]["outcome"]
        self.assertEqual(report["scientific_outcome"], "no_counterexample_found")
        self.assertEqual(report["counterexample_ids"], [])
        self.assertIn("no completeness", report["scope"])
        self.assertTrue(all(not c["is_counterexample"] for c in bundle["report"]["checked"]["candidate_results"]))
        self.assertEqual(self.replay(packet, problem=problem)["replay"], "passed")

    def test_impossible_measurement_reports_bounded_no_candidate_and_integrity_only(self):
        payload = self.problem.to_payload()
        payload["observations"][0]["value"] = "1"
        problem = normalize_problem(payload)
        packet = self.create(problem)
        bundle = strict_json_loads(packet)
        self.assertEqual(bundle["search"]["feasible_count"], 0)
        self.assertEqual(bundle["search"]["failure_counts"]["amplitude_infeasible"], 96)
        self.assertEqual(bundle["candidates"], [])
        self.assertEqual(bundle["exact_trials"], [])
        self.assertIsNone(bundle["certificate"])
        self.assertIsNone(bundle["report"]["checked"])
        self.assertEqual(bundle["report"]["outcome"]["scientific_outcome"], "no_counterexample_found")
        self.assertFalse(bundle["report"]["outcome"]["pair_available"])
        replay = self.replay(packet, problem=problem)
        self.assertEqual(replay["replay"], "unsupported")
        self.assertEqual(replay["integrity"], "passed")
        self.assertEqual(replay["verification"], "not_checked")

    def test_unresolved_exact_checks_remain_distinct_from_no_candidate_found(self):
        payload = self.problem.to_payload()
        # Numerically near one hour and within source scalar limits, but its
        # exact denominator exceeds the fixed analytic checker's 256-bit cap.
        payload["observations"][1]["time"] = f"{2**300 + 1}/{2**300}"
        problem = normalize_problem(payload)
        packet = self.create(problem)
        bundle = strict_json_loads(packet)
        self.assertGreater(bundle["search"]["feasible_count"], 0)
        self.assertTrue(bundle["exact_trials"])
        self.assertTrue(all(trial["verification"] == "inconclusive" and trial["reason_code"] == "construction_range"
                            for trial in bundle["exact_trials"]))
        self.assertEqual(bundle["report"]["execution"], "completed")
        self.assertIsNone(bundle["report"]["failure_reason"])
        self.assertEqual(bundle["report"]["outcome"]["scientific_outcome"], "inconclusive")
        self.assertEqual(bundle["report"]["outcome"]["reason_code"], "candidate_checks_inconclusive")
        self.assertIsNone(bundle["certificate"])
        fresh = self.replay(packet, problem=problem)
        self.assertEqual(fresh["verification"], "not_checked")
        self.assertEqual(fresh["outcome"]["scientific_outcome"], "inconclusive")
        self.assertEqual(fresh["outcome"]["reason_code"], "candidate_checks_inconclusive")

    def test_single_candidate_budget_keeps_one_native_witness_and_disables_pair(self):
        settings = dict(self.settings, max_candidates=1)
        packet = self.create(settings=settings)
        bundle = strict_json_loads(packet)
        self.assertEqual(len(bundle["candidates"]), 1)
        self.assertEqual(len(bundle["exact_trials"]), 1)
        self.assertEqual(bundle["report"]["outcome"]["scientific_outcome"], "certified_counterexample")
        self.assertFalse(bundle["report"]["outcome"]["pair_available"])
        certificate = strict_json_loads(base64.b64decode(bundle["certificate"]["bytes_base64"]))
        self.assertEqual(len(certificate["candidates"]), 1)
        self.assertEqual(self.replay(packet)["replay"], "passed")

    def test_changed_measurements_change_frozen_candidates_and_native_identity(self):
        payload = self.problem.to_payload()
        payload["observations"][1].update(value="4", allowance="1")
        changed = normalize_problem(payload)
        packet = self.create(changed)
        bundle = strict_json_loads(packet)
        self.assertNotEqual(changed.digest, self.problem.digest)
        self.assertNotEqual(bundle["baseline_digest"], self.bundle["baseline_digest"])
        self.assertNotEqual(bundle["candidates"], self.bundle["candidates"])
        self.assertTrue(all(c["problem_digest"] == changed.digest for c in bundle["candidates"]))
        self.assertEqual(self.replay(packet, problem=changed)["replay"], "passed")

    def test_stopped_context_has_no_checked_claim_and_replays_only_integrity(self):
        packet = self.create(context=ExecutionContext(cancelled=lambda: True))
        bundle = strict_json_loads(packet)
        self.assertEqual(bundle["report"]["execution"], "cancelled")
        self.assertEqual(bundle["report"]["failure_reason"], "cancelled")
        self.assertEqual(bundle["search"]["attempted_count"], 0)
        self.assertEqual(bundle["candidates"], [])
        self.assertIsNone(bundle["certificate"])
        self.assertEqual(bundle["report"]["outcome"]["scientific_outcome"], "inconclusive")
        replay = self.replay(packet)
        self.assertEqual(replay["verification"], "not_checked")
        self.assertEqual(replay["reason_code"], "cancelled")
        self.assert_code("cancelled", self.replay, context=ExecutionContext(cancelled=lambda: True))

    def test_invalid_execution_context_is_not_replaced_by_a_fresh_budget(self):
        unverified = self.create(context=ExecutionContext(cancelled=lambda: True))
        for context in (False, {}, [], object()):
            with self.subTest(context=type(context).__name__):
                self.assert_code("invalid_input", self.create, context=context)
                self.assert_code("invalid_input", self.replay, context=context)
                self.assert_code("invalid_input", self.replay, unverified, context=context)

    def test_independent_problem_scenario_and_complete_bundle_anchors(self):
        self.assert_code("artifact_mismatch", self.replay, digest="0" * 64)
        self.assert_code("wrong_scenario_binding", self.replay, scenario="different-scenario")
        changed_problem = replace(self.problem, notes="A different reviewed problem")
        self.assert_code("wrong_specification_binding", self.replay, problem=changed_problem)
        self.assert_code("wrong_specification_binding", create_baseline, self.problem.to_payload(),
                         expected_problem_digest="0" * 64, scenario_id=SCENARIO, workflow=WORKFLOW,
                         settings=self.settings)
        altered = deepcopy(self.bundle)
        altered["workflow"]["execution_id"] = "altered-execution"
        packet = self.reseal(altered)
        self.assert_code("artifact_mismatch", self.replay, packet, digest=self.bundle["baseline_digest"])

    def test_missing_certificate_cannot_retain_candidate_success(self):
        altered = deepcopy(self.bundle)
        altered["certificate"] = None
        self.assert_code("recorded_result_mismatch", self.replay, self.reseal(altered))
        altered = deepcopy(self.bundle)
        del altered["certificate"]["bytes_base64"]
        self.assert_code("invalid_input", self.replay, self.reseal(altered))

    def test_artifact_hash_is_checked_before_native_math(self):
        altered = deepcopy(self.bundle)
        altered["certificate"]["bytes_base64"] = base64.b64encode(b"different bytes").decode("ascii")
        self.assert_code("artifact_mismatch", self.replay, self.reseal(altered))

    def test_resealed_false_bounds_fail_fresh_mathematical_check(self):
        altered = deepcopy(self.bundle)
        certificate = strict_json_loads(base64.b64decode(altered["certificate"]["bytes_base64"]))
        certificate["candidates"][0]["samples"][1]["lower"] = "0/1"
        content = canonical_bytes(certificate)
        altered["certificate"] = {"sha256": artifact_digest(content), "bytes_base64": base64.b64encode(content).decode("ascii")}
        self.assert_code("exact_check_failure", self.replay, self.reseal(altered))

    def test_resealed_stored_flags_do_not_override_fresh_math(self):
        altered = deepcopy(self.bundle)
        altered["report"]["checked"]["candidate_results"][0]["is_counterexample"] = not altered["report"]["checked"]["candidate_results"][0]["is_counterexample"]
        self.assert_code("recorded_result_mismatch", self.replay, self.reseal(altered))
        altered = deepcopy(self.bundle)
        altered["report"]["outcome"]["pair_available"] = False
        self.assert_code("recorded_result_mismatch", self.replay, self.reseal(altered))

    def test_source_version_and_runtime_records_are_explicitly_checked(self):
        altered = deepcopy(self.bundle)
        altered["implementation"]["source_digest"] = "0" * 64
        self.assert_code("source_version_mismatch", self.replay, self.reseal(altered))
        altered = deepcopy(self.bundle)
        altered["implementation"]["python"] = "3.13.0"
        self.assert_code("unsupported_runtime", self.replay, self.reseal(altered))

    def test_byte_caps_apply_to_complete_envelope(self):
        self.assert_code("resource_exhaustion", self.create, max_bundle_bytes=256)
        altered = deepcopy(self.bundle)
        altered["limits"]["max_bundle_bytes"] = 256
        self.assert_code("resource_exhaustion", self.replay, self.reseal(altered))

    def test_fixed_candidate_review_distinguishes_both_excluded_from_failed_evidence(self):
        payload = self.problem.to_payload()
        payload["observations"].append(dict(payload["observations"][0], id="hypothetical-followup", time="8", value="100", allowance="0.1"))
        changed = normalize_problem(payload)
        selected = tuple(replace(c, problem_digest=changed.digest) for c in self.design.candidates)
        packet = self.create(changed, frozen_candidates=selected)
        bundle = strict_json_loads(packet)
        self.assertEqual(bundle["operation"], "fixed_candidate_review")
        self.assertIsNone(bundle["search"])
        self.assertEqual(bundle["exact_trials"], [])
        self.assertEqual(bundle["report"]["checked"]["verification"], "valid")
        self.assertEqual(bundle["report"]["checked"]["historical_compatibility"], "invalid")
        self.assertEqual(bundle["report"]["outcome"]["scientific_outcome"], "inconclusive")
        self.assertEqual(bundle["report"]["outcome"]["compatible_candidate_ids"], [])
        self.assertFalse(bundle["report"]["outcome"]["pair_available"])
        replay = self.replay(packet, problem=changed)
        self.assertEqual(replay["replay"], "passed")
        self.assertEqual(replay["historical_compatibility"], "invalid")
        self.assertTrue(all(c["verification"] == "invalid" for c in replay["candidate_results"]))

    def test_replay_never_calls_search(self):
        with patch("counterdex.search.search_candidates", side_effect=AssertionError("Replay must not run search")):
            self.assertEqual(self.replay()["replay"], "passed")

    def test_fresh_process_replay_does_not_import_numerical_producers(self):
        package_root = Path(counterdex.__file__).resolve().parent.parent
        env = {"PATH": os.defpath, "PYTHONPATH": str(package_root)}
        script = """
import json
import sys
from counterdex.models import normalize_problem
from counterdex.replay_baseline import replay_baseline
data = sys.stdin.buffer.read()
bundle = json.loads(data)
result = replay_baseline(data, expected_problem_digest=normalize_problem(bundle['problem']).digest,
    expected_baseline_digest=bundle['baseline_digest'], expected_scenario_id=bundle['scenario_id'])
assert result['replay'] == 'passed'
assert 'counterdex.search' not in sys.modules
assert 'counterdex.numerical' not in sys.modules
print(result['replay'])
"""
        completed = subprocess.run([sys.executable, "-c", script], input=self.packet, env=env,
                                   cwd="/tmp", capture_output=True, timeout=15, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr.decode())
        self.assertEqual(completed.stdout, b"passed\n")


if __name__ == "__main__":
    unittest.main()
