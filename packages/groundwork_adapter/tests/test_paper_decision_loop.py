"""Missing decision-loop controls on a computed pair, not paper extraction scores.

The existing bridge matrix covers either survivor and both exclusions. These
controls add both-compatible feedback and changes to reviewed design/reading
precision without replacing the original vectors or expanding the model.
"""
import base64
from copy import deepcopy
from fractions import Fraction
import os
import subprocess
import sys
import unittest
from unittest.mock import patch

from counterdex.analytical import concentration_interval
from counterdex.bridge import dispatch
from counterdex.errors import AdapterError
from counterdex.exact import artifact_digest, canonical_bytes, rational_text, semantic_digest, strict_json_loads
from counterdex.native_packet import packet_anchors, replay_packet
import test_bridge as bridge
from test_application import application_records


class PaperDecisionLoopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.problem, cls.dataset = application_records()
        cls.baseline = dispatch(bridge.investigation_request(cls.problem, cls.dataset))
        if not cls.baseline["ok"]:
            raise AssertionError(cls.baseline)

    def design_request(self, *, suffix, times=("8/1", "6/1"), allowance="1/5", **scope):
        request = bridge.design_request(self.problem, self.dataset, self.baseline,
            suffix=suffix, times=times, allowance=allowance)
        request["request"].update({"scientific_profile": "counterdex.v1",
            "requested_tier": "checked_pair_separation", "maximum_horizon": "10/1", "source_artifact_ids": [],
            "allowance_origin": {"kind": "hypothetical", "description": "Separately reviewed synthetic future hard bound"},
            **scope})
        request["expected_request_digest"] = semantic_digest("design-request", request["request"])
        return request

    def fresh(self, response):
        self.assertTrue(response["ok"], response)
        artifact, = response["native_artifacts"]
        raw = base64.b64decode(artifact["bytes_base64"], validate=True)
        self.assertEqual(artifact_digest(raw), artifact["sha256"])
        self.assertEqual(len(raw), artifact["byte_size"])
        self.assertEqual(packet_anchors(raw), response["anchors"])
        with patch("counterdex.search.search_candidates", side_effect=AssertionError("Replay cannot rediscover a pair")):
            fresh = replay_packet(raw, expected=response["anchors"])
        replayed = subprocess.run([sys.executable, "-m", "counterdex.bridge"],
            input=canonical_bytes({"protocol": bridge.PROTOCOL, "operation": "replay",
                "native_artifact_base64": artifact["bytes_base64"], "expected": response["anchors"]}),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15, cwd="/tmp",
            env={"PATH": os.defpath, "PYTHONPATH": str(bridge.PACKAGE), "PYTHONDONTWRITEBYTECODE": "1"})
        self.assertEqual(replayed.returncode, 0, replayed.stderr.decode())
        self.assertEqual(strict_json_loads(replayed.stdout)["result"], fresh)
        self.assertEqual(fresh["integrity"], "passed")
        self.assertEqual(fresh["expected_binding"], "matches")
        packet, native = bridge.scientific_from(response)
        return packet, native, fresh

    def execute(self, request):
        with patch("counterdex.search.search_candidates", side_effect=AssertionError("The approved pair cannot be replaced")):
            response = dispatch(request)
        return response, *self.fresh(response)

    def test_both_compatible_and_unresolved_depend_on_the_reviewed_reading_precision(self):
        original_baseline = deepcopy(self.baseline)
        self.fresh(self.baseline)
        design, _, parent, _ = self.execute(self.design_request(suffix="paper_followup_parent"))
        original_design = deepcopy(design)
        candidates = parent["design"]["candidates"]
        checks = {c["candidate_id"]: c for c in self.baseline["result"]["candidate_results"]}
        reference, = [c for c in candidates if not checks[c["id"]]["outside_closed_claim"]]
        outside, = [c for c in candidates if checks[c["id"]]["outside_closed_claim"]]
        time = Fraction(79, 10)
        bounds = {c["id"]: concentration_interval(
            *(Fraction(c["parameters"][key]) for key in ("A", "ke", "ka")), time) for c in candidates}
        lo, hi = bounds[reference["id"]]
        self.assertLess(lo, hi)
        reading = (lo + hi) / 2
        wide = max(abs(endpoint - reading) for interval in bounds.values() for endpoint in interval) + Fraction(1, 100)
        narrow = (hi - lo) / 4
        revisions = []
        cases = (
            ("both_compatible", wide, {c["id"]: "valid" for c in candidates}, "certified_counterexample"),
            ("unresolved", narrow, {reference["id"]: "inconclusive", outside["id"]: "invalid"}, "inconclusive"),
        )
        for name, allowance, expected, outcome in cases:
            with self.subTest(name=name):
                request = bridge.recheck_request(self.problem, self.dataset, design,
                    suffix="paper_" + name, origin="actual", time=rational_text(time),
                    reading=rational_text(reading), allowance=rational_text(allowance))
                response, packet, native, fresh = self.execute(request)
                revisions.append(request)
                self.assertEqual(packet["operation"], "recheck")
                self.assertEqual(packet["history"], bridge.artifact_from(design))
                self.assertEqual(packet["binding"]["observation_proposal"], request["observation_proposal"])
                self.assertEqual(request["dataset"]["body"]["rows"][:-1], self.dataset["body"]["rows"])
                self.assertEqual([(c["id"], c["parameters"]) for c in native["candidates"]],
                                 [(c["id"], c["parameters"]) for c in candidates])
                self.assertIsNone(native["search"])
                self.assertEqual(fresh["dataset_origin"], "synthetic")
                self.assertEqual(fresh["replay"], "passed")
                self.assertEqual(response["result"]["verification"], "valid")
                self.assertEqual(response["result"]["scientific_outcome"], outcome)
                self.assertEqual(fresh["outcome"]["scientific_outcome"], outcome)
                for rows in (response["result"]["candidate_results"], fresh["candidate_results"]):
                    self.assertEqual({c["candidate_id"]: c["verification"] for c in rows}, expected)
                # Both compatible does not establish the claimed interval:
                # the same original outside vector remains a checked witness.
                self.assertEqual(fresh["outcome"]["counterexample_ids"],
                                 [outside["id"]] if name == "both_compatible" else [])
                for candidate in fresh["candidate_results"]:
                    status = expected[candidate["candidate_id"]]
                    self.assertEqual(candidate["violating_observation_ids"], ["row_followup"] if status == "invalid" else [])
                    self.assertEqual(candidate["unresolved_observation_ids"], ["row_followup"] if status == "inconclusive" else [])
                    if status == "inconclusive":
                        self.assertEqual(candidate["reason_code"], "insufficient_enclosure")
        self.assertNotEqual(revisions[0]["observation_proposal"]["digest"], revisions[1]["observation_proposal"]["digest"])
        self.assertNotEqual(revisions[0]["dataset"]["digest"], revisions[1]["dataset"]["digest"])
        self.assertNotEqual(revisions[0]["problem"]["digest"], revisions[1]["problem"]["digest"])
        self.assertEqual(self.baseline, original_baseline)
        self.assertEqual(design, original_design)

    def test_changed_grid_and_future_precision_change_fresh_checked_computation(self):
        self.fresh(self.baseline)
        requests = (
            self.design_request(suffix="paper_grid"),
            self.design_request(suffix="paper_constrained_grid", times=("6/1",)),
            self.design_request(suffix="paper_insufficient_precision", allowance="10/1"),
        )
        results = [self.execute(request) for request in requests]
        full, constrained, wide = (item[0]["result"] for item in results)
        full_rows, constrained_rows, wide_rows = (item[3]["fresh_checked"]["rows"] for item in results)
        full_by_time = {row["time"]: row for row in full_rows}
        self.assertEqual(full["design_tier"], "checked_pair_separation")
        self.assertEqual(constrained["selected_time"], "6/1")
        self.assertEqual([row["time"] for row in constrained_rows], ["6/1"])
        self.assertEqual(constrained_rows[0], full_by_time["6/1"])
        self.assertNotEqual(full["selected_time"], constrained["selected_time"])
        self.assertEqual(wide["design_tier"], "no_separation_established")
        self.assertIsNone(wide["selected_time"])
        self.assertEqual(wide["verification"], "valid")
        self.assertEqual(wide["reason_code"], "no_separating_time")
        for row in wide_rows:
            before = full_by_time[row["time"]]
            self.assertEqual(row["centers"], before["centers"])
            self.assertEqual(row["errors"], before["errors"])
            self.assertEqual(Fraction(row["margin"]), Fraction(before["margin"]) - 2 * (Fraction(10) - Fraction(1, 5)))
            self.assertLessEqual(Fraction(row["margin"]), 0)
            self.assertFalse(row["separated"])
        for request, (response, packet, native, fresh) in zip(requests, results, strict=True):
            self.assertEqual(packet["binding"]["request"], request["request"])
            self.assertEqual(packet["history"], bridge.artifact_from(self.baseline))
            self.assertEqual(native["design"]["candidates"], results[0][2]["design"]["candidates"])
            self.assertEqual(fresh["replay"], "passed")
            self.assertEqual([r["time"] for r in response["result"]["options"]], request["request"]["feasible_times"])
        self.assertEqual(len({item[0]["anchors"]["design_digest"] for item in results}), 3)

    def test_explicit_horizon_refusal_and_missing_extension_never_gain_checked_tier(self):
        self.fresh(self.baseline)
        short = self.design_request(suffix="paper_short_horizon", maximum_horizon="7/1")
        with patch("counterdex.pipeline.create_suggestion", side_effect=AssertionError("Reject before scientific production")):
            with self.assertRaises(AdapterError) as caught:
                dispatch(short)
        self.assertEqual(caught.exception.code, "unavailable_horizon")
        self.assertEqual(caught.exception.field_paths, ("request/maximum_horizon",))
        request = self.design_request(suffix="paper_no_extension", allow_continuation=False)
        response, packet, native, fresh = self.execute(request)
        self.assertEqual(packet["binding"]["request"], request["request"])
        self.assertEqual(packet["history"], bridge.artifact_from(self.baseline))
        self.assertEqual(native["report"]["checked"]["reason_code"], "unavailable_horizon")
        self.assertIsNone(native["report"]["checked"]["pair_digest"])
        self.assertEqual(native["artifacts"], [])
        self.assertEqual(response["result"]["design_tier"], "numerical_guidance")
        self.assertEqual(response["result"]["verification"], "not_checked")
        self.assertEqual(fresh["replay"], "unsupported")
        self.assertEqual(fresh["verification"], "not_checked")
        self.assertTrue(all(option["exact_margin"] is None for option in response["result"]["options"]))


if __name__ == "__main__":
    unittest.main()
