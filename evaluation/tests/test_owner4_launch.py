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


class _Root:
    def __init__(self, pid, alive=True):
        self.pid, self._alive = pid, alive

    def poll(self):
        return None if self._alive else 0


class OrphanDetection(unittest.TestCase):
    """A reparented grandchild in an orphaned session is still found; attached and unrelated processes are not."""

    def stack(self, table, roots, seen):
        stack = launcher.LocalStack.__new__(launcher.LocalStack)
        stack.processes = {name: _Root(pid, alive) for name, (pid, alive) in roots.items()}
        stack.seen_descendants = {pid: table[pid] for pid in seen}
        stack.events = []
        original = launcher.process_table
        launcher.process_table = lambda: table
        self.addCleanup(setattr, launcher, "process_table", original)
        return stack

    def table(self):
        row = lambda ppid, pgid, command: {"ppid": ppid, "pgid": pgid, "command": command}  # noqa: E731
        return {100: row(1, 100, "python -m bean_api.worker"),
                101: row(100, 100, "python -c from multiprocessing.resource_tracker"),
                200: row(1, 200, "python -c from multiprocessing.spawn import spawn_main"),   # orphaned child
                201: row(1, 200, "python3.11 -m counterdex"),                                # its reparented grandchild
                300: row(1, 300, "unrelated process")}

    def test_orphan_session_members_are_found_even_after_reparenting(self):
        stack = self.stack(self.table(), {"worker": (100, True)}, seen=[101, 200])
        self.assertEqual(set(stack.orphans()), {200, 201})

    def test_after_teardown_everything_left_in_tracked_groups_is_reported(self):
        # The root no longer counts as owned-and-alive, so its surviving group members (even itself, had it
        # ignored the stop) and the orphaned session are all leftovers; the unrelated process never is.
        stack = self.stack(self.table(), {"worker": (100, False)}, seen=[101, 200])
        self.assertEqual(set(stack.orphans()), {100, 101, 200, 201})


if __name__ == "__main__":
    unittest.main()


class EvidenceOnlyDescendants(unittest.TestCase):
    """Committing evidence moves HEAD; the gate still reads it, but never across a code change."""

    def git(self, *args):
        env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t",
               "GIT_COMMITTER_EMAIL": "t@example.invalid", "PATH": os.environ.get("PATH", ""), "HOME": self.repo}
        out = subprocess.run(["git", "-C", self.repo, *args], capture_output=True, text=True, env=env, check=True)
        return out.stdout.strip()

    def commit(self, path, text):
        full = os.path.join(self.repo, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as handle:
            handle.write(text)
        self.git("add", path)
        self.git("commit", "-q", "-m", path)
        return self.git("rev-parse", "HEAD")

    def setUp(self):
        self.repo = tempfile.mkdtemp(prefix="drbean-gate-git-")
        self.addCleanup(shutil.rmtree, self.repo, ignore_errors=True)
        self.git("init", "-q")
        self.code = self.commit("evaluation/drbean_eval/x.py", "a = 1\n")

    def test_evidence_and_log_commits_keep_the_tested_code(self):
        from drbean_eval import gates
        evidence = self.commit("evaluation/results/attempts.jsonl", "{}\n")
        log = self.commit("docs/workstreams/05-validation.md", "log\n")
        self.assertEqual(gates.equivalent_commits(self.repo, log, {self.code, evidence}), {self.code, evidence, log})

    def test_a_code_change_or_an_unrelated_commit_is_never_equivalent(self):
        from drbean_eval import gates
        evidence = self.commit("evaluation/results/attempts.jsonl", "{}\n")
        changed = self.commit("evaluation/drbean_eval/x.py", "a = 2\n")
        self.assertEqual(gates.equivalent_commits(self.repo, changed, {self.code, evidence}), {changed})
        self.assertEqual(gates.equivalent_commits(self.repo, changed, {"0" * 40}), {changed})
