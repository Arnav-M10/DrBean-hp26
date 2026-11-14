"""Owner01 adapter seam and killable, bounded scientific process boundary.

No scientific theorem implementation is imported by this backend. The default
adapter reports unavailable. A qualified adapter is supplied explicitly by the
integration owner; a model can never select an import, path, or command.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import multiprocessing
import os
import signal
import time
from typing import Any, Callable, Protocol


class ScienceAdapter(Protocol):
    def capabilities(self) -> dict[str, Any]: ...
    def investigate(self, problem: dict[str, Any], dataset: dict[str, Any], limits: dict[str, int]) -> dict[str, Any]: ...
    def design(self, request: dict[str, Any], historical_evidence: dict[str, Any]) -> dict[str, Any]: ...


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


def _child(connection: Any, adapter: ScienceAdapter, operation: str, args: tuple[Any, ...], wall: int, memory: int, result_cap: int) -> None:
    try:
        os.setsid()
        # The scientific process needs neither provider nor application credentials.
        os.environ.clear()
        import resource
        resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
        resource.setrlimit(resource.RLIMIT_CPU, (wall + 1, wall + 1))
        resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))
        result = getattr(adapter, operation)(*args)
        encoded = json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
        if len(encoded) > result_cap:
            connection.send_bytes(b'{"worker_error":"artifact_size_limit"}')
        else:
            connection.send_bytes(encoded)
    except BaseException:
        connection.send_bytes(b'{"worker_error":"scientific_worker_failed"}')
    finally:
        connection.close()


def run_bounded(adapter: ScienceAdapter, operation: str, args: tuple[Any, ...], *, wall_seconds: int,
                cancelled: Callable[[], bool] = lambda: False, memory_bytes: int = 1024 * 1024 * 1024,
                result_cap: int = 4 * 1024 * 1024) -> dict[str, Any]:
    if operation not in {"investigate", "design"} or not 1 <= wall_seconds <= 300:
        raise ValueError("Unsupported scientific worker operation or limit")
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_child, args=(sender, adapter, operation, args, wall_seconds, memory_bytes, result_cap))
    started = time.monotonic()
    process.start()
    sender.close()
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
                return result
            if not process.is_alive():
                return {"worker_error": "scientific_worker_failed"}
        return {"worker_error": "scientific_wall_limit"}
    finally:
        if process.is_alive():
            # Target only this process's new session; never kill a shared worker group.
            try:
                if os.getpgid(process.pid) == process.pid:
                    os.killpg(process.pid, signal.SIGKILL)
                else:
                    process.kill()
            except ProcessLookupError:
                pass
        process.join(timeout=2)
        receiver.close()
        process.close()
