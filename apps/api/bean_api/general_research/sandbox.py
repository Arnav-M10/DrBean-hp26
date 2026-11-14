"""Run a fixed-path parser worker with wall-clock, output and effective memory bounds.

Linux: the worker installs RLIMIT_AS itself (``resource_policy.apply_limits``) and
the parent additionally polls resident memory. macOS cannot set RLIMIT_AS/DATA for
this runtime (setrlimit fails below the current reservation), so the parent polls
the child's physical footprint through ``proc_pid_rusage`` and kills the whole
process group once it exceeds the bound. A timeout alone never caps memory. The
watchdog is a backstop: the PDF pre-scan refuses unbounded decoding beforehand.
This is resource isolation, not a complete security sandbox.
"""
from __future__ import annotations

import ctypes
import ctypes.util
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field


class WorkerLimitExceeded(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass
class WorkerOutcome:
    returncode: int
    stdout: bytes
    stderr: bytes
    guard: dict = field(default_factory=dict)


class _RusageInfoV0(ctypes.Structure):
    _fields_ = [("ri_uuid", ctypes.c_uint8 * 16), ("ri_user_time", ctypes.c_uint64),
                ("ri_system_time", ctypes.c_uint64), ("ri_pkg_idle_wkups", ctypes.c_uint64),
                ("ri_interrupt_wkups", ctypes.c_uint64), ("ri_pageins", ctypes.c_uint64),
                ("ri_wired_size", ctypes.c_uint64), ("ri_resident_size", ctypes.c_uint64),
                ("ri_phys_footprint", ctypes.c_uint64), ("ri_proc_start_abstime", ctypes.c_uint64),
                ("ri_proc_exit_abstime", ctypes.c_uint64)]


_LIBPROC = None


def _darwin_memory(pid: int) -> int | None:
    global _LIBPROC
    if _LIBPROC is None:
        _LIBPROC = ctypes.CDLL(ctypes.util.find_library("proc") or "/usr/lib/libproc.dylib", use_errno=True)
        _LIBPROC.proc_pid_rusage.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.POINTER(_RusageInfoV0)]
        _LIBPROC.proc_pid_rusage.restype = ctypes.c_int
    info = _RusageInfoV0()
    if _LIBPROC.proc_pid_rusage(pid, 0, ctypes.byref(info)) != 0:
        return None
    return max(int(info.ri_phys_footprint), int(info.ri_resident_size))


def _linux_memory(pid: int) -> int | None:
    try:
        resident_pages = int(Path(f"/proc/{pid}/statm").read_text().split()[1])
    except (OSError, ValueError, IndexError):
        return None
    return resident_pages * os.sysconf("SC_PAGE_SIZE")


def memory_probe():
    if sys.platform == "darwin":
        return _darwin_memory, "phys_footprint_watchdog"
    if sys.platform.startswith("linux"):
        return _linux_memory, "rlimit_as_and_rss_watchdog"
    return None, "unavailable"


def describe_guards() -> dict:
    _, kind = memory_probe()
    return {"memory": kind, "memory_enforced_by": "worker_rlimit_and_parent" if kind.startswith("rlimit") else
            "parent_watchdog" if kind != "unavailable" else "unavailable",
            "wall_clock": "parent_enforced", "output_bytes": "parent_enforced", "cpu": "rlimit_cpu",
            "process_group": "killed_on_any_limit"}


def run_worker(script: Path, header: bytes, payload: bytes, *, timeout: float, memory_bytes: int,
               output_bytes: int, poll_seconds: float = 0.005, executable: str | None = None) -> WorkerOutcome:
    """Start ``script`` in its own session with a minimal environment and supervise it."""
    probe, kind = memory_probe()
    if probe is None:
        raise WorkerLimitExceeded("worker_memory_guard_unavailable")
    command = [executable or sys.executable, "-I", str(script)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               env={"PATH": os.defpath, "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
                               start_new_session=True, close_fds=True)
    chunks: dict[str, list[bytes]] = {"stdout": [], "stderr": []}
    sizes = {"stdout": 0, "stderr": 0}
    breach: list[str] = []

    def kill(code: str) -> None:
        if not breach:
            breach.append(code)
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass

    def feed() -> None:
        try:
            process.stdin.write(header + b"\n" + payload)
            process.stdin.close()
        except (BrokenPipeError, OSError):
            pass

    def drain(name: str, stream, cap: int) -> None:
        while True:
            block = stream.read(1 << 16)
            if not block:
                return
            sizes[name] += len(block)
            if sizes[name] > cap:
                kill("worker_output_limit")
                return
            chunks[name].append(block)

    threads = [threading.Thread(target=feed, daemon=True),
               threading.Thread(target=drain, args=("stdout", process.stdout, output_bytes), daemon=True),
               threading.Thread(target=drain, args=("stderr", process.stderr, 4096), daemon=True)]
    for thread in threads:
        thread.start()
    started, peak = time.monotonic(), 0
    while process.poll() is None:
        used = probe(process.pid)
        if used is not None:
            peak = max(peak, used)
            if used > memory_bytes:
                kill("worker_memory_limit")
                break
        if time.monotonic() - started > timeout:
            kill("worker_timeout")
            break
        time.sleep(poll_seconds)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        kill("worker_timeout")
        process.wait()
    for thread in threads:
        thread.join(timeout=5)
    guard = {"memory_guard": kind, "memory_limit_bytes": memory_bytes, "peak_observed_bytes": peak,
             "wall_seconds": round(time.monotonic() - started, 3), "poll_seconds": poll_seconds}
    if breach:
        raise WorkerLimitExceeded(breach[0])
    return WorkerOutcome(process.returncode, b"".join(chunks["stdout"]), b"".join(chunks["stderr"]), guard)
