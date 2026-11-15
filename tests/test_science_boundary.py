import multiprocessing
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

from bean_api.science import UnavailableAdapter, run_bounded
from bean_api.science import _kill_owned_session


class SlowAdapter:
    def investigate(self, *args):
        time.sleep(10)
        return {"should_not_arrive": True}


class DescendantAdapter:
    def investigate(self, problem, dataset, limits):
        descendant = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        Path(problem["pid_file"]).write_text(str(descendant.pid))
        if problem.get("return_early"):
            return {"descendant_pid": descendant.pid}
        time.sleep(30)
        return {}


def process_running(pid):
    # A dead process awaiting its OS reaper is no longer executing computation.
    stat = Path(f"/proc/{pid}/stat")
    try:
        if stat.read_text().split()[2] == "Z":
            return False
    except (FileNotFoundError, ProcessLookupError):
        # The OS can reap the process while this observer reads its state.
        # Fall through to the portable liveness check (also used off Linux).
        pass
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def assert_descendant_terminated(pid):
    deadline = time.monotonic() + 2
    while process_running(pid) and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not process_running(pid), "The owned descendant remained running after parent acknowledgement"


@pytest.mark.parametrize("failure", [FileNotFoundError, ProcessLookupError])
def test_process_observer_handles_reaping_during_stat_read(monkeypatch, failure):
    def disappeared(*args, **kwargs):
        raise failure
    def reaped(*args):
        raise ProcessLookupError
    monkeypatch.setattr(Path, "read_text", disappeared)
    monkeypatch.setattr(os, "kill", reaped)
    assert not process_running(12345)


@pytest.mark.parametrize("reaped_exitcode", [-9, None])
def test_session_permission_failure_retries_only_after_reaping_dead_leader(monkeypatch, reaped_exitcode):
    class Process:
        pid = 12345
        exitcode = None

        def join(self, timeout):
            assert timeout == 2
            self.exitcode = reaped_exitcode

    attempts = []

    def killpg(pid, stop_signal):
        attempts.append((pid, stop_signal))
        if len(attempts) == 1:
            raise PermissionError("controlled Darwin zombie session")
        raise ProcessLookupError("reaped session no longer exists")

    monkeypatch.setattr(os, "killpg", killpg)
    if reaped_exitcode is None:
        with pytest.raises(PermissionError):
            _kill_owned_session(Process())
        assert len(attempts) == 1
    else:
        _kill_owned_session(Process())
        assert attempts == [(12345, 9), (12345, 9)]


def test_session_permission_failure_after_reaping_is_not_ignored(monkeypatch):
    class Process:
        pid = 12345
        exitcode = -9

        def join(self, timeout):
            pass

    def denied(*args):
        raise PermissionError("controlled real signal denial")

    monkeypatch.setattr(os, "killpg", denied)
    times = iter([0, 3])
    monkeypatch.setattr(time, "monotonic", lambda: next(times))
    with pytest.raises(PermissionError, match="real signal denial"):
        _kill_owned_session(Process())


def test_unconfigured_science_has_no_checked_capability():
    adapter = UnavailableAdapter()
    assert adapter.capabilities()["implemented"] is False
    result = run_bounded(adapter, "investigate", ({"id": "problem"}, {}, {}), wall_seconds=3)
    assert result["scientific_outcome"] == "unsupported"
    assert result["verification"] == "unsupported"


def test_wall_limit_terminates_owned_process():
    before = {child.pid for child in multiprocessing.active_children()}
    started = time.monotonic()
    result = run_bounded(SlowAdapter(), "investigate", ({}, {}, {}), wall_seconds=1)
    assert result == {"worker_error": "scientific_wall_limit"}
    assert time.monotonic() - started < 4
    assert {child.pid for child in multiprocessing.active_children()} == before


def test_cancel_is_acknowledged_after_process_termination():
    before = {child.pid for child in multiprocessing.active_children()}
    result = run_bounded(SlowAdapter(), "investigate", ({}, {}, {}), wall_seconds=5, cancelled=lambda: True)
    assert result == {"worker_error": "cancelled"}
    assert {child.pid for child in multiprocessing.active_children()} == before


def test_cancellation_terminates_descendants(tmp_path):
    pid_file = tmp_path / "child.pid"
    result = run_bounded(DescendantAdapter(), "investigate", ({"pid_file": str(pid_file)}, {}, {}),
                         wall_seconds=5, cancelled=pid_file.exists)
    assert result == {"worker_error": "cancelled"}
    assert_descendant_terminated(int(pid_file.read_text()))


def test_descendant_cannot_escape_by_outliving_adapter(tmp_path):
    pid_file = tmp_path / "child.pid"
    result = run_bounded(DescendantAdapter(), "investigate",
                         ({"pid_file": str(pid_file), "return_early": True}, {}, {}), wall_seconds=5)
    assert "descendant_pid" in result
    assert_descendant_terminated(result["descendant_pid"])
