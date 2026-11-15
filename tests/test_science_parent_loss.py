"""Real worker death and owned-session cleanup, without scientific claims."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import pytest

from bean_api.science import run_bounded


RUNNER = r'''
import json, multiprocessing.process, os, subprocess, sys, time
from pathlib import Path
import bean_api.science as science

root = Path(sys.argv[1])
mode = sys.argv[2]
original_watch = science._watch_parent

def delayed_watch(lifeline, ready, process_group):
    (root / "guard_environment.json").write_text(json.dumps({"synthetic_secret_present": "SYNTHETIC_WORKER_SECRET" in os.environ}))
    (root / "guard.json").write_text(json.dumps({"group": process_group, "guard": os.getpid()}))
    while not (root / "release").exists():
        time.sleep(.01)
    original_watch(lifeline, ready, process_group)

def failed_watch(lifeline, ready, process_group):
    ready.close()
    lifeline.close()

if mode == "startup":
    science._watch_parent = delayed_watch
elif mode == "guard_failure":
    science._watch_parent = failed_watch
elif mode == "guard_start_failure":
    original_start = multiprocessing.process.BaseProcess.start
    def failed_guard_start(process):
        if process._target is science._watch_parent:
            raise OSError("controlled guard creation failure")
        return original_start(process)
    multiprocessing.process.BaseProcess.start = failed_guard_start

class Adapter:
    def investigate(self, *args):
        grandchild = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        (root / "children.json").write_text(json.dumps({"leader": os.getpid(), "grandchild": grandchild.pid}))
        if mode == "normal":
            return {"completed": True}
        if mode == "error":
            raise RuntimeError("controlled adapter failure")
        if mode == "leader_exit":
            while not (root / "release").exists():
                time.sleep(.01)
            os._exit(9)
        time.sleep(30)
        return {"should_not_arrive": True}

if __name__ == "__main__":
    result = science.run_bounded(Adapter(), "investigate", ({}, {}, {}), wall_seconds=25)
    (root / "result.json").write_text(json.dumps(result))
'''


def running(pid):
    """A zombie awaiting the OS reaper is no longer executing computation."""
    try:
        if Path(f"/proc/{pid}/stat").read_text().split()[2] == "Z":
            return False
    except (FileNotFoundError, ProcessLookupError):
        pass
    if sys.platform == "darwin":
        # With the worker deliberately stopped, an exited direct child remains
        # its zombie until the worker resumes/reaps it. Observe only this owned
        # PID; kill(pid, 0) alone cannot distinguish that from running work.
        state = subprocess.run(["/bin/ps", "-o", "stat=", "-p", str(pid)], capture_output=True,
                               text=True, timeout=2, env={"PATH": os.defpath, "LANG": "C"})
        if state.stdout.lstrip().startswith("Z"):
            return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def wait_until(predicate, message, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(.01)
    pytest.fail(message)


def read_when_ready(path):
    def parse():
        try:
            return json.loads(path.read_text())
        except (FileNotFoundError, ValueError):
            return None
    wait_until(parse, f"The controlled child never wrote {path.name}")
    return parse()


@pytest.fixture
def launch(tmp_path):
    script = tmp_path / "runner.py"
    script.write_text(RUNNER)
    processes = []
    roots = []

    def start(mode):
        root = tmp_path / mode
        root.mkdir()
        env = {"PATH": os.defpath, "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "apps" / "api"),
               "SYNTHETIC_WORKER_SECRET": "controlled-test-value"}
        process = subprocess.Popen([sys.executable, str(script), str(root), mode], env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        processes.append(process)
        roots.append(root)
        return process, root

    yield start

    for process in processes:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=5)
        process.stderr.close()
    # Test failure cleanup uses only groups freshly captured by this fixture.
    for root in roots:
        for name, field in (("children.json", "leader"), ("guard.json", "group")):
            path = root / name
            if path.exists():
                try:
                    os.killpg(json.loads(path.read_text())[field], signal.SIGKILL)
                except ProcessLookupError:
                    pass


@pytest.mark.parametrize("stop_signal", [signal.SIGKILL, signal.SIGTERM])
def test_worker_death_ends_running_scientific_session_before_wall_limit(launch, stop_signal):
    worker, root = launch("hang")
    pids = read_when_ready(root / "children.json")
    assert all(running(pid) for pid in pids.values())
    started = time.monotonic()
    worker.send_signal(stop_signal)
    worker.wait(timeout=3)
    wait_until(lambda: not any(running(pid) for pid in pids.values()),
               "Scientific work survived the supervising worker")
    assert time.monotonic() - started < 5  # approved wall budget is 25 seconds
    assert not (root / "result.json").exists()


def test_guard_survives_scientific_leader_exit_until_worker_death(launch):
    worker, root = launch("leader_exit")
    pids = read_when_ready(root / "children.json")
    worker.send_signal(signal.SIGSTOP)  # prevent its ordinary finally cleanup
    try:
        (root / "release").touch()
        wait_until(lambda: not running(pids["leader"]), "Scientific leader did not exit")
        assert running(pids["grandchild"]), "The test needs a live descendant at worker death"
    finally:
        worker.kill()  # SIGKILL also ends a stopped process
        worker.wait(timeout=3)
    wait_until(lambda: not running(pids["grandchild"]),
               "The independent guard did not clean the abandoned descendant")


def test_worker_death_before_guard_readiness_cannot_dispatch_adapter(launch):
    worker, root = launch("startup")
    pids = read_when_ready(root / "guard.json")
    assert read_when_ready(root / "guard_environment.json") == {"synthetic_secret_present": False}
    assert running(pids["group"]) and running(pids["guard"])
    assert not (root / "children.json").exists()
    worker.kill()
    worker.wait(timeout=3)
    (root / "release").touch()
    wait_until(lambda: not any(running(pid) for pid in pids.values()),
               "The startup guard did not observe parent loss")
    assert not (root / "children.json").exists()


@pytest.mark.parametrize("mode,expected", [("normal", {"completed": True}),
    ("error", {"worker_error": "scientific_worker_failed"}),
    ("guard_failure", {"worker_error": "scientific_worker_setup_failed"}),
    ("guard_start_failure", {"worker_error": "scientific_worker_setup_failed"})])
def test_return_error_and_guard_failure_preserve_results_and_clean_descendants(launch, mode, expected):
    worker, root = launch(mode)
    worker.wait(timeout=8)
    assert worker.returncode == 0, worker.stderr.read().decode()
    assert read_when_ready(root / "result.json") == expected
    if mode in {"guard_failure", "guard_start_failure"}:
        assert not (root / "children.json").exists()
    else:
        pids = read_when_ready(root / "children.json")
        wait_until(lambda: not any(running(pid) for pid in pids.values()),
                   "A descendant outlived its completed scientific session")


class ImmediateAdapter:
    def investigate(self, *args):
        return {"completed": True}


def test_repeated_immediate_results_are_not_lost_when_the_leader_exits():
    for _ in range(5):
        assert run_bounded(ImmediateAdapter(), "investigate", ({}, {}, {}), wall_seconds=5) == {"completed": True}
