"""Workstream 5 Python integration tests: shared guard, markers and launched-stack fixtures.

Markers (select with ``-m``):

* ``real_stack``      launches an isolated local API + worker and talks real HTTP;
* ``real_science``    additionally needs the real scientific adapter end to end;
* ``controlled_app``  in-process application with explicitly controlled provider/model doubles
                      (controlled placeholder output, never Gemini evidence);
* ``zero_dispatch``   proves that no external model request can be attempted.

The whole pytest process runs under the egress guard once this directory is collected:
non-loopback DNS/connect and Gemini client construction are refused and logged.
Owner 4's ``web_manual_smoke.mjs``, ``package.json`` and ``release_checklist.json`` are not
touched by these fixtures.
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from drbean_support import REPO, SESSION_GUARD_LOG, launcher  # noqa: E402
from drbean_eval.guard import sitecustomize as guard  # noqa: E402

guard.install(SESSION_GUARD_LOG)  # no-op if already installed in this interpreter
os.environ.setdefault("DRBEAN_BACKEND_PYTHON", sys.executable)  # pytest already runs in the backend env

MARKERS = {
    "real_stack": "launches an isolated local API + worker (real HTTP)",
    "real_science": "needs the real scientific adapter through the ordinary stack",
    "controlled_app": "in-process app with controlled provider/model doubles (placeholder, not Gemini)",
    "zero_dispatch": "proves no external model request can be attempted",
}


def pytest_configure(config):
    for name, text in MARKERS.items():
        config.addinivalue_line("markers", f"{name}: {text}")


@pytest.fixture
def stack_factory():
    """Start isolated stacks inside a test; every one is stopped and its orphans reported."""
    started = []

    def start(**kwargs) -> launcher.LocalStack:
        stack = launcher.LocalStack(str(REPO), **kwargs)
        started.append(stack)
        return stack.start()

    yield start
    for stack in started:
        report = stack.stop()
        stack.cleanup()
        assert not report["orphans"], f"processes outlived teardown: {report['orphans']}"


@pytest.fixture(scope="module")
def module_stack():
    stack = launcher.LocalStack(str(REPO)).start()
    yield stack
    report = stack.stop()
    stack.cleanup()
    assert not report["orphans"], f"processes outlived teardown: {report['orphans']}"
