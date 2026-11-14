"""Immutable report annotations and deterministic summaries of retained science.

These helpers never call a model, dispatch science or infer scientific success
from execution, integrity or replay. Commentary is separately labelled and checked
against the same complete facts used by the graph before it reaches persistence.
"""
from __future__ import annotations

import re

from .contracts import GroundedExplanation
from .coordinator import CoordinatorFailure, _safe_fact, _validate_explanation
from .workflow import DomainError


def validated_commentary(commentary, evidence, mode):
    if commentary is None:
        return None
    authorship = "model_commentary" if mode == "live" else "controlled_commentary"
    if (not isinstance(commentary, dict)
            or set(commentary) != {*GroundedExplanation.model_fields, "authorship", "scientific_authority"}
            or commentary.get("authorship") != authorship
            or commentary.get("scientific_authority") is not False):
        raise DomainError("research_commentary_invalid", "Commentary must retain its non-scientific authorship and complete validated shape.", 422)
    try:
        # Local import avoids making the authority port depend on graph building.
        from .research_integration import _evidence_fact
        explanation = GroundedExplanation.model_validate({key: commentary[key] for key in GroundedExplanation.model_fields})
        if explanation.fact_ids != [item["id"] for item in evidence]:
            raise ValueError("Commentary must reference the complete ordered evidence snapshot")
        facts = {item["id"]: _safe_fact(_evidence_fact(item, item["id"], item["workspace_id"])) for item in evidence}
        _validate_explanation(explanation, facts)
    except (ValueError, TypeError, KeyError, CoordinatorFailure) as error:
        raise DomainError("research_commentary_invalid", "The explanation or next-action references do not match the retained scientific evidence.", 422) from error
    return {**explanation.model_dump(mode="json"), "scientific_authority": False, "authorship": authorship}


def deterministic_summary(evidence):
    rows = []
    for item in evidence:
        result = item["body"].get("result", item["body"])
        row = {"evidence_id": item["id"], "evidence_digest": item["digest"], "kind": item["kind"]}
        for key in ("scientific_outcome", "outcome", "verification", "expected_binding"):
            if key in result:
                row[key] = result[key]
        replay = result.get("native_replay")
        if isinstance(replay, dict):
            row["native_replay"] = {key: replay[key] for key in ("replay", "integrity", "verification", "expected_binding") if key in replay}
        rows.append(row)
    return {"authorship": "deterministic_backend", "scientific_authority": False,
            "text": "Retained scientific results are available below with their original outcome and checking states. Model commentary is separate. No counterexample found does not prove a claim; replay does not strengthen a scientific conclusion.",
            "results": rows}


def failure_reference(code):
    return {"code": code if isinstance(code, str) and re.fullmatch(r"[a-z0-9_]{1,128}", code) else "research_runtime_failure"}
