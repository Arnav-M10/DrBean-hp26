"""Bounded structural pre-scan of PDF bytes, run before any PDF library sees the file.

Standard library only; the PDF worker loads this file by path. The scan walks the
file iteratively (no recursion on attacker-controlled nesting), skips stream data
by its declared or recovered extent, and decodes every stream with a bounded
decoder. A file is refused when any stream would decode beyond its limit, when an
image declares more pixels than admitted, when nesting is excessive, or when the
document is encrypted. PDFium afterwards only receives files whose decoded stream
sizes are known to be bounded; the parent's memory watchdog remains a backstop.

JBIG2 and JPEG 2000 image sizes are taken from the image dictionary (and JPEG from
its frame header as well); their codec internals are not parsed here.
"""
from __future__ import annotations

import base64
import re
import zlib

try:
    from . import limits as L
except ImportError:  # loaded by path inside the isolated worker
    import limits as L  # type: ignore[no-redef]


class PrescanError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class Ref(tuple):
    """An indirect reference (object number, generation)."""


ACTIVE_NAMES = {b"/JavaScript": "javascript", b"/JS": "javascript", b"/OpenAction": "open_action",
                b"/AA": "additional_actions", b"/Launch": "launch_action", b"/URI": "uri_action",
                b"/EmbeddedFiles": "embedded_files", b"/AcroForm": "form_fields", b"/XFA": "xfa_form",
                b"/RichMedia": "rich_media", b"/SubmitForm": "submit_form", b"/GoToR": "remote_goto",
                b"/ImportData": "import_data"}
IMAGE_CODECS = {"/DCTDecode", "/DCT", "/JPXDecode", "/JBIG2Decode", "/CCITTFaxDecode", "/CCF"}
COMPONENTS = {"/DeviceGray": 1, "/G": 1, "/CalGray": 1, "/DeviceRGB": 3, "/RGB": 3, "/CalRGB": 3,
              "/Lab": 3, "/DeviceCMYK": 4, "/CMYK": 4, "/Indexed": 1, "/I": 1}

_TOKEN = re.compile(rb"%|\(|<<|>>|<|\[|\]|/[^\s/<>\[\]()%{}]*|(?<![A-Za-z0-9])(?:stream|obj|trailer)(?![A-Za-z0-9])")
_WS = b" \t\r\n\f\x00"
_NUMBER = re.compile(rb"[+-]?(?:\d+\.?\d*|\.\d+)")
_REF_TAIL = re.compile(rb"\s+(\d+)\s+R(?![A-Za-z0-9])")
_WORD = re.compile(rb"[A-Za-z]+")
_DIGITS = re.compile(rb"\d+")
_DELIMS = b"()<>[]{}/%"


# --------------------------------------------------------------------------- small object parser
def _skip_ws(buf: bytes, pos: int) -> int:
    n = len(buf)
    while pos < n:
        ch = buf[pos]
        if ch in _WS:
            pos += 1
        elif ch == 0x25:  # comment
            while pos < n and buf[pos] not in b"\r\n":
                pos += 1
        else:
            break
    return pos


def _literal_end(buf: bytes, pos: int) -> int:
    """Return the index after the literal string starting at ``pos`` (which holds '(')."""
    depth, n, pos = 1, len(buf), pos + 1
    while pos < n:
        ch = buf[pos]
        if ch == 0x5C:  # backslash escape
            pos += 2
            continue
        if ch == 0x28:
            depth += 1
        elif ch == 0x29:
            depth -= 1
            if depth == 0:
                return pos + 1
        pos += 1
    raise PrescanError("malformed_pdf")


def _parse(buf: bytes, pos: int, depth: int = 0):
    """Parse one PDF object from a small dictionary span; depth-bounded."""
    if depth > L.MAX_PDF_NESTING:
        raise PrescanError("pdf_nesting_limit")
    pos = _skip_ws(buf, pos)
    if pos >= len(buf):
        raise PrescanError("malformed_pdf")
    ch = buf[pos]
    if buf.startswith(b"<<", pos):
        result, pos = {}, pos + 2
        while True:
            pos = _skip_ws(buf, pos)
            if buf.startswith(b">>", pos):
                return result, pos + 2
            key, pos = _parse(buf, pos, depth + 1)
            if not (isinstance(key, str) and key.startswith("/")):
                raise PrescanError("malformed_pdf")
            value, pos = _parse(buf, pos, depth + 1)
            result[key] = value
    if ch == 0x5B:  # [
        result, pos = [], pos + 1
        while True:
            pos = _skip_ws(buf, pos)
            if pos < len(buf) and buf[pos] == 0x5D:
                return result, pos + 1
            value, pos = _parse(buf, pos, depth + 1)
            result.append(value)
    if ch == 0x2F:  # name
        end = pos + 1
        while end < len(buf) and buf[end] not in _WS and buf[end] not in _DELIMS:
            end += 1
        return buf[pos:end].decode("latin-1"), end
    if ch == 0x28:
        end = _literal_end(buf, pos)
        return buf[pos + 1:end - 1], end
    if ch == 0x3C:  # hex string
        end = buf.find(b">", pos)
        if end < 0:
            raise PrescanError("malformed_pdf")
        return b"", end + 1
    match = _NUMBER.match(buf, pos)
    if match:
        text, end = match.group(0), match.end()
        ref = _REF_TAIL.match(buf, end)
        if ref and _DIGITS.fullmatch(text):
            return Ref((int(text), int(ref.group(1)))), ref.end()
        return (float(text) if b"." in text else int(text)), end
    match = _WORD.match(buf, pos)
    if match:
        word = match.group(0)
        return {b"true": True, b"false": False, b"null": None}.get(word, word.decode("latin-1")), match.end()
    raise PrescanError("malformed_pdf")


# --------------------------------------------------------------------------- bounded decoders
def _inflate(data: bytes, cap: int, keep: bool = True) -> tuple[bytes, int, bool]:
    """Inflate at most ``cap`` bytes. Returns (output or b"", decoded size, complete)."""
    decoder, out, size = zlib.decompressobj(), bytearray(), 0
    try:
        view, step = memoryview(data), 1 << 16
        for start in range(0, len(data), step):
            chunk = bytes(view[start:start + step])
            while chunk:
                piece = decoder.decompress(chunk, min(1 << 20, cap + 1 - size))
                size += len(piece)
                if size > cap:
                    raise PrescanError("pdf_decompression_limit")
                if keep:
                    out += piece
                chunk = decoder.unconsumed_tail
                if decoder.eof:
                    break
            if decoder.eof:
                break
    except zlib.error:
        raise PrescanError("malformed_pdf_stream") from None
    if decoder.eof and decoder.unused_data.strip(_WS):
        raise PrescanError("malformed_pdf_stream")
    return bytes(out), size, decoder.eof


def _lzw(data: bytes, cap: int, early: int = 1) -> bytes:
    out, table, bits, prev = bytearray(), [bytes([i]) for i in range(256)] + [b"", b""], 9, None
    acc = nacc = 0
    for byte in data:
        acc, nacc = (acc << 8) | byte, nacc + 8
        while nacc >= bits:
            nacc -= bits
            code = (acc >> nacc) & ((1 << bits) - 1)
            if code == 256:
                table, bits, prev = table[:258], 9, None
                continue
            if code == 257:
                return bytes(out)
            if prev is None:
                if code >= len(table):
                    raise PrescanError("malformed_pdf_stream")
                entry = table[code]
            elif code < len(table):
                entry = table[code]
                table.append(prev + entry[:1])
            elif code == len(table):
                entry = prev + prev[:1]
                table.append(entry)
            else:
                raise PrescanError("malformed_pdf_stream")
            out += entry
            if len(out) > cap:
                raise PrescanError("pdf_decompression_limit")
            prev = entry
            if len(table) + early >= (1 << bits) and bits < 12:
                bits += 1
    return bytes(out)


def _run_length(data: bytes, cap: int) -> bytes:
    out, pos, n = bytearray(), 0, len(data)
    while pos < n:
        length = data[pos]
        if length == 128:
            break
        if length < 128:
            out += data[pos + 1:pos + 2 + length]
            pos += length + 2
        else:
            if pos + 1 >= n:
                break
            out += data[pos + 1:pos + 2] * (257 - length)
            pos += 2
        if len(out) > cap:
            raise PrescanError("pdf_decompression_limit")
    return bytes(out)


def _ascii_hex(data: bytes) -> bytes:
    text = re.sub(rb"\s+", b"", data.split(b">", 1)[0])
    if len(text) % 2:
        text += b"0"
    try:
        return bytes.fromhex(text.decode("ascii"))
    except (ValueError, UnicodeDecodeError):
        raise PrescanError("malformed_pdf_stream") from None


def _ascii85(data: bytes) -> bytes:
    text = re.sub(rb"\s+", b"", data)
    if text.startswith(b"<~"):
        text = text[2:]
    text = text.split(b"~>", 1)[0]
    try:
        return base64.a85decode(text)
    except ValueError:
        raise PrescanError("malformed_pdf_stream") from None


def _jpeg_dimensions(data: bytes) -> tuple[int, int] | None:
    pos, n = 2, len(data)
    while pos + 9 < n:
        if data[pos] != 0xFF:
            pos += 1
            continue
        marker = data[pos + 1]
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7 or marker == 0xFF:
            pos += 1 if marker == 0xFF else 2
            continue
        length = int.from_bytes(data[pos + 2:pos + 4], "big")
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            return int.from_bytes(data[pos + 7:pos + 9], "big"), int.from_bytes(data[pos + 5:pos + 7], "big")
        pos += 2 + length
    return None


# --------------------------------------------------------------------------- the scan
def _names(value) -> list:
    if value is None:
        return []
    return [value] if not isinstance(value, list) else value


def _int(value, default=0):
    return value if isinstance(value, int) and not isinstance(value, bool) else default


def _nesting(decoded: bytes) -> None:
    """Iterative nesting check for decoded object streams."""
    depth, pos, n = 0, 0, len(decoded)
    token = re.compile(rb"\(|<<|>>|\[|\]|%")
    while True:
        match = token.search(decoded, pos)
        if not match:
            return
        kind, pos = match.group(0), match.end()
        if kind == b"(":
            pos = _literal_end(decoded, match.start())
        elif kind == b"%":
            while pos < n and decoded[pos] not in b"\r\n":
                pos += 1
        elif kind in (b"<<", b"["):
            depth += 1
            if depth > L.MAX_PDF_NESTING:
                raise PrescanError("pdf_nesting_limit")
        else:
            depth = max(0, depth - 1)


_INLINE_IMAGE = re.compile(rb"(?<![A-Za-z0-9])BI\s(.{0,4096}?)(?<![A-Za-z0-9])ID\s", re.S)
_INLINE_DIM = re.compile(rb"/(W|Width|H|Height)\s+(\d{1,12})")


def prescan_pdf(data: bytes) -> dict:
    if not data.startswith(b"%PDF-") or not re.match(rb"%PDF-[12]\.\d", data):
        raise PrescanError("not_a_pdf")
    report = {"streams": 0, "decoded_bytes": 0, "image_pixels": 0, "objects": 0, "max_nesting": 0,
              "recovered_stream_extents": 0, "incomplete_streams": 0, "active_content": set()}
    n, pos, depth = len(data), 0, 0
    dict_start, last_dict, pending_trailer = None, None, False
    while True:
        match = _TOKEN.search(data, pos)
        if not match:
            break
        token, start, pos = match.group(0), match.start(), match.end()
        if token == b"%":
            while pos < n and data[pos] not in b"\r\n":
                pos += 1
        elif token == b"(":
            pos = _literal_end(data, start)
        elif token == b"<<":
            if depth == 0:
                dict_start = start
            depth += 1
        elif token == b">>":
            depth -= 1
            if depth < 0:
                raise PrescanError("malformed_pdf")
            if depth == 0 and dict_start is not None:
                last_dict = (dict_start, pos)
                if pending_trailer:
                    _check_trailer(_parse(data[dict_start:pos], 0)[0])
                    pending_trailer = False
        elif token == b"<":
            end = data.find(b">", pos)
            if end < 0:
                raise PrescanError("malformed_pdf")
            pos = end + 1
        elif token == b"[":
            depth += 1
        elif token == b"]":
            depth = max(0, depth - 1)
        elif token == b"obj":
            report["objects"] += 1
            depth = 0
        elif token == b"trailer":
            pending_trailer = True
        elif token == b"stream":
            pos = _stream(data, start, pos, last_dict, report)
            depth, last_dict = 0, None
            continue
        else:  # a name
            feature = ACTIVE_NAMES.get(token)
            if feature:
                report["active_content"].add(feature)
            if token == b"/Encrypt" and pending_trailer:
                raise PrescanError("encrypted_pdf")
        if depth > L.MAX_PDF_NESTING:
            raise PrescanError("pdf_nesting_limit")
        report["max_nesting"] = max(report["max_nesting"], depth)
        if report["objects"] > L.MAX_PDF_OBJECTS:
            raise PrescanError("pdf_object_limit")
    if report["objects"] == 0:
        raise PrescanError("malformed_pdf")
    report["active_content"] = sorted(report["active_content"])
    return report


def _check_trailer(trailer) -> None:
    if not isinstance(trailer, dict):
        raise PrescanError("malformed_pdf")
    if "/Encrypt" in trailer:
        raise PrescanError("encrypted_pdf")
    size = trailer.get("/Size")
    if isinstance(size, int) and size > L.MAX_PDF_DECLARED_SIZE:
        raise PrescanError("pdf_object_limit")


def _resolve_length(data: bytes, ref: Ref) -> int | None:
    pattern = re.compile(rb"(?<![0-9])%d\s+%d\s+obj\s*(\d{1,12})\s*endobj" % (ref[0], ref[1]))
    match = pattern.search(data)
    return int(match.group(1)) if match else None


def _stream(data: bytes, keyword_start: int, after_keyword: int, last_dict, report: dict) -> int:
    if last_dict is None or data[last_dict[1]:keyword_start].strip(_WS):
        raise PrescanError("malformed_pdf")
    info, _ = _parse(data[last_dict[0]:last_dict[1]], 0)
    if not isinstance(info, dict):
        raise PrescanError("malformed_pdf")
    begin = after_keyword
    if data.startswith(b"\r\n", begin):
        begin += 2
    elif data[begin:begin + 1] in (b"\n", b"\r"):
        begin += 1
    length = info.get("/Length")
    if isinstance(length, Ref):
        length = _resolve_length(data, length)
    end, exact = None, False
    if isinstance(length, int) and not isinstance(length, bool) and 0 <= length <= len(data) - begin:
        tail = begin + length
        if data[tail:tail + 32].lstrip(_WS).startswith(b"endstream"):
            end, exact = tail, True
    if end is None:
        found = data.find(b"endstream", begin)
        if found < 0:
            raise PrescanError("malformed_pdf")
        end = found
        while end > begin and data[end - 1] in b"\r\n":
            end -= 1
        report["recovered_stream_extents"] += 1
    resume = data.find(b"endstream", end) + len(b"endstream")
    report["streams"] += 1
    _decode_stream(info, data[begin:end], exact, report)
    return resume


def _image_pixels(info: dict, encoded: bytes, codec: str | None) -> int:
    width, height = _int(info.get("/Width", info.get("/W"))), _int(info.get("/Height", info.get("/H")))
    if codec in ("/DCTDecode", "/DCT"):
        dims = _jpeg_dimensions(encoded)
        if dims:
            width, height = max(width, dims[0]), max(height, dims[1])
    return width * height


def _components(info: dict) -> int:
    space = info.get("/ColorSpace", info.get("/CS"))
    if info.get("/ImageMask") is True:
        return 1
    if isinstance(space, list) and space and isinstance(space[0], str):
        space = space[0]
    return COMPONENTS.get(space, 4) if isinstance(space, str) else 4


def _decode_stream(info: dict, encoded: bytes, exact: bool, report: dict) -> None:
    kind, subtype = info.get("/Type"), info.get("/Subtype")
    if kind == "/XRef":
        _check_trailer(info)
    declared = _names(info.get("/Filter", info.get("/F") if subtype == "/Image" else None))
    filters = [f for f in declared if isinstance(f, str)]
    if len(filters) != len(declared) or len(filters) > 4:
        raise PrescanError("malformed_pdf")
    params = _names(info.get("/DecodeParms", info.get("/DP")))
    is_image = subtype == "/Image" or any(name in IMAGE_CODECS for name in filters)
    cap = L.MAX_PDF_STREAM_DECODED_BYTES
    if is_image:
        pixels = _image_pixels(info, b"", None)
        if pixels > L.MAX_PDF_IMAGE_PIXELS:
            raise PrescanError("pdf_image_pixel_limit")
        bits = max(1, min(16, _int(info.get("/BitsPerComponent", info.get("/BPC")), 8)))
        cap = max(cap, (pixels * _components(info) * bits + 7) // 8 + 4096)
    decoded, size, codec = encoded, len(encoded), None
    for index, name in enumerate(filters):
        last = index == len(filters) - 1
        keep = not (last and (is_image or kind == "/XRef"))
        if name in ("/FlateDecode", "/Fl"):
            decoded, size, complete = _inflate(decoded, cap, keep)
            if not complete:
                if not exact:
                    raise PrescanError("malformed_pdf_stream")
                report["incomplete_streams"] += 1
        elif name in ("/LZWDecode", "/LZW"):
            param = params[index] if index < len(params) and isinstance(params[index], dict) else {}
            decoded = _lzw(decoded, cap, _int(param.get("/EarlyChange", 1), 1))
            size = len(decoded)
        elif name in ("/ASCIIHexDecode", "/AHx"):
            decoded = _ascii_hex(decoded)
            size = len(decoded)
        elif name in ("/ASCII85Decode", "/A85"):
            decoded = _ascii85(decoded)
            size = len(decoded)
        elif name in ("/RunLengthDecode", "/RL"):
            decoded = _run_length(decoded, cap)
            size = len(decoded)
        elif name in IMAGE_CODECS:
            if not last:
                raise PrescanError("unsupported_pdf_filter")
            codec = name
        elif name == "/Crypt":
            raise PrescanError("encrypted_pdf")
        else:
            raise PrescanError("unsupported_pdf_filter")
    if is_image:
        pixels = _image_pixels(info, decoded if codec else b"", codec)
        if pixels > L.MAX_PDF_IMAGE_PIXELS:
            raise PrescanError("pdf_image_pixel_limit")
        report["image_pixels"] += pixels
        if report["image_pixels"] > L.MAX_PDF_PAGE_IMAGE_PIXELS * L.MAX_PDF_PAGES:
            raise PrescanError("pdf_image_pixel_limit")
        report["decoded_bytes"] += max(size, pixels * _components(info))
    else:
        report["decoded_bytes"] += size
        if kind == "/ObjStm":
            _nesting(decoded)
            report["objects"] += _int(info.get("/N"))
            for name, feature in ACTIVE_NAMES.items():
                if re.search(re.escape(name) + rb"(?![A-Za-z0-9])", decoded):
                    report["active_content"].add(feature)
            if re.search(rb"/Encrypt(?![A-Za-z0-9])", decoded) and re.search(rb"/Type\s*/XRef", decoded):
                raise PrescanError("encrypted_pdf")
        elif kind != "/XRef" and b"BI" in decoded:
            for inline in _INLINE_IMAGE.finditer(decoded):
                dims = {key: int(value) for key, value in _INLINE_DIM.findall(inline.group(1))}
                width = dims.get(b"W", dims.get(b"Width", 0))
                height = dims.get(b"H", dims.get(b"Height", 0))
                if width * height > L.MAX_PDF_IMAGE_PIXELS:
                    raise PrescanError("pdf_image_pixel_limit")
    if report["decoded_bytes"] > L.MAX_PDF_TOTAL_DECODED_BYTES:
        raise PrescanError("pdf_decompression_limit")
