"""Design-bound follow-up: the harness re-derives binding and per-candidate verdicts from saved records alone.

Standard library only. The records below are harness-built test doubles shaped like Owner 2's
``PlanBody.followup`` responses; they are never product evidence. The pair and readings are the
audited regression pair (fixed-pair-regression-v1), whose verdicts the decimal oracle recomputes.
"""
import copy
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from drbean_eval import contract, kinetics, qualify, science_flow  # noqa: E402

with open(os.path.join(ROOT, "cases", "science", "fixed-pair-regression-v1.json"), encoding="utf-8") as handle:
    PAIR = json.load(handle)
with open(os.path.join(ROOT, "cases", "science", "hero-v2.json"), encoding="utf-8") as handle:
    HERO = json.load(handle)
VECTORS = {c["id"]: {"A": c["A"], "ka": c["ka"], "ke": c["ke"]} for c in PAIR["pair"]}
IDS = list(VECTORS)
ROW = {"id": "followup_reading_3_4", "time": "8/1", "concentration": "17/5", "hard_allowance": "1/5",
       "included": True, "source_asset_id": None}
SCOPE = {"design_job_id": "djob_1", "design_result_id": "sugg_1", "design_result_digest": "d" * 64,
         "observation_proposal_id": "prop_1", "source_artifact_id": "art_design"}


def records(verdicts=None, outcome="inconclusive", **overrides):
    """A consistent saved-record set for label 'fu-x'; overrides replace whole records."""
    verdicts = verdicts or {"reference": "valid", "outside": "invalid"}
    parent_rows = HERO["dataset"]["rows"]
    base = {
        "fu-x-dataset": {"id": "ds_2", "digest": "2" * 64, "parent_id": "ds_1", "workspace_id": "ws",
                         "body": {"origin": "hypothetical", "rows": [*parent_rows, ROW], "parent_id": "ds_1"}},
        "fu-x-parent-dataset": {"id": "ds_1", "digest": "1" * 64, "workspace_id": "ws",
                                "body": {"origin": "synthetic", "rows": parent_rows}},
        "fu-x-problem": {"id": "pr_2", "digest": "3" * 64, "workspace_id": "ws",
                         "body": {"dataset_id": "ds_2", "dataset_digest": "2" * 64,
                                  "target": HERO["problem"]["target"]}},
        "fu-x-plan": {"id": "pl_2", "digest": "4" * 64, "workspace_id": "ws",
                      "body": {"problem_id": "pr_2", "problem_digest": "3" * 64, "dataset_id": "ds_2",
                               "followup": dict(SCOPE)}},
        "fu-x-approval": {"id": "ap_2", "plan_id": "pl_2", "plan_digest": "4" * 64, "scope": "investigation",
                          "expected_revision_id": "pr_2", "workspace_id": "ws"},
        "fu-x-run": {"id": "run_2", "plan_id": "pl_2", "approval_id": "ap_2", "kind": "run", "workspace_id": "ws",
                     "scenarios": [{"scenario_id": "baseline", "result_id": "ev_2"}]},
        "fu-x-evidence-baseline": {"id": "ev_2", "workspace_id": "ws", "body": {
            "run_id": "run_2", "problem_id": "pr_2", "expected_problem_digest": "3" * 64,
            "result": {"candidates": [{"id": cid, "parameter_vector": VECTORS[cid]} for cid in IDS],
                       "candidate_results": [{"candidate_id": cid, "verification": verdicts[cid]} for cid in IDS],
                       "baseline_search": None, "scientific_outcome": outcome}}},
        "fu-x-proposal": {"id": "prop_1", "workspace_id": "ws", "body": {"origin": "hypothetical", "row": ROW}},
        "fu-x-bound-design-job": {"id": "djob_1", "result_id": "sugg_1", "plan_id": "dplan_1", "workspace_id": "ws"},
        "fu-x-bound-suggestion": {"id": "sugg_1", "digest": "d" * 64, "workspace_id": "ws",
                                  "body": {"selected_time": "8/1", "artifacts": [{"id": "art_design"}]}},
        "fu-x-bound-design-plan": {"id": "dplan_1", "workspace_id": "ws", "body": {"request": {
            "candidate_ids": IDS, "candidate_vectors": [VECTORS[c] for c in IDS], "future_hard_allowance": "1/5"}}},
    }
    base.update(overrides)
    proposal = base["fu-x-proposal"]
    observation = {"dataset_id": "ds_1", "experiment_id": HERO["dataset"]["experiment_id"],
                   "observable": "concentration", "time_unit": "h", "concentration_unit": "mg/L",
                   "source_description": "Explicit synthetic qualifier control", "change_reason": "One reviewed reading",
                   "generating_choices": {"generator": "qualifier-control"}, **proposal["body"]}
    proposal["body"] = observation
    proposal["digest"] = contract.artifact_digest(contract.canonical_json(observation))
    parent = base["fu-x-parent-dataset"]
    parent["body"] = {**HERO["dataset"], **parent["body"]}
    revised = base["fu-x-dataset"]
    revised["body"] = {**parent["body"], **revised["body"], "change_reason": observation["change_reason"],
                       "rows": [*parent["body"]["rows"], observation["row"]]}
    base["fu-x-evidence-baseline"]["body"].update(scenario_id="baseline")
    base["fu-x-evidence-baseline"]["body"]["result"]["native_replay"] = {"operation": "review"}
    base["fu-x-bound-suggestion"]["body"].update(scientific_problem_digest="5" * 64, scientific_design_digest="6" * 64)
    base["fu-x-bound-suggestion"]["body"]["artifacts"][0]["sha256"] = "7" * 64
    base["fu-x-bound-design-plan"]["body"].update(request_digest="8" * 64)
    base["fu-x-bound-design-plan"]["body"]["request"].update(problem_id="pr_1", problem_digest="9" * 64, scenario_id="baseline")
    base["fu-x-report"] = {"body": {"followup": {"observation_proposal": copy.deepcopy(proposal),
        "dataset": copy.deepcopy(parent), "revised_dataset": copy.deepcopy(revised), "observation_review": {"body": {
            "proposal_id": proposal["id"], "proposal_digest": proposal["digest"], "dataset_id": revised["id"],
            "dataset_digest": revised["digest"], "accepted": True}}}}}
    return base


def followup_checks(saved):
    return {c["id"].rsplit(":", 1)[1]: c for c in qualify._link_checks(saved) if ":followup" in c["id"]}


class FollowupQualifierTests(unittest.TestCase):
    def test_oracle_matches_the_audited_regression_expectations(self):
        for follow in PAIR["followups_at_8h_allowance_0.2"]:
            reading = follow["reading"]
            for cid in IDS:
                self.assertEqual(kinetics.band_verdict(VECTORS[cid], "8", reading, "0.2"), follow["expected"][cid])

    def test_consistent_followup_passes_every_link(self):
        checks = followup_checks(records())
        self.assertEqual(set(checks), {"followup_binds_its_design", "followup_appends_exactly_the_reviewed_row",
                                       "followup_rechecks_the_design_pair", "followup_verdicts_match_oracle",
                                       "followup_outcome_follows_from_survivors", "followup_review_binds_proposal"})
        self.assertTrue(all(c["passed"] for c in checks.values()), checks)

    def test_verdict_disagreeing_with_the_oracle_fails(self):
        checks = followup_checks(records({"reference": "valid", "outside": "valid"}))
        self.assertFalse(checks["followup_verdicts_match_oracle"]["passed"])

    def test_outcome_must_follow_from_which_candidates_survive(self):
        # Reading 3.4 keeps only the reference candidate (ke 0.122, inside the closed claim): no counterexample.
        self.assertFalse(followup_checks(records(outcome="certified_counterexample"))[
            "followup_outcome_follows_from_survivors"]["passed"])
        self.assertFalse(followup_checks(records(outcome="no_counterexample_found"))[
            "followup_outcome_follows_from_survivors"]["passed"])
        # Reading 4.57 keeps only the outside candidate (ke 0.074): the counterexample must be reported.
        row = {**ROW, "concentration": "457/100"}
        overrides = {"fu-x-proposal": {"id": "prop_1", "body": {"origin": "hypothetical", "row": row}}}
        swapped = {"reference": "invalid", "outside": "valid"}
        for outcome, passed in (("certified_counterexample", True), ("inconclusive", False)):
            saved = records(swapped, outcome=outcome, **overrides)
            saved["fu-x-dataset"]["body"]["rows"][-1] = row
            checks = followup_checks(saved)
            self.assertTrue(checks["followup_verdicts_match_oracle"]["passed"], checks)
            self.assertEqual(checks["followup_outcome_follows_from_survivors"]["passed"], passed, outcome)

    def test_tampered_scope_digest_fails(self):
        saved = records()
        saved["fu-x-plan"]["body"]["followup"]["design_result_digest"] = "0" * 64
        self.assertFalse(followup_checks(saved)["followup_binds_its_design"]["passed"])

    def test_both_excluded_fixed_review_requires_inconclusive_outcome(self):
        row = {**ROW, "concentration": "4/1"}
        for outcome, passed in (("inconclusive", True), ("no_counterexample_found", False)):
            saved = records({cid: "invalid" for cid in IDS}, outcome=outcome,
                **{"fu-x-proposal": {"id": "prop_1", "workspace_id": "ws", "body": {"origin": "hypothetical", "row": row}}})
            checks = followup_checks(saved)
            self.assertTrue(checks["followup_verdicts_match_oracle"]["passed"], checks)
            self.assertEqual(checks["followup_outcome_follows_from_survivors"]["passed"], passed)

    def test_design_request_keeps_baseline_history_out_of_prospective_reuse(self):
        flow = science_flow.Flow.__new__(science_flow.Flow)
        flow.schema_properties = lambda _: ({"scientific_profile": {}}, set())
        pair = [{"id": cid, "parameter_vector": VECTORS[cid], "artifact_ids": ["historical-baseline"]} for cid in IDS]
        request = flow.design_request({"id": "original_run"}, {"id": "original_problem", "digest": "1" * 64}, pair,
                                      HERO["design_review"])
        self.assertEqual(request["source_artifact_ids"], [])

    def test_substituted_vectors_or_new_discovery_fail(self):
        saved = records()
        result = saved["fu-x-evidence-baseline"]["body"]["result"]
        result["candidates"][0]["parameter_vector"] = {**VECTORS[IDS[0]], "ke": "0.123"}
        self.assertFalse(followup_checks(saved)["followup_rechecks_the_design_pair"]["passed"])
        saved = records()
        saved["fu-x-evidence-baseline"]["body"]["result"]["baseline_search"] = {"evaluated": 10}
        self.assertFalse(followup_checks(saved)["followup_rechecks_the_design_pair"]["passed"])

    def test_extra_or_moved_row_fails(self):
        saved = records()
        saved["fu-x-dataset"]["body"]["rows"].append({**ROW, "id": "smuggled"})
        self.assertFalse(followup_checks(saved)["followup_appends_exactly_the_reviewed_row"]["passed"])
        moved = {**ROW, "time": "6/1"}
        saved = records(**{"fu-x-proposal": {"id": "prop_1", "body": {"origin": "hypothetical", "row": moved}}})
        saved["fu-x-dataset"]["body"]["rows"][-1] = moved
        self.assertFalse(followup_checks(saved)["followup_appends_exactly_the_reviewed_row"]["passed"])

    def test_missing_bound_records_fail_closed(self):
        saved = records()
        del saved["fu-x-bound-suggestion"]
        checks = followup_checks(saved)
        self.assertEqual(list(checks), ["followup_complete"])
        self.assertFalse(checks["followup_complete"]["passed"])

    def test_changed_proposal_provenance_does_not_inherit_its_accepted_review(self):
        saved = records()
        saved["fu-x-proposal"]["body"]["source_description"] = "Substituted provenance"
        self.assertFalse(followup_checks(saved)["followup_review_binds_proposal"]["passed"])

    def test_actual_own_time_recheck_preserves_synthetic_ancestry(self):
        saved = records()
        proposal = saved["fu-x-proposal"]
        proposal["body"].update(origin="actual", generating_choices={})
        proposal["body"]["row"] = {**proposal["body"]["row"], "time": "79/10", "hard_allowance": "7/20"}
        saved["fu-x-dataset"]["body"].update(origin="synthetic", rows=[*saved["fu-x-parent-dataset"]["body"]["rows"], proposal["body"]["row"]])
        saved["fu-x-evidence-baseline"]["body"]["result"]["native_replay"]["operation"] = "recheck"
        checks = followup_checks(saved)
        self.assertTrue(checks["followup_appends_exactly_the_reviewed_row"]["passed"], checks)
        saved["fu-x-dataset"]["body"]["origin"] = "actual"
        self.assertFalse(followup_checks(saved)["followup_appends_exactly_the_reviewed_row"]["passed"])

    def test_native_recheck_binds_full_proposal_and_original_design_scope(self):
        saved = records()
        saved["fu-x-evidence-baseline"]["body"]["result"]["native_replay"]["operation"] = "recheck"
        packet = {"operation": "recheck", "run_id": "run_2", "scenario_id": "baseline", "binding": {
            "schema_version": "counterdex.followup-binding.v1", "application": {
                "schema_version": "counterdex.application-binding.v1", "mapping_policy": "DB-SC-1-to-groundwork-v1",
                "dataset": {key: saved["fu-x-dataset"][key] for key in ("id", "digest", "body")},
                "problem": {key: saved["fu-x-problem"][key] for key in ("id", "digest", "body")},
                "dataset_origin": "hypothetical"},
            "observation_proposal": {key: copy.deepcopy(saved["fu-x-proposal"][key]) for key in ("id", "digest", "body")},
            "parent": {"operation": "design", "run_id": "djob_1", "scenario_id": "baseline", "problem_id": "pr_1",
                       "problem_digest": "9" * 64, "dataset_id": "ds_1", "dataset_digest": "1" * 64, "projection_digest": "5" * 64}},
            "history": {"id": "art_design", "sha256": "7" * 64, "anchors": {
                "artifact_sha256": "7" * 64, "dataset_digest": "1" * 64, "problem_digest": "9" * 64,
                "projection_digest": "5" * 64, "app_request_digest": "8" * 64, "design_digest": "6" * 64,
                "run_id": "djob_1", "scenario_id": "baseline"}}}
        self.assertTrue(qualify.followup_native_binding("fu-x", packet, saved)["passed"])
        for changed in ("proposal", "parent", "operation"):
            altered = copy.deepcopy(packet)
            if changed == "proposal":
                altered["binding"]["observation_proposal"]["body"]["source_description"] = "Substituted provenance"
            elif changed == "parent":
                altered["binding"]["parent"]["run_id"] = "another_design_job"
            else:
                altered["operation"] = "review"
            self.assertFalse(qualify.followup_native_binding("fu-x", altered, saved)["passed"], changed)

    def test_plans_without_followup_scope_get_no_followup_checks(self):
        saved = records()
        del saved["fu-x-plan"]["body"]["followup"]
        self.assertEqual(followup_checks(saved), {})


class PriorCandidateResultTests(unittest.TestCase):
    def evidence(self, vectors, verdicts):
        return [{"body": {"result": {"candidates": [{"id": c, "parameter_vector": v} for c, v in vectors.items()],
                                     "candidate_results": [{"candidate_id": c, "verification": verdicts[c]}
                                                           for c in vectors]}}}]

    def test_exact_vectors_give_per_candidate_verdicts(self):
        found = science_flow._prior_candidate_results(
            self.evidence(VECTORS, {"reference": "valid", "outside": "invalid"}), VECTORS)
        self.assertEqual(found, {"reference": "compatible", "outside": "excluded"})

    def test_fresh_discovery_reusing_ids_is_not_a_recheck(self):
        discovered = copy.deepcopy(VECTORS)
        discovered["outside"]["ke"] = "0.075"
        self.assertIsNone(science_flow._prior_candidate_results(
            self.evidence(discovered, {"reference": "valid", "outside": "valid"}), VECTORS))

    def test_no_pair_means_no_verdicts(self):
        self.assertIsNone(science_flow._prior_candidate_results(
            self.evidence(VECTORS, {"reference": "valid", "outside": "invalid"}), {}))


if __name__ == "__main__":
    unittest.main()
