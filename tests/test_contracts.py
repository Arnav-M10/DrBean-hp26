from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from bean_api.canonical import canonical_bytes, parse_decimal, parse_json_strict, semantic_digest, validate_rational
from bean_api.contracts import ApprovalRequest, DatasetBody, DesignRequestBody, DesignResult, IntakeProposalBody, IntakeReviewRequest, PlanBody, ProblemBody, ScientificResult

FIXTURES = Path(__file__).resolve().parents[1] / "shared" / "contracts" / "DB-SC-1" / "fixtures"


@pytest.mark.parametrize("value", [0, 0.5, True, "0.5", "2/4", "-0/1", "+1/1", "01/1", "1/01", "1/0", "0/2", "1/-2", "1" * 257 + "/1"])
def test_noncanonical_rationals_are_rejected(value):
    with pytest.raises(ValueError):
        validate_rational(value)


@pytest.mark.parametrize(("value", "expected"), [("0.05", "1/20"), ("0.50", "1/2"), ("4.80", "24/5"), ("1e-3", "1/1000"), ("-0.0", "0/1"), ("+.25", "1/4")])
def test_decimal_spelling_is_converted_exactly(value, expected):
    assert parse_decimal(value) == expected


@pytest.mark.parametrize("value", [0.05, True, "NaN", "Infinity", "1e129", "1e-129", "1e999999999999999999999", "=1+1", " 0.5 ", "1/2"])
def test_unsafe_decimal_spellings_are_not_guessed(value):
    with pytest.raises(ValueError):
        parse_decimal(value)


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"x":0.5}', b'{"x":1e0}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":-0}', b'{"x":-1}', b'{"x":9007199254740992}', b'{"x":"\xff"}', b'{"x":"\\ud800"}', b'{"x":"unescaped\n"}', b'{"\xc3\xa9":1}'])
def test_strict_json_rejects_ambiguous_or_lossy_inputs(raw):
    with pytest.raises(ValueError):
        parse_json_strict(raw)


def test_json_depth_and_size_are_bounded():
    with pytest.raises(ValueError):
        parse_json_strict("[" * 33 + "0" + "]" * 33)
    with pytest.raises(ValueError):
        parse_json_strict(b'{"x":"123"}', max_bytes=5)


def test_golden_bytes_preserve_unicode_escaping_and_array_order():
    for fixture in json.loads((FIXTURES / "canonical-golden.json").read_text()):
        assert canonical_bytes(fixture["value"]).hex() == fixture["canonical_utf8_hex"]
        assert semantic_digest(fixture["kind"], fixture["value"]) == fixture["semantic_sha256"]
    assert canonical_bytes({"x": "é"}) != canonical_bytes({"x": "e\u0301"})
    assert semantic_digest("dataset", {"rows": ["1/1", "2/1"]}) != semantic_digest("dataset", {"rows": ["2/1", "1/1"]})
    assert parse_json_strict(b'{"x":"\\ud83d\\ude00"}') == {"x": "😀"}


def test_unknown_identity_kinds_are_rejected():
    with pytest.raises(ValueError):
        semantic_digest("approval", {"accepted": True})


@pytest.fixture
def workflow():
    return json.loads((FIXTURES / "synthetic-workflow.json").read_text())


def test_synthetic_contract_fixtures_round_trip(workflow):
    for key, cls, kind in [("dataset", DatasetBody, "dataset"), ("problem", ProblemBody, "problem"), ("plan", PlanBody, "plan"), ("design_request", DesignRequestBody, "design-request")]:
        entity = cls.model_validate(workflow[key])
        assert semantic_digest(kind, entity) == workflow["digests"][kind]


def test_excluded_rows_and_heterogeneous_allowances_keep_identity(workflow):
    body = workflow["dataset"]
    original_digest = semantic_digest("dataset", DatasetBody.model_validate(body))
    body["rows"][1]["included"] = False
    body["rows"][1]["hard_allowance"] = "1/10"
    dataset = DatasetBody.model_validate(body)
    assert len(dataset.rows) == 5
    assert dataset.rows[1].included is False
    assert dataset.rows[0].hard_allowance == "1/2"
    assert dataset.rows[1].hard_allowance == "1/10"
    assert semantic_digest("dataset", dataset) != original_digest
    body["rows"][1]["time"] = 0.5
    with pytest.raises(ValidationError):
        DatasetBody.model_validate(body)


def test_unknown_schema_fields_and_boolean_scientific_scalars_fail(workflow):
    body = workflow["problem"]
    body["approved"] = True
    with pytest.raises(ValidationError):
        ProblemBody.model_validate(body)
    del body["approved"]
    body["target"]["lower"] = True
    with pytest.raises(ValidationError):
        ProblemBody.model_validate(body)


def test_plan_cannot_rebind_baseline_or_expand_policy(workflow):
    body = workflow["plan"]
    body["scenarios"][0]["problem_digest"] = "f" * 64
    with pytest.raises(ValidationError):
        PlanBody.model_validate(body)
    body["scenarios"][0]["problem_digest"] = body["problem_digest"]
    body["budget"]["provider_turns"] = 5
    with pytest.raises(ValidationError):
        PlanBody.model_validate(body)


def test_design_requires_separate_positive_future_allowance(workflow):
    body = workflow["design_request"]
    del body["future_hard_allowance"]
    with pytest.raises(ValidationError):
        DesignRequestBody.model_validate(body)
    body["future_hard_allowance"] = "0/1"
    with pytest.raises(ValidationError):
        DesignRequestBody.model_validate(body)


def test_approval_requires_json_true_instead_of_truthy_value():
    for value in [False, 1, "yes", "true"]:
        with pytest.raises(ValidationError):
            ApprovalRequest(expected_plan_digest="0" * 64, expected_current_revision_id="revision", accepted=value)


def test_visual_transcription_remains_unaccepted_and_source_bound():
    proposal = {
        "source_asset_id": "source_a", "source_digest": "0" * 64,
        "fields": [{"field_path": "/rows/0/hard_allowance", "original_value": "0.05", "candidate_exact": "1/20", "source_asset_id": "source_a", "locator": {"label": "row 1 allowance", "excerpt": "0.05"}}],
    }
    parsed = IntakeProposalBody.model_validate(proposal)
    assert parsed.fields[0].grounding == "unreviewed_visual"
    assert "accepted" not in parsed.model_dump()
    proposal["fields"][0]["source_asset_id"] = "source_b"
    with pytest.raises(ValidationError):
        IntakeProposalBody.model_validate(proposal)


def test_row_diagnostic_can_be_explicitly_resolved():
    review = IntakeReviewRequest.model_validate({
        "expected_proposal_digest": "0" * 64,
        "reviewed_fields": [{"field_path": "rows[0].time", "value": "1/4", "origin": "corrected_transcription", "correction_reason": "Read decimal against the original source"}],
        "resolved_diagnostics": ["source_ambiguity:rows[0].time"],
    })
    assert review.resolved_diagnostics == ["source_ambiguity:rows[0].time"]


def test_valid_flag_cannot_create_a_verification_record():
    result = {"scientific_outcome": "certified_counterexample", "verification": "valid", "expected_binding": "matches", "replay": "not_run", "reason_code": "fixture_only", "problem_id": "problem_a"}
    with pytest.raises(ValidationError):
        ScientificResult.model_validate(result)
    result.update(scientific_outcome="unsupported", verification="unsupported", expected_binding="not_supplied")
    assert ScientificResult.model_validate(result).scientific_outcome == "unsupported"


def test_zero_margin_never_establishes_pair_separation():
    result = {
        "design_tier": "checked_pair_separation", "verification": "valid", "replay": "passed",
        "reason_code": "fixture_only", "selected_time": "6/1", "algorithm": "exact_margin_v1",
        "candidate_ids": ["candidate_a", "candidate_b"], "future_hard_allowance": "1/5",
        "options": [{"time": "6/1", "state": "evaluated", "reason_code": "fixture_only", "exact_margin": "0/1"}],
        "artifacts": [{"id": "artifact_a", "sha256": "a" * 64, "byte_size": 1, "media_type": "application/json"}],
        "verification_record": {"checker_name": "fixture_checker", "checker_version": "fixture_only", "artifact_id": "artifact_a", "artifact_sha256": "a" * 64, "proposition": "Synthetic schema control, no real verification", "verification": "valid", "expected_binding": "matches", "expected_problem_digest": "b" * 64, "observed_problem_digest": "b" * 64},
    }
    with pytest.raises(ValidationError):
        DesignResult.model_validate(result)
    result["options"][0]["exact_margin"] = "1/100"
    assert DesignResult.model_validate(result).selected_time == "6/1"
    result["replay"] = "not_run"
    with pytest.raises(ValidationError):
        DesignResult.model_validate(result)
