"""Bounded PDF admission, manifest construction, page rendering and page subsets."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from ..workflow import DomainError
from . import limits as L

WORKER = Path(__file__).with_name("_pdf_worker.py")


class PaperError(DomainError):
    """A user-facing refusal with a fixed code; never contains document content.

    A DomainError, so the API's existing error handler returns the standard error body."""

    MESSAGES = {
        "unsupported_media_type": "Only PDF papers are admitted on this path. Images use the image source path.",
        "media_type_mismatch": "The file does not start with a PDF header, whatever its name or declared type.",
        "source_too_large": f"Papers are limited to {L.MAX_PAPER_BYTES // (1024 * 1024)} MiB. Supply a smaller excerpt with its page provenance.",
        "empty_pdf": "The file is empty or has no pages.",
        "encrypted_pdf": "The PDF is password-protected or encrypted. Save an unprotected copy you are permitted to use.",
        "page_limit": f"Papers are limited to {L.MAX_PAGES} pages. Supply an excerpt with declared page provenance.",
        "malformed_pdf": "The PDF could not be parsed. It may be damaged; try re-saving it, or enter values manually.",
        "page_out_of_range": "That page number is not in this paper.",
        "selection_limit": f"Select between 1 and {L.MAX_PAGES_PER_BATCH} distinct pages per batch.",
        "render_pixel_limit": "The page is too large to preview within the configured limit.",
        "resource_limit": "Processing this paper exceeded its memory or time limit. Try an excerpt.",
        "parse_timeout": "Processing this paper exceeded its time limit. Try an excerpt.",
        "invalid_command": "Invalid paper processing request.",
        "decoder_setup_failed": "The isolated PDF worker could not start with its required limits.",
        "worker_output_invalid": "The PDF worker returned an invalid response.",
    }
    STATUS = {"decoder_setup_failed": 503, "worker_output_invalid": 503}

    def __init__(self, code: str):
        code = code if code in self.MESSAGES else "malformed_pdf"
        super().__init__(code, self.MESSAGES[code], self.STATUS.get(code, 422))


def sniff_pdf(raw: bytes, declared_mime: str) -> None:
    """Check size and structure before any parsing. Names and MIME headers are not trusted."""
    if not raw:
        raise PaperError("empty_pdf")
    if len(raw) > L.MAX_PAPER_BYTES:
        raise PaperError("source_too_large")
    if declared_mime != "application/pdf":
        raise PaperError("unsupported_media_type")
    if not raw.startswith(b"%PDF-"):
        raise PaperError("media_type_mismatch")


def _run(operation: str, raw: bytes, **arguments) -> dict:
    header = json.dumps({"operation": operation, **arguments}).encode() + b"\n"
    try:
        # Minimal environment: no credentials, no PYTHONPATH, no proxies reach the parser.
        done = subprocess.run([sys.executable, "-s", str(WORKER)], input=header + raw, capture_output=True,
                              timeout=L.WORKER_TIMEOUT_SECONDS[operation], check=False,
                              env={"PATH": os.defpath, "LANG": "C.UTF-8"}, start_new_session=True)
    except subprocess.TimeoutExpired:
        raise PaperError("parse_timeout") from None
    except OSError:
        raise PaperError("decoder_setup_failed") from None
    if done.returncode:
        lines = done.stderr.decode("utf-8", "replace").strip().splitlines()
        code = lines[-1].strip() if lines else ""
        if done.returncode < 0:  # killed by a resource limit signal
            code = "resource_limit"
        raise PaperError(code)
    if len(done.stdout) > L.WORKER_OUTPUT_BYTES:
        raise PaperError("worker_output_invalid")
    try:
        result = json.loads(done.stdout)
    except ValueError:
        raise PaperError("worker_output_invalid") from None
    if not isinstance(result, dict):
        raise PaperError("worker_output_invalid")
    return result


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def inspect_paper(raw: bytes, declared_mime: str = "application/pdf") -> dict:
    """Admit one PDF and return its bounded manifest. Raises PaperError with a fixed code."""
    sniff_pdf(raw, declared_mime)
    result = _run("inspect", raw)
    pages = result["pages"]
    with_text = [p["physical_page"] for p in pages if p["has_text_layer"]]
    manifest = {
        "manifest_version": L.MANIFEST_VERSION,
        "source": {"sha256": hashlib.sha256(raw).hexdigest(), "byte_size": len(raw), "media_type": "application/pdf"},
        "page_count": result["page_count"], "parser": result["parser"], "renderer": result["renderer"],
        "coordinates": L.COORDINATES, "limits": L.capabilities(),
        "pages": [{k: v for k, v in p.items() if k != "text"} for p in pages],
        "document_warnings": result["document_warnings"],
        "coverage": {"physical_pages": result["page_count"], "pages_with_text_layer": with_text,
                     "pages_without_text_layer": [p["physical_page"] for p in pages if not p["has_text_layer"]],
                     "text_truncated_pages": [p["physical_page"] for p in pages if any(w.startswith("text_truncated") for w in p["warnings"])],
                     "rendered_pages": [], "model_processed_pages": [],
                     "statement": "Native text extraction only. Pages without a text layer (for example scans) need visual review; no OCR is performed here."},
    }
    manifest["manifest_sha256"] = _digest(manifest)
    return {"manifest": manifest, "page_text": {p["physical_page"]: p["text"] for p in pages}}


def render_page(raw: bytes, page: int, scale: float = L.DEFAULT_RENDER_SCALE) -> dict:
    """Render one physical page to PNG. Returns metadata and the PNG bytes separately."""
    sniff_pdf(raw, "application/pdf")
    result = _run("render", raw, page=page, scale=scale)
    png = base64.b64decode(result.pop("png_base64"))
    if hashlib.sha256(png).hexdigest() != result["png_sha256"]:
        raise PaperError("worker_output_invalid")
    result["source_sha256"] = hashlib.sha256(raw).hexdigest()
    return {"preview": result, "png": png}


def select_pages(raw: bytes, pages: list[int], manifest: dict) -> dict:
    """Build a derived PDF of the selected physical pages, with its own digest and page mapping."""
    sniff_pdf(raw, "application/pdf")
    source_sha = hashlib.sha256(raw).hexdigest()
    if manifest["source"]["sha256"] != source_sha:
        raise PaperError("worker_output_invalid")
    result = _run("subset", raw, pages=list(pages))
    data = base64.b64decode(result["subset_base64"])
    if hashlib.sha256(data).hexdigest() != result["subset_sha256"]:
        raise PaperError("worker_output_invalid")
    by_number = {p["physical_page"]: p for p in manifest["pages"]}
    mapping = [{"subset_page": i + 1, "physical_page": p, "printed_label": by_number[p]["printed_label"],
                "text_sha256": by_number[p]["text_sha256"]} for i, p in enumerate(result["pages"])]
    selection = {"source_sha256": source_sha, "manifest_sha256": manifest["manifest_sha256"],
                 "subset_sha256": result["subset_sha256"], "subset_byte_size": result["byte_size"], "mapping": mapping}
    selection["selection_sha256"] = _digest(selection)  # what a provider disclosure must bind
    unselected = [p for p in by_number if p not in result["pages"]]
    selection["coverage_note"] = (f"{len(mapping)} of {manifest['page_count']} pages selected. "
                                  f"Unselected pages: {unselected or 'none'}. Unselected pages are not reviewed by this batch.")
    return {"selection": selection, "pdf": data}
