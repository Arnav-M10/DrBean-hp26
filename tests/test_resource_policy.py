"""Platform controls use injected OS calls; no claim these emulate a Mac kernel."""

from pathlib import Path
import resource
import runpy

import pytest

from bean_api.resource_policy import ResourceSetupError, apply_limits, describe_policy


class ResourceDouble:
    RLIMIT_AS, RLIMIT_CPU, RLIMIT_NOFILE, RLIMIT_NPROC = range(4)
    RLIM_INFINITY = -1

    def __init__(self, *, fail=None, hard=-1):
        self.calls = []
        self.fail = fail
        self.hard = hard

    def getrlimit(self, which):
        return (-1, self.hard)

    def setrlimit(self, which, values):
        if which == self.fail:
            raise ValueError("unsupported resource in runtime")
        self.calls.append((which, values))


def test_darwin_does_not_attempt_broken_address_space_guard():
    os_resource = ResourceDouble(fail=ResourceDouble.RLIMIT_AS)
    report = apply_limits(memory_bytes=4096, cpu_seconds=3, platform_name="darwin", resource_module=os_resource)
    assert report["address_space"] == "unavailable"
    assert report["address_space_reason"] == "platform_guard_not_supported"
    assert {which for which, _ in os_resource.calls} == {1, 2, 3}
    assert report["cpu_limit"] == 3
    assert report["wall_clock"] == "parent_enforced"


def test_linux_applies_address_space_and_supported_limits():
    os_resource = ResourceDouble()
    report = apply_limits(memory_bytes=4096, cpu_seconds=3, platform_name="linux", resource_module=os_resource)
    assert report["address_space_limit"] == 4096
    assert report["process_count"] == "rlimit_nproc_per_user"
    assert len(os_resource.calls) == 4


def test_inherited_stricter_hard_limits_are_not_increased():
    os_resource = ResourceDouble(hard=2)
    report = apply_limits(memory_bytes=4096, cpu_seconds=3, platform_name="linux", resource_module=os_resource)
    assert all(values == (2, 2) for _, values in os_resource.calls)
    assert report["cpu_limit"] == 2


def test_supported_guard_setup_failure_stops_before_work():
    os_resource = ResourceDouble(fail=ResourceDouble.RLIMIT_CPU)
    with pytest.raises(ResourceSetupError, match="cpu_guard_setup_failed"):
        apply_limits(memory_bytes=4096, cpu_seconds=3, platform_name="darwin", resource_module=os_resource)
    assert os_resource.calls == []


def test_unsupported_process_supervision_is_explicit():
    assert describe_policy("win32")["process_tree"] == "unavailable"
    with pytest.raises(ResourceSetupError, match="platform_process_supervision_unavailable"):
        apply_limits(memory_bytes=4096, cpu_seconds=3, platform_name="win32", resource_module=ResourceDouble())


def test_decoder_setup_failure_is_not_malformed_image(monkeypatch, capsys):
    decoder = Path(__file__).resolve().parents[1] / "apps/api/bean_api/_image_decode.py"
    monkeypatch.syspath_prepend(str(decoder.parent))
    def denied(*args):
        raise ValueError("runtime refuses guard")
    monkeypatch.setattr(resource, "setrlimit", denied)
    with pytest.raises(SystemExit) as stopped:
        runpy.run_path(str(decoder), run_name="__main__")
    assert stopped.value.code == 1
    assert capsys.readouterr().err.strip() == "decoder_setup_failed"
