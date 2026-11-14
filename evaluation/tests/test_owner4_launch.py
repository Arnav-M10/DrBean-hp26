"""Owner 4's launch path: the harness passes only configuration that launcher honours.

Nothing is launched here. The stack object is built without its constructor so these checks
need no backend interpreter (the CI harness job has none); tests/integration and the
``--subject http-owner4-launcher`` lane exercise the real launcher.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(ROOT)
sys.path.insert(0, ROOT)

from drbean_eval import launcher  # noqa: E402


def bare_stack(diagnostics=()):
    stack = launcher.Owner4LauncherStack.__new__(launcher.Owner4LauncherStack)
    stack.workdir = tempfile.mkdtemp(prefix="drbean-o4-unit-")
    stack.repo, stack.var = REPO, os.path.join(stack.workdir, "var")
    stack.guard_log = os.path.join(stack.workdir, "egress-guard.jsonl")
    stack.barrier_path = os.path.join(stack.workdir, "science.barrier")
    stack.diagnostic_overrides = tuple(diagnostics)
    return stack


class Owner4LaunchEnvironment(unittest.TestCase):
    def setUp(self):
        self.stacks = []

    def tearDown(self):
        for stack in self.stacks:
            shutil.rmtree(stack.workdir, ignore_errors=True)

    def stack(self, diagnostics=()):
        self.stacks.append(bare_stack(diagnostics))
        return self.stacks[-1]

    def test_only_dummy_credentials_and_an_isolated_store(self):
        stack = self.stack()
        env = stack.launcher_environment(import_path=False)
        credentials = {k: v for k, v in env.items() if launcher._CREDENTIAL_NAME.search(k)}
        self.assertEqual(set(credentials), set(launcher.OWNER4_DUMMY_CREDENTIALS))
        self.assertTrue(all(launcher.DUMMY_VALUE.match(v) for v in credentials.values()), credentials)
        self.assertEqual(env["DRBEAN_VAR_DIR"], stack.var)  # the stack's own temporary store, never <repo>/var
        self.assertFalse(env["DRBEAN_VAR_DIR"].startswith(os.path.join(REPO, "var")))
        self.assertNotIn("BEAN_AUTH_TOKENS_JSON", env)  # the launcher's own auth-file path is exercised
        self.assertNotIn("VIRTUAL_ENV", env)

    def test_guard_comes_first_and_the_import_path_is_only_a_labelled_retry(self):
        stack = self.stack()
        plain = stack.launcher_environment(import_path=False)["PYTHONPATH"].split(os.pathsep)
        retry = stack.launcher_environment(import_path=True)["PYTHONPATH"].split(os.pathsep)
        self.assertEqual(plain, [launcher.GUARD_DIR])
        self.assertEqual(retry, [launcher.GUARD_DIR, os.path.join(REPO, "apps", "api")])

    def test_diagnostics_are_named_explicitly(self):
        env = self.stack(("relax_nproc", "science_barrier")).launcher_environment(import_path=False)
        self.assertEqual(env["DRBEAN_DIAGNOSTIC_OVERRIDES"], "relax_nproc,science_barrier")
        self.assertIn("DRBEAN_DIAGNOSTIC_BARRIER", env)
        self.assertNotIn("DRBEAN_DIAGNOSTIC_OVERRIDES", self.stack().launcher_environment(import_path=False))

    def test_cli_keeps_the_owner4_path_out_of_the_release_history(self):
        out = subprocess.run([sys.executable, os.path.join(ROOT, "cli.py"), "run", "--lane", "offline_real_science",
                              "--subject", "http-owner4-launcher"], capture_output=True, text=True, timeout=60)
        self.assertEqual(out.returncode, 1, out.stdout + out.stderr)
        self.assertIn("separate --results", out.stdout)


if __name__ == "__main__":
    unittest.main()
