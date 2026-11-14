#!/usr/bin/env python3
"""Regenerate frontend JSON Schemas and synthetic wire examples from Python DTOs."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from bean_api.canonical import canonical_bytes, semantic_digest  # noqa: E402
from bean_api.contracts import (  # noqa: E402
    CONTRACT_VERSION, POLICY_VERSION, PUBLIC_SCHEMAS, ApiError, DatasetBody,
    DesignPlanBody, DesignRequestBody, PlanBody, ProblemBody,
)
from bean_api.conversation import (  # noqa: E402
    AssistantOutput, AssistantProposalRecord, AssistantProposalRecordBody,
    AssistantResponseRecordBody, DesignDraft, ObservationDraft,
)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    destination = ROOT / "shared" / "contracts" / CONTRACT_VERSION
    schemas = {**PUBLIC_SCHEMAS, **{model.__name__: model for model in (
        AssistantOutput, AssistantProposalRecord, AssistantProposalRecordBody,
        AssistantResponseRecordBody, DesignDraft, ObservationDraft,
    )}}
    for name, model in sorted(schemas.items()):
        schema = model.model_json_schema()
        schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        schema["$id"] = f"urn:dr-bean:{CONTRACT_VERSION}:{name}"
        write_json(destination / f"{name}.schema.json", schema)
    write_json(destination / "manifest.json", {
        "contract_version": CONTRACT_VERSION,
        "operational_policy": POLICY_VERSION,
        "schemas": [f"{name}.schema.json" for name in sorted(schemas)],
        "identity_authority": "server",
        "generator": "scripts/export_contracts.py",
        "note": "JSON Schema validates structure. The server also enforces exact arithmetic, ownership, source locators, and transition invariants.",
    })
    dataset = DatasetBody.model_validate({
        "experiment_id": "synthetic_experiment", "time_origin": "Elapsed hours from this synthetic experiment's declared t=0",
        "origin": "synthetic", "change_reason": "Synthetic transcription oracle; no scientific result is asserted",
        "rows": [
            {"id": f"row_{index + 1}", "time": time, "concentration": value, "hard_allowance": "1/2", "included": True,
             "original_values": {"time": original_time, "concentration": original_value, "hard_allowance": "0.50"}}
            for index, (time, value, original_time, original_value) in enumerate([
                ("1/4", "24/5", "0.25", "4.80"), ("1/2", "36/5", "0.5", "7.20"),
                ("1/1", "8/1", "1", "8.00"), ("2/1", "34/5", "2", "6.80"), ("4/1", "57/10", "4", "5.70"),
            ])
        ],
    })
    problem = ProblemBody.model_validate({
        "dataset_id": "synthetic_dataset", "dataset_digest": semantic_digest("dataset", dataset),
        "domain": {"A": {"lower": "1/1", "upper": "100/1"}, "ke": {"lower": "1/100", "upper": "1/1"}, "ka": {"lower": "2/1", "upper": "10/1"}},
        "target": {"lower": "1/10", "upper": "17/100"},
    })
    plan = PlanBody.model_validate({
        "problem_id": "synthetic_problem", "problem_digest": semantic_digest("problem", problem),
        "dataset_id": "synthetic_dataset",
        "scenarios": [{"id": "baseline", "problem_id": "synthetic_problem", "problem_digest": semantic_digest("problem", problem), "kind": "baseline", "label": "Synthetic baseline preview"}],
        "budget": {"provider_turns": 0, "tool_calls": 2, "scientific_reservations": 1, "wall_seconds": 120, "scientific_wall_seconds": 120},
    })
    design = DesignRequestBody.model_validate({
        "historical_run_id": "synthetic_run", "scenario_id": "baseline", "problem_id": "synthetic_problem", "problem_digest": semantic_digest("problem", problem),
        "candidate_ids": ["synthetic_candidate_a", "synthetic_candidate_b"],
        "candidate_vectors": [{"A": "10/1", "ke": "1/10", "ka": "2/1"}, {"A": "12/1", "ke": "1/5", "ka": "3/1"}],
        "feasible_times": ["6/1", "8/1"], "future_hard_allowance": "1/5",
    })
    design_plan = DesignPlanBody(request=design, request_digest=semantic_digest("design-request", design))
    fixtures = {
        "synthetic": True,
        "note": "Schema/transcription examples only. Candidate vectors are invented, unchecked, and do not assert compatibility or separation. Replace envelope IDs through real create responses.",
        "dataset": dataset.model_dump(mode="json"), "problem": problem.model_dump(mode="json"),
        "plan": plan.model_dump(mode="json"), "design_request": design.model_dump(mode="json"),
        "design_plan": design_plan.model_dump(mode="json"),
        "digests": {"dataset": semantic_digest("dataset", dataset), "problem": semantic_digest("problem", problem), "plan": semantic_digest("plan", plan), "design-request": semantic_digest("design-request", design)},
    }
    write_json(destination / "fixtures" / "synthetic-workflow.json", fixtures)

    # Additive strict-profile example. Do not rewrite the legacy fixture's
    # historical identities when introducing newly reviewed scientific scope.
    reviewed_problem = ProblemBody.model_validate({**problem.model_dump(mode="json"), "domain": {
        "A": {"lower": "1/1000", "upper": "30/1"},
        "ke": {"lower": "3/200", "upper": "7/20"},
        "ka": {"lower": "2/5", "upper": "8/1"}}})
    reviewed_digest = semantic_digest("problem", reviewed_problem)
    reviewed_plan = PlanBody.model_validate({**plan.model_dump(mode="json"), "problem_digest": reviewed_digest,
        "scientific_profile": "counterdex.v1", "objective": {
            "question": "Do the reviewed observations admit a candidate outside the closed ke claim?",
            "success_criterion": "Retain exact checked evidence or an explicit unresolved outcome; never infer a universal claim from a pair."},
        "scenarios": [{"id": "baseline", "kind": "baseline", "label": "Reviewed synthetic baseline",
            "problem_id": "synthetic_problem", "problem_digest": reviewed_digest}]})
    reviewed_design = DesignRequestBody.model_validate({**design.model_dump(mode="json"), "problem_digest": reviewed_digest,
        "scientific_profile": "counterdex.v1", "requested_tier": "checked_pair_separation",
        "allowance_origin": {"kind": "hypothetical", "description": "Team-selected future hard bound, requiring explicit human review; not extracted from the source image."},
        "maximum_horizon": "8/1", "allow_construction": True, "allow_continuation": True,
        "source_artifact_ids": ["synthetic_native_artifact"]})
    write_json(destination / "fixtures" / "counterdex-reviewed-scope.json", {
        "synthetic": True, "scientific_result_asserted": False,
        "note": "Schema-only preview with reviewed assumptions. Pair vectors are invented placeholders; replace them and all IDs with immutable real baseline output. This fixture grants no approval or verification.",
        "dataset": dataset.model_dump(mode="json"), "problem": reviewed_problem.model_dump(mode="json"),
        "plan": reviewed_plan.model_dump(mode="json"), "design_request": reviewed_design.model_dump(mode="json"),
        "digests": {"dataset": semantic_digest("dataset", dataset), "problem": reviewed_digest,
            "plan": semantic_digest("plan", reviewed_plan), "design-request": semantic_digest("design-request", reviewed_design)}})

    # Literal expected bytes make escaping/Unicode controls reviewable separately
    # from the implementation under test. No user or provider content is included.
    canonical_cases = [
        ("unicode_and_controls", {"z": "line\n\t\b\f\r\u0001\"\\/", "a": "é😀\u2028\u2029"}, '{"a":"é😀\u2028\u2029","z":"line\\n\\t\\b\\f\\r\\u0001\\\"\\\\/"}'),
        ("ordered_array", {"rows": ["2/1", "1/1"], "counter": 9007199254740991, "included": True, "missing": None}, '{"counter":9007199254740991,"included":true,"missing":null,"rows":["2/1","1/1"]}'),
        ("rational_text", {"value": "123456789012345678901234567890123456789/7", "zero": "0/1"}, '{"value":"123456789012345678901234567890123456789/7","zero":"0/1"}'),
    ]
    golden = []
    for name, value, expected in canonical_cases:
        expected_bytes = expected.encode("utf-8")
        if canonical_bytes(value) != expected_bytes:
            raise RuntimeError(f"Golden canonical byte mismatch: {name}")
        golden.append({"name": name, "value": value, "canonical_utf8_hex": expected_bytes.hex(), "kind": "report", "semantic_sha256": hashlib.sha256(b"dr-bean:report:v1\n" + expected_bytes).hexdigest()})
    write_json(destination / "fixtures" / "canonical-golden.json", golden)
    write_json(destination / "fixtures" / "admission-golden.json", {
        "version": "db-sc-1-admission.v1",
        "limits": {"canonical_json_bytes": 1048576, "http_json_bytes_default": 262144,
            "nested_levels": 32, "rational_digits_per_component": 256, "counter_maximum": 9007199254740991},
        "rational_cases": [{"value": value, "accepted": accepted} for value, accepted in [
            ("1/1", True), ("1/1\n", False), ("-0/1", False), ("0/1", True),
            ("1" * 256 + "/1", True), ("1" * 257 + "/1", False)]],
        "json_cases": [{"raw": raw, "accepted": accepted} for raw, accepted in [
            ('{"counter":-0}', False), ('{"counter":0}', True),
            ("[" * 32 + "0" + "]" * 32, True), ("[" * 33 + "0" + "]" * 33, False)]],
        "byte_cases": [
            {"raw": '{"x":"é"}', "max_bytes": 10, "accepted": True},
            {"raw": '{"x":"é"}', "max_bytes": 9, "accepted": False}],
        "byte_note": "Limits count encoded UTF-8 bytes, not characters. The compact byte controls use an explicit test limit; production default limits above are independently enforced by canonical parsing and HTTP admission.",
        "engine_note": "Counterdex projection adds stricter exact rational bit, row and domain admission; application admission does not claim engine qualification."})

    errors = [
        (401, "unauthorized", "Authentication is required", False, None, []),
        (422, "invalid_fields", "Scientific values must be canonical rational strings", False, None, ["/rows/0/time"]),
        (409, "stale_revision", "The reviewed revision changed; inspect the current revision", False, "synthetic_new_revision", []),
        (409, "idempotency_conflict", "This operation key is already bound to a different request", False, None, []),
        (503, "capability_unavailable", "The requested engine capability is not qualified in this environment", False, None, []),
        (503, "provider_timeout", "The provider outcome is unknown; existing reviewed data are unchanged", True, None, []),
    ]
    write_json(destination / "fixtures" / "http-exchanges.json", {
        "synthetic": True,
        "success": {"request": {"method": "POST", "path": "/api/bean/v1/plans/synthetic_plan/runs", "headers": {"Idempotency-Key": "synthetic_operation_key"}, "body": {"approval_id": "synthetic_approval", "expected_plan_digest": semantic_digest("plan", plan)}}, "response": {"status": 202, "body": {"id": "synthetic_run", "status": "queued", "request_id": "synthetic_request"}}, "retry_behavior": "An identical accepted request returns the same run; a changed body under this key conflicts. Fresh keys cannot rerun an already reserved plan."},
        "errors": [{"status": status, "body": ApiError(code=code, message=message, retryable=retryable, current_revision_id=revision, field_paths=paths, request_id="synthetic_request").model_dump(mode="json")} for status, code, message, retryable, revision, paths in errors],
    })
    print(f"Exported {len(schemas)} shared schemas and five fixture files to {destination}")


if __name__ == "__main__":
    main()
