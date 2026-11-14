#!/usr/bin/env python3
"""Replay the supplied immutable bytes with the caller's prepared CPython 3.11."""
import base64
import json
import os
from pathlib import Path
import subprocess
import sys

HERE = Path(__file__).resolve().parent
request = {
    "protocol": "counterdex.bridge.v1", "operation": "replay",
    "native_artifact_base64": base64.b64encode((HERE / "hero-baseline.native.json").read_bytes()).decode("ascii"),
    "expected": json.loads((HERE / "hero-baseline.anchors.json").read_text(encoding="utf-8")),
}
result = subprocess.run(
    [sys.executable, "-I", "-m", "counterdex.bridge"],
    input=json.dumps(request, separators=(",", ":")).encode("utf-8"),
    capture_output=True, timeout=125, env={"PATH": os.defpath, "LANG": "C.UTF-8"},
)
sys.stdout.buffer.write(result.stdout)
sys.stderr.buffer.write(result.stderr)
raise SystemExit(result.returncode)
