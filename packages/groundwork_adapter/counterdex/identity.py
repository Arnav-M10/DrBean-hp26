"""Prepared runtime identity; artifact metadata never selects imports or paths."""
import platform
from pathlib import Path
import sys

from .errors import AdapterError
from .exact import artifact_digest, canonical_bytes

VERSION = "0.3.0"


def implementation_identity() -> dict:
    if sys.implementation.name != "cpython" or sys.version_info[:2] != (3, 11):
        raise AdapterError("unsupported_runtime", "This release is qualified on CPython 3.11; use its prepared environment.")
    root = Path(__file__).resolve().parent
    # Locally installed package files only. No artifact-controlled discovery.
    files = [{"file": p.name, "sha256": artifact_digest(p.read_bytes())} for p in sorted(root.glob("*.py"))]
    return {"adapter_version": VERSION, "python": platform.python_version(), "runtime": "CPython",
            "canonicalization_profile": "DB-SC-1", "source_manifest": files,
            "source_digest": artifact_digest(canonical_bytes(files))}
