"""Portable analytic evidence, independent anchors, and hostile stored reports."""

import base64
from copy import deepcopy
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from counterdex.exact import artifact_digest, canonical_bytes, semantic_digest, strict_json_loads
from counterdex.errors import AdapterError
from counterdex.models import normalize_design
from counterdex.pipeline import create_suggestion
from counterdex.replay import replay_bundle
from counterdex.resource import ExecutionContext

from helpers import synthetic_inputs


WORKFLOW = {"plan_id": "fixture-plan", "approval_id": "fixture-approval",
            "operation_id": "fixture-operation", "execution_id": "fixture-execution"}


class ReplayControls(unittest.TestCase):
    def setUp(self):
        self.problem, self.design = synthetic_inputs()
        self.packet = self.create()
        self.bundle = strict_json_loads(self.packet)

    def create(self, design=None, **kwargs):
        design = design or self.design
        return create_suggestion(self.problem.to_payload(), design.to_payload(),
            expected_problem_digest=self.problem.digest, expected_design_digest=design.digest,
            workflow=WORKFLOW, **kwargs)

    def replay(self, packet=None, expected_digest=None, expected_problem=None, **kwargs):
        packet = self.packet if packet is None else packet
        anchor = strict_json_loads(packet)["suggestion_digest"] if expected_digest is None else expected_digest
        return replay_bundle(packet, expected_problem_digest=self.problem.digest if expected_problem is None else expected_problem,
                             expected_suggestion_digest=anchor, **kwargs)

    def reseal(self, bundle):
        """Control deliberately supplies a new anchor to exercise fresh checking."""
        body = {key: value for key, value in bundle.items() if key != "suggestion_digest"}
        bundle["suggestion_digest"] = semantic_digest("suggestion", body)
        return canonical_bytes(bundle)

    def assert_code(self, code, function, *args, **kwargs):
        with self.assertRaises(AdapterError) as caught:
            function(*args, **kwargs)
        self.assertEqual(caught.exception.code, code)

    def design_with(self, change):
        payload = self.design.to_payload()
        change(payload)
        return normalize_design(payload, self.problem)

    def test_complete_checked_packet_has_fresh_portable_exact_result(self):
        bundle = self.bundle
        self.assertEqual(bundle["workflow"], WORKFLOW)
        self.assertEqual(bundle["problem"], self.problem.to_payload())
        self.assertEqual(bundle["design"], self.design.to_payload())
        self.assertEqual(bundle["report"]["numerical"]["evaluated_count"], 2)
        self.assertEqual(bundle["report"]["tier"], "checked_pair_separation")
        self.assertEqual(len(bundle["artifacts"]), 1)
        result = self.replay()
        self.assertEqual(result["replay"], "passed")
        self.assertEqual(result["scope"], "analytic_fixed_pair")
        self.assertEqual(result["integrity"], "passed")
        self.assertTrue(result["recorded_result_matches"])
        self.assertEqual(result["fresh_checked"]["selected_time"], "6/1")
        stored = {key: value for key, value in bundle["report"]["checked"].items()
                  if key not in ("construction_attempts", "pair_verification_passes")}
        self.assertEqual(result["fresh_checked"], stored)
        self.assertEqual(self.replay(), result)

    def test_complete_numeric_packet_reports_integrity_only(self):
        design = self.design_with(lambda d: d.__setitem__("requested_tier", "numerical_guidance"))
        packet = self.create(design)
        bundle = strict_json_loads(packet)
        self.assertEqual(bundle["artifacts"], [])
        self.assertEqual(bundle["report"]["tier"], "numerical_guidance")
        self.assertEqual(bundle["report"]["checked"]["verification"], "not_checked")
        result = self.replay(packet)
        self.assertEqual(result["integrity"], "passed")
        self.assertEqual(result["verification"], "not_checked")
        self.assertEqual(result["replay"], "unsupported")
        self.assertEqual(result["reason_code"], "numerical_only")

    def test_external_anchor_is_required_even_for_self_consistent_bytes(self):
        self.assert_code("artifact_mismatch", self.replay, expected_digest="0" * 64)
        modified = deepcopy(self.bundle)
        modified["workflow"]["execution_id"] = "fixture-other-execution"
        packet = self.reseal(modified)
        self.assert_code("artifact_mismatch", self.replay, packet, self.bundle["suggestion_digest"])
        self.assertEqual(self.replay(packet)["replay"], "passed")

    def test_wrong_problem_and_design_anchor_fail(self):
        self.assert_code("wrong_specification_binding", self.replay, expected_problem="0" * 64)
        modified = deepcopy(self.bundle)
        modified["problem"]["notes"] += " changed reviewed input"
        self.assert_code("wrong_specification_binding", self.replay, self.reseal(modified))
        self.assert_code("wrong_specification_binding", create_suggestion,
            self.problem.to_payload(), self.design.to_payload(), expected_problem_digest=self.problem.digest,
            expected_design_digest="0" * 64, workflow=WORKFLOW)

    def test_forged_stored_separation_recomputes_and_mismatches(self):
        modified = deepcopy(self.bundle)
        modified["report"]["checked"]["rows"][0]["separated"] = False
        result = self.replay(self.reseal(modified))
        self.assertEqual(result["verification"], "valid")
        self.assertEqual(result["replay"], "failed")
        self.assertFalse(result["recorded_result_matches"])
        self.assertEqual(result["reason_code"], "recorded_result_mismatch")
        self.assertTrue(result["fresh_checked"]["rows"][0]["separated"])

    def test_forged_selected_time_does_not_change_fresh_ranking(self):
        modified = deepcopy(self.bundle)
        modified["report"]["checked"]["selected_time"] = "8/1"
        result = self.replay(self.reseal(modified))
        self.assertEqual(result["replay"], "failed")
        self.assertFalse(result["recorded_result_matches"])
        self.assertEqual(result["fresh_checked"]["selected_time"], "6/1")

    def test_positive_badge_cannot_promote_nonseparating_pair(self):
        design = self.design_with(lambda d: d.__setitem__("future_allowance", "10/1"))
        modified = strict_json_loads(self.create(design))
        self.assertEqual(modified["report"]["checked"]["tier"], "no_separation_established")
        modified["report"]["checked"].update(tier="checked_pair_separation", selected_time="6/1")
        modified["report"]["checked"]["rows"][0]["separated"] = True
        result = self.replay(self.reseal(modified))
        self.assertEqual(result["replay"], "failed")
        self.assertEqual(result["fresh_checked"]["tier"], "no_separation_established")
        self.assertIsNone(result["fresh_checked"]["selected_time"])
        self.assertFalse(any(row["separated"] for row in result["fresh_checked"]["rows"]))

    def test_changed_pair_bytes_fail_their_raw_hash(self):
        modified = deepcopy(self.bundle)
        artifact = modified["artifacts"][0]
        raw = base64.b64decode(artifact["content"])
        artifact["content"] = base64.b64encode(raw + b" ").decode("ascii")
        self.assert_code("artifact_mismatch", self.replay, self.reseal(modified))

    def test_missing_pair_bytes_block_scientific_replay(self):
        modified = deepcopy(self.bundle)
        modified["artifacts"] = []
        self.assert_code("incomplete_export", self.replay, self.reseal(modified))

    def test_reused_source_pair_remains_complete_and_fresh(self):
        source = self.bundle["artifacts"][0]
        content = base64.b64decode(source["content"])
        payload = self.design.to_payload()
        for candidate in payload["candidates"]:
            candidate["source_artifact_digest"] = source["digest"]
        payload["limits"]["max_constructions"] = 0
        payload["horizon_policy"].update(allow_construction=False, allow_extension=False)
        design = normalize_design(payload, self.problem)
        with patch("counterdex.checked.construct_pair", side_effect=AssertionError("unexpected construction")):
            packet = self.create(design, artifacts={source["digest"]: content})
        bundle = strict_json_loads(packet)
        self.assertEqual(bundle["report"]["checked"]["construction_attempts"], 0)
        self.assertEqual(len(bundle["artifacts"]), 1)
        self.assertEqual(self.replay(packet)["replay"], "passed")
        bundle["artifacts"] = []
        self.assert_code("incomplete_export", self.replay, self.reseal(bundle))

    def test_unrelated_source_blob_cannot_authorize_an_unreferenced_valid_pair(self):
        unrelated = b"Synthetic unrelated artifact content, not analytic pair evidence."
        unrelated_digest = artifact_digest(unrelated)
        for partial_reference in (False, True):
            with self.subTest(partial_reference=partial_reference):
                modified = deepcopy(self.bundle)
                modified["artifacts"].append({"digest": unrelated_digest, "encoding": "base64",
                    "content": base64.b64encode(unrelated).decode("ascii")})
                for index, candidate in enumerate(modified["design"]["candidates"]):
                    candidate["source_artifact_digest"] = None if partial_reference and index == 1 else unrelated_digest
                modified["design"]["horizon_policy"].update(allow_construction=False, allow_extension=False)
                modified["design"]["limits"]["max_constructions"] = 0
                design = normalize_design(modified["design"], self.problem)
                modified["report"]["design_digest"] = design.digest
                modified["report"]["checked"]["construction_attempts"] = 0
                # Both raw hashes and the external suggestion anchor now agree.
                # The existing valid pair still does not match selected sources.
                self.assert_code("candidate_mismatch", self.replay, self.reseal(modified))

    def test_new_pair_cannot_exceed_declared_construction_or_extension_scope(self):
        for construction, extension in ((False, False), (True, False)):
            with self.subTest(construction=construction, extension=extension):
                modified = deepcopy(self.bundle)
                modified["design"]["horizon_policy"].update(
                    allow_construction=construction, allow_extension=extension)
                design = normalize_design(modified["design"], self.problem)
                modified["report"]["design_digest"] = design.digest
                # A plausible claimed work count does not supply missing scope.
                modified["report"]["checked"]["construction_attempts"] = 2
                self.assert_code("recorded_result_mismatch", self.replay, self.reseal(modified))

    def test_usage_counters_reject_booleans_and_values_above_approved_caps(self):
        numerical_design = self.design_with(lambda d: d.__setitem__("requested_tier", "numerical_guidance"))
        numerical_bundle = strict_json_loads(self.create(numerical_design))
        for base in (self.bundle, numerical_bundle):
            for key in ("construction_attempts", "pair_verification_passes"):
                for value in (True, False, 3, None):
                    with self.subTest(tier=base["report"]["tier"], key=key, value=value):
                        modified = deepcopy(base)
                        modified["report"]["checked"][key] = value
                        self.assert_code("invalid_input", self.replay, self.reseal(modified))

    def test_usage_counts_match_fixed_producer_profile(self):
        for key, value in (("construction_attempts", 0), ("construction_attempts", 1),
                           ("pair_verification_passes", 0), ("pair_verification_passes", 2)):
            with self.subTest(key=key, value=value):
                modified = deepcopy(self.bundle)
                modified["report"]["checked"][key] = value
                self.assert_code("recorded_result_mismatch", self.replay, self.reseal(modified))

    def test_usage_counters_respect_a_smaller_reviewed_budget(self):
        modified = deepcopy(self.bundle)
        modified["design"]["limits"]["max_constructions"] = 1
        design = normalize_design(modified["design"], self.problem)
        modified["report"]["design_digest"] = design.digest
        self.assert_code("invalid_input", self.replay, self.reseal(modified))

    def test_partial_cancellation_preserves_every_time_and_completed_rows(self):
        calls = 0

        def cancelled():
            nonlocal calls
            calls += 1
            return calls >= 2

        packet = self.create(context=ExecutionContext(cancelled=cancelled))
        bundle = strict_json_loads(packet)
        report = bundle["report"]
        self.assertEqual(report["execution"], "cancelled")
        self.assertEqual(report["tier"], "numerical_guidance")
        self.assertTrue(report["numerical"]["partial"])
        self.assertEqual(report["numerical"]["evaluated_count"], 1)
        self.assertEqual(report["numerical"]["ranked_times"], ["6/1"])
        self.assertEqual([row["time"] for row in report["numerical"]["rows"]], ["6/1", "8/1"])
        self.assertEqual([row["status"] for row in report["numerical"]["rows"]], ["evaluated", "skipped"])
        self.assertEqual(report["numerical"]["rows"][1]["reason_code"], "cancelled")
        self.assertEqual(report["checked"]["reason_code"], "cancelled")
        self.assertIsNone(report["checked"]["pair_digest"])
        self.assertEqual(bundle["artifacts"], [])
        result = self.replay(packet)
        self.assertEqual(result["replay"], "unsupported")
        self.assertEqual(result["reason_code"], "incomplete_export")

    def test_unsupported_rule_is_not_selected_by_artifact_metadata(self):
        modified = deepcopy(self.bundle)
        artifact = modified["artifacts"][0]
        pair = strict_json_loads(base64.b64decode(artifact["content"]))
        pair["proof_rule"] = "unqualified-proof-rule.v1"
        raw = canonical_bytes(pair)
        artifact.update(content=base64.b64encode(raw).decode("ascii"), digest=artifact_digest(raw))
        modified["report"]["checked"]["pair_digest"] = artifact["digest"]
        self.assert_code("unsupported_model", self.replay, self.reseal(modified))

    def test_unsupported_runtime_and_changed_source_pin_fail(self):
        for key, value in (("runtime", "unqualified-runtime"), ("source_digest", "0" * 64),
                           ("source_manifest", [])):
            with self.subTest(key=key):
                modified = deepcopy(self.bundle)
                modified["implementation"][key] = value
                self.assert_code("unsupported_runtime", self.replay, self.reseal(modified))

    def test_invalid_recorded_python_metadata_fails(self):
        for value in ("3.10.1", "3.12.0", "3.11", "3.11.0000", "3.11.1\n", None, False):
            with self.subTest(value=value):
                modified = deepcopy(self.bundle)
                modified["implementation"]["python"] = value
                self.assert_code("unsupported_runtime", self.replay, self.reseal(modified))

    def test_outer_tier_cannot_override_fresh_checked_result(self):
        for tier in ("numerical_guidance", "no_separation_established", "unavailable", "unqualified-tier"):
            with self.subTest(tier=tier):
                modified = deepcopy(self.bundle)
                modified["report"]["tier"] = tier
                result = self.replay(self.reseal(modified))
                self.assertEqual(result["replay"], "failed")
                self.assertEqual(result["reason_code"], "recorded_result_mismatch")
                self.assertFalse(result["recorded_result_matches"])
                self.assertEqual(result["fresh_checked"]["tier"], "checked_pair_separation")

    def test_outer_units_cannot_relabel_exact_scientific_values(self):
        for key, value in (("time", "minutes"), ("concentration", "mmol/L"), ("score", "probability")):
            with self.subTest(key=key):
                modified = deepcopy(self.bundle)
                modified["report"]["units"][key] = value
                self.assert_code("invalid_input", self.replay, self.reseal(modified))

    def test_complete_packet_overhead_counts_toward_byte_cap(self):
        pair_size = len(base64.b64decode(self.bundle["artifacts"][0]["content"]))
        self.assertGreater(len(self.packet), pair_size)
        design = self.design_with(lambda d: d["limits"].__setitem__("max_bundle_bytes", pair_size))
        self.assert_code("resource_exhaustion", self.create, design)
        modified = deepcopy(self.bundle)
        modified["design"] = design.to_payload()
        modified["report"]["design_digest"] = design.digest
        self.assert_code("resource_exhaustion", self.replay, self.reseal(modified))

    def test_native_replay_imports_no_numerical_provider_or_network_module(self):
        script = r'''
import importlib.abc
import json
import sys

forbidden = ("counterdex.numerical", "counterdex.pipeline", "numpy", "scipy",
             "matplotlib", "google", "openai", "anthropic", "deepagents", "requests", "httpx",
             "aiohttp", "socket", "ssl", "urllib.request", "urllib.response", "http.client")

class DenyImports(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == prefix or fullname.startswith(prefix + ".") for prefix in forbidden):
            raise ImportError("Forbidden exact replay import: " + fullname)

sys.meta_path.insert(0, DenyImports())
from counterdex.replay import replay_bundle
with open(sys.argv[1], "rb") as source:
    result = replay_bundle(source.read(), expected_problem_digest=sys.argv[2],
                           expected_suggestion_digest=sys.argv[3])
loaded = [name for name in sys.modules if any(name == prefix or name.startswith(prefix + ".")
                                             for prefix in forbidden)]
if loaded:
    raise AssertionError("Forbidden imported modules: " + ",".join(loaded))
print(json.dumps({"replay": result["replay"], "verification": result["verification"],
                  "selected_time": result["fresh_checked"]["selected_time"]}))
'''
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(Path(__file__).resolve().parents[1])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic-suggestion.json"
            path.write_bytes(self.packet)
            done = subprocess.run([sys.executable, "-c", script, str(path), self.problem.digest,
                                   self.bundle["suggestion_digest"]], env=environment,
                                  capture_output=True, text=True, timeout=10)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('"replay": "passed"', done.stdout)
        self.assertIn('"verification": "valid"', done.stdout)
        self.assertIn('"selected_time": "6/1"', done.stdout)


if __name__ == "__main__":
    unittest.main()
