"""Supervisor fault-injection diagnostics; no scientific workload qualification."""
from pathlib import Path
import subprocess

import pytest

from bean_api.general_research import sandbox


def child_script(tmp_path, source):
    script = tmp_path / "controlled_supervisor_probe.py"
    script.write_text(source)
    return script


def record_children(monkeypatch):
    children = []
    original = subprocess.Popen
    def start(*args, **kwargs):
        child = original(*args, **kwargs)
        children.append(child)
        return child
    monkeypatch.setattr(sandbox.subprocess, "Popen", start)
    return children


def assert_closed(child):
    assert child.poll() is not None
    assert all(stream.closed for stream in (child.stdin, child.stdout, child.stderr))


def test_monitor_exception_terminates_owned_parser_and_closes_all_handles(tmp_path, monkeypatch):
    children = record_children(monkeypatch)
    script = child_script(tmp_path, "import time\ntime.sleep(60)\n")
    def failed_probe(pid):
        raise RuntimeError("controlled monitor failure")
    monkeypatch.setattr(sandbox, "memory_probe", lambda: (failed_probe, "controlled_probe"))
    with pytest.raises(RuntimeError, match="controlled monitor failure"):
        sandbox.run_worker(Path(script), b"{}", b"", timeout=5, memory_bytes=512*1024*1024, output_bytes=1024)
    assert len(children) == 1
    assert_closed(children[0])


def test_genuine_permission_failure_is_visible_while_final_cleanup_closes_handles(tmp_path, monkeypatch):
    children = record_children(monkeypatch)
    script = child_script(tmp_path, "import sys,time\nsys.stdout.write('x'*100000);sys.stdout.flush()\ntime.sleep(60)\n")
    original = sandbox._kill_owned_session
    denied = []
    def one_denial(handle):
        if not denied:
            denied.append(True)
            raise PermissionError("controlled genuine signal denial")
        return original(handle)
    monkeypatch.setattr(sandbox, "_kill_owned_session", one_denial)
    with pytest.raises(PermissionError, match="controlled genuine signal denial"):
        sandbox.run_worker(script, b"{}", b"", timeout=2, memory_bytes=512*1024*1024, output_bytes=16)
    assert_closed(children[0])
