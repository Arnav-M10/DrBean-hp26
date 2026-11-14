"""Owner 4: reference paper storage service against the real Workflow and Store (no routes)."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

pytest.importorskip("pypdf", reason="pypdf is not installed; Owner 2 pins it")
pytest.importorskip("pypdfium2", reason="pypdfium2 is not installed; Owner 2 pins it")

from bean_api.papers import PaperError  # noqa: E402
from bean_api.papers.service import PaperService  # noqa: E402
from bean_api.store import Store  # noqa: E402
from bean_api.workflow import DomainError, Workflow  # noqa: E402

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "papers"


@pytest.fixture
def env(tmp_path):
    workflow = Workflow(Store(tmp_path / "papers.sqlite3"))
    service = PaperService(workflow, tmp_path / "blobs")
    alice = workflow.create_workspace("alice", "Paper review")["id"]
    bob = workflow.create_workspace("bob", "Other lab")["id"]
    return workflow, service, alice, bob, tmp_path / "blobs"


def raw(name="synthetic-native.pdf"):
    return (FIXTURES / name).read_bytes()


def test_upload_retains_bytes_and_manifest_without_model_processing(env):
    workflow, service, alice, _bob, blobs = env
    record = service.admit("alice", alice, raw(), "application/pdf", "synthetic", "retain", "../../etc/passwd paper.pdf", "k1")
    body = record["body"]
    assert record["kind"] == "paper_source" and body["sha256"] == hashlib.sha256(raw()).hexdigest()
    assert not any(key.endswith("blob_key") for key in body), "private blob names never leave the service"
    assert "/" not in body["filename"]
    assert body["manifest"]["coverage"]["model_processed_pages"] == [] and body["model_processing"].startswith("none")
    stored, content = service.read("alice", record["id"])
    assert content == raw() and stored == record
    assert service.page_text("alice", record["id"], 1)["text"].count("4.80") == 1


def test_retry_with_the_same_key_returns_the_same_identity_and_writes_once(env):
    workflow, service, alice, _bob, blobs = env
    first = service.admit("alice", alice, raw(), "application/pdf", "synthetic", "retain", "p.pdf", "same-key")
    files = sorted(blobs.iterdir())
    again = service.admit("alice", alice, raw(), "application/pdf", "synthetic", "retain", "p.pdf", "same-key")
    assert again == first and sorted(blobs.iterdir()) == files
    with pytest.raises(DomainError) as caught:  # same key, different paper
        service.admit("alice", alice, raw("statistical-trap.pdf"), "application/pdf", "synthetic", "retain", "p.pdf", "same-key")
    assert caught.value.status == 409 or caught.value.code.endswith("conflict") or "key" in caught.value.message.lower()


def test_refused_papers_create_no_record(env):
    workflow, service, alice, _bob, _blobs = env
    with pytest.raises(PaperError):
        service.admit("alice", alice, b"%PDF-1.7\n\x00broken", "application/pdf", "synthetic", "retain", "x.pdf", "bad")
    with pytest.raises(DomainError):
        service.admit("alice", alice, raw(), "application/pdf", "private", "retain", "x.pdf", "origin")
    assert workflow.list_records("alice", alice, "paper_source") == []


def test_another_workspace_cannot_read_pages_text_previews_or_selections(env):
    workflow, service, alice, bob, _blobs = env
    paper = service.admit("alice", alice, raw("statistical-trap.pdf"), "application/pdf", "synthetic", "retain", "t.pdf", "k")
    selection = service.select("alice", paper["id"], [2], "sel")
    for call in (lambda: service.read("bob", paper["id"]), lambda: service.page_text("bob", paper["id"], 1),
                 lambda: service.page_preview("bob", paper["id"], 1), lambda: service.subset_content("bob", selection["id"]),
                 lambda: service.select("bob", paper["id"], [1], "x"), lambda: service.check_citation("bob", paper["id"], 1, "mean")):
        with pytest.raises(DomainError) as caught:
            call()
        assert caught.value.status == 404


def test_selection_is_idempotent_bound_to_the_paper_and_downloadable(env):
    workflow, service, alice, _bob, _blobs = env
    paper = service.admit("alice", alice, raw("statistical-trap.pdf"), "application/pdf", "synthetic", "retain", "t.pdf", "k")
    selection = service.select("alice", paper["id"], [2, 1], "sel")
    assert service.select("alice", paper["id"], [2, 1], "sel") == selection
    body = selection["body"]
    assert body["paper_id"] == paper["id"] and body["manifest_sha256"] == paper["body"]["manifest"]["manifest_sha256"]
    assert [m["physical_page"] for m in body["mapping"]] == [2, 1]
    record, data = service.subset_content("alice", selection["id"])
    assert hashlib.sha256(data).hexdigest() == body["subset_sha256"] and record["parent_id"] == paper["id"]


def test_previews_and_citation_checks(env):
    workflow, service, alice, _bob, _blobs = env
    paper = service.admit("alice", alice, raw("statistical-trap.pdf"), "application/pdf", "synthetic", "retain", "t.pdf", "k")
    preview = service.page_preview("alice", paper["id"], 2)
    assert preview["png"].startswith(b"\x89PNG") and preview["preview"]["page"] == 2
    checked = service.check_citation("alice", paper["id"], 1, "SEM, not SD")
    assert checked["quotation"]["status"] == "wrong_page" and checked["location_problems"]
    with pytest.raises(PaperError):
        service.page_text("alice", paper["id"], 9)


def test_tampered_bytes_are_detected(env):
    workflow, service, alice, _bob, blobs = env
    paper = service.admit("alice", alice, raw(), "application/pdf", "synthetic", "retain", "p.pdf", "k")
    for blob in blobs.iterdir():
        blob.write_bytes(blob.read_bytes() + b" ")
    with pytest.raises(DomainError) as caught:
        service.read("alice", paper["id"])
    assert caught.value.code == "source_integrity_failed"
