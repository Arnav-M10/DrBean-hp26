"""Parent-side calls into the isolated PDF and image workers.

The workers return fixed refusal codes; this module converts them into
``AdmissionRefused`` with a human message and validates every worker envelope
before anything is stored. No worker output is trusted as instructions.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
from pathlib import Path
import re

from . import limits as L
from .sandbox import WorkerLimitExceeded, run_worker

HERE = Path(__file__).resolve().parent

MESSAGES = {
    "not_a_pdf": "The file does not start with a PDF header. Upload the original PDF.",
    "malformed_pdf": "The PDF is damaged or not a supported PDF structure.",
    "malformed_pdf_stream": "A compressed part of the PDF is damaged.",
    "encrypted_pdf": "The PDF is encrypted or password protected. Remove the protection and upload it again.",
    "unsupported_pdf_security": "The PDF uses an unsupported security handler.",
    "pdf_page_limit": f"The PDF has more than {L.MAX_PDF_PAGES} pages. Upload at most {L.MAX_PDF_PAGES} pages.",
    "empty_pdf": "The PDF contains no pages.",
    "pdf_decompression_limit": "The PDF expands beyond the admitted decoding limit (possible decompression bomb).",
    "pdf_image_pixel_limit": "An image inside the PDF declares more pixels than admitted.",
    "pdf_nesting_limit": "The PDF nests objects more deeply than admitted.",
    "pdf_object_limit": "The PDF declares more objects than admitted.",
    "unsupported_pdf_filter": "The PDF uses an unsupported compression filter.",
    "pdf_page_dimension_limit": "A PDF page is larger or smaller than the admitted page dimensions.",
    "pdf_text_limit": "A PDF page has more text than admitted; nothing was truncated.",
    "pdf_render_failed": "A PDF page could not be rendered within the admitted image bounds.",
    "malformed_image": "The image is damaged or not a supported PNG/JPEG.",
    "image_pixel_limit": f"The image exceeds {L.MAX_IMAGE_PIXELS:,} pixels or {L.MAX_IMAGE_SIDE_PX} pixels per side.",
    "animated_image_unsupported": "Animated or multi-frame images are not supported.",
    "image_mode_unsupported": "The image color mode is not supported.",
    "source_too_large": f"Each PDF must be at most {L.MAX_PDF_BYTES // L.MiB} MiB and each other file at most {L.MAX_ASSET_BYTES // L.MiB} MiB.",
    "worker_timeout": "Parsing the file exceeded its time limit.",
    "worker_memory_limit": "Parsing the file exceeded its memory limit.",
    "worker_output_limit": "Parsing the file produced more output than admitted.",
    "resource_limit": "Parsing the file exceeded its resource limits.",
    "decoder_setup_failed": "The isolated parser could not start with its required guards.",
    "worker_memory_guard_unavailable": "No effective memory guard is available on this platform.",
}
INFRASTRUCTURE = {"decoder_setup_failed", "worker_memory_guard_unavailable", "invalid_command"}


class AdmissionRefused(Exception):
    def __init__(self, code: str, status: int = 422):
        self.code = code
        self.message = MESSAGES.get(code, "The file could not be admitted.")
        self.status = 503 if code in INFRASTRUCTURE else status
        super().__init__(code)


def _call(kind: str, data: bytes) -> dict:
    script = HERE / ("_pdf_worker.py" if kind == "pdf" else "_image_worker.py")
    try:
        outcome = run_worker(script, json.dumps({"operation": "inspect"}).encode(), data,
                             timeout=L.WORKER_TIMEOUT_SECONDS[kind], memory_bytes=L.WORKER_MEMORY_BYTES,
                             output_bytes=L.WORKER_OUTPUT_BYTES, poll_seconds=L.WORKER_POLL_SECONDS)
    except WorkerLimitExceeded as exc:
        raise AdmissionRefused(exc.code) from None
    except OSError:
        raise AdmissionRefused("decoder_setup_failed") from None
    if outcome.returncode:
        lines = outcome.stderr.decode("utf-8", "replace").strip().splitlines()
        code = lines[-1].strip() if lines else "malformed_pdf" if kind == "pdf" else "malformed_image"
        if code not in MESSAGES and code != "invalid_command":
            code = "malformed_pdf" if kind == "pdf" else "malformed_image"
        raise AdmissionRefused(code)
    try:
        result = json.loads(outcome.stdout)
    except ValueError:
        raise AdmissionRefused("decoder_setup_failed") from None
    if not isinstance(result, dict):
        raise AdmissionRefused("decoder_setup_failed")
    result["guard"] = outcome.guard
    return result


def _b64(value: str, limit: int) -> bytes:
    if not isinstance(value, str) or len(value) > limit * 4 // 3 + 8:
        raise AdmissionRefused("decoder_setup_failed")
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError):
        raise AdmissionRefused("decoder_setup_failed") from None


_DECIMAL = re.compile(r"\d{1,5}(?:\.\d{1,3})?")


def inspect_pdf(data: bytes) -> dict:
    """Return validated pages: text, char boxes (bytes), page image (bytes) and dimensions."""
    result = _call("pdf", data)
    pages = result.get("pages")
    if (not isinstance(pages, list) or result.get("page_count") != len(pages)
            or not 1 <= len(pages) <= L.MAX_PDF_PAGES):
        raise AdmissionRefused("decoder_setup_failed")
    checked = []
    for index, page in enumerate(pages):
        render = page.get("render") if isinstance(page, dict) else None
        if (not isinstance(render, dict) or page.get("page_index") != index
                or not isinstance(page.get("text"), str)
                or not all(isinstance(page.get(k), str) and _DECIMAL.fullmatch(page[k])
                           for k in ("width_pt", "height_pt"))
                or page.get("rotation") not in (0, 90, 180, 270)
                or page.get("text_quality") not in ("usable", "none", "unreliable")):
            raise AdmissionRefused("decoder_setup_failed")
        boxes = _b64(page.get("char_boxes"), 8 * L.MAX_PDF_TEXT_CHARS_PER_PAGE)
        png = _b64(render.get("png_base64"), L.WORKER_OUTPUT_BYTES)
        if (len(boxes) != 8 * len(page["text"]) or hashlib.sha256(png).hexdigest() != render.get("sha256")
                or not png.startswith(b"\x89PNG\r\n\x1a\n")
                or not all(type(render.get(k)) is int and 1 <= render[k] <= L.RENDER_MAX_SIDE_PX
                           for k in ("width_px", "height_px"))):
            raise AdmissionRefused("decoder_setup_failed")
        checked.append({"page_index": index, "width": page["width_pt"], "height": page["height_pt"],
                        "rotation": page["rotation"], "text": page["text"], "char_boxes": boxes,
                        "text_quality": page["text_quality"], "image": png,
                        "image_width": render["width_px"], "image_height": render["height_px"]})
    active = result.get("active_content")
    if not isinstance(active, list) or not all(isinstance(item, str) and len(item) < 40 for item in active):
        raise AdmissionRefused("decoder_setup_failed")
    parser = result.get("parser") if isinstance(result.get("parser"), dict) else {}
    return {"pages": checked, "active_content": active, "prescan": result.get("prescan", {}),
            "parser": {"name": "pypdfium2", "version": str(parser.get("version", "unknown"))[:40],
                       "pdfium": str(parser.get("pdfium", "unknown"))[:60]}, "guard": result["guard"]}


def inspect_image(data: bytes) -> dict:
    result = _call("image", data)
    required = {"media_type", "width", "height", "display_width", "display_height", "orientation", "mode"}
    if not required <= set(result) or result["media_type"] not in ("image/png", "image/jpeg"):
        raise AdmissionRefused("decoder_setup_failed")
    if not all(type(result[k]) is int and 1 <= result[k] <= L.MAX_IMAGE_SIDE_PX
               for k in ("width", "height", "display_width", "display_height")):
        raise AdmissionRefused("decoder_setup_failed")
    preview = result.get("preview")
    if preview is not None:
        if not isinstance(preview, dict) or preview.get("media_type") not in ("image/png", "image/jpeg"):
            raise AdmissionRefused("decoder_setup_failed")
        content = _b64(preview.get("base64"), L.WORKER_OUTPUT_BYTES)
        if (hashlib.sha256(content).hexdigest() != preview.get("sha256")
                or not all(type(preview.get(k)) is int and 1 <= preview[k] <= L.RENDER_MAX_SIDE_PX
                           for k in ("width", "height"))):
            raise AdmissionRefused("decoder_setup_failed")
        preview = {**preview, "content": content}
        preview.pop("base64")
    return {**result, "preview": preview}
