"""Detect the real media type of uploaded bytes, parse them in bounds, and describe pages.

The declared ``Content-Type`` selects how text is parsed; it never proves format.
Binary formats must carry their signature. Filenames, PDF metadata, page text and
embedded instructions are untrusted data: they are stored and displayed, never
executed, followed or used as storage paths.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
import importlib.metadata
import re
import unicodedata
from urllib.parse import unquote_to_bytes

from . import limits as L
from .textformats import ParseRefused, decode_text, parse_delimited, parse_json_document, parse_text
from .workers import AdmissionRefused, inspect_image, inspect_pdf

MEDIA_ALIASES = {
    "text/csv": "text/csv", "application/csv": "text/csv", "text/x-csv": "text/csv",
    "application/vnd.ms-excel": "text/csv", "text/comma-separated-values": "text/csv",
    "text/tab-separated-values": "text/tab-separated-values", "text/tsv": "text/tab-separated-values",
    "application/json": "application/json", "text/json": "application/json", "application/geo+json": "application/json",
    "text/plain": "text/plain", "text/markdown": "text/markdown", "text/x-markdown": "text/markdown",
    "image/png": "image/png", "image/jpeg": "image/jpeg", "image/jpg": "image/jpeg",
    "application/pdf": "application/pdf", "application/x-pdf": "application/pdf",
}
SUPPORTED_MEDIA_TYPES = ["text/csv", "text/tab-separated-values", "application/json", "text/plain", "text/markdown",
                         "image/png", "image/jpeg", "application/pdf"]
DATA_ORIGINS = ("real_observation", "public_source", "synthetic_example", "hypothetical", "unspecified")
_BIDI = {"‪", "‫", "‬", "‭", "‮", "⁦", "⁧", "⁨", "⁩"}


class Refusal(Exception):
    def __init__(self, code: str, message: str, status: int = 422):
        super().__init__(code)
        self.code, self.message, self.status = code, message, status


def canonical_media_type(header: str | None) -> tuple[str, str]:
    declared = (header or "").split(";")[0].strip().lower()
    if declared not in MEDIA_ALIASES:
        raise Refusal("unsupported_media_type", "Supported files are CSV, TSV, JSON, plain text, Markdown, PNG, JPEG "
                      "and PDF. Send the file with its media type.", 415)
    return declared, MEDIA_ALIASES[declared]


def source_name(header: str | None) -> str | None:
    """Decode an optional percent-encoded UTF-8 file name and keep it as inert display text."""
    if header is None or header == "":
        return None
    if len(header.encode("utf-8")) > L.MAX_SOURCE_NAME_HEADER_BYTES:
        raise Refusal("invalid_source_name", "The file name header is too long.")
    if any(ord(ch) > 0xFF for ch in header):
        decoded = header  # already text (not a latin-1 header value)
    else:
        raw = header.encode("latin-1")
        try:
            decoded = unquote_to_bytes(raw).decode("utf-8") if b"%" in raw else raw.decode("utf-8")
        except UnicodeDecodeError:
            decoded = raw.decode("latin-1")
    name = re.split(r"[\\/]", decoded)[-1]
    name = "".join(ch for ch in name if ch not in _BIDI and unicodedata.category(ch) not in ("Cc", "Cs"))
    name = name.strip()
    if len(name) > L.MAX_SOURCE_NAME_CHARS:
        raise Refusal("invalid_source_name", f"File names are limited to {L.MAX_SOURCE_NAME_CHARS} characters.")
    return name or None


def _signature(raw: bytes) -> str | None:
    if raw.startswith(b"%PDF-"):
        return "application/pdf"
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if raw.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return None


def _version(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "not_installed"


@dataclass
class Parsed:
    media_type: str
    pages: list[dict]
    summary: dict
    text_pages: list[dict]                       # {"page_index", "text", "char_boxes": bytes|None, "quality"}
    blobs: dict[str, bytes] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    active_content: list[str] = field(default_factory=list)
    parser: dict = field(default_factory=dict)
    encoding: str | None = None
    preview_sha256: str | None = None


def _text_page(text: str) -> dict:
    return {"page_index": 0, "page_number": 1, "width": None, "height": None, "dimension_unit": None,
            "rotation": None, "image_sha256": None, "image_media_type": None, "image_width": None,
            "image_height": None, "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "text_layer": "decoded_text", "char_count": len(text)}


def parse(raw: bytes, media_type: str) -> Parsed:
    if not raw:
        raise Refusal("empty_file", "The file is empty.")
    if len(raw) > L.MAX_ASSET_BYTES:
        raise Refusal("file_too_large", f"Each file must be at most {L.MAX_ASSET_BYTES // L.MiB} MiB.", 413)
    observed = _signature(raw)
    binary = media_type in ("image/png", "image/jpeg", "application/pdf")
    if binary and observed != media_type:
        raise Refusal("media_type_mismatch", "The file contents do not match the declared media type.", 415)
    if not binary and observed is not None:
        raise Refusal("media_type_mismatch", "The file is a binary document, not the declared text format.", 415)
    try:
        if media_type == "application/pdf":
            return _parse_pdf(raw)
        if media_type in ("image/png", "image/jpeg"):
            return _parse_image(raw, media_type)
        return _parse_text(raw, media_type)
    except AdmissionRefused as exc:
        raise Refusal(exc.code, exc.message, exc.status) from None
    except ParseRefused as exc:
        raise Refusal(exc.code, exc.message, 415 if exc.code == "media_type_mismatch" else 422) from None


def _parse_text(raw: bytes, media_type: str) -> Parsed:
    text, encoding, warnings = decode_text(raw)
    if media_type in ("text/csv", "text/tab-separated-values"):
        summary = parse_delimited(text, media_type)
    elif media_type == "application/json":
        summary = parse_json_document(text)
    else:
        summary = parse_text(text, media_type)
    return Parsed(media_type, [_text_page(text)], summary,
                  [{"page_index": 0, "text": text, "char_boxes": None, "quality": "usable"}],
                  warnings=warnings + summary.get("warnings", []),
                  parser={"name": "python-stdlib", "version": "csv/json/text"}, encoding=encoding)


def _parse_image(raw: bytes, media_type: str) -> Parsed:
    info = inspect_image(raw)
    if info["media_type"] != media_type:
        raise Refusal("media_type_mismatch", "The image decoder found a different media type.", 415)
    digest = hashlib.sha256(raw).hexdigest()
    page = {"page_index": 0, "page_number": 1, "width": info["display_width"], "height": info["display_height"],
            "dimension_unit": "px", "rotation": None, "image_sha256": digest, "image_media_type": media_type,
            "image_width": info["display_width"], "image_height": info["display_height"], "text_sha256": None,
            "text_layer": "none", "char_count": 0}
    preview = info.get("preview")
    parsed = Parsed(media_type, [page], {
        "kind": "image", "width": info["width"], "height": info["height"], "display_width": info["display_width"],
        "display_height": info["display_height"], "exif_orientation": info["orientation"], "mode": info["mode"],
        "preview_reason": preview["reason"] if preview else None, "ocr": False},
        [{"page_index": 0, "text": "", "char_boxes": None, "quality": "none"}],
        parser={"name": "Pillow", "version": _version("pillow")})
    if preview:
        parsed.blobs[preview["sha256"]] = preview["content"]
        parsed.preview_sha256 = preview["sha256"]
        parsed.warnings.append(f"page_image_is_derived_preview:{preview['reason']}")
    return parsed


def _parse_pdf(raw: bytes) -> Parsed:
    info = inspect_pdf(raw)
    pages, text_pages, blobs = [], [], {}
    for page in info["pages"]:
        image_sha = hashlib.sha256(page["image"]).hexdigest()
        blobs[image_sha] = page["image"]
        quality = page["text_quality"]
        text = page["text"]
        pages.append({"page_index": page["page_index"], "page_number": page["page_index"] + 1,
                      "width": page["width"], "height": page["height"], "dimension_unit": "pt",
                      "rotation": page["rotation"], "image_sha256": image_sha, "image_media_type": "image/png",
                      "image_width": page["image_width"], "image_height": page["image_height"],
                      "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest() if quality != "none" else None,
                      "text_layer": {"usable": "native_pdf_text", "none": "none", "unreliable": "unreliable"}[quality],
                      "char_count": len(text)})
        text_pages.append({"page_index": page["page_index"], "text": text if quality != "none" else "",
                           "char_boxes": page["char_boxes"] if quality != "none" else None, "quality": quality})
    without = [page["page_index"] for page in pages if page["text_layer"] != "native_pdf_text"]
    warnings = [f"page_without_usable_text_layer:{index}" for index in without]
    if info["active_content"]:
        warnings.append("active_content_present_not_executed")
    return Parsed("application/pdf", pages, {
        "kind": "pdf", "page_count": len(pages), "pages_with_text_layer": len(pages) - len(without),
        "pages_without_text_layer": without, "ocr": False, "executes_document_scripts": False},
        text_pages, blobs=blobs, warnings=warnings, active_content=info["active_content"],
        parser={"name": "pypdfium2", "version": f"{info['parser']['version']} ({info['parser']['pdfium']})"})


def encode_text_layer(asset_sha256: str, text_pages: list[dict]) -> dict:
    return {"version": "text-layer.v1", "asset_sha256": asset_sha256, "normalization": L.CITATION_NORMALIZATION_VERSION,
            "pages": [{"page_index": page["page_index"], "text": page["text"], "quality": page["quality"],
                       "char_boxes_b64": base64.b64encode(page["char_boxes"]).decode("ascii")
                       if page["char_boxes"] else None} for page in text_pages]}
