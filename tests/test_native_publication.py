"""Worker publication boundary controls using synthetic bytes, never scientific claims."""
import base64
import copy
import hashlib

import pytest

from bean_api.canonical import semantic_digest
from bean_api.config import Settings
from bean_api.science import UnavailableAdapter
from bean_api.scientific_projection import PROJECTION_VERSION, project_problem
from bean_api.store import Store
from bean_api.worker import Worker
from bean_api.workflow import DomainError, Workflow
from test_counterdex_adapter import reviewed_history


@pytest.fixture
def publication(tmp_path):
    workflow = Workflow(Store(tmp_path / "publication.sqlite"))
    workspace = workflow.create_workspace("alice", "Synthetic publication boundary")
    history = reviewed_history()
    dataset = workflow.create_dataset("alice", workspace["id"], history["dataset"]["body"], "dataset")
    problem = workflow.create_problem("alice", workspace["id"], {
        **history["problem"]["body"], "dataset_id": dataset["id"], "dataset_digest": dataset["digest"],
    }, "problem")
    settings = Settings(database_path=workflow.store.path, artifact_dir=str(tmp_path / "artifacts"))
    worker = Worker(workflow, adapter=UnavailableAdapter(), settings=settings)
    job = {"id": "run_publication_control", "workspace_id": workspace["id"]}
    content = b'{"purpose":"synthetic byte-boundary control"}\n'
    sha = hashlib.sha256(content).hexdigest()
    reference = {"id": "native_" + sha, "sha256": sha,
                 "byte_size": len(content), "media_type": "application/json"}
    scientific_digest = semantic_digest("problem", project_problem(problem, dataset))
    anchor = {"projection_version": PROJECTION_VERSION,
              "application_problem_id": problem["id"], "application_problem_digest": problem["digest"],
              "application_dataset_id": dataset["id"], "application_dataset_digest": dataset["digest"],
              "scientific_problem_digest": scientific_digest,
              "scientific_design_digest": "d" * 64, "native_suggestion_digest": "e" * 64}
    result = {"projection_version": PROJECTION_VERSION, "scientific_problem_digest": scientific_digest,
              "scientific_design_digest": "d" * 64, "native_suggestion_digest": "e" * 64,
              "artifacts": [reference],
              "verification_record": {"artifact_id": reference["id"], "artifact_sha256": sha,
                                      "expected_problem_digest": problem["digest"],
                                      "expected_scientific_problem_digest": scientific_digest},
              "candidates": [{"artifact_ids": [reference["id"]]}],
              "_native_artifacts": [{**reference, "content_base64": base64.b64encode(content).decode(),
                                     "artifact_kind": "bundle", "anchor": anchor}]}
    return worker, job, problem, dataset, result, content


def publish(context, result=None, *, limit=4 * 1024 * 1024):
    worker, job, problem, dataset, original, _ = context
    return worker._publish_native("alice", job, copy.deepcopy(original if result is None else result),
                                  problem=problem, dataset=dataset, aggregate_limit=limit)


def assert_unpublished(context):
    worker, job, *_ = context
    assert worker.workflow.list_records("alice", job["workspace_id"], "native_artifact") == []
    assert list(worker.artifacts.blob_dir.iterdir()) == []


def test_publication_preserves_bytes_and_rebinds_every_reference(publication):
    worker, _, _, _, original, content = publication
    result = publish(publication)
    assert "_native_artifacts" not in result
    identifier = result["artifacts"][0]["id"]
    assert identifier != original["artifacts"][0]["id"]
    assert result["verification_record"]["artifact_id"] == identifier
    assert result["candidates"][0]["artifact_ids"] == [identifier]
    record, downloaded = worker.artifacts.read("alice", identifier)
    assert downloaded == content
    assert record["body"]["anchor"] == original["_native_artifacts"][0]["anchor"]
    assert result["artifacts"][0]["sha256"] == record["body"]["sha256"]
    assert publish(publication) == result


@pytest.mark.parametrize("field,value", [
    ("sha256", "0" * 64), ("byte_size", 1), ("media_type", "text/plain"),
])
def test_public_reference_must_match_actual_packet(publication, field, value):
    result = copy.deepcopy(publication[4])
    result["artifacts"][0][field] = value
    with pytest.raises(DomainError):
        publish(publication, result)
    assert_unpublished(publication)


@pytest.mark.parametrize("field,value", [
    ("application_problem_id", "wrong_problem"), ("application_problem_digest", "0" * 64),
    ("application_dataset_id", "wrong_dataset"), ("application_dataset_digest", "0" * 64),
    ("scientific_problem_digest", "0" * 64), ("projection_version", "unreviewed.v2"),
    ("scientific_design_digest", "0" * 64), ("native_suggestion_digest", "0" * 64),
])
def test_packet_anchor_must_match_frozen_scope(publication, field, value):
    result = copy.deepcopy(publication[4])
    result["_native_artifacts"][0]["anchor"][field] = value
    with pytest.raises(DomainError):
        publish(publication, result)
    assert_unpublished(publication)


def test_result_cannot_self_assert_a_different_scientific_projection(publication):
    result = copy.deepcopy(publication[4])
    result["scientific_problem_digest"] = "0" * 64
    result["_native_artifacts"][0]["anchor"]["scientific_problem_digest"] = "0" * 64
    result["verification_record"]["expected_scientific_problem_digest"] = "0" * 64
    with pytest.raises(DomainError):
        publish(publication, result)
    assert_unpublished(publication)


@pytest.mark.parametrize("mode", ["duplicate_packet", "duplicate_reference", "missing_packet", "missing_reference", "extra_reference"])
def test_packet_and_reference_aliases_form_one_complete_mapping(publication, mode):
    result = copy.deepcopy(publication[4])
    if mode == "duplicate_packet":
        result["_native_artifacts"].append(copy.deepcopy(result["_native_artifacts"][0]))
    elif mode == "duplicate_reference":
        result["artifacts"].append(copy.deepcopy(result["artifacts"][0]))
    elif mode == "missing_packet":
        result["_native_artifacts"] = []
    elif mode == "missing_reference":
        result["artifacts"] = []
    else:
        result["artifacts"].append({**result["artifacts"][0], "id": "unpublished_artifact"})
    with pytest.raises(DomainError):
        publish(publication, result)
    assert_unpublished(publication)


@pytest.mark.parametrize("field,value", [
    ("artifact_id", "unpublished_artifact"), ("artifact_sha256", "0" * 64),
    ("expected_problem_digest", "0" * 64), ("expected_scientific_problem_digest", "0" * 64),
])
def test_verification_record_must_bind_published_bytes_and_scope(publication, field, value):
    result = copy.deepcopy(publication[4])
    result["verification_record"][field] = value
    with pytest.raises(DomainError):
        publish(publication, result)
    assert_unpublished(publication)


def test_approved_aggregate_limit_is_enforced_before_publication(publication):
    with pytest.raises(DomainError) as caught:
        publish(publication, limit=len(publication[5]) - 1)
    assert caught.value.code == "artifact_aggregate_limit"
    assert_unpublished(publication)


def test_malformed_native_encoding_fails_without_partial_publication(publication):
    result = copy.deepcopy(publication[4])
    result["_native_artifacts"][0]["content_base64"] = "not base64!"
    with pytest.raises(DomainError):
        publish(publication, result)
    assert_unpublished(publication)
