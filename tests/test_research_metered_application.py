"""Ordinary research runner + actual metered model, with no hosted requests.

Only provider-readiness and the SDK constructor are controlled fixtures. The
application graph, routes, canonical consent, operator-only session allocation,
leases, logical admission, checkpoints and physical ledger are real. This does
not qualify credentials, free-tier availability or Gemini understanding.
"""
from dataclasses import replace
import json
import os
from pathlib import Path
import shutil
import socket
from types import SimpleNamespace

from fastapi.testclient import TestClient
from google.genai import types
from langchain_core.messages import ToolMessage
import pytest

from bean_api.config import Settings
from bean_api.main import PREFIX, create_app
from bean_api.providers import LIVE_MODEL, ProviderConfig, ProviderFailure
from bean_api.research import ResearchService
from bean_api.research_coordinator import TOOLS
from bean_api.worker import Worker


class OfflineReadyConfig(ProviderConfig):
    """Readiness fixture; the deliberately invalid dummy can never authenticate."""

    def check_ready(self):
        assert self.api_key == "DRBEAN-DUMMY-OFFLINE-RESEARCH"
        assert self.mode == "live" and self.model == LIVE_MODEL
        assert self.account_gate_passed and self.free_tier_user_asserted


class OfflineSDK:
    """Two decisions, the second conditioned on the actual planning tool result."""

    def __init__(self):
        self.requests, self.constructions, self.closed = [], [], 0
        self.before_request = lambda: None
        self.research_policy = False
        self.policy_calls = []

    def factory(self, **kwargs):
        assert kwargs["api_key"] == "DRBEAN-DUMMY-OFFLINE-RESEARCH"
        self.constructions.append(kwargs)
        return SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=self.generate),
                                                   aclose=self.close))

    async def generate(self, **kwargs):
        self.before_request()
        self.requests.append(kwargs)
        declared = {item.name for tool in kwargs["config"].tools for item in tool.function_declarations}
        assert declared == TOOLS
        if self.research_policy:
            from research_efficient_wire import efficient_calls, efficient_response
            calls = efficient_calls(kwargs["contents"], len(self.requests))
            self.policy_calls.extend(calls)
            return efficient_response(calls, LIVE_MODEL)
        results = [part.function_response for content in kwargs["contents"] for part in content.parts
                   if part.function_response is not None]
        if not results:
            name = "write_todos"
            args = {"todos": [{"content": "Resolve the missing reviewed model and measurements.",
                               "status": "in_progress"}]}
        else:
            assert results[-1].name == "write_todos" and results[-1].response
            name = "request_clarification"
            args = {"fields": ["reviewed_problem"],
                    "question": "Please review the model, measurements and hard allowances before investigation."}
        return self.response(name, args, f"offline-call-{len(self.requests)}")

    @staticmethod
    def response(name, args, call_id):
        return types.GenerateContentResponse(candidates=[types.Candidate(
            content=types.Content(role="model", parts=[types.Part(function_call=types.FunctionCall(
                name=name, args=args, id=call_id))]), finish_reason="STOP")],
            usage_metadata=types.GenerateContentResponseUsageMetadata(
                prompt_token_count=20, candidates_token_count=6, total_token_count=26), model_version=LIVE_MODEL)

    async def close(self):
        self.closed += 1


@pytest.fixture
def metered_app(tmp_path, monkeypatch, request):
    def denied(*args, **kwargs):
        raise AssertionError("Hosted network and real SDK construction are forbidden")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    wire = OfflineSDK()
    monkeypatch.setattr("google.genai.Client", wire.factory)
    config = OfflineReadyConfig(mode="live", model=LIVE_MODEL, api_key="DRBEAN-DUMMY-OFFLINE-RESEARCH",
        account_gate_passed=True, account_decision_id="explicit-offline-readiness-fixture",
        free_tier_user_asserted=True, max_input_tokens=24_000, max_output_tokens=512)
    native = getattr(request, "param", None) == "native"
    python = os.getenv("BEAN_COUNTERDEX_PYTHON") or shutil.which("python3.11")
    if native and python is None:
        pytest.skip("Qualified CPython 3.11 is required for actual Counterdex execution")
    settings = Settings(database_path=str(tmp_path / "offline-metered.sqlite3"),
        blob_dir=str(tmp_path / "blobs"), artifact_dir=str(tmp_path / "artifacts"),
        auth_tokens={"alice": "DRBEAN-DUMMY-AUTH-" + "a" * 40},
        science_adapter="counterdex" if native else "unavailable", counterdex_python=python or "python3.11", research_mode="live")
    # Explicit provider avoids all environment/credential lookup during startup.
    app = create_app(settings, provider=SimpleNamespace(config=config))
    with TestClient(app) as client:
        client.headers["Authorization"] = "Bearer " + settings.auth_tokens["alice"]
        service = ResearchService(app.state.workflow, live_enabled=True, allocation_actor="alice")
        worker = Worker(app.state.workflow, settings=settings, provider_config=config, ledger=app.state.ledger)
        yield client, service, worker, wire


def post(client, path, body, key):
    return client.post(PREFIX + path, json=body, headers={"Idempotency-Key": key})


def create_session(client, key="session"):
    workspace = post(client, "/workspaces", {"name": "Offline SDK through the ordinary runner"}, "workspace").json()["id"]
    response = post(client, f"/workspaces/{workspace}/research-sessions",
        {"objective": "Which reviewed assumptions are missing before a scientific investigation?", "mode": "live"}, key)
    assert response.status_code == 200, response.text
    return response.json()


def consent(client, session):
    response = post(client, f"/research-sessions/{session['id']}/provider-consents", {
        "model": LIVE_MODEL, "expected_context_digest": session["provider_disclosure"]["context_digest"],
        "accepted": True}, "consent")
    assert response.status_code == 200, response.text
    return response.json()


def advance(client, session):
    return post(client, f"/research-sessions/{session['id']}/advance",
        {"expected_revision": session["revision"]}, "advance")


def test_ordinary_live_routes_require_separate_consent_and_nonzero_session_admission(metered_app):
    client, service, worker, wire = metered_app
    session = create_session(client)
    assert session["provider_allocation"]["physical_requests"] == 0
    refused = advance(client, session)
    assert refused.status_code == 403 and refused.json()["code"] == "research_provider_consent_required"
    consent(client, session)
    refused = advance(client, session)
    assert refused.status_code == 409 and refused.json()["code"] == "research_provider_allocation_exhausted"
    assert worker.research.tick() == 0
    assert wire.requests == wire.constructions == []
    with service.store.read() as conn:
        assert conn.execute("SELECT count(*) FROM research_actions").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM provider_attempts").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0


@pytest.mark.parametrize("physical_requests,expected_state,request_count", [(2, "waiting_review", 2), (1, "failed", 1)])
def test_ordinary_runner_uses_same_graph_and_one_atomic_physical_boundary(
        metered_app, physical_requests, expected_state, request_count):
    client, service, worker, wire = metered_app
    session = create_session(client)
    approved = consent(client, session)
    # Temporary offline store only; production ceilings and grants are untouched.
    service.allocate_provider("alice", session["id"], {"physical_requests": physical_requests,
        "input_tokens": 48_000, "output_tokens": 1024, "accepted": True}, "offline-operator-allocation")
    queued = advance(client, session)
    assert queued.status_code == 200, queued.text

    def reserved_before_sdk():
        attempts = client.app.state.ledger.list_attempts("alice", session["workspace_id"])
        assert len(attempts) == len(wire.requests) + 1
        assert attempts[-1]["state"] == "reserved"
        assert attempts[-1]["metadata"]["context"]["consent_id"] == approved["id"]
    wire.before_request = reserved_before_sdk
    assert worker.research.model_factory is None
    assert worker.research.tick() == 1
    current = service.get("alice", session["id"])
    assert current["state"] == expected_state, current
    assert len(wire.requests) == len(wire.constructions) == wire.closed == request_count
    attempts = client.app.state.ledger.list_attempts("alice", session["workspace_id"])
    assert len(attempts) == request_count
    assert current["usage"]["physical_calls"] == request_count
    assert current["usage"]["logical_turns"] == 2
    assert all(item["metadata"]["operation"] == "agent" for item in attempts)
    assert all(item["http_options"].retry_options.attempts == 1 for item in wire.constructions)
    assert all(request["config"].automatic_function_calling.disable for request in wire.requests)
    assert current["plan"] is not None
    if physical_requests == 2:
        assert current["pending_review"]["kind"] == "research_clarification"
        assert current["pending_review"]["body"]["fields"] == ["reviewed_problem"]
    else:
        assert current["action"]["error_code"] == "provider_budget_exhausted"
        assert current["pending_review"] is None
    with service.store.read() as conn:
        assert conn.execute("SELECT count(*) FROM research_attempt_bindings").fetchone()[0] == request_count
        assert conn.execute("SELECT count(*) FROM research_checkpoint_blobs").fetchone()[0] > 0
        assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0
    # A fresh worker cannot replay a finished/failed action or replenish capacity.
    replacement = Worker(service.workflow, settings=client.app.state.settings,
        provider_config=worker.config, ledger=client.app.state.ledger)
    assert replacement.research.tick() == 0
    assert len(wire.requests) == len(client.app.state.ledger.list_attempts("alice", session["workspace_id"])) == request_count


def test_real_configuration_keeps_free_tier_and_account_gate_checks():
    config = ProviderConfig(mode="live", model=LIVE_MODEL, api_key="DRBEAN-DUMMY-NEVER-AUTHENTICATES",
        account_gate_passed=True, account_decision_id="explicit-offline-test", free_tier_user_asserted=True)
    with pytest.raises(ProviderFailure, match="provider_free_tier_assertion_required"):
        replace(config, free_tier_user_asserted=False).check_ready()
    with pytest.raises(ProviderFailure, match="provider_account_gate_unmet"):
        replace(config, account_gate_passed=False).check_ready()
    with pytest.raises(ProviderFailure, match="provider_key_format_invalid"):
        config.check_ready()


@pytest.mark.parametrize("metered_app", ["native"], indirect=True)
def test_actual_baseline_approval_evidence_and_report_through_metered_model(metered_app, tmp_path):
    """Three admitted offline SDK turns through ordinary production application wiring."""
    from test_research_controlled_application import replay_current_source, saved_messages
    client, service, worker, wire = metered_app
    wire.research_policy = True
    root = Path(__file__).resolve().parents[1]
    fixture = json.loads((root / "packages/groundwork_adapter/fixtures/decision/hero-baseline.request.json").read_text())

    def accepted(path, body, key):
        response = post(client, path, body, key)
        assert response.status_code in {200, 201, 202}, response.text
        return response.json()

    workspace = accepted("/workspaces", {"name": "Offline metered actual science"}, "workspace")["id"]
    dataset = accepted(f"/workspaces/{workspace}/datasets", {
        "experiment_id": "explicit-offline-metered-test", "time_origin": fixture["dataset"]["body"]["time_origin"],
        "origin": "hypothetical", "change_reason": "Synthetic reviewed measurements, no fixed candidate outputs",
        "rows": fixture["dataset"]["body"]["rows"]}, "dataset")
    problem = accepted(f"/workspaces/{workspace}/problems", {
        "dataset_id": dataset["id"], "dataset_digest": dataset["digest"],
        "domain": fixture["problem"]["body"]["domain"], "target": fixture["problem"]["body"]["target"]}, "problem")
    session = accepted(f"/workspaces/{workspace}/research-sessions", {
        "objective": "Do the reviewed measurements challenge this range, and what should I do next?", "mode": "live",
        "problem_id": problem["id"], "expected_problem_digest": problem["digest"]}, "session")
    consent_record = consent(client, session)
    service.allocate_provider("alice", session["id"], {"physical_requests": 6,
        "input_tokens": 64_000, "output_tokens": 3072, "accepted": True}, "offline-operator-allocation")

    def reserved_before_sdk():
        attempts = client.app.state.ledger.list_attempts("alice", workspace)
        assert len(attempts) == len(wire.requests) + 1
        assert attempts[-1]["state"] == "reserved"
        assert attempts[-1]["metadata"]["context"]["consent_id"] == consent_record["id"]
    wire.before_request = reserved_before_sdk
    assert advance(client, session).status_code == 200
    assert worker.research.model_factory is None
    assert worker.tick() == 1
    waiting = service.get("alice", session["id"])
    assert waiting["state"] == "waiting_review", waiting
    assert waiting["pending_review"]["kind"] == "plan" and not waiting["children"]
    assert len(wire.requests) == 1
    decision = {"expected_revision": waiting["revision"], "pending_review_id": waiting["pending_review"]["id"],
        "expected_review_digest": waiting["pending_review_digest"], "decision": "approve", "accepted": True}
    path = f"/research-sessions/{session['id']}/decisions"
    accepted(path, decision, "approve-baseline")
    accepted(path, decision, "approve-baseline")
    for _ in range(4):
        # The same ordinary runtime reconstructs both the model and disk-backed
        # graph; no in-memory fixture progress is required across worker objects.
        worker = Worker(service.workflow, settings=client.app.state.settings,
            provider_config=worker.config, ledger=client.app.state.ledger)
        worker.tick()
        final = service.get("alice", session["id"])
        if final["state"] != "waiting_child":
            break
    assert final["state"] == "completed", final
    assert len(final["children"]) == len(final["reports"]) == 1
    child = final["children"][0]
    assert child["state"] == "completed" and child["scientific_reservations"] == 1
    evidence_id = child["scenarios"][0]["result_id"]
    evidence = client.get(PREFIX + "/records/" + evidence_id).json()
    result = evidence["body"]["result"]
    assert result["scientific_outcome"] == "certified_counterexample"
    assert result["baseline_search"]["attempted_count"] > 0
    assert result["problem_digest"] == problem["digest"]
    assert any(part.function_response and any(fact["id"] == evidence_id for fact in
                   part.function_response.response.get("output", {}).get("canonical_evidence", []))
               for request in wire.requests for content in request["contents"] for part in content.parts
               if part.function_response and isinstance(part.function_response.response.get("output"), dict))
    report_call = wire.policy_calls[-1]
    assert report_call["name"] == "publish_research_report"
    assert report_call["args"]["evidence_ids"] == [evidence_id]
    assert report_call["args"]["next_action"] == "review_design"
    messages = saved_messages(client, session["id"])
    acknowledged = next(json.loads(message.content) for message in messages if isinstance(message, ToolMessage)
                        and message.tool_call_id == report_call["id"])
    assert acknowledged["id"] in final["reports"]
    assert acknowledged["agent_commentary"]["next_action"] == "review_design"
    assert acknowledged["agent_commentary"]["scientific_authority"] is False
    report = client.get(PREFIX + "/reports/" + final["reports"][0]).json()
    assert report["body"]["evidence"] == [evidence]
    assert report["body"]["root_inputs"]["dataset"] == dataset
    attempts = client.app.state.ledger.list_attempts("alice", workspace)
    assert len(wire.requests) == len(wire.constructions) == wire.closed == len(attempts) == 3
    assert final["usage"]["physical_calls"] == final["usage"]["logical_turns"] == 3
    assert all(item["state"] == "completed" for item in attempts)
    assert final["provider_allocation"]["physical_requests"] == 6
    fresh = replay_current_source(client, result, tmp_path)
    assert fresh["verification"] == "valid" and fresh["replay"] == "passed"
    assert worker.tick() == 0
    assert len(wire.requests) == 3


@pytest.mark.parametrize("metered_app", ["native"], indirect=True)
@pytest.mark.parametrize("input_allocation", [64_000, 61_000])
def test_reviewed_design_constraints_baseline_fits_the_documented_operator_allocation(metered_app, input_allocation):
    """Real baseline + separately reviewed design, without increasing allocation.

    The SDK is substituted. This exercises one admissible evidence-dependent
    model strategy, not live Gemini understanding or its eventual request size.
    A smaller allocation must preserve completed science and stop before SDK use.
    """
    client, service, worker, wire = metered_app
    wire.research_policy = True
    root = Path(__file__).resolve().parents[1]
    fixture = json.loads((root / "packages/groundwork_adapter/fixtures/decision/hero-baseline.request.json").read_text())
    conditions = json.loads((root / "docs/agent/controlled-conditions.v1.json").read_text())["inputs"]

    def accepted(path, body, key):
        response = post(client, path, body, key)
        assert response.status_code in {200, 201, 202}, response.text
        return response.json()

    workspace = accepted("/workspaces", {"name": "Live sample admission estimate"}, "workspace")["id"]
    dataset = accepted(f"/workspaces/{workspace}/datasets", {
        "experiment_id": "explicit-offline-metered-test", "time_origin": fixture["dataset"]["body"]["time_origin"],
        "origin": "hypothetical", "change_reason": "Synthetic reviewed measurements, no fixed candidate outputs",
        "rows": fixture["dataset"]["body"]["rows"]}, "dataset")
    problem = accepted(f"/workspaces/{workspace}/problems", {
        "dataset_id": dataset["id"], "dataset_digest": dataset["digest"],
        "domain": fixture["problem"]["body"]["domain"], "target": fixture["problem"]["body"]["target"]}, "problem")
    session = accepted(f"/workspaces/{workspace}/research-sessions", {
        "objective": conditions["objective"], "mode": "live", "problem_id": problem["id"],
        "expected_problem_digest": problem["digest"], "design_constraints": conditions["design_constraints"]}, "session")
    consent(client, session)
    service.allocate_provider("alice", session["id"], {"physical_requests": 6,
        "input_tokens": input_allocation, "output_tokens": 3072, "accepted": True}, "offline-operator-allocation")

    def reserved_before_sdk():
        attempts = client.app.state.ledger.list_attempts("alice", workspace)
        assert len(attempts) == len(wire.requests) + 1 and attempts[-1]["state"] == "reserved"
    wire.before_request = reserved_before_sdk
    assert advance(client, session).status_code == 200
    worker.tick()
    waiting = service.get("alice", session["id"])
    assert waiting["state"] == "waiting_review" and not waiting["children"]
    accepted(f"/research-sessions/{session['id']}/decisions", {
        "expected_revision": waiting["revision"], "pending_review_id": waiting["pending_review"]["id"],
        "expected_review_digest": waiting["pending_review_digest"], "decision": "approve", "accepted": True}, "approve")
    for _ in range(4):
        worker = Worker(service.workflow, settings=client.app.state.settings,
            provider_config=worker.config, ledger=client.app.state.ledger)
        worker.tick()
        final = service.get("alice", session["id"])
        if final["state"] != "waiting_child":
            break
    assert final["state"] == "completed" and len(final["reports"]) == 1, final
    attempts = client.app.state.ledger.list_attempts("alice", workspace)
    reserved = [item["metadata"]["reserved_input_tokens"] for item in attempts]
    assert len(attempts) == len(wire.requests) == 3 and all(item["state"] == "completed" for item in attempts)
    assert [call["name"] for call in wire.policy_calls] == ["write_todos", "prepare_scientific_proposal",
        "run_scientific_operation", "write_todos", "publish_research_report"]
    assert sum(reserved) <= 64_000, reserved
    assert sum(item["metadata"]["reserved_output_tokens"] for item in attempts) <= 3072
    steps = final["plan"]["body"]["steps"]
    evidence_id = final["children"][0]["scenarios"][0]["result_id"]
    assert [step["status"] for step in steps] == ["completed", "completed", "pending"]
    assert all(step["reference_ids"] == [evidence_id] for step in steps[:2])
    # Continue the same session into a separately approved design without any
    # capacity increase or new consent. All physical calls still use the meter.
    accepted(f"/research-sessions/{session['id']}/advance", {"expected_revision": final["revision"]}, "design-advance")
    worker.tick()
    waiting = service.get("alice", session["id"])
    assert waiting["state"] == "waiting_review" and len(waiting["children"]) == 1, waiting
    assert len(wire.requests) == 4
    accepted(f"/research-sessions/{session['id']}/decisions", {
        "expected_revision": waiting["revision"], "pending_review_id": waiting["pending_review"]["id"],
        "expected_review_digest": waiting["pending_review_digest"], "decision": "approve", "accepted": True}, "approve-design")
    for _ in range(4):
        worker = Worker(service.workflow, settings=client.app.state.settings,
            provider_config=worker.config, ledger=client.app.state.ledger)
        worker.tick()
        final = service.get("alice", session["id"])
        if final["state"] != "waiting_child":
            break
    if input_allocation == 61_000:
        assert final["state"] == "failed" and final["action"]["error_code"] == "provider_budget_exhausted"
        assert len(final["children"]) == len(final["reports"]) == 2
        assert all(child["state"] == "completed" for child in final["children"])
        assert final["interaction"]["quota_exhausted"] and final["interaction"]["results"]["available"]
        assert final["interaction"]["results"]["deterministic_summary_available"]
        assert not final["interaction"]["results"]["commentary_available"]
        report = client.get(PREFIX + "/reports/" + final["reports"][-1]).json()
        assert report["body"]["commentary_status"] == "unavailable"
        assert report["body"]["model_failure"] == {"code": "provider_budget_exhausted"}
        attempts = client.app.state.ledger.list_attempts("alice", workspace)
        assert len(wire.requests) == len(attempts) == 5
        worker.tick()
        denied = post(client, f"/research-sessions/{session['id']}/advance", {"expected_revision": final["revision"]}, "exhausted-resume")
        assert denied.status_code == 409
        assert len(wire.requests) == 5
        assert service.get("alice", session["id"])["provider_allocation"]["input_tokens"] == input_allocation
        return
    assert final["state"] == "completed" and len(final["children"]) == 2, final
    assert len(final["reports"]) == 2
    assert wire.policy_calls[-1]["name"] == "publish_research_report"
    assert wire.policy_calls[-1]["args"]["next_action"] == "review_observation"
    attempts = client.app.state.ledger.list_attempts("alice", workspace)
    reservations = [item["metadata"]["reserved_input_tokens"] for item in attempts]
    assert len(wire.requests) == len(attempts) == final["usage"]["physical_calls"] == 6
    assert sum(reservations) <= 64_000, reservations
    assert final["provider_allocation"] == {"physical_requests": 6, "input_tokens": input_allocation, "output_tokens": 3072}
    assert final["provider_usage"]["reported_input_tokens"] == 120
    assert final["provider_usage"]["reserved_input_tokens"] == sum(reservations)
    assert final["provider_usage"]["unresolved_attempts"] == 0
    assert all(item["state"] == "completed" for item in attempts)
    from test_research_controlled_application import saved_messages
    # Compaction affects only requests, not provider signatures or audit history.
    retained = saved_messages(client, session["id"])
    assert sum(bool(getattr(message, "tool_calls", [])) for message in retained) == 6
    assert len(retained) > len(wire.requests[-1]["contents"])
    assert worker.tick() == 0 and len(wire.requests) == 6
