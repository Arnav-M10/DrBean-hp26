"""Tests for the manifest, grader, runner and evidence-lane discipline."""
import copy
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(ROOT)
sys.path.insert(0, ROOT)

import cli  # noqa: E402
from drbean_eval import manifest, report, runner, sanitize  # noqa: E402
from drbean_eval.assertions import grade, resolve  # noqa: E402
from drbean_eval.budget import BudgetLedger  # noqa: E402
from drbean_eval.subject import NoSubject, RecordedSubject, SubjectTimeout  # noqa: E402


def exemplar(entry_id, kind="pass"):
    case_id, letter = entry_id.split("-")[:2]
    with open(os.path.join(ROOT, "selftest", case_id + ".json"), encoding="utf-8") as handle:
        data = json.load(handle)[letter]
    return copy.deepcopy(data["pass"] if kind == "pass" else data["fails"][0]["observation"])


class StubSubject:
    """Test double for the harness itself. Never used to produce product evidence."""
    name = "harness-test-double"

    def __init__(self, change=None, raises=None):
        self.change, self.raises = change, raises
        self.commit = runner.git_state(REPO)["commit"]
        self.manifest = manifest.load(ROOT)

    def describe(self):
        return {"subject": "harness-test-double"}

    def run_entry(self, entry, variant, lane):
        if self.raises:
            raise self.raises
        obs = exemplar(entry["entry_id"])
        live = lane != "fixture_contract"
        obs.update(lane=lane, tested_commit=self.commit, case_sha256=self.manifest["cases"][entry["case_id"]]["sha256"],
                   provider={"transport": "live" if live else "controlled"})
        if live:
            obs["usage"] = {"requests": [{"acceptance": "known", "input_tokens": 900, "output_tokens": 200,
                                          "provider_request_id": "req-test"}]}
        if self.change:
            self.change(obs)
        return obs


class ManifestAndGrader(unittest.TestCase):
    def test_manifest_verifies_and_has_24_scheduled_fixture_entries(self):
        self.assertEqual(manifest.verify(ROOT), [])
        m = manifest.load(ROOT)
        self.assertEqual(len(m["schedule"]["fixture_contract"]), 24)
        self.assertEqual(len({e["entry_id"] for e in m["schedule"]["fixture_contract"]}), 24)

    def test_frozen_cases_match_the_authoring_script(self):
        out = subprocess.run([sys.executable, os.path.join(ROOT, "authoring", "build_cases.py"), "--check"],
                             capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)

    def test_tampering_with_a_frozen_file_is_detected(self):
        temp = tempfile.mkdtemp()
        try:
            for name in ("cases", "sources", "manifest.json"):
                src = os.path.join(ROOT, name)
                (shutil.copytree if os.path.isdir(src) else shutil.copy)(src, os.path.join(temp, name))
            path = os.path.join(temp, "cases", "C02.json")
            path = pathlib.Path(path)
            path.write_text(path.read_text(encoding="utf-8").replace('"value": false', '"value": true', 1),
                            encoding="utf-8")
            self.assertTrue(any("C02" in p for p in manifest.verify(temp)))
            os.remove(os.path.join(temp, "sources", "c04a.png"))
            self.assertTrue(any("c04a" in p for p in manifest.verify(temp)))
        finally:
            shutil.rmtree(temp)

    def test_grader_passes_compliant_and_fails_named_violations(self):
        counts = cli.selftest()
        self.assertEqual(counts["variants"], 24)
        self.assertEqual(counts["passing_exemplars"], 24)
        self.assertGreaterEqual(counts["failing_exemplars"], 48)  # at least two violations per variant

    def test_decision_and_enforcement_are_graded_separately(self):
        case = manifest.load_case(ROOT, "C08")["variants"]["B"]
        with open(os.path.join(ROOT, "selftest", "C08.json"), encoding="utf-8") as handle:
            blocked = json.load(handle)["B"]["fails"][0]["observation"]
        result = grade(case["expected"], blocked)
        self.assertFalse(result["passed"])
        self.assertGreater(result["by_axis"]["decision"]["failed"], 0)
        self.assertEqual(result["by_axis"]["enforcement"]["failed"], 0)

    def test_c08_and_c09_differ_in_tool_behaviour_under_the_same_permissions(self):
        c08, c09 = (manifest.load_case(ROOT, c)["variants"]["A"] for c in ("C08", "C09"))
        self.assertEqual(c08["input"], c09["input"])  # same objective, plan and permitted tools
        self.assertNotEqual(c08["controlled"]["tool_outcomes"]["run_scenario:baseline"],
                            c09["controlled"]["tool_outcomes"]["run_scenario:baseline"])
        self.assertFalse(grade(c09["expected"], exemplar("C08-A"))["passed"])
        self.assertFalse(grade(c08["expected"], exemplar("C09-A"))["passed"])

    def test_path_resolution(self):
        obs = {"a": {"b-c": [{"k": "x", "v": 1}, {"k": "y", "v": 2}]}}
        self.assertEqual(resolve(obs, "a.b-c[k=y].v"), 2)
        self.assertFalse(grade([{"id": "t", "axis": "outcome", "type": "eq", "why": "w", "path": "a.zz", "value": 1}],
                               obs)["passed"])


class Runner(unittest.TestCase):
    def setUp(self):
        self.results = tempfile.mkdtemp()
        self.ledger = os.path.join(self.results, "budget.jsonl")

    def tearDown(self):
        shutil.rmtree(self.results)

    def run_lane(self, lane, subject, only=None, activation=None):
        return runner.run_lane(lane, subject, ROOT, self.results, REPO, only, self.ledger, activation)

    def run_live(self, lane, subject, only=None):
        """Budget-machinery tests only: stub subject, isolated temporary ledger, synthetic activation."""
        return self.run_lane(lane, subject, only, runner.SyntheticActivation())

    def test_without_a_subject_all_24_entries_are_recorded_unrun(self):
        records = self.run_lane("fixture_contract", NoSubject())
        self.assertEqual(len(records), 24)
        self.assertEqual({r["status"] for r in records}, {"unrun"})
        self.assertTrue(all(r["reason"] and r["tested_commit"] and r["started_at"].endswith("Z") for r in records))
        self.assertEqual(len(runner.read_attempts(self.results)), 24)
        # Report v2 columns: lane, lane version, enabled, provider, tools, scheduled, attempts.
        self.assertIn("| fixture_contract | 1 | yes | controlled/none | any | 24 | 24 |", report.render(ROOT, self.results))

    def test_attempts_are_append_only_and_numbered(self):
        self.run_lane("fixture_contract", NoSubject(), ["C01-A"])
        second = self.run_lane("fixture_contract", StubSubject(), ["C01-A"])
        self.assertEqual(second[0]["attempt_number"], 2)
        self.assertEqual(second[0]["status"], "passed")
        self.assertEqual([a["status"] for a in runner.read_attempts(self.results)], ["unrun", "passed"])
        self.assertTrue(os.path.exists(os.path.join(self.results, second[0]["trace"])))

    def test_failed_assertions_are_recorded_as_failed(self):
        record = self.run_lane("fixture_contract",
                               StubSubject(lambda o: o.update(computation_authorized=True)), ["C01-A"])[0]
        self.assertEqual(record["status"], "failed")
        self.assertIn("C01A-L4", record["grade"]["failed_ids"])

    def test_a_result_cannot_be_relabelled_into_another_lane(self):
        relabel = self.run_lane("fixture_contract", StubSubject(lambda o: o.update(lane="actual_full_stack")),
                                ["C01-A"])[0]
        self.assertEqual(relabel["status"], "error")
        stale = self.run_lane("fixture_contract", StubSubject(lambda o: o.update(tested_commit="0" * 40)),
                              ["C01-A"])[0]
        self.assertEqual(stale["status"], "error")
        other = self.run_lane("fixture_contract", StubSubject(lambda o: o.update(case_sha256="0" * 64)),
                              ["C01-A"])[0]
        self.assertEqual(other["status"], "error")

    def test_live_lanes_are_disabled_without_explicit_activation(self):
        BudgetLedger(self.ledger).open_cohort("t", "A. Human", "synthetic test allowance")
        for lane in ("live_intake", "live_agent_controlled_tools", "actual_full_stack"):
            records = self.run_lane(lane, StubSubject())
            self.assertTrue(records)
            self.assertEqual({r["status"] for r in records}, {"unrun"}, lane)
            self.assertTrue(all("NOT_RUN" in r["reason"] for r in records))
        state = BudgetLedger(self.ledger).state()
        self.assertEqual(state["reservations"], {})  # an open cohort alone dispatches and reserves nothing

    def test_live_lane_without_an_authorized_cohort_makes_no_request(self):
        record = self.run_live("live_intake", StubSubject(), ["C01"])[0]
        self.assertEqual(record["status"], "unrun")
        self.assertIn("cohort", record["reason"])
        self.assertFalse(os.path.exists(self.ledger))

    def test_fixture_cannot_be_substituted_into_a_live_lane(self):
        BudgetLedger(self.ledger).open_cohort("t", "A. Human", "synthetic test allowance")
        record = self.run_live("live_intake", StubSubject(lambda o: o.update(provider={"transport": "controlled"})),
                               ["C01-A-live1"])[0]
        self.assertEqual(record["status"], "error")
        self.assertIn("live lane", record["reason"])

    def test_live_usage_is_reserved_then_reconciled(self):
        ledger = BudgetLedger(self.ledger)
        ledger.open_cohort("t", "A. Human", "synthetic test allowance")
        record = self.run_live("live_intake", StubSubject(), ["C01-A-live1"])[0]
        self.assertEqual(record["status"], "passed")
        state = ledger.state()
        self.assertEqual(state["committed"], {"provider_requests": 1, "input_tokens": 900, "output_tokens": 200})
        self.assertEqual(state["unreconciled"], [])

    def test_timeout_keeps_the_maximum_reserved(self):
        ledger = BudgetLedger(self.ledger)
        ledger.open_cohort("t", "A. Human", "synthetic test allowance")
        record = self.run_live("live_intake", StubSubject(raises=SubjectTimeout("60 s wall bound")),
                               ["C01-A-live1"])[0]
        self.assertEqual(record["status"], "timed_out")
        state = ledger.state()
        self.assertEqual(state["committed"], {"provider_requests": 2, "input_tokens": 6000, "output_tokens": 1400})
        self.assertEqual(len(state["unreconciled"]), 2)

    def test_budget_stop_is_a_retained_attempt(self):
        BudgetLedger(self.ledger).open_cohort("t", "A. Human", "synthetic", {"provider_requests": 1})
        record = self.run_live("live_intake", StubSubject(), ["C01-A-live1"])[0]
        self.assertEqual(record["status"], "budget_stopped")
        self.assertEqual(BudgetLedger(self.ledger).state()["committed"]["provider_requests"], 0)

    def test_traces_are_sanitized_and_sentinel_leaks_withhold_the_trace(self):
        key = "AIza" + "C" * 35
        record = self.run_lane("fixture_contract",
                               StubSubject(lambda o: o.update(raw_prompt="private", note=key)), ["C01-A"])[0]
        trace = pathlib.Path(self.results, record["trace"]).read_text(encoding="utf-8")
        self.assertNotIn(key, trace)
        self.assertNotIn("private", trace)
        leaked = self.run_lane("fixture_contract",
                               StubSubject(lambda o: o["disclosed_text"].append(sanitize.SENTINEL_WITHHELD)),
                               ["C01-A"])[0]
        self.assertEqual(leaked["status"], "failed")
        self.assertIsNone(leaked["trace"])

    def test_recorded_subject_relays_an_owner_emitted_observation(self):
        directory = tempfile.mkdtemp()
        try:
            obs = StubSubject().run_entry({"entry_id": "C11-B", "case_id": "C11"}, {}, "fixture_contract")
            with open(os.path.join(directory, "C11-B.observation.json"), "w", encoding="utf-8") as handle:
                json.dump(obs, handle)
            records = self.run_lane("fixture_contract", RecordedSubject(directory), ["C11"])
            self.assertEqual({r["entry_id"]: r["status"] for r in records}, {"C11-A": "unrun", "C11-B": "passed"})
        finally:
            shutil.rmtree(directory)


if __name__ == "__main__":
    unittest.main()
