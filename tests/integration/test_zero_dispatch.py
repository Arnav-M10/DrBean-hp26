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

from drbean_support import REPO, announce_guard_probe, load_packet, reviewer, session_guard_events

pytestmark = [pytest.mark.zero_dispatch]
DUMMY_KEY = "DRBEAN-DUMMY-KEY-0001"
DUMMY_MODEL = "drbean-placeholder-model"
LEGACY_LIVE_SWITCH = {"GEMINI_API_KEY": DUMMY_KEY, "GEMINI_MODEL": DUMMY_MODEL, "BEAN_GEMINI_ACCOUNT_GATE": "approved",
                      "BEAN_GEMINI_ACCOUNT_DECISION_ID": "DRBEAN-DUMMY-DECISION-0001",
                      "BEAN_GEMINI_IMAGE_TOKEN_BOUND": "1000"}


def test_pytest_process_itself_is_egress_guarded():
    announce_guard_probe("egress_blocked", "test_pytest_process_itself_is_egress_guarded")
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
    from drbean_eval import science_flow
    builder = science_flow.Flow(client, None, str(stack.workdir) + "/zero-dispatch-scratch", science_python=None,
                                package_dir=str(REPO / "packages" / "groundwork_adapter"))
    plan_body = {**builder.plan_body(problem, dataset, "agent baseline"),
                 "provider_disclosure": {"provider": "gemini", "model": model, "context_fields": ["problem", "dataset"],
                                         "permission_id": permission["id"]}}
    created = client.raw("POST", f"/workspaces/{workspace}/plans", key=client.new_key("agent-plan"),
                         content_type="application/json",
                         body=_json({"expected_current_revision_id": problem["id"], "plan": plan_body}))
    if created.status != 201:  # refusing an AI-disclosed plan while dispatch is disabled is also a safe outcome
        seen["agent_run"] = {"state": "plan_refused", "error_code": created.json().get("code")}
    else:
        plan = created.json()
        approval = client.post(f"/plans/{plan['id']}/approvals", {"expected_plan_digest": plan["digest"],
                               "expected_current_revision_id": problem["id"], "accepted": True})
        run = client.post(f"/plans/{plan['id']}/runs", {"approval_id": approval["id"],
                          "expected_plan_digest": plan["digest"]})
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
    assert seen["agent_run"]["state"] in {"failed", "plan_refused"}  # an AI plan cannot silently run
    assert all(a["state"] != "completed" for a in seen["provider_attempts"])


@pytest.mark.real_stack
def test_dummy_key_alone_cannot_activate_dispatch(stack_factory):
    stack = stack_factory(stack_env={"GEMINI_API_KEY": DUMMY_KEY, "GEMINI_MODEL": DUMMY_MODEL},
                          allow_dummy_provider_config=True)
    exercise_model_paths(stack)
    assert_no_external_attempt(stack)


@pytest.mark.real_stack
def test_present_dummy_credentials_are_never_read_in_placeholder_mode(stack_factory):
    """Placeholder mode has no reason to load a credential: the guard records reads of present credential names."""
    stack = stack_factory(stack_env=LEGACY_LIVE_SWITCH, allow_dummy_provider_config=True)
    exercise_model_paths(stack)
    reads = stack.credential_reads()
    assert not reads, ("live credential loading in placeholder mode (finding F-CREDENTIAL-READ): "
                       + "; ".join(f"{r['name']} via {r['stack'][-3:]}" for r in reads[:3]))


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
    capabilities = reviewer(module_stack).raw("GET", "/capabilities", authenticated=False).json()
    gemini = capabilities["gemini"]
    mode = capabilities.get("ai_mode") or gemini.get("mode") or gemini.get("provider_mode")
    assert isinstance(mode, str) and ("placeholder" in mode or "disabled" in mode), (
        f"capabilities declare no explicit placeholder/disabled AI mode (got {mode!r}); finding F-PLACEHOLDER-MODE: "
        "the default must be an explicit disabled/placeholder mode, not merely 'not configured'")
    assert gemini.get("dispatch_enabled") is not True
    assert gemini.get("verified_in_environment") is False


def test_guard_spies_refuse_client_construction_but_allow_sdk_types():
    from google.genai import types  # local SDK types and schemas stay allowed
    assert types.GenerateContentConfig.__name__
    from google import genai
    announce_guard_probe("provider_client_blocked", "test_guard_spies_refuse_client_construction_but_allow_sdk_types")
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


DUMMY_OPT_IN = {"mode": "live", "GEMINI_API_KEY": "DRBEAN-DUMMY-KEY-0042", "GEMINI_MODEL": DUMMY_MODEL,
                "BEAN_GEMINI_ACCOUNT_GATE": "approved", "BEAN_GEMINI_ACCOUNT_DECISION_ID": "DRBEAN-DUMMY-DECISION-0042"}


def _process_environment(pid: int) -> str:
    """macOS/BSD ps shows a same-user process's environment after its command (used only for dummy values)."""
    import subprocess
    return subprocess.run(["ps", "eww", "-p", str(pid), "-o", "command="], capture_output=True, text=True).stdout


def test_owner4_doctor_reports_a_dummy_opt_in_without_printing_its_key(tmp_path):
    """Owner 4's doctor reads the opt-in file as data and never prints the key (isolated var directory, dummy key)."""
    import json as _json
    import subprocess
    import sys as _sys
    launcher_path = REPO / "scripts" / "dev" / "launcher.py"
    if "gemini.local.json" not in launcher_path.read_text(encoding="utf-8"):
        pytest.xfail("NOT_AVAILABLE: Owner 4's launcher has no live opt-in file on this candidate")
    var = tmp_path / "var"
    var.mkdir(mode=0o700)
    (var / "gemini.local.json").write_text(_json.dumps(DUMMY_OPT_IN), encoding="utf-8")
    (var / "gemini.local.json").chmod(0o600)
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "LANG": "C.UTF-8", "DRBEAN_VAR_DIR": str(var)}
    outputs = []
    for args in (["doctor"], ["doctor", "--json"]):
        done = subprocess.run([_sys.executable, str(launcher_path), *args], cwd=REPO, capture_output=True, text=True,
                              timeout=120, env=env)
        outputs.append(done.stdout + done.stderr)
    joined = "\n".join(outputs)
    assert DUMMY_OPT_IN["GEMINI_API_KEY"] not in joined, "doctor printed the opt-in key"
    assert "key present" in joined, "doctor did not report the opt-in state"


@pytest.mark.real_stack
def test_owner4_live_opt_in_with_a_dummy_key_dispatches_nothing_and_stays_scoped():
    """Owner 4's launcher opt-in ('mode': 'live' plus a key in an ignored file) with DUMMY values only.

    Nothing may be dispatched from any process. The value must never appear in launcher or doctor output. It may
    reach the API and worker, as the launcher documents, but never the web server. Ordinary routes keep working."""
    launcher_source = (REPO / "scripts" / "dev" / "launcher.py").read_text(encoding="utf-8")
    if "gemini.local.json" not in launcher_source:
        pytest.xfail("NOT_AVAILABLE: Owner 4's launcher has no live opt-in file on this candidate")
    from drbean_eval import launcher as harness_launcher
    try:
        stack = harness_launcher.Owner4LauncherStack(str(REPO), live_opt_in=dict(DUMMY_OPT_IN)).start()
    except harness_launcher.StackError as error:
        text = str(error).lower()
        if "port" in text or "in use" in text or "setup.sh first" in text:
            pytest.xfail(f"NOT_RUN: Owner 4's launcher cannot start here (fixed ports busy or setup not run): "
                         f"{str(error)[-160:]}")
        raise
    try:
        seen = exercise_model_paths(stack)
        outputs = "\n".join(run.get("output_tail", "") for run in stack.launcher_runs)
        assert DUMMY_OPT_IN["GEMINI_API_KEY"] not in outputs, "the opt-in key value was printed by the launcher"
        assert "opt-in" in outputs.lower() or "Gemini" in outputs
        assert seen["capabilities"]["gemini"].get("dispatch_enabled") is not True
        environments = {name: _process_environment(process.pid) for name, process in stack.processes.items()}
        assert "web" in environments and DUMMY_OPT_IN["GEMINI_API_KEY"] not in environments["web"], \
            "the web server received the opt-in key"
        attempts = stack.external_attempts()
        assert attempts == [], f"external model attempts with a dummy live opt-in: {attempts[:3]}"
    finally:
        stack.stop()
        stack.cleanup()
