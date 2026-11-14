"""Bounded local parsing of CSV, TSV, JSON, plain text and Markdown.

Column names, units and cell spellings are preserved exactly as written. A unit is
reported only when the header prints it in a trailing bracket; everything else stays
``unresolved``. Empty cells stay empty strings, missing cells (short rows) stay null,
and no value is converted through floating point. These summaries describe the file;
they are not scientific validation. Every limit refuses explicitly; nothing is
truncated while claiming the whole file was read.
"""
from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
import io
import json
import re

from . import limits as L


class ParseRefused(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(code)
        self.code, self.message = code, message


SIGNATURES = (b"%PDF-", b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"PK\x03\x04", b"\xd0\xcf\x11\xe0", b"GIF8")
MISSING_TOKENS = {"na", "n/a", "nan", "null", "none", "nd", "n.d.", "-", "--", "?", "missing", ".", "#n/a"}
_MARKER = re.compile(r"[*\-.?]+|-?9{3,}(?:\.0+)?")  # ***, ---, -999, 9999: common written missing-value markers
_RDB_FORMAT = re.compile(r"\d+[sdn]")
_NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d{1,4})?")
_NUMBER_COMMA = re.compile(r"[+-]?\d+(?:,\d+)?(?:[eE][+-]?\d{1,4})?")
_UNIT = (re.compile(r"\(([^()]{1,32})\)\s*$"), re.compile(r"\[([^\[\]]{1,32})\]\s*$"),
         re.compile(r"\{([^{}]{1,32})\}\s*$"))
_HEADING = re.compile(r"^(#{1,6})\s+(.{1,200})$", re.M)


def decode_text(raw: bytes) -> tuple[str, str, list[str]]:
    """Decode user text without guessing silently; returns (text, encoding, warnings)."""
    if any(raw.startswith(signature) for signature in SIGNATURES):
        raise ParseRefused("media_type_mismatch", "The bytes are a binary file, not text.")
    warnings: list[str] = []
    if raw.startswith(b"\xef\xbb\xbf"):
        encoding = "utf-8-sig"
    elif raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        encoding = "utf-16"
    else:
        encoding = "utf-8"
    try:
        text = raw.decode(encoding)
    except UnicodeDecodeError:
        if encoding != "utf-8":
            raise ParseRefused("text_encoding_unsupported", "The text is not valid in its declared Unicode encoding.") from None
        try:
            text = raw.decode("cp1252")
        except UnicodeDecodeError:
            raise ParseRefused("text_encoding_unsupported", "Save the file as UTF-8 text and upload it again.") from None
        encoding = "cp1252"
        warnings.append("decoded_as_windows_1252_not_utf8")
    if "\x00" in text:
        raise ParseRefused("binary_content", "The file contains binary data, not text.")
    controls = sum(1 for ch in text if ord(ch) < 32 and ch not in "\t\r\n\f")
    if controls > max(8, len(text) // 100):
        raise ParseRefused("binary_content", "The file contains binary data, not text.")
    if len(text) > L.MAX_TEXT_CHARS:
        raise ParseRefused("text_limit", "The text exceeds the admitted character limit.")
    if not text.strip():
        raise ParseRefused("empty_text", "The file contains no text.")
    return text, encoding, warnings


def header_unit(name: str) -> str | None:
    for pattern in _UNIT:
        match = pattern.search(name)
        if match:
            unit = match.group(1).strip()
            if unit and "=" not in unit and not unit.replace(".", "").isdigit():
                return unit
    return None


def _number(value: str, decimal_comma: bool) -> Decimal | None:
    text = value.strip()
    if not text or len(text) > 64:
        return None
    if _NUMBER.fullmatch(text):
        candidate = text
    elif decimal_comma and _NUMBER_COMMA.fullmatch(text):
        candidate = text.replace(",", ".")
    else:
        return None
    try:
        number = Decimal(candidate)
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def describe_columns(names: list[str], rows: list[list[str | None]], *, decimal_comma: bool = False) -> list[dict]:
    columns = []
    for index, name in enumerate(names):
        empty = missing = numeric = text = absent = 0
        low = high = None
        for row in rows:
            value = row[index] if index < len(row) else None
            if value is None:
                absent += 1
                continue
            stripped = value.strip()
            if not stripped:
                empty += 1
            elif stripped.lower() in MISSING_TOKENS or (_MARKER.fullmatch(stripped) and not stripped.isdigit()):
                missing += 1
            else:
                number = _number(stripped, decimal_comma)
                if number is None:
                    text += 1
                else:
                    numeric += 1
                    if low is None or number < low[0]:
                        low = (number, stripped)
                    if high is None or number > high[0]:
                        high = (number, stripped)
        present = numeric + text
        kind = ("empty" if present == 0 else "numeric" if numeric and text == 0
                else "text" if numeric == 0 else "mixed")
        unit = header_unit(name)
        columns.append({"index": index, "name": name, "unit": unit,
                        "unit_status": "stated_in_header" if unit else "unresolved",
                        "kind": kind, "numeric_cells": numeric, "text_cells": text, "empty_cells": empty,
                        "missing_marker_cells": missing, "absent_cells": absent,
                        "min_as_written": low[1] if low else None, "max_as_written": high[1] if high else None})
    return columns


def _sniff_delimiter(lines: list[str]) -> str:
    best, best_score = ",", -1
    for delimiter in (",", ";", "\t", "|"):
        counts = [len(next(csv.reader([line], delimiter=delimiter))) for line in lines[:21] if line.strip()]
        if not counts:
            continue
        mode = max(set(counts), key=counts.count)
        if mode < 2:
            continue
        score = counts.count(mode) * 1000 + mode
        if score > best_score:
            best, best_score = delimiter, score
    return best


def parse_delimited(text: str, media_type: str) -> dict:
    lines = text.splitlines()
    preamble = 0
    while preamble < len(lines) and lines[preamble].lstrip().startswith("#"):
        preamble += 1
    if not any(line.strip() for line in lines[preamble:]):
        raise ParseRefused("table_empty", "No header row was found after the comment lines.")
    delimiter = "\t" if media_type == "text/tab-separated-values" else _sniff_delimiter(
        [line for line in lines[preamble:] if line.strip()])
    title_lines = []
    candidates = [line for line in lines[preamble:preamble + 6] if line.strip()]
    if len(candidates) >= 3:
        widths = [len(next(csv.reader([line], delimiter=delimiter))) for line in candidates]
        if widths[0] == 1 and widths[1] > 1 and widths[1] == widths[2]:
            title_lines.append(candidates[0])
            preamble = lines.index(candidates[0], preamble) + 1
    body_lines = lines[preamble:]
    previous = csv.field_size_limit()
    csv.field_size_limit(L.MAX_FIELD_CHARS)
    rows, row_lines, blank = [], [], 0
    try:
        stream = io.StringIO("\n".join(body_lines), newline="")
        reader = csv.reader(stream, delimiter=delimiter, quotechar='"', doublequote=True, strict=True)
        for row in reader:
            if not row or (len(row) == 1 and not row[0].strip()):
                blank += 1
                continue
            rows.append(row)
            row_lines.append(preamble + reader.line_num)
            if len(rows) > L.MAX_TABLE_ROWS + 1:
                raise ParseRefused("table_row_limit", f"The table has more than {L.MAX_TABLE_ROWS:,} rows.")
            if len(row) > L.MAX_TABLE_COLUMNS:
                raise ParseRefused("table_column_limit", f"The table has more than {L.MAX_TABLE_COLUMNS} columns.")
    except csv.Error:
        raise ParseRefused("malformed_table", "The table has an unterminated quote or an oversized field.") from None
    finally:
        csv.field_size_limit(previous)
    header, data = rows[0], rows[1:]
    width = len(header)
    format_row_line = None
    if data and len(data[0]) == width and all(_RDB_FORMAT.fullmatch(cell.strip()) for cell in data[0]):
        format_row_line = row_lines[1]
        data, row_lines = data[1:], row_lines[:1] + row_lines[2:]
    ragged = [row_lines[i + 1] for i, row in enumerate(data) if len(row) != width]
    normalized = [row + [None] * (width - len(row)) if len(row) < width else row[:width] for row in data]
    extra_cells = sum(max(0, len(row) - width) for row in data)
    warnings = []
    if ragged:
        warnings.append("rows_with_different_field_counts")
    if extra_cells:
        warnings.append("cells_beyond_header_width_not_assigned_to_columns")
    if len(set(header)) != len(header):
        warnings.append("duplicate_column_names")
    if any(not name.strip() for name in header):
        warnings.append("unnamed_columns")
    if all(_number(name, delimiter == ";") is not None for name in header if name.strip()):
        warnings.append("first_row_looks_numeric_header_may_be_absent")
    if title_lines:
        warnings.append("title_line_before_header")
    if format_row_line:
        warnings.append("rdb_column_format_row_excluded_from_data")
    if data and all(_number(cell, delimiter == ";") is None for cell in data[0] if cell.strip()) and any(
            _number(cell, delimiter == ";") is not None for row in data[1:4] for cell in row if cell.strip()):
        warnings.append("first_data_row_may_hold_units_or_labels_not_applied")
    decimal_comma = delimiter == ";"
    return {"kind": "table", "delimiter": delimiter, "comment_lines": preamble,
            "comment_preview": lines[:min(preamble, 12)], "title_lines": title_lines,
            "format_row_line": format_row_line, "header_line": row_lines[0],
            "row_count": len(data), "column_count": width, "blank_lines": blank,
            "decimal_comma_candidate": decimal_comma,
            "columns": describe_columns(header, normalized, decimal_comma=decimal_comma),
            "preview_rows": [{"line": row_lines[i + 1], "cells": normalized[i]}
                             for i in range(min(L.TABLE_PREVIEW_ROWS, len(normalized)))],
            "ragged_row_lines": ragged[:20], "ragged_row_count": len(ragged), "extra_cells": extra_cells,
            "warnings": warnings}


class _Number(str):
    """A JSON number kept as its exact source spelling."""


def _json_prescan(text: str) -> tuple[int, int]:
    depth = max_depth = nodes = 0
    in_string = escaped = False
    for ch in text:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            nodes += 1
        elif ch in "[{":
            depth += 1
            nodes += 1
            if depth > L.MAX_JSON_DEPTH:
                raise ParseRefused("json_nesting_limit", f"The JSON nests deeper than {L.MAX_JSON_DEPTH} levels.")
            max_depth = max(max_depth, depth)
        elif ch in "]}":
            depth -= 1
        elif ch == ",":
            nodes += 1
        if nodes > L.MAX_JSON_NODES:
            raise ParseRefused("json_node_limit", "The JSON contains more values than admitted.")
    return max_depth, nodes


def _dump(value) -> str:
    """Exact JSON text for a parsed value; numbers keep their source spelling."""
    if isinstance(value, _Number):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, _Pairs):
        return "{" + ",".join(json.dumps(key, ensure_ascii=False) + ":" + _dump(item) for key, item in value) + "}"
    if isinstance(value, list):
        return "[" + ",".join(_dump(item) for item in value) + "]"
    return "true" if value is True else "false" if value is False else "null"


def _cell(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return str(value)
    text = _dump(value)
    return text if len(text) <= 200 else text[:199] + "\u2026"


class _Pairs(list):
    """An object kept as ordered key/value pairs so duplicate keys are not lost."""


def _flatten(record: _Pairs) -> list[tuple[str, object]]:
    flat = []
    for key, value in record:
        if isinstance(value, _Pairs):
            flat.extend((f"{key}.{inner}", item) for inner, item in value)
        else:
            flat.append((key, value))
    return flat


def _record_tables(value, path: str = "$", depth: int = 0) -> list[dict]:
    found = []
    if isinstance(value, list) and value and all(isinstance(item, _Pairs) for item in value):
        names: list[str] = []
        rows_pairs = [_flatten(item) for item in value]
        for pairs in rows_pairs:
            for key, _ in pairs:
                if key not in names:
                    names.append(key)
                    if len(names) > L.MAX_TABLE_COLUMNS:
                        raise ParseRefused("table_column_limit", "A JSON record array has too many fields.")
        rows = []
        for pairs in rows_pairs:
            mapping = {}
            for key, item in pairs:
                mapping.setdefault(key, item)
            rows.append([_cell(mapping[name]) if name in mapping else None for name in names])
        columns = describe_columns(names, rows)
        found.append({"json_path": path, "row_count": len(rows), "column_count": len(names), "columns": columns,
                      "preview_rows": [{"index": i, "cells": rows[i]} for i in range(min(L.TABLE_PREVIEW_ROWS,
                                                                                         len(rows)))]})
    elif isinstance(value, _Pairs) and depth < 2:
        for key, item in value:
            found.extend(_record_tables(item, f"{path}.{key}" if re.fullmatch(r"[A-Za-z_]\w{0,63}", key)
                                        else f"{path}[{json.dumps(key)}]", depth + 1))
    return found[:8]


def parse_json_document(text: str) -> dict:
    max_depth, nodes = _json_prescan(text)
    warnings: list[str] = []
    duplicates: list[str] = []

    def pairs(items):
        seen = set()
        for key, _ in items:
            if key in seen and len(duplicates) < 20:
                duplicates.append(key)
            seen.add(key)
        return _Pairs(items)

    def constant(name: str):
        warnings.append("nonstandard_json_constant")
        return _Number(name)

    try:
        value = json.loads(text, object_pairs_hook=pairs, parse_float=_Number, parse_int=_Number,
                           parse_constant=constant)
    except (json.JSONDecodeError, RecursionError):
        raise ParseRefused("malformed_json", "The JSON is not valid.") from None
    if duplicates:
        warnings.append("duplicate_object_keys")
    top = ("object" if isinstance(value, _Pairs) else "array" if isinstance(value, list)
           else "string" if isinstance(value, str) and not isinstance(value, _Number)
           else "number" if isinstance(value, _Number) else "literal")
    keys = [key for key, _ in value][:50] if isinstance(value, _Pairs) else []
    return {"kind": "json", "top_level": top, "top_level_keys": keys, "max_depth": max_depth,
            "value_count_estimate": nodes, "duplicate_keys": sorted(set(duplicates)),
            "tables": _record_tables(value), "warnings": sorted(set(warnings))}


def parse_text(text: str, media_type: str) -> dict:
    headings = [{"level": len(match.group(1)), "text": match.group(2).strip()}
                for match in _HEADING.finditer(text)][:40] if media_type == "text/markdown" else []
    return {"kind": "markdown" if media_type == "text/markdown" else "text",
            "line_count": text.count("\n") + 1, "char_count": len(text), "headings": headings, "warnings": []}
