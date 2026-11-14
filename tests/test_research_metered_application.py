"""Ordinary research runner + actual metered model, with no hosted requests.

Only provider-readiness and the SDK constructor are controlled fixtures. The
application graph, routes, canonical consent, operator-only session allocation,
leases, logical admission, checkpoints and physical ledger are real. This does
not qualify credentials, free-tier availability or Gemini understanding.
"""
from dataclasses import replace
import socket
from types import SimpleNamespace

from fastapi.testclient import TestClient
from google.genai import types
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
def metered_app(tmp_path, monkeypatch):
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
    settings = Settings(database_path=str(tmp_path / "offline-metered.sqlite3"),
        blob_dir=str(tmp_path / "blobs"), artifact_dir=str(tmp_path / "artifacts"),
        auth_tokens={"alice": "DRBEAN-DUMMY-AUTH-" + "a" * 40}, science_adapter="unavailable", research_mode="live")
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
