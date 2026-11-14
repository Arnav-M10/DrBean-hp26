"""Controlled transcription is reviewed before real application input creation."""
import asyncio
from copy import deepcopy

import pytest

from bean_api.contracts import DatasetBody, IntakeReviewRequest, MaterializedProblemInputs
from bean_api.intake import IntakeService, SourceService
from bean_api.source_materialization import SourceMaterializationService, reviewed_input_values
from bean_api.store import Store
from bean_api.workflow import DomainError, Workflow
from test_intake import FakeProvider, png, request


@pytest.fixture
def prepared(tmp_path):
    workflow = Workflow(Store(tmp_path / "db.sqlite"))
    workspace = workflow.create_workspace("alice", "Synthetic source review")
    sources = SourceService(workflow, tmp_path / "sources")
    source = sources.admit("alice", workspace["id"], png(), "image/png", "synthetic", "retain", "upload")
    def ambiguous(body):
        body["fields"][0]["original_value"] = "0.5"
        body["fields"][0]["candidate_exact"] = "1/2"
    intake = IntakeService(workflow, sources, FakeProvider(source, ambiguous))
    proposal = asyncio.run(intake.create("alice", workspace["id"], request(source), "extract"))
    review = intake.review("alice", workspace["id"], proposal["id"], IntakeReviewRequest(
        expected_proposal_digest=proposal["digest"], reviewed_fields=[{
            "field_path": "rows[0].hard_allowance", "value": "0.05", "origin": "corrected_transcription",
            "correction_reason": "Human read the decimal point from the original source."}]), "review")
    dataset = DatasetBody(experiment_id="source_experiment", time_origin="Elapsed time from synthetic start", origin="synthetic",
        change_reason="Explicit source materialization", rows=[
            {"id": "row1", "time": "1/1", "concentration": "3/1", "hard_allowance": "1/20", "included": True},
            {"id": "row2", "time": "2/1", "concentration": "4/1", "hard_allowance": "1/5", "included": True},
            {"id": "row3", "time": "3/1", "concentration": "5/1", "hard_allowance": "1/5", "included": True},
        ]).model_dump(mode="json")
    problem = MaterializedProblemInputs(domain={"A": {"lower": "1/1", "upper": "20/1"},
        "ke": {"lower": "1/100", "upper": "1/2"}, "ka": {"lower": "1/1", "upper": "8/1"}},
        target={"lower": "1/10", "upper": "1/5"}).model_dump(mode="json")
    assumptions = {path: "Explicit team-selected synthetic assumption for review." for path in reviewed_input_values(dataset, problem)
                   if path != "rows[0].hard_allowance" and not path.endswith(".notes")}
    body = {"expected_review_digest": review["digest"], "dataset": dataset, "problem": problem, "human_assumptions": assumptions}
    return workflow, workspace["id"], review, body, SourceMaterializationService(workflow, sources)


def test_corrected_value_enters_exact_immutable_dataset_without_approval(prepared):
    workflow, workspace, review, body, service = prepared
    result = service.materialize("alice", workspace, review["id"], body, "materialize")
    row = result["dataset"]["body"]["rows"][0]
    assert row["hard_allowance"] == "1/20"
    assert row["original_values"]["hard_allowance"] == "0.5"
    provenance = result["materialization"]["body"]["field_provenance"][0]
    assert provenance["origin"] == "corrected_transcription"
    assert provenance["review_id"] == review["id"]
    assert result["problem"]["body"]["dataset_digest"] == result["dataset"]["digest"]
    assert service.materialize("alice", workspace, review["id"], body, "different-key") == result
    with workflow.store.read() as conn:
        assert conn.execute("SELECT count(*) FROM approvals").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0


def test_mismatch_or_missing_assumptions_never_creates_executable_input(prepared):
    workflow, workspace, review, body, service = prepared
    changed = deepcopy(body)
    changed["dataset"]["rows"][0]["hard_allowance"] = "1/2"
    with pytest.raises(DomainError) as caught:
        service.materialize("alice", workspace, review["id"], changed, "wrong")
    assert caught.value.code == "review_value_mismatch"
    missing = deepcopy(body)
    del missing["human_assumptions"]["concentration_unit"]
    with pytest.raises(DomainError) as caught:
        service.materialize("alice", workspace, review["id"], missing, "missing")
    assert caught.value.code == "unreviewed_assumptions"
    assert "concentration_unit" in caught.value.field_paths
    assert workflow.list_records("alice", workspace, "dataset") == []


def test_synthetic_source_and_scope_cannot_be_relabelled(prepared):
    _, workspace, review, body, service = prepared
    changed = deepcopy(body)
    changed["dataset"]["origin"] = "actual"
    with pytest.raises(DomainError) as caught:
        service.materialize("alice", workspace, review["id"], changed, "actual")
    assert caught.value.code == "origin_mismatch"
    with pytest.raises(DomainError) as caught:
        service.materialize("mallory", workspace, review["id"], body, "unauthorized")
    assert caught.value.status == 404


def test_materialized_values_are_not_silently_changed_with_new_key(prepared):
    _, workspace, review, body, service = prepared
    service.materialize("alice", workspace, review["id"], body, "first")
    changed = deepcopy(body)
    changed["problem"]["domain"]["A"]["upper"] = "30/1"
    with pytest.raises(DomainError) as caught:
        service.materialize("alice", workspace, review["id"], changed, "again")
    assert caught.value.code == "review_already_materialized"


def test_corrupt_source_is_not_materialized(prepared):
    workflow, workspace, review, body, service = prepared
    source = workflow.get("alice", review["body"]["source_asset_id"], "source_asset")
    (service.sources.blob_dir / source["body"]["blob_key"]).write_bytes(b"corrupt")
    with pytest.raises(DomainError) as caught:
        service.materialize("alice", workspace, review["id"], body, "corrupt")
    assert caught.value.code == "source_integrity_failed"
    assert workflow.list_records("alice", workspace, "dataset") == []


def test_decoder_setup_failure_remains_infrastructure(monkeypatch):
    from bean_api.intake import inspect_image
    from types import SimpleNamespace
    monkeypatch.setattr("bean_api.intake.subprocess.run", lambda *args, **kwargs:
        SimpleNamespace(returncode=1, stdout=b"", stderr=b"decoder_setup_failed\n"))
    with pytest.raises(DomainError) as caught:
        inspect_image(png(), "image/png")
    assert caught.value.code == "decoder_setup_failed"
    assert caught.value.status == 503
