"""Append-only result history: hash chain over attempt lines and digests of referenced evidence.

Records written by harness 0.2.0 and later carry ``prev_record_sha256`` (the SHA-256
of the exact bytes of the previous line, newline excluded) and, when a trace or
evidence directory exists, its digests. Earlier records (harness 0.1.0) are legacy:
they are preserved byte-for-byte and interpreted as written, and the first chained
record commits to the last legacy line, so later edits to legacy lines are caught too.

A modified, reordered or deleted line, or a changed trace or evidence file, makes
:func:`verify` report a problem; gates refuse to qualify a release from such a history.

Fork segments: when two branches append to the same history concurrently, a merge keeps the
integrated chain in ``attempts.jsonl`` and moves the other side's records, byte for byte, into
``forks/<name>.jsonl``. Each segment must be fully chained, start from a line of the main chain
(its fork point) and keep its trace/evidence digests; attempt ids stay unique across all files.
Gates read only the main chain (fork records are at other commits); nothing is rewritten.
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


FORK_DIR = "forks"


def _lines(path: str) -> list[bytes]:
    with open(path, "rb") as handle:
        return [line for line in handle if line.strip()]


def verify(results_dir: str, filename: str = "attempts.jsonl") -> list[str]:
    """Problems in the append-only history (main chain and fork segments); empty means it verifies."""
    path = os.path.join(results_dir, filename)
    if not os.path.exists(path):
        return []
    lines = _lines(path)
    seen: dict = {}
    problems = _verify_chain(results_dir, lines, "", seen, fork_points=None)
    fork_dir = os.path.join(results_dir, FORK_DIR)
    if os.path.isdir(fork_dir):
        main_digests = {line_digest(line) for line in lines}
        for name in sorted(os.listdir(fork_dir)):
            if name.endswith(".jsonl"):
                problems += _verify_chain(results_dir, _lines(os.path.join(fork_dir, name)), f"{FORK_DIR}/{name} ",
                                          seen, fork_points=main_digests)
    return problems


def _verify_chain(results_dir: str, lines: list[bytes], where: str, seen: dict, *,
                  fork_points: set[str] | None) -> list[str]:
    """One chain. A fork segment (``fork_points`` given) is fully chained from a line of the main chain."""
    problems, previous, chained = [], None, fork_points is not None
    for number, raw in enumerate(lines, 1):
        try:
            record = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            problems.append(f"{where}line {number}: not valid JSON")
            previous = raw
            continue
        attempt_id = record.get("attempt_id")
        if attempt_id in seen:
            problems.append(f"{where}line {number}: duplicate attempt_id {attempt_id} (first at {seen[attempt_id]})")
        elif attempt_id:
            seen[attempt_id] = f"{where}line {number}"
        if previous is None and fork_points is not None:
            if record.get("prev_record_sha256") not in fork_points:
                problems.append(f"{where}line {number} ({record.get('entry_id')}): fork segment does not start "
                                "from a line of the main chain")
        elif "prev_record_sha256" in record:
            chained = True
            if record["prev_record_sha256"] != (line_digest(previous) if previous is not None else GENESIS):
                problems.append(f"{where}line {number} ({record.get('entry_id')}): chain break; an earlier line "
                                "was modified, removed or reordered")
        elif chained:
            problems.append(f"{where}line {number} ({record.get('entry_id')}): unchained record after the chain began")
        trace = record.get("trace")
        if trace and record.get("trace_sha256"):
            actual = file_digest(os.path.join(results_dir, trace))
            if actual != record["trace_sha256"]:
                problems.append(f"{where}line {number} ({record.get('entry_id')}): trace {trace} "
                                f"{'missing' if actual is None else 'changed'}")
        evidence = record.get("evidence_dir")
        if evidence and record.get("evidence_index_sha256"):
            index_path = os.path.join(results_dir, evidence, "index.json")
            try:
                with open(index_path, encoding="utf-8") as handle:
                    index = json.load(handle)
            except (OSError, ValueError):
                problems.append(f"{where}line {number}: evidence index missing")
                index = None
            if index is not None:
                if index_digest(index) != record["evidence_index_sha256"]:
                    problems.append(f"{where}line {number}: evidence index changed")
                for name, item in index.items():
                    if file_digest(os.path.join(results_dir, evidence, item["path"])) != item["sha256"]:
                        problems.append(f"{where}line {number}: evidence file {name} missing or changed")
        previous = raw
    return problems
