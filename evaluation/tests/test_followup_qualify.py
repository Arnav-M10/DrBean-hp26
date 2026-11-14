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

from drbean_eval import kinetics, qualify, science_flow  # noqa: E402

PAIR = json.load(open(os.path.join(ROOT, "cases", "science", "fixed-pair-regression-v1.json"), encoding="utf-8"))
HERO = json.load(open(os.path.join(ROOT, "cases", "science", "hero-v2.json"), encoding="utf-8"))
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
                                       "followup_outcome_follows_from_survivors"})
        self.assertTrue(all(c["passed"] for c in checks.values()), checks)

    def test_verdict_disagreeing_with_the_oracle_fails(self):
        checks = followup_checks(records({"reference": "valid", "outside": "valid"}))
        self.assertFalse(checks["followup_verdicts_match_oracle"]["passed"])

    def test_outcome_must_follow_from_which_candidates_survive(self):
        # Reading 3.4 keeps only the reference candidate (ke 0.122, inside the closed claim): no counterexample.
        self.assertFalse(followup_checks(records(outcome="certified_counterexample"))[
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
