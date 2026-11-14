"""Content-addressed, write-once blob storage for research assets and derived artifacts.

Names are SHA-256 digests only; uploaded filenames never reach the filesystem.
Every read re-verifies the digest, so a modified blob is reported, never served.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re

_DIGEST = re.compile(r"[a-f0-9]{64}")


class BlobIntegrityError(RuntimeError):
    pass


class BlobStore:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve() / "research-assets"
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.root, 0o700)

    def _path(self, digest: str) -> Path:
        if not _DIGEST.fullmatch(digest):
            raise BlobIntegrityError("invalid digest")
        return self.root / digest[:2] / digest

    def put(self, data: bytes) -> str:
        digest = hashlib.sha256(data).hexdigest()
        path = self._path(digest)
        if path.exists():
            self.get(digest, len(data))  # verify the existing immutable copy
            return digest
        path.parent.mkdir(exist_ok=True, mode=0o700)
        temporary = path.with_name(f".{digest}.{os.getpid()}.{os.urandom(4).hex()}")
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            try:
                os.link(temporary, path)  # never replaces an existing name
            except FileExistsError:
                self.get(digest, len(data))
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
        return digest

    def get(self, digest: str, size: int | None = None) -> bytes:
        try:
            data = self._path(digest).read_bytes()
        except OSError as exc:
            raise BlobIntegrityError("unavailable") from exc
        if (size is not None and len(data) != size) or hashlib.sha256(data).hexdigest() != digest:
            raise BlobIntegrityError("digest mismatch")
        return data
