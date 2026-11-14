"""Unit tests for the offline real-science lane, qualification, history, gates and budget hardening.

Standard library only; no product stack is launched here (tests/integration does that).
Every subject in this module is a harness test double, never product evidence.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from fractions import Fraction

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(ROOT)
sys.path.insert(0, ROOT)

import cli  # noqa: E402
from drbean_eval import gates, history, kinetics, launcher, manifest, native, runner  # noqa: E402
from drbean_eval.budget import BudgetLedger, UsageRejected  # noqa: E402
from drbean_eval.subject import NoSubject, RecordedSubject  # noqa: E402


def fabricated(entry_id="RS-HERO-FULL", **changes):
    """An observation that *claims* success, with nothing behind it."""
    m = manifest.load(ROOT)
    packet = next(e["packet"] for e in m["schedule"]["offline_real_science"] if e["entry_id"] == entry_id)
    obs = {"schema": "eval-observation/v1", "lane": "offline_real_science", "operation": "science",
           "tested_commit": runner.git_state(REPO)["commit"],
           "case_sha256": m["science_packets"][packet]["sha256"],
           "provider": {"transport": "none"}, "tools": {"transport": "real"}, "provider_requests": 0,
           "state": "completed", "status": "passed",
           "external_dispatch": {"verified": True, "egress_attempts": 0, "client_constructions": 0},
           "checks": [{"id": "everything", "outcome": "passed", "level": "required"}],
           "records": {"run_id": "run_fabricated"}, "evidence_index": {}, "native_artifacts": []}
    obs.update(changes)
    return obs


class ExecutingDouble:
    """Pretends to execute (sets the executes_acceptance flag) but writes no corroborating evidence."""
    name = "harness-test-double"
    accepts_context = True
    executes_acceptance = True
    science_python = None
    package_dir = None

    def __init__(self, observation):
        self.observation = observation
        self.attempt_context = {}

    def describe(self):
        return {"subject": "harness-test-double"}

    def run_entry(self, entry, variant, lane):
        os.makedirs(self.attempt_context["evidence_dir"], exist_ok=True)
        return dict(self.observation, case_sha256=self.attempt_context["case_sha256"])


class Base(unittest.TestCase):
    def setUp(self):
        self.results = tempfile.mkdtemp()
        self.ledger = os.path.join(self.results, "ledger.jsonl")

    def tearDown(self):
        shutil.rmtree(self.results)

    def run_lane(self, subject, only=None, lane="offline_real_science"):
        return runner.run_lane(lane, subject, ROOT, self.results, REPO, only, self.ledger)


class ManifestV2(unittest.TestCase):
    def test_lane_rules_and_disabled_live_lanes(self):
        m = manifest.load(ROOT)
        self.assertGreaterEqual(m["manifest_version"], 2)
        self.assertEqual(sorted(m["lanes"]), sorted(manifest.LANES))
        for lane, rule in m["lanes"].items():
            if rule["live_provider"]:
                self.assertFalse(rule["enabled"], lane)
        offline = m["lanes"]["offline_real_science"]
        self.assertEqual((offline["tools"], offline["cohort"], offline["zero_dispatch_required"]), ("real", False, True))
        self.assertNotIn("live", offline["provider"])
        self.assertEqual([e["entry_id"] for e in m["schedule"]["offline_real_science"]][-1], "RS-ZERO-DISPATCH")

    def test_v1_is_archived_byte_identical_and_old_attempts_still_reference_it(self):
        m = manifest.load(ROOT)
        v1 = next(a for a in m["supersedes"] if a["manifest_version"] == 1)
        self.assertEqual(manifest.sha256_file(os.path.join(ROOT, v1["archived"])), v1["sha256"])
        historical = [a for a in runner.read_attempts(os.path.join(ROOT, "results")) if a["manifest_version"] == 1]
        self.assertEqual(len(historical), 34)  # the pre-merge unrun inventory is preserved, not relabelled
        self.assertEqual({a["manifest_sha256"] for a in historical}, {v1["sha256"]})
        self.assertEqual({a["status"] for a in historical}, {"unrun"})

    def test_tampered_archive_or_packet_is_detected(self):
        work = tempfile.mkdtemp()
        try:
            copy = os.path.join(work, "evaluation")
            shutil.copytree(ROOT, copy, ignore=shutil.ignore_patterns("results", "__pycache__"))
            with open(os.path.join(copy, "manifests", "manifest-v1.json"), "ab") as handle:
                handle.write(b" ")
            with open(os.path.join(copy, "cases", "science", "hero-v1.json"), "ab") as handle:
                handle.write(b" ")
            problems = " ".join(manifest.verify(copy))
            self.assertIn("archived manifest v1 does not match", problems)
            self.assertIn("science packet changed without a manifest version", problems)
        finally:
            shutil.rmtree(work)

    def test_packets_keep_separate_identities_and_synthetic_provenance(self):
        packets = {}
        for name in manifest.SCIENCE_PACKETS:
            with open(os.path.join(ROOT, "cases", "science", name + ".json"), encoding="utf-8") as handle:
                packets[name] = json.load(handle)
        self.assertEqual(packets["hero-v1"]["provenance"]["origin"], "synthetic")
        self.assertEqual(packets["hero-v1"]["dataset"]["origin"], "synthetic")
        self.assertIn("NEVER a production result lookup", packets["fixed-pair-regression-v1"]["identity_note"])
        self.assertNotIn("pair", packets["hero-v1"])  # the regression pair is never part of an application input
        rows = packets["hero-v1"]["dataset"]["rows"]
        self.assertEqual([(r["original_values"]["time"], r["original_values"]["concentration"]) for r in rows],
                         [("0.25", "4.80"), ("0.5", "7.20"), ("1", "8.00"), ("2", "6.80"), ("4", "5.70")])
        self.assertEqual({r["hard_allowance"] for r in rows}, {"1/2"})


class OfflineLaneRunner(Base):
    def test_no_subject_records_every_entry_unrun_without_any_cohort(self):
        records = self.run_lane(NoSubject())
        self.assertEqual(len(records), 7)
        self.assertEqual({r["status"] for r in records}, {"unrun"})
        self.assertFalse(os.path.exists(self.ledger))  # the offline lane never touches a provider budget
        self.assertTrue(all(r["lane_version"] == 1 and r["packet"] for r in records))

    def test_offline_attestation_refuses_live_or_nonzero_or_controlled_tools(self):
        for change, needle in ((dict(provider={"transport": "live"}), "not admitted"),
                               (dict(provider_requests=1), "zero provider requests"),
                               (dict(tools={"transport": "controlled"}), "real scientific tools")):
            record = self.run_lane(ExecutingDouble(fabricated(**change)), ["RS-HERO-FULL"])[0]
            self.assertEqual(record["status"], "error", change)
            self.assertIn(needle, record["reason"])

    def test_imported_success_claim_never_qualifies(self):
        directory = tempfile.mkdtemp()
        try:
            with open(os.path.join(directory, "RS-HERO-FULL.observation.json"), "w", encoding="utf-8") as handle:
                json.dump(fabricated(), handle)
            record = self.run_lane(RecordedSubject(directory), ["RS-HERO-FULL"])[0]
            self.assertEqual(record["status"], "failed")
            self.assertEqual(record["evidence_class"], "imported_claim")
            self.assertIn("imported observation", record["reason"])
        finally:
            shutil.rmtree(directory)

    def test_state_completed_without_evidence_fails_qualification(self):
        index = {"hero-run": {"path": "records/hero-run.json", "sha256": "0" * 64}}
        record = self.run_lane(ExecutingDouble(fabricated(evidence_index=index)), ["RS-HERO-FULL"])[0]
        self.assertEqual(record["status"], "failed")
        failed = [c["id"] for c in record["qualification"]["qualifier_checks"] if not c["passed"]]
        self.assertIn("file:hero-run", failed)

    def test_unverified_dispatch_is_unknown_not_zero(self):
        obs = fabricated(external_dispatch={"verified": False, "egress_attempts": 0, "client_constructions": 0})
        record = self.run_lane(ExecutingDouble(obs), ["RS-HERO-FULL"])[0]
        self.assertEqual(record["status"], "failed")
        self.assertEqual(record["external_model_requests"], {"value": None, "basis": "unknown"})

    def test_blocked_prerequisite_is_unrun_never_passed(self):
        obs = fabricated(checks=[{"id": "a", "outcome": "passed", "level": "required"},
                                 {"id": "b", "outcome": "blocked", "level": "required", "finding": "F-X",
                                  "detail": "owner prerequisite absent"}])
        record = self.run_lane(ExecutingDouble(obs), ["RS-HERO-FULL"])[0]
        self.assertEqual(record["status"], "unrun")
        self.assertIn("blocked", record["reason"])
        self.assertIn("F-X", record["reason"])

    def test_external_attempt_fails_even_when_blocked_by_the_guard(self):
        obs = fabricated(external_dispatch={"verified": True, "egress_attempts": 1, "client_constructions": 0},
                         provider_requests=0)
        record = self.run_lane(ExecutingDouble(obs), ["RS-HERO-FULL"])[0]
        self.assertEqual(record["status"], "failed")
        self.assertIn("zero_external_model_dispatch", record["reason"])


class AppendOnlyHistory(Base):
    def test_chain_and_trace_tampering_are_detected(self):
        self.run_lane(NoSubject(), ["RS-HERO-FULL", "RS-ZERO-DISPATCH"])
        self.run_lane(ExecutingDouble(fabricated()), ["RS-HERO-FULL"])
        self.assertEqual(history.verify(self.results), [])
        path = os.path.join(self.results, "attempts.jsonl")
        with open(path, encoding="utf-8") as handle:
            lines = handle.readlines()
        edited = json.loads(lines[0])
        edited["status"] = "passed"
        with open(path, "w", encoding="utf-8") as handle:
            handle.writelines([json.dumps(edited, sort_keys=True) + "\n"] + lines[1:])
        self.assertTrue(any("chain break" in p for p in history.verify(self.results)))
        with open(path, "w", encoding="utf-8") as handle:
            handle.writelines(lines[1:])  # deleting the first line breaks the chain too
        self.assertTrue(history.verify(self.results))
        with open(path, "w", encoding="utf-8") as handle:
            handle.writelines(lines)
        traced = json.loads(lines[-1])
        with open(os.path.join(self.results, traced["trace"]), "a", encoding="utf-8") as handle:
            handle.write(" ")
        self.assertTrue(any("trace" in p and "changed" in p for p in history.verify(self.results)))

    def test_real_repository_history_verifies(self):
        self.assertEqual(history.verify(os.path.join(ROOT, "results")), [])


class DirtyFlag(unittest.TestCase):
    def test_evidence_output_on_the_first_status_line_is_not_dirty(self):
        """Regression: harness 0.1.0 stripped porcelain output and lost the first line's leading space."""
        work = tempfile.mkdtemp()
        try:
            def git(*args):
                subprocess.run(["git", "-C", work, *args], check=True, capture_output=True)
            git("init", "-q")
            git("config", "user.email", "harness@example.invalid")
            git("config", "user.name", "harness")
            os.makedirs(os.path.join(work, "evaluation", "results"))
            for rel in ("evaluation/results/attempts.jsonl", "code.py"):
                with open(os.path.join(work, rel), "w", encoding="utf-8") as handle:
                    handle.write("x\n")
            git("add", ".")
            git("commit", "-q", "-m", "init")
            with open(os.path.join(work, "evaluation/results/attempts.jsonl"), "a", encoding="utf-8") as handle:
                handle.write("y\n")
            self.assertFalse(runner.git_state(work)["dirty"])
            with open(os.path.join(work, "code.py"), "a", encoding="utf-8") as handle:
                handle.write("y\n")
            state = runner.git_state(work)
            self.assertTrue(state["dirty"])
            self.assertEqual(state["changed"], ["code.py"])
        finally:
            shutil.rmtree(work)


class Gates(Base):
    def test_absent_evidence_blocks_release_but_inventory_succeeds(self):
        result = gates.compute(ROOT, self.results, "0" * 40, False)
        status = {g["gate"]: g["status"] for g in result["gates"]}
        self.assertEqual(status["real_science_http"], "blocked")
        self.assertEqual(status["live_gemini_qualification"], "not_run")
        self.assertNotEqual(result["overall"], "passed")
        self.assertEqual(cli.main(["inventory", "--results", self.results]), 0)
        self.assertNotEqual(cli.main(["gate", "--require", "release", "--results", self.results]), 0)

    def test_imported_pass_cannot_satisfy_a_gate(self):
        attempt = {"entry_id": "RS-HERO-FULL", "lane": "offline_real_science", "tested_commit": "c" * 40,
                   "status": "passed", "evidence_class": "imported_claim", "attempt_id": "att_x", "reason": None}
        gate = gates._entry_gate("real_science_http", {"RS-HERO-FULL": attempt}, ("RS-HERO-FULL",), "")
        self.assertEqual(gate["status"], "blocked")

    def test_open_p0_fails_the_release(self):
        findings = os.path.join(self.results, "findings.json")
        with open(findings, "w", encoding="utf-8") as handle:
            json.dump({"findings": [{"id": "F-1", "severity": "P0", "status": "open"}]}, handle)
        result = gates.compute(ROOT, self.results, "0" * 40, False, findings)
        self.assertEqual(next(g for g in result["gates"] if g["gate"] == "no_unresolved_p0")["status"], "failed")


class BudgetHardening(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.ledger = BudgetLedger(os.path.join(self.dir, "b.jsonl"))
        self.ledger.open_cohort("t", "A. Human", "synthetic test allowance")

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_reproduced_probe_negative_usage_and_seven_attempts(self):
        rid = self.ledger.reserve("t", "p", "C01", 3000, 700, "unit")
        with self.assertRaises(UsageRejected):
            self.ledger.reconcile(rid, -10, -20, "completed", None, 7)
        self.ledger.mark_unknown(rid, "usage_rejected", 7)
        state = self.ledger.state()
        self.assertEqual(state["committed"], {"provider_requests": 7, "input_tokens": 3000, "output_tokens": 700})
        self.assertLessEqual(state["remaining"]["provider_requests"], 32 - 7)

    def test_boolean_float_and_zero_attempts_are_rejected(self):
        rid = self.ledger.reserve("t", "p", "C01", 3000, 700, "unit")
        for args in ((True, 1, "ok", None, 1), (1.5, 1, "ok", None, 1), (1, 1, "ok", None, 0), (1, 1, "", None, 1)):
            with self.assertRaises(UsageRejected, msg=args):
                self.ledger.reconcile(rid, *args)

    def test_retries_count_as_requests_and_flag_overrun(self):
        rid = self.ledger.reserve("t", "p", "C01", 3000, 700, "unit")
        self.assertTrue(self.ledger.reconcile(rid, 100, 10, "completed", "req", 3)["overrun"])
        self.assertEqual(self.ledger.state()["committed"]["provider_requests"], 3)

    def test_untrusted_or_malformed_usage_never_refunds(self):
        ids = [self.ledger.reserve("t", "p", "C01", 3000, 700, "unit") for _ in range(2)]
        runner._reconcile(self.ledger, ids, {"usage": {"requests": [{"acceptance": "known", "input_tokens": 1,
                                                                      "output_tokens": 1}]}}, None, trusted=False)
        self.assertEqual(self.ledger.state()["committed"]["input_tokens"], 6000)
        more = [self.ledger.reserve("t", "p", "C01", 3000, 700, "unit")]
        problem = runner._reconcile(self.ledger, more, {"usage": {"requests": "not-a-list"}}, None)
        self.assertIn("malformed", problem)
        self.assertEqual(self.ledger.state()["committed"]["input_tokens"], 9000)

    def test_more_reported_requests_than_reserved_slots_is_recorded(self):
        ids = [self.ledger.reserve("t", "p", "C01", 3000, 700, "unit")]
        reqs = [{"acceptance": "known", "input_tokens": 10, "output_tokens": 1, "network_attempts": 1}] * 2
        problem = runner._reconcile(self.ledger, ids, {"usage": {"requests": reqs}}, None)
        self.assertIn("unreserved dispatch", problem)
        with open(self.ledger.path, encoding="utf-8") as handle:
            self.assertIn("reconcile_error", handle.read())


class IndependentOracle(unittest.TestCase):
    def setUp(self):
        with open(os.path.join(ROOT, "cases", "science", "fixed-pair-regression-v1.json"), encoding="utf-8") as h:
            self.pair = {p["id"]: p for p in json.load(h)["pair"]}
        with open(os.path.join(ROOT, "cases", "science", "hero-v1.json"), encoding="utf-8") as h:
            self.hero = json.load(h)

    def test_audit_numbers_recomputed_independently(self):
        pair = list(self.pair.values())
        self.assertAlmostEqual(float(kinetics.separation_margin(pair, "8", "0.2")), 0.76719, places=5)
        self.assertAlmostEqual(float(kinetics.separation_margin(pair, "6", "0.2")), 0.55535, places=5)
        self.assertLess(kinetics.separation_margin(pair, "8", "0.6"), 0)
        for name in self.pair:
            self.assertEqual(kinetics.history_verdict(self.pair[name], self.hero["dataset"]["rows"]), "compatible")
        expect = {"3.4": ("compatible", "excluded"), "4.57": ("excluded", "compatible"), "4.0": ("excluded", "excluded")}
        for reading, (ref, out) in expect.items():
            self.assertEqual(kinetics.band_verdict(self.pair["reference"], "8", reading, "0.2"), ref)
            self.assertEqual(kinetics.band_verdict(self.pair["outside"], "8", reading, "0.2"), out)

    def test_closed_endpoint_is_inside(self):
        self.assertFalse(kinetics.outside_closed_claim("1/10", "1/10", "17/100"))
        self.assertFalse(kinetics.outside_closed_claim("17/100", "1/10", "17/100"))
        self.assertTrue(kinetics.outside_closed_claim("37/500", "1/10", "17/100"))
        self.assertTrue(kinetics.outside_closed_claim(Fraction(171, 1000), "1/10", "17/100"))


class NativeEvidenceHandling(unittest.TestCase):
    def test_entity_envelope_is_not_a_native_packet(self):
        envelope = json.dumps({"id": "evidence_1", "kind": "evidence", "workspace_id": "ws", "body": {
            "result": {"artifacts": [{"id": "a", "sha256": "0" * 64}]}}}).encode()
        self.assertEqual(native.classify(envelope)["class"], "entity_envelope")
        self.assertEqual(native.classify(b'{"schema_version":"groundwork.suggestion-bundle.v1"}')["class"],
                         "native_packet")

    def test_download_checks_catch_each_mismatch(self):
        data = b"bytes"
        reference = {"sha256": native.sha256(data), "byte_size": 5, "media_type": "application/json"}
        good = native.validate_download(reference, data, {"x-artifact-sha256": native.sha256(data),
                                                          "content-type": "application/json"})
        self.assertTrue(all(c["passed"] for c in good))
        bad = native.validate_download({**reference, "byte_size": 6}, b"bytez", {"content-type": "text/plain"})
        self.assertEqual(sum(not c["passed"] for c in bad), 4)

    def test_anchors_come_from_named_record_fields_only(self):
        record = {"body": {"result": {"scientific_problem_digest": "a" * 64, "nested": [{"suggestion_digest": "b" * 64}],
                                      "problem_digest": "c" * 64}}}
        self.assertEqual(native.anchors_from_record(record),
                         {"problem_digest": "a" * 64, "suggestion_digest": "b" * 64})


class GuardAndLauncher(unittest.TestCase):
    def test_guard_blocks_external_egress_and_allows_loopback(self):
        work = tempfile.mkdtemp()
        try:
            log = os.path.join(work, "guard.jsonl")
            script = ("import socket\n"
                      "s=socket.socket(); s.bind(('127.0.0.1',0)); s.listen(1)\n"
                      "socket.create_connection(('127.0.0.1', s.getsockname()[1])).close()\n"
                      "try:\n socket.create_connection(('example.invalid', 443), timeout=1); print('LEAK')\n"
                      "except OSError: print('blocked')\n")
            env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": launcher.GUARD_DIR, "DRBEAN_EGRESS_GUARD_LOG": log}
            out = subprocess.run([sys.executable, "-c", script], env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(out.stdout.strip(), "blocked", out.stderr)
            with open(log, encoding="utf-8") as handle:
                kinds = [json.loads(line)["kind"] for line in handle]
            self.assertEqual(kinds, ["guard_installed", "egress_blocked"])
        finally:
            shutil.rmtree(work)

    def test_launcher_refuses_credentials_and_real_looking_values(self):
        check = launcher.LocalStack._checked_extra_env
        with self.assertRaises(launcher.StackError):
            check({"GEMINI_API_KEY": "AIza" + "x" * 35}, True)
        with self.assertRaises(launcher.StackError):
            check({"GEMINI_API_KEY": "DRBEAN-DUMMY-KEY-0001"}, False)
        with self.assertRaises(launcher.StackError):
            check({"HTTP_PROXY": "http://example.invalid"}, True)
        self.assertEqual(check({"GEMINI_API_KEY": "DRBEAN-DUMMY-KEY-0001"}, True),
                         {"GEMINI_API_KEY": "DRBEAN-DUMMY-KEY-0001"})
        self.assertEqual(check({"BEAN_SCIENCE_ADAPTER": "counterdex"}, False), {"BEAN_SCIENCE_ADAPTER": "counterdex"})

    def test_cli_has_no_live_activation_and_refuses_to_open_a_cohort(self):
        work = tempfile.mkdtemp()
        try:
            self.assertEqual(cli.main(["budget", "open", "--cohort", "x", "--authorized-by", "A", "--spending-note",
                                       "n"]), 1)
        finally:
            shutil.rmtree(work)
        with open(os.path.join(ROOT, "cli.py"), encoding="utf-8") as handle:
            text = handle.read()
        self.assertNotIn("LiveActivation(", text)
        self.assertNotIn("SyntheticActivation(", text)


if __name__ == "__main__":
    unittest.main()


class Projection(unittest.TestCase):
    def test_field_paths_round_trip_and_unknowns_refuse(self):
        from drbean_eval import projection
        pairs = {"rows[0].time": "row1_time", "rows[4].concentration": "row5_concentration",
                 "rows[2].hard_allowance": "row3_allowance", "domain.A.lower": "A_min", "domain.ke.upper": "ke_max",
                 "target.lower": "target_min", "target.upper": "target_max", "model": "model_template"}
        for production, evaluation in pairs.items():
            self.assertEqual(projection.field_to_eval(production), evaluation)
            self.assertEqual(projection.field_to_production(evaluation), production)
        self.assertEqual(projection.field_to_eval("ka.upper"), "ka_max")
        for bad in ("rows[0].notes", "approvals[0].accepted", "row0_time"):
            with self.assertRaises(projection.ProjectionError):
                (projection.field_to_eval if "[" in bad or "." in bad else projection.field_to_production)(bad)

    def test_bbox_corners_are_not_width_height(self):
        from drbean_eval import projection
        self.assertEqual(projection.bbox_to_xywh([44, 39, 685, 68], 1000, 814), [44, 39, 641, 29])
        self.assertEqual(projection.xywh_to_bbox([44, 39, 641, 29], 1000, 814), [44, 39, 685, 68])
        for bbox in ([10, 10, 10, 20], [0, 0, 1001, 10], [5, 5, 2, 9]):
            with self.assertRaises(projection.ProjectionError):
                projection.bbox_to_xywh(bbox, 1000, 814)
        with self.assertRaises(projection.ProjectionError):
            projection.xywh_to_bbox([990, 10, 20, 5], 1000, 814)  # would extend past the right edge
        with self.assertRaises(projection.ProjectionError):
            projection.bbox_to_xywh([0, 0, 5, 5], 0, 814)  # original dimensions are required

    def test_intake_field_keeps_source_identity_and_spelling(self):
        from drbean_eval import projection
        source = {"id": "source_1", "body": {"sha256": "a" * 64, "width": 1200, "height": 1550}}
        field = {"field_path": "rows[0].hard_allowance", "original_value": "0.05", "candidate_exact": "1/20",
                 "unit": "mg/L", "ambiguity": "0.05 or 0.5", "grounding": "unreviewed_visual",
                 "locator": {"page": 1, "label": "row 1", "excerpt": "0.05", "bbox": [100, 200, 160, 230]}}
        out = projection.intake_field_to_eval(field, source)
        self.assertEqual(out["field"], "row1_allowance")
        self.assertEqual((out["value"], out["original_value"], out["status"]), ("1/20", "0.05", "ambiguous"))
        self.assertEqual(out["source_ref"]["region_xywh_px"], [100, 200, 60, 30])
        self.assertEqual(out["source_ref"]["asset_sha256"], "a" * 64)
        self.assertEqual(out["source_ref"]["source_label"], "needs_human_verification")


class PreviewAndDiagnosticSeparation(unittest.TestCase):
    def test_previews_and_diagnostics_never_satisfy_a_release_gate(self):
        base = {"entry_id": "RS-HERO-FULL", "lane": "offline_real_science", "tested_commit": "c" * 40,
                "status": "passed", "attempt_id": "att_x", "reason": None, "worktree_dirty": False}
        for change in ({"evidence_class": "preview"}, {"evidence_class": "diagnostic"},
                       {"evidence_class": "executed_acceptance", "app_under_test": {"commit": "d" * 40, "dirty": False}},
                       {"evidence_class": "executed_acceptance", "app_under_test": {"commit": "c" * 40, "dirty": True}}):
            gate = gates._entry_gate("real_science_http", {"RS-HERO-FULL": {**base, **change}}, ("RS-HERO-FULL",), "")
            self.assertEqual(gate["status"], "blocked", change)
        own = {**base, "evidence_class": "executed_acceptance", "app_under_test": {"commit": "c" * 40, "dirty": False}}
        self.assertEqual(gates._entry_gate("g", {"RS-HERO-FULL": own}, ("RS-HERO-FULL",), "")["status"], "passed")

    def test_cli_refuses_previews_or_diagnostics_in_the_acceptance_results(self):
        self.assertEqual(cli.main(["run", "--lane", "offline_real_science", "--subject", "http-launch",
                                   "--diagnostic", "relax_nproc"]), 1)
        self.assertEqual(cli.main(["run", "--lane", "offline_real_science", "--subject", "http-launch",
                                   "--app-repo", REPO]), 1)

    def test_unknown_diagnostic_override_is_refused(self):
        with self.assertRaises(launcher.StackError):
            launcher.LocalStack(REPO, diagnostic_overrides=("disable_all_guards",))


class LedgerAndHistoryIntegrity(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "b.jsonl")
        self.ledger = BudgetLedger(self.path)
        self.ledger.open_cohort("t", "A. Human", "synthetic test allowance")

    def tearDown(self):
        shutil.rmtree(self.dir)

    def test_corrupt_ledger_fails_closed_and_is_preserved(self):
        self.ledger.reserve("t", "p", "C01", 100, 10, "unit")
        with open(self.path, "a", encoding="utf-8") as handle:
            handle.write("{not json\n")
        with open(self.path, encoding="utf-8") as handle:
            before = handle.read()
        from drbean_eval.budget import BudgetStop
        with self.assertRaises(BudgetStop):
            self.ledger.reserve("t", "p", "C01", 100, 10, "unit")
        with self.assertRaises(BudgetStop):
            self.ledger.state()
        with open(self.path, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), before)

    def test_crash_after_reservation_keeps_the_maximum_committed(self):
        self.ledger.reserve("t", "p", "C01", 3000, 700, "unit")  # process dies here: never reconciled
        state = BudgetLedger(self.path).state()
        self.assertEqual(state["committed"], {"provider_requests": 1, "input_tokens": 3000, "output_tokens": 700})
        self.assertEqual(len(state["unreconciled"]), 1)

    def test_concurrent_reservations_never_exceed_caps(self):
        import threading
        ledger = BudgetLedger(os.path.join(self.dir, "c.jsonl"))
        ledger.open_cohort("t", "A. Human", "synthetic", {"provider_requests": 5})
        results = []

        def reserve():
            try:
                results.append(ledger.reserve("t", "p", "C01", 10, 1, "unit"))
            except Exception as error:  # BudgetStop for the ones that do not fit
                results.append(type(error).__name__)

        threads = [threading.Thread(target=reserve) for _ in range(20)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sum(1 for r in results if str(r).startswith("rsv_")), 5)
        self.assertEqual(ledger.state()["committed"]["provider_requests"], 5)

    def test_conflicting_provider_request_ids_are_flagged(self):
        a = self.ledger.reserve("t", "p", "C01", 100, 10, "unit")
        b = self.ledger.reserve("t", "p", "C01", 100, 10, "unit")
        self.ledger.reconcile(a, 10, 1, "completed", "req-same")
        self.ledger.reconcile(b, 10, 1, "completed", "req-same")
        self.assertEqual(self.ledger.state()["conflicting_request_ids"], ["req-same"])

    def test_malformed_history_line_is_surfaced_not_dropped(self):
        results = os.path.join(self.dir, "results")
        os.makedirs(results)
        with open(os.path.join(results, "attempts.jsonl"), "w", encoding="utf-8") as handle:
            handle.write(json.dumps({"attempt_id": "a1", "entry_id": "X", "lane": "l", "status": "passed"}) + "\n")
            handle.write("{broken\n")
            handle.write(json.dumps({"attempt_id": "a1", "entry_id": "X", "lane": "l", "status": "failed"}) + "\n")
        records = runner.read_attempts(results)
        self.assertEqual([r["status"] for r in records], ["passed", "error", "failed"])
        problems = " ".join(history.verify(results))
        self.assertIn("not valid JSON", problems)
        self.assertIn("duplicate attempt_id a1", problems)
