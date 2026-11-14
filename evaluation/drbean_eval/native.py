"""Downloaded-evidence validation and fresh native replay.

Fresh native replay runs the project's own checker (Counterdex) again in a new
CPython 3.11 process in isolated mode. It is a re-execution of the same checker on
the downloaded bytes, NOT an independent proof system.

Rules this module enforces:

* the interpreter and package directory are chosen by the operator, never by the
  evidence being tested;
* expected anchors come from the authenticated application record (the expected
  run/problem/design), never only from the bundle under test;
* an application entity envelope (JSON with ``kind``/``body``/``workspace_id``) is
  classified as such: a record that merely references an artifact is not a native
  replay packet;
* hash, length and media type of the bytes are checked against the recorded
  reference and the response header before any replay.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GUARD_FILE = os.path.join(HERE, "guard", "sitecustomize.py")

# Where an authenticated application record may carry the expected scientific
# anchors. Owner 2 owns the final names; extend this list deliberately when the
# contract lands. The value must come from the API record, not from the bundle.
ANCHOR_KEYS = {
    "problem_digest": ("scientific_problem_digest", "scientific_projection_digest", "projection_digest",
                       "science_problem_digest", "expected_scientific_problem_digest", "counterdex_problem_digest"),
    "suggestion_digest": ("suggestion_digest", "expected_suggestion_digest", "scientific_suggestion_digest"),
    "design_digest": ("scientific_design_digest", "design_digest", "expected_design_digest"),
}

_BOOTSTRAP = r"""
import importlib.util, os, sys
guard = os.environ.get("DRBEAN_GUARD_FILE")
if guard and os.environ.get("DRBEAN_EGRESS_GUARD_LOG"):
    spec = importlib.util.spec_from_file_location("drbean_guard", guard)
    spec.loader.exec_module(importlib.util.module_from_spec(spec))
sys.path.insert(0, os.environ["DRBEAN_COUNTERDEX_DIR"])
from counterdex.__main__ import main
sys.exit(main(sys.argv[1:]))
"""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def validate_download(reference: dict, data: bytes, headers: dict) -> list[dict]:
    """Checks that tie downloaded bytes to the recorded ArtifactReference and response header."""
    digest = sha256(data)
    header = (headers or {}).get("x-artifact-sha256")
    media = ((headers or {}).get("content-type") or "").split(";")[0].strip()
    return [
        {"id": "bytes_match_recorded_sha256", "passed": digest == reference.get("sha256"),
         "detail": f"downloaded {digest[:16]}, recorded {str(reference.get('sha256'))[:16]}"},
        {"id": "bytes_match_response_header", "passed": header == digest,
         "detail": f"header {str(header)[:16]}"},
        {"id": "length_matches_recorded_byte_size", "passed": len(data) == reference.get("byte_size"),
         "detail": f"{len(data)} bytes, recorded {reference.get('byte_size')}"},
        {"id": "media_type_matches_reference", "passed": media == reference.get("media_type"),
         "detail": f"served {media or '<none>'}, recorded {reference.get('media_type')}"},
    ]


def classify(data: bytes) -> dict:
    """native_packet | entity_envelope | unparsed. Parsing here is for classification only."""
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return {"class": "unparsed"}
    if isinstance(value, dict) and {"kind", "body", "workspace_id"} <= set(value):
        return {"class": "entity_envelope", "kind": value.get("kind"),
                "note": "an application record envelope is not a native replay packet"}
    schema = value.get("schema_version") if isinstance(value, dict) else None
    if isinstance(schema, str) and schema.startswith("groundwork."):
        return {"class": "native_packet", "schema_version": schema,
                "top_level_keys": sorted(value)[:40]}
    return {"class": "unrecognized_json", "top_level_keys": sorted(value)[:40] if isinstance(value, dict) else None}


def anchors_from_record(*records: dict) -> dict:
    """Search authenticated record JSON (any depth) for expected scientific anchors."""
    found: dict = {}

    def walk(value, depth=0):
        if depth > 12:
            return
        if isinstance(value, dict):
            for key, item in value.items():
                for anchor, names in ANCHOR_KEYS.items():
                    if key in names and isinstance(item, str) and len(item) == 64 and anchor not in found:
                        found[anchor] = item
                walk(item, depth + 1)
        elif isinstance(value, list):
            for item in value:
                walk(item, depth + 1)

    for record in records:
        walk(record)
    return found


def replay(science_python: str, package_dir: str, data: bytes, anchors: dict, *,
           guard_log: str | None = None, timeout: float = 120.0) -> dict:
    """Fresh replay of downloaded bytes against separately supplied anchors."""
    with tempfile.TemporaryDirectory(prefix="drbean-replay-") as work:
        bundle = os.path.join(work, "bundle.json")
        with open(bundle, "wb") as handle:
            handle.write(data)
        argv = [science_python, "-I", "-c", _BOOTSTRAP, "replay", bundle]
        clean = {k: v for k, v in anchors.items() if k in ("problem_digest", "suggestion_digest") and v}
        if clean:
            anchor_path = os.path.join(work, "anchors.json")
            with open(anchor_path, "w", encoding="utf-8") as handle:
                json.dump(clean, handle)
            argv += ["--anchors", anchor_path]
        env = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": work, "TMPDIR": work,
               "DRBEAN_COUNTERDEX_DIR": os.path.abspath(package_dir), "DRBEAN_GUARD_FILE": GUARD_FILE}
        if guard_log:
            env["DRBEAN_EGRESS_GUARD_LOG"] = guard_log
        try:
            done = subprocess.run(argv, capture_output=True, timeout=timeout, env=env, cwd=work)
        except subprocess.TimeoutExpired:
            return {"status": "timed_out", "exit_code": None, "anchors_supplied": sorted(clean)}
    report = _json_line(done.stdout)
    error = _json_line(done.stderr)
    status = "error"
    if report is not None:
        status = "passed" if report.get("replay") == "passed" else "failed"
    elif error is not None:
        status = "rejected"
    return {"status": status, "exit_code": done.returncode, "report": report,
            "error": (error or {}).get("error") if isinstance(error, dict) else None,
            "anchors_supplied": sorted(clean)}


def _json_line(raw: bytes):
    text = raw.decode("utf-8", "replace").strip()
    if not text:
        return None
    try:
        return json.loads(text.splitlines()[-1])
    except ValueError:
        return None


def flip_one_byte(data: bytes) -> bytes:
    """Integrity control: change one byte inside a JSON string value, keeping valid JSON."""
    text = data.decode("utf-8")
    for marker in ('"reason_code":"', '"proof_rule":"', '"schema_version":"'):
        index = text.find(marker)
        if index >= 0:
            position = index + len(marker)
            if position < len(text) and text[position] not in '"\\':
                replacement = "X" if text[position] != "X" else "Y"
                return (text[:position] + replacement + text[position + 1:]).encode("utf-8")
    middle = len(data) // 2
    return data[:middle] + bytes([data[middle] ^ 0x01]) + data[middle + 1:]


def wrong_anchor(anchor: str) -> str:
    """A syntactically valid but different expected identity."""
    return hashlib.sha256(("wrong-expected-identity:" + anchor).encode()).hexdigest()
