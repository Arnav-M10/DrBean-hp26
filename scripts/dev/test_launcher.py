"""Tests for the local launcher. Standard library only: python3 -m unittest scripts/dev/test_launcher.py"""
import json
import io
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import launcher  # noqa: E402


class ChildEnvironment(unittest.TestCase):
    def test_isolated_ports_are_explicit_bounded_and_reach_the_web_proxy(self):
        with mock.patch.dict(os.environ, {"BEAN_DEV_API_PORT": "28130"}):
            self.assertEqual(launcher.local_port("BEAN_DEV_API_PORT", 8000), 28130)
        for invalid in ("0", "80", "65536", "28130/secret", " 28130"):
            with self.subTest(value=invalid), mock.patch.dict(os.environ, {"BEAN_DEV_API_PORT": invalid}):
                with self.assertRaises(SystemExit):
                    launcher.local_port("BEAN_DEV_API_PORT", 8000)
        with mock.patch.object(launcher, "API_PORT", 28130):
            self.assertEqual(launcher.child_env()["BEAN_WEB_API_PORT"], "28130")

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
                if name in {"GEMINI_API_KEY", "LANGSMITH_API_KEY", "OPENAI_API_KEY", "BEAN_AUTH_TOKENS_JSON",
                            "BEAN_SHARED_GATEWAY_FILE", "BEAN_SHARE_GATEWAY_FILE"}:
                    raise AssertionError("A discarded provider value was read")
                return super().__getitem__(name)

        planted = NamesOnlySecrets(GEMINI_API_KEY="dummy", LANGSMITH_API_KEY="dummy", OPENAI_API_KEY="dummy",
                                   BEAN_AUTH_TOKENS_JSON="dummy", BEAN_SHARE_GATEWAY_FILE="dummy", BEAN_SHARED_GATEWAY_FILE="dummy",
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
        self.assertNotIn("BEAN_SHARE_GATEWAY_FILE", env)
        self.assertNotIn("BEAN_SHARED_GATEWAY_FILE", env)


class OwnedProcesses(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.patch = mock.patch.object(launcher, "RUN", self.dir.name)
        self.patch.start()
        self.var_patch = mock.patch.object(launcher, "VAR", self.dir.name)
        self.var_patch.start()
        self.config_patch = mock.patch.object(launcher, "LIVE_CONFIG", os.path.join(self.dir.name, "absent.json"))
        self.config_patch.start()

    def tearDown(self):
        self.config_patch.stop()
        self.var_patch.stop()
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

    def test_core_stop_closes_shared_admission_even_when_gateway_ownership_is_unproven(self):
        origin = os.path.join(launcher.VAR, "share-origin.json")
        launcher.private_json(origin, {"origin": "https://controlled.trycloudflare.com"})
        def stop(name):
            self.assertFalse(os.path.exists(origin), "Admission must close before any process is stopped")
            return "ownership unproven (record preserved; process not signaled)" if name == "share-gateway" else "stopped"
        with mock.patch.object(launcher, "stop_one", side_effect=stop) as stopped, \
                mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(launcher.cmd_stop(None), 1)
        self.assertEqual([call.args[0] for call in stopped.call_args_list],
                         [*launcher.SHARING_SERVICES, "web", "worker", "api"])

    def test_core_stop_refuses_to_free_upstreams_if_admission_cannot_be_closed(self):
        with mock.patch.object(launcher.os, "unlink", side_effect=PermissionError), \
                mock.patch.object(launcher, "stop_one") as stopped, \
                mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(launcher.cmd_stop(None), 1)
            stopped.assert_not_called()

    def test_missing_start_time_cannot_establish_ownership(self):
        with open(launcher.pidfile("worker"), "w", encoding="utf-8") as handle:
            json.dump({"pid": os.getpid(), "started_at": None}, handle)
        with mock.patch.object(launcher, "started_at", return_value=None):
            self.assertIsNone(launcher.owned("worker"))

    def test_malformed_records_never_establish_ownership_or_crash(self):
        for data in ([], None, {"name": "worker", "pid": True, "started_at": "value"},
                     {"name": "worker", "pid": "123", "started_at": "value"},
                     {"name": "worker", "pid": 2**200, "started_at": "value"},
                     {"name": "api", "pid": os.getpid(), "started_at": "value"}):
            with self.subTest(data=data):
                launcher.private_json(launcher.pidfile("worker"), data)
                self.assertIsNone(launcher.owned("worker"))
                self.assertTrue(launcher.unproven_process("worker"))

    def test_live_pid_without_owned_process_group_is_not_stoppable(self):
        record = {"name": "worker", "pid": os.getpid(), "started_at": launcher.started_at(os.getpid())}
        launcher.private_json(launcher.pidfile("worker"), record)
        with mock.patch.object(launcher.os, "getpgid", return_value=os.getpid() + 1), \
                mock.patch.object(launcher.os, "killpg") as kill:
            self.assertIsNone(launcher.owned("worker"))
            self.assertTrue(launcher.unproven_process("worker"))
            self.assertIn("ownership unproven", launcher.stop_one("worker"))
            kill.assert_not_called()
            self.assertTrue(os.path.exists(launcher.pidfile("worker")))

    def test_failed_atomic_record_write_reaps_only_the_new_child(self):
        popen = subprocess.Popen
        launched = []
        def capture(*args, **kwargs):
            process = popen(*args, **kwargs)
            if kwargs.get("start_new_session"):
                launched.append(process)
            return process
        bystander = popen([sys.executable, "-c", "import time; time.sleep(60)"])
        try:
            with mock.patch.object(launcher.subprocess, "Popen", side_effect=capture), \
                    mock.patch.object(launcher, "private_json", side_effect=OSError("write failed")):
                with self.assertRaises(OSError):
                    launcher.spawn("api", [sys.executable, "-c", "import time; time.sleep(60)"], dict(os.environ))
            self.assertEqual(len(launched), 1)
            self.assertIsNotNone(launched[0].poll())
            self.assertIsNone(bystander.poll())
            self.assertFalse(os.path.exists(launcher.pidfile("api")))
        finally:
            bystander.kill()
            bystander.wait()

    def test_missing_start_stamp_reaps_new_process_instead_of_recording_unknown_pid(self):
        with mock.patch.object(launcher, "started_at", return_value=None), \
                mock.patch.object(launcher.time, "sleep"):
            with self.assertRaises(launcher.LifecycleError):
                launcher.spawn("worker", [sys.executable, "-c", "import time; time.sleep(60)"], dict(os.environ))
        self.assertFalse(os.path.exists(launcher.pidfile("worker")))

    def test_lock_serializes_threads_and_survives_interrupted_holder(self):
        entered = threading.Event()
        order = []
        def first():
            with launcher.lifecycle_lock():
                order.append("first entered")
                entered.set()
                time.sleep(0.15)
                order.append("first left")
        def second():
            entered.wait(timeout=2)
            with launcher.lifecycle_lock():
                order.append("second entered")
        threads = [threading.Thread(target=first), threading.Thread(target=second)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=3)
            self.assertFalse(thread.is_alive())
        self.assertEqual(order, ["first entered", "first left", "second entered"])
        with self.assertRaisesRegex(RuntimeError, "controlled interruption"):
            with launcher.lifecycle_lock():
                raise RuntimeError("controlled interruption")
        with launcher.lifecycle_lock(timeout=0):
            with self.assertRaises(launcher.LifecycleError):
                with launcher.lifecycle_lock(timeout=0):
                    self.fail("A second lock holder was admitted")
        self.assertEqual(os.stat(os.path.join(launcher.RUN, "lifecycle.lock")).st_mode & 0o777, 0o600)

    def test_lock_refuses_symlinks_without_touching_target(self):
        target = os.path.join(self.dir.name, "target")
        with open(target, "w", encoding="utf-8") as handle:
            handle.write("unchanged")
        os.symlink(target, os.path.join(launcher.RUN, "lifecycle.lock"))
        with self.assertRaises(launcher.LifecycleError):
            with launcher.lifecycle_lock(timeout=0):
                self.fail("A symlink lock was admitted")
        with open(target, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "unchanged")

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
        self.assertIn("ownership unproven", launcher.stop_one("worker"))
        self.assertTrue(os.path.exists(launcher.pidfile("worker")))  # evidence and foreign process survive

    def test_verified_dead_record_is_removed_without_signaling(self):
        launcher.private_json(launcher.pidfile("worker"), {"name": "worker", "pid": 123, "started_at": "old"})
        with mock.patch.object(launcher, "started_at", return_value=None), \
                mock.patch.object(launcher.os, "getpgid", side_effect=ProcessLookupError), \
                mock.patch.object(launcher.os, "killpg") as kill:
            self.assertEqual(launcher.stop_one("worker"), "not running (stale record removed)")
            kill.assert_not_called()
        self.assertFalse(os.path.exists(launcher.pidfile("worker")))

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
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        patch = mock.patch.object(launcher, "LIVE_CONFIG", os.path.join(directory.name, "absent.json"))
        patch.start()
        self.addCleanup(patch.stop)

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


class LiveOptIn(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = os.path.join(self.directory.name, "gemini.local.json")
        patch = mock.patch.object(launcher, "LIVE_CONFIG", self.path)
        patch.start()
        self.addCleanup(patch.stop)
        run_patch = mock.patch.object(launcher, "RUN", os.path.join(self.directory.name, "run"))
        run_patch.start()
        self.addCleanup(run_patch.stop)
        self.config = {
            "mode": "live", "GEMINI_API_KEY": "launcher-test-canary-not-a-real-key",
            "GEMINI_MODEL": "gemini-3.5-flash-lite", "BEAN_GEMINI_FREE_TIER_ONLY": "1",
            "BEAN_GEMINI_ACCOUNT_GATE": "approved", "BEAN_GEMINI_ACCOUNT_DECISION_ID": "local-test-approval",
            "BEAN_GEMINI_IMAGE_TOKEN_BOUND": "8192", "BEAN_GEMINI_MAX_INPUT_TOKENS": "16000",
            "BEAN_GEMINI_MAX_OUTPUT_TOKENS": "2048",
        }
        self.static = {
            "uv": "uv", "node": "v22.0.0", "backend": {"python": "3.13.0", "application_importable": True,
                                                        "packages": {"dr-bean-backend": "0"}},
            "engine": {"python": "3.11.0", "runtime_qualified": True, "counterdex": "0",
                       "native_replay_supported": True}, "auth_file_present": True,
            "os": "x", "os_release": "x", "arch": "x",
        }
        self.service = {"api_ready": True, "web_ready": True, "worker_ready": True,
                        "capabilities": {"science": {}, "gemini": {"dispatch_enabled": True}}}

    def write(self, data=None, mode=0o600):
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(self.config if data is None else data, handle)
        os.chmod(self.path, mode)

    def assert_closed(self, expected="invalid"):
        live = launcher.live_config()
        self.assertEqual(live["state"], expected)
        self.assertEqual(live["env"], {})
        self.assertNotIn(self.config["GEMINI_API_KEY"], json.dumps(live))

    def test_absent_and_disabled_do_not_admit_credentials(self):
        self.assert_closed("absent")
        self.write({**self.config, "mode": "disabled"})
        self.assert_closed("disabled")
        self.write({**self.config, "GEMINI_API_KEY": ""})
        self.assert_closed("missing_key")

    def test_only_explicit_supported_models_and_valid_limits_are_admitted(self):
        for model in ("gemini-3.5-flash-lite", "gemini-2.5-flash-lite"):
            with self.subTest(model=model):
                self.write({**self.config, "GEMINI_MODEL": model})
                live = launcher.live_config()
                self.assertEqual(live["state"], "configured")
                self.assertEqual(live["env"]["GEMINI_MODEL"], model)
                self.assertEqual(live["env"]["BEAN_AI_MODE"], "live_opt_in")
        for key, value in (
            ("GEMINI_MODEL", ""), ("GEMINI_MODEL", "gemini-pro"), ("BEAN_GEMINI_FREE_TIER_ONLY", "0"),
            ("BEAN_GEMINI_ACCOUNT_GATE", "pending"), ("BEAN_GEMINI_ACCOUNT_DECISION_ID", ""),
            ("BEAN_GEMINI_ACCOUNT_DECISION_ID", "cannot contain spaces"),
            ("BEAN_GEMINI_MAX_INPUT_TOKENS", "0"), ("BEAN_GEMINI_MAX_INPUT_TOKENS", "24001"),
            ("BEAN_GEMINI_MAX_OUTPUT_TOKENS", "4097"), ("BEAN_GEMINI_IMAGE_TOKEN_BOUND", "-1"),
            ("BEAN_GEMINI_IMAGE_TOKEN_BOUND", "8191"), ("BEAN_GEMINI_IMAGE_TOKEN_BOUND", "8193"),
            ("BEAN_GEMINI_MAX_INPUT_TOKENS", 16000),
        ):
            with self.subTest(key=key, value=value):
                self.write({**self.config, key: value})
                self.assert_closed()
        for key in launcher.LIVE_KEYS - {"GEMINI_API_KEY"}:
            with self.subTest(missing=key):
                self.write({name: value for name, value in self.config.items() if name != key})
                self.assert_closed()
        self.write({**self.config, "BEAN_GEMINI_MAX_INPUT_TOKENS": "24000",
                    "BEAN_GEMINI_MAX_OUTPUT_TOKENS": "4096"})
        self.assertEqual(launcher.live_config()["state"], "configured")

    def test_permission_and_file_type_failures_never_read_a_key(self):
        self.write(mode=0o644)
        with mock.patch.object(launcher.json, "loads", side_effect=AssertionError("must not read JSON")):
            self.assert_closed()
        os.unlink(self.path)
        target = os.path.join(self.directory.name, "target.json")
        with open(target, "w", encoding="utf-8") as handle:
            json.dump(self.config, handle)
        os.chmod(target, 0o600)
        os.symlink(target, self.path)
        self.assert_closed()
        os.unlink(self.path)
        os.mkdir(self.path)
        self.assert_closed()

    def test_malformed_or_oversized_configuration_never_leaks_values(self):
        for raw in (
            '{"mode":"live","mode":"disabled"}', "[1, 2]", "{not JSON}",
            json.dumps({**self.config, "undocumented": "secret"}),
            json.dumps({**self.config, "GEMINI_API_KEY": "line\nbreak"}),
            " " * 16385,
        ):
            with self.subTest(kind=raw[:20]):
                with open(self.path, "w", encoding="utf-8") as handle:
                    handle.write(raw)
                os.chmod(self.path, 0o600)
                self.assert_closed()

    def test_live_values_go_only_to_server_children(self):
        self.write()
        shell = {"GEMINI_API_KEY": "wrong-shell-key", "GEMINI_MODEL": "wrong-shell-model",
                 "BEAN_AI_MODE": "live_opt_in", "BEAN_GEMINI_MAX_INPUT_TOKENS": "999999",
                 "GOOGLE_GEMINI_BASE_URL": "https://wrong-provider.example", "BEAN_GEMINI_EXTRA": "shell-only"}
        with mock.patch.dict(os.environ, shell, clear=True):
            base = launcher.child_env()
        server = launcher.provider_child_env(base, launcher.live_config())
        self.assertEqual(server["GEMINI_API_KEY"], self.config["GEMINI_API_KEY"])
        self.assertEqual(server["BEAN_GEMINI_MAX_INPUT_TOKENS"], "16000")
        self.assertEqual(server["BEAN_GEMINI_FREE_TIER_ONLY"], "1")
        self.assertNotIn("GOOGLE_GEMINI_BASE_URL", server)
        self.assertNotIn("BEAN_GEMINI_EXTRA", server)
        self.assertNotIn("wrong-shell", json.dumps(server))
        self.assertNotIn("GEMINI_API_KEY", base)
        self.assertEqual(base["BEAN_AI_MODE"], "placeholder")
        self.assertEqual(base["GOOGLE_GEMINI_BASE_URL"], "http://127.0.0.1:9")
        self.assertNotIn(self.config["GEMINI_API_KEY"], json.dumps(base))

    def test_start_routes_the_configuration_to_api_and_worker_only(self):
        self.write()
        with mock.patch.object(launcher, "static_facts", return_value=self.static), \
                mock.patch.object(launcher, "owned", side_effect=[None] * 3 + [{"pid": 1}] * 6), \
                mock.patch.object(launcher, "port_in_use", return_value=False), \
                mock.patch.object(launcher, "service_facts", return_value=self.service), \
                mock.patch.object(launcher, "spawn") as spawn, mock.patch("sys.stdout", new_callable=io.StringIO) as output:
            self.assertEqual(launcher.cmd_start(None), 0)
        environments = {call.args[0]: call.args[2] for call in spawn.call_args_list}
        self.assertEqual(set(environments), {"api", "worker", "web"})
        for name in ("api", "worker"):
            self.assertEqual(environments[name]["GEMINI_API_KEY"], self.config["GEMINI_API_KEY"])
            self.assertNotIn("GOOGLE_GEMINI_BASE_URL", environments[name])
        self.assertNotIn("GEMINI_API_KEY", environments["web"])
        self.assertEqual(environments["web"]["BEAN_AI_MODE"], "placeholder")
        self.assertNotIn(self.config["GEMINI_API_KEY"], output.getvalue())

    def test_invalid_config_blocks_start_without_spawning(self):
        self.write(mode=0o644)
        with mock.patch.object(launcher, "static_facts", return_value=self.static), \
                mock.patch.object(launcher, "spawn") as spawn, mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(launcher.cmd_start(None), 1)
            spawn.assert_not_called()

    def test_doctor_reports_configuration_and_server_state_without_claiming_qualification(self):
        self.write()
        for observed in (True, False):
            self.service["capabilities"]["gemini"]["dispatch_enabled"] = observed
            with self.subTest(observed=observed), \
                    mock.patch.object(launcher, "static_facts", return_value=self.static), \
                    mock.patch.object(launcher, "owned", return_value={"pid": 1}), \
                    mock.patch.object(launcher, "service_facts", return_value=self.service), \
                    mock.patch("sys.stdout", new_callable=io.StringIO) as output:
                self.assertEqual(launcher.cmd_doctor(type("Args", (), {"json": True})()), 0)
                report = json.loads(output.getvalue())
            self.assertEqual(report["ai_mode"], "live_opt_in")
            self.assertEqual(report["gemini_live"]["server_dispatch_enabled"], observed)
            self.assertEqual(report["gemini_live"]["live_qualification"], "not_established_by_launcher")
            self.assertNotIn(self.config["GEMINI_API_KEY"], output.getvalue())
        live = launcher.live_status(launcher.live_config(), None)
        self.assertFalse(live["server_observed"])
        self.assertIsNone(live["server_dispatch_enabled"])


if __name__ == "__main__":
    unittest.main()
