"""The authoritative server implementation of the DB-SC-1 byte profile.

This module does not normalize scientific problems or verify evidence. Callers
validate a versioned entity schema before giving its semantic body to the hash.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from decimal import Decimal
from fractions import Fraction
from typing import Any

MAX_JSON_BYTES = 1024 * 1024
MAX_DEPTH = 32
MAX_DIGITS = 256
MAX_DECIMAL_EXPONENT = 128
MAX_COUNTER = 9007199254740991
IDENTITY_KINDS = frozenset({"dataset", "problem", "plan", "design-request", "suggestion", "report"})
_RATIONAL = re.compile(r"(?:0|-[1-9][0-9]*|[1-9][0-9]*)/[1-9][0-9]*\Z")
_DECIMAL = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE]([+-]?[0-9]+))?\Z")


def validate_rational(value: Any) -> str:
    """Accept only reduced, bounded rational *strings*, without repair."""
    if not isinstance(value, str) or len(value) > MAX_DIGITS * 2 + 2 or not _RATIONAL.fullmatch(value):
        raise ValueError("Expected a canonical reduced rational string n/d")
    numerator_text, denominator_text = value.split("/")
    if len(numerator_text.lstrip("-")) > MAX_DIGITS or len(denominator_text) > MAX_DIGITS:
        raise ValueError("Rational numerator and denominator are limited to 256 digits")
    numerator, denominator = int(numerator_text), int(denominator_text)
    if math.gcd(numerator, denominator) != 1:
        raise ValueError("Rational must be reduced; zero is exactly 0/1")
    return value


def parse_decimal(value: Any) -> str:
    """Convert a reviewed finite decimal spelling exactly, never via float."""
    if not isinstance(value, str) or len(value) > MAX_DIGITS:
        raise ValueError("Decimal input must be a bounded string")
    match = _DECIMAL.fullmatch(value)
    if not match:
        raise ValueError("Expected a finite decimal spelling")
    exponent = match.group(1)
    if exponent is not None and (len(exponent.lstrip("+-")) > 3 or abs(int(exponent)) > MAX_DECIMAL_EXPONENT):
        raise ValueError("Decimal exponent exceeds the admitted limit of 128")
    fraction = Fraction(Decimal(value))
    return validate_rational(f"{fraction.numerator}/{fraction.denominator}")


def _validate_value(value: Any, depth: int = 0) -> None:
    if depth > MAX_DEPTH:
        raise ValueError("JSON nesting exceeds 32 levels")
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, int):
        if not 0 <= value <= MAX_COUNTER:
            raise ValueError("JSON counters must be nonnegative safe integers")
        return
    if isinstance(value, str):
        if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
            raise ValueError("Unpaired Unicode surrogates are not permitted")
        return
    if isinstance(value, list):
        for item in value:
            _validate_value(item, depth + 1)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not key.isascii():
                raise ValueError("Schema keys must be ASCII strings")
            _validate_value(item, depth + 1)
        return
    raise ValueError("JSON contains an unsupported type or floating-point number")


def canonical_bytes(value: Any) -> bytes:
    """Canonical UTF-8, retaining Unicode and declared array order."""
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    _validate_value(value)
    return json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def semantic_digest(kind: str, body: Any) -> str:
    if kind not in IDENTITY_KINDS:
        raise ValueError("Unsupported DB-SC-1 identity kind")
    return hashlib.sha256(f"dr-bean:{kind}:v1\n".encode("ascii") + canonical_bytes(body)).hexdigest()


def byte_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def parse_json_strict(data: bytes | str, *, max_bytes: int = MAX_JSON_BYTES) -> Any:
    """Parse before schema validation so duplicate keys and -0 remain visible."""
    raw = data.encode("utf-8", "strict") if isinstance(data, str) else data
    if len(raw) > max_bytes:
        raise ValueError("JSON body exceeds the admitted byte limit")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result

    def integer(value: str) -> int:
        if value.startswith("-") or len(value) > 16:
            raise ValueError("JSON counters must be nonnegative safe integers")
        return int(value)

    def invalid_number(_: str) -> None:
        raise ValueError("Floating-point and non-finite JSON values are not permitted")

    try:
        decoded = raw.decode("utf-8", "strict")
        value = json.loads(decoded, object_pairs_hook=pairs, parse_int=integer, parse_float=invalid_number, parse_constant=invalid_number)
        _validate_value(value)
    except (UnicodeError, RecursionError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed UTF-8 JSON") from exc
    return value
