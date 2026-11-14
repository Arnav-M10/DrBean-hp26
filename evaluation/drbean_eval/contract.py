"""Test oracle for the DB-SC-1 wire profile, written from the contract text.

This is NOT the product canonicalizer. Owner 02 owns the authoritative
implementation and golden byte fixtures. The harness uses this oracle only to
check fixtures and observed API output; any disagreement is an issue-ledger
entry for Owner 02, never something to "fix" here silently.
"""
from __future__ import annotations

import hashlib
import json
import re
from fractions import Fraction
from math import gcd

MAX_SAFE_INT = 9007199254740991
MAX_DEPTH = 64
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

_RATIONAL = re.compile(r"^(0|-?[1-9][0-9]*)/([1-9][0-9]*)$")
_DECIMAL = re.compile(r"^(-?)([0-9]+)(?:\.([0-9]+))?$")


class ContractError(ValueError):
    pass


def is_canonical_rational(text) -> bool:
    """Reduced n/d: signed numerator, positive denominator, gcd one, zero is 0/1."""
    if not isinstance(text, str):
        return False
    match = _RATIONAL.match(text)
    if not match:
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
    """Exact conversion of a finite decimal spelling. No floats are involved."""
    match = _DECIMAL.match(source) if isinstance(source, str) else None
    if not match:
        raise ContractError(f"not a finite decimal spelling: {source!r}")
    sign, whole, places = match.group(1), match.group(2), match.group(3) or ""
    value = Fraction(int(whole + places), 10 ** len(places))
    return from_fraction(-value if sign else value)


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


def parse_strict(data: bytes):
    """Parse wire JSON, failing (not repairing) on the DB-SC-1 rejections."""
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise ContractError(f"invalid UTF-8: {error}") from None
    try:
        value = json.loads(text, object_pairs_hook=_no_duplicates, parse_float=_reject, parse_constant=_reject)
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
