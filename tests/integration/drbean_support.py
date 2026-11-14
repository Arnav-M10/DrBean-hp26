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

SESSION_GUARD_LOG = os.path.join(tempfile.gettempdir(), f"drbean-pytest-guard-{os.getpid()}.jsonl")


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
