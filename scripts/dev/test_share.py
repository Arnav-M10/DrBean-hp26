"""Offline sharing launcher controls. Never starts a tunnel or reads provider keys."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from scripts.dev import share


class Sharing(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name)
        self.origin = self.path / "origin.json"
        for name, value in (("ORIGIN_FILE", self.origin),):
            patch = mock.patch.object(share, name, value)
            patch.start()
            self.addCleanup(patch.stop)
        patch = mock.patch.object(share.launcher, "RUN", str(self.path))
        patch.start()
        self.addCleanup(patch.stop)
        self.capture = mock.patch("sys.stdout", new_callable=io.StringIO)
        self.output = self.capture.start()
        self.addCleanup(self.capture.stop)
        patch = mock.patch.object(share, "ACCESS_FILE", self.path / "access.json")
        patch.start()
        self.addCleanup(patch.stop)

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

    def test_stopping_sharing_touches_only_owned_sharing_processes_and_removes_origin(self):
        self.origin.write_text('{"origin":"https://bean.trycloudflare.com"}')
        with mock.patch.object(share.launcher, "stop_one", return_value="stopped") as stop:
            self.assertEqual(share.stop(), 0)
        self.assertEqual([call.args[0] for call in stop.call_args_list], list(share.NAMES))
        self.assertFalse(self.origin.exists())

    def test_missing_tool_or_local_app_does_not_spawn_or_publish(self):
        for binary, occupied in ((None, True), ("/test/cloudflared", False)):
            with self.subTest(binary=binary), mock.patch.object(share.launcher, "owned", return_value=None), \
                    mock.patch.object(share.shutil, "which", return_value=binary), \
                    mock.patch.object(share.launcher, "port_in_use", return_value=occupied), \
                    mock.patch.object(share.launcher, "spawn") as spawn:
                self.assertEqual(share.start(), 1)
                spawn.assert_not_called()
        self.assertFalse(self.origin.exists())

    def test_foreign_gateway_port_is_left_alone(self):
        with mock.patch.object(share.launcher, "owned", return_value=None), \
                mock.patch.object(share.shutil, "which", return_value="/test/cloudflared"), \
                mock.patch.object(share.launcher, "port_in_use", return_value=True), \
                mock.patch.object(share.launcher, "spawn") as spawn, \
                mock.patch.object(share.launcher, "stop_one") as stop:
            self.assertEqual(share.start(), 1)
            spawn.assert_not_called()
            stop.assert_not_called()

    def test_controlled_start_records_origin_and_routes_only_sanitized_environment(self):
        processes = {}
        def spawn(name, command, env):
            self.assertEqual(env, {"BEAN_AI_MODE": "placeholder", "BEAN_SHARE_ORIGIN_FILE": str(self.origin),
                                   "BEAN_SHARE_ACCESS_FILE": str(share.ACCESS_FILE)})
            self.assertNotIn("GEMINI_API_KEY", env)
            processes[name] = {"pid": 123, "command": command}
            if name == "share-tunnel":
                (self.path / "share-tunnel.log").write_text("Shared URL https://bean-study.trycloudflare.com\n")
        with mock.patch.object(share.launcher, "owned", side_effect=lambda name: processes.get(name)), \
                mock.patch.object(share.launcher, "port_in_use", side_effect=lambda port: port != share.PORT), \
                mock.patch.object(share.shutil, "which", side_effect=lambda name: "/test/cloudflared" if name == "cloudflared" else None), \
                mock.patch.object(share.launcher, "child_env", return_value={"BEAN_AI_MODE": "placeholder"}), \
                mock.patch.object(share, "prepare_demo"), \
                mock.patch.object(share.launcher, "spawn", side_effect=spawn):
            self.assertEqual(share.start(), 0)
        self.assertEqual(share.recorded_origin(), "https://bean-study.trycloudflare.com")
        self.assertEqual(self.origin.stat().st_mode & 0o777, 0o600)
        self.assertEqual(set(processes), {"share-gateway", "share-tunnel"})
        command = processes["share-tunnel"]["command"]
        self.assertIn("http://127.0.0.1:4174", command)
        self.assertNotIn("--token", command)

    def test_failed_gateway_start_closes_origin_and_stops_only_sharing(self):
        with mock.patch.object(share.launcher, "owned", return_value=None), \
                mock.patch.object(share.launcher, "port_in_use", side_effect=lambda port: port != share.PORT), \
                mock.patch.object(share.shutil, "which", return_value="/test/cloudflared"), \
                mock.patch.object(share, "prepare_demo"), \
                mock.patch.object(share.launcher, "spawn", side_effect=OSError("controlled start failure")), \
                mock.patch.object(share.launcher, "stop_one", return_value="not running") as stop:
            self.assertEqual(share.start(), 1)
        self.assertEqual([call.args[0] for call in stop.call_args_list], list(share.NAMES))
        self.assertFalse(self.origin.exists())

    def test_preparing_demo_preserves_owner_identity_and_restarts_only_the_owned_api(self):
        auth = self.path / "auth.json"
        owner_token = "owner_" + "a" * 40
        auth.write_text(json.dumps({"owner": owner_token}))
        with mock.patch.object(share.launcher, "VAR", str(self.path)), \
                mock.patch.object(share.launcher, "owned", return_value={"command": ["python", "api"]}), \
                mock.patch.object(share.launcher, "stop_one") as stop, \
                mock.patch.object(share.launcher, "spawn") as spawn, \
                mock.patch.object(share.launcher, "child_env", return_value={}), \
                mock.patch.object(share.launcher, "live_config", return_value={"state": "disabled"}), \
                mock.patch.object(share, "demo_request", side_effect=[[], {"id": "demo-workspace"}]) as request:
            share.prepare_demo()
        tokens = json.loads(auth.read_text())
        self.assertEqual(tokens["owner"], owner_token)
        demo_token = tokens[share.DEMO_ACTOR]
        self.assertNotEqual(demo_token, owner_token)
        self.assertGreaterEqual(len(demo_token), 32)
        self.assertEqual(json.loads(share.ACCESS_FILE.read_text()), {"token": demo_token})
        self.assertEqual(share.ACCESS_FILE.stat().st_mode & 0o777, 0o600)
        stop.assert_called_once_with("api")
        self.assertEqual(spawn.call_args.args[0], "api")
        self.assertEqual(request.call_args_list[-1].args[1], {"name": "Shared demo"})

    def test_existing_demo_access_reuses_identity_without_restarting_api_or_reading_gemini_config(self):
        demo_token = "demo_" + "b" * 40
        (self.path / "auth.json").write_text(json.dumps({share.DEMO_ACTOR: demo_token}))
        with mock.patch.object(share.launcher, "VAR", str(self.path)), \
                mock.patch.object(share.launcher, "stop_one") as stop, \
                mock.patch.object(share.launcher, "live_config") as live, \
                mock.patch.object(share, "demo_request", return_value=[{"id": "existing"}]):
            share.prepare_demo()
        stop.assert_not_called()
        live.assert_not_called()
        self.assertEqual(json.loads(share.ACCESS_FILE.read_text())["token"], demo_token)


if __name__ == "__main__":
    unittest.main()
