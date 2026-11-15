"""Admitted observation provenance and fixed vectors from freshly replayed history."""

from copy import deepcopy
import unittest
from unittest.mock import patch

from counterdex.application import project_application
from counterdex.baseline import create_baseline
from counterdex.errors import AdapterError
from counterdex.exact import artifact_digest, canonical_bytes
from counterdex.followup import FOLLOWUP_BINDING, project_followup, verify_followup_binding
from counterdex.historical import normalize_candidates
from counterdex.models import normalize_problem
from counterdex.replay_baseline import replay_baseline
from counterdex.search import SearchSettings
from test_application import application_records, rebind
from test_bridge import (design_request, investigation_request, scientific_from,
                         workflow)


def observation_revision(problem, dataset, *, origin="actual", time="79/10", allowance="3/10", reading="17/5"):
    """Use the actual backend proposal and accepted-dataset field shapes."""
    proposal = {"id": "observation_followup", "body": {
        "dataset_id": dataset["id"], "experiment_id": dataset["body"]["experiment_id"],
        "observable": "concentration", "origin": origin,
        "row": {"id": "row_followup", "time": time, "concentration": reading,
                "hard_allowance": allowance, "included": True,
                "original_values": {"time": f"{time} h", "concentration": f"{reading} mg/L"},
                "source_asset_id": None, "notes": "Separately reviewed follow-up reading"},
        "source_description": "Manual reviewed observation, with its original value spellings",
        "change_reason": "Append the separately reviewed reading at its supplied elapsed time",
        "generating_choices": {"value": "Explicit scenario input"} if origin == "hypothetical" else {},
        "time_unit": "h", "concentration_unit": "mg/L"}}
    revise_proposal_digest(proposal)
    revised_problem, revised_dataset = deepcopy(problem), deepcopy(dataset)
    revised_dataset["id"] = "dataset_followup"
    revised_dataset["body"].update(parent_id=dataset["id"],
        origin="hypothetical" if "hypothetical" in (origin, dataset["body"]["origin"]) else dataset["body"]["origin"],
        change_reason=proposal["body"]["change_reason"])
    revised_dataset["body"]["rows"].append(deepcopy(proposal["body"]["row"]))
    revised_problem["id"] = "problem_followup"
    revised_problem["body"]["dataset_id"] = revised_dataset["id"]
    rebind(revised_problem, revised_dataset)
    return revised_problem, revised_dataset, proposal


def revise_proposal_digest(proposal):
    proposal["digest"] = artifact_digest(canonical_bytes(proposal["body"]))


class FollowupBindingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from counterdex.bridge import dispatch
        cls.parents = {}
        for origin in ("actual", "synthetic", "hypothetical"):
            problem, dataset = application_records()
            dataset["body"]["origin"] = origin
            rebind(problem, dataset)
            response = dispatch(investigation_request(problem, dataset))
            if not response["ok"]:
                raise AssertionError(response)
            packet, native = scientific_from(response)
            cls.parents[origin] = (problem, dataset, packet, native, response["details"]["fresh_replay"])
            if origin == "synthetic":
                designed = dispatch(design_request(problem, dataset, response))
                if not designed["ok"]:
                    raise AssertionError(designed)
                packet, native = scientific_from(designed)
                cls.parents["design"] = (problem, dataset, packet, native, designed["details"]["fresh_replay"])
                lone = dispatch(investigation_request(problem, dataset,
                    search_settings=SearchSettings(max_candidates=1).to_payload()))
                if not lone["ok"]:
                    raise AssertionError(lone)
                packet, native = scientific_from(lone)
                cls.parents["lone"] = (problem, dataset, packet, native, lone["details"]["fresh_replay"])

    def inputs(self, parent="synthetic", **kwargs):
        problem, dataset, packet, scientific, fresh = deepcopy(self.parents[parent])
        problem, dataset, proposal = observation_revision(problem, dataset, **kwargs)
        return {"projection": project_application(problem, dataset), "observation_proposal": proposal,
                "parent_packet": packet, "parent_scientific": scientific, "parent_replay": fresh}

    def assert_rejected(self, inputs, code=None):
        with self.assertRaises(AdapterError) as caught:
            project_followup(**inputs)
        if code is not None:
            self.assertEqual(code, caught.exception.code)
        return caught.exception

    def update_revision(self, inputs, edit):
        binding = inputs["projection"]["binding"]
        problem, dataset = deepcopy(binding["problem"]), deepcopy(binding["dataset"])
        edit(problem, dataset)
        rebind(problem, dataset)
        inputs["projection"] = project_application(problem, dataset)

    def test_origin_matrix_preserves_full_proposal_and_ancestry(self):
        for ancestry in ("actual", "synthetic", "hypothetical"):
            for origin in ("actual", "transcription", "hypothetical"):
                with self.subTest(ancestry=ancestry, origin=origin):
                    inputs = self.inputs(ancestry, origin=origin)
                    output = project_followup(**inputs)
                    binding = output["binding"]
                    expected_origin = "hypothetical" if "hypothetical" in (ancestry, origin) else ancestry
                    self.assertEqual(FOLLOWUP_BINDING, binding["schema_version"])
                    self.assertEqual(expected_origin, binding["application"]["dataset_origin"])
                    self.assertEqual(origin, binding["observation_proposal"]["body"]["origin"])
                    self.assertEqual(inputs["observation_proposal"], binding["observation_proposal"])
                    self.assertEqual(output, verify_followup_binding(binding,
                        **{key: inputs[key] for key in ("parent_packet", "parent_scientific", "parent_replay")}))

    def test_actual_time_and_allowance_do_not_require_a_design_or_snap_to_one(self):
        for parent in ("actual", "design", "lone"):
            with self.subTest(parent=parent):
                inputs = self.inputs(parent, time="79/10", allowance="7/20")
                output = project_followup(**inputs)
                row = output["problem"]["observations"][-1]
                self.assertEqual("79/10", row["time"])
                self.assertEqual("7/20", row["allowance"])
                originals = (inputs["parent_scientific"]["design"]["candidates"] if parent == "design"
                             else inputs["parent_scientific"]["candidates"])
                self.assertEqual([(c["id"], c["parameters"]) for c in originals],
                                 [(c["id"], c["parameters"]) for c in output["candidates"]])
                self.assertEqual(1 if parent == "lone" else 2, len(output["candidates"]))
                self.assertTrue(all(c["problem_digest"] == output["projection_digest"] for c in output["candidates"]))

    def test_full_provenance_is_copied_without_aliasing_or_truncation(self):
        inputs = self.inputs(origin="transcription")
        inputs["observation_proposal"]["body"]["source_description"] = "s" * 2000
        revise_proposal_digest(inputs["observation_proposal"])
        output = project_followup(**inputs)
        inputs["observation_proposal"]["body"]["source_description"] = "changed"
        self.assertEqual("s" * 2000, output["binding"]["observation_proposal"]["body"]["source_description"])

    def test_recheck_can_exclude_both_without_search_or_corrupted_evidence(self):
        inputs = self.inputs("design", reading="100/1", time="79/10", allowance="1/10")
        output = project_followup(**inputs)
        candidates = normalize_candidates(normalize_problem(output["problem"]), output["candidates"])
        with patch("counterdex.search.search_candidates", side_effect=AssertionError("Recheck cannot discover replacement vectors")):
            content = create_baseline(output["problem"], expected_problem_digest=output["projection_digest"],
                scenario_id="scenario_followup", workflow=workflow("followup"), frozen_candidates=candidates)
        from counterdex.exact import strict_json_loads
        native = strict_json_loads(content)
        fresh = replay_baseline(content, expected_problem_digest=output["projection_digest"],
            expected_baseline_digest=native["baseline_digest"], expected_scenario_id="scenario_followup")
        self.assertEqual("passed", fresh["replay"])
        self.assertEqual("fixed_candidate_review", native["operation"])
        self.assertIsNone(native["search"])
        self.assertEqual("inconclusive", fresh["outcome"]["scientific_outcome"])
        self.assertEqual(2, len(fresh["candidate_results"]))
        for result in fresh["candidate_results"]:
            self.assertEqual("invalid", result["verification"])
            self.assertEqual(["row_followup"], result["violating_observation_ids"])
        self.assertTrue(all(c["verification"] == "valid" for c in inputs["parent_replay"]["candidate_results"]))

    def test_parent_failure_or_nonoriginal_operation_cannot_supply_vectors(self):
        for value in ("failed", "inconclusive", None):
            inputs = self.inputs()
            inputs["parent_replay"]["replay"] = value
            self.assert_rejected(inputs, "incomplete_export")
        for value in ("review", "recheck", "unknown"):
            inputs = self.inputs()
            inputs["parent_packet"]["operation"] = value
            self.assert_rejected(inputs, "wrong_specification_binding")

    def test_changed_proposal_digest_provenance_units_or_generation_are_rejected(self):
        edits = (
            lambda body: body.update(origin="generated"),
            lambda body: body.update(observable="other"),
            lambda body: body.update(time_unit="min"),
            lambda body: body.update(concentration_unit="g/L"),
            lambda body: body.update(generating_choices={"simulation": "hidden"}),
            lambda body: body.update(origin="hypothetical", generating_choices={}),
            lambda body: body.update(source_description=""),
            lambda body: body.update(source_description="s" * 2001),
            lambda body: body.update(change_reason=""),
            lambda body: body.update(approval=True),
            lambda body: body.pop("source_description"),
        )
        for edit in edits:
            with self.subTest(edit=edit):
                inputs = self.inputs()
                edit(inputs["observation_proposal"]["body"])
                revise_proposal_digest(inputs["observation_proposal"])
                self.assert_rejected(inputs)
        inputs = self.inputs()
        inputs["observation_proposal"]["body"]["source_description"] = "Changed without new digest"
        self.assert_rejected(inputs, "wrong_specification_binding")

    def test_missing_or_changed_row_and_source_lineage_are_rejected(self):
        for key, value in (("time", "8/1"), ("hard_allowance", "1/5"), ("concentration", "23/5"),
                           ("included", False), ("source_asset_id", "source_unreviewed")):
            inputs = self.inputs()
            inputs["observation_proposal"]["body"]["row"][key] = value
            revise_proposal_digest(inputs["observation_proposal"])
            self.assert_rejected(inputs)
        for key, value in (("dataset_id", "dataset_other"), ("experiment_id", "experiment_other")):
            inputs = self.inputs()
            inputs["observation_proposal"]["body"][key] = value
            revise_proposal_digest(inputs["observation_proposal"])
            self.assert_rejected(inputs, "wrong_specification_binding")

    def test_old_rows_problem_and_aggregate_origin_cannot_change(self):
        edits = (
            lambda p, d: d["body"]["rows"][0].update(notes="Changed original provenance"),
            lambda p, d: d["body"]["rows"].reverse(),
            lambda p, d: d["body"].update(origin="actual"),
            lambda p, d: d["body"].update(parent_id="dataset_other"),
            lambda p, d: d["body"].update(experiment_id="experiment_other"),
            lambda p, d: d["body"].update(time_origin="Different initial event"),
            lambda p, d: d["body"].update(change_reason="Different reviewed reason"),
            lambda p, d: p["body"]["target"].update(lower="11/100"),
            lambda p, d: p["body"]["domain"]["A"].update(upper="29/1"),
            lambda p, d: p.update(id="problem_synthetic"),
        )
        for edit in edits:
            with self.subTest(edit=edit):
                inputs = self.inputs()
                self.update_revision(inputs, edit)
                self.assert_rejected(inputs, "wrong_specification_binding")

    def test_missing_duplicate_changed_or_incompatible_parent_candidates_are_rejected(self):
        edits = (
            lambda fresh: fresh.pop("candidate_results"),
            lambda fresh: fresh["candidate_results"].pop(),
            lambda fresh: fresh["candidate_results"].append(deepcopy(fresh["candidate_results"][0])),
            lambda fresh: fresh["candidate_results"][0].update(candidate_id="different"),
            lambda fresh: fresh["candidate_results"][0]["parameters"].update(A="9/1"),
            lambda fresh: fresh["candidate_results"][0].update(verification="invalid"),
        )
        for edit in edits:
            inputs = self.inputs()
            edit(inputs["parent_replay"])
            self.assert_rejected(inputs)
        inputs = self.inputs()
        inputs["parent_scientific"]["candidates"][0]["parameters"]["A"] = "9/1"
        self.assert_rejected(inputs, "candidate_mismatch")

    def test_stored_parent_metadata_or_profile_cannot_change(self):
        inputs = self.inputs()
        output = project_followup(**inputs)
        context = {key: inputs[key] for key in ("parent_packet", "parent_scientific", "parent_replay")}
        for key in output["binding"]["parent"]:
            binding = deepcopy(output["binding"])
            binding["parent"][key] = "changed"
            with self.assertRaises(AdapterError) as caught:
                verify_followup_binding(binding, **context)
            self.assertEqual("wrong_specification_binding", caught.exception.code)
        binding = deepcopy(output["binding"])
        binding["schema_version"] = "counterdex.followup-binding.future"
        with self.assertRaises(AdapterError) as caught:
            verify_followup_binding(binding, **context)
        self.assertEqual("unsupported_model", caught.exception.code)


if __name__ == "__main__":
    unittest.main()
