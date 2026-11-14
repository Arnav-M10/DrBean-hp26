"""Owner01 adapter seam and killable, bounded scientific process boundary.

The server chooses the prepared adapter and runtime; a model can never select
an import, path, or command. The explicit unavailable adapter remains useful
for deployment diagnosis and isolated workflow tests.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import multiprocessing
import os
import signal
import time
from typing import Any, Callable, Protocol

from .resource_policy import ResourceSetupError, apply_limits


class ScienceAdapter(Protocol):
    def capabilities(self) -> dict[str, Any]: ...
    def investigate(self, problem: dict[str, Any], dataset: dict[str, Any], limits: dict[str, int]) -> dict[str, Any]: ...
    def design(self, request: dict[str, Any], historical_evidence: dict[str, Any]) -> dict[str, Any]: ...
    def review(self, problem: dict[str, Any], dataset: dict[str, Any], limits: dict[str, int], context: dict[str, Any]) -> dict[str, Any]: ...
    def recheck(self, problem: dict[str, Any], dataset: dict[str, Any], limits: dict[str, int], context: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class UnavailableAdapter:
    def capabilities(self) -> dict[str, Any]:
        return {"implemented": False, "configured": False, "verified_in_environment": False,
                "reason": "groundwork_adapter_not_installed", "claim_families": [],
                "design_tiers": [], "native_replay": False, "browser_replay": False}

    def investigate(self, problem: dict[str, Any], dataset: dict[str, Any], limits: dict[str, int]) -> dict[str, Any]:
        return {"scientific_outcome": "unsupported", "verification": "unsupported",
                "expected_binding": "not_supplied", "replay": "unsupported",
                "reason_code": "groundwork_adapter_not_installed", "problem_id": problem.get("id"),
                "candidates": [], "artifacts": []}

    def design(self, request: dict[str, Any], historical_evidence: dict[str, Any]) -> dict[str, Any]:
        return {"design_tier": "unavailable", "verification": "unsupported", "replay": "unsupported",
                "reason_code": "groundwork_adapter_not_installed", "selected_time": None,
                "options": [{"time": t, "state": "unavailable", "reason_code": "groundwork_adapter_not_installed"}
                            for t in request["feasible_times"]]}


def _watch_parent(lifeline: Any, ready: Any, process_group: int) -> None:
    """The parent's sole writer closes on death, including an uncatchable kill.

    This guard shares the scientific session but is independent of its leader.
    It therefore still cleans descendants if that leader exits unexpectedly.
    Neither a PID lookup nor a durable PID from an earlier run is trusted here.
    """
    try:
        if process_group <= 1 or os.getpgrp() != process_group:
            raise ResourceSetupError("parent_guard_session_mismatch")
        if lifeline.poll():
            # Readability before readiness means the sole parent writer already
            # vanished (or sent unexpected data). Never acknowledge this setup.
            return
        ready.send_bytes(b"ready")
        ready.close()
        # No payload is ever sent. EOF, a broken pipe, or unexpected bytes all
        # end the authority to execute this scientific session.
        lifeline.recv_bytes(maxlength=1)
    except (EOFError, OSError):
        pass
    finally:
        ready.close()
        lifeline.close()
        if process_group > 1 and os.getpgrp() == process_group:
            try:
                os.killpg(process_group, signal.SIGKILL)
            except ProcessLookupError:
                pass


def _child(connection: Any, lifeline: Any, adapter: ScienceAdapter, operation: str, args: tuple[Any, ...], wall: int, memory: int, result_cap: int) -> None:
    owned_session = False
    try:
        try:
            os.setsid()
            owned_session = True
        except (AttributeError, OSError) as exc:
            raise ResourceSetupError("process_session_setup_failed") from exc
        connection.send_bytes(b'{"_worker_control":"session_started"}')
        # The scientific process and its guard need neither provider nor
        # application credentials. Install limits before creating the guard so
        # it inherits the same effective resource policy as the science session.
        os.environ.clear()
        # Preserve the inherited account-wide process ceiling. RLIMIT_NPROC
        # counts this user's other processes too, so it cannot express a job
        # quota. The owned session and parent wall/output controls remain.
        apply_limits(memory_bytes=memory, cpu_seconds=wall + 1)
        context = multiprocessing.get_context("spawn")
        ready, ready_sender = context.Pipe(duplex=False)
        guard = context.Process(target=_watch_parent,
            args=(lifeline, ready_sender, os.getpid()), daemon=True)
        try:
            guard.start()
            ready_sender.close()
            if not ready.poll(5) or ready.recv_bytes(maxlength=5) != b"ready":
                raise ResourceSetupError("parent_guard_setup_failed")
        except (EOFError, OSError, RuntimeError) as exc:
            raise ResourceSetupError("parent_guard_setup_failed") from exc
        finally:
            ready.close()
            ready_sender.close()
            lifeline.close()
        result = getattr(adapter, operation)(*args)
        encoded = json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
        if len(encoded) > result_cap:
            connection.send_bytes(b'{"worker_error":"artifact_size_limit"}')
        else:
            connection.send_bytes(encoded)
    except ResourceSetupError:
        connection.send_bytes(b'{"worker_error":"scientific_worker_setup_failed"}')
    except BaseException:
        connection.send_bytes(b'{"worker_error":"scientific_worker_failed"}')
    finally:
        connection.close()
        lifeline.close()
        if owned_session:
            # send_bytes completed synchronously before this point. Clean even
            # when the worker disappears between the final send and its cleanup.
            try:
                os.killpg(os.getpid(), signal.SIGKILL)
            except ProcessLookupError:
                pass


def _kill_owned_session(process: Any) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except PermissionError:
        # Darwin reports EPERM while a self-killed session contains only
        # unreaped zombies. Reap our leader and give the OS reaper a bounded
        # chance to remove its descendants. Live or persistently denied groups
        # still fail explicitly; EPERM alone never means cleanup succeeded.
        process.join(timeout=2)
        if process.exitcode is None:
            raise
        deadline = time.monotonic() + 2
        while True:
            try:
                os.killpg(process.pid, signal.SIGKILL)
                return
            except ProcessLookupError:
                return
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.01)


def run_bounded(adapter: ScienceAdapter, operation: str, args: tuple[Any, ...], *, wall_seconds: int,
                cancelled: Callable[[], bool] = lambda: False, memory_bytes: int = 1024 * 1024 * 1024,
                result_cap: int = 4 * 1024 * 1024) -> dict[str, Any]:
    if operation not in {"investigate", "design", "review", "recheck"} or not 1 <= wall_seconds <= 300:
        raise ValueError("Unsupported scientific worker operation or limit")
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    lifeline, parent_lifeline = context.Pipe(duplex=False)
    process = context.Process(target=_child, args=(sender, lifeline, adapter, operation, args, wall_seconds, memory_bytes, result_cap))
    started = time.monotonic()
    try:
        process.start()
    except BaseException:
        receiver.close()
        sender.close()
        lifeline.close()
        parent_lifeline.close()
        process.close()
        raise
    sender.close()
    lifeline.close()
    owned_session = False
    try:
        while time.monotonic() - started < wall_seconds:
            if cancelled():
                return {"worker_error": "cancelled"}
            if receiver.poll(0.05):
                try:
                    result = json.loads(receiver.recv_bytes(maxlength=result_cap))
                except (EOFError, OSError, ValueError):
                    return {"worker_error": "scientific_worker_failed"}
                if not isinstance(result, dict):
                    return {"worker_error": "invalid_adapter_output"}
                if result == {"_worker_control": "session_started"} and not owned_session:
                    owned_session = True
                    continue
                return result
            if not process.is_alive() and not receiver.poll():
                # A child may exit immediately after the first poll while its
                # final synchronous write is already queued. Drain it first.
                return {"worker_error": "scientific_worker_failed"}
        return {"worker_error": "scientific_wall_limit"}
    finally:
        # Clean the owned process group even when its leader returned or exited:
        # descendants may still hold resources after an adapter spawns a child.
        # Closing the sole writer also lets the guard clean up if signalling
        # from this parent fails unexpectedly.
        parent_lifeline.close()
        if owned_session:
            _kill_owned_session(process)
        elif process.is_alive():
            try:
                if os.getpgid(process.pid) == process.pid:
                    _kill_owned_session(process)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
        process.join(timeout=2)
        receiver.close()
        process.close()
