"""Platform-aware child-process guards, with no claim of equal OS enforcement.

Darwin's RLIMIT_AS is not a reliable supported address-space limit for this
Python runtime. We deliberately omit it there instead of classifying its setup
failure as bad image/scientific input. RSS is not substituted: RLIMIT_RSS is not
a dependable hard memory guard. Wall/output limits are enforced by the parent.
"""

from __future__ import annotations

import sys
from typing import Any


class ResourceSetupError(RuntimeError):
    """A supported process guard could not be installed before executing work."""


def describe_policy(platform_name: str | None = None) -> dict[str, Any]:
    platform_name = platform_name or sys.platform
    posix = platform_name.startswith("linux") or platform_name == "darwin"
    return {
        "policy_version": "process-guards-v2",
        "platform": platform_name,
        "wall_clock": "parent_enforced",
        "output_bytes": "parent_enforced",
        "process_tree": "owned_posix_session" if posix else "unavailable",
        "address_space": "rlimit_as" if platform_name.startswith("linux") else "unavailable",
        "address_space_reason": None if platform_name.startswith("linux") else "platform_guard_not_supported",
        "cpu": "rlimit_cpu" if posix else "unavailable",
        "open_files": "rlimit_nofile" if posix else "unavailable",
        "process_count": "rlimit_nproc_per_user" if posix else "unavailable",
    }


def apply_limits(*, memory_bytes: int, cpu_seconds: int, open_files: int = 64,
                 processes: int = 32, platform_name: str | None = None,
                 resource_module: Any = None) -> dict[str, Any]:
    """Install applicable limits or explicitly fail before decoding/computation.

Only known unsupported platform guards are omitted. An unexpected failure to
set a supported guard is an infrastructure failure, never silently ignored.
The returned report records limits actually installed in this child.
"""
    if any(type(value) is not int or value <= 0 for value in (memory_bytes, cpu_seconds, open_files, processes)):
        raise ValueError("Resource bounds must be positive integers")
    report = describe_policy(platform_name)
    if report["process_tree"] == "unavailable":
        raise ResourceSetupError("platform_process_supervision_unavailable")
    if resource_module is None:
        try:
            import resource as resource_module
        except ImportError:
            raise ResourceSetupError("resource_module_unavailable") from None
    limits = [("cpu", "RLIMIT_CPU", cpu_seconds),
              ("open_files", "RLIMIT_NOFILE", open_files),
              ("process_count", "RLIMIT_NPROC", processes)]
    if report["address_space"] == "rlimit_as":
        limits.insert(0, ("address_space", "RLIMIT_AS", memory_bytes))
    for name, constant, requested in limits:
        if not hasattr(resource_module, constant):
            raise ResourceSetupError(f"{name}_guard_unavailable")
        try:
            _, existing_hard = resource_module.getrlimit(getattr(resource_module, constant))
            infinity = resource_module.RLIM_INFINITY
            admitted = requested if existing_hard == infinity else min(requested, existing_hard)
            if admitted <= 0:
                raise ValueError("Inherited hard guard admits no work")
            resource_module.setrlimit(getattr(resource_module, constant), (admitted, admitted))
        except (OSError, ValueError) as exc:
            raise ResourceSetupError(f"{name}_guard_setup_failed") from exc
        report[name + "_limit"] = admitted
    return report
