"""Binding checks for a fixed-pair review with immutable native design lineage."""
from __future__ import annotations

import base64
import hashlib
import json

from .baseline_evidence import expected_baseline_anchor
from .canonical import semantic_digest
from .contracts import CandidateResult
from .workflow import DomainError

PROFILE = "counterdex.application-bundle.v1"


def _require(condition, message):
    if not condition:
        raise DomainError("binding_mismatch", message)


def _decode(packet):
    raw = base64.b64decode(packet["scientific"]["bytes_base64"], validate=True)
    _require(hashlib.sha256(raw).hexdigest() == packet["scientific"]["sha256"], "Scientific bytes differ from their retained hash.")
    return json.loads(raw)


def _summaries(checked):
    return [CandidateResult.model_validate({key: row[key] for key in CandidateResult.model_fields}).model_dump(mode="json")
            for row in checked]


def _faithful(result):
    fresh = result["native_replay"]
    checked = fresh["candidate_results"]
    _require(len(checked) == 2 and len({row["candidate_id"] for row in checked}) == 2,
             "Follow-up must retain facts for both original candidates.")
    outcome = fresh["outcome"]
    valid = [row for row in checked if row["verification"] == "valid"]
    outside = [row for row in valid if row["is_counterexample"]]
    _require(outcome["scientific_outcome"] == ("certified_counterexample" if outside else "inconclusive")
             and outcome["reason_code"] == ("compatible_outside_witness" if outside else "selected_candidates_checked")
             and outcome["compatible_candidate_ids"] == [row["candidate_id"] for row in valid]
             and outcome["counterexample_ids"] == [row["candidate_id"] for row in outside]
             and outcome["pair_available"] == (len(valid) == 2),
             "Fixed-pair feedback cannot imply discovery completeness or whole-model exclusion.")
    _require(result.get("baseline_search") is None and result.get("candidate_results") == _summaries(checked)
             and all(result.get(key) == outcome[key] for key in ("scientific_outcome", "reason_code")),
             "Published candidate facts differ from the retained review.")
    refs = result["artifacts"]
    _require(len(refs) == 1, "Follow-up requires its original native packet.")
    candidates = result["candidates"]
    _require(len(candidates) == len(checked), "Candidate references must retain both reviewed vectors.")
    for candidate, row in zip(candidates, checked, strict=True):
        _require(candidate["id"] == row["candidate_id"] and candidate["parameter_vector"] == row["parameters"]
                 and candidate["verification"] == row["verification"]
                 and candidate["problem_id"] == result["problem_id"]
                 and candidate["problem_digest"] == result["problem_digest"]
                 and candidate["artifact_ids"] == [refs[0]["id"]],
                 "Candidate references differ from fresh fixed-pair feedback.")


def validate_followup_packet(content, anchor, *, projection, job, scenario_id, result, historical_artifact, design_request):
    """Check application identity and facts; the engine remains the mathematical checker."""
    try:
        binding = projection["binding"]
        expected = expected_baseline_anchor(projection, problem=binding["problem"], dataset=binding["dataset"],
                                            job=job, scenario_id=scenario_id)
        _require(anchor == {**expected, "artifact_sha256": hashlib.sha256(content).hexdigest()},
                 "Follow-up bytes differ from the independently retained anchor.")
        packet = json.loads(content)
        science = _decode(packet)
        _require(packet["schema_version"] == PROFILE and packet["operation"] == "review"
                 and packet["binding"] == binding and packet["history"] == historical_artifact
                 and packet["run_id"] == job["id"] and packet["scenario_id"] == scenario_id,
                 "Follow-up packet differs from the approved revision and historical design.")
        _require(science["operation"] == "fixed_candidate_review" and science["search"] is None
                 and science["exact_trials"] == [] and science["problem"] == projection["problem"]
                 and science["scenario_id"] == scenario_id
                 and science["workflow"] == {"plan_id": job["plan_id"], "approval_id": job["approval_id"],
                                            "operation_id": job["id"], "execution_id": job["id"]},
                 "Follow-up cannot substitute discovery or another approved operation.")
        historical_bytes = base64.b64decode(historical_artifact["bytes_base64"], validate=True)
        _require(hashlib.sha256(historical_bytes).hexdigest() == historical_artifact["sha256"]
                 == historical_artifact["anchors"]["artifact_sha256"], "Historical design differs from its independent hash.")
        parent = json.loads(historical_bytes)
        parent_science = _decode(parent)
        _require(parent["operation"] == "design" and parent["binding"]["request"] == design_request,
                 "Historical design must be exactly the approved source request.")
        old = parent["binding"]["application"]
        parent_anchor = {"artifact_sha256": historical_artifact["sha256"],
            "dataset_digest": old["dataset"]["digest"], "problem_digest": old["problem"]["digest"],
            "projection_digest": old["projection_digest"], "run_id": parent["run_id"],
            "scenario_id": parent["scenario_id"], "app_request_digest": semantic_digest("design-request", design_request),
            "design_digest": parent["binding"]["design_digest"]}
        _require(historical_artifact["anchors"] == parent_anchor,
                 "Historical design identity must match all separately retained anchors.")
        prior, new = old["dataset"], binding["dataset"]
        old_problem, new_problem = old["problem"], binding["problem"]
        body, before = new["body"], prior["body"]
        _require(new["id"] != prior["id"] and body["parent_id"] == prior["id"]
                 and body["origin"] == "hypothetical" and body["experiment_id"] == before["experiment_id"]
                 and body["time_origin"] == before["time_origin"]
                 and len(body["rows"]) == len(before["rows"]) + 1 and body["rows"][:-1] == before["rows"]
                 and new_problem["id"] != old_problem["id"]
                 and {k: v for k, v in new_problem["body"].items() if k not in {"dataset_id", "dataset_digest"}}
                    == {k: v for k, v in old_problem["body"].items() if k not in {"dataset_id", "dataset_digest"}},
                 "Follow-up must preserve the original history, model and claim in a new hypothetical revision.")
        row = body["rows"][-1]
        selected = parent_science["report"]["checked"]
        _require(selected["tier"] == "checked_pair_separation" and row["time"] == selected["selected_time"]
                 and row["hard_allowance"] == design_request["future_hard_allowance"]
                 and row["included"] is True and row.get("source_asset_id") is None,
                 "Follow-up must use the checked selected time and reviewed future allowance.")
        expected_pair = list(zip(design_request["candidate_ids"], design_request["candidate_vectors"], strict=True))
        _require(len(expected_pair) == 2 and len({item[0] for item in expected_pair}) == 2
                 and [(c["id"], c["parameters"]) for c in parent_science["design"]["candidates"]] == expected_pair
                 and [(c["id"], c["parameters"]) for c in science["candidates"]] == expected_pair,
                 "Follow-up must check the original ordered candidate IDs and vectors.")
        digest = semantic_digest("report", {key: value for key, value in science.items() if key != "baseline_digest"})
        fresh = result["native_replay"]
        _require(science["baseline_digest"] == fresh["baseline_digest"] == digest
                 and fresh["anchors"] == anchor and fresh["candidate_results"] == science["report"]["checked"]["candidate_results"]
                 and fresh["outcome"] == science["report"]["outcome"]
                 and fresh["historical_compatibility"] == science["report"]["checked"]["historical_compatibility"]
                 and fresh["dataset_origin"] == "hypothetical"
                 and science["report"]["execution"] == "completed" and science["report"]["failure_reason"] is None,
                 "Fresh feedback must match the retained computed evidence.")
        _require(all(c["checked_horizon"] == science["report"]["checked"]["historical_horizon"]
                     and c["observable"] == "concentration" for c in result["candidates"]),
                 "Candidate references must retain the actual checked horizon and observable.")
        _faithful(result)
        _require(followup_result_checked(result), "Follow-up result requires successful integrity, binding and fresh checking.")
    except DomainError:
        raise
    except (KeyError, TypeError, ValueError, IndexError):
        raise DomainError("binding_mismatch", "The native follow-up evidence is incomplete or inconsistent.") from None


def followup_result_checked(result):
    try:
        fresh, record = result["native_replay"], result["verification_record"]
        anchors = fresh["anchors"]
        _faithful(result)
        return (fresh["packet_profile"] == PROFILE and fresh["operation"] == "review"
            and fresh["integrity"] == "passed" and fresh["search_replayed"] is False
            and fresh["replay"] == result["replay"] == "passed"
            and fresh["verification"] == record["verification"] == result["verification"] == "valid"
            and fresh["expected_binding"] == record["expected_binding"] == result["expected_binding"] == "matches"
            and anchors["problem_digest"] == result["problem_digest"] == record["expected_problem_digest"] == record["observed_problem_digest"]
            and anchors["projection_digest"] == result["scientific_problem_digest"]
                == record["expected_scientific_problem_digest"] == record["observed_scientific_problem_digest"]
            and record["artifact_id"] == result["artifacts"][0]["id"]
            and record["artifact_sha256"] == result["artifacts"][0]["sha256"] == anchors["artifact_sha256"])
    except (DomainError, KeyError, TypeError, ValueError, IndexError):
        return False
