"""Platform controls use injected OS calls; no claim these emulate a Mac kernel."""

from pathlib import Path
import json
import os
import resource
import runpy
import signal
import subprocess
import sys

import pytest

from bean_api.resource_policy import ResourceSetupError, apply_limits, describe_policy


class ResourceDouble:
    RLIMIT_AS, RLIMIT_CPU, RLIMIT_NOFILE, RLIMIT_NPROC = range(4)
    RLIM_INFINITY = -1

    def __init__(self, *, fail=None, read_fail=None, error_type=ValueError, hard=-1,
                 inherited_processes=(4000, 6000)):
        self.calls = []
        self.reads = []
        self.fail = fail
        self.read_fail = read_fail
        self.error_type = error_type
        self.hard = hard
        self.nproc_resource = self.RLIMIT_NPROC
        self.inherited_processes = inherited_processes

    def getrlimit(self, which):
        self.reads.append(which)
        if which == self.read_fail:
            raise self.error_type("runtime refuses resource inspection")
        if which == self.nproc_resource:
            return self.inherited_processes
        return (-1, self.hard)

    def setrlimit(self, which, values):
        if which == self.fail:
            raise self.error_type("unsupported resource in runtime")
        self.calls.append((which, values))


def test_darwin_does_not_attempt_broken_address_space_guard():
    os_resource = ResourceDouble(fail=ResourceDouble.RLIMIT_AS)
    report = apply_limits(memory_bytes=4096, cpu_seconds=3, platform_name="darwin", resource_module=os_resource)
    assert report["address_space"] == "unavailable"
    assert report["address_space_reason"] == "platform_guard_not_supported"
    assert {which for which, _ in os_resource.calls} == {1, 2}
    assert ResourceDouble.RLIMIT_AS not in os_resource.reads
    assert report["cpu_limit"] == 3
    assert report["wall_clock"] == "parent_enforced"


def test_linux_applies_address_space_and_supported_limits():
    os_resource = ResourceDouble()
    report = apply_limits(memory_bytes=4096, cpu_seconds=3, platform_name="linux", resource_module=os_resource)
    assert report["address_space_limit"] == 4096
    assert report["process_count"] == "inherited_rlimit_nproc_per_user"
    assert len(os_resource.calls) == 3


@pytest.mark.parametrize("platform_name", ["darwin", "linux"])
@pytest.mark.parametrize("inherited", [(4000, 6000), (2, 2), (-1, -1), (4000, -1)])
def test_account_process_ceiling_is_preserved_without_claiming_job_quota(platform_name, inherited):
    os_resource = ResourceDouble(inherited_processes=inherited)
    report = apply_limits(memory_bytes=4096, cpu_seconds=3, processes=1,
                          platform_name=platform_name, resource_module=os_resource)
    assert all(which != ResourceDouble.RLIMIT_NPROC for which, _ in os_resource.calls)
    assert report["process_count_soft_limit"] == inherited[0]
    assert report["process_count_hard_limit"] == inherited[1]
    assert report["process_count_reason"] == "account_wide_limit_not_job_quota"
    assert report["process_count_job_quota"] == "unavailable"
    assert report["process_count_requested_limit"] == 1
    assert report["process_count_request_applied"] is False
    assert "process_count_limit" not in report


def test_inherited_stricter_hard_limits_are_not_increased():
    os_resource = ResourceDouble(hard=2)
    report = apply_limits(memory_bytes=4096, cpu_seconds=3, platform_name="linux", resource_module=os_resource)
    assert all(values == (2, 2) for _, values in os_resource.calls)
    assert report["cpu_limit"] == 2
    assert report["process_count_soft_limit"] == 4000
    assert report["process_count_hard_limit"] == 6000


@pytest.mark.parametrize("error_type", [OSError, ValueError, OverflowError])
@pytest.mark.parametrize("operation", ["read", "set"])
def test_supported_guard_setup_failure_stops_before_work(error_type, operation):
    failures = {"fail" if operation == "set" else "read_fail": ResourceDouble.RLIMIT_CPU}
    os_resource = ResourceDouble(error_type=error_type, **failures)
    with pytest.raises(ResourceSetupError, match="cpu_guard_setup_failed"):
        apply_limits(memory_bytes=4096, cpu_seconds=3, platform_name="darwin", resource_module=os_resource)
    assert os_resource.calls == []


@pytest.mark.parametrize("error_type", [OSError, ValueError, OverflowError])
def test_account_process_policy_inspection_failure_is_explicit(error_type):
    os_resource = ResourceDouble(read_fail=ResourceDouble.RLIMIT_NPROC, error_type=error_type)
    with pytest.raises(ResourceSetupError, match="process_count_policy_inspection_failed"):
        apply_limits(memory_bytes=4096, cpu_seconds=3, platform_name="darwin", resource_module=os_resource)
    assert os_resource.calls == []


def test_absent_account_process_ceiling_is_disclosed(monkeypatch):
    os_resource = ResourceDouble()
    monkeypatch.delattr(ResourceDouble, "RLIMIT_NPROC")
    report = apply_limits(memory_bytes=4096, cpu_seconds=3, platform_name="darwin", resource_module=os_resource)
    assert report["process_count"] == "unavailable"
    assert report["process_count_reason"] == "resource_constant_unavailable"
    assert report["process_count_job_quota"] == "unavailable"
    assert "process_count_soft_limit" not in report
    assert {which for which, _ in os_resource.calls} == {1, 2}


@pytest.mark.parametrize("platform_name,constant,name", [
    ("linux", "RLIMIT_AS", "address_space"),
    ("darwin", "RLIMIT_CPU", "cpu"),
    ("darwin", "RLIMIT_NOFILE", "open_files"),
])
def test_absent_required_guard_fails_explicitly(monkeypatch, platform_name, constant, name):
    os_resource = ResourceDouble()
    monkeypatch.delattr(ResourceDouble, constant)
    with pytest.raises(ResourceSetupError, match=f"{name}_guard_unavailable"):
        apply_limits(memory_bytes=4096, cpu_seconds=3, platform_name=platform_name, resource_module=os_resource)


def test_unsupported_process_supervision_is_explicit():
    assert describe_policy("win32")["process_tree"] == "unavailable"
    with pytest.raises(ResourceSetupError, match="platform_process_supervision_unavailable"):
        apply_limits(memory_bytes=4096, cpu_seconds=3, platform_name="win32", resource_module=ResourceDouble())


def test_missing_resource_module_is_explicit(monkeypatch):
    monkeypatch.setitem(sys.modules, "resource", None)
    with pytest.raises(ResourceSetupError, match="resource_module_unavailable"):
        apply_limits(memory_bytes=4096, cpu_seconds=3, platform_name="darwin")


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


@pytest.mark.skipif(sys.platform not in {"linux", "darwin"}, reason="POSIX resource policy required")
@pytest.mark.parametrize("interpreter", ["backend", "prepared_engine"])
def test_owned_limited_child_can_launch_interpreter_without_lowering_account_ceiling(interpreter):
    executable = sys.executable if interpreter == "backend" else os.getenv("BEAN_COUNTERDEX_PYTHON")
    if not executable:
        pytest.skip("Set BEAN_COUNTERDEX_PYTHON to test the prepared engine interpreter")
    # All real rlimit changes occur only in this owned, killable child. The host
    # pytest/agent process never installs limits, and the engine does no science.
    script = """
import json
import resource
import subprocess
import sys
from bean_api.resource_policy import apply_limits

before = resource.getrlimit(resource.RLIMIT_NPROC)
report = apply_limits(memory_bytes=512 * 1024 * 1024, cpu_seconds=5, processes=1)
after = resource.getrlimit(resource.RLIMIT_NPROC)
engine = subprocess.run([sys.argv[1], "-I", "-c", "import sys; print(sys.version_info.major)"],
                        capture_output=True, text=True, check=True, timeout=5)
print(json.dumps({"before": before, "after": after, "policy": report, "engine": engine.stdout.strip()}))
"""
    environment = {"PATH": os.defpath, "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1",
                   "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "apps/api")}
    child = subprocess.Popen([sys.executable, "-c", script, executable], start_new_session=True,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=environment)
    try:
        stdout, stderr = child.communicate(timeout=10)
        assert child.returncode == 0, stderr
        result = json.loads(stdout)
        assert result["before"] == result["after"]
        assert result["policy"]["process_count_soft_limit"] == result["before"][0]
        assert result["policy"]["process_count_hard_limit"] == result["before"][1]
        assert result["policy"]["process_count_request_applied"] is False
        assert result["engine"] == "3"
    finally:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait(timeout=5)
        child.stdout.close()
        child.stderr.close()
