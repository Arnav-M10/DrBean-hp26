"""Evidence lanes: identity-bound reports, guard accounting, replay classification and the evidence_lanes gate."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from drbean_eval import history, lanes  # noqa: E402

IDENTITY = {"application_tree_sha256": "a" * 64, "harness_tree_sha256": "b" * 64, "fixtures_tree_sha256": "c" * 64,
            "engine_source_sha256": "d" * 64}


def report(lane, status="passed", *, dirty=False, evidence_class="executed_acceptance", **identity):
    return {"schema": lanes.SCHEMA, "report_id": f"lane_{lane}_{status}_{len(identity)}", "lane": lane,
            "status": status, "evidence_class": evidence_class, "app_under_test": None,
            "source_identity": {**IDENTITY, **identity, "worktree_dirty": dirty, "commit": "1" * 40},
            "results": {"counts": {"passed": 1}},
            "requests_and_usage": {"external_model_requests": {"status": "verified_zero", "value": 0}}}


class LaneStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.results = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def store(self, item, artifacts=None):
        return lanes._store(dict(item), self.results, artifacts or {})

    def gate(self):
        return lanes.lanes_gate(self.results, ROOT, current={**IDENTITY})


class GateTests(LaneStore):
    def test_all_required_lanes_at_the_identity_pass_and_live_is_not_run(self):
        for lane in lanes.REQUIRED_LANES:
            self.store(report(lane))
        result = self.gate()
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["lanes"]["live_gemini"]["status"], "not_run")
        self.assertFalse(result["lanes"]["live_gemini"]["required"])

    def test_a_report_from_another_source_identity_never_counts(self):
        for lane in lanes.REQUIRED_LANES:
            self.store(report(lane))
        self.store(report("controlled_science", application_tree_sha256="e" * 64))  # newer, but other code
        result = self.gate()
        self.assertEqual(result["status"], "passed")  # the newer foreign report neither helps nor hurts
        self.assertEqual(result["lanes"]["controlled_science"]["reports_at_other_identities"], 1)
        other = lanes.lanes_gate(self.results, ROOT, current={**IDENTITY, "engine_source_sha256": "f" * 64})
        self.assertEqual(other["status"], "blocked")
        self.assertTrue(all(other["lanes"][lane]["status"] == "blocked" for lane in lanes.REQUIRED_LANES))

    def test_each_identity_digest_is_enforced(self):
        for key in lanes.IDENTITY_KEYS:
            with self.subTest(key=key):
                self.assertFalse(lanes.identity_matches({**IDENTITY, key: "0" * 64}, IDENTITY))
                self.assertFalse(lanes.identity_matches({**IDENTITY, key: None}, {**IDENTITY, key: None}))
        self.assertTrue(lanes.identity_matches(dict(IDENTITY), IDENTITY))

    def test_newest_dirty_or_preview_report_blocks_despite_an_older_clean_pass(self):
        for lane in lanes.REQUIRED_LANES:
            self.store(report(lane))
        self.store(report("controlled_callbacks", dirty=True))
        result = self.gate()
        self.assertEqual(result["lanes"]["controlled_callbacks"]["status"], "blocked")
        self.assertEqual(result["status"], "blocked")
        self.store(report("controlled_callbacks"))
        self.store(report("historical_replay", evidence_class="preview"))
        result = self.gate()
        self.assertEqual(result["lanes"]["controlled_callbacks"]["status"], "passed")
        self.assertEqual(result["lanes"]["historical_replay"]["status"], "blocked")

    def test_dirty_flag_must_be_recorded_explicitly(self):
        item = report("controlled_callbacks")
        del item["source_identity"]["worktree_dirty"]
        self.assertIn("worktree dirty or not recorded", lanes.report_problems(item))

    def test_newest_failed_report_fails_and_a_later_clean_pass_supersedes_it(self):
        for lane in lanes.REQUIRED_LANES:
            self.store(report(lane))
        self.store(report("historical_replay", status="failed"))
        self.assertEqual(self.gate()["status"], "failed")
        self.store(report("historical_replay"))
        self.assertEqual(self.gate()["status"], "passed")

    def test_missing_lane_blocks(self):
        self.store(report("controlled_callbacks"))
        result = self.gate()
        self.assertEqual(result["status"], "blocked")
        self.assertEqual(result["lanes"]["historical_replay"]["status"], "blocked")


class ChainTests(LaneStore):
    def test_chain_and_artifacts_verify_and_tampering_is_detected(self):
        artifact = os.path.join(self.results, "probe.txt")
        with open(artifact, "w", encoding="utf-8") as handle:
            handle.write("evidence\n")
        stored = self.store(report("controlled_callbacks"), {"junit.xml": artifact})
        self.store(report("historical_replay"))
        self.assertEqual(lanes.verify(self.results), [])
        self.assertEqual(stored["prev_record_sha256"], history.GENESIS)
        kept = os.path.join(self.results, stored["artifacts"][0]["path"])
        with open(kept, "a", encoding="utf-8") as handle:
            handle.write("edited\n")
        self.assertTrue(any("changed or missing" in p for p in lanes.verify(self.results)))

    def test_rewritten_line_breaks_the_chain_and_fails_the_gate(self):
        for lane in lanes.REQUIRED_LANES:
            self.store(report(lane))
        path = os.path.join(self.results, lanes.REPORTS)
        with open(path, encoding="utf-8") as handle:
            lines = handle.readlines()
        first = json.loads(lines[0])
        first["status"] = "passed"
        first["results"] = {"counts": {"passed": 99}}
        lines[0] = json.dumps(first, sort_keys=True, separators=(",", ":")) + "\n"
        with open(path, "w", encoding="utf-8") as handle:
            handle.writelines(lines)
        self.assertTrue(any("breaks the hash chain" in p for p in lanes.verify(self.results)))
        self.assertEqual(self.gate()["status"], "failed")


class AccountingTests(unittest.TestCase):
    def write(self, directory, name, events):
        path = os.path.join(directory, name)
        with open(path, "w", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event) + "\n")
        return path

    def test_verified_zero_needs_the_guard_in_every_log_and_every_stack(self):
        with tempfile.TemporaryDirectory() as tmp:
            archive = os.path.join(tmp, "stacks")
            os.makedirs(archive)
            session = self.write(tmp, "session.jsonl", [{"kind": "guard_installed", "pid": 1}])
            self.assertEqual(lanes.dispatch_accounting(session, archive)["external_model_requests"]["status"],
                             "verified_zero")
            self.write(archive, "s1.started", [{}])
            unknown = lanes.dispatch_accounting(session, archive)["external_model_requests"]
            self.assertEqual((unknown["status"], unknown["value"]), ("unknown", None))  # a stack log is missing
            self.write(archive, "s1.guard.jsonl", [{"kind": "credential_read", "name": "GEMINI_API_KEY"}])
            self.assertEqual(lanes.dispatch_accounting(session, archive)["external_model_requests"]["status"],
                             "unknown")  # that stack's processes never installed the guard
            self.write(archive, "s1.guard.jsonl", [{"kind": "guard_installed", "pid": 2,
                                                    "credential_names_present": ["GEMINI_API_KEY"]}])
            result = lanes.dispatch_accounting(session, archive)
            self.assertEqual(result["external_model_requests"]["status"], "verified_zero")
            self.assertEqual(result["guard"]["credential_variable_names_present"], ["GEMINI_API_KEY"])
            self.assertEqual(lanes.dispatch_accounting(os.path.join(tmp, "absent.jsonl"), None)[
                "external_model_requests"]["status"], "unknown")

    def test_only_an_announced_probe_is_excused_and_only_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = self.write(tmp, "session.jsonl", [
                {"kind": "guard_installed", "pid": 1},
                {"kind": "guard_self_test_probe", "expect": "egress_blocked", "test": "t1", "pid": 1},
                {"kind": "egress_blocked", "host": "example.invalid", "pid": 1},
            ])
            result = lanes.dispatch_accounting(session, None)["external_model_requests"]
            self.assertEqual(result["status"], "verified_zero")
            self.assertEqual(result["deliberate_guard_probes"][0]["test"], "t1")
            for extra in ({"kind": "egress_blocked", "host": "example.invalid", "pid": 1},  # second event: not covered
                          {"kind": "provider_client_blocked", "client": "google.genai.Client", "pid": 1}):
                with self.subTest(extra=extra["kind"]):
                    with open(session, "a", encoding="utf-8") as handle:
                        handle.write(json.dumps(extra) + "\n")
                    result = lanes.dispatch_accounting(session, None)["external_model_requests"]
                    self.assertEqual(result["status"], "attempted_and_blocked")
                    self.assertIsNone(result["value"])

    def test_probe_announced_by_another_process_does_not_excuse_an_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = self.write(tmp, "session.jsonl", [
                {"kind": "guard_installed", "pid": 1},
                {"kind": "guard_self_test_probe", "expect": "egress_blocked", "test": "t1", "pid": 1},
                {"kind": "egress_blocked", "host": "example.invalid", "pid": 7},
            ])
            result = lanes.dispatch_accounting(session, None)["external_model_requests"]
            self.assertEqual(result["status"], "attempted_and_blocked")
            self.assertIn({"unmatched_announcements": ["t1"]}, result["deliberate_guard_probes"])

    def test_tokens_are_never_reported_as_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            session = self.write(tmp, "session.jsonl", [{"kind": "guard_installed", "pid": 1}])
            result = lanes.dispatch_accounting(session, None)
            self.assertIsNone(result["provider_tokens"]["value"])
            self.assertIsNone(result["controlled_model_invocations"]["value"])
        self.assertEqual(lanes.live_not_run_statement()["status"], "not_run")


class OriginalCheckerTests(unittest.TestCase):
    def git(self, repo, *args):
        return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True, text=True).stdout.strip()

    def test_original_checker_is_extracted_at_the_recorded_commit_only(self):
        with tempfile.TemporaryDirectory() as repo, tempfile.TemporaryDirectory() as work:
            self.git(repo, "init", "-q")
            self.git(repo, "config", "user.email", "eval@example.invalid")
            self.git(repo, "config", "user.name", "eval")
            engine = os.path.join(repo, "packages", "groundwork_adapter", "counterdex")
            os.makedirs(engine)
            with open(os.path.join(engine, "core.py"), "w", encoding="utf-8") as handle:
                handle.write("VERSION = 'old'\n")
            self.git(repo, "add", "-A")
            self.git(repo, "commit", "-qm", "old engine")
            old = self.git(repo, "rev-parse", "HEAD")
            with open(os.path.join(engine, "core.py"), "w", encoding="utf-8") as handle:
                handle.write("VERSION = 'new'\n")
            self.git(repo, "commit", "-qam", "new engine")
            package = lanes.original_checker(repo, old, work)
            with open(os.path.join(package, "counterdex", "core.py"), encoding="utf-8") as handle:
                self.assertEqual(handle.read(), "VERSION = 'old'\n")
            self.assertIsNone(lanes.original_checker(repo, "0" * 40, work))
            self.assertIsNone(lanes.original_checker(repo, "not-a-commit; rm -rf /", work))
            self.assertIsNone(lanes.original_checker(repo, None, work))
            self.assertEqual(lanes.packet_commit(repo, {"origin": {"tested_commit": old}}), (old, "attempt tested_commit"))
            self.assertEqual(lanes.packet_commit(repo, {"origin": {"path": "packages/x/docs/review-evidence/4f6c580/u.json"}}),
                             ("4f6c580", "review-evidence directory commit"))
            self.assertEqual(lanes.packet_commit(repo, {"origin": {}}), (None, "unknown"))


class EnginePreconditionTests(unittest.TestCase):
    def test_precondition_follows_the_applications_import_not_the_installed_copy(self):
        app = os.path.dirname(ROOT)
        source = lanes.engine_controls.engine_source_identity(os.path.join(app, "packages", "groundwork_adapter"))
        repository = {"imported_from": "repository", "version": "x", "source_sha256": source["source_sha256"]}
        for installed, expected in (({"installed": False}, True), ({"installed": True, "matches_repository": True}, True),
                                    ({"installed": True, "matches_repository": False, "differing_files": ["core.py"]},
                                     False)):
            with self.subTest(installed=installed):
                result = lanes.engine_precondition({"versions": {"engine_repository": repository,
                                                                 "engine_installed": installed}}, app)
                self.assertEqual(result["passed"], expected, result["detail"])
        for imported in ({**repository, "imported_from": "elsewhere"}, {**repository, "source_sha256": "0" * 64}, {}):
            with self.subTest(imported=imported):
                result = lanes.engine_precondition({"versions": {"engine_repository": imported,
                                                                 "engine_installed": {"installed": False}}}, app)
                self.assertFalse(result["passed"])


class JunitAndReplayTests(unittest.TestCase):
    def test_junit_outcomes(self):
        xml = ('<?xml version="1.0"?><testsuites><testsuite name="pytest">'
               '<testcase classname="m" name="ok"/>'
               '<testcase classname="m" name="bad"><failure message="boom"/></testcase>'
               '<testcase classname="m" name="err"><error message="setup"/></testcase>'
               '<testcase classname="m" name="gap"><skipped type="pytest.xfail" message="F-X known gap"/></testcase>'
               '<testcase classname="m" name="absent"><skipped type="pytest.xfail" '
               'message="NOT_AVAILABLE: papers capability absent"/></testcase>'
               '<testcase classname="m" name="skip"><skipped type="pytest.skip" message="why"/></testcase>'
               '<testcase classname="m" name="todo"><skipped type="pytest.xfail" '
               'message="HARNESS_PENDING: papers advertised"/></testcase>'
               '<testcase classname="m" name="heavy"><skipped type="pytest.xfail" '
               'message="NOT_RUN: heavy resource attack is opt-in"/></testcase>'
               '</testsuite></testsuites>')
        with tempfile.NamedTemporaryFile("w", suffix=".xml", delete=False) as handle:
            handle.write(xml)
        try:
            result = lanes.parse_junit(handle.name)
        finally:
            os.unlink(handle.name)
        self.assertEqual(result["counts"], {"passed": 1, "failed": 2, "xfailed": 1, "skipped": 1, "not_available": 1,
                                            "harness_pending": 1, "not_run": 1})
        self.assertEqual({t["id"]: t["outcome"] for t in result["tests"]}["m::absent"], "not_available")
        self.assertIsNone(lanes.parse_junit("/nonexistent/junit.xml")["counts"])

    def test_replay_classification(self):
        self.assertEqual(lanes.classify_replay({"status": "passed", "report": {"replay": "passed"}}), "replayed")
        self.assertEqual(lanes.classify_replay({"status": "rejected", "error": {"code": "source_version_mismatch"}}),
                         "incompatible_version")
        self.assertEqual(lanes.classify_replay({"status": "rejected", "error": {"code": "anchor_mismatch"}}),
                         "rejected")
        self.assertEqual(lanes.classify_replay({"status": "failed", "report": {
            "integrity": "passed", "expected_binding": "matches", "replay": "not_applicable"}}), "bound_not_checked")
        self.assertEqual(lanes.classify_replay({"status": "failed", "report": {
            "integrity": "failed", "expected_binding": "matches", "replay": "not_applicable"}}), "failed")
        self.assertEqual(lanes.classify_replay({"status": "failed", "report": {
            "integrity": "passed", "expected_binding": "matches", "replay": "failed"}}), "failed")
        self.assertEqual(lanes.classify_replay({"status": "timed_out"}), "error")


class IdentityTests(unittest.TestCase):
    def git(self, repo, *args):
        subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True)

    def write(self, repo, rel, text):
        path = os.path.join(repo, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def test_evidence_only_changes_keep_the_identity_and_code_changes_do_not(self):
        with tempfile.TemporaryDirectory() as repo:
            self.git(repo, "init", "-q")
            self.git(repo, "config", "user.email", "eval@example.invalid")
            self.git(repo, "config", "user.name", "eval")
            for rel in ("apps/api/bean_api/ai_prompts.py", "packages/groundwork_adapter/counterdex/core.py",
                        "evaluation/drbean_eval/gates.py", "evaluation/results/attempts.jsonl",
                        "evaluation/findings.json", "tests/integration/test_x.py", "fixtures/intake/a.txt"):
                self.write(repo, rel, 'SOURCE_PROPOSAL_PROMPT_VERSION = "p.v1"\n' if rel.endswith("prompts.py")
                           else f"{rel}\n")
            self.git(repo, "add", "-A")
            self.git(repo, "commit", "-qm", "base")
            first = lanes.source_identity(repo)
            self.assertFalse(first["worktree_dirty"])
            self.assertEqual(lanes.application_versions(repo),
                             {"apps/api/bean_api/ai_prompts.py:SOURCE_PROPOSAL_PROMPT_VERSION": "p.v1"})
            self.write(repo, "evaluation/results/attempts.jsonl", "more evidence\n")
            self.write(repo, "evaluation/findings.json", "{}\n")
            self.git(repo, "commit", "-qam", "evidence")
            second = lanes.source_identity(repo)
            self.assertNotEqual(first["commit"], second["commit"])
            self.assertTrue(lanes.identity_matches(second, first))
            for rel, key in (("tests/integration/test_x.py", "harness_tree_sha256"),
                             ("apps/api/bean_api/ai_prompts.py", "application_tree_sha256"),
                             ("fixtures/intake/a.txt", "fixtures_tree_sha256"),
                             ("packages/groundwork_adapter/counterdex/core.py", "engine_source_sha256")):
                with self.subTest(rel=rel):
                    before = lanes.source_identity(repo)
                    self.write(repo, rel, f"changed {rel}\n")
                    self.assertTrue(lanes.source_identity(repo)["worktree_dirty"])
                    self.git(repo, "commit", "-qam", f"change {rel}")
                    after = lanes.source_identity(repo)
                    self.assertNotEqual(before[key], after[key])
                    self.assertFalse(lanes.identity_matches(after, before))


if __name__ == "__main__":
    unittest.main()
