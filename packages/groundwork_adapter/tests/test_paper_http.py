"""Optional real HTTP/worker controls for both-compatible and unresolved outcomes.

Run with the backend environment, repository apps/api and tests on PYTHONPATH,
and explicit installed BEAN_COUNTERDEX_PYTHON/BEAN_COUNTERDEX_REPLAY_PYTHON.
The observations are synthetic; declared actual origin is not acquisition proof.
This exercises no PDF parser or model provider and invokes no pytest fixtures.
"""
import base64
from fractions import Fraction
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch


class PaperHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for dependency in ("bean_api", "fastapi", "httpx", "pytest"):
            if importlib.util.find_spec(dependency) is None:
                raise unittest.SkipTest("Optional prepared backend dependencies are not installed: " + dependency)
        cls.engine = os.environ.get("BEAN_COUNTERDEX_PYTHON")
        if not cls.engine:
            raise unittest.SkipTest("Set BEAN_COUNTERDEX_PYTHON to an installed prepared Counterdex runtime")
        cls.replay = os.environ.get("BEAN_COUNTERDEX_REPLAY_PYTHON") or cls.engine
        # Once dependencies and an explicit runtime are selected, failures are
        # failures, including a missing executable or an unqualified engine.
        cls.http = importlib.import_module("test_scientific_http")
        cls.baseline = importlib.import_module("test_baseline_workflow")
        cls.design = importlib.import_module("test_native_design_workflow")
        cls.followup = importlib.import_module("test_native_followup_workflow")

    def test_both_compatible_retains_original_outside_witness_and_replays(self):
        self._exercise_followup(unresolved=False)

    def test_unresolved_reference_stays_inconclusive_despite_valid_replay(self):
        self._exercise_followup(unresolved=True)

    def _exercise_followup(self, *, unresolved):
        http, baseline, design = self.http, self.baseline, self.design
        post, prefix, worker = http.post, http.PREFIX, http.Worker
        with tempfile.TemporaryDirectory(prefix="counterdex-paper-followup-") as directory:
            scratch = Path(directory)
            settings = http.Settings(database_path=str(scratch / "science.sqlite3"),
                blob_dir=str(scratch / "sources"), artifact_dir=str(scratch / "artifacts"),
                auth_file=str(scratch / "unused-auth.json"), counterdex_python=self.engine,
                auth_tokens={"alice": "a" * 40, "bob": "b" * 40})
            with patch.object(socket.socket, "connect", side_effect=AssertionError("No network dispatch is allowed")), \
                    http.TestClient(http.create_app(settings)) as client:
                client.headers["Authorization"] = "Bearer " + "a" * 40
                capabilities = client.get(prefix + "/capabilities").json()
                self.assertTrue(capabilities["science"]["available"], capabilities)
                self.assertEqual(capabilities["ai_mode"], "disabled_placeholder")
                workspace, dataset, problem, _, approval, run, _ = http.prepare_approved_history(client)
                result, content, anchors, _ = baseline.execute_and_download(client, run)
                finished = client.get(prefix + f"/runs/{run['id']}").json()
                evidence = client.get(prefix + f"/records/{finished['scenarios'][0]['result_id']}").json()
                history = dict(client=client, workspace=workspace, dataset=dataset, problem=problem,
                    approval=approval, run=run, result=result, content=content, anchors=anchors, evidence=evidence)
                plan = design.propose(history, design.design_request(history), "paper-followup-design")
                job, design_approval, suggestion, design_bytes, design_anchors = design.approve_start_and_download(
                    history, plan, "paper-followup-design")
                self.assertEqual(suggestion["design_tier"], "checked_pair_separation")
                job = client.get(prefix + f"/design-jobs/{job['id']}").json()
                record = client.get(prefix + f"/records/{job['result_id']}").json()
                history.update(design_plan=plan, design_job=job, design_approval=design_approval,
                    design_result=suggestion, design_record=record, design_content=design_bytes,
                    design_anchors=design_anchors)

                # Derive each reading/allowance from actual checked predictions,
                # not a frozen pair, copied answer or extreme incompatible value.
                row = next(r for r in suggestion["native_replay"]["fresh_checked"]["rows"]
                           if r["time"] == suggestion["selected_time"])
                ids = suggestion["candidate_ids"]
                self.assertEqual(len(set(ids)), 2)
                centers = {cid: Fraction(row["centers"][cid]) for cid in ids}
                outside = {r["candidate_id"] for r in history["result"]["candidate_results"] if r["outside_closed_claim"]}
                self.assertEqual(len(outside), 1)
                inside, = set(ids) - outside
                if unresolved:
                    error = Fraction(row["errors"][inside])
                    self.assertGreater(error, 0)
                    reading, allowance = centers[inside], error / 2
                    self.assertLess(allowance, error)
                    expected_status = {cid: "inconclusive" if cid == inside else "invalid" for cid in ids}
                    expected_outcome, expected_witnesses = "inconclusive", set()
                else:
                    reading = sum(centers.values()) / 2
                    allowance = max(abs(centers[cid] + sign * Fraction(row["errors"][cid]) - reading)
                                    for cid in ids for sign in (-1, 1)) + Fraction(1, 100)
                    self.assertGreater(allowance, Fraction(suggestion["future_hard_allowance"]))
                    expected_status = dict.fromkeys(ids, "valid")
                    expected_outcome, expected_witnesses = "certified_counterexample", outside
                def text(value):
                    return f"{value.numerator}/{value.denominator}"
                proposal, revised, revised_problem, body = self.followup.revised_inputs(history,
                    text(reading), origin="actual", time=row["time"], allowance=text(allowance))
                body["objective"]["question"] = "Which original candidates remain compatible with this synthetic control?"
                self.assertEqual(revised["body"]["origin"], "synthetic")
                self.assertEqual(revised["body"]["rows"][:-1], dataset["body"]["rows"])
                followup = post(client, f"/workspaces/{workspace}/plans", {
                    "expected_current_revision_id": revised_problem["id"], "plan": body}, "paper-followup-plan")
                for old in (approval, design_approval):
                    rejected = client.post(prefix + f"/plans/{followup['id']}/runs", json={
                        "approval_id": old["id"], "expected_plan_digest": followup["digest"]},
                        headers={"Idempotency-Key": "wrong-approval-" + old["id"]})
                    self.assertEqual(rejected.status_code, 403, rejected.text)
                    self.assertEqual(rejected.json()["code"], "approval_required")
                self.assertEqual(worker(client.app.state.workflow, settings=settings).tick(), 0)
                fresh_approval = post(client, f"/plans/{followup['id']}/approvals", {
                    "expected_current_revision_id": revised_problem["id"],
                    "expected_plan_digest": followup["digest"], "accepted": True}, "paper-followup-approval")
                start = {"approval_id": fresh_approval["id"], "expected_plan_digest": followup["digest"]}
                recheck = post(client, f"/plans/{followup['id']}/runs", start, "paper-followup-start")
                self.assertEqual(worker(client.app.state.workflow, settings=settings).tick(), 1)
                finished = client.get(prefix + f"/runs/{recheck['id']}").json()
                self.assertEqual(finished["state"], "completed", finished)
                result = client.get(prefix + f"/records/{finished['scenarios'][0]['result_id']}").json()["body"]["result"]
                vectors = dict(zip(ids, plan["body"]["request"]["candidate_vectors"], strict=True))
                self.assertEqual({c["id"]: c["parameter_vector"] for c in result["candidates"]}, vectors)
                self.assertEqual(result["scientific_outcome"], expected_outcome)
                self.assertEqual(result["verification"], "valid")
                self.assertEqual(result["expected_binding"], "matches")
                self.assertEqual(result["replay"], "passed")
                self.assertIsNone(result.get("baseline_search"))

                reference, = result["artifacts"]
                download = client.get(prefix + f"/artifacts/{reference['id']}")
                self.assertEqual(download.status_code, 200)
                self.assertEqual(len(download.content), reference["byte_size"])
                self.assertEqual(hashlib.sha256(download.content).hexdigest(), reference["sha256"])
                self.assertEqual(download.headers["X-Artifact-SHA256"], reference["sha256"])
                anchor_response = client.get(prefix + f"/artifacts/{reference['id']}/anchor?download=true")
                self.assertEqual(anchor_response.status_code, 200)
                expected = anchor_response.json()
                self.assertEqual(set(expected), {"artifact_sha256", "dataset_digest", "problem_digest", "projection_digest",
                    "app_request_digest", "design_digest", "scenario_id", "run_id"})
                packet = download.json()
                self.assertEqual(packet["operation"], "recheck")
                self.assertEqual(packet["binding"]["observation_proposal"], {k: proposal[k] for k in ("id", "digest", "body")})
                self.assertEqual(packet["binding"]["observation_proposal"]["body"]["origin"], "actual")
                self.assertEqual(base64.b64decode(packet["history"]["bytes_base64"], validate=True), design_bytes)
                self.assertEqual(packet["history"]["anchors"], design_anchors)
                native = json.loads(base64.b64decode(packet["scientific"]["bytes_base64"], validate=True))
                self.assertEqual(native["operation"], "fixed_candidate_review")
                self.assertIsNone(native["search"])
                self.assertEqual({c["id"]: c["parameters"] for c in native["candidates"]}, vectors)
                self.assertEqual(native["problem"]["observations"][-1]["allowance"], text(allowance))
                process, fresh = baseline.replay_cli(self.replay, scratch, download.content, expected)
                self.assertEqual(process.returncode, 0, fresh)
                self.assertEqual(fresh["integrity"], "passed")
                self.assertEqual(fresh["replay"], "passed")
                self.assertEqual(fresh["expected_binding"], "matches")
                self.assertEqual(fresh["verification"], "valid")
                self.assertEqual(fresh["operation"], "recheck")
                self.assertEqual(fresh["dataset_origin"], "synthetic")
                self.assertEqual(fresh["outcome"]["scientific_outcome"], expected_outcome)
                for checked in (result["candidate_results"], fresh["candidate_results"]):
                    self.assertEqual({c["candidate_id"]: c["verification"] for c in checked}, expected_status)
                    self.assertEqual({c["candidate_id"] for c in checked if c["outside_closed_claim"]}, outside)
                    self.assertEqual({c["candidate_id"] for c in checked if c["is_counterexample"]}, expected_witnesses)
                    for candidate in checked:
                        status = expected_status[candidate["candidate_id"]]
                        row_id = proposal["body"]["row"]["id"]
                        self.assertEqual(candidate["violating_observation_ids"], [row_id] if status == "invalid" else [])
                        self.assertEqual(candidate["unresolved_observation_ids"], [row_id] if status == "inconclusive" else [])
                        if status == "inconclusive":
                            self.assertEqual(candidate["reason_code"], "insufficient_enclosure")
                process, failure = baseline.replay_cli(self.replay, scratch, download.content,
                    {**expected, "problem_digest": problem["digest"]})
                self.assertEqual(process.returncode, 2, failure)
                self.assertEqual(failure["error"]["code"], "wrong_specification_binding")
                self.assertEqual(post(client, f"/plans/{followup['id']}/runs", start, "paper-followup-retry")["id"], recheck["id"])
                self.assertEqual(worker(client.app.state.workflow, settings=settings).tick(), 0)
                design.assert_preserved_history(history)
                for old in (dataset, problem, record, proposal):
                    self.assertEqual(client.get(prefix + f"/records/{old['id']}").json(), old)
                self.assertEqual(client.get(prefix + f"/artifacts/{suggestion['artifacts'][0]['id']}").content, design_bytes)


if __name__ == "__main__":
    unittest.main()
