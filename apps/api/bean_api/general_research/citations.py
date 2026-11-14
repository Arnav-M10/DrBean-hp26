"""Locate quoted source text exactly, with documented normalization and token boundaries.

A verified citation establishes where words occur in the retained text layer of
one source page. It does not establish that an interpretation is correct.

Normalization ``citation-normalization.v1`` (applied to page text and quote alike):
  * every run of Unicode whitespace, including line breaks and no-break spaces,
    becomes one space; leading and trailing space is ignored;
  * U+00B5 MICRO SIGN and U+03BC GREEK SMALL LETTER MU are the same character;
  * hyphen, non-breaking hyphen, figure dash, en dash and minus sign are "-";
  * curly single and double quotation marks are ' and ";
  * the ligatures ff, fi, fl, ffi, ffl and st are expanded;
  * soft hyphens and zero-width characters are removed.
Nothing else changes: no case folding and no NFKC, so superscripts stay distinct.
A second pass removes a hyphen followed by a line break between two letters
(``concen-\\ntration``); a match found only that way reports ``dehyphenation``.

A match must not begin or end inside a token: between two digits, two letters,
or a digit and a decimal separator that continues the number, and it must not
drop the sign of a negative number. "538" therefore does not match "5380", nor
"4.6" match "4.62", nor "0.5" match "-0.5". Where commas delimit fields (CSV
and JSON) only "." continues a number; elsewhere "," does too. Ambiguous matches
(more than one admissible occurrence) are reported, never resolved by guessing.
"""
from __future__ import annotations

from array import array
from dataclasses import dataclass
import re
import sys

from . import limits as L

NORMALIZATION_VERSION = L.CITATION_NORMALIZATION_VERSION
NONE_BOX = 0xFFFF
_SPACE = re.compile(r"\s")
_EQUIVALENT = {"µ": "μ", "‐": "-", "‑": "-", "‒": "-", "–": "-", "−": "-",
               "﹣": "-", "－": "-", "‘": "'", "’": "'", "‚": "'", "‛": "'",
               "“": '"', "”": '"', "„": '"', "‟": '"', "ﬀ": "ff", "ﬁ": "fi",
               "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"}
_REMOVED = {"­", "​", "‌", "‍", "⁠", "﻿"}
MIN_QUOTE_CHARS = 2
MAX_QUOTE_CHARS = 500

_FLATTENED_EXPONENT = re.compile(r"\d(?:[.,]\d+)?\s*[×xX*·]\s*10-?\d{1,3}(?!\d)")
_EXPLICIT_EXPONENT = re.compile(r"10(?:\^|\*\*)-?\d|10[⁰¹²³⁴⁵⁶⁷⁸⁹⁻]")
_STATISTICAL = re.compile(
    r"(?<![A-Za-z])(?:SD|S\.D\.|SEM|SE|S\.E\.|S\.E\.M\.|CI|IQR|CV)(?![A-Za-z])|±|\+/-|"
    r"standard deviation|standard error|confidence interval|interquartile|credible interval", re.I)
_NUMBER = re.compile(r"(?<![A-Za-z0-9.,])-?\d+(?:[.,]\d+)*")
_LOCATOR_WORDS = re.compile(r"(?:page|pages|p\.|pp\.|row|rows|line|lines|table|figure|fig\.|column|section|source)\s*$",
                            re.I)


def normalize(text: str, *, dehyphenate: bool = False) -> tuple[str, list[int]]:
    """Return the normalized text and, for each normalized character, its raw index."""
    out: list[str] = []
    origin: list[int] = []
    pending_space = -1
    index, n = 0, len(text)
    while index < n:
        ch = text[index]
        if dehyphenate and ch in "-‐­" and out and out[-1].isalpha():
            probe = index + 1
            saw_break = False
            while probe < n and _SPACE.match(text[probe]):
                saw_break = saw_break or text[probe] in "\r\n  "
                probe += 1
            if saw_break and probe < n and text[probe].isalpha() and text[probe].islower():
                index, pending_space = probe, -1
                continue
        if ch in _REMOVED:
            index += 1
            continue
        if _SPACE.match(ch):
            if pending_space < 0 and out:
                pending_space = index
            index += 1
            continue
        if pending_space >= 0:
            out.append(" ")
            origin.append(pending_space)
            pending_space = -1
        for piece in _EQUIVALENT.get(ch, ch):
            out.append(piece)
            origin.append(index)
        index += 1
    return "".join(out), origin


def _splits_token(text: str, position: int, separators: str = ".,") -> bool:
    """Does a boundary at ``position`` cut through a word or a number?"""
    if position <= 0 or position >= len(text):
        return False
    left, right = text[position - 1], text[position]
    if (left.isdigit() and right.isdigit()) or (left.isalpha() and right.isalpha()):
        return True
    if left.isdigit() and right in separators and position + 1 < len(text) and text[position + 1].isdigit():
        return True
    if left in separators and right.isdigit() and position >= 2 and text[position - 2].isdigit():
        return True
    if left == "-" and (right.isdigit() or right == ".") and (position < 2 or not text[position - 2].isalnum()):
        return True   # a quote that drops the sign of "-0.5" or "-.19" changes the number
    return False


def separators_for(media_type: str, delimiter: str | None = None) -> str:
    """Characters that continue a number inside this kind of source."""
    if media_type == "application/json" or (media_type == "text/csv" and delimiter == ","):
        return "."
    return ".,"


def token_occurrences(haystack: str, needle: str, separators: str = ".,") -> tuple[list[int], int]:
    """Admissible start offsets of ``needle`` in ``haystack`` (both normalized) and the rejected count."""
    admissible, rejected, start = [], 0, haystack.find(needle)
    while start >= 0:
        end = start + len(needle)
        if _splits_token(haystack, start, separators) or _splits_token(haystack, end, separators):
            rejected += 1
        else:
            admissible.append(start)
        start = haystack.find(needle, start + 1)
    return admissible, rejected


def flattened_exponents(text: str) -> list[tuple[int, int]]:
    return [(m.start(), m.end()) for m in _FLATTENED_EXPONENT.finditer(text)]


def has_flattened_exponent(text: str) -> bool:
    normalized, _ = normalize(text)
    return bool(_FLATTENED_EXPONENT.search(normalized))


def statistical_qualifiers(text: str) -> list[str]:
    return sorted({m.group(0) for m in _STATISTICAL.finditer(text)})


def numbers_in(text: str) -> list[str]:
    """Numeric tokens a statement asserts, excluding locator numbers such as "page 2"."""
    normalized, _ = normalize(text)
    found = []
    for match in _NUMBER.finditer(normalized):
        if _LOCATOR_WORDS.search(normalized[:match.start()]):
            continue
        token = match.group(0).lstrip("-")
        if token not in found:
            found.append(token)
    return found


def contains_token(text: str, token: str, separators: str = ".,") -> bool:
    normalized_text, _ = normalize(text)
    normalized_token, _ = normalize(token)
    if not normalized_token:
        return False
    admissible, _ = token_occurrences(normalized_text, normalized_token, separators)
    return bool(admissible)


@dataclass(frozen=True)
class PageText:
    text: str
    char_boxes: bytes | None = None   # 4 little-endian uint16 per character, 0..10000, top-left origin
    quality: str = "usable"           # usable | none | unreliable


def _bbox(page: PageText, raw_start: int, raw_end: int) -> list[int] | None:
    if not page.char_boxes:
        return None
    boxes = array("H")
    boxes.frombytes(page.char_boxes)
    if sys.byteorder != "little":
        boxes.byteswap()
    x0 = y0 = 10_001
    x1 = y1 = -1
    for index in range(raw_start, min(raw_end, len(boxes) // 4)):
        box = boxes[index * 4:index * 4 + 4]
        if box[0] == NONE_BOX:
            continue
        x0, y0, x1, y1 = min(x0, box[0]), min(y0, box[1]), max(x1, box[2]), max(y1, box[3])
    if x1 < 0 or x1 <= x0 or y1 <= y0:
        return None
    return [x0, y0, x1, y1]


def locate(pages: list[PageText], page_index: int, quote: str, separators: str = ".,") -> dict:
    """Validate one citation against the retained text layers of a source."""
    result = {"status": "not_found", "normalizations": [], "match": None, "bbox_e4": None,
              "admissible_occurrences": 0, "rejected_partial_token_occurrences": 0, "found_on_pages": [],
              "flags": []}
    if type(page_index) is not int or not 0 <= page_index < len(pages):
        result["status"] = "invalid_page"
        return result
    needle, _ = normalize(quote or "")
    if len(needle.replace(" ", "")) < MIN_QUOTE_CHARS:
        result["status"] = "quote_too_short"
        return result
    if len(needle) > MAX_QUOTE_CHARS:
        result["status"] = "quote_too_long"
        return result
    if statistical_qualifiers(needle):
        result["flags"].append("statistical_qualifier_in_quote")
    if _FLATTENED_EXPONENT.search(needle) and not _EXPLICIT_EXPONENT.search(needle):
        result["flags"].append("possible_flattened_exponent")
    page = pages[page_index]
    if page.quality != "usable":
        result["status"] = "unverifiable_no_text_layer" if page.quality == "none" else "unverifiable_text_layer"
        return result
    for dehyphenate in (False, True):
        haystack, origin = normalize(page.text, dehyphenate=dehyphenate)
        admissible, rejected = token_occurrences(haystack, needle, separators)
        result["rejected_partial_token_occurrences"] = max(result["rejected_partial_token_occurrences"], rejected)
        if not admissible:
            continue
        result["admissible_occurrences"] = len(admissible)
        result["normalizations"] = ["citation-normalization.v1"] + (["dehyphenation"] if dehyphenate else [])
        if len(admissible) > 1:
            result["status"] = "ambiguous"
            return result
        start = admissible[0]
        end = start + len(needle)
        raw_start, raw_end = origin[start], origin[end - 1] + 1
        result["status"] = "verified"
        result["match"] = {"start": raw_start, "end": raw_end}
        result["bbox_e4"] = _bbox(page, raw_start, raw_end)
        for flat_start, flat_end in flattened_exponents(haystack):
            if flat_start < end and start < flat_end and "possible_flattened_exponent" not in result["flags"]:
                result["flags"].append("possible_flattened_exponent")
        return result
    if result["rejected_partial_token_occurrences"]:
        result["status"] = "partial_token_match"
        return result
    for other, candidate in enumerate(pages):
        if other != page_index and candidate.quality == "usable":
            haystack, _ = normalize(candidate.text, dehyphenate=True)
            if token_occurrences(haystack, needle, separators)[0]:
                result["found_on_pages"].append(other)
    if result["found_on_pages"]:
        result["status"] = "wrong_page"
    return result
