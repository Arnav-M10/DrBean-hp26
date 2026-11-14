"""Qualification controls use real local replay, never package-presence badges."""
import copy
from pathlib import Path
import shutil

import pytest

from bean_api.contracts import DesignResult
from bean_api.counterdex_adapter import CounterdexAdapter
from bean_api.worker import Worker
from test_counterdex_adapter import request, reviewed_history


def qualification_worker(adapter):
    worker = object.__new__(Worker)
    worker.adapter = adapter
    return worker


@pytest.fixture(scope="module")
def native_results():
    executable = shutil.which("python3.11")
    if executable is None:
        prepared = Path("/workspace/.python/cpython-3.11-linux-x86_64-gnu/bin/python3.11")
        executable = str(prepared) if prepared.exists() else None
    if executable is None:
        pytest.skip("Prepared CPython 3.11 is required for actual replay qualification controls")
    adapter = CounterdexAdapter(executable)
    history = reviewed_history()
    results = []
    for allowance in ("1/5", "3/5"):
        result = adapter.design(request(history, allowance=allowance), history)
        assert "worker_error" not in result, result
        result.pop("_native_artifacts")
        results.append(DesignResult.model_validate(result).model_dump(mode="json"))
    return adapter, results


def test_qualification_does_not_probe_after_supervised_result(native_results, monkeypatch):
    adapter, results = native_results

    def forbidden_probe(self):
        raise AssertionError("A late subprocess probe exceeds the supervised job's boundary")

    monkeypatch.setattr(CounterdexAdapter, "capabilities", forbidden_probe)
    worker = qualification_worker(adapter)
    assert [result["design_tier"] for result in results] == ["checked_pair_separation", "no_separation_established"]
    assert all(worker._checked_result_allowed(result) for result in results)


def test_package_badge_and_module_name_cannot_qualify_result():
    class PackageBadge:
        def capabilities(self):
            raise AssertionError("Global package flags must not be consulted")

    class ModuleImpostor(PackageBadge):
        __module__ = "bean_api.counterdex_adapter"

    class Subclass(CounterdexAdapter):
        pass

    result = {"native_replay": {"replay": "passed", "expected_binding": "matches"}}
    for adapter in (PackageBadge(), ModuleImpostor(), Subclass()):
        assert qualification_worker(adapter)._checked_result_allowed(result) is False


@pytest.mark.parametrize("section,key,value", [
    ("native_replay", "integrity", "failed"),
    ("native_replay", "verification", "invalid"),
    ("native_replay", "expected_binding", "not_supplied"),
    ("native_replay", "recorded_result_matches", False),
    ("native_replay", "suggestion_digest", "0" * 64),
    ("verification_record", "expected_scientific_problem_digest", "0" * 64),
    ("verification_record", "observed_scientific_problem_digest", "0" * 64),
    (None, "native_suggestion_digest", None),
    (None, "candidate_results", []),
    (None, "selected_time", "6/1"),
    (None, "design_tier", "no_separation_established"),
])
def test_qualification_rejects_swapped_or_incomplete_replay(native_results, section, key, value):
    adapter, results = native_results
    result = copy.deepcopy(results[0])
    target = result if section is None else result[section]
    target[key] = value
    assert qualification_worker(adapter)._checked_result_allowed(result) is False


def test_qualification_rejects_margin_not_established_by_replay(native_results):
    adapter, results = native_results
    result = copy.deepcopy(results[0])
    result["options"][0]["exact_margin"] = "1000/1"
    assert qualification_worker(adapter)._checked_result_allowed(result) is False
