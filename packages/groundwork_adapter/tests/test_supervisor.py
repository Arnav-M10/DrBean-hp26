"""Parent-only process supervision controls, runnable on CPython 3.12/3.13.

Temporary executable scripts stand in for a server-selected interpreter. They
exercise bounded pipes and owned process groups without scientific imports,
providers, inherited credentials or artifact-selected executable paths.
"""
from importlib.util import module_from_spec, spec_from_file_location
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest


SUPERVISOR_PATH = Path(__file__).resolve().parents[1] / "scripts" / "supervise_bridge.py"
SPEC = spec_from_file_location("counterdex_test_supervisor", SUPERVISOR_PATH)
SUPERVISOR = module_from_spec(SPEC)
SPEC.loader.exec_module(SUPERVISOR)
HANDSHAKE = {"protocol": SUPERVISOR.PROTOCOL, "operation": "handshake"}


@unittest.skipUnless(os.name == "posix", "The prepared bridge supervisor is POSIX only")
class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="counterdex-supervisor-")
        self.directory = Path(self.temporary.name)
        self.owned_groups = set()

    def tearDown(self):
        # If an assertion exposes a supervisor regression, clean up only the
        # private groups whose fake executable recorded itself as the leader.
        for group in self.owned_groups:
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                pass
        self.temporary.cleanup()

    def executable(self, body, name="prepared-python"):
        path = self.directory / name
        path.write_text("#!" + sys.executable + "\n" + body, encoding="utf-8")
        path.chmod(0o700)
        return str(path)

    def metadata(self, path):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return None
        if data["parent_group"] == data["parent_pid"]:
            self.owned_groups.add(data["parent_group"])
        return data

    def descendant_executable(self, *, mode):
        metadata = self.directory / (mode + ".json")
        source = (
            "import json, os, pathlib, subprocess, sys, time\n"
            "sys.stdin.buffer.read()\n"
            "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'], "
            "stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
            "data = {'parent_pid': os.getpid(), 'parent_group': os.getpgrp(), "
            "'parent_session': os.getsid(0), 'child_pid': child.pid, 'child_group': os.getpgid(child.pid)}\n"
            f"pathlib.Path({str(metadata)!r}).write_text(json.dumps(data))\n"
        )
        if mode == "leader_exits":
            response = json.dumps({"protocol": SUPERVISOR.PROTOCOL, "ok": True})
            source += f"print({response!r}, flush=True)\nos._exit(0)\n"
        elif mode == "closed_outputs":
            source += "os.close(1)\nos.close(2)\ntime.sleep(120)\n"
        else:
            source += "time.sleep(120)\n"
        return self.executable(source, mode), metadata

    def assert_process_gone(self, pid):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.02)
        status = subprocess.run(["/bin/ps", "-o", "stat=", "-p", str(pid)],
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False).stdout.decode().strip()
        # A killed orphan may briefly await the platform's init reaper; it
        # cannot run any scientific work and is not a surviving process.
        self.assertTrue(not status or status.startswith("Z"), f"Owned process {pid} still running with state {status}")

    def assert_private_group_gone(self, metadata):
        self.assertIsNotNone(metadata)
        self.assertEqual(metadata["parent_group"], metadata["parent_pid"])
        self.assertEqual(metadata["parent_session"], metadata["parent_pid"])
        self.assertEqual(metadata["child_group"], metadata["parent_group"])
        self.assertNotEqual(metadata["parent_group"], os.getpgrp())
        self.assert_process_gone(metadata["parent_pid"])
        self.assert_process_gone(metadata["child_pid"])

    def test_child_receives_clean_environment_and_fixed_module_argv(self):
        executable = self.executable(
            "import json, os, sys\n"
            "request = json.loads(sys.stdin.buffer.read())\n"
            f"print(json.dumps({{'protocol': {SUPERVISOR.PROTOCOL!r}, 'ok': True, "
            "'environment': dict(os.environ), 'arguments': sys.argv[1:]}))\n")
        marker = "COUNTERDEX_TEST_HARMLESS_MARKER"
        previous = os.environ.get(marker)
        os.environ[marker] = "public-test-marker-not-a-credential"
        try:
            response = SUPERVISOR.PreparedBridge(executable).call(HANDSHAKE)
        finally:
            if previous is None:
                os.environ.pop(marker, None)
            else:
                os.environ[marker] = previous
        self.assertTrue(response["ok"], response)
        self.assertNotIn(marker, response["environment"])
        # macOS/Python may inject their own locale metadata after exec.
        self.assertLessEqual(set(response["environment"]), {"LANG", "LC_ALL", "LC_CTYPE", "__CF_USER_TEXT_ENCODING"})
        self.assertEqual(response["arguments"], ["-I", "-m", "counterdex.bridge"])

    def test_cancellation_kills_leader_and_descendant_even_after_outputs_close(self):
        for mode in ("open_outputs", "closed_outputs"):
            executable, record = self.descendant_executable(mode=mode)
            with self.subTest(mode=mode):
                response = SUPERVISOR.PreparedBridge(executable).call(
                    HANDSHAKE, wall_seconds=10, cancelled=lambda: self.metadata(record) is not None)
                self.assertEqual(response["error"]["code"], "cancelled")
                self.assert_private_group_gone(self.metadata(record))

    def test_deadline_kills_leader_and_descendant_even_after_outputs_close(self):
        for mode in ("open_outputs", "closed_outputs"):
            executable, record = self.descendant_executable(mode=mode)
            with self.subTest(mode=mode):
                started = time.monotonic()
                response = SUPERVISOR.PreparedBridge(executable).call(HANDSHAKE, wall_seconds=1)
                elapsed = time.monotonic() - started
                self.assertEqual(response["error"]["code"], "scientific_wall_limit")
                self.assertLess(elapsed, 3)
                self.assert_private_group_gone(self.metadata(record))

    def test_successful_exited_leader_does_not_leave_descendant_running(self):
        executable, record = self.descendant_executable(mode="leader_exits")
        response = SUPERVISOR.PreparedBridge(executable).call(HANDSHAKE, wall_seconds=5)
        self.assertTrue(response["ok"], response)
        self.assert_private_group_gone(self.metadata(record))

    def test_pre_cancelled_request_never_starts_executable(self):
        record = self.directory / "must-not-exist"
        executable = self.executable(f"from pathlib import Path\nPath({str(record)!r}).touch()\n")
        response = SUPERVISOR.PreparedBridge(executable).call(HANDSHAKE, cancelled=lambda: True)
        self.assertEqual(response["error"]["code"], "cancelled")
        self.assertFalse(record.exists())

    def test_stdout_and_stderr_caps_stop_the_child(self):
        for stream, size in ((1, SUPERVISOR.TRANSPORT_CAP + 1), (2, 65537)):
            executable = self.executable(
                "import os, sys, time\nsys.stdin.buffer.read()\n"
                f"remaining = {size}\n"
                "while remaining:\n"
                f"    written = os.write({stream}, b'x' * min(remaining, 65536))\n"
                "    remaining -= written\n"
                "time.sleep(120)\n", name=f"pipe-{stream}")
            with self.subTest(stream=stream):
                started = time.monotonic()
                response = SUPERVISOR.PreparedBridge(executable).call(HANDSHAKE, wall_seconds=5)
                self.assertEqual(response["error"]["code"], "transport_byte_limit")
                self.assertLess(time.monotonic() - started, 3)
                self.assertNotIn("x" * 20, json.dumps(response))

    def test_missing_relative_nonexecutable_and_nonexistent_runtime(self):
        absent = SUPERVISOR.PreparedBridge("python3.11").capabilities()
        self.assertFalse(absent["configured"])
        self.assertFalse(absent["available"])
        self.assertFalse(absent["qualified"])
        for path in (self.directory / "missing", self.directory / "not-executable"):
            if path.name == "not-executable":
                path.write_text("not executable")
            with self.subTest(path=path):
                status = SUPERVISOR.PreparedBridge(str(path)).capabilities()
                self.assertTrue(status["configured"])
                self.assertFalse(status["available"])
                self.assertFalse(status["qualified"])
                self.assertEqual(status["reason_code"], "runtime_unavailable")

    def test_invalid_wall_request_and_input_size_fail_before_launch(self):
        executable = self.executable("raise AssertionError('must not launch')\n")
        bridge = SUPERVISOR.PreparedBridge(executable)
        for seconds in (0, 121, True, 1.5):
            with self.subTest(seconds=seconds):
                self.assertEqual(bridge.call(HANDSHAKE, wall_seconds=seconds)["error"]["code"], "invalid_wall_limit")
        self.assertEqual(bridge.call({"value": float("nan")})["error"]["code"], "invalid_bridge_request")
        self.assertEqual(bridge.call({"large": "x" * SUPERVISOR.TRANSPORT_CAP})["error"]["code"], "transport_byte_limit")

    def test_malformed_response_and_failure_exit_cannot_be_success(self):
        bodies = ["print('not JSON')\n", "print('[]')\n",
                  f"print({json.dumps({'protocol': SUPERVISOR.PROTOCOL, 'ok': True})!r})\nraise SystemExit(3)\n"]
        for index, body in enumerate(bodies):
            executable = self.executable(body, name=f"invalid-{index}")
            with self.subTest(index=index):
                response = SUPERVISOR.PreparedBridge(executable).call(HANDSHAKE)
                self.assertFalse(response["ok"])
                self.assertEqual(response["error"]["code"], "invalid_bridge_response")

    def test_valid_child_failure_is_preserved(self):
        child_failure = SUPERVISOR.failure("unsupported_runtime")
        executable = self.executable(f"print({json.dumps(child_failure)!r})\nraise SystemExit(2)\n")
        self.assertEqual(SUPERVISOR.PreparedBridge(executable).call(HANDSHAKE), child_failure)

    def test_available_unqualified_handshake_stays_unqualified(self):
        response = {"protocol": SUPERVISOR.PROTOCOL, "ok": True, "configured": None,
                    "available": True, "qualified": False, "implementation": None}
        executable = self.executable(f"print({json.dumps(response)!r})\n")
        status = SUPERVISOR.PreparedBridge(executable).capabilities()
        self.assertTrue(status["configured"])
        self.assertTrue(status["available"])
        self.assertFalse(status["qualified"])

    def test_malformed_successful_handshake_cannot_omit_or_invent_runtime_status(self):
        base = {"protocol": SUPERVISOR.PROTOCOL, "ok": True}
        for index, response in enumerate((base, dict(base, available=True, qualified="yes"),
                                           dict(base, available=False, qualified=True))):
            executable = self.executable(f"print({json.dumps(response)!r})\n", name=f"handshake-{index}")
            with self.subTest(response=response):
                status = SUPERVISOR.PreparedBridge(executable).capabilities()
                self.assertTrue(status["configured"])
                self.assertFalse(status["available"])
                self.assertFalse(status["qualified"])
                self.assertEqual(status["reason_code"], "invalid_bridge_response")

    @unittest.skipUnless(os.environ.get("COUNTERDEX_TEST_PYTHON"), "Set COUNTERDEX_TEST_PYTHON to an installed prepared CPython 3.11")
    def test_prepared_installed_real_bridge(self):
        bridge = SUPERVISOR.PreparedBridge(os.environ["COUNTERDEX_TEST_PYTHON"])
        status = bridge.capabilities()
        self.assertTrue(status["configured"], status)
        self.assertTrue(status["available"], status)
        self.assertTrue(status["qualified"], status)
        self.assertIsNotNone(status["implementation"])


if __name__ == "__main__":
    unittest.main()
