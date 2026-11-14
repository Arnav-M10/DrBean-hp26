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
    def test_controlled_examples_require_explicit_start_option(self):
        with mock.patch.dict(os.environ, {}, clear=True), mock.patch.object(launcher, "cmd_start", return_value=0):
            self.assertEqual(launcher.main(["start", "--controlled-source-examples"]), 0)
            env = launcher.child_env()
        self.assertEqual(env["BEAN_SOURCE_INTAKE_MODE"], "controlled")
        self.assertEqual(env["BEAN_CONTROLLED_SOURCE_MANIFEST"],
                         os.path.join(launcher.REPO, "scripts", "ai", "fixtures", "source-previews.v1.json"))
        self.assertEqual(env["BEAN_AI_MODE"], "placeholder")

    def test_provider_values_are_never_read_while_filtering_or_probing(self):
        class NamesOnlySecrets(dict):
            def __getitem__(self, name):
                if name in {"GEMINI_API_KEY", "LANGSMITH_API_KEY", "OPENAI_API_KEY"}:
                    raise AssertionError("A discarded provider value was read")
                return super().__getitem__(name)

        planted = NamesOnlySecrets(GEMINI_API_KEY="dummy", LANGSMITH_API_KEY="dummy", OPENAI_API_KEY="dummy",
                                   PATH=os.defpath, PYTHONPATH="/operator/guard")
        completed = subprocess.CompletedProcess([], 0, stdout="probe ok", stderr="")
        with mock.patch.object(launcher.os, "environ", planted), \
                mock.patch.object(launcher.subprocess, "run", return_value=completed) as run:
            env = launcher.child_env()
            self.assertEqual(launcher.out(["probe"]), (0, "probe ok"))
        self.assertFalse(set(planted) & {"GEMINI_API_KEY", "LANGSMITH_API_KEY", "OPENAI_API_KEY"} & set(env))
        self.assertEqual(run.call_args.kwargs["env"], env)
        self.assertEqual(env["PYTHONPATH"].split(os.pathsep), [os.path.join(launcher.REPO, "apps", "api"), "/operator/guard"])

    def test_application_import_does_not_depend_on_editable_pth_processing(self):
        with tempfile.TemporaryDirectory() as directory:
            foreign = os.path.join(directory, "bean_api")
            os.mkdir(foreign)
            working = os.path.join(directory, "caller")
            os.mkdir(working)
            with open(os.path.join(foreign, "__init__.py"), "w", encoding="utf-8") as handle:
                handle.write("raise AssertionError('An unrelated checkout shadowed the application')\n")
            with mock.patch.dict(os.environ, {"PYTHONPATH": directory}):
                env = launcher.child_env()
            process = subprocess.run([sys.executable, "-S", "-c", "import bean_api; print(bean_api.__file__)"],
                                     cwd=working, env=env, capture_output=True, text=True, timeout=10)
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(os.path.realpath(process.stdout.strip()),
                         os.path.join(launcher.REPO, "apps", "api", "bean_api", "__init__.py"))

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
        # Both cmd_start and the survival assertion connect without an accept
        # loop; leave room for both probes on Darwin's small listen backlog.
        listener.listen(4)
        port = listener.getsockname()[1]
        ready = {"uv": "uv", "node": "v22.0.0", "backend": {"python": "3.13.0", "application_importable": True,
                                                                  "packages": {"dr-bean-backend": "0"}},
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
        static = {"uv": "uv", "node": "v22.0.0", "backend": {"python": "3.13.0", "application_importable": True,
                                                                   "packages": {"dr-bean-backend": "0"}},
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

    def test_package_metadata_without_application_import_does_not_qualify_backend(self):
        static = {"uv": "uv", "node": "v22.0.0", "backend": {"python": "3.13.0", "application_importable": False,
            "packages": {"dr-bean-backend": "0"}}, "engine": {"python": "3.11.0", "runtime_qualified": True,
            "counterdex": "0", "native_replay_supported": True}, "auth_file_present": True,
            "os": "x", "os_release": "x", "arch": "x"}
        rows, ok = launcher.summarize(static, None)
        self.assertFalse(ok)
        self.assertTrue(any(state == "MISSING" and fact == "backend runtime (.venv)" for state, fact, _ in rows))


if __name__ == "__main__":
    unittest.main()


class LiveOptIn(unittest.TestCase):
    """The opt-in file is data, its key reaches only the API and worker, and a key alone enables nothing."""
    CANARY = "CANARY-gemini-key-not-real-0001"

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.patches = [mock.patch.object(launcher, "LIVE_CONFIG", os.path.join(self.dir.name, "gemini.local.json")),
                        mock.patch.object(launcher, "LIVE_CHECK", os.path.join(self.dir.name, "check.json"))]
        for patch in self.patches:
            patch.start()

    def tearDown(self):
        for patch in self.patches:
            patch.stop()
        self.dir.cleanup()

    def write(self, data, raw=None):
        with open(launcher.LIVE_CONFIG, "w", encoding="utf-8") as handle:
            handle.write(raw if raw is not None else json.dumps(data))
        os.chmod(launcher.LIVE_CONFIG, 0o600)

    def test_states_are_distinct_and_never_print_the_key(self):
        self.assertEqual(launcher.live_config()["state"], "absent")
        self.write({"GEMINI_API_KEY": self.CANARY})
        disabled = launcher.live_config()
        self.assertEqual((disabled["state"], disabled["env"]), ("disabled", {}))  # a saved key alone is not opt-in
        self.write({"mode": "live"})
        self.assertEqual(launcher.live_config()["state"], "missing_key")
        self.write({"mode": "live", "GEMINI_API_KEY": self.CANARY, "GEMINI_MODEL": "model-x"})
        live = launcher.live_config()
        self.assertEqual(live["state"], "configured")
        self.assertEqual(live["env"]["GEMINI_API_KEY"], self.CANARY)
        for state in (disabled, live):
            self.assertNotIn(self.CANARY, state["detail"])
        self.assertEqual(launcher.live_check_record(), "not run")

    def test_file_is_data_not_shell(self):
        self.write(None, raw="export GEMINI_API_KEY=$(touch /tmp/drbean-should-not-exist)\n")
        self.assertEqual(launcher.live_config()["state"], "invalid")
        self.assertFalse(os.path.exists("/tmp/drbean-should-not-exist"))
        self.write({"mode": "live", "GEMINI_API_KEY": "k", "LD_PRELOAD": "/evil.so"})
        invalid = launcher.live_config()
        self.assertEqual((invalid["state"], invalid["env"]), ("invalid", {}))
        self.assertIn("LD_PRELOAD", invalid["detail"])

    def test_key_reaches_api_and_worker_only(self):
        self.write({"mode": "live", "GEMINI_API_KEY": self.CANARY})
        spawned = {}
        ready = {"uv": "uv", "node": "v22.0.0", "backend": {"python": "3.13.0", "application_importable": True,
                 "packages": {"dr-bean-backend": "0"}}, "engine": {"python": "3.11.0", "runtime_qualified": True,
                 "counterdex": "0", "native_replay_supported": True}, "auth_file_present": True,
                 "os": "x", "os_release": "x", "arch": "x"}
        with mock.patch.object(launcher, "static_facts", return_value=ready), \
                mock.patch.object(launcher, "port_in_use", return_value=False), \
                mock.patch.object(launcher, "owned", return_value=None), \
                mock.patch.object(launcher, "spawn", side_effect=lambda name, cmd, env: spawned.__setitem__(name, env)), \
                mock.patch.object(launcher, "service_facts", side_effect=RuntimeError("stop after spawning")):
            with self.assertRaises(RuntimeError):
                launcher.cmd_start(None)
        self.assertEqual(spawned["api"]["GEMINI_API_KEY"], self.CANARY)
        self.assertEqual(spawned["worker"]["GEMINI_API_KEY"], self.CANARY)
        self.assertNotIn(self.CANARY, json.dumps(spawned["web"]))
        self.assertEqual(spawned["api"]["BEAN_AI_MODE"], "live_opt_in")
