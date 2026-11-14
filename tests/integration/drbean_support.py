"""Helpers shared by Workstream 5 integration tests (imported by conftest and test modules)."""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EVALUATION = REPO / "evaluation"
if str(EVALUATION) not in sys.path:
    sys.path.insert(0, str(EVALUATION))

from drbean_eval import launcher  # noqa: E402
from drbean_eval.http_client import ApiClient  # noqa: E402

# A lane runner names the log (DRBEAN_SESSION_GUARD_LOG) so its report can count this process's guard events.
SESSION_GUARD_LOG = (os.environ.get("DRBEAN_SESSION_GUARD_LOG")
                     or os.path.join(tempfile.gettempdir(), f"drbean-pytest-guard-{os.getpid()}.jsonl"))


def announce_guard_probe(expect: str, test: str) -> None:
    """Label the next guard event of kind ``expect`` in this process as a deliberate self-test of the guard.

    Lane accounting pairs each announcement with that one event and reports it as a probe. Any blocked event without
    an announcement still counts as an attempted external model request."""
    import time
    with open(SESSION_GUARD_LOG, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"kind": "guard_self_test_probe", "expect": expect, "test": test,
                                 "pid": os.getpid(), "at": time.time()}) + "\n")


def session_guard_events() -> list[dict]:
    if not os.path.exists(SESSION_GUARD_LOG):
        return []
    with open(SESSION_GUARD_LOG, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def load_packet(name: str) -> dict:
    return json.loads((EVALUATION / "cases" / "science" / f"{name}.json").read_text(encoding="utf-8"))


def reviewer(stack: launcher.LocalStack) -> ApiClient:
    return ApiClient(stack.base_url, stack.tokens[launcher.REVIEWER])


def other_actor(stack: launcher.LocalStack) -> ApiClient:
    return ApiClient(stack.base_url, stack.tokens[launcher.OTHER_ACTOR])
