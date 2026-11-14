"""Private native scientific bytes, distinct from application entity envelopes."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import uuid

from .canonical import canonical_bytes
from .workflow import DomainError

CERTIFICATE_LIMIT = 2 * 1024 * 1024
BUNDLE_LIMIT = 4 * 1024 * 1024


class ArtifactService:
    """Publish complete bytes before immutable metadata, never arbitrary paths.

    The worker supplies anchors from its frozen application scope. The native
    verifier must still consume those independently expected identities: storage
    integrity by itself does not establish a scientific proposition.
    """

    def __init__(self, workflow, blob_dir: str | Path):
        self.workflow = workflow
        self.blob_dir = Path(blob_dir).resolve()
        self.blob_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.blob_dir, 0o700)

    @staticmethod
    def public_record(record: dict) -> dict:
        return {**record, "body": {k: v for k, v in record["body"].items() if k != "blob_key"}}

    def publish(self, actor: str, workspace_id: str, content: bytes, *, media_type: str,
                anchor: dict, key: str, kind: str = "certificate") -> dict:
        return self.publish_many(actor, workspace_id, [{"content": content, "media_type": media_type,
            "anchor": anchor, "artifact_kind": kind}], key=key)[0]

    def publish_many(self, actor: str, workspace_id: str, items: list[dict], *, key: str,
                     aggregate_limit: int = BUNDLE_LIMIT) -> list[dict]:
        self.workflow.authorize(actor, workspace_id)
        if type(aggregate_limit) is not int or not 1 <= aggregate_limit <= BUNDLE_LIMIT:
            raise DomainError("artifact_size_limit", "The aggregate native export limit is invalid.", 422)
        if not isinstance(items, list) or not 1 <= len(items) <= 16:
            raise DomainError("artifact_count_limit", "Supply one to sixteen bounded native artifacts.", 422)
        metadata, contents = [], []
        for item in items:
            content = item.get("content")
            kind = item.get("artifact_kind", "certificate")
            if not isinstance(content, bytes) or not content:
                raise DomainError("invalid_artifact", "Native artifact content must be nonempty bytes.", 422)
            if kind not in {"certificate", "bundle"} or item.get("media_type") != "application/json":
                raise DomainError("invalid_artifact", "This scientific lane exports native JSON certificates and bundles.", 422)
            if len(content) > (CERTIFICATE_LIMIT if kind == "certificate" else BUNDLE_LIMIT):
                raise DomainError("artifact_size_limit", "The native artifact exceeds its admitted byte limit.", 422)
            anchor = item.get("anchor")
            if not isinstance(anchor, dict) or not anchor or len(canonical_bytes(anchor)) > 16_384:
                raise DomainError("invalid_artifact_anchor", "A bounded independently supplied application anchor is required.", 422)
            metadata.append({"sha256": hashlib.sha256(content).hexdigest(), "byte_size": len(content),
                "media_type": item["media_type"], "artifact_kind": kind, "anchor": anchor})
            contents.append(content)
        if sum(len(content) for content in contents) > aggregate_limit:
            raise DomainError("artifact_aggregate_limit", "Combined native bytes exceed the approved aggregate export limit.", 422)

        def publish(conn):
            result = []
            for body, content in zip(metadata, contents, strict=True):
                blob_key = uuid.uuid4().hex
                temporary = self.blob_dir / ("." + blob_key + ".tmp")
                destination = self.blob_dir / blob_key
                fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                try:
                    with os.fdopen(fd, "wb") as stream:
                        stream.write(content)
                        stream.flush()
                        os.fsync(stream.fileno())
                    observed = temporary.read_bytes()
                    if len(observed) != body["byte_size"] or hashlib.sha256(observed).hexdigest() != body["sha256"]:
                        raise DomainError("artifact_integrity_failed", "Written native bytes failed integrity verification.", 503)
                    # Atomic, non-overwriting promotion; UUID names are server-owned.
                    os.link(temporary, destination)
                    temporary.unlink()
                    directory = os.open(self.blob_dir, os.O_RDONLY)
                    try:
                        os.fsync(directory)
                    finally:
                        os.close(directory)
                    record = self.workflow._insert(conn, actor, workspace_id, "native_artifact", {**body, "blob_key": blob_key})
                    result.append(self.public_record(record))
                finally:
                    temporary.unlink(missing_ok=True)
            return {"artifacts": result}

        outcome = self.workflow._perform(actor, workspace_id, "native-artifact-publication", key,
            {"artifacts": metadata, "aggregate_limit": aggregate_limit}, publish)
        return outcome["artifacts"]

    def read(self, actor: str, artifact_id: str) -> tuple[dict, bytes]:
        record = self.workflow.get(actor, artifact_id, "native_artifact")
        body = record["body"]
        key = body.get("blob_key", "")
        if not re.fullmatch(r"[a-f0-9]{32}", key):
            raise DomainError("artifact_unavailable", "The native artifact storage reference is invalid.", 409)
        try:
            # A corrupt oversized file is rejected without reading unbounded bytes.
            with (self.blob_dir / key).open("rb") as stream:
                content = stream.read(BUNDLE_LIMIT + 1)
        except OSError:
            raise DomainError("artifact_unavailable", "The retained native artifact is unavailable.", 409) from None
        if len(content) != body["byte_size"] or hashlib.sha256(content).hexdigest() != body["sha256"]:
            raise DomainError("artifact_integrity_failed", "Native bytes do not match the immutable recorded length and SHA-256.", 409)
        return self.public_record(record), content
