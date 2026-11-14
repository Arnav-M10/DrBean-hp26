"""Platform-aware child-process guards, with no claim of equal OS enforcement.

Darwin's RLIMIT_AS is not a reliable supported address-space limit for this
Python runtime. We deliberately omit it there instead of classifying its setup
failure as bad image/scientific input. RSS is not substituted: RLIMIT_RSS is not
a dependable hard memory guard. Wall/output limits are enforced by the parent.

RLIMIT_NPROC is an account-wide ceiling, not a limit on an owned job tree.
Lowering it in a child can prevent all further forks by that child when the
user's existing desktop processes already exceed it. Preserve the inherited
ceiling on Linux and Darwin; owned-session cleanup is not a process-count quota.
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
        "policy_version": "process-guards-v3",
        "platform": platform_name,
        "wall_clock": "parent_enforced",
        "output_bytes": "parent_enforced",
        "process_tree": "owned_posix_session" if posix else "unavailable",
        "address_space": "rlimit_as" if platform_name.startswith("linux") else "unavailable",
        "address_space_reason": None if platform_name.startswith("linux") else "platform_guard_not_supported",
        "cpu": "rlimit_cpu" if posix else "unavailable",
        "open_files": "rlimit_nofile" if posix else "unavailable",
        "process_count": "inherited_rlimit_nproc_per_user" if posix else "unavailable",
        "process_count_reason": "account_wide_limit_not_job_quota" if posix else "platform_guard_not_supported",
        "process_count_job_quota": "unavailable",
    }


def apply_limits(*, memory_bytes: int, cpu_seconds: int, open_files: int = 64,
                 processes: int | None = None, platform_name: str | None = None,
                 resource_module: Any = None) -> dict[str, Any]:
    """Install applicable limits or explicitly fail before decoding/computation.

Only known unsupported platform guards are omitted. An unexpected failure to
set a supported guard is an infrastructure failure, never silently ignored.
The returned report distinguishes installed guards from the inherited per-user
process ceiling. ``processes`` is accepted for existing callers but never applied:
an RLIMIT_NPROC value cannot express a job quota.
"""
    bounds = (memory_bytes, cpu_seconds, open_files) + (() if processes is None else (processes,))
    if any(type(value) is not int or value <= 0 for value in bounds):
        raise ValueError("Resource bounds must be positive integers")
    report = describe_policy(platform_name)
    if report["process_tree"] == "unavailable":
        raise ResourceSetupError("platform_process_supervision_unavailable")
    if resource_module is None:
        try:
            import resource as resource_module
        except ImportError:
            raise ResourceSetupError("resource_module_unavailable") from None
    if processes is not None:
        report["process_count_requested_limit"] = processes
        report["process_count_request_applied"] = False
    if hasattr(resource_module, "RLIMIT_NPROC"):
        try:
            soft, hard = resource_module.getrlimit(resource_module.RLIMIT_NPROC)
        except (OSError, ValueError, OverflowError) as exc:
            raise ResourceSetupError("process_count_policy_inspection_failed") from exc
        report["process_count_soft_limit"] = soft
        report["process_count_hard_limit"] = hard
    else:
        report["process_count"] = "unavailable"
        report["process_count_reason"] = "resource_constant_unavailable"
    limits = [("cpu", "RLIMIT_CPU", cpu_seconds),
              ("open_files", "RLIMIT_NOFILE", open_files)]
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
        except (OSError, ValueError, OverflowError) as exc:
            raise ResourceSetupError(f"{name}_guard_setup_failed") from exc
        report[name + "_limit"] = admitted
    return report
