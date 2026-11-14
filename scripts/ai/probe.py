#!/usr/bin/env python3
"""Offline preflight only. Does not inspect credentials, accounts, models or DNS.

Run from the repository root: .venv/bin/python scripts/ai/probe.py
Its callback is explicitly controlled; no scientific result is manufactured as a
real run. Owner 5 separately qualifies actual HTTP/worker/engine integration.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
import socket
import sys

# Protect imports and implicit middleware as well as explicit requests. Allow the
# local UNIX socketpair used by asyncio, but no IP socket, DNS or UDP dispatch.
observed_external_dispatches = 0
_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex
_real_sendto = socket.socket.sendto


def _deny(*args, **kwargs):
    global observed_external_dispatches
    observed_external_dispatches += 1
    raise AssertionError("offline_preflight_external_dispatch_denied")


def _connect(sock, *args, **kwargs):
    if sock.family in {socket.AF_INET, socket.AF_INET6}:
        return _deny()
    return _real_connect(sock, *args, **kwargs)


def _connect_ex(sock, *args, **kwargs):
    if sock.family in {socket.AF_INET, socket.AF_INET6}:
        return _deny()
    return _real_connect_ex(sock, *args, **kwargs)


def _sendto(sock, *args, **kwargs):
    if sock.family in {socket.AF_INET, socket.AF_INET6}:
        return _deny()
    return _real_sendto(sock, *args, **kwargs)


socket.socket.connect = _connect
socket.socket.connect_ex = _connect_ex
socket.socket.sendto = _sendto
socket.getaddrinfo = _deny
socket.gethostbyname = _deny
socket.gethostbyname_ex = _deny
root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / "apps" / "api"))

from bean_api.ai_prompts import (  # noqa: E402
    CONVERSATION_PROMPT_VERSION, SOURCE_PROMPT_VERSION, build_conversation_prompt, build_source_prompt,
)
from bean_api.contracts import IntakeProposalBody  # noqa: E402
from bean_api.conversation import AssistantOutput  # noqa: E402
from bean_api.coordinator import CoordinatorScope, ScopedCallbacks, run_coordinator  # noqa: E402
from bean_api.providers import (  # noqa: E402
    AttemptContext, ControlledSourceProvider, GeminiProvider, ProviderConfig, ProviderFailure, package_version,
)


class NoDispatchLedger:
    def begin_attempt(self, *args, **kwargs):
        raise AssertionError("offline_preflight_live_ledger_used")

    def finish_attempt(self, *args, **kwargs):
        raise AssertionError("offline_preflight_live_ledger_used")


async def preflight():
    ledger = NoDispatchLedger()
    # Both empty and populated dummy values must remain disabled by default.
    for dummy in (None, "constant-nonsecret-dummy"):
        provider = GeminiProvider(ProviderConfig(api_key=dummy, model="dummy"), ledger, client_factory=_deny)
        assert provider.capabilities()["external_dispatch_enabled"] is False
        try:
            await provider.generate("explanation", "offline only", AssistantOutput,
                context=AttemptContext("preflight", "preflight", "preflight", "preflight"))
        except ProviderFailure as exc:
            assert exc.code == "provider_placeholder_disabled"
        else:
            raise AssertionError("offline_default_was_not_disabled")
    source_provider = ControlledSourceProvider.from_development_fixtures(root)
    packet = json.loads((root / "evaluation/sources/expected/c01a.json").read_text())
    source = {"id": "preflight_source", "body": {"sha256": packet["sha256"], "width": packet["width_px"],
        "height": packet["height_px"], "observed_media_type": packet["media_type"]}}
    proposal = source_provider.propose(source, (root / "evaluation/sources/c01a.png").read_bytes())
    IntakeProposalBody.model_validate(proposal.value.model_dump())
    assert proposal.provider_attempt_id is None and proposal.provider_requests == 0
    assert build_source_prompt(source, {}, "").startswith("Extract") or SOURCE_PROMPT_VERSION in build_source_prompt(source, {}, "")
    build_conversation_prompt({"operation": "explain", "question": "Review", "facts": [], "critical_statements": [],
        "user_context": {}, "history": [], "source_asset_ids": []})
    IntakeProposalBody.model_json_schema()
    AssistantOutput.model_json_schema()
    calls = []

    def execute(scenario):
        calls.append(scenario)
        return {"id": "controlled_preflight_fact", "problem_id": "preflight_problem", "scientific_outcome": "inconclusive",
                "verification": "not_checked", "expected_binding": "not_supplied", "replay": "not_checked",
                "provenance": "controlled tool output; not real scientific evidence"}

    result = await run_coordinator(ProviderConfig(mode="controlled"), ledger,
        AttemptContext("preflight", "preflight", "preflight", "preflight"),
        CoordinatorScope("preflight_run", "preflight_plan", "preflight_problem", "baseline", wall_seconds=30),
        ScopedCallbacks(check_authority=lambda: None, execute_scenario=execute,
            read_evidence=lambda _: None, record_skip=lambda *_: None))
    assert result.status == "completed", result.error_code
    assert calls == ["baseline"]
    assert result.runtime["provider_requests"] == 0 and result.runtime["provider_usage"] is None
    assert result.runtime["tool_inventory"] == sorted(["execute_approved_scenario", "read_scoped_evidence", "record_allowed_skip", "return_grounded_explanation"])
    assert observed_external_dispatches == 0
    return {"status": "offline_preflight_passed", "gemini_live_qualification": "pending",
            "label": "controlled placeholder output; not Gemini reasoning",
            "observed_live_requests_this_run": 0, "observed_live_usage_this_run": 0,
            "historical_ledger": "not read or modified", "external_dispatch_attempts": observed_external_dispatches,
            "tools": result.runtime["tool_inventory"], "controlled_callback_count": len(calls),
            "actual_scientific_jobs": 0,
            "versions": {name: package_version(name) for name in ("google-genai", "deepagents", "langchain-google-genai")},
            "prompt_versions": {"source": SOURCE_PROMPT_VERSION, "conversation": CONVERSATION_PROMPT_VERSION}}


if __name__ == "__main__":
    print(json.dumps(asyncio.run(preflight()), sort_keys=True))
