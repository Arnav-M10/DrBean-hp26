"""Exact DB-SC-1 source-body mapping; no provider or transport calls."""

from copy import deepcopy
from fractions import Fraction
from pathlib import Path
import sys
import unittest

from counterdex.application import (project_application, project_design, restore_approved_grid,
                                   verify_application_binding, verify_design_binding)
from counterdex.errors import AdapterError
from counterdex.exact import artifact_digest, canonical_bytes, rational_text, semantic_digest, strict_json_loads


def application_records():
    """Synthetic hero in the actual normalized application DTO field shapes."""
    measurements = [("0.25", "4.80"), ("0.5", "7.20"), ("1", "8.00"), ("2", "6.80"), ("4", "5.70")]
    dataset = {"id": "dataset_synthetic", "body": {
        "schema_version": "DB-SC-1", "experiment_id": "experiment_synthetic",
        "time_origin": "Elapsed hours from reviewed fixed initial state",
        "rows": [{"id": f"row_{i}", "time": rational_text(Fraction(time)),
                  "concentration": rational_text(Fraction(value)), "hard_allowance": "1/2",
                  "included": True, "original_values": {"time": time, "concentration": value},
                  "source_asset_id": None, "notes": "Synthetic demonstration; not collected measurements"}
                 for i, (time, value) in enumerate(measurements)],
        "parent_id": None, "change_reason": "Reviewed synthetic five-row experiment", "origin": "synthetic"}}
    dataset["digest"] = semantic_digest("dataset", dataset["body"])
    problem = {"id": "problem_synthetic", "body": {
        "schema_version": "DB-SC-1", "dataset_id": dataset["id"], "dataset_digest": dataset["digest"],
        "model": "two_rate_concentration", "domain": {
            "A": {"lower": "1/1000", "upper": "30/1"},
            "ke": {"lower": "3/200", "upper": "7/20"},
            "ka": {"lower": "2/5", "upper": "8/1"}, "rate_order": "ke_lt_ka"},
        "initial_concentration": "0/1", "observable": "concentration", "time_unit": "h",
        "concentration_unit": "mg/L", "rate_unit": "1/h",
        "target": {"parameter": "ke", "lower": "1/10", "upper": "17/100", "closed": True}}}
    problem["digest"] = semantic_digest("problem", problem["body"])
    return problem, dataset


def rebind(problem, dataset):
    dataset["digest"] = semantic_digest("dataset", dataset["body"])
    problem["body"]["dataset_digest"] = dataset["digest"]
    problem["digest"] = semantic_digest("problem", problem["body"])


def application_design(problem=None):
    problem = problem or application_records()[0]
    vectors = [{name: rational_text(Fraction(value)) for name, value in zip(("A", "ke", "ka"), vector)}
               for vector in (("9.041075603155", "0.122", "3.54"), ("8.267973235218", "0.074", "4.17"))]
    request = {"schema_version": "DB-SC-1", "historical_run_id": "run_synthetic",
               "scenario_id": "scenario_synthetic", "problem_id": problem["id"],
               "problem_digest": problem["digest"], "candidate_ids": ["reference", "outside"],
               "candidate_vectors": vectors, "observable": "concentration", "feasible_times": ["8/1", "6/1"],
               "future_hard_allowance": "1/5", "allow_construction": True, "allow_continuation": False,
               "budget": {"wall_seconds": 120, "fixed_vector_constructions": 2,
                          "pair_verifications": 2, "bundle_bytes": 4194304}}
    candidates = [{"id": cid, "parameter_vector": vector, "problem_id": problem["id"],
                   "problem_digest": problem["digest"], "observable": "concentration",
                   "checked_horizon": "4/1", "verification": "valid", "artifact_ids": ["native_history"]}
                  for cid, vector in zip(request["candidate_ids"], vectors)]
    evidence = {"run_id": request["historical_run_id"], "scenario_id": request["scenario_id"],
                "problem_id": problem["id"], "expected_problem_digest": problem["digest"],
                "result": {"problem_id": problem["id"], "problem_digest": problem["digest"],
                           "expected_binding": "matches", "candidates": candidates},
                "arrived_after_cancel": False}
    native = [{"candidate_id": cid, "parameters": vector, "verification": "valid"}
              for cid, vector in zip(request["candidate_ids"], vectors)]
    return request, evidence, native


class ApplicationProjectionTests(unittest.TestCase):
    def setUp(self):
        self.problem, self.dataset = application_records()

    def project(self):
        return project_application(self.problem, self.dataset)

    def rejects(self, code=None):
        with self.assertRaises(AdapterError) as caught:
            self.project()
        if code:
            self.assertEqual(code, caught.exception.code)

    def test_full_source_and_separate_identities(self):
        result = self.project()
        self.assertEqual(result["binding"]["dataset"], self.dataset)
        self.assertEqual(result["binding"]["problem"], self.problem)
        self.assertEqual("synthetic", result["binding"]["dataset_origin"])
        self.assertEqual("hypothetical", result["problem"]["dataset_kind"])
        self.assertIn("original origin synthetic", result["problem"]["provenance"])
        self.assertNotEqual(result["projection_digest"], self.problem["digest"])
        self.assertEqual(verify_application_binding(result["binding"]), result)

    def test_no_input_aliases(self):
        result = self.project()
        self.dataset["body"]["rows"][0]["original_values"]["time"] = "changed"
        self.assertEqual("0.25", result["binding"]["dataset"]["body"]["rows"][0]["original_values"]["time"])

    def test_order_excluded_rows_and_heterogeneous_allowances(self):
        rows = self.dataset["body"]["rows"]
        rows.reverse()
        rows[1]["included"] = False
        rows[1]["hard_allowance"] = "7/10"
        rebind(self.problem, self.dataset)
        output = self.project()["problem"]["observations"]
        self.assertEqual([row["id"] for row in rows], [row["id"] for row in output])
        self.assertEqual([row["included"] for row in rows], [row["included"] for row in output])
        self.assertEqual("7/10", output[1]["allowance"])
        self.assertEqual(len(rows), len(output))

    def test_all_source_metadata_changes_identity_without_text_overflow(self):
        before = self.project()
        row = self.dataset["body"]["rows"][0]
        row["original_values"] = {f"source_{i}": "x" * 256 for i in range(12)}
        row["source_asset_id"] = "source_synthetic"
        self.dataset["body"]["parent_id"] = "dataset_parent"
        self.dataset["body"]["change_reason"] = "r" * 2000
        rebind(self.problem, self.dataset)
        after = self.project()
        self.assertNotEqual(before["projection_digest"], after["projection_digest"])
        self.assertEqual(row, after["binding"]["dataset"]["body"]["rows"][0])
        self.assertLess(len(after["problem"]["observations"][0]["provenance"]), 4096)
        self.assertEqual("dataset_parent", after["binding"]["dataset"]["body"]["parent_id"])

    def test_actual_and_hypothetical_origins(self):
        for origin, kind, row_origin in (("actual", "actual", "transcription"),
                                          ("hypothetical", "hypothetical", "hypothetical")):
            with self.subTest(origin=origin):
                self.dataset["body"]["origin"] = origin
                self.dataset["body"]["rows"][0]["source_asset_id"] = "source_reviewed"
                rebind(self.problem, self.dataset)
                result = self.project()
                self.assertEqual(kind, result["problem"]["dataset_kind"])
                self.assertEqual(row_origin, result["problem"]["observations"][0]["origin"])

    def test_closed_endpoint_and_elapsed_origin_preserved(self):
        self.problem["body"]["target"]["lower"] = self.problem["body"]["target"]["upper"] = "1/10"
        self.dataset["body"]["time_origin"] = "Hours since initial state; no dose reset"
        rebind(self.problem, self.dataset)
        result = self.project()["problem"]
        self.assertEqual(["1/10", "1/10"], result["claim"]["interval"])
        self.assertEqual(self.dataset["body"]["time_origin"], result["time_origin"])

    def test_dataset_or_problem_digest_tampering_rejected(self):
        self.dataset["body"]["rows"][0]["notes"] = "mutated without new identity"
        self.rejects("wrong_specification_binding")
        self.problem, self.dataset = application_records()
        self.problem["body"]["target"]["lower"] = "11/100"
        self.rejects("wrong_specification_binding")

    def test_cross_dataset_binding_rejected(self):
        self.problem["body"]["dataset_id"] = "dataset_other"
        self.problem["digest"] = semantic_digest("problem", self.problem["body"])
        self.rejects("wrong_specification_binding")

    def test_binding_policy_or_projection_tampering_rejected(self):
        for field, value in (("mapping_policy", "unknown"), ("dataset_origin", "actual"), ("projection_digest", "0" * 64)):
            binding = self.project()["binding"]
            binding[field] = value
            with self.subTest(field=field), self.assertRaises(AdapterError):
                verify_application_binding(binding)

    def test_rows_beyond_engine_cap_are_not_dropped(self):
        template = self.dataset["body"]["rows"][0]
        self.dataset["body"]["rows"] = [dict(template, id=f"row_{i}") for i in range(129)]
        rebind(self.problem, self.dataset)
        self.rejects("unsupported_model")

    def test_insufficient_included_distinct_times(self):
        for row in self.dataset["body"]["rows"][2:]:
            row["included"] = False
        rebind(self.problem, self.dataset)
        self.rejects("unsupported_model")
        self.problem, self.dataset = application_records()
        for row in self.dataset["body"]["rows"]:
            row["time"] = "1/1"
        rebind(self.problem, self.dataset)
        self.rejects("unsupported_model")

    def test_zero_width_and_overlapping_rate_domains(self):
        for name, lower, upper in (("A", "1/1", "1/1"), ("ke", "3/200", "2/5")):
            self.problem, self.dataset = application_records()
            self.problem["body"]["domain"][name] = {"lower": lower, "upper": upper}
            rebind(self.problem, self.dataset)
            with self.subTest(name=name):
                self.rejects("unsupported_model")

    def test_units_origin_model_initial_state_not_inferred(self):
        for key, value in (("time_unit", "min"), ("initial_concentration", "1/1"), ("model", "another_model")):
            self.problem, self.dataset = application_records()
            self.problem["body"][key] = value
            rebind(self.problem, self.dataset)
            with self.subTest(key=key):
                self.rejects("unsupported_model")
        self.problem, self.dataset = application_records()
        self.dataset["body"]["origin"] = "unspecified"
        rebind(self.problem, self.dataset)
        self.rejects("unsupported_model")

    def test_noncanonical_exact_or_nonpositive_allowance_rejected(self):
        for field, value in (("time", "0.25"), ("hard_allowance", "0/1"), ("concentration", "-1/1")):
            self.problem, self.dataset = application_records()
            self.dataset["body"]["rows"][0][field] = value
            rebind(self.problem, self.dataset)
            with self.subTest(field=field):
                self.rejects("invalid_input")

    def test_source_body_cap(self):
        self.dataset["body"]["rows"][0]["original_values"] = {"large": "x" * (1024 * 1024)}
        rebind(self.problem, self.dataset)
        self.rejects("resource_exhaustion")

    def test_authoritative_application_models_when_installed(self):
        api = str(Path(__file__).resolve().parents[3] / "apps" / "api")
        sys.path.insert(0, api)
        try:
            try:
                from bean_api.contracts import DatasetBody, DesignRequestBody, ProblemBody
            except ImportError as exc:
                self.skipTest(f"Run under prepared API environment for exact DTO validation: {exc.name}")
            self.assertEqual(self.dataset["body"], DatasetBody.model_validate(self.dataset["body"]).model_dump(mode="json"))
            self.assertEqual(self.problem["body"], ProblemBody.model_validate(self.problem["body"]).model_dump(mode="json"))
            request, _, _ = application_design(self.problem)
            self.assertEqual(request, DesignRequestBody.model_validate(request).model_dump(mode="json"))
        finally:
            sys.path.remove(api)


class ApplicationDesignProjectionTests(unittest.TestCase):
    def setUp(self):
        problem, dataset = application_records()
        self.projection = project_application(problem, dataset)
        self.request, self.evidence, self.native = application_design(problem)

    def project(self, digest=None):
        return project_design(self.request, expected_request_digest=digest or semantic_digest("design-request", self.request),
                              projection=self.projection, historical_evidence=self.evidence, native_candidate_results=self.native)

    def test_selected_vectors_grid_allowance_horizon_and_caps(self):
        output = self.project()
        design = output["design"]
        self.assertEqual(["6/1", "8/1"], [row["time"] for row in design["grid"]])
        self.assertEqual(["8/1", "6/1"], output["approved_grid_order"])
        self.assertEqual("1/5", design["future_allowance"])
        self.assertEqual("reviewed_hard_bound", design["allowance_origin"]["kind"])
        self.assertEqual("8/1", design["horizon_policy"]["maximum_horizon"])
        self.assertEqual(self.request["candidate_vectors"], [c["parameters"] for c in design["candidates"]])
        self.assertTrue(all(c["source_artifact_digest"] is None for c in design["candidates"]))
        self.assertEqual(2, design["limits"]["max_times"])
        self.assertEqual(self.request["budget"]["bundle_bytes"], design["limits"]["max_bundle_bytes"])
        self.assertNotEqual(output["design_digest"], output["binding"]["request_digest"])
        self.assertEqual(output, verify_design_binding(output["binding"], native_candidate_results=self.native))

    def test_approved_grid_restored_with_failure_details(self):
        options = [{"time": "6/1", "state": "failed", "reason_code": "wall_limit"},
                   {"time": "8/1", "state": "evaluated", "exact_margin": "1/2"}]
        restored = restore_approved_grid(options, ["8/1", "6/1"])
        self.assertEqual(["8/1", "6/1"], [o["time"] for o in restored])
        self.assertEqual("wall_limit", restored[1]["reason_code"])
        for invalid in (options[:1], options + [options[0]]):
            with self.assertRaises(AdapterError):
                restore_approved_grid(invalid, ["8/1", "6/1"])

    def test_wrong_request_or_problem_digest(self):
        with self.assertRaises(AdapterError):
            self.project("0" * 64)
        self.request["problem_digest"] = "0" * 64
        with self.assertRaises(AdapterError):
            self.project()

    def test_wrong_historical_scenario_run_or_problem(self):
        for field in ("scenario_id", "run_id", "problem_id", "expected_problem_digest"):
            original = self.evidence[field]
            self.evidence[field] = "another_scope"
            with self.subTest(field=field), self.assertRaises(AdapterError):
                self.project()
            self.evidence[field] = original

    def test_missing_candidate_and_native_vector_mismatch(self):
        self.native.pop()
        with self.assertRaises(AdapterError):
            self.project()
        self.setUp()
        self.native = deepcopy(self.native)
        self.native[0]["parameters"]["A"] = "9/1"
        with self.assertRaises(AdapterError):
            self.project()
        self.setUp()
        self.evidence["result"]["candidates"].pop()
        with self.assertRaises(AdapterError):
            self.project()

    def test_stored_candidate_vector_cannot_replace_native_vector(self):
        self.evidence = deepcopy(self.evidence)
        self.evidence["result"]["candidates"][0]["parameter_vector"]["A"] = "9/1"
        with self.assertRaises(AdapterError):
            self.project()

    def test_one_candidate_or_duplicated_vector_not_pair(self):
        self.request["candidate_ids"] = self.request["candidate_ids"][:1]
        self.request["candidate_vectors"] = self.request["candidate_vectors"][:1]
        with self.assertRaises(AdapterError) as caught:
            self.project()
        self.assertEqual("missing_second_witness", caught.exception.code)
        self.setUp()
        vector = self.request["candidate_vectors"][0]
        self.request["candidate_vectors"][1] = vector
        self.evidence["result"]["candidates"][1]["parameter_vector"] = vector
        self.native[1]["parameters"] = vector
        with self.assertRaises(AdapterError):
            self.project()

    def test_exact_changed_allowance_changes_design_and_request_identities(self):
        original = self.project()
        self.request["future_hard_allowance"] = "3/5"
        changed = self.project()
        self.assertNotEqual(original["design_digest"], changed["design_digest"])
        self.assertNotEqual(original["binding"]["request_digest"], changed["binding"]["request_digest"])
        self.assertEqual("3/5", changed["design"]["future_allowance"])

    def test_resource_caps_and_continuation_authority(self):
        self.request["budget"]["bundle_bytes"] = 1000
        self.assertEqual(1000, self.project()["design"]["limits"]["max_certificate_bytes"])
        self.request["budget"]["wall_seconds"] = 121
        with self.assertRaises(AdapterError):
            self.project()
        self.setUp()
        self.request["allow_construction"], self.request["allow_continuation"] = False, True
        with self.assertRaises(AdapterError):
            self.project()

    def test_design_binding_is_reproduced_not_trusted(self):
        binding = self.project()["binding"]
        binding["design_digest"] = "0" * 64
        with self.assertRaises(AdapterError):
            verify_design_binding(binding, native_candidate_results=self.native)


class NativePacketAdmissionTests(unittest.TestCase):
    """Reject malformed envelopes before attempting scientific replay."""

    def setUp(self):
        from counterdex.native_packet import packet_anchors, packet_bytes
        problem, dataset = application_records()
        binding = project_application(problem, dataset)["binding"]
        self.content = packet_bytes("investigate", binding, b"{}", run_id="run_synthetic", scenario_id="scenario_synthetic")
        self.packet = strict_json_loads(self.content)
        self.anchors = packet_anchors(self.content)

    def test_bad_nested_shapes_return_adapter_error(self):
        from counterdex.native_packet import replay_packet
        alterations = [("binding", None), ("binding", {}), ("scientific", []),
                       ("run_id", 1), ("scenario_id", "invalid\nlabel"),
                       ("history", {"id": "history", "sha256": "0" * 64, "bytes_base64": "", "anchors": []})]
        for field, value in alterations:
            packet = deepcopy(self.packet)
            packet[field] = value
            content = canonical_bytes(packet)
            anchors = dict(self.anchors, artifact_sha256=artifact_digest(content))
            with self.subTest(field=field, value=value), self.assertRaises(AdapterError):
                replay_packet(content, expected=anchors)

    def test_bad_anchors_and_missing_scientific_fields_are_safe(self):
        from counterdex.native_packet import replay_packet
        for expected in (None, [], {}, dict(self.anchors, problem_digest=1), dict(self.anchors, run_id=[])):
            with self.subTest(expected=expected), self.assertRaises(AdapterError):
                replay_packet(self.content, expected=expected)
        with self.assertRaises(AdapterError):
            replay_packet(self.content, expected=self.anchors)

    def test_packet_anchor_extraction_does_not_trust_missing_source(self):
        from counterdex.native_packet import packet_anchors
        del self.packet["binding"]["dataset"]
        with self.assertRaises(AdapterError):
            packet_anchors(canonical_bytes(self.packet))

    def test_followup_rejects_reused_problem_record_id(self):
        import base64
        from counterdex.native_packet import packet_bytes, validate_followup
        problem, dataset = application_records()
        projection = project_application(problem, dataset)
        request, evidence, native_results = application_design(problem)
        evidence["result"]["artifacts"] = [{"id": "native_history", "sha256": artifact_digest(self.content)}]
        mapping = project_design(request, expected_request_digest=semantic_digest("design-request", request),
                                 projection=projection, historical_evidence=evidence,
                                 native_candidate_results=native_results)
        # An intentionally incomplete native body is enough for this admission
        # rejection. It is never claimed to pass mathematical replay.
        history = {"id": "native_history", "sha256": artifact_digest(self.content),
                   "bytes_base64": base64.b64encode(self.content).decode(), "anchors": self.anchors}
        parent = strict_json_loads(packet_bytes("design", mapping["binding"], b"{}", run_id="design_run",
                                              scenario_id="scenario_synthetic", history=history))
        dataset["id"] = "dataset_followup"
        dataset["body"]["parent_id"] = "dataset_synthetic"
        dataset["body"]["origin"] = "hypothetical"
        dataset["body"]["rows"].append({"id": "new_reading", "time": "8/1", "concentration": "17/5",
                                       "hard_allowance": "1/5", "included": True, "original_values": {},
                                       "source_asset_id": None, "notes": "Hypothetical reading"})
        problem["body"]["dataset_id"] = dataset["id"]
        rebind(problem, dataset)
        revised = project_application(problem, dataset)
        with self.assertRaises(AdapterError) as caught:
            validate_followup(revised["binding"], parent, {"operation": "fixed_candidate_review", "candidates": []})
        self.assertEqual("wrong_specification_binding", caught.exception.code)


if __name__ == "__main__":
    unittest.main()
