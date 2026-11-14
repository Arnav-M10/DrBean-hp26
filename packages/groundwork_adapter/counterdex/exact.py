"""Bounded exact input and the new DB-SC-1 canonical byte profile.

A caller must first validate its versioned schema, including unknown fields and
its named identity projection.
The generic digest helper never removes fields or inserts an object's own hash.
"""

from __future__ import annotations

from fractions import Fraction
import hashlib
import json
import re

from .errors import AdapterError

CANONICALIZATION_PROFILE = "DB-SC-1"
MAX_LEXEME = 256
MAX_RATIONAL_LEXEME = 1024
MAX_EXPONENT = 256
MAX_RATIONAL_BITS = 4096
MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_JSON_DEPTH = 32
MAX_JSON_NODES = 20_000
MAX_STRUCTURAL_INTEGER = 9_007_199_254_740_991
_INTEGER = re.compile(r"[+-]?[0-9]+\Z")
_RATIONAL = re.compile(r"([+-]?[0-9]+)/([+-]?[0-9]+)\Z")
_DECIMAL = re.compile(
    r"(?P<sign>[+-]?)(?P<mantissa>(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+))"
    r"(?:[eE](?P<exponent>[+-]?[0-9]+))?\Z"
)
_KINDS = frozenset({"dataset", "problem", "plan", "design-request", "suggestion", "report"})


def _error(code: str, message: str, field_path: str = "") -> AdapterError:
    return AdapterError(code, message, (field_path,) if field_path else ())


def parse_rational(value: object, field_path: str = "") -> Fraction:
    """Parse an exact bounded lexeme; no binary floating-point conversion occurs.

    Input spellings may have a leading sign, leading zeros, a decimal point, or
    decimal exponent. A rational denominator may be signed and is normalized to
    positive. These are admission spellings, not canonical output spellings.
    """
    if type(value) is not str:
        raise _error("invalid_input", "An exact decimal or rational string is required.", field_path)
    lexeme_limit = MAX_RATIONAL_LEXEME if "/" in value else MAX_LEXEME
    if not value or len(value) > lexeme_limit:
        raise _error("invalid_input", "Exact scalar text exceeds its admitted length.", field_path)
    fraction_match = _RATIONAL.fullmatch(value)
    if fraction_match:
        numerator, denominator = map(int, fraction_match.groups())
        if denominator == 0:
            raise _error("invalid_input", "A rational denominator must be nonzero.", field_path)
        result = Fraction(numerator, denominator)
    elif _INTEGER.fullmatch(value):
        result = Fraction(int(value), 1)
    else:
        match = _DECIMAL.fullmatch(value)
        if match is None:
            raise _error("invalid_input", "Invalid exact decimal or rational spelling.", field_path)
        exponent = int(match.group("exponent") or "0")
        if abs(exponent) > MAX_EXPONENT:
            raise _error("invalid_input", "Decimal exponent exceeds the admitted limit.", field_path)
        whole, dot, fractional = match.group("mantissa").partition(".")
        digits = (whole or "0") + fractional
        numerator = int(digits)
        if match.group("sign") == "-":
            numerator = -numerator
        power = exponent - (len(fractional) if dot else 0)
        result = (Fraction(numerator * 10**power, 1) if power >= 0
                  else Fraction(numerator, 10**(-power)))
    if max(result.numerator.bit_length(), result.denominator.bit_length()) > MAX_RATIONAL_BITS:
        raise _error("invalid_input", "Exact scalar exceeds the admitted arithmetic size.", field_path)
    if len(f"{result.numerator}/{result.denominator}") > MAX_RATIONAL_LEXEME:
        raise _error("invalid_input", "Normalized rational text exceeds the admitted length.", field_path)
    return result


def rational_text(value: Fraction) -> str:
    """Return a reduced n/d string, including n/1 and the unique zero 0/1."""
    if type(value) is not Fraction:
        raise _error("invalid_input", "Exact Fraction value required for rational serialization.")
    if max(value.numerator.bit_length(), value.denominator.bit_length()) > MAX_RATIONAL_BITS:
        raise _error("invalid_input", "Exact scalar exceeds the admitted arithmetic size.")
    result = f"{value.numerator}/{value.denominator}"
    if len(result) > MAX_RATIONAL_LEXEME:
        raise _error("invalid_input", "Normalized rational text exceeds the admitted length.")
    return result


def normalize_rational(value: object, field_path: str = "") -> str:
    return rational_text(parse_rational(value, field_path))


def _limits(max_bytes: int, max_depth: int, max_nodes: int) -> None:
    for supplied, maximum in ((max_bytes, MAX_JSON_BYTES), (max_depth, MAX_JSON_DEPTH),
                              (max_nodes, MAX_JSON_NODES)):
        if type(supplied) is not int or not 1 <= supplied <= maximum:
            raise _error("invalid_input", "JSON limits must be positive integers within adapter caps.")


def _preflight(text: str, max_depth: int, max_nodes: int) -> None:
    """Bound nesting and token count before the JSON decoder builds containers.

    String escapes are only scanned for token boundaries here; the standard
    decoder remains responsible for JSON grammar and escape validity.
    """
    depth = nodes = 0
    in_string = escaped = in_atom = False
    for char in text:
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            in_atom = False
            nodes += 1
        elif char in "[{":
            depth += 1
            in_atom = False
            nodes += 1
            if depth > max_depth:
                raise _error("resource_exhaustion", "JSON nesting exceeds the admitted limit.")
        elif char in "]}":
            depth -= 1
            in_atom = False
        elif char in " \t\r\n,:":
            in_atom = False
        elif not in_atom:
            in_atom = True
            nodes += 1
        if nodes > max_nodes:
            raise _error("resource_exhaustion", "JSON structure exceeds the admitted node count.")


def _validate_tree(value: object, max_depth: int, max_nodes: int) -> None:
    # Count values, containers, and object keys, matching the preflight scanner.
    stack = [(value, 0)]
    nodes = 0
    while stack:
        current, parent_depth = stack.pop()
        nodes += 1
        if nodes > max_nodes:
            raise _error("resource_exhaustion", "JSON structure exceeds the admitted node count.")
        value_type = type(current)
        if value_type in (dict, list):
            depth = parent_depth + 1
            if depth > max_depth:
                raise _error("resource_exhaustion", "JSON nesting exceeds the admitted limit.")
            if len(current) > max_nodes:
                raise _error("resource_exhaustion", "JSON structure exceeds the admitted node count.")
            if value_type is dict:
                for key, item in current.items():
                    if type(key) is not str or not key or any(not 32 <= ord(c) <= 126 for c in key):
                        raise _error("invalid_input", "Schema keys must be nonempty printable ASCII strings.")
                    nodes += 1
                    if nodes > max_nodes:
                        raise _error("resource_exhaustion", "JSON structure exceeds the admitted node count.")
                    stack.append((item, depth))
            else:
                stack.extend((item, depth) for item in current)
        elif value_type is str:
            if any(0xD800 <= ord(char) <= 0xDFFF for char in current):
                raise _error("invalid_input", "JSON strings must contain valid Unicode scalar values.")
        elif value_type is int:
            if not 0 <= current <= MAX_STRUCTURAL_INTEGER:
                raise _error("invalid_input", "Structural integers must be within 0..9007199254740991.")
        elif current is not None and value_type is not bool:
            raise _error("invalid_input", "JSON floats and non-JSON scalar types are not admitted.")


def strict_json_loads(
    data: bytes,
    max_bytes: int = MAX_JSON_BYTES,
    max_depth: int = MAX_JSON_DEPTH,
    max_nodes: int = MAX_JSON_NODES,
) -> object:
    """Parse bounded DB-SC-1 JSON without losing duplicates or numeric spellings."""
    _limits(max_bytes, max_depth, max_nodes)
    if type(data) is not bytes:
        raise _error("invalid_input", "JSON must be supplied as UTF-8 bytes.")
    if len(data) > max_bytes:
        raise _error("resource_exhaustion", "JSON bytes exceed the admitted limit.")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise _error("invalid_input", "JSON must contain valid UTF-8.") from None
    _preflight(text, max_depth, max_nodes)

    def object_pairs(pairs: list[tuple[str, object]]) -> dict:
        result = {}
        for key, value in pairs:
            if key in result:
                raise _error("invalid_input", "Duplicate JSON object keys are not admitted.")
            result[key] = value
        return result

    def integer(token: str) -> int:
        if token.startswith("-") or len(token) > 16:
            raise _error("invalid_input", "JSON counters must be nonnegative safe integers.")
        parsed = int(token)
        if parsed > MAX_STRUCTURAL_INTEGER:
            raise _error("invalid_input", "JSON counters must be nonnegative safe integers.")
        return parsed

    def rejected_number(token: str) -> object:
        raise _error("invalid_input", "Scientific JSON scalars require exact strings; floats are not admitted.")

    try:
        value = json.loads(text, object_pairs_hook=object_pairs, parse_int=integer,
                           parse_float=rejected_number, parse_constant=rejected_number)
    except (json.JSONDecodeError, RecursionError):
        raise _error("invalid_input", "Malformed JSON input.") from None
    _validate_tree(value, max_depth, max_nodes)
    return value


def canonical_bytes(value: object) -> bytes:
    """DB-SC-1 bytes for an already schema-validated value; order arrays verbatim."""
    _validate_tree(value, MAX_JSON_DEPTH, MAX_JSON_NODES)
    # CPython's escaping has the required minimal ASCII-control spellings. The
    # tests freeze the bytes, including literal U+2028/U+2029 and no slash escape.
    encoded = json.dumps(value, ensure_ascii=False, allow_nan=False,
                         sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(encoded) > MAX_JSON_BYTES:
        raise _error("resource_exhaustion", "Canonical JSON bytes exceed the admitted limit.")
    return encoded


def semantic_digest(kind: str, body: object) -> str:
    """Hash the caller's named projection, without adding/removing any fields."""
    if type(kind) is not str or kind not in _KINDS:
        raise _error("invalid_input", "Unsupported DB-SC-1 semantic identity domain.")
    return hashlib.sha256(f"dr-bean:{kind}:v1\n".encode("ascii") + canonical_bytes(body)).hexdigest()


def artifact_digest(data: bytes) -> str:
    """Raw bytes only, deliberately distinct from semantic identity hashing."""
    if type(data) is not bytes:
        raise _error("invalid_input", "Artifact digest requires exact bytes.")
    return hashlib.sha256(data).hexdigest()
