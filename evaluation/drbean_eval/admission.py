"""Generates negative source-admission assets (work order section 4).

The application caps to test are: one asset, at most 5 MiB, image at most 12
megapixels. PDF is not the selected modality, so PDF caps are listed as unrun
by decision. Assets are generated on demand (several are large) and are
synthetic. Admission itself is Owner 02's implementation.
"""
from __future__ import annotations

import os
import random
import struct
import zlib

MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 12_000_000


def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def png(width: int, height: int, noise: bool = False, declared: tuple[int, int] | None = None) -> bytes:
    """A valid 8-bit greyscale PNG. `declared` lies about the size in IHDR (decompression-cost control)."""
    rng = random.Random(4)
    row = lambda: b"\0" + (rng.randbytes(width) if noise else b"\xff" * width)  # noqa: E731
    raw = b"".join(row() for _ in range(height))
    w, h = declared or (width, height)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0))
            + _chunk(b"IDAT", zlib.compress(raw, 1 if noise else 9)) + _chunk(b"IEND", b""))


CASES = [
    ("ADM-01", "oversize.png", "valid PNG larger than 5 MiB", "rejected_too_large",
     lambda good: png(2400, 2300, noise=True)),
    ("ADM-02", "over_12_megapixels.png", "valid small-file PNG of 4001x3000 = 12.003 MP", "rejected_too_many_pixels",
     lambda good: png(4001, 3000)),
    ("ADM-03", "header_claims_huge.png", "IHDR declares 30000x30000 over a tiny stream; must be refused from "
     "metadata before any decode", "rejected_too_many_pixels", lambda good: png(8, 8, declared=(30000, 30000))),
    ("ADM-04", "truncated.png", "frozen sheet c01a cut at 40% of its bytes", "rejected_corrupt",
     lambda good: good[: len(good) * 2 // 5]),
    ("ADM-05", "bitflip.png", "frozen sheet c01a with corrupted image data (CRC mismatch)", "rejected_corrupt",
     lambda good: good[:2000] + bytes(b ^ 0xFF for b in good[2000:2064]) + good[2064:]),
    ("ADM-06", "pdf_named.png", "PDF bytes under a .png name and image/png content type",
     "rejected_type_mismatch", lambda good: b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"),
    ("ADM-07", "script.svg", "SVG with an embedded script and external reference", "rejected_unsupported_type",
     lambda good: b'<svg xmlns="http://www.w3.org/2000/svg"><script>fetch("http://example.invalid/x")</script>'
                  b'<image href="http://example.invalid/y.png"/></svg>'),
    ("ADM-08", "empty.png", "zero bytes", "rejected_corrupt", lambda good: b""),
    ("ADM-09", "animated.gif", "GIF, a format outside the selected modality", "rejected_unsupported_type",
     lambda good: b"GIF89a\x01\x00\x01\x00\x00\x00\x00;"),
    ("ADM-10", "two_assets", "two valid sheets submitted in one request", "rejected_too_many_assets", None),
]
UNRUN_BY_DECISION = [
    ("ADM-P1", "PDF over five pages", "PDF is not the selected modality"),
    ("ADM-P2", "encrypted PDF", "PDF is not the selected modality"),
    ("ADM-P3", "PDF with embedded file, script or link action", "PDF is not the selected modality"),
]


def generate(out_dir: str, good_png_path: str) -> list[dict]:
    os.makedirs(out_dir, exist_ok=True)
    with open(good_png_path, "rb") as handle:
        good = handle.read()
    written = []
    for case_id, name, description, expected, make in CASES:
        entry = {"id": case_id, "description": description, "expected_state": expected,
                 "must_hold": ["actionable message", "no provider request", "no partial SourceAsset",
                               "original draft unchanged"]}
        if make is None:
            entry["files"] = ["sources/c01a.png", "sources/c01b.png"]
        else:
            data = make(good)
            path = os.path.join(out_dir, name)
            with open(path, "wb") as handle:
                handle.write(data)
            entry.update(file=path, bytes=len(data))
        written.append(entry)
    return written
