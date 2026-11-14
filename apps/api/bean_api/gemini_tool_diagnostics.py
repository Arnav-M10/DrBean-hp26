"""Bounded validation labels; never retain provider arguments or raw errors."""
from __future__ import annotations

import re

from .providers import ProviderFailure

REASONS = frozenset({"unknown_tool", "missing_required", "unknown_arguments", "wrong_argument_type",
                    "schema_constraint", "strict_validation", "incremental_call", "duplicate_id",
                    "invalid_id", "invalid_tool_call"})
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_.:-]{0,127}\Z")


def _declared_fields(schema):
    fields, pending = set(), [(schema, 0)]
    while pending:
        current, depth = pending.pop()
        if not isinstance(current, dict) or depth > 32:
            continue
        properties = current.get("properties", {})
        if isinstance(properties, dict):
            fields.update(name for name in properties if isinstance(name, str) and _NAME.fullmatch(name))
            pending.extend((child, depth + 1) for child in properties.values())
        definitions = current.get("$defs", {})
        if isinstance(definitions, dict):
            pending.extend((child, depth + 1) for child in definitions.values())
        pending.extend((current.get(key), depth + 1) for key in ("items", "additionalProperties"))
        for key in ("anyOf", "oneOf", "allOf"):
            if isinstance(current.get(key), list):
                pending.extend((child, depth + 1) for child in current[key])
    return fields


def safe_validation_detail(value, declarations):
    """Recheck diagnostics against the trusted outbound schemas before storage."""
    if type(value) is not dict or not isinstance(value.get("reason"), str) or value["reason"] not in REASONS:
        return None
    result = {"reason": value["reason"]}
    name = value.get("tool_name")
    if isinstance(name, str) and _NAME.fullmatch(name) and name in declarations:
        result["tool_name"] = name
        fields = value.get("missing_fields")
        if value["reason"] == "missing_required" and type(fields) in (list, tuple):
            declared = _declared_fields(declarations[name])
            missing = sorted({field for field in fields if isinstance(field, str) and field in declared})[:16]
            if missing:
                result["missing_fields"] = missing
    return result


class ToolCallValidationFailure(ProviderFailure):
    """The public error code stays stable; the optional detail contains labels only."""

    def __init__(self, reason, declarations, *, tool_name=None, missing_fields=()):
        super().__init__("provider_malformed_tool_call")
        self.validation_detail = safe_validation_detail(
            {"reason": reason, "tool_name": tool_name, "missing_fields": missing_fields}, declarations)
