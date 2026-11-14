"""Admission of native engine-control evidence (finding H-GATE-CONTROLS-DIRTY).

Audit reproduction: a control record named the tested commit, recorded worktree_dirty: true and listed
every required control as passed, yet the native_engine_controls gate reported passed because it copied
the dirty flag without enforcing it. Each control is now decided by its newest relevant run, which must be
clean, executed acceptance of this checkout, on CPython 3.11, against the tested engine source.
Synthetic records only; nothing is launched.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(ROOT)
sys.path.insert(0, ROOT)

from drbean_eval import engine_controls, gates  # noqa: E402

EXPECTED = engine_controls.engine_source_identity(os.path.join(REPO, "packages", "groundwork_adapter"))["source_sha256"]
COMMIT = "0" * 40


def record(passed=True, at="2026-11-14T06:00:00+00:00", **overrides):
    """A fully qualified control run unless overridden."""
    run = {"schema": "drbean-engine-controls/v1", "tested_commit": COMMIT, "worktree_dirty": False, "at": at,
           "evidence_class": "executed_acceptance", "app_under_test": None,
           "interpreter": {"implementation": "CPython", "version": "3.11.17"},
           "engine": {"version": "0.3.0", "imported_from": "repository", "source_sha256": EXPECTED, "files": 24},
           "results": [{"id": control, "passed": passed} for control in gates.REQUIRED_CONTROLS]}
    run.update(overrides)
    return run


def status(*runs):
    return gates.native_controls_gate(list(runs), EXPECTED)


class NativeControlsAdmission(unittest.TestCase):
    def test_audit_reproduction_dirty_record_with_every_control_passed_is_not_admitted(self):
        gate = status(record(worktree_dirty=True))
        self.assertEqual(gate["status"], "blocked")
        self.assertEqual(set(gate["unqualified"]), set(gates.REQUIRED_CONTROLS))
        self.assertTrue(all("worktree dirty or not recorded" in p for p in gate["unqualified"].values()))

    def test_an_unrecorded_dirty_flag_is_not_clean(self):
        run = record()
        del run["worktree_dirty"]
        self.assertEqual(status(run)["status"], "blocked")
        self.assertEqual(status(record(worktree_dirty=None))["status"], "blocked")

    def test_previews_and_unclassified_records_are_not_acceptance(self):
        for overrides in ({"evidence_class": "preview"}, {"evidence_class": None},
                          {"app_under_test": {"commit": "f" * 40, "dirty": False}}):
            self.assertEqual(status(record(**overrides))["status"], "blocked", overrides)

    def test_wrong_interpreter_or_engine_is_not_qualified(self):
        cases = {
            "interpreter 3.13": {"interpreter": {"implementation": "CPython", "version": "3.13.18"}},
            "no interpreter": {"interpreter": {}},
            "no engine identity": {"engine": {}},
            "installed copy": {"engine": {"version": "0.3.0", "imported_from": "elsewhere", "source_sha256": EXPECTED}},
            "other source": {"engine": {"version": "0.3.0", "imported_from": "repository", "source_sha256": "e" * 64}},
        }
        for name, overrides in cases.items():
            gate = status(record(**overrides))
            self.assertEqual(gate["status"], "blocked", name)
            self.assertTrue(gate["unqualified"], name)

    def test_a_clean_qualified_record_still_passes(self):
        gate = status(record())
        self.assertEqual(gate["status"], "passed")
        self.assertEqual((gate["missing"], gate["failed"], gate["unqualified"]), ([], [], {}))

    def test_missing_controls_block_and_failing_controls_fail(self):
        partial = record()
        partial["results"] = partial["results"][1:]
        self.assertEqual(status(partial)["status"], "blocked")
        self.assertEqual(status(partial)["missing"], [gates.REQUIRED_CONTROLS[0]])
        failing = record()
        failing["results"][3]["passed"] = False
        self.assertEqual(status(failing)["status"], "failed")
        truthy = record()
        truthy["results"][0]["passed"] = "true"  # only the boolean True counts as a pass
        self.assertEqual(status(truthy)["status"], "failed")
        self.assertEqual(status()["status"], "blocked")

    def test_older_passes_never_override_newer_invalid_evidence(self):
        clean_pass, later = record(at="2026-11-14T06:00:00+00:00"), "2026-11-14T06:30:00+00:00"
        self.assertEqual(status(clean_pass, record(at=later, worktree_dirty=True))["status"], "blocked")
        self.assertEqual(status(clean_pass, record(at=later, evidence_class="preview"))["status"], "blocked")
        self.assertEqual(status(clean_pass, record(passed=False, at=later))["status"], "failed")
        # A clean retest after a failure is newer valid evidence and does count.
        self.assertEqual(status(record(passed=False), record(at=later))["status"], "passed")
        # A newer partial run decides only the controls it contains.
        newer_partial = record(at=later, worktree_dirty=True)
        newer_partial["results"] = newer_partial["results"][:1]
        gate = status(clean_pass, newer_partial)
        self.assertEqual((gate["status"], list(gate["unqualified"])), ("blocked", [gates.REQUIRED_CONTROLS[0]]))


class ThroughTheReleaseGate(unittest.TestCase):
    def setUp(self):
        self.results = tempfile.mkdtemp(prefix="drbean-gate-controls-")
        self.addCleanup(shutil.rmtree, self.results, ignore_errors=True)

    def write(self, *runs):
        with open(os.path.join(self.results, "controls.jsonl"), "a", encoding="utf-8") as handle:
            for run in runs:
                handle.write(json.dumps(run, sort_keys=True) + "\n")

    def native(self):
        result = gates.compute(ROOT, self.results, COMMIT, False, repo=REPO)
        return next(g for g in result["gates"] if g["gate"] == "native_engine_controls"), result

    def test_the_audited_dirty_record_is_refused_and_a_clean_one_is_admitted_without_releasing(self):
        self.write(record(worktree_dirty=True))
        gate, result = self.native()
        self.assertEqual(gate["status"], "blocked")
        self.assertNotEqual(result["overall"], "passed")
        self.write(record(at="2026-11-14T07:00:00+00:00"))
        gate, result = self.native()
        self.assertEqual(gate["status"], "passed")
        # Qualified controls alone never make the release pass: HTTP science evidence is still absent.
        self.assertEqual(next(g for g in result["gates"] if g["gate"] == "real_science_http")["status"], "blocked")
        self.assertNotEqual(result["overall"], "passed")

    def test_records_at_other_code_are_ignored(self):
        self.write(record(tested_commit="1" * 40))
        self.assertEqual(self.native()[0]["status"], "blocked")


if __name__ == "__main__":
    unittest.main()
