"""Tests for the local launcher. Standard library only: python3 -m unittest scripts/dev/test_launcher.py"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import launcher  # noqa: E402


class ChildEnvironment(unittest.TestCase):
    def test_provider_credentials_never_reach_a_child(self):
        planted = {"GEMINI_API_KEY": "decoy", "GEMINI_MODEL": "decoy", "GOOGLE_API_KEY": "decoy",
                   "GOOGLE_GENAI_USE_VERTEXAI": "1", "BEAN_GEMINI_ACCOUNT_GATE": "approved",
                   "BEAN_GEMINI_ACCOUNT_DECISION_ID": "decoy", "LANGSMITH_API_KEY": "decoy",
                   "LANGCHAIN_TRACING_V2": "true", "ANTHROPIC_API_KEY": "decoy", "OPENAI_API_KEY": "decoy",
                   "DATABASE_URL": "postgres://decoy", "HOME": "/keep"}
        with mock.patch.dict(os.environ, planted, clear=True):
            env = launcher.child_env()
        self.assertEqual(env["HOME"], "/keep")
        self.assertEqual(env["BEAN_AI_MODE"], "placeholder")
        self.assertEqual([k for k in planted if k in env and k != "HOME"], [])
        self.assertEqual(env["GOOGLE_GEMINI_BASE_URL"], "http://127.0.0.1:9")  # closed loopback port
        self.assertNotIn("decoy", json.dumps(env))

    def test_one_store_with_absolute_paths(self):
        env = launcher.child_env()
        for name in ("BEAN_DATABASE_PATH", "BEAN_BLOB_DIR", "BEAN_AUTH_FILE", "BEAN_ARTIFACT_DIR"):
            self.assertTrue(os.path.isabs(env[name]) and env[name].startswith(launcher.VAR), name)
        self.assertEqual(env["BEAN_COUNTERDEX_PYTHON"], launcher.ENGINE_PY)  # not a python3.11 from PATH


class OwnedProcesses(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(launcher, "RUN", self.dir.name)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.dir.cleanup()

    def test_stop_ends_only_the_recorded_process_and_its_group(self):
        record = launcher.spawn("api", [sys.executable, "-c", "import time; time.sleep(60)"], dict(os.environ))
        bystander = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        try:
            self.assertEqual(launcher.owned("api")["pid"], record["pid"])
            self.assertEqual(launcher.stop_one("api", grace=5), "stopped")
            self.assertIsNone(launcher.owned("api"))
            self.assertIsNone(launcher.started_at(record["pid"]))
            self.assertIsNone(bystander.poll())  # an unrelated process is untouched
        finally:
            bystander.kill()
            bystander.wait()

    def test_missing_start_time_cannot_establish_ownership(self):
        with open(launcher.pidfile("worker"), "w", encoding="utf-8") as handle:
            json.dump({"pid": os.getpid(), "started_at": None}, handle)
        with mock.patch.object(launcher, "started_at", return_value=None):
            self.assertIsNone(launcher.owned("worker"))

    def test_partial_spawn_failure_stops_services(self):
        with mock.patch.object(launcher, "static_facts", return_value={}), \
                mock.patch.object(launcher, "summarize", return_value=([], True)), \
                mock.patch.object(launcher, "owned", return_value=None), \
                mock.patch.object(launcher, "port_in_use", return_value=False), \
                mock.patch.object(launcher, "spawn", side_effect=[{}, OSError("launch failed")]), \
                mock.patch.object(launcher, "stop_one") as stop:
            self.assertEqual(launcher.cmd_start(None), 1)
        self.assertEqual(stop.call_args_list, [mock.call(name) for name in reversed(launcher.SERVICES)])

    def test_a_reused_or_foreign_pid_is_never_treated_as_ours(self):
        with open(launcher.pidfile("worker"), "w", encoding="utf-8") as handle:
            json.dump({"name": "worker", "pid": os.getpid(), "started_at": "Thu Jan  1 00:00:00 1970"}, handle)  # this test's own pid, wrong start time
        self.assertIsNone(launcher.owned("worker"))
        self.assertEqual(launcher.stop_one("worker"), "not running (stale record removed)")
        self.assertFalse(os.path.exists(launcher.pidfile("worker")))  # and this test process is still alive

    def test_start_refuses_a_port_held_by_someone_else_and_kills_nothing(self):
        listener = socket.socket()
        listener.bind((launcher.HOST, 0))
        listener.listen(1)
        port = listener.getsockname()[1]
        ready = {"uv": "uv", "node": "v22.0.0", "backend": {"python": "3.13.0", "packages": {"dr-bean-backend": "0"}},
                 "engine": {"python": "3.11.0", "runtime_qualified": True, "counterdex": "0",
                            "native_replay_supported": True}, "auth_file_present": True,
                 "os": "x", "os_release": "x", "arch": "x"}
        try:
            with mock.patch.object(launcher, "API_PORT", port), mock.patch.object(launcher, "static_facts",
                                                                                 return_value=ready), \
                    mock.patch.object(launcher, "spawn") as spawn:
                self.assertEqual(launcher.cmd_start(None), 1)
                spawn.assert_not_called()
            self.assertTrue(launcher.port_in_use(port))  # the foreign listener survives
        finally:
            listener.close()


class Doctor(unittest.TestCase):
    def test_live_gemini_configuration_is_an_alert_not_a_pass(self):
        static = {"uv": "uv", "node": "v22.0.0", "backend": {"python": "3.13.0", "packages": {"dr-bean-backend": "0"}},
                  "engine": {"python": "3.11.0", "runtime_qualified": True, "counterdex": "0",
                             "native_replay_supported": True}, "auth_file_present": True,
                  "os": "x", "os_release": "x", "arch": "x"}
        service = {"api_ready": True, "web_ready": True, "worker_ready": True,
                   "capabilities": {"science": {}, "gemini": {"configured": True}}}
        rows, ok = launcher.summarize(static, service)
        self.assertFalse(ok)
        self.assertIn("ALERT", [state for state, fact, _ in rows if fact == "Gemini live"])
        service["capabilities"]["gemini"] = {"configured": False, "account_gate_passed": False}
        rows, ok = launcher.summarize(static, service)
        self.assertTrue(ok)
        self.assertIn(("ok", "Gemini live", "disabled, not tested"), rows)
        service["capabilities"]["gemini"]["dispatch_enabled"] = True
        self.assertFalse(launcher.summarize(static, service)[1])

    def test_missing_runtimes_block_start_with_an_explanation(self):
        rows, ok = launcher.summarize({"uv": None, "node": None, "backend": None, "engine": None,
                                       "auth_file_present": False, "os": "x", "os_release": "x", "arch": "x"}, None)
        self.assertFalse(ok)
        self.assertTrue(all("setup" in detail or "Install" in detail
                            for state, _, detail in rows if state == "MISSING" and "replay" not in _))


if __name__ == "__main__":
    unittest.main()
