"""Actual scientific facts fit the coordinator without dropping candidate truth."""
from copy import deepcopy
import json

import pytest

from bean_api.agent_evidence import project_evidence_fact
from bean_api.contracts import ScientificResult
from bean_api.coordinator import _safe_fact
from bean_api.workflow import DomainError, _digest
import test_counterdex_adapter as native_tests
from test_baseline_adapter import investigate, rebind

adapter = native_tests.adapter


def evidence(result):
    body = {"run_id": "approved_run", "scenario_id": "baseline", "result": result}
    return {"id": "evidence_actual", "digest": _digest("evidence", body), "body": body}


def test_real_replicates_fit_coordinator_without_discarding_scientific_facts(adapter):
    history = native_tests.reviewed_history()
    for index in range(2):
        row = deepcopy(history["dataset"]["body"]["rows"][0])
        row["id"] = f"replicate_{index}"
        history["dataset"]["body"]["rows"].append(row)
    rebind(history)
    computed = investigate(adapter, history)
    assert "worker_error" not in computed, computed
    public = ScientificResult.model_validate({k: v for k, v in computed.items() if not k.startswith("_")}).model_dump(mode="json")
    record = evidence(public)
    before = deepcopy(record)
    assert len(json.dumps({"id": record["id"], **public}).encode()) > 12_000
    fact = project_evidence_fact(record)
    assert _safe_fact(fact) == fact
    assert fact["scientific_outcome"] == "certified_counterexample"
    assert fact["evidence_digest"] == record["digest"]
    assert fact["run_id"] == record["body"]["run_id"]
    for name in ("candidates", "candidate_results", "verification_record", "artifacts", "baseline_search"):
        assert fact[name] == public[name]
    for name in ("verification", "expected_binding", "replay", "reason_code", "scientific_problem_digest"):
        assert fact[name] == public[name]
    assert "native_replay" not in fact and record == before
    fact["candidates"][0]["parameter_vector"]["A"] = "0/1"
    assert record == before


def test_projection_preserves_exclusions_and_unresolved_rows_without_upgrading_axes():
    public = {"problem_id": "problem", "scientific_outcome": "inconclusive",
        "verification": "valid", "expected_binding": "matches", "replay": "passed",
        "reason_code": "selected_candidates_checked", "candidate_results": [
            {"candidate_id": "a", "verification": "invalid", "violating_observation_ids": ["new_row"]},
            {"candidate_id": "b", "verification": "inconclusive", "unresolved_observation_ids": ["new_row"]}],
        "native_replay": {"large_exact_detail": "x" * 20_000}}
    fact = project_evidence_fact(evidence(public))
    assert fact["candidate_results"] == public["candidate_results"]
    assert fact["scientific_outcome"] == "inconclusive"
    assert fact["verification"] == "valid"


def test_projection_rejects_oversized_core_facts_instead_of_silently_truncating():
    record = evidence({"candidate_results": [{"candidate_id": "a", "violating_observation_ids": ["x" * 128] * 128}]})
    before = deepcopy(record)
    with pytest.raises(DomainError) as error:
        project_evidence_fact(record)
    assert error.value.code == "agent_evidence_limit"
    assert record == before
