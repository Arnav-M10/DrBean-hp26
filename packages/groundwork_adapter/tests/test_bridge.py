"""Actual bounded search, design and native replay through the JSON bridge.

These synthetic observations exercise application-shaped inputs. Candidate
vectors always come from the actual discovery result, never a fixed pair.
"""
import base64
from copy import deepcopy
from fractions import Fraction
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import counterdex
from counterdex.analytical import concentration_interval
from counterdex.errors import AdapterError
from counterdex.exact import artifact_digest, canonical_bytes, rational_text, semantic_digest, strict_json_loads
from counterdex.native_packet import packet_anchors, replay_packet
from test_application import application_records, rebind


PROTOCOL = "counterdex.bridge.v1"
PACKAGE = Path(counterdex.__file__).resolve().parent.parent


def workflow(suffix):
    return {key: key + "_" + suffix for key in ("plan_id", "approval_id", "operation_id", "execution_id")}


def investigation_request(problem, dataset, *, suffix="baseline", search_settings=None):
    return {"protocol": PROTOCOL, "operation": "investigate", "problem": deepcopy(problem),
            "dataset": deepcopy(dataset), "run_id": "run_" + suffix, "scenario_id": "scenario_synthetic",
            "workflow": workflow(suffix), "limits": {"wall_seconds": 120, "max_bundle_bytes": 4194304},
            "search_settings": search_settings}


def artifact_from(response):
    artifact = response["native_artifacts"][0]
    return {key: artifact[key] for key in ("id", "sha256", "bytes_base64")} | {"anchors": response["anchors"]}


def scientific_from(response):
    content = base64.b64decode(response["native_artifacts"][0]["bytes_base64"], validate=True)
    packet = strict_json_loads(content)
    native = base64.b64decode(packet["scientific"]["bytes_base64"], validate=True)
    return packet, strict_json_loads(native)


def design_request(problem, dataset, discovered, *, times=("8/1", "6/1"), allowance="1/5", suffix="design"):
    candidates = discovered["result"]["candidates"]
    request = {"schema_version": "DB-SC-1", "historical_run_id": "run_baseline",
               "scenario_id": "scenario_synthetic", "problem_id": problem["id"],
               "problem_digest": problem["digest"], "candidate_ids": [c["id"] for c in candidates],
               "candidate_vectors": [c["parameter_vector"] for c in candidates],
               "observable": "concentration", "feasible_times": list(times),
               "future_hard_allowance": allowance, "allow_construction": True, "allow_continuation": True,
               "budget": {"wall_seconds": 120, "fixed_vector_constructions": 2,
                          "pair_verifications": 2, "bundle_bytes": 4194304}}
    evidence = {"run_id": "run_baseline", "scenario_id": "scenario_synthetic",
                "problem_id": problem["id"], "expected_problem_digest": problem["digest"],
                "result": deepcopy(discovered["result"]), "arrived_after_cancel": False}
    return {"protocol": PROTOCOL, "operation": "design", "problem": deepcopy(problem), "dataset": deepcopy(dataset),
            "run_id": "run_" + suffix, "workflow": workflow(suffix), "request": request,
            "expected_request_digest": semantic_digest("design-request", request),
            "historical_evidence": evidence, "historical_artifact": artifact_from(discovered)}


def followup_records(problem, dataset, design, reading, *, suffix):
    revised_problem, revised_dataset = deepcopy(problem), deepcopy(dataset)
    revised_dataset["id"] = "dataset_followup_" + suffix
    revised_dataset["body"].update(parent_id=dataset["id"], origin="hypothetical",
                                    change_reason="Separate hypothetical reading at the checked selected time")
    revised_dataset["body"]["rows"].append(
        {"id": "row_followup_" + suffix, "time": design["result"]["selected_time"],
         "concentration": rational_text(reading), "hard_allowance": design["result"]["future_hard_allowance"],
         "included": True, "original_values": {"concentration": rational_text(reading)},
         "source_asset_id": None, "notes": "Hypothetical follow-up, not an observed measurement"})
    revised_problem["id"] = "problem_followup_" + suffix
    revised_problem["body"]["dataset_id"] = revised_dataset["id"]
    rebind(revised_problem, revised_dataset)
    return revised_problem, revised_dataset


def review_request(problem, dataset, design, reading, *, suffix):
    revised_problem, revised_dataset = followup_records(problem, dataset, design, reading, suffix=suffix)
    return {"protocol": PROTOCOL, "operation": "review", "problem": revised_problem, "dataset": revised_dataset,
            "run_id": "run_review_" + suffix, "workflow": workflow("review_" + suffix),
            "scenario_id": "scenario_synthetic", "limits": {"wall_seconds": 120, "max_bundle_bytes": 4194304},
            "historical_artifact": artifact_from(design)}


class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from counterdex.bridge import dispatch
        cls.dispatch = staticmethod(dispatch)
        cls.problem, cls.dataset = application_records()
        cls.baseline_request = investigation_request(cls.problem, cls.dataset)
        cls.baseline = dispatch(cls.baseline_request)
        if not cls.baseline["ok"]:
            raise AssertionError(cls.baseline)
        cls.design_input = design_request(cls.problem, cls.dataset, cls.baseline)
        cls.design = dispatch(cls.design_input)
        if not cls.design["ok"]:
            raise AssertionError(cls.design)

    def assert_native(self, response):
        self.assertTrue(response["ok"], response)
        self.assertEqual(response["protocol"], PROTOCOL)
        self.assertEqual(len(response["native_artifacts"]), 1)
        artifact = response["native_artifacts"][0]
        raw = base64.b64decode(artifact["bytes_base64"], validate=True)
        self.assertEqual(artifact_digest(raw), artifact["sha256"])
        self.assertEqual(len(raw), artifact["byte_size"])
        self.assertEqual(packet_anchors(raw), response["anchors"])
        replay = replay_packet(raw, expected=response["anchors"])
        self.assertEqual(replay["replay"], "passed")
        return raw, replay

    def test_discovery_returns_actual_checked_outside_and_original_source_binding(self):
        _, replay = self.assert_native(self.baseline)
        result = self.baseline["result"]
        self.assertEqual(result["scientific_outcome"], "certified_counterexample")
        self.assertEqual(result["verification"], "valid")
        self.assertEqual(result["expected_binding"], "matches")
        self.assertEqual(len(result["candidates"]), 2)
        packet, native = scientific_from(self.baseline)
        self.assertEqual(packet["binding"]["problem"], self.problem)
        self.assertEqual(packet["binding"]["dataset"], self.dataset)
        self.assertEqual(replay["dataset_origin"], "synthetic")
        self.assertEqual(native["search"]["attempted_count"], 16384)
        self.assertGreater(native["search"]["feasible_count"], 2)
        self.assertTrue(any(c["is_counterexample"] for c in replay["candidate_results"]))

    def test_design_uses_actual_frozen_pair_and_preserves_approved_grid_order(self):
        _, replay = self.assert_native(self.design)
        result = self.design["result"]
        self.assertEqual(result["design_tier"], "checked_pair_separation")
        self.assertEqual(result["selected_time"], "8/1")
        self.assertEqual([option["time"] for option in result["options"]], ["8/1", "6/1"])
        self.assertTrue(all(Fraction(option["exact_margin"]) > 0 for option in result["options"]))
        self.assertEqual(set(result["candidate_ids"]), {c["id"] for c in self.baseline["result"]["candidates"]})
        _, native = scientific_from(self.design)
        expected_vectors = {c["id"]: c["parameter_vector"] for c in self.baseline["result"]["candidates"]}
        self.assertEqual({c["id"]: c["parameters"] for c in native["design"]["candidates"]}, expected_vectors)
        self.assertEqual(replay["operation"], "design")

    def test_reviewed_single_time_and_larger_allowance_change_design_result(self):
        six_only = self.dispatch(design_request(self.problem, self.dataset, self.baseline, times=("6/1",), suffix="six"))
        self.assert_native(six_only)
        self.assertEqual(six_only["result"]["selected_time"], "6/1")
        broad = self.dispatch(design_request(self.problem, self.dataset, self.baseline, allowance="3/5", suffix="broad"))
        self.assert_native(broad)
        self.assertEqual(broad["result"]["design_tier"], "no_separation_established")
        self.assertIsNone(broad["result"]["selected_time"])
        self.assertNotEqual(broad["anchors"]["app_request_digest"], self.design["anchors"]["app_request_digest"])

    def test_raw_byte_integrity_and_external_scenario_binding_are_separate(self):
        raw, _ = self.assert_native(self.baseline)
        with self.assertRaises(AdapterError) as mismatch:
            replay_packet(raw + b" ", expected=self.baseline["anchors"])
        self.assertEqual(mismatch.exception.code, "artifact_mismatch")
        wrong = dict(self.baseline["anchors"], scenario_id="scenario_other")
        with self.assertRaises(AdapterError) as binding:
            replay_packet(raw, expected=wrong)
        self.assertEqual(binding.exception.code, "wrong_scenario_binding")

    def test_complete_native_wrapper_obeys_approved_byte_cap_on_replay(self):
        from counterdex.application import project_application, project_design
        for operation, response in (("investigate", self.baseline), ("design", self.design)):
            with self.subTest(operation=operation):
                packet, native = scientific_from(response)
                # Set a diagnostic cap between inner scientific bytes and the
                # complete application packet, retaining the original theorem.
                cap = len(canonical_bytes(native)) + 1024
                self.assertLess(cap, len(canonical_bytes(packet)))
                if operation == "investigate":
                    native["limits"]["max_bundle_bytes"] = cap
                    digest_field, digest_kind = "baseline_digest", "report"
                else:
                    request = deepcopy(packet["binding"]["request"])
                    request["budget"]["bundle_bytes"] = cap
                    mapping = project_design(request, expected_request_digest=semantic_digest("design-request", request),
                        projection=project_application(self.problem, self.dataset),
                        historical_evidence=packet["binding"]["historical_evidence"],
                        native_candidate_results=self.baseline["details"]["fresh_replay"]["candidate_results"])
                    packet["binding"] = mapping["binding"]
                    native["design"] = mapping["design"]
                    native["report"]["design_digest"] = mapping["design_digest"]
                    digest_field, digest_kind = "suggestion_digest", "suggestion"
                native[digest_field] = semantic_digest(digest_kind, {k: v for k, v in native.items() if k != digest_field})
                encoded = canonical_bytes(native)
                self.assertLess(len(encoded), cap)
                packet["scientific"] = {"sha256": artifact_digest(encoded), "bytes_base64": base64.b64encode(encoded).decode("ascii")}
                changed = canonical_bytes(packet)
                self.assertGreater(len(changed), cap)
                # The real original external anchor still rejects changed bytes.
                with self.assertRaises(AdapterError) as original:
                    replay_packet(changed, expected=response["anchors"])
                self.assertEqual(original.exception.code, "artifact_mismatch")
                # Only this deliberate diagnostic anchor reaches scope checks.
                with self.assertRaises(AdapterError) as checked:
                    replay_packet(changed, expected=packet_anchors(changed))
                self.assertEqual(checked.exception.code, "resource_exhaustion")

    def test_design_rejects_stale_request_and_missing_or_mismatched_history(self):
        variants = []
        changed = deepcopy(self.design_input)
        changed["request"]["future_hard_allowance"] = "1/10"
        variants.append(changed)
        missing = deepcopy(self.design_input)
        missing["historical_artifact"] = None
        variants.append(missing)
        corrupt = deepcopy(self.design_input)
        corrupt["historical_artifact"]["sha256"] = "0" * 64
        variants.append(corrupt)
        wrong = deepcopy(self.design_input)
        wrong["historical_evidence"]["scenario_id"] = "scenario_other"
        variants.append(wrong)
        for request in variants:
            with self.subTest(request_keys=tuple(request)), self.assertRaises(AdapterError):
                self.dispatch(request)

    def test_followup_excludes_either_or_both_without_global_claim(self):
        original_baseline = deepcopy(self.baseline)
        original_design = deepcopy(self.design)
        _, native_design = scientific_from(self.design)
        candidates = native_design["design"]["candidates"]
        time = Fraction(self.design["result"]["selected_time"])
        predictions = []
        for candidate in candidates:
            vector = tuple(Fraction(candidate["parameters"][key]) for key in ("A", "ke", "ka"))
            lower, upper = concentration_interval(*vector, time)
            predictions.append(Fraction(format(float((lower + upper) / 2), ".6f")))
        cases = [("first", predictions[0], {candidates[0]["id"]}),
                 ("second", predictions[1], {candidates[1]["id"]}),
                 ("neither", sum(predictions) / 2, set())]
        for suffix, reading, expected_survivors in cases:
            with self.subTest(suffix=suffix):
                request = review_request(self.problem, self.dataset, self.design, reading, suffix=suffix)
                response = self.dispatch(request)
                _, fresh = self.assert_native(response)
                survivors = {c["candidate_id"] for c in fresh["candidate_results"] if c["verification"] == "valid"}
                self.assertEqual(survivors, expected_survivors)
                self.assertEqual(fresh["dataset_origin"], "hypothetical")
                self.assertEqual({c["candidate_id"] for c in fresh["candidate_results"]}, {c["id"] for c in candidates})
                packet, native = scientific_from(response)
                self.assertEqual(native["operation"], "fixed_candidate_review")
                self.assertIsNone(native["search"])
                self.assertEqual(packet["binding"]["dataset"]["body"]["parent_id"], self.dataset["id"])
                self.assertNotEqual(response["anchors"]["problem_digest"], self.baseline["anchors"]["problem_digest"])
                if not expected_survivors:
                    self.assertEqual(response["result"]["scientific_outcome"], "inconclusive")
        self.assertEqual(self.baseline, original_baseline)
        self.assertEqual(self.design, original_design)

    def test_followup_cannot_change_old_rows_allowance_or_selected_time(self):
        base = review_request(self.problem, self.dataset, self.design, Fraction("3.3"), suffix="invalid")
        variants = []
        changed = deepcopy(base)
        changed["dataset"]["body"]["rows"][0]["concentration"] = "4/1"
        variants.append(changed)
        allowance = deepcopy(base)
        allowance["dataset"]["body"]["rows"][-1]["hard_allowance"] = "1/10"
        variants.append(allowance)
        time = deepcopy(base)
        time["dataset"]["body"]["rows"][-1]["time"] = "7/1"
        variants.append(time)
        for request in variants:
            rebind(request["problem"], request["dataset"])
            with self.subTest(revision=request["dataset"]["digest"]), self.assertRaises(AdapterError) as error:
                self.dispatch(request)
            self.assertEqual(error.exception.code, "wrong_specification_binding")

    def test_offline_lineage_shares_one_budget_and_respects_cancellation(self):
        import counterdex.native_packet as native_packet
        from counterdex.resource import ExecutionContext
        response = self.dispatch(review_request(self.problem, self.dataset, self.design, Fraction("3.3"), suffix="budget"))
        content = base64.b64decode(response["native_artifacts"][0]["bytes_base64"], validate=True)
        contexts = []
        historical, design = native_packet.replay_baseline, native_packet.replay_bundle
        def observe(function):
            def replay(*args, **kwargs):
                contexts.append(kwargs["context"])
                return function(*args, **kwargs)
            return replay
        with patch.object(native_packet, "replay_baseline", side_effect=observe(historical)), \
             patch.object(native_packet, "replay_bundle", side_effect=observe(design)):
            self.assertEqual(replay_packet(content, expected=response["anchors"])["replay"], "passed")
        self.assertEqual(len(contexts), 3)
        self.assertIsInstance(contexts[0], ExecutionContext)
        self.assertTrue(all(context is contexts[0] for context in contexts))
        for context in (ExecutionContext(cancelled=lambda: True), ExecutionContext(clock=lambda: 0)):
            if not context.cancelled():
                context.clock = lambda: 121
            with self.assertRaises(AdapterError) as error:
                replay_packet(content, expected=response["anchors"], context=context)
            self.assertIn(error.exception.code, ("cancelled", "resource_exhaustion"))

    def test_altered_input_is_projected_and_searched_again(self):
        problem, dataset = application_records()
        for row in dataset["body"]["rows"]:
            row["concentration"] = rational_text(Fraction(row["concentration"]) / 2)
            row["hard_allowance"] = "1/4"
        rebind(problem, dataset)
        response = self.dispatch(investigation_request(problem, dataset, suffix="changed"))
        self.assert_native(response)
        self.assertNotEqual(response["anchors"]["projection_digest"], self.baseline["anchors"]["projection_digest"])
        self.assertNotEqual(response["result"]["candidates"][0]["parameter_vector"],
                            self.baseline["result"]["candidates"][0]["parameter_vector"])

    def test_one_candidate_disables_pair_and_no_candidate_keeps_limits_visible(self):
        from counterdex.search import SearchSettings
        one = self.dispatch(investigation_request(self.problem, self.dataset,
                    suffix="one", search_settings=SearchSettings(max_candidates=1).to_payload()))
        self.assert_native(one)
        self.assertEqual(len(one["result"]["candidates"]), 1)
        self.assertFalse(one["details"]["fresh_replay"]["outcome"]["pair_available"])
        with self.assertRaises(AdapterError):
            self.dispatch(design_request(self.problem, self.dataset, one))
        problem, dataset = application_records()
        for row in dataset["body"]["rows"]:
            row["concentration"] = "100/1"
            row["hard_allowance"] = "1/100"
        rebind(problem, dataset)
        empty = self.dispatch(investigation_request(problem, dataset, suffix="empty"))
        self.assertEqual(empty["result"]["candidates"], [])
        self.assertEqual(empty["result"]["scientific_outcome"], "no_counterexample_found")
        self.assertEqual(empty["result"]["verification"], "not_checked")
        _, native = scientific_from(empty)
        self.assertEqual(native["search"]["attempted_count"], 16384)
        self.assertIsNone(native["certificate"])

    def test_separately_reviewed_construction_scope_is_enforced(self):
        request = deepcopy(self.design_input)
        request["request"]["allow_continuation"] = False
        request["expected_request_digest"] = semantic_digest("design-request", request["request"])
        response = self.dispatch(request)
        self.assertNotEqual(response["result"]["design_tier"], "checked_pair_separation")
        _, native = scientific_from(response)
        self.assertEqual(native["report"]["checked"]["reason_code"], "unavailable_horizon")

    def test_handshake_distinguishes_available_and_unqualified_runtime(self):
        response = self.dispatch({"protocol": PROTOCOL, "operation": "handshake"})
        self.assertTrue(response["available"])
        self.assertTrue(response["qualified"])
        self.assertIsNone(response["configured"])
        with patch("counterdex.capabilities.sys.version_info", (3, 12, 0)):
            response = self.dispatch({"protocol": PROTOCOL, "operation": "handshake"})
        self.assertTrue(response["available"])
        self.assertFalse(response["qualified"])
        self.assertIsNone(response["implementation"])

    def test_bridge_replay_takes_raw_bytes_and_separate_expected_anchors(self):
        artifact = self.design["native_artifacts"][0]
        response = self.dispatch({"protocol": PROTOCOL, "operation": "replay",
                                  "native_artifact_base64": artifact["bytes_base64"], "expected": self.design["anchors"]})
        self.assertEqual(response["result"]["replay"], "passed")
        wrong = dict(self.design["anchors"], run_id="run_unrelated")
        with self.assertRaises(AdapterError) as error:
            self.dispatch({"protocol": PROTOCOL, "operation": "replay",
                           "native_artifact_base64": artifact["bytes_base64"], "expected": wrong})
        self.assertEqual(error.exception.code, "wrong_scenario_binding")

    def test_bridge_has_no_model_network_dispatch(self):
        with patch("socket.create_connection", side_effect=AssertionError("unexpected network call")):
            response = self.dispatch(investigation_request(self.problem, self.dataset, suffix="offline"))
        self.assertEqual(response["result"]["scientific_outcome"], "certified_counterexample")


class BridgeProcessTests(unittest.TestCase):
    def run_process(self, content):
        # Deliberately supply no inherited environment or credential variables.
        return subprocess.run([sys.executable, "-m", "counterdex.bridge"], input=content,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15,
                              cwd="/tmp", env={"PATH": os.defpath, "PYTHONPATH": str(PACKAGE)})

    def test_process_handshake_and_actual_discovery_stdout(self):
        handshake = self.run_process(canonical_bytes({"protocol": PROTOCOL, "operation": "handshake"}))
        self.assertEqual(handshake.returncode, 0, handshake.stderr.decode())
        self.assertTrue(strict_json_loads(handshake.stdout)["qualified"])
        problem, dataset = application_records()
        execution = self.run_process(canonical_bytes(investigation_request(problem, dataset)))
        self.assertEqual(execution.returncode, 0, execution.stderr.decode())
        response = strict_json_loads(execution.stdout)
        self.assertEqual(response["result"]["scientific_outcome"], "certified_counterexample")
        raw = base64.b64decode(response["native_artifacts"][0]["bytes_base64"], validate=True)
        self.assertEqual(replay_packet(raw, expected=response["anchors"])["replay"], "passed")
        self.assertEqual(execution.stderr, b"")

    def test_process_rejects_malformed_duplicate_and_float_json_safely(self):
        for malformed in (b"{", b'{"protocol":"counterdex.bridge.v1","protocol":"duplicate","operation":"handshake"}',
                          b'{"protocol":"counterdex.bridge.v1","operation":"handshake","number":1.5}', b"[]"):
            with self.subTest(malformed=malformed):
                process = self.run_process(malformed)
                self.assertEqual(process.returncode, 2)
                response = strict_json_loads(process.stdout)
                self.assertFalse(response["ok"])
                self.assertEqual(response["error"]["code"], "invalid_input")
                self.assertNotIn(b"Traceback", process.stdout + process.stderr)

    def test_process_enforces_input_byte_cap(self):
        from counterdex.bridge import TRANSPORT_CAP
        process = self.run_process(b" " * (TRANSPORT_CAP + 1))
        self.assertEqual(process.returncode, 2)
        self.assertEqual(strict_json_loads(process.stdout)["error"]["code"], "resource_exhaustion")


if __name__ == "__main__":
    unittest.main()
