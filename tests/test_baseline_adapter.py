"""Real discovery controls; no fixed candidates or saved producer outputs."""
import base64
import copy
from fractions import Fraction
import hashlib
import json

import pytest

from bean_api.canonical import semantic_digest
from bean_api.contracts import ScientificResult
from test_counterdex_adapter import adapter as adapter_fixture, reviewed_history

adapter = adapter_fixture


def scope(history):
    return {"run_id": "actual_discovery_run", "scenario_id": "baseline", "workflow": history["workflow"]}


def investigate(adapter, history):
    return adapter.investigate(history["problem"], history["dataset"], {"scientific_wall_seconds": 30}, scope(history))


def rebind(history):
    history["dataset"]["digest"] = semantic_digest("dataset", history["dataset"]["body"])
    history["problem"]["body"]["dataset_digest"] = history["dataset"]["digest"]
    history["problem"]["digest"] = semantic_digest("problem", history["problem"]["body"])


def packet_and_science(result):
    packet = result["_native_artifacts"][0]
    content = base64.b64decode(packet["content_base64"], validate=True)
    wrapper = json.loads(content)
    scientific = json.loads(base64.b64decode(wrapper["scientific"]["bytes_base64"], validate=True))
    return packet, content, wrapper, scientific


def test_real_discovery_returns_exact_checked_candidates_and_portable_native_bytes(adapter):
    history = reviewed_history()
    result = investigate(adapter, history)
    assert "worker_error" not in result, result
    packet, content, wrapper, scientific = packet_and_science(result)
    public = {key: value for key, value in result.items() if not key.startswith("_")}
    ScientificResult.model_validate(public)
    assert result["scientific_outcome"] == "certified_counterexample"
    assert result["verification"] == "valid" and result["replay"] == "passed"
    assert scientific["operation"] == "bounded_discovery"
    assert scientific["search"]["attempted_count"] > 0
    assert result["baseline_search"]["exact_attempts"] > 0
    assert result["baseline_search"]["attempted_count"] == scientific["search"]["attempted_count"]
    assert wrapper["binding"]["problem"]["body"] == history["problem"]["body"]
    assert wrapper["binding"]["dataset"]["body"] == history["dataset"]["body"]
    assert wrapper["run_id"] == scope(history)["run_id"]
    assert hashlib.sha256(content).hexdigest() == packet["sha256"] == packet["anchor"]["artifact_sha256"]
    assert packet["media_type"] == "application/vnd.counterdex.native+json"
    target = history["problem"]["body"]["target"]
    assert any(Fraction(candidate["parameter_vector"]["ke"]) < Fraction(target["lower"])
               or Fraction(candidate["parameter_vector"]["ke"]) > Fraction(target["upper"])
               for candidate in result["candidates"])
    assert all(candidate["verification"] == "valid" for candidate in result["candidates"])
    fresh = adapter.replay_native(content, expected=packet["anchor"])
    assert fresh["replay"] == "passed" and fresh["search_replayed"] is False
    assert fresh["candidate_results"] == result["native_replay"]["candidate_results"]
    assert adapter.replay_native(content[:-1] + b"!", expected=packet["anchor"])["worker_error"] == "artifact_mismatch"
    changed = {**packet["anchor"], "problem_digest": "0" * 64}
    assert adapter.replay_native(content, expected=changed)["worker_error"] == "wrong_specification_binding"


def test_changed_reviewed_input_runs_new_discovery_and_preserves_its_binding(adapter):
    history = reviewed_history()
    before = investigate(adapter, history)
    changed = copy.deepcopy(history)
    changed["dataset"]["body"]["rows"][0]["concentration"] = "97/20"
    changed["dataset"]["body"]["rows"][0]["original_values"]["concentration"] = "4.85"
    rebind(changed)
    after = investigate(adapter, changed)
    assert "worker_error" not in after, after
    assert after["scientific_problem_digest"] != before["scientific_problem_digest"]
    _, _, wrapper, scientific = packet_and_science(after)
    assert wrapper["binding"]["dataset"]["body"] == changed["dataset"]["body"]
    assert scientific["problem"]["observations"][0]["value"] == "97/20"
    assert scientific["search"]["problem_digest"] == after["scientific_problem_digest"]
    assert scientific["search"]["attempted_count"] > 0


def test_no_candidate_has_honest_result_and_downloadable_unchecked_packet(adapter):
    history = reviewed_history()
    # This model has concentration zero at t=0; a positive lower measurement
    # bound there makes this search find no feasible vectors.
    history["dataset"]["body"]["rows"][0]["time"] = "0/1"
    rebind(history)
    result = investigate(adapter, history)
    assert "worker_error" not in result, result
    ScientificResult.model_validate({key: value for key, value in result.items() if not key.startswith("_")})
    assert result["scientific_outcome"] == "no_counterexample_found"
    assert result["candidates"] == []
    assert result["verification"] == "not_checked" and result["replay"] == "unsupported"
    assert result["verification_record"] is None
    packet, content, _, scientific = packet_and_science(result)
    assert scientific["search"]["attempted_count"] > 0
    fresh = adapter.replay_native(content, expected=packet["anchor"])
    assert fresh["integrity"] == "passed" and fresh["replay"] == "unsupported"


@pytest.mark.parametrize("tamper", ["anchor", "binding", "candidate", "digest"])
def test_discovery_transport_cannot_replace_reviewed_scope_or_checked_candidates(adapter, monkeypatch, tamper):
    real_run = adapter._run

    def changed_response(payload, wall_seconds):
        result = real_run(payload, wall_seconds)
        if payload["operation"] != "investigate" or "worker_error" in result:
            return result
        if tamper == "anchor":
            result["anchors"]["scenario_id"] = "another_scenario"
        elif tamper == "candidate":
            result["result"]["candidates"][0]["parameter_vector"]["A"] = "1/1"
        elif tamper == "digest":
            result["native_artifacts"][0]["sha256"] = "0" * 64
        else:
            packet = json.loads(base64.b64decode(result["native_artifacts"][0]["bytes_base64"]))
            packet["binding"]["dataset"]["body"]["time_origin"] = "another experiment start"
            content = json.dumps(packet, sort_keys=True, separators=(",", ":")).encode()
            digest = hashlib.sha256(content).hexdigest()
            result["native_artifacts"][0].update(bytes_base64=base64.b64encode(content).decode(), sha256=digest, byte_size=len(content))
            result["anchors"]["artifact_sha256"] = digest
        return result

    monkeypatch.setattr(adapter, "_run", changed_response)
    result = investigate(adapter, reviewed_history())
    assert result["worker_error"] in {"binding_mismatch", "artifact_mismatch"}
