"""Zero external model dispatch: enforceable, not assumed (Workstream 5).

Every launched API, worker and scientific child loads the egress guard, so a dispatch
attempt is refused AND recorded; the test then fails on the record, because an attempt
is a P0 finding even when the guard prevented any packet or charge.

Configurations use obviously fake ``DRBEAN-DUMMY-...`` values. No real key is read,
copied or tested; the launcher refuses anything that is not a dummy value.
"""
from __future__ import annotations

import socket
import time
from pathlib import Path

import pytest

from drbean_support import REPO, load_packet, reviewer, session_guard_events

pytestmark = [pytest.mark.zero_dispatch]
DUMMY_KEY = "DRBEAN-DUMMY-KEY-0001"
DUMMY_MODEL = "drbean-placeholder-model"
LEGACY_LIVE_SWITCH = {"GEMINI_API_KEY": DUMMY_KEY, "GEMINI_MODEL": DUMMY_MODEL, "BEAN_GEMINI_ACCOUNT_GATE": "approved",
                      "BEAN_GEMINI_ACCOUNT_DECISION_ID": "DRBEAN-DUMMY-DECISION-0001",
                      "BEAN_GEMINI_IMAGE_TOKEN_BOUND": "1000"}


def test_pytest_process_itself_is_egress_guarded():
    before = len(session_guard_events())
    with pytest.raises(OSError):
        socket.create_connection(("generativelanguage.googleapis.com", 443), timeout=1)
    events = session_guard_events()[before:]
    assert [e["kind"] for e in events] == ["egress_blocked"]
    assert events[0]["host"] == "generativelanguage.googleapis.com"


def exercise_model_paths(stack) -> dict:
    """Drive every route that could reach a provider in this release; returns what the API said."""
    client = reviewer(stack)
    seen = {"capabilities": client.raw("GET", "/capabilities", authenticated=False).json()}
    workspace = client.post("/workspaces", {"name": "zero dispatch"})["id"]
    raw = (REPO / "fixtures" / "intake" / "clean.png").read_bytes()
    upload = client.raw("POST", f"/workspaces/{workspace}/source-assets?origin=synthetic&retention=retain",
                        body=raw, content_type="image/png", key=client.new_key("upload"))
    seen["upload_status"] = upload.status
    model = (seen["capabilities"].get("gemini") or {}).get("model") or DUMMY_MODEL
    consent = {"provider": "gemini", "model": model, "include_notes": True, "include_existing_values": True,
               "accepted": True}
    if upload.status == 201:
        source = upload.json()["id"]
        intake = client.raw("POST", f"/workspaces/{workspace}/intake-proposals",
                            body=_json({"source_id": source, "notes": "transcribe the table",
                                        "consent": {**consent, "source_asset_ids": [source]}}),
                            content_type="application/json", key=client.new_key("intake"))
        seen["intake_status"] = intake.status
    for index, operation in enumerate(("explain", "interpret_design", "interpret_observation")):
        key = client.new_key(f"turn{index}")
        turn = client.raw("POST", f"/workspaces/{workspace}/assistant-turns", body=_json({
            "operation": operation, "client_operation_id": key, "expected_conversation_revision": index,
            "text": "Explain the evidence and propose the next measurement at 6 and 8 hours with 0.2 mg/L.",
            "consent": {**consent, "source_asset_ids": []}}), content_type="application/json", key=key)
        seen[f"turn_{operation}"] = turn.status
    hero = load_packet("hero-v1")
    dataset = client.post(f"/workspaces/{workspace}/datasets", hero["dataset"])
    problem = client.post(f"/workspaces/{workspace}/problems", {**hero["problem"], "dataset_id": dataset["id"],
                                                                 "dataset_digest": dataset["digest"]})
    permission = client.post(f"/workspaces/{workspace}/provider-consents", {
        "provider": "gemini", "model": model, "source_asset_ids": [], "context_fields": ["problem", "dataset"],
        "problem_id": problem["id"], "accepted": True})
    plan = client.post(f"/workspaces/{workspace}/plans", {"expected_current_revision_id": problem["id"], "plan": {
        "schema_version": "DB-SC-1", "problem_id": problem["id"], "problem_digest": problem["digest"],
        "dataset_id": dataset["id"], "scenarios": [{"id": "baseline", "problem_id": problem["id"],
                                                     "problem_digest": problem["digest"], "kind": "baseline",
                                                     "label": "agent baseline"}],
        "provider_disclosure": {"provider": "gemini", "model": model, "context_fields": ["problem", "dataset"],
                                "permission_id": permission["id"]}}})
    approval = client.post(f"/plans/{plan['id']}/approvals", {"expected_plan_digest": plan["digest"],
                           "expected_current_revision_id": problem["id"], "accepted": True})
    run = client.post(f"/plans/{plan['id']}/runs", {"approval_id": approval["id"], "expected_plan_digest": plan["digest"]})
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        state = client.get(f"/runs/{run['id']}")
        if state["state"] in {"completed", "failed", "cancelled", "interrupted"}:
            break
        time.sleep(0.3)
    seen["agent_run"] = {"state": state["state"], "error_code": state.get("error_code")}
    seen["provider_attempts"] = client.get(f"/workspaces/{workspace}/provider-attempts")
    return seen


def _json(value) -> bytes:
    import json
    return json.dumps(value).encode()


def assert_no_external_attempt(stack):
    events = stack.guard_events()
    installed = {e["pid"] for e in events if e["kind"] == "guard_installed"}
    assert stack.processes["api"].pid in installed, "the API ran without the egress guard"
    assert stack.processes["worker"].pid in installed, "the worker ran without the egress guard"
    attempts = stack.external_attempts()
    assert not attempts, ("external model attempt(s) recorded by the guard (P0, finding F-EXTERNAL-ATTEMPT): "
                          + "; ".join(f"{a['kind']} {a.get('host') or a.get('client')} via {a['stack'][-3:]}"
                                      for a in attempts[:3]))


@pytest.mark.real_stack
def test_default_configuration_attempts_no_external_model_request(stack_factory):
    stack = stack_factory()
    seen = exercise_model_paths(stack)
    assert_no_external_attempt(stack)
    gemini = seen["capabilities"]["gemini"]
    assert gemini["verified_in_environment"] is False and gemini["configured"] is False
    assert seen["capabilities"]["deepagents"]["verified_in_environment"] is False
    assert seen["agent_run"]["state"] == "failed"  # an AI plan cannot silently run without a provider
    assert all(a["state"] != "completed" for a in seen["provider_attempts"])


@pytest.mark.real_stack
def test_dummy_key_alone_cannot_activate_dispatch(stack_factory):
    stack = stack_factory(stack_env={"GEMINI_API_KEY": DUMMY_KEY, "GEMINI_MODEL": DUMMY_MODEL},
                          allow_dummy_provider_config=True)
    exercise_model_paths(stack)
    assert_no_external_attempt(stack)


@pytest.mark.real_stack
def test_legacy_documented_live_switch_with_dummy_values_still_cannot_dispatch(stack_factory):
    """The pre-placeholder runbook switch (.env.example gate variables) must not activate a live provider.

    Activation now needs a new explicit user instruction plus a deliberate new configuration change
    (Owner 3's explicit mode). Until that exists, these settings construct a Gemini client and attempt
    dispatch; the guard refuses it and this test fails on the recorded attempt (finding F-PLACEHOLDER-AUTO).
    """
    stack = stack_factory(stack_env=LEGACY_LIVE_SWITCH, allow_dummy_provider_config=True)
    exercise_model_paths(stack)
    assert_no_external_attempt(stack)


@pytest.mark.real_stack
def test_placeholder_mode_is_explicit_in_capabilities(module_stack):
    gemini = reviewer(module_stack).raw("GET", "/capabilities", authenticated=False).json()["gemini"]
    mode = gemini.get("mode") or gemini.get("provider_mode") or gemini.get("execution_mode")
    assert mode in {"placeholder", "disabled", "controlled_placeholder", "offline_placeholder"}, (
        f"capabilities.gemini declares no explicit placeholder/disabled mode (got {mode!r}); finding F-PLACEHOLDER-MODE "
        "(Owner 3): the default must be an explicit disabled/placeholder mode, not merely 'not configured'")


def test_guard_spies_refuse_client_construction_but_allow_sdk_types():
    from google.genai import types  # local SDK types and schemas stay allowed
    assert types.GenerateContentConfig.__name__
    from google import genai
    before = len(session_guard_events())
    with pytest.raises(RuntimeError, match="egress guard"):
        genai.Client(api_key=DUMMY_KEY)
    assert [e["kind"] for e in session_guard_events()[before:]] == ["provider_client_blocked"]


def test_repository_ships_no_real_looking_credentials():
    import re
    pattern = re.compile(r"AIza[0-9A-Za-z_\-]{35}")
    offenders = []
    for path in list((REPO / "evaluation").rglob("*.py")) + list((REPO / "tests").rglob("*.py")) + [REPO / ".env.example"]:
        if pattern.search(Path(path).read_text(encoding="utf-8", errors="ignore")):
            offenders.append(str(Path(path).relative_to(REPO)))
    assert offenders == []
