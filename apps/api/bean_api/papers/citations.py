"""Citation checks against a paper manifest. A matched excerpt is a text occurrence, not proof."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
import unicodedata


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("−", "-").replace("­", "")
    return re.sub(r"\s+", " ", text).strip().casefold()


def match_quotation(manifest: dict, page_text: dict, page: int, excerpt: str) -> dict:
    """Is this excerpt present in the native text of that physical page? Never says the reading is right."""
    pages = {p["physical_page"]: p for p in manifest["pages"]}
    if page not in pages:
        return {"status": "invalid_page", "label": f"Page {page} is not in this paper ({manifest['page_count']} pages)."}
    if not pages[page]["has_text_layer"]:
        return {"status": "no_text_layer", "label": "This page has no useful text layer (for example a scan). Check the cited region visually."}
    needle = _normalize(excerpt or "")
    if len(needle) < 3:
        return {"status": "excerpt_too_short", "label": "The quoted excerpt is too short to locate."}
    if needle in _normalize(page_text.get(page, "")):
        return {"status": "text_occurrence", "label": "This text occurs on the cited page. That locates the words; it does not confirm how they were interpreted."}
    elsewhere = [n for n, text in page_text.items() if n != page and needle in _normalize(text)]
    if elsewhere:
        found = ", ".join(str(n) for n in elsewhere)
        return {"status": "wrong_page", "label": f"This text does not occur on page {page}; it occurs on page(s) {found}.", "found_on": elsewhere}
    return {"status": "not_found", "label": "This text was not found in the native text of the cited page. Treat the citation as unverified."}


def _decimal(value) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("not a number") from None
    if not number.is_finite():
        raise ValueError("not finite")
    return number


def validate_citation(manifest: dict, page: int, box: list | None) -> list[str]:
    """Problems with a cited page and optional box [x0, y0, x1, y1] in PDF points (manifest convention)."""
    pages = {p["physical_page"]: p for p in manifest["pages"]}
    if type(page) is not int or page not in pages:
        return [f"page {page} is not a physical page of this paper (1-{manifest['page_count']})"]
    if box is None:
        return ["no location within the page was given; the value must be found by the reviewer"]
    try:
        x0, y0, x1, y1 = (_decimal(v) for v in box)
    except (ValueError, TypeError):
        return ["location is not four finite numbers"]
    info = pages[page]
    left, bottom = (_decimal(v) for v in info["origin_pt"])
    right, top = left + _decimal(info["width_pt"]), bottom + _decimal(info["height_pt"])
    problems = []
    if not (x0 < x1 and y0 < y1):
        problems.append("location box is empty or inverted")
    if x0 < left or y0 < bottom or x1 > right or y1 > top:
        problems.append("location box extends outside the page")
    return problems


def render_box(manifest: dict, page: int, box: list, scale: str | float) -> list[float]:
    """Map a PDF-point box to pixel coordinates of the rendered preview (origin top-left, rotation applied)."""
    info = {p["physical_page"]: p for p in manifest["pages"]}[page]
    s = float(scale)
    left, bottom = (float(v) for v in info["origin_pt"])
    width, height = float(info["width_pt"]), float(info["height_pt"])
    x0, y0, x1, y1 = (float(v) for v in box)
    # Unrotated: x' = x - left, y' = top - y.
    ux0, ux1 = x0 - left, x1 - left
    uy0, uy1 = (bottom + height) - y1, (bottom + height) - y0
    rotation = info["rotation"]
    if rotation == 0:
        px = (ux0, uy0, ux1, uy1)
    elif rotation == 90:
        px = (height - uy1, ux0, height - uy0, ux1)
    elif rotation == 180:
        px = (width - ux1, height - uy1, width - ux0, height - uy0)
    else:  # 270
        px = (uy0, width - ux1, uy1, width - ux0)
    return [round(v * s, 2) for v in px]
