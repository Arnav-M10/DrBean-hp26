"""The hostile PDF assets have the property each one claims (checked independently of any product parser)."""
from __future__ import annotations

import hashlib
import os
import re
import sys
import unittest
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from drbean_eval import hostile_pdfs as hp  # noqa: E402


def inflated_size(data: bytes, cap: int = 512 * 1024 * 1024) -> int:
    """Inflate the first Flate stream in bounded chunks; never allocate the whole output."""
    start = data.index(b"stream\n") + len(b"stream\n")
    decompressor, total = zlib.decompressobj(), 0
    chunk = data[start:]
    while chunk and total < cap and not decompressor.eof:
        out = decompressor.decompress(chunk, 1 << 20)
        total += len(out)
        chunk = decompressor.unconsumed_tail
    return total


class HostileAssetTests(unittest.TestCase):
    def test_every_asset_builds_deterministically(self):
        for name in hp.ASSETS:
            if name in ("oversize-21mib", "inflate-bomb", "image-inflate-bomb", "pages-2000"):
                continue  # large; covered by the specific tests below
            with self.subTest(name=name):
                self.assertEqual(hashlib.sha256(hp.build(name)).digest(), hashlib.sha256(hp.build(name)).digest())

    def test_encrypted_asset_round_trips_only_with_its_key(self):
        data, material = hp.encrypted_pdf()
        self.assertIn(b"/Encrypt 6 0 R", data)
        self.assertIn(material["ciphertext"], data)
        self.assertNotIn(b"Encrypted synthetic paper", data)
        self.assertEqual(hp._rc4(material["object_key"], material["ciphertext"]), material["plaintext"])
        self.assertNotEqual(hp._rc4(b"wrongkey12", material["ciphertext"]), material["plaintext"])

    def test_page_counts_and_caps(self):
        self.assertEqual(len(re.findall(rb"/Type /Page /Parent", hp.build("pages-51"))), 51)
        many = hp.build("pages-2000")
        self.assertEqual(len(re.findall(rb"/Type /Page /Parent", many)), 2000)
        self.assertLess(len(many), 5 * hp.MiB)  # small file, many pages: the cap must apply before page work
        self.assertGreater(len(hp.build("oversize-21mib")), 20 * hp.MiB)

    def test_bombs_are_small_and_inflate_far_beyond_their_size(self):
        bomb = hp.build("inflate-bomb")
        self.assertLess(len(bomb), 1 * hp.MiB)
        self.assertEqual(inflated_size(bomb), 128 * hp.MiB)
        image = hp.build("image-inflate-bomb")
        self.assertLess(len(image), 1 * hp.MiB)
        self.assertIn(b"/Width 12000 /Height 12000", image)
        self.assertIn(b"/Width 60000 /Height 60000", hp.build("image-dimension-bomb"))
        self.assertGreaterEqual(hp.build("nested-arrays").count(b"["), 50000)

    def test_active_content_and_spoofs_are_what_they_claim(self):
        self.assertIn(b"/S /JavaScript", hp.build("javascript-openaction"))
        launch = hp.build("launch-and-uri-actions")
        self.assertIn(b"/S /Launch", launch)
        self.assertIn(b"/S /URI", launch)
        self.assertIn(b"/EmbeddedFiles", hp.build("embedded-attachment"))
        polyglot = hp.build("html-polyglot")
        self.assertTrue(polyglot.startswith(b"<!doctype html>"))
        self.assertGreater(polyglot.index(b"%PDF-"), 512)
        self.assertTrue(hp.build("png-bytes-named-pdf").startswith(b"\x89PNG\r\n\x1a\n"))
        self.assertEqual(hp.build("empty"), b"")
        self.assertIn(b"/Kids [2 0 R 4 0 R]", hp.build("page-tree-cycle"))
        self.assertIn(b"/Size 2147483647", hp.build("huge-xref-size"))
        self.assertNotIn(b"startxref", hp.build("truncated"))

    def test_hostile_filenames_cover_traversal_and_control_characters(self):
        joined = "\n".join(hp.HOSTILE_FILENAMES)
        for marker in ("../", "..\\", "\x00", "‮", "\r\n", "CON."):
            self.assertIn(marker, joined)


if __name__ == "__main__":
    unittest.main()
