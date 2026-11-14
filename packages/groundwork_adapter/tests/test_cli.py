"""Exercise the native CLI from fresh requests using the active installation.

Subprocesses inherit the caller's import environment. The tests do not inject
a source checkout path, so the same controls can qualify an installed wheel.
"""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from counterdex.__main__ import _write_complete
from counterdex.exact import canonical_bytes, strict_json_loads
from helpers import synthetic_inputs


class CommandLineControls(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="counterdex-cli-test-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.problem, self.design = synthetic_inputs()
        self.request = self.directory / "request.json"
        self.output = self.directory / "suggestion.json"
        self.anchors = self.directory / "anchors.json"
        self.request.write_bytes(canonical_bytes({"problem": self.problem.to_payload(), "design": self.design.to_payload(),
            "workflow": {"plan_id": "fixture-cli-plan", "approval_id": "fixture-cli-approval",
                         "operation_id": "fixture-cli-operation", "execution_id": "fixture-cli-execution"}}))
        self.anchors.write_bytes(canonical_bytes({"problem_digest": self.problem.digest, "design_digest": self.design.digest}))

    def cli(self, *arguments):
        return subprocess.run([sys.executable, "-m", "counterdex", *map(str, arguments)],
                              capture_output=True, timeout=20, check=False)

    def run_request(self, *extra):
        return self.cli("run", self.request, "--anchors", self.anchors, "--output", self.output, *extra)

    def assert_safe_error(self, result, code):
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, b"")
        self.assertLess(len(result.stderr), 1024)
        error = strict_json_loads(result.stderr)["error"]
        self.assertEqual(error["code"], code)
        self.assertNotIn(self.temporary.name.encode(), result.stderr)
        self.assertNotIn(b"Traceback", result.stderr)
        return error

    def test_run_and_fresh_replay_complete(self):
        result = self.run_request()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, b"")
        receipt = strict_json_loads(result.stdout)
        self.assertEqual(receipt["output"], str(self.output))
        packet = self.output.read_bytes()
        bundle = strict_json_loads(packet)
        self.assertEqual(receipt["artifact_bytes"], len(packet))
        self.assertEqual(receipt["suggestion_digest"], bundle["suggestion_digest"])
        self.anchors.write_bytes(canonical_bytes({"problem_digest": self.problem.digest,
                                                 "suggestion_digest": receipt["suggestion_digest"]}))
        replay = self.cli("replay", self.output, "--anchors", self.anchors)
        self.assertEqual(replay.returncode, 0, replay.stderr)
        fresh = strict_json_loads(replay.stdout)
        self.assertEqual(fresh["replay"], "passed")
        self.assertEqual(fresh["scope"], "analytic_fixed_pair")
        self.assertTrue(fresh["recorded_result_matches"])
        self.assertEqual(fresh["fresh_checked"]["selected_time"], "6/1")
        self.assertEqual(self.output.read_bytes(), packet)

    def test_explicit_trust_anchor_flags_work(self):
        result = self.cli("run", self.request, "--output", self.output,
                          "--expected-problem", self.problem.digest, "--expected-design", self.design.digest)
        self.assertEqual(result.returncode, 0, result.stderr)
        digest = strict_json_loads(result.stdout)["suggestion_digest"]
        replay = self.cli("replay", self.output, "--expected-problem", self.problem.digest,
                          "--expected-suggestion", digest)
        self.assertEqual(replay.returncode, 0, replay.stderr)

    def test_existing_destination_is_preserved(self):
        marker = b"existing user content\n"
        self.output.write_bytes(marker)
        self.assert_safe_error(self.run_request(), "local_io_failure")
        self.assertEqual(self.output.read_bytes(), marker)
        self.assertEqual(list(self.directory.glob(".counterdex-*")), [])

    def test_malformed_input_is_bounded_safe_error(self):
        self.request.write_bytes(b'{"private":"sensitive-test-value","problem":')
        result = self.run_request()
        self.assert_safe_error(result, "invalid_input")
        self.assertNotIn(b"sensitive-test-value", result.stderr)
        self.assertFalse(self.output.exists())

    def test_oversized_input_is_rejected_before_parsing(self):
        self.request.write_bytes(b" " * (4 * 1024 * 1024 + 1))
        self.assert_safe_error(self.run_request(), "resource_exhaustion")
        self.assertFalse(self.output.exists())

    def test_invalid_expected_identity_cannot_create_output(self):
        self.anchors.write_bytes(canonical_bytes({"problem_digest": self.problem.digest, "design_digest": "0" * 64}))
        self.assert_safe_error(self.run_request(), "wrong_specification_binding")
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.directory.glob(".counterdex-*")), [])

    def test_wrong_replay_anchor_yields_no_success_output(self):
        created = self.run_request()
        self.assertEqual(created.returncode, 0, created.stderr)
        packet = self.output.read_bytes()
        result = self.cli("replay", self.output, "--expected-problem", self.problem.digest,
                          "--expected-suggestion", "0" * 64)
        self.assert_safe_error(result, "artifact_mismatch")
        self.assertEqual(self.output.read_bytes(), packet)

    def test_unknown_anchor_fields_and_missing_anchor_fail(self):
        self.anchors.write_bytes(canonical_bytes({"problem_digest": self.problem.digest, "approved": True}))
        self.assert_safe_error(self.run_request(), "invalid_input")
        self.assertFalse(self.output.exists())
        result = self.cli("run", self.request, "--output", self.output)
        self.assert_safe_error(result, "invalid_input")
        self.assertFalse(self.output.exists())

    def test_atomic_writer_interrupted_before_link_publishes_nothing(self):
        with patch("counterdex.__main__.os.link", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                _write_complete(str(self.output), b"complete evidence bytes")
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.directory.glob(".counterdex-*")), [])

    def test_atomic_writer_success_is_complete_and_exclusive(self):
        payload = b"new complete artifact\n"
        _write_complete(str(self.output), payload)
        self.assertEqual(self.output.read_bytes(), payload)
        with self.assertRaises(FileExistsError):
            _write_complete(str(self.output), b"replacement")
        self.assertEqual(self.output.read_bytes(), payload)
        self.assertEqual(list(self.directory.glob(".counterdex-*")), [])


if __name__ == "__main__":
    unittest.main()
