"""Append-only result history: hash chain over attempt lines and digests of referenced evidence.

Records written by harness 0.2.0 and later carry ``prev_record_sha256`` (the SHA-256
of the exact bytes of the previous line, newline excluded) and, when a trace or
evidence directory exists, its digests. Earlier records (harness 0.1.0) are legacy:
they are preserved byte-for-byte and interpreted as written, and the first chained
record commits to the last legacy line, so later edits to legacy lines are caught too.

A modified, reordered or deleted line, or a changed trace or evidence file, makes
:func:`verify` report a problem; gates refuse to qualify a release from such a history.
"""
from __future__ import annotations

import hashlib
import json
import os

GENESIS = "0" * 64


def line_digest(line: bytes) -> str:
    return hashlib.sha256(line.rstrip(b"\n")).hexdigest()


def last_digest(path: str) -> str:
    if not os.path.exists(path):
        return GENESIS
    last = None
    with open(path, "rb") as handle:
        for line in handle:
            if line.strip():
                last = line
    return line_digest(last) if last is not None else GENESIS


def index_digest(index: dict) -> str:
    return hashlib.sha256(json.dumps(index, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def file_digest(path: str) -> str | None:
    if not os.path.isfile(path):
        return None
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def verify(results_dir: str, filename: str = "attempts.jsonl") -> list[str]:
    """Problems in the append-only history; an empty list means it verifies."""
    path = os.path.join(results_dir, filename)
    if not os.path.exists(path):
        return []
    problems, previous, chained = [], None, False
    with open(path, "rb") as handle:
        lines = [line for line in handle if line.strip()]
    for number, raw in enumerate(lines, 1):
        try:
            record = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            problems.append(f"line {number}: not valid JSON")
            previous = raw
            continue
        expected_prev = line_digest(previous) if previous is not None else GENESIS
        if "prev_record_sha256" in record:
            chained = True
            if record["prev_record_sha256"] != expected_prev:
                problems.append(f"line {number} ({record.get('entry_id')}): chain break; an earlier line was "
                                "modified, removed or reordered")
        elif chained:
            problems.append(f"line {number} ({record.get('entry_id')}): unchained record after the chain began")
        trace = record.get("trace")
        if trace and record.get("trace_sha256"):
            actual = file_digest(os.path.join(results_dir, trace))
            if actual != record["trace_sha256"]:
                problems.append(f"line {number} ({record.get('entry_id')}): trace {trace} "
                                f"{'missing' if actual is None else 'changed'}")
        evidence = record.get("evidence_dir")
        if evidence and record.get("evidence_index_sha256"):
            index_path = os.path.join(results_dir, evidence, "index.json")
            try:
                with open(index_path, encoding="utf-8") as handle:
                    index = json.load(handle)
            except (OSError, ValueError):
                problems.append(f"line {number}: evidence index missing")
                index = None
            if index is not None:
                if index_digest(index) != record["evidence_index_sha256"]:
                    problems.append(f"line {number}: evidence index changed")
                for name, item in index.items():
                    if file_digest(os.path.join(results_dir, evidence, item["path"])) != item["sha256"]:
                        problems.append(f"line {number}: evidence file {name} missing or changed")
        previous = raw
    return problems
