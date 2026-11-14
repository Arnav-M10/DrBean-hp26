"""Isolated fixed-path PDF worker: bounded pre-scan, PDFium text layer with boxes, bounded page images.

Run as ``python -I _pdf_worker.py`` by ``sandbox.run_worker``. Reads one JSON command
line, then the PDF bytes, from stdin. Writes one JSON object to stdout, or one fixed
error code to stderr. It never initialises forms, runs document JavaScript, opens
attachments, follows links or launch actions, fetches anything, or receives
credentials. Sibling modules are loaded by explicit path: the application package
directory is never placed on ``sys.path`` (its ``http.py`` would shadow the stdlib).
"""
import base64
import ctypes
import hashlib
import importlib.util
import io
import json
import math
import os
import sys
from array import array

HERE = os.path.dirname(os.path.abspath(__file__))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


L = _load("limits", os.path.join(HERE, "limits.py"))
P = _load("_prescan", os.path.join(HERE, "_prescan.py"))
R = _load("resource_policy", os.path.join(os.path.dirname(HERE), "resource_policy.py"))

KNOWN = {"not_a_pdf", "malformed_pdf", "malformed_pdf_stream", "encrypted_pdf", "pdf_page_limit", "empty_pdf",
         "pdf_decompression_limit", "pdf_image_pixel_limit", "pdf_nesting_limit", "pdf_object_limit",
         "unsupported_pdf_filter", "pdf_page_dimension_limit", "pdf_text_limit", "source_too_large",
         "invalid_command", "decoder_setup_failed", "resource_limit", "pdf_render_failed",
         "unsupported_pdf_security"}
NONE_BOX = 0xFFFF
SCALE = 10_000


class Refused(ValueError):
    pass


def number(value):
    return format(float(value), ".3f").rstrip("0").rstrip(".")


def device_box(raw, page, size_x, size_y, left, bottom, right, top):
    xs, ys = [], []
    out_x, out_y = ctypes.c_int(), ctypes.c_int()
    for x, y in ((left, bottom), (left, top), (right, bottom), (right, top)):
        raw.FPDF_PageToDevice(page, 0, 0, size_x, size_y, 0, ctypes.c_double(x), ctypes.c_double(y),
                              ctypes.byref(out_x), ctypes.byref(out_y))
        xs.append(out_x.value / size_x)
        ys.append(out_y.value / size_y)
    clamp = lambda v: max(0, min(SCALE, int(round(v * SCALE))))  # noqa: E731
    return clamp(min(xs)), clamp(min(ys)), clamp(max(xs)), clamp(max(ys))


def text_layer(raw, pdfium, page, width, height):
    textpage = page.get_textpage()
    try:
        count = textpage.count_chars()
        if count > L.MAX_PDF_TEXT_CHARS_PER_PAGE:
            raise Refused("pdf_text_limit")
        longer = max(width, height)
        size_x, size_y = max(1, round(SCALE * width / longer)), max(1, round(SCALE * height / longer))
        chars, boxes = [], array("H")
        left, right, bottom, top = (ctypes.c_double() for _ in range(4))
        index = 0
        while index < count:
            code = raw.FPDFText_GetUnicode(textpage.raw, index)
            step = 1
            if 0xD800 <= code <= 0xDBFF and index + 1 < count:
                low = raw.FPDFText_GetUnicode(textpage.raw, index + 1)
                if 0xDC00 <= low <= 0xDFFF:
                    code, step = 0x10000 + ((code - 0xD800) << 10) + (low - 0xDC00), 2
            if code == 2:  # PDFium marks a line-end hyphenation point with U+0002
                code = 0x00AD
            elif code in (0, 0xFFFE, 0xFFFF) or 0xD800 <= code <= 0xDFFF or code > 0x10FFFF or (
                    code < 0x20 and code not in (9, 10, 13)):
                code = 0xFFFD
            chars.append(chr(code))
            generated = raw.FPDFText_IsGenerated(textpage.raw, index) == 1
            has_box = (not generated and raw.FPDFText_GetCharBox(textpage.raw, index, ctypes.byref(left),
                       ctypes.byref(right), ctypes.byref(bottom), ctypes.byref(top)))
            if has_box and right.value > left.value and top.value > bottom.value and chr(code).strip():
                boxes.extend(device_box(raw, page.raw, size_x, size_y, left.value, bottom.value, right.value,
                                        top.value))
            else:
                boxes.extend((NONE_BOX,) * 4)
            index += step
    finally:
        textpage.close()
    text = "".join(chars)
    if sys.byteorder != "little":
        boxes.byteswap()
    return text, base64.b64encode(boxes.tobytes()).decode("ascii")


def render(page, width, height):
    scale = min(L.RENDER_MAX_SIDE_PX / max(width, height), math.sqrt(L.RENDER_MAX_PIXELS / (width * height)),
                L.RENDER_MAX_SCALE) * 0.995
    bitmap = page.render(scale=scale, may_draw_forms=False)
    try:
        image = bitmap.to_pil().convert("RGB")
    finally:
        bitmap.close()
    if image.width > L.RENDER_MAX_SIDE_PX or image.height > L.RENDER_MAX_SIDE_PX:
        raise Refused("pdf_render_failed")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", compress_level=6)
    png = buffer.getvalue()
    return {"png_base64": base64.b64encode(png).decode("ascii"), "sha256": hashlib.sha256(png).hexdigest(),
            "width_px": image.width, "height_px": image.height, "scale": number(scale), "media_type": "image/png"}


def inspect(raw_bytes):
    report = P.prescan_pdf(raw_bytes)
    import pypdfium2 as pdfium
    import pypdfium2.raw as raw
    try:
        document = pdfium.PdfDocument(raw_bytes)
    except pdfium.PdfiumError as exc:
        code = getattr(exc, "err_code", None)
        if code is None:
            code = raw.FPDF_GetLastError()
        raise Refused({raw.FPDF_ERR_PASSWORD: "encrypted_pdf",
                       raw.FPDF_ERR_SECURITY: "unsupported_pdf_security"}.get(code, "malformed_pdf")) from None
    try:
        count = len(document)
        if count == 0:
            raise Refused("empty_pdf")
        if count > L.MAX_PDF_PAGES:
            raise Refused("pdf_page_limit")
        pages, total_chars = [], 0
        for index in range(count):
            page = document[index]
            try:
                width, height = page.get_size()
                if not (L.MIN_PDF_PAGE_SIDE_POINTS <= width <= L.MAX_PDF_PAGE_SIDE_POINTS
                        and L.MIN_PDF_PAGE_SIDE_POINTS <= height <= L.MAX_PDF_PAGE_SIDE_POINTS):
                    raise Refused("pdf_page_dimension_limit")
                text, boxes = text_layer(raw, pdfium, page, width, height)
                total_chars += len(text)
                if total_chars > L.MAX_PDF_TEXT_CHARS_TOTAL:
                    raise Refused("pdf_text_limit")
                visible = [ch for ch in text if not ch.isspace()]
                alnum = sum(ch.isalnum() for ch in visible)
                replaced = text.count("�")
                quality = ("none" if alnum < L.MIN_TEXT_LAYER_ALNUM
                           else "unreliable" if visible and replaced * 10 > len(visible) else "usable")
                pages.append({"page_index": index, "width_pt": number(width), "height_pt": number(height),
                              "rotation": page.get_rotation(), "text": text, "char_boxes": boxes,
                              "text_quality": quality, "alnum_chars": alnum, "replacement_chars": replaced,
                              "render": render(page, width, height)})
            finally:
                page.close()
    finally:
        document.close()
    return {"page_count": count, "pages": pages,
            "prescan": {key: report[key] for key in ("streams", "decoded_bytes", "image_pixels", "objects",
                                                      "max_nesting", "recovered_stream_extents",
                                                      "incomplete_streams")},
            "active_content": report["active_content"],
            "parser": {"name": "pypdfium2", "version": pdfium.version.PYPDFIUM_INFO.api_tag
                       if hasattr(pdfium.version.PYPDFIUM_INFO, "api_tag") else str(pdfium.version.PYPDFIUM_INFO),
                       "pdfium": str(pdfium.version.PDFIUM_INFO)}}


def main():
    header = sys.stdin.buffer.readline(4096)
    try:
        command = json.loads(header)
    except ValueError:
        raise Refused("invalid_command") from None
    if not isinstance(command, dict) or command.get("operation") != "inspect":
        raise Refused("invalid_command")
    R.apply_limits(cpu_seconds=L.WORKER_CPU_SECONDS["pdf"], memory_bytes=L.WORKER_MEMORY_BYTES, open_files=64)
    data = sys.stdin.buffer.read(L.MAX_ASSET_BYTES + 1)
    if len(data) > L.MAX_ASSET_BYTES:
        raise Refused("source_too_large")
    result = inspect(data)
    sys.stdout.write(json.dumps(result, ensure_ascii=True, separators=(",", ":")))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # only fixed codes leave this process; never document content or tracebacks
        if isinstance(exc, P.PrescanError):
            code = exc.code
        elif isinstance(exc, Refused):
            code = str(exc)
        elif isinstance(exc, R.ResourceSetupError):
            code = "decoder_setup_failed"
        elif isinstance(exc, MemoryError):
            code = "resource_limit"
        elif isinstance(exc, ImportError):
            code = "decoder_setup_failed"
        else:
            code = "malformed_pdf"
        print(code if code in KNOWN else "malformed_pdf", file=sys.stderr)
        raise SystemExit(1) from None
