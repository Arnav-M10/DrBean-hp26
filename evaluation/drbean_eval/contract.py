"""Test oracle for the DB-SC-1 wire profile, written independently from the contract text.

This is NOT the product canonicalizer. Owner 02's implementation
(``apps/api/bean_api/canonical.py``) and its golden fixtures are authoritative.
The harness uses this oracle to check fixtures and observed API output.

Revision 2 (Workstream 5) deliberately aligned four boundaries with the
authoritative profile after cross-implementation probes showed the oracle
accepted inputs the API rejects. Each is pinned by a golden boundary test in
``evaluation/tests/test_contract_boundaries.py`` and compared against the API in
``tests/test_evaluation.py``:

* a rational must match in full: ``"1/2\n"`` is rejected (``$`` matched before a
  trailing newline);
* JSON integer tokens may not carry a sign, so ``-0`` is rejected like any
  negative counter (``json.loads`` silently turned ``-0`` into ``0``);
* maximum nesting depth is 32 (was 64), counted the same way as the API;
* numerator and denominator are limited to 256 digits each, integers to 16
  digits and 2**53-1, and parsed JSON to 1 MiB;
* finite decimal spelling follows the API grammar: optional sign, ``.5`` and
  ``5.``, and a decimal exponent of at most three digits and magnitude 128.
"""
from __future__ import annotations

import hashlib
import json
import re
from fractions import Fraction
from math import gcd

MAX_SAFE_INT = 9007199254740991
MAX_DEPTH = 32
MAX_DIGITS = 256
MAX_INTEGER_DIGITS = 16
MAX_JSON_BYTES = 1024 * 1024
MAX_DECIMAL_EXPONENT = 128
IDENTITY_KINDS = ("dataset", "problem", "plan", "design-request", "suggestion", "report")

AXES = {
    "execution": ("queued", "running", "completed", "cancel_requested", "cancelled", "failed", "interrupted"),
    "scientific_outcome": ("certified_counterexample", "numerical_candidate", "no_counterexample_found",
                           "inconclusive", "unsupported", "failed"),
    "verification": ("not_checked", "valid", "invalid", "inconclusive", "unsupported", "failed"),
    "expected_binding": ("matches", "mismatch", "not_supplied"),
    "design_tier": ("numerical_guidance", "checked_pair_separation", "no_separation_established", "unavailable"),
    "replay": ("not_run", "running", "passed", "failed", "unsupported"),
}
ERROR_BODY_KEYS = ("code", "message", "field_paths", "retryable", "current_revision_id", "request_id")

_RATIONAL = re.compile(r"(0|-?[1-9][0-9]*)/([1-9][0-9]*)")
_DECIMAL = re.compile(r"([+-]?)(?:([0-9]+)(?:\.([0-9]*))?|\.([0-9]+))(?:[eE]([+-]?[0-9]+))?")


class ContractError(ValueError):
    pass


def is_canonical_rational(text) -> bool:
    """Reduced n/d: signed numerator, positive denominator, gcd one, zero is 0/1."""
    if not isinstance(text, str) or len(text) > 2 * MAX_DIGITS + 2:
        return False
    match = _RATIONAL.fullmatch(text)
    if not match:
        return False
    if len(match.group(1).lstrip("-")) > MAX_DIGITS or len(match.group(2)) > MAX_DIGITS:
        return False
    numerator, denominator = int(match.group(1)), int(match.group(2))
    if numerator == 0:
        return text == "0/1"
    return gcd(abs(numerator), denominator) == 1


def to_fraction(text: str) -> Fraction:
    if not is_canonical_rational(text):
        raise ContractError(f"not a canonical rational string: {text!r}")
    numerator, denominator = text.split("/")
    return Fraction(int(numerator), int(denominator))


def from_fraction(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


def decimal_to_rational(source: str) -> str:
    """Exact conversion of a finite decimal spelling. No floats or Decimal objects are involved."""
    match = _DECIMAL.fullmatch(source) if isinstance(source, str) and len(source) <= MAX_DIGITS else None
    if not match:
        raise ContractError(f"not a finite decimal spelling: {source!r}")
    sign, whole, places, bare_places, exponent = match.groups()
    digits_whole, digits_places = (whole or ""), (places if whole is not None else bare_places) or ""
    shift = 0
    if exponent is not None:
        if len(exponent.lstrip("+-")) > 3 or abs(int(exponent)) > MAX_DECIMAL_EXPONENT:
            raise ContractError(f"decimal exponent outside the admitted range: {source!r}")
        shift = int(exponent)
    value = Fraction(int((digits_whole + digits_places) or "0"), 10 ** len(digits_places)) * Fraction(10) ** shift
    text = from_fraction(-value if sign == "-" else value)
    if not is_canonical_rational(text):
        raise ContractError(f"decimal converts outside the admitted rational bounds: {source!r}")
    return text


def _escape(text: str) -> str:
    out = ['"']
    short = {'"': '\\"', "\\": "\\\\", "\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t"}
    for char in text:
        code = ord(char)
        if char in short:
            out.append(short[char])
        elif code < 0x20:
            out.append("\\u%04x" % code)
        elif 0xD800 <= code <= 0xDFFF:
            raise ContractError("unpaired surrogate in string")
        else:
            out.append(char)
    out.append('"')
    return "".join(out)


def _emit(value, depth: int) -> str:
    if depth > MAX_DEPTH:
        raise ContractError("nesting too deep")
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, int):
        if not 0 <= value <= MAX_SAFE_INT:
            raise ContractError(f"integer counter outside 0..{MAX_SAFE_INT}: {value}")
        return str(value)
    if isinstance(value, float):
        raise ContractError("floating-point numbers are not permitted; use rational strings")
    if isinstance(value, str):
        return _escape(value)
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_emit(item, depth + 1) for item in value) + "]"
    if isinstance(value, dict):
        for key in value:
            if not isinstance(key, str) or not key.isascii():
                raise ContractError(f"schema keys must be ASCII strings: {key!r}")
        return "{" + ",".join(_escape(key) + ":" + _emit(value[key], depth + 1) for key in sorted(value)) + "}"
    raise ContractError(f"unsupported type {type(value).__name__}")


def canonical_json(value) -> bytes:
    return _emit(value, 0).encode("utf-8")


def identity(kind: str, body) -> str:
    """sha256 over 'dr-bean:<kind>:v1' + LF + canonical JSON body, lowercase hex."""
    if kind not in IDENTITY_KINDS:
        raise ContractError(f"unknown identity kind {kind!r}")
    return hashlib.sha256(f"dr-bean:{kind}:v1\n".encode() + canonical_json(body)).hexdigest()


def artifact_digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _no_duplicates(pairs):
    seen = {}
    for key, value in pairs:
        if key in seen:
            raise ContractError(f"duplicate key {key!r}")
        seen[key] = value
    return seen


def _reject(token):
    raise ContractError(f"non-finite or floating-point number {token!r}")


def _depth(value, level=0):
    if level > MAX_DEPTH:
        raise ContractError("nesting too deep")
    if isinstance(value, dict):
        for item in value.values():
            _depth(item, level + 1)
    elif isinstance(value, list):
        for item in value:
            _depth(item, level + 1)


def _integer(token: str) -> int:
    """JSON integers are unsigned counters: '-0' and every signed token are rejected, as by the API."""
    if token.startswith("-") or len(token) > MAX_INTEGER_DIGITS:
        raise ContractError(f"integer token {token[:20]!r} is not a nonnegative safe counter")
    return int(token)


def parse_strict(data: bytes, max_bytes: int = MAX_JSON_BYTES):
    """Parse wire JSON, failing (not repairing) on the DB-SC-1 rejections."""
    if len(data) > max_bytes:
        raise ContractError(f"JSON exceeds {max_bytes} bytes")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ContractError(f"invalid UTF-8: {error}") from None
    try:
        value = json.loads(text, object_pairs_hook=_no_duplicates, parse_float=_reject, parse_constant=_reject,
                           parse_int=_integer)
    except RecursionError:
        raise ContractError("nesting too deep") from None
    except json.JSONDecodeError as error:
        raise ContractError(f"malformed JSON: {error.msg}") from None
    _depth(value)
    canonical_json(value)  # also rejects negative/oversized integers and surrogates
    return value


def check_error_body(body) -> list[str]:
    """Problems with a public error body; empty list means it conforms."""
    if not isinstance(body, dict):
        return ["error body is not an object"]
    problems = [f"missing key {key}" for key in ERROR_BODY_KEYS if key not in body]
    problems += [f"unexpected key {key}" for key in body if key not in ERROR_BODY_KEYS]
    if "retryable" in body and not isinstance(body["retryable"], bool):
        problems.append("retryable is not a boolean")
    if "field_paths" in body and not isinstance(body["field_paths"], list):
        problems.append("field_paths is not a list")
    return problems
