"""Scientific paper seam controls; no PDF parser or Gemini success is claimed."""
import base64
from copy import deepcopy
from fractions import Fraction
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from counterdex.application import project_application
from counterdex.bridge import dispatch
from counterdex.errors import AdapterError
from counterdex.exact import artifact_digest, canonical_bytes, rational_text, strict_json_loads
from counterdex.paper_mapping import assess_paper_scope, convert_scalar, oral_amplitude
from test_application import application_records, rebind
from test_bridge import investigation_request

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures/papers/synthetic-five-row.json"
REVIEWED = ("source_values", "model_applicability", "time_origin", "hard_allowances", "rate_meanings")
FACTS = dict(model_form="two_rate_difference", regimen="single_initial_event",
             response_kind="single_trajectory", observation_kind="table_transcription",
             source_claim_kind="deterministic_interval", question_kind="paper_deterministic_claim",
             allowance_basis="reviewed_hard_bound", amplitude_scope="independent_amplitude",
             reviewed_assumptions=REVIEWED)


def paper_records(*, unit_variant=False):
    """Controlled accepted records at the scientific seam, not a parsed PDF."""
    fixture = json.loads(FIXTURE.read_text())
    source = fixture["unit_variant_source" if unit_variant else "canonical_source"]
    problem, dataset = application_records()
    suffix = "units" if unit_variant else "canonical"
    dataset["id"], problem["id"] = "dataset_paper_" + suffix, "problem_paper_" + suffix
    problem["body"]["dataset_id"] = dataset["id"]
    dataset["body"]["change_reason"] = "Controlled synthetic reviewed mapping; no PDF extraction performed"
    for target, raw in zip(dataset["body"]["rows"], source["rows"], strict=True):
        target["source_asset_id"] = "source_controlled_paper"
        target["original_values"] = {}
        for field, quantity in (("time", "time"), ("concentration", "concentration"), ("hard_allowance", "concentration")):
            unit = source["units"][field]
            conversion = convert_scalar(raw[field], unit, quantity=quantity)
            target[field] = conversion["normalized_value"]
            target["original_values"].update({field: raw[field], field + "_unit": unit})
    rebind(problem, dataset)
    return problem, dataset


def mathematical_content(projection):
    """Test comparison only, NEVER an authority digest or replacement binding."""
    p = projection["problem"]
    keys = ("schema_version", "model", "model_revision", "units", "initial_conditions", "time_origin", "domain", "claim")
    return {**{key: p[key] for key in keys}, "rows": [
        {key: row[key] for key in ("id", "time", "value", "allowance", "included")}
        for row in p["observations"]]}


class PaperMappingTests(unittest.TestCase):
    def test_exact_units_keep_accepted_spelling_without_rounding(self):
        cases = [("15", "min", "time", "1/4", "h"), ("900", "s", "time", "1/4", "h"),
                 ("4.80", "ug/mL", "concentration", "24/5", "mg/L"),
                 ("4800", "ng/mL", "concentration", "24/5", "mg/L"),
                 ("4800", "µg/L", "concentration", "24/5", "mg/L"),
                 ("4.80", "μg/mL", "concentration", "24/5", "mg/L"),
                 ("0.48", "mg/dL", "concentration", "24/5", "mg/L"),
                 ("0.0048", "g/L", "concentration", "24/5", "mg/L"),
                 ("1/600", "1/min", "rate", "1/10", "1/h"),
                 ("1/36000", "1/s", "rate", "1/10", "1/h"),
                 ("0.123456789012345678901", "h", "time", "123456789012345678901/1000000000000000000000", "h")]
        for value, unit, quantity, expected, normalized_unit in cases:
            with self.subTest(value=value, unit=unit):
                result = convert_scalar(value, unit, quantity=quantity)
                self.assertEqual((result["normalized_value"], result["normalized_unit"]), (expected, normalized_unit))
                self.assertEqual((result["accepted_value"], result["accepted_unit"]), (value, unit))
                self.assertEqual(Fraction(result["normalized_value"]), Fraction(value) * Fraction(result["factor"]))
        for value in ("4,80", "<5", "1 ± 0.2", "10^3", "NaN", "1e999999", 4.8, True):
            with self.subTest(value=value), self.assertRaises(AdapterError):
                convert_scalar(value, "mg/L", quantity="concentration")
        for unit in ("mG/L", "mg/l", "log(mg/L)", "nmol/L", "unknown", None):
            with self.subTest(unit=unit), self.assertRaises(AdapterError):
                convert_scalar("4.8", unit, quantity="concentration")

    def test_oral_reparameterization_does_not_identify_dose_volume_or_bioavailability(self):
        first = oral_amplitude(bioavailability="1/2", dose_mg="100", volume_L="10", ke_per_h="1/10", ka_per_h="2")
        second = oral_amplitude(bioavailability="1", dose_mg="50", volume_L="10", ke_per_h="1/10", ka_per_h="2")
        self.assertEqual(first["A"], "100/19")
        self.assertEqual(first["A"], second["A"])
        self.assertNotEqual(first["inputs"], second["inputs"])
        # Coefficient identity follows directly from the oral ODE/expression.
        self.assertEqual(Fraction(first["A"]) * (Fraction(2) - Fraction(1, 10)), Fraction(1, 2) * 100 * 2 / 10)
        self.assertFalse(first["domain_equivalence_established"])
        for changed in ({"bioavailability": "2"}, {"volume_L": "0"}, {"dose_mg": "-1"},
                        {"ka_per_h": "1/10"}, {"ka_per_h": "1/20"}):
            with self.subTest(changed=changed), self.assertRaises(AdapterError):
                oral_amplitude(**(first["inputs"] | changed))

    def test_eligibility_binds_inputs_but_grants_no_execution_or_verification(self):
        p, d = paper_records()
        before = deepcopy((p, d))
        result = assess_paper_scope(p, d, **FACTS)
        self.assertEqual(result["status"], "eligible_supported_problem")
        self.assertEqual(result["input_binding"]["problem_digest"], p["digest"])
        self.assertEqual(result["input_binding"]["projection_digest"], project_application(p, d)["projection_digest"])
        self.assertFalse(result["execution_approved"])
        self.assertFalse(result["source_authenticity_verified"])
        self.assertEqual(result["mathematical_verification"], "not_run")
        self.assertEqual((p, d), before)

    def test_statistical_interval_trap_requires_separate_reviewed_question(self):
        p, d = paper_records()
        for claim in ("confidence_interval", "prediction_interval", "point_estimate", "qualitative"):
            with self.subTest(claim=claim):
                facts = FACTS | {"source_claim_kind": claim}
                self.assertEqual(assess_paper_scope(p, d, **facts)["status"], "unsupported_claim_semantics")
                facts.update(question_kind="user_deterministic_robustness", reviewed_assumptions=REVIEWED + ("separate_user_question",))
                result = assess_paper_scope(p, d, **facts)
                self.assertEqual(result["status"], "eligible_supported_problem")
                self.assertIn("not a refutation", " ".join(result["limitations"]))
        facts = FACTS | {"question_kind": "user_deterministic_robustness"}
        result = assess_paper_scope(p, d, **facts)
        self.assertEqual(result["status"], "needs_measurements_or_assumptions")
        self.assertIn("reviewed_assumptions.separate_user_question", [x["field"] for x in result["issues"]])

    def test_uncertainty_is_not_a_hard_bound_and_aggregate_or_digitization_stays_unaccepted(self):
        p, d = paper_records()
        for uncertainty in (None, "sd", "sem", "confidence_interval", "instrument_resolution", "detection_threshold"):
            with self.subTest(uncertainty=uncertainty):
                result = assess_paper_scope(p, d, **(FACTS | {"allowance_basis": uncertainty}))
                self.assertEqual(result["status"], "needs_measurements_or_assumptions")
        hypothetical = FACTS | {"allowance_basis": "hypothetical_hard_bound"}
        self.assertEqual(assess_paper_scope(p, d, **hypothetical)["status"], "unsupported_claim_semantics")
        hypothetical.update(question_kind="user_deterministic_robustness", reviewed_assumptions=REVIEWED + ("separate_user_question",))
        self.assertEqual(assess_paper_scope(p, d, **hypothetical)["status"], "eligible_supported_problem")
        for field, value, status in (("response_kind", "aggregate_mean", "needs_measurements_or_assumptions"),
                ("response_kind", "pooled_subjects", "unsupported_model"), ("regimen", "repeated_dosing", "unsupported_model"),
                ("regimen", "infusion", "unsupported_model"), ("model_form", "arbitrary_equation", "unsupported_model"),
                ("observation_kind", "figure_digitization", "unsupported_model")):
            with self.subTest(field=field, value=value):
                self.assertEqual(assess_paper_scope(p, d, **(FACTS | {field: value}))["status"], status)

    def test_oral_domain_relaxation_is_explicit_and_does_not_swap_rates(self):
        p, d = paper_records()
        facts = FACTS | {"model_form": "single_dose_oral_first_order", "amplitude_scope": "coupled_physical_parameters"}
        self.assertEqual(assess_paper_scope(p, d, **facts)["status"], "unsupported_model")
        facts.update(amplitude_scope="independent_amplitude", question_kind="user_deterministic_robustness",
                     reviewed_assumptions=REVIEWED + ("separate_user_question",))
        self.assertEqual(assess_paper_scope(p, d, **facts)["status"], "needs_measurements_or_assumptions")
        facts["reviewed_assumptions"] += ("independent_amplitude_relaxation",)
        self.assertEqual(assess_paper_scope(p, d, **facts)["status"], "eligible_supported_problem")
        p["body"]["domain"]["ke"]["upper"] = "1/1"
        rebind(p, d)
        result = assess_paper_scope(p, d, **facts)
        self.assertEqual(result["status"], "unsupported_model")
        self.assertTrue(any(i["field"] == "problem/body/domain" for i in result["issues"]))

    def test_missing_inputs_and_existing_projection_constraints_are_not_bypassed(self):
        self.assertEqual(assess_paper_scope(None, None)["status"], "needs_measurements_or_assumptions")
        p, d = paper_records()
        d["body"]["rows"] = d["body"]["rows"][:2]
        rebind(p, d)
        self.assertEqual(assess_paper_scope(p, d, **FACTS)["status"], "needs_measurements_or_assumptions")
        p, d = paper_records()
        p["body"]["initial_concentration"] = "1/1"
        rebind(p, d)
        self.assertEqual(assess_paper_scope(p, d, **FACTS)["status"], "unsupported_model")
        p, d = paper_records()
        p["body"]["target"]["closed"] = False
        rebind(p, d)
        self.assertEqual(assess_paper_scope(p, d, **FACTS)["status"], "unsupported_claim_semantics")


class PaperBridgeEquivalenceTests(unittest.TestCase):
    def run_and_replay(self, p, d, suffix):
        response = dispatch(investigation_request(p, d, suffix=suffix))
        self.assertTrue(response["ok"], response)
        artifact, = response["native_artifacts"]
        raw = base64.b64decode(artifact["bytes_base64"], validate=True)
        self.assertEqual(artifact_digest(raw), artifact["sha256"])
        self.assertEqual(len(response["anchors"]), 8)
        with tempfile.TemporaryDirectory(prefix="counterdex-paper-replay-") as folder:
            packet, anchors = Path(folder) / "native.json", Path(folder) / "anchors.json"
            packet.write_bytes(raw)
            anchors.write_bytes(canonical_bytes(response["anchors"]))
            engine = os.environ.get("COUNTERDEX_TEST_PYTHON", sys.executable)
            fresh = subprocess.run([engine, "-I", "-m", "counterdex", "replay-native", str(packet), "--anchors", str(anchors)],
                cwd=folder, env={"PATH": os.defpath, "PYTHONDONTWRITEBYTECODE": "1"}, capture_output=True, timeout=20)
            self.assertEqual(fresh.returncode, 0, fresh.stderr.decode() + fresh.stdout.decode())
            replay = strict_json_loads(fresh.stdout)
            self.assertEqual(replay["integrity"], "passed")
            self.assertEqual(replay["replay"], "passed")
            self.assertEqual(replay["expected_binding"], "matches")
            self.assertEqual(replay["outcome"]["scientific_outcome"], response["result"]["scientific_outcome"])
        return response

    def test_controlled_paper_units_and_manual_inputs_compute_equivalent_math_with_distinct_provenance(self):
        pairs = [application_records(), paper_records(), paper_records(unit_variant=True)]
        projections = [project_application(p, d) for p, d in pairs]
        self.assertEqual(mathematical_content(projections[0]), mathematical_content(projections[1]))
        self.assertEqual(mathematical_content(projections[0]), mathematical_content(projections[2]))
        self.assertEqual(len({x["projection_digest"] for x in projections}), 3)
        results = [self.run_and_replay(p, d, "paper_equivalence_" + str(i)) for i, (p, d) in enumerate(pairs)]
        vectors = lambda r: sorted(tuple(c["parameter_vector"][name] for name in ("A", "ke", "ka")) for c in r["result"]["candidates"])
        self.assertEqual(vectors(results[0]), vectors(results[1]))
        self.assertEqual(vectors(results[0]), vectors(results[2]))
        self.assertEqual(len({r["anchors"]["artifact_sha256"] for r in results}), 3)
        for result in results:
            self.assertEqual(result["result"]["scientific_outcome"], "certified_counterexample")
            self.assertTrue(any(c["verification"] == "valid" and c["outside_closed_claim"] for c in result["result"]["candidate_results"]))

    def test_correction_changes_executable_inputs_and_stale_source_claim_unit_time_bound_identity_refuses(self):
        p, d = paper_records()
        original = deepcopy((p, d))
        before = self.run_and_replay(p, d, "paper_original")
        preserved = deepcopy(before)
        old_math = mathematical_content(project_application(p, d))
        d["body"]["rows"][4]["concentration"] = "53/10"
        d["body"]["rows"][4]["notes"] = "Reviewed synthetic correction 5.70 to 5.30; original retained"
        with self.assertRaises(AdapterError):
            project_application(p, d)
        rebind(p, d)
        corrected = self.run_and_replay(p, d, "paper_corrected")
        self.assertNotEqual(d["digest"], original[1]["digest"])
        self.assertNotEqual(p["digest"], original[0]["digest"])
        self.assertNotEqual(mathematical_content(project_application(p, d)), old_math)
        vectors = lambda result: sorted(tuple(c["parameter_vector"][key] for key in ("A", "ke", "ka"))
                                         for c in result["result"]["candidates"])
        self.assertNotEqual(vectors(before), vectors(corrected))
        self.assertEqual(d["body"]["rows"][4]["original_values"]["concentration"], "5.70")
        self.assertEqual(before, preserved)
        variants = [lambda p, d: d["body"]["rows"][0].update(source_asset_id="source_different_bytes"),
                    lambda p, d: p["body"]["target"].update(upper="1/5"),
                    lambda p, d: p["body"].update(time_unit="min"),
                    lambda p, d: d["body"].update(time_origin="Different reviewed initial event"),
                    lambda p, d: d["body"]["rows"][0].update(hard_allowance="1/4")]
        for mutate in variants:
            p, d = deepcopy(original)
            mutate(p, d)
            with self.subTest(mutate=mutate), self.assertRaises(AdapterError):
                project_application(p, d)


if __name__ == "__main__":
    unittest.main()
