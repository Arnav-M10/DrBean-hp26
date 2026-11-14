"""Private fixed-path PDF worker process. Reads one command line plus the PDF bytes on stdin.

It never executes document JavaScript, opens attachments, follows links or launch
actions, fetches anything, or receives credentials (the parent passes a minimal
environment). Output is one JSON object on stdout or one fixed error code on stderr.
"""
import base64
import hashlib
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from resource_policy import ResourceSetupError, apply_limits  # noqa: E402
import limits as L  # noqa: E402  (sibling module; this file is run directly, never imported)

KNOWN = {"encrypted_pdf", "page_limit", "malformed_pdf", "empty_pdf", "page_out_of_range", "selection_limit",
         "render_pixel_limit", "decoder_setup_failed", "source_too_large", "invalid_command", "resource_limit"}


def fail(code):
    raise ValueError(code)


def read_input():
    header = sys.stdin.buffer.readline(4096)
    try:
        command = json.loads(header)
    except ValueError:
        fail("invalid_command")
    raw = sys.stdin.buffer.read(L.MAX_PAPER_BYTES + 1)
    if not raw:
        fail("empty_pdf")
    if len(raw) > L.MAX_PAPER_BYTES:
        fail("source_too_large")
    return command, raw


def open_reader(raw):
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError
    try:
        reader = PdfReader(io.BytesIO(raw), strict=False)
        if reader.is_encrypted:
            fail("encrypted_pdf")
        count = len(reader.pages)
    except ValueError:
        raise
    except (PdfReadError, Exception):
        fail("malformed_pdf")
    if count == 0:
        fail("empty_pdf")
    if count > L.MAX_PAGES:
        fail("page_limit")
    return reader, count


def number(value):
    # Exact enough for display and transforms; strings keep the manifest free of floats.
    return format(float(value), ".3f").rstrip("0").rstrip(".")


def document_features(reader):
    root = reader.trailer.get("/Root", {})
    names = root.get("/Names", {}) if hasattr(root, "get") else {}
    found = []
    try:
        if "/JavaScript" in names or "/OpenAction" in root or "/AA" in root:
            found.append("document_actions_present_not_executed")
        if "/EmbeddedFiles" in names:
            found.append("attachments_present_not_opened")
        if "/AcroForm" in root:
            found.append("form_fields_present_not_evaluated")
    except Exception:  # feature detection is advisory only
        found.append("document_structure_partly_unreadable")
    return found


def inspect(raw):
    import pypdf
    import pypdfium2
    reader, count = open_reader(raw)
    try:
        labels = list(reader.page_labels)
    except Exception:
        labels = [str(i + 1) for i in range(count)]
    total, pages = 0, []
    for index, page in enumerate(reader.pages):
        warnings = []
        box = page.mediabox
        rotation = int(page.get("/Rotate", 0) or 0) % 360
        try:
            text = page.extract_text() or ""
        except Exception:
            text, warnings = "", ["text_extraction_failed"]
        text = text.replace("\x00", "")
        if len(text) > L.MAX_TEXT_CHARS_PER_PAGE:
            text = text[:L.MAX_TEXT_CHARS_PER_PAGE]
            warnings.append("text_truncated_at_page_limit")
        if total + len(text) > L.MAX_TEXT_CHARS_TOTAL:
            text = text[:max(0, L.MAX_TEXT_CHARS_TOTAL - total)]
            warnings.append("text_truncated_at_document_limit")
        total += len(text)
        meaningful = sum(ch.isalnum() for ch in text)
        if meaningful < L.MIN_TEXT_CHARS_FOR_TEXT_LAYER:
            warnings.append("no_useful_text_layer")
        try:
            if page.get("/Annots"):
                warnings.append("annotations_present_not_followed")
        except Exception:
            pass
        label = str(labels[index] if index < len(labels) else index + 1)[:L.MAX_LABEL_CHARS]
        pages.append({"physical_page": index + 1, "printed_label": label,
                      "width_pt": number(box.width), "height_pt": number(box.height),
                      "origin_pt": [number(box.left), number(box.bottom)], "rotation": rotation,
                      "text": text, "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                      "text_chars": len(text), "has_text_layer": meaningful >= L.MIN_TEXT_CHARS_FOR_TEXT_LAYER,
                      "warnings": warnings})
    return {"page_count": count, "pages": pages, "document_warnings": document_features(reader),
            "parser": {"name": "pypdf", "version": pypdf.__version__},
            "renderer": {"name": "pypdfium2", "version": pypdfium2.version.PYPDFIUM_INFO.api_tag
                         if hasattr(pypdfium2, "version") else "unknown",
                         "pdfium": str(pypdfium2.PDFIUM_INFO)}}


def render(raw, command):
    import pypdfium2
    open_reader(raw)  # same admission rules (encryption, page count) before rendering
    page_number, scale = command.get("page"), float(command.get("scale", L.DEFAULT_RENDER_SCALE))
    if not 0 < scale <= L.MAX_RENDER_SCALE:
        fail("invalid_command")
    document = pypdfium2.PdfDocument(raw)  # forms are never initialised, so no form JavaScript runs
    try:
        if type(page_number) is not int or not 1 <= page_number <= len(document):
            fail("page_out_of_range")
        page = document[page_number - 1]
        width, height = page.get_size()
        rotation = page.get_rotation()
        if rotation in (90, 270):
            width, height = height, width
        if width * height * scale * scale > L.MAX_RENDER_PIXELS:
            scale = (L.MAX_RENDER_PIXELS / (width * height)) ** 0.5 * 0.995  # pdfium rounds pixel sizes up
        bitmap = page.render(scale=scale, may_draw_forms=False)
        image = bitmap.to_pil()
        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=False)
        png = buffer.getvalue()
    finally:
        document.close()
    return {"page": page_number, "scale": number(scale), "rotation": rotation, "width_px": image.width,
            "height_px": image.height, "png_sha256": hashlib.sha256(png).hexdigest(),
            "png_base64": base64.b64encode(png).decode("ascii")}


def subset(raw, command):
    from pypdf import PdfWriter
    reader, count = open_reader(raw)
    selected = command.get("pages")
    if (not isinstance(selected, list) or not selected or len(selected) > L.MAX_PAGES_PER_BATCH
            or len(set(selected)) != len(selected) or any(type(p) is not int for p in selected)):
        fail("selection_limit")
    if any(not 1 <= p <= count for p in selected):
        fail("page_out_of_range")
    writer = PdfWriter()
    for physical in selected:
        writer.add_page(reader.pages[physical - 1])
    # The derived subset carries page content only: no links, annotations, actions or attachments.
    for page in writer.pages:
        if "/Annots" in page:
            del page["/Annots"]
        if "/AA" in page:
            del page["/AA"]
    writer.add_metadata({"/Producer": "Dr. Bean page subset"})
    buffer = io.BytesIO()
    writer.write(buffer)
    data = buffer.getvalue()
    return {"pages": selected, "subset_sha256": hashlib.sha256(data).hexdigest(), "byte_size": len(data),
            "subset_base64": base64.b64encode(data).decode("ascii")}


def main():
    command, raw = read_input()
    operation = command.get("operation")
    if operation not in L.WORKER_CPU_SECONDS:
        fail("invalid_command")
    apply_limits(cpu_seconds=L.WORKER_CPU_SECONDS[operation], memory_bytes=L.WORKER_MEMORY_BYTES, open_files=64)
    result = inspect(raw) if operation == "inspect" else render(raw, command) if operation == "render" else subset(raw, command)
    sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # only fixed codes leave this process; never document content or tracebacks
        code = ("decoder_setup_failed" if isinstance(exc, ResourceSetupError)
                else str(exc) if isinstance(exc, ValueError) and str(exc) in KNOWN
                else "resource_limit" if isinstance(exc, MemoryError)
                else "decoder_setup_failed" if isinstance(exc, ImportError) else "malformed_pdf")
        print(code, file=sys.stderr)
        raise SystemExit(1) from None
