"""Native-byte storage controls; no fixture is claimed as scientific evidence."""
import hashlib
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from bean_api.artifacts import ArtifactService, CERTIFICATE_LIMIT
from bean_api.store import Store
from bean_api.workflow import DomainError, Workflow


@pytest.fixture
def artifacts(tmp_path):
    workflow = Workflow(Store(tmp_path / "db.sqlite"))
    workspace = workflow.create_workspace("alice", "Native bytes")
    return workflow, workspace["id"], ArtifactService(workflow, tmp_path / "artifacts")


def test_download_is_exact_native_bytes_and_anchor_is_separate(artifacts):
    workflow, workspace, service = artifacts
    content = b'{"native":"synthetic storage test"}\n'
    anchor = {"application_problem_id": "problem", "scientific_problem_digest": "a" * 64}
    record = service.publish("alice", workspace, content, media_type="application/json", anchor=anchor, key="one")
    public, downloaded = service.read("alice", record["id"])
    assert downloaded == content
    assert public["body"]["sha256"] == hashlib.sha256(content).hexdigest()
    assert public["body"]["anchor"] == anchor
    assert "blob_key" not in public["body"]
    assert service.publish("alice", workspace, content, media_type="application/json", anchor=anchor, key="one") == record
    with pytest.raises(DomainError) as error:
        service.read("mallory", record["id"])
    assert error.value.status == 404
    with pytest.raises(DomainError) as changed:
        service.publish("alice", workspace, content + b" ", media_type="application/json", anchor=anchor, key="one")
    assert changed.value.code == "idempotency_conflict"


def test_corrupted_bytes_fail_before_download(artifacts):
    workflow, workspace, service = artifacts
    record = service.publish("alice", workspace, b"{}", media_type="application/json", anchor={"expected": "a"}, key="one")
    stored = workflow.get("alice", record["id"], "native_artifact")
    (service.blob_dir / stored["body"]["blob_key"]).write_bytes(b"[]")
    with pytest.raises(DomainError) as caught:
        service.read("alice", record["id"])
    assert caught.value.code == "artifact_integrity_failed"


def test_aggregate_budget_checked_before_any_publication(artifacts):
    workflow, workspace, service = artifacts
    items = [{"content": b"x" * CERTIFICATE_LIMIT, "media_type": "application/json", "anchor": {"expected": "a"}}] * 3
    with pytest.raises(DomainError) as caught:
        service.publish_many("alice", workspace, items, key="too-large")
    assert caught.value.code == "artifact_aggregate_limit"
    assert workflow.list_records("alice", workspace, "native_artifact") == []
    assert list(service.blob_dir.iterdir()) == []


def test_concurrent_idempotent_publication_keeps_one_native_record(artifacts):
    workflow, workspace, service = artifacts
    barrier = Barrier(2)
    def publish(_):
        barrier.wait()
        return service.publish("alice", workspace, b"{}", media_type="application/json", anchor={"expected": "a"}, key="race")
    with ThreadPoolExecutor(max_workers=2) as pool:
        records = list(pool.map(publish, range(2)))
    assert records[0] == records[1]
    assert len(workflow.list_records("alice", workspace, "native_artifact")) == 1
    assert len(list(service.blob_dir.iterdir())) == 1
