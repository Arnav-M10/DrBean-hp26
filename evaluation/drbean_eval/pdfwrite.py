"""Minimal deterministic PDF writer for synthetic papers and hostile-PDF assets (standard library only).

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
                 producer: str = "drbean-eval synthetic corpus (no timestamps)"):
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
            kids.append(self.add_object(b"<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.0f %.0f] /Resources %s "
                                        b"/Contents %d 0 R%s >>" % (pages_number, page.width, page.height, resources,
                                                                    content, annots)))
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
