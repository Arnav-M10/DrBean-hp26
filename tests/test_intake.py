"""Synthetic offline controls; these tests do not qualify live Gemini extraction."""
import asyncio
from io import BytesIO
from types import SimpleNamespace

from PIL import Image
import pytest

from bean_api.contracts import IntakeProposalBody, IntakeProposalRecordBody, IntakeRequest, IntakeReviewRequest
from bean_api.intake import IntakeService, SourceService, inspect_image
from bean_api.providers import ProviderResult
from bean_api.store import Store
from bean_api.workflow import DomainError, Workflow


def png(size=(20, 30)):
    buffer = BytesIO()
    Image.new("RGB", size, "white").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def setup(tmp_path):
    workflow = Workflow(Store(tmp_path / "db.sqlite"))
    workspace = workflow.create_workspace("alice", "Synthetic intake tests")
    sources = SourceService(workflow, tmp_path / "private")
    source = sources.admit("alice", workspace["id"], png(), "image/png", "synthetic", "retain", "upload1")
    return workflow, workspace["id"], sources, source


class FakeProvider:
    """Explicit test double; never records a live model claim."""
    config = SimpleNamespace(model="fixture-model")

    def __init__(self, source, mutate=None):
        self.source, self.mutate, self.calls = source, mutate, 0

    async def generate(self, operation, prompt, schema, **kwargs):
        self.calls += 1
        body = {
            "source_asset_id": self.source["id"], "source_digest": self.source["body"]["sha256"],
            "fields": [{"field_path": "rows[0].hard_allowance", "original_value": "0.05", "candidate_exact": "1/20", "unit": "mg/L",
                        "source_asset_id": self.source["id"], "locator": {"page": 1, "label": "Allowance", "excerpt": "0.05 mg/L", "bbox": [1, 1, 10, 20]},
                        "method": "gemini_vision", "grounding": "unreviewed_visual", "ambiguity": None}],
            "diagnostics": [],
        }
        if self.mutate:
            self.mutate(body)
        return ProviderResult(schema.model_validate(body), "fixture_attempt", "fixture-model", None, "STOP")


def request(source, **kwargs):
    return IntakeRequest(
        source_id=source["id"], existing_values=kwargs.get("existing_values", {}),
        consent={"provider": "gemini", "model": "fixture-model", "source_asset_ids": [source["id"]],
                 "include_notes": True, "include_existing_values": True, "accepted": True},
    )


def test_sniff_decode_and_private_source_roundtrip(setup):
    workflow, workspace, sources, source = setup
    assert source["body"]["width"] == 20
    assert "blob_key" not in source["body"]
    public, raw = sources.read("alice", source["id"])
    assert raw == png()
    assert public == source
    assert sources.admit("alice", workspace, png(), "image/png", "synthetic", "retain", "upload1")["id"] == source["id"]
    with pytest.raises(DomainError, match="different content"):
        sources.admit("alice", workspace, png((10, 10)), "image/png", "synthetic", "retain", "upload1")
    with pytest.raises(DomainError) as exc:
        sources.read("mallory", source["id"])
    assert exc.value.status == 404


@pytest.mark.parametrize("raw,mime,code", [
    (b"%PDF-1.4 hello", "image/png", "unsupported_media_type"),
    (png(), "image/jpeg", "media_type_mismatch"),
    (b"\x89PNG\r\n\x1a\nmalformed", "image/png", "malformed_image"),
    (b"x" * (5 * 1024 * 1024 + 1), "image/png", "source_size_limit"),
])
def test_admission_rejects_unsupported_or_malformed_bytes(raw, mime, code):
    with pytest.raises(DomainError) as exc:
        inspect_image(raw, mime)
    assert exc.value.code == code


def test_decoded_pixel_limit():
    with pytest.raises(DomainError) as exc:
        inspect_image(png((4000, 3001)), "image/png")
    assert exc.value.code in {"pixel_limit", "malformed_image"}


def test_exif_orientation_requires_explicit_resave():
    image = Image.new("RGB", (10, 20))
    exif = image.getexif()
    exif[274] = 6
    stream = BytesIO()
    image.save(stream, "JPEG", exif=exif)
    with pytest.raises(DomainError) as exc:
        inspect_image(stream.getvalue(), "image/jpeg")
    assert exc.value.code == "orientation_unsupported"


def test_visual_intake_never_accepts_and_retries_are_deduplicated(setup):
    workflow, workspace, sources, source = setup
    provider = FakeProvider(source)
    intake = IntakeService(workflow, sources, provider)
    proposal = asyncio.run(intake.create("alice", workspace, request(source), "intake1"))
    assert IntakeProposalRecordBody.model_validate(proposal["body"]).provider_attempt_id == "fixture_attempt"
    assert proposal["body"]["review_state"] == "unaccepted"
    assert workflow.list_records("alice", workspace, "dataset") == []
    assert asyncio.run(intake.create("alice", workspace, request(source), "intake1"))["id"] == proposal["id"]
    assert provider.calls == 1
    review = intake.review("alice", workspace, proposal["id"], IntakeReviewRequest(
        expected_proposal_digest=proposal["digest"],
        reviewed_fields=[{"field_path": "rows[0].hard_allowance", "value": "0.05", "origin": "confirmed_transcription"}],
    ), "review1")
    assert review["body"]["reviewed_fields"][0]["normalized_value"] == "1/20"
    assert review["body"]["execution_approved"] is False
    assert workflow.list_records("alice", workspace, "dataset") == []


def test_provider_output_cannot_supply_server_record_metadata(setup):
    from pydantic import ValidationError
    workflow, workspace, sources, source = setup
    proposal = asyncio.run(IntakeService(workflow, sources, FakeProvider(source)).create(
        "alice", workspace, request(source), "record_contract"))
    assert IntakeProposalRecordBody.model_validate(proposal["body"]).review_state == "unaccepted"
    with pytest.raises(ValidationError):
        IntakeProposalBody.model_validate(proposal["body"])


def test_decimal_misread_preserves_source_and_requires_correction(setup):
    workflow, workspace, sources, source = setup
    provider = FakeProvider(source, lambda b: b["fields"][0].update(original_value="0.5", candidate_exact="1/2", ambiguity="Possible 0.05 versus 0.5"))
    intake = IntakeService(workflow, sources, provider)
    proposal = asyncio.run(intake.create("alice", workspace, request(source), "ambiguous1"))
    with pytest.raises(DomainError) as exc:
        intake.review("alice", workspace, proposal["id"], IntakeReviewRequest(
            expected_proposal_digest=proposal["digest"], reviewed_fields=[{
                "field_path": "rows[0].hard_allowance", "value": "1/2", "origin": "confirmed_transcription"}],
        ), "bad-review")
    assert exc.value.code == "unresolved_clarification"
    review = intake.review("alice", workspace, proposal["id"], IntakeReviewRequest(
        expected_proposal_digest=proposal["digest"], reviewed_fields=[{
            "field_path": "rows[0].hard_allowance", "value": "0.05", "origin": "corrected_transcription", "correction_reason": "I inspected the original decimal point."}],
        resolved_diagnostics=["source_ambiguity:rows[0].hard_allowance"],
    ), "corrected-review")
    row = review["body"]["reviewed_fields"][0]
    assert row["normalized_value"] == "1/20"
    assert row["original_proposal"]["candidate_exact"] == "1/2"
    assert proposal["body"]["fields"][0]["candidate_exact"] == "1/2"


def test_existing_field_conflict_is_explicit(setup):
    workflow, workspace, sources, source = setup
    intake = IntakeService(workflow, sources, FakeProvider(source))
    proposal = asyncio.run(intake.create("alice", workspace, request(source, existing_values={"rows[0].hard_allowance": "1/5"}), "conflict"))
    assert any(d["code"] == "existing_value_conflict" for d in proposal["body"]["diagnostics"])
    assert proposal["body"]["fields"][0]["candidate_exact"] == "1/20"


@pytest.mark.parametrize("mutation,code", [
    (lambda b: b["fields"][0].update(grounding="human_reviewed"), "invalid_grounding"),
    (lambda b: b["fields"][0]["locator"].update(bbox=[0, 0, 200, 200]), "invalid_source_locator"),
    (lambda b: b["fields"][0].update(field_path="approval.accepted"), "invalid_field_path"),
    (lambda b: b.update(source_digest="a" * 64), "source_binding_mismatch"),
])
def test_model_cannot_change_grounding_scope_or_source(setup, mutation, code):
    workflow, workspace, sources, source = setup
    provider = FakeProvider(source, mutation)
    intake = IntakeService(workflow, sources, provider)
    with pytest.raises(DomainError) as exc:
        asyncio.run(intake.create("alice", workspace, request(source), "rejected"))
    assert exc.value.code == code
    assert workflow.list_records("alice", workspace, "intake_proposal") == []
    validation = workflow.list_records("alice", workspace, "provider_validation")[0]["body"]
    assert validation["attempt_id"] == "fixture_attempt" and validation["validation_outcome"] == "rejected"
    with pytest.raises(DomainError):
        asyncio.run(intake.create("alice", workspace, request(source), "rejected"))
    assert provider.calls == 1


def test_cross_workspace_source_is_rejected_even_with_membership(setup):
    workflow, workspace, sources, source = setup
    other = workflow.create_workspace("alice", "Other")
    provider = FakeProvider(source)
    with pytest.raises(DomainError) as exc:
        asyncio.run(IntakeService(workflow, sources, provider).create("alice", other["id"], request(source), "cross"))
    assert exc.value.status == 404
    assert provider.calls == 0


def test_retained_source_integrity_failure(setup):
    workflow, workspace, sources, source = setup
    record = workflow.get("alice", source["id"])
    (sources.blob_dir / record["body"]["blob_key"]).write_bytes(b"changed")
    with pytest.raises(DomainError) as exc:
        sources.read("alice", source["id"])
    assert exc.value.code == "source_integrity_failed"
