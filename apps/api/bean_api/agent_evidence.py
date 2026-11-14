"""Bounded authoritative facts for the controlled coordinator.

The immutable evidence record and native downloads retain full replay detail.
This projection is for reasoning about accepted results, not mathematical replay.
"""
from __future__ import annotations

from copy import deepcopy
import json

from .workflow import DomainError

FACT_BYTE_LIMIT = 12_000
FACT_FIELDS = (
    "scientific_outcome", "verification", "expected_binding", "replay", "reason_code",
    "problem_id", "problem_digest", "projection_version", "scientific_problem_digest",
    "scientific_design_digest", "native_suggestion_digest", "candidates", "candidate_results",
    "artifacts", "verification_record", "baseline_search",
)


def project_evidence_fact(record: dict) -> dict:
    """Copy typed scientific facts without duplicating native replay's exact rows.

    No candidate, status, or exact parameter is truncated to fit. Oversized core
    facts fail explicitly; the already persisted evidence remains available.
    """
    body = record["body"]
    result = body["result"]
    fact = {"id": record["id"], "evidence_digest": record["digest"],
            "fact_projection": "agent-evidence.v1", "run_id": body["run_id"],
            "scenario_id": body["scenario_id"],
            **{name: deepcopy(result[name]) for name in FACT_FIELDS if name in result}}
    encoded = json.dumps(fact, ensure_ascii=False, allow_nan=False).encode()
    if len(encoded) > FACT_BYTE_LIMIT:
        raise DomainError("agent_evidence_limit", "The complete selected scientific facts exceed the coordinator context limit; retained evidence remains available.")
    return fact
