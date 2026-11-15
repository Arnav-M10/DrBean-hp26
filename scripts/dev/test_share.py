"""Offline sharing controls. Tests never start a tunnel or read provider keys."""
from contextlib import ExitStack
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest import mock

from scripts.dev import share


class Sharing(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name)
        self.origin = self.path / "origin.json"
        self.gateway = self.path / "gateway.json"
        for target, name, value in (
            (share, "ORIGIN_FILE", self.origin), (share, "GATEWAY_FILE", self.gateway),
            (share.launcher, "RUN", str(self.path / "run")), (share.launcher, "VAR", str(self.path)),
        ):
            patch = mock.patch.object(target, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        self.capture = mock.patch("sys.stdout", new_callable=io.StringIO)
        self.output = self.capture.start()
        self.addCleanup(self.capture.stop)
        self.processes = {name: {"pid": 100} for name in ("api", "web")}
        self.spawned = []

    def controlled(self):
        stack = ExitStack()
        stack.enter_context(mock.patch.object(share.launcher, "owned", side_effect=lambda name: self.processes.get(name)))
        stack.enter_context(mock.patch.object(share.launcher, "unproven_process", return_value=False))
        stack.enter_context(mock.patch.object(share.launcher, "port_in_use", side_effect=lambda port: port != share.PORT))
        stack.enter_context(mock.patch.object(share.shutil, "which", side_effect=lambda name: "/test/cloudflared" if name == "cloudflared" else None))
        stack.enter_context(mock.patch.object(share.launcher, "child_env", return_value={"BEAN_AI_MODE": "placeholder"}))
        stack.enter_context(mock.patch.object(share, "session_api_ready", return_value=True))
        stack.enter_context(mock.patch.object(share.launcher, "spawn", side_effect=self.spawn))
        stack.enter_context(mock.patch.object(share.launcher, "stop_one", side_effect=self.stop_one))
        return stack

    def spawn(self, name, command, env):
        self.assertNotIn("GEMINI_API_KEY", env)
        self.assertEqual(env["BEAN_AI_MODE"], "placeholder")
        if name == "share-gateway":
            self.assertEqual(env["BEAN_SHARE_ORIGIN_FILE"], str(self.origin))
            self.assertEqual(env["BEAN_SHARE_GATEWAY_FILE"], str(self.gateway))
        else:
            self.assertFalse(any(key.startswith("BEAN_SHARE_") for key in env))
        self.processes[name] = {"pid": 123, "started_at": "controlled process start", "command": command}
        self.spawned.append(name)
        if name == "share-tunnel":
            with (Path(share.launcher.RUN) / "share-tunnel.log").open("a") as handle:
                handle.write("Shared URL https://bean-study.trycloudflare.com\n")
        return self.processes[name]

    def stop_one(self, name):
        self.assertIn(name, share.NAMES)
        self.assertFalse(self.origin.exists())
        self.processes.pop(name, None)
        return "stopped"

    def test_only_exact_https_quick_tunnel_origin_is_recovered(self):
        for data in ({"origin": "https://bean-study.trycloudflare.com"},
                     {"origin": "http://bean-study.trycloudflare.com"},
                     {"origin": "https://bean-study.trycloudflare.com.evil.test"},
                     {"origin": "https://user:password" + "@bean.trycloudflare.com"}, {}, [], None):
            self.origin.write_text(json.dumps(data))
            expected = data["origin"] if isinstance(data, dict) and data.get("origin") == "https://bean-study.trycloudflare.com" else None
            self.assertEqual(share.recorded_origin(), expected)
        self.origin.write_text("{broken")
        self.assertIsNone(share.recorded_origin())

    def test_stop_closes_origin_before_stopping_only_sharing_and_retains_credential(self):
        share.prepare_gateway()
        credential = self.gateway.read_bytes()
        self.origin.write_text('{"origin":"https://bean.trycloudflare.com"}')
        with mock.patch.object(share.launcher, "stop_one", side_effect=self.stop_one) as stop:
            self.assertEqual(share.stop(), 0)
        self.assertEqual([call.args[0] for call in stop.call_args_list], list(share.NAMES))
        self.assertFalse(self.origin.exists())
        self.assertEqual(self.gateway.read_bytes(), credential)
        self.assertEqual(set(self.processes), {"api", "web"})

    def test_missing_tool_or_unowned_local_app_does_not_spawn(self):
        for binary, managed in ((None, True), ("/test/cloudflared", False)):
            with self.subTest(binary=binary), self.controlled(), \
                    mock.patch.object(share.shutil, "which", return_value=binary), \
                    mock.patch.object(share.launcher, "owned", side_effect=lambda name: {"pid": 1} if managed and name in {"api", "web"} else None), \
                    mock.patch.object(share.launcher, "spawn") as spawn:
                self.assertEqual(share.start(), 1)
                spawn.assert_not_called()
        self.assertFalse(self.origin.exists())
        self.assertFalse(self.gateway.exists())

    def test_foreign_gateway_port_is_left_alone(self):
        with self.controlled(), mock.patch.object(share.launcher, "port_in_use", return_value=True), \
                mock.patch.object(share.launcher, "stop_one") as stop:
            self.assertEqual(share.start(), 1)
            stop.assert_not_called()
        self.assertEqual(self.spawned, [])

    def test_start_is_idempotent_and_only_gateway_gets_credential_path(self):
        with self.controlled():
            self.assertEqual(share.start(), 0)
            credential = self.gateway.read_bytes()
            with mock.patch.object(share, "prepare_gateway", side_effect=AssertionError("Already started")):
                self.assertEqual(share.start(), 0)
        self.assertEqual(share.recorded_origin(), "https://bean-study.trycloudflare.com")
        self.assertEqual(self.origin.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.gateway.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.gateway.read_bytes(), credential)
        self.assertEqual(self.spawned, ["share-gateway", "share-tunnel"])
        command = self.processes["share-tunnel"]["command"]
        self.assertIn("http://127.0.0.1:4174", command)
        self.assertNotIn("--token", command)
        self.assertNotIn(json.loads(credential)["secret"], self.output.getvalue())

    def test_real_launcher_environment_does_not_pass_local_proof_configuration_to_public_children(self):
        # Use the actual launcher environment so additions to it cannot bypass
        # this boundary through the small controlled() fixture above.
        with mock.patch.dict(os.environ, {}, clear=True):
            environment = share.launcher.child_env()
        self.assertEqual(environment["BEAN_LOCAL_GATEWAY_FILE"], str(self.path / "local-gateway.json"))
        self.assertIn("BEAN_LOCAL_BROWSER_ORIGIN", environment)
        captured = {}

        def capture(name, command, env):
            captured[name] = env.copy()
            return self.spawn(name, command, env)

        with self.controlled(), mock.patch.object(share.launcher, "child_env", return_value=environment), \
                mock.patch.object(share.launcher, "spawn", side_effect=capture):
            self.assertEqual(share.start(), 0)
        self.assertEqual(set(captured), {"share-gateway", "share-tunnel"})
        for name, env in captured.items():
            self.assertFalse(any(key.startswith("BEAN_LOCAL_") for key in env), name)
            shared = {key: value for key, value in env.items() if key.startswith("BEAN_SHARE_")}
            self.assertEqual(shared, {"BEAN_SHARE_ORIGIN_FILE": str(self.origin),
                                      "BEAN_SHARE_GATEWAY_FILE": str(self.gateway),
                                      "BEAN_SHARE_WEB_PORT": str(share.launcher.WEB_PORT),
                                      "BEAN_SHARE_API_PORT": str(share.launcher.API_PORT)} if name == "share-gateway" else {})

    def test_selected_app_ports_reach_only_gateway_and_inherited_proof_is_stripped(self):
        captured = {}
        inherited_proof = "/private/owner-only-local-proof.json"
        environment = {"BEAN_AI_MODE": "placeholder",
                       "BEAN_LOCAL_GATEWAY_FILE": inherited_proof,
                       "DRBEAN_PROXY_SECRET": "p" * 43,
                       "BEAN_SHARE_WEB_PORT": "9999", "BEAN_SHARE_API_PORT": "9998"}

        def capture(name, command, env):
            captured[name] = env.copy()
            return self.spawn(name, command, env)

        with self.controlled(), mock.patch.object(share.launcher, "WEB_PORT", 28170), \
                mock.patch.object(share.launcher, "API_PORT", 28171), \
                mock.patch.object(share.launcher, "child_env", return_value=environment), \
                mock.patch.object(share.launcher, "spawn", side_effect=capture):
            self.assertEqual(share.start(), 0)
        self.assertEqual(captured["share-gateway"]["BEAN_SHARE_WEB_PORT"], "28170")
        self.assertEqual(captured["share-gateway"]["BEAN_SHARE_API_PORT"], "28171")
        for name, env in captured.items():
            self.assertNotIn(inherited_proof, env.values(), name)
            self.assertFalse(any(key.startswith("BEAN_LOCAL_") for key in env), name)
            self.assertNotIn("DRBEAN_PROXY_SECRET", env, name)
            self.assertNotIn("p" * 43, env.values(), name)
        self.assertFalse(any(key.startswith("BEAN_SHARE_") for key in captured["share-tunnel"]))
        self.assertNotIn(str(self.gateway), captured["share-tunnel"].values())

    def test_gateway_restart_preserves_tunnel_origin_app_and_credentials(self):
        share.prepare_gateway()
        self.origin.write_text('{"origin":"https://bean-study.trycloudflare.com"}')
        origin_bytes, gateway_bytes = self.origin.read_bytes(), self.gateway.read_bytes()
        self.processes.update({"share-gateway": {"pid": 120, "sharing_mode": share.GATEWAY_MODE},
                               "share-tunnel": {"pid": 121}, "share-awake": {"pid": 122}})
        retained = {name: record.copy() for name, record in self.processes.items() if name != "share-gateway"}

        def stop_gateway(name):
            self.assertEqual(name, "share-gateway")
            self.assertEqual(self.origin.read_bytes(), origin_bytes)
            self.processes.pop(name)
            return "stopped"

        with self.controlled(), mock.patch.object(share.launcher, "stop_one", side_effect=stop_gateway) as stop, \
                mock.patch.object(share.launcher, "port_in_use", side_effect=lambda port: port != share.PORT or "share-gateway" in self.processes), \
                mock.patch.object(share.launcher, "live_config", side_effect=AssertionError("No provider configuration read")):
            self.assertEqual(share.restart_gateway(), 0)
        stop.assert_called_once_with("share-gateway")
        self.assertEqual(self.spawned, ["share-gateway"])
        self.assertEqual({name: self.processes[name] for name in retained}, retained)
        self.assertEqual(self.origin.read_bytes(), origin_bytes)
        self.assertEqual(self.gateway.read_bytes(), gateway_bytes)
        self.assertEqual(self.processes["share-gateway"]["sharing_mode"], share.GATEWAY_MODE)
        self.assertNotIn(json.loads(gateway_bytes)["secret"], self.output.getvalue())

    def test_gateway_restart_refuses_unproven_or_foreign_processes_and_unready_api(self):
        self.origin.write_text('{"origin":"https://bean-study.trycloudflare.com"}')
        self.processes["share-tunnel"] = {"pid": 121}
        before = self.origin.read_bytes()
        for problem in ("unproven", "foreign-port", "unready-api", "legacy-gateway"):
            with self.subTest(problem=problem), self.controlled(), \
                    mock.patch.object(share.launcher, "unproven_process", return_value=problem == "unproven"), \
                    mock.patch.object(share.launcher, "port_in_use", return_value=problem == "foreign-port"), \
                    mock.patch.object(share, "session_api_ready", return_value=problem != "unready-api"), \
                    mock.patch.object(share.launcher, "stop_one") as stop:
                if problem == "legacy-gateway":
                    self.processes["share-gateway"] = {"pid": 120}
                self.assertEqual(share.restart_gateway(), 1)
                stop.assert_not_called()
        self.assertEqual(self.spawned, [])
        self.assertEqual(self.origin.read_bytes(), before)

    def test_failed_gateway_restart_retains_tunnel_and_can_be_retried(self):
        share.prepare_gateway()
        self.origin.write_text('{"origin":"https://bean-study.trycloudflare.com"}')
        before = (self.origin.read_bytes(), self.gateway.read_bytes())
        self.processes["share-tunnel"] = {"pid": 121}
        with self.controlled(), mock.patch.object(share.launcher, "spawn", side_effect=OSError("secret-error-text")), \
                mock.patch.object(share.launcher, "stop_one") as stop:
            self.assertEqual(share.restart_gateway(), 1)
            stop.assert_not_called()
        self.assertEqual((self.origin.read_bytes(), self.gateway.read_bytes()), before)
        self.assertEqual(self.processes["share-tunnel"], {"pid": 121})
        self.assertNotIn("secret-error-text", self.output.getvalue())
        with self.controlled(), mock.patch.object(share.launcher, "port_in_use", side_effect=lambda port: port != share.PORT or "share-gateway" in self.processes):
            self.assertEqual(share.restart_gateway(), 0)
        self.assertEqual(self.spawned, ["share-gateway"])

    def test_partial_failure_recovers_without_api_restart_or_credential_rotation(self):
        def fail_tunnel(name, command, env):
            if name == "share-tunnel":
                raise OSError("sensitive-text-must-not-be-printed")
            return self.spawn(name, command, env)
        with self.controlled(), mock.patch.object(share.launcher, "live_config", side_effect=AssertionError("No provider config read")):
            with mock.patch.object(share.launcher, "spawn", side_effect=fail_tunnel):
                self.assertEqual(share.start(), 1)
            self.assertFalse(self.origin.exists())
            credential = self.gateway.read_bytes()
            self.assertEqual(set(self.processes), {"api", "web"})
            self.assertEqual(share.start(), 0)
        self.assertEqual(self.gateway.read_bytes(), credential)
        self.assertNotIn("sensitive-text", self.output.getvalue())

    def test_incomplete_owned_sharing_is_cleaned_before_restart(self):
        self.processes["share-gateway"] = {"pid": 987}
        self.origin.write_text('{"origin":"https://stale.trycloudflare.com"}')
        with self.controlled():
            self.assertEqual(share.start(), 0)
        self.assertEqual(self.spawned, ["share-gateway", "share-tunnel"])
        self.assertEqual(set(self.processes), {"api", "web", "share-gateway", "share-tunnel"})

    def test_legacy_owned_pair_cannot_claim_private_sessions_and_is_replaced_after_preflight(self):
        self.processes.update({"share-gateway": {"pid": 987}, "share-tunnel": {"pid": 988}})
        self.origin.write_text('{"origin":"https://legacy.trycloudflare.com"}')
        with self.controlled():
            self.assertEqual(share.status(), 1)
            self.assertNotIn("Each browser opens its own private session", self.output.getvalue())
            def ready_before_cleanup():
                self.assertEqual(self.processes["share-gateway"]["pid"], 987)
                self.assertEqual(self.processes["share-tunnel"]["pid"], 988)
                return True
            with mock.patch.object(share, "session_api_ready", side_effect=ready_before_cleanup):
                self.assertEqual(share.start(), 0)
            self.assertEqual(share.status(), 0)
        self.assertEqual(self.spawned, ["share-gateway", "share-tunnel"])
        self.assertEqual(self.processes["share-gateway"]["sharing_mode"], share.GATEWAY_MODE)
        stored = json.loads(Path(share.launcher.pidfile("share-gateway")).read_text())
        self.assertEqual(stored["sharing_mode"], share.GATEWAY_MODE)
        self.assertEqual(stored["pid"], self.processes["share-gateway"]["pid"])
        self.assertEqual(stored["started_at"], self.processes["share-gateway"]["started_at"])

    def test_unproven_process_record_is_refused_without_any_mutation(self):
        self.origin.write_text('{"origin":"https://old.trycloudflare.com"}')
        with self.controlled(), mock.patch.object(share.launcher, "unproven_process", return_value=True), \
                mock.patch.object(share.launcher, "stop_one") as stop:
            self.assertEqual(share.start(), 1)
            stop.assert_not_called()
        self.assertTrue(self.origin.exists())
        self.assertEqual(self.spawned, [])

    def test_parallel_starts_produce_one_process_pair_and_one_credential(self):
        results = []
        def delayed_spawn(*args):
            time.sleep(0.1)
            return self.spawn(*args)
        with self.controlled(), mock.patch.object(share.launcher, "spawn", side_effect=delayed_spawn):
            threads = [threading.Thread(target=lambda: results.append(share.start())) for _ in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)
                self.assertFalse(thread.is_alive())
        self.assertEqual(results, [0, 0])
        self.assertEqual(self.spawned, ["share-gateway", "share-tunnel"])
        self.assertEqual(set(json.loads(self.gateway.read_text())), {"version", "secret"})

    def test_parallel_stop_waits_for_start_and_then_removes_only_sharing(self):
        entered = threading.Event()
        results = []
        def delayed_spawn(*args):
            entered.set()
            time.sleep(0.1)
            return self.spawn(*args)
        def stop_after_start_enters():
            entered.wait(timeout=2)
            results.append(share.stop())
        with self.controlled(), mock.patch.object(share.launcher, "spawn", side_effect=delayed_spawn):
            threads = [threading.Thread(target=lambda: results.append(share.start())),
                       threading.Thread(target=stop_after_start_enters)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=5)
                self.assertFalse(thread.is_alive())
        self.assertEqual(results, [0, 0])
        self.assertEqual(self.spawned, ["share-gateway", "share-tunnel"])
        self.assertFalse(self.origin.exists())
        self.assertTrue(self.gateway.exists())
        self.assertEqual(set(self.processes), {"api", "web"})

    def test_preparation_never_changes_owner_credentials_data_or_api(self):
        owner = self.path / "auth.json"
        database = self.path / "bean.sqlite3"
        owner.write_text('{"owner":"synthetic-owner-credential-for-this-test-only"}')
        database.write_bytes(b"synthetic existing database")
        expected = (owner.read_bytes(), database.read_bytes())
        with mock.patch.object(share.launcher, "spawn", side_effect=AssertionError("No API restart")), \
                mock.patch.object(share.launcher, "live_config", side_effect=AssertionError("No provider read")):
            share.prepare_gateway()
            credential = self.gateway.read_bytes()
            share.prepare_gateway()
        self.assertEqual((owner.read_bytes(), database.read_bytes()), expected)
        self.assertEqual(self.gateway.read_bytes(), credential)
        data = json.loads(credential)
        self.assertEqual(data["version"], 1)
        self.assertRegex(data["secret"], r"^[A-Za-z0-9_-]{43}$")
        self.assertNotIn(data["secret"], self.output.getvalue())

    def test_invalid_credential_file_is_preserved_and_values_never_reported(self):
        for raw in ('{"version":1,"secret":"private-canary"}', '{"version":1,"version":1}',
                    '[]', '{invalid', ' ' * 1025,
                    json.dumps({"version": True, "secret": "a" * 43}),
                    json.dumps({"version": 1, "secret": "a" * 43, "extra": "value"})):
            with self.subTest(raw=raw[:20]):
                self.gateway.write_text(raw)
                self.gateway.chmod(0o600)
                with self.assertRaisesRegex(share.launcher.LifecycleError, "Gateway configuration is invalid") as raised:
                    share.prepare_gateway()
                self.assertNotIn("private-canary", str(raised.exception))
                self.assertEqual(self.gateway.read_text(), raw)

    def test_permission_symlink_and_nonregular_files_are_refused_before_json_read(self):
        self.gateway.write_text('{"version":1,"secret":"' + 'a' * 43 + '"}')
        self.gateway.chmod(0o644)
        with mock.patch.object(share.json, "loads", side_effect=AssertionError("Must not read content")):
            with self.assertRaises(share.launcher.LifecycleError):
                share.prepare_gateway()
        self.gateway.unlink()
        target = self.path / "target.json"
        target.write_text("private-canary")
        self.gateway.symlink_to(target)
        with self.assertRaises(share.launcher.LifecycleError):
            share.prepare_gateway()
        self.assertEqual(target.read_text(), "private-canary")
        self.gateway.unlink()
        self.gateway.mkdir()
        with self.assertRaises(share.launcher.LifecycleError):
            share.prepare_gateway()

    def test_readiness_requires_registered_available_browser_session_contract(self):
        for body, expected in (
            ({"shared_access": {"mode": "browser_session", "available": True}}, True),
            ({"shared_access": {"mode": "browser_session", "available": False}}, False),
            ({"shared_access": {"mode": "shared_demo", "available": True}}, False), ({}, False), ([], False),
        ):
            with mock.patch.object(share.launcher, "http_json", return_value=(200, body)) as request:
                self.assertEqual(share.session_api_ready(), expected)
                request.assert_called_once_with("http://127.0.0.1:8000/api/bean/v1/capabilities")
        with self.controlled(), mock.patch.object(share, "session_api_ready", return_value=False):
            self.assertEqual(share.start(), 1)
        self.assertEqual(self.spawned, [])
        self.assertTrue(self.gateway.exists())
        self.assertFalse(self.origin.exists())


if __name__ == "__main__":
    unittest.main()
