"""Reference paper storage service, for Owner 2 to register (see docs/proposals/owner2-paper-interface.md).

Uses only the existing Workflow record and operation primitives: no new tables, no migration.
Record kinds: `paper_source` (retained original + manifest) and `paper_page_selection`
(derived selected-page PDF + mapping). Blob names are server generated and never leave
this service. Every read is workspace-authorized through Workflow.get. Nothing here calls a
provider, accepts a value, approves a plan or submits a job.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import uuid

from . import limits as L
from .admission import PaperError, inspect_paper, render_page, select_pages
from .citations import match_quotation, validate_citation

_BLOB = re.compile(r"[a-f0-9]{32}")
_FILENAME = re.compile(r"[^A-Za-z0-9._ ()-]+")


class PaperService:
    def __init__(self, workflow, blob_dir: str | Path):
        self.workflow = workflow
        self.blob_dir = Path(blob_dir).resolve()
        self.blob_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.blob_dir, 0o700)

    # ---------------------------------------------------------------- storage
    def _write(self, data: bytes) -> str:
        name = uuid.uuid4().hex
        fd = os.open(self.blob_dir / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        return name

    def _read(self, name: str, sha256: str, size: int | None = None) -> bytes:
        if not _BLOB.fullmatch(name or ""):
            raise PaperError("worker_output_invalid")
        try:
            data = (self.blob_dir / name).read_bytes()
        except OSError:
            raise _unavailable() from None
        if hashlib.sha256(data).hexdigest() != sha256 or (size is not None and len(data) != size):
            raise _integrity()
        return data

    @staticmethod
    def public_record(record: dict) -> dict:
        body = {k: v for k, v in record["body"].items() if not k.endswith("blob_key")}
        return {**record, "body": body}

    # ---------------------------------------------------------------- commands
    def admit(self, actor: str, workspace_id: str, raw: bytes, declared_mime: str, origin: str,
              retention: str, filename: str, key: str) -> dict:
        """Retain one paper and its manifest. Upload never sends anything to a model."""
        self.workflow.authorize(actor, workspace_id)
        if origin not in {"synthetic", "public"}:
            raise _domain("source_origin_not_admitted", "Use a permitted synthetic or public paper.", ["origin"])
        if retention != "retain":
            raise _domain("retention_not_supported", "Retaining the paper is required for page-cited review.", ["retention"])
        inspected = inspect_paper(raw, declared_mime)
        manifest = inspected["manifest"]
        name = _FILENAME.sub("_", (filename or "paper.pdf").strip())[:120] or "paper.pdf"
        identity = {"sha256": manifest["source"]["sha256"], "byte_size": len(raw), "origin": origin,
                    "retention": retention, "filename": name}
        operation = self.workflow.begin_operation(actor, workspace_id, "paper-upload", key, identity)
        if not operation["created_new"]:
            if operation.get("response") is not None:
                return operation["response"]
            raise _domain("operation_pending", "This upload was already accepted and requires reconciliation.", status=409)
        try:
            text = json.dumps({str(k): v for k, v in inspected["page_text"].items()}, ensure_ascii=False).encode()
            body = {**identity, "media_type": "application/pdf", "upload_actor_id": actor, "manifest": manifest,
                    "page_text_sha256": hashlib.sha256(text).hexdigest(),
                    "blob_key": self._write(raw), "text_blob_key": self._write(text),
                    "model_processing": "none: upload retains the paper locally and sends nothing to a provider"}
            record = self.workflow.create_record(actor, workspace_id, "paper_source", body, key, operation="paper-record")
            public = self.public_record(record)
            self.workflow.finish_operation(actor, workspace_id, "paper-upload", key, public)
            return public
        except BaseException:
            self.workflow.fail_operation(actor, workspace_id, "paper-upload", key, "paper_storage_failed")
            raise

    def select(self, actor: str, paper_id: str, pages: list[int], key: str) -> dict:
        """Derive the selected-page PDF a provider disclosure would bind (no provider call here)."""
        record, raw = self.read(actor, paper_id)
        workspace_id, operation_name = record["workspace_id"], f"paper-select:{paper_id}"
        derived = select_pages(raw, pages, record["body"]["manifest"])  # validates pages before any write
        operation = self.workflow.begin_operation(actor, workspace_id, operation_name, key,
                                                  {"paper_id": paper_id, "pages": list(pages)})
        if not operation["created_new"]:
            if operation.get("response") is not None:
                return operation["response"]
            raise _domain("operation_pending", "This selection was already accepted and requires reconciliation.", status=409)
        try:
            body = {**derived["selection"], "paper_id": paper_id, "subset_blob_key": self._write(derived["pdf"]),
                    "pages": list(pages), "model_processing": "none"}
            created = self.workflow.create_record(actor, workspace_id, "paper_page_selection", body, key,
                                                  operation="paper-selection-record", parent_id=paper_id)
            public = self.public_record(created)
            self.workflow.finish_operation(actor, workspace_id, operation_name, key, public)
            return public
        except BaseException:
            self.workflow.fail_operation(actor, workspace_id, operation_name, key, "paper_selection_failed")
            raise

    # ---------------------------------------------------------------- reads
    def read(self, actor: str, paper_id: str) -> tuple[dict, bytes]:
        record = self.workflow.get(actor, paper_id, kind="paper_source")
        raw = self._read(record["body"]["blob_key"], record["body"]["sha256"], record["body"]["byte_size"])
        return self.public_record(record), raw

    def _text(self, actor: str, paper_id: str) -> tuple[dict, dict]:
        record = self.workflow.get(actor, paper_id, kind="paper_source")
        text = json.loads(self._read(record["body"]["text_blob_key"], record["body"]["page_text_sha256"]))
        return record, {int(k): v for k, v in text.items()}

    def page_text(self, actor: str, paper_id: str, page: int) -> dict:
        record, text = self._text(actor, paper_id)
        info = {p["physical_page"]: p for p in record["body"]["manifest"]["pages"]}.get(page)
        if info is None:
            raise PaperError("page_out_of_range")
        return {"paper_id": paper_id, "physical_page": page, "printed_label": info["printed_label"],
                "has_text_layer": info["has_text_layer"], "text": text.get(page, ""),
                "text_sha256": info["text_sha256"], "warnings": info["warnings"],
                "note": "Native text layer only. It may miss tables, symbols and scanned content."}

    def page_preview(self, actor: str, paper_id: str, page: int, scale: float = L.DEFAULT_RENDER_SCALE) -> dict:
        _record, raw = self.read(actor, paper_id)
        return render_page(raw, page, scale)

    def subset_content(self, actor: str, selection_id: str) -> tuple[dict, bytes]:
        record = self.workflow.get(actor, selection_id, kind="paper_page_selection")
        data = self._read(record["body"]["subset_blob_key"], record["body"]["subset_sha256"], record["body"]["subset_byte_size"])
        return self.public_record(record), data

    def check_citation(self, actor: str, paper_id: str, page: int, excerpt: str, box: list | None = None) -> dict:
        record, text = self._text(actor, paper_id)
        manifest = record["body"]["manifest"]
        return {"paper_id": paper_id, "physical_page": page, "quotation": match_quotation(manifest, text, page, excerpt),
                "location_problems": validate_citation(manifest, page, box) if box is not None else
                ["no location within the page was given; the reviewer must find the value on the page"]}


def _domain(code, message, paths=None, status=422):
    from ..workflow import DomainError
    return DomainError(code, message, status, paths or [])


def _unavailable():
    return _domain("source_unavailable", "The retained paper is unavailable.", status=409)


def _integrity():
    return _domain("source_integrity_failed", "The retained paper bytes no longer match their recorded digest.", status=409)
