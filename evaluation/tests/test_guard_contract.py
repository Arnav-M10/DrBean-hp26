"""Small guard/observer controls using synthetic names and no real credentials."""
from collections.abc import Mapping
import os
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from drbean_eval import launcher  # noqa: E402
from drbean_eval.guard import sitecustomize as guard  # noqa: E402


class NameOnlyEnvironment(Mapping):
    def __iter__(self):
        return iter(("OPENAI_API_KEY", "PATH"))

    def __len__(self):
        return 2

    def __getitem__(self, name):
        if name == "OPENAI_API_KEY":
            raise AssertionError("Credential inventory must not access a value")
        raise KeyError(name)


class GuardContractTests(unittest.TestCase):
    def test_startup_credential_inventory_iterates_names_without_reading_values(self):
        with patch.object(guard.os, "environ", NameOnlyEnvironment()), \
             patch.object(guard.sys, "_drbean_guard_installed", False, create=True), \
             patch.object(guard.sys, "meta_path", list(sys.meta_path)), \
             patch.object(guard.sys, "addaudithook"), patch.object(guard, "_LOG", None), \
             patch.object(guard, "_watch_credential_reads"), patch.object(guard, "_record") as recorded:
            self.assertTrue(guard.install("synthetic-guard-log"))
        recorded.assert_called_once()
        self.assertEqual(recorded.call_args.kwargs["credential_names_present"], ["OPENAI_API_KEY"])

    def test_explicit_diagnostic_barrier_holds_recheck_too(self):
        class Adapter:
            def recheck(self):
                return "actual method reached"

        with patch.dict(os.environ, {"DRBEAN_DIAGNOSTIC_BARRIER": "synthetic-barrier"}), \
             patch.object(guard.os.path, "exists", side_effect=[True, True, False]), \
             patch.object(guard.time, "sleep") as sleep, patch.object(guard, "_record") as recorded:
            guard._science_barrier(SimpleNamespace(CounterdexAdapter=Adapter))
            self.assertEqual(Adapter().recheck(), "actual method reached")
        sleep.assert_called_once_with(0.05)
        self.assertEqual(recorded.call_args_list[0].kwargs["method"], "recheck")

    def test_orphan_zombie_is_not_live_computation_and_unknown_state_stays_live(self):
        for state, expected in (("Z+", False), ("S", True), ("", True)):
            with patch.object(launcher.os, "kill"), patch.object(launcher.os, "waitpid", side_effect=ChildProcessError), \
                 patch.object(launcher.subprocess, "run", return_value=SimpleNamespace(stdout=state)):
                self.assertEqual(launcher.alive(12345), expected)


if __name__ == "__main__":
    unittest.main()
