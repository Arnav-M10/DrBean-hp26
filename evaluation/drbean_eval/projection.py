"""Explicit, documented mapping between application records and the evaluation vocabulary.

``eval-observation/v1`` is an evaluation envelope, NOT a production DTO. Production field
names and coordinates stay authoritative; this module converts in both directions and
refuses anything it cannot convert exactly.

Field paths
    production ``rows[i].time | rows[i].concentration | rows[i].hard_allowance``  (zero-based)
    evaluation ``row{i+1}_time | row{i+1}_concentration | row{i+1}_allowance``  (one-based)
    production ``domain.A.lower`` / ``A.lower`` -> evaluation ``A_min`` (``upper`` -> ``A_max``),
    likewise ``ke`` and ``ka``; ``target.lower|upper`` -> ``target_min|target_max``;
    ``model`` -> ``model_template``.

Values
    production ``candidate_exact`` (reduced rational string) <-> evaluation ``value``;
    the original spelling is kept separately and never re-derived from the rational.

Locators
    production ``locator.bbox = [x0, y0, x1, y1]`` (opposite corners, original pixels)
    evaluation ``region_xywh_px = [x, y, width, height]`` (original pixels)
    Conversion uses the admitted source's original width/height; a rectangle with no area
    or outside the image is refused rather than clipped. Source identity (asset id and
    sha256) travels with every converted locator.
"""
from __future__ import annotations

import re

_ROW = re.compile(r"rows\[(\d{1,3})\]\.(time|concentration|hard_allowance)")
_EVAL_ROW = re.compile(r"row(\d{1,3})_(time|concentration|allowance)")
_BOUND = re.compile(r"(?:domain\.)?(A|ke|ka)\.(lower|upper)")
_EVAL_BOUND = re.compile(r"(A|ke|ka)_(min|max)")
_SCALAR = {"target.lower": "target_min", "target.upper": "target_max", "model": "model_template"}


class ProjectionError(ValueError):
    pass


def field_to_eval(path: str) -> str:
    match = _ROW.fullmatch(path)
    if match:
        index, name = int(match.group(1)), match.group(2)
        return f"row{index + 1}_{'allowance' if name == 'hard_allowance' else name}"
    match = _BOUND.fullmatch(path)
    if match:
        return f"{match.group(1)}_{'min' if match.group(2) == 'lower' else 'max'}"
    if path in _SCALAR:
        return _SCALAR[path]
    raise ProjectionError(f"no evaluation name for production field path {path!r}")


def field_to_production(name: str) -> str:
    match = _EVAL_ROW.fullmatch(name)
    if match:
        index, field = int(match.group(1)), match.group(2)
        if index < 1:
            raise ProjectionError("evaluation rows are one-based")
        return f"rows[{index - 1}].{'hard_allowance' if field == 'allowance' else field}"
    match = _EVAL_BOUND.fullmatch(name)
    if match:
        return f"domain.{match.group(1)}.{'lower' if match.group(2) == 'min' else 'upper'}"
    for production, evaluation in _SCALAR.items():
        if evaluation == name:
            return production
    raise ProjectionError(f"no production field path for evaluation name {name!r}")


def _check_dims(width: int, height: int) -> None:
    if not (type(width) is int and type(height) is int and width > 0 and height > 0):
        raise ProjectionError("original image width and height are required")


def bbox_to_xywh(bbox: list[int], width: int, height: int) -> list[int]:
    _check_dims(width, height)
    if not (isinstance(bbox, list) and len(bbox) == 4 and all(type(v) is int for v in bbox)):
        raise ProjectionError("bbox must be four integers [x0, y0, x1, y1]")
    x0, y0, x1, y1 = bbox
    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
        raise ProjectionError(f"bbox {bbox} is empty or outside the {width}x{height} image")
    return [x0, y0, x1 - x0, y1 - y0]


def xywh_to_bbox(region: list[int], width: int, height: int) -> list[int]:
    _check_dims(width, height)
    if not (isinstance(region, list) and len(region) == 4 and all(type(v) is int for v in region)):
        raise ProjectionError("region must be four integers [x, y, width, height]")
    x, y, w, h = region
    if not (x >= 0 and y >= 0 and w > 0 and h > 0 and x + w <= width and y + h <= height):
        raise ProjectionError(f"region {region} is empty or outside the {width}x{height} image")
    return [x, y, x + w, y + h]


def intake_field_to_eval(field: dict, source: dict) -> dict:
    """One production IntakeField -> one evaluation proposal, keeping source identity and original spelling."""
    body = source.get("body") or source
    locator = field.get("locator") or {}
    bbox = locator.get("bbox")
    return {
        "field": field_to_eval(field["field_path"]),
        "value": field.get("candidate_exact"),
        "original_value": field.get("original_value"),
        "unit": field.get("unit"),
        "status": "ambiguous" if field.get("ambiguity") else ("missing" if field.get("original_value") is None
                                                               else "proposed"),
        "source_ref": {"asset_id": source.get("id"), "asset_sha256": body.get("sha256"), "page": locator.get("page"),
                       "region_xywh_px": bbox_to_xywh(bbox, body["width"], body["height"]) if bbox else None,
                       "image_px": [body.get("width"), body.get("height")],
                       "source_label": "needs_human_verification"},
        "grounding": field.get("grounding"),
    }
