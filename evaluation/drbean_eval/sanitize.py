"""Sanitizer for evaluation traces, and a leak scanner for release checks.

Applies to harness traces and logs only. Immutable scientific records and
exported artifacts are never passed through a redactor: they are checked with
`scan`, and a hit is a release failure to fix at its source.
"""
from __future__ import annotations

import os
import re

# Keys whose values never belong in a public trace.
DROP_KEYS = {"raw_prompt", "raw_response", "prompt", "system_prompt", "chain_of_thought", "thoughts",
             "thought_signature", "authorization", "cookie", "set-cookie", "api_key", "x-goog-api-key"}

PATTERNS = {
    "google_api_key": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "bearer_token": re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/\-]{16,}=*"),
    "generic_secret_key": re.compile(r"\b(?:sk|rk|pk)-[A-Za-z0-9_\-]{20,}"),
    "private_key_block": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "url_credential": re.compile(r"(?i)([?&](?:key|token|access_token|approval|capability|sig)=)[^&\s\"']+"),
    "email": re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    "postgres_url": re.compile(r"(?i)\bpostgres(?:ql)?://[^\s\"'@]+:[^\s\"'@]+@"),
}

# Planted diagnostics. A release test plants these in configuration and
# withheld content, then proves they appear nowhere public.
SENTINEL_CREDENTIAL = "DRBEAN-PLANTED-CREDENTIAL-7f3a9c"
SENTINEL_WITHHELD = "DRBEAN-WITHHELD-CONTENT-b41e02"
SENTINEL_OTHER_WORKSPACE = "DRBEAN-OTHER-WORKSPACE-SOURCE-55d0c8"
SENTINELS = (SENTINEL_CREDENTIAL, SENTINEL_WITHHELD, SENTINEL_OTHER_WORKSPACE)


def redact_text(text: str) -> str:
    for name, pattern in PATTERNS.items():
        if name == "url_credential":
            text = pattern.sub(lambda m: m.group(1) + "[REDACTED]", text)
        else:
            text = pattern.sub(f"[REDACTED:{name}]", text)
    return text


def sanitize(value):
    """Deep copy with dropped private keys and redacted secret-shaped strings."""
    if isinstance(value, dict):
        return {key: ("[DROPPED]" if key.lower() in DROP_KEYS else sanitize(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def find_leaks(text: str, sentinels=SENTINELS, allow_email=()) -> list[dict]:
    hits = []
    for sentinel in sentinels:
        if sentinel in text:
            hits.append({"kind": "sentinel", "match": sentinel})
    for name, pattern in PATTERNS.items():
        for match in pattern.finditer(text):
            found = match.group(0)
            if name == "email" and (found in allow_email or found.endswith(("@example.com", "@example.invalid",
                                                                           "@anthropic.com", "@openai.com"))):
                continue
            if name == "url_credential" and found.endswith("[REDACTED]"):
                continue
            hits.append({"kind": name, "match": found[:12] + "…"})
    return hits


def scan(paths, sentinels=SENTINELS, max_bytes=8 * 1024 * 1024) -> list[dict]:
    """Scan files for secret-shaped strings and planted sentinels."""
    findings = []
    for path in paths:
        try:
            if os.path.getsize(path) > max_bytes:
                continue
            with open(path, "rb") as handle:
                data = handle.read()
        except OSError:
            continue
        binary = b"\0" in data  # compressed bytes match the email shape by chance; other shapes still apply
        for hit in find_leaks(data.decode("utf-8", errors="ignore"), sentinels):
            if not (binary and hit["kind"] == "email"):
                findings.append({"path": path, **hit})
    return findings
