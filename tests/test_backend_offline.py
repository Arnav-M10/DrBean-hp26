"""Independent backend controls for the zero-model-dispatch implementation lane.

All credentials named below are synthetic test strings. No actual environment
secret is inspected, and the in-memory HTTP client needs no socket connection.
"""

import asyncio
from io import BytesIO
import os
import socket

from fastapi.testclient import TestClient
from PIL import Image
import pytest

from bean_api.config import Settings
from bean_api.main import PREFIX, create_app, provider_config_from_env
from bean_api.providers import ProviderConfig, ProviderFailure
from bean_api.science import UnavailableAdapter
from bean_api.store import Store
from bean_api.worker import Worker
from bean_api.workflow import Workflow
from test_workflow import prepared


def test_ordinary_provider_configuration_never_reads_provider_environment(monkeypatch):
    queried = []

    def guarded_getenv(name, default=None):
        queried.append(name)
        if name.startswith("GEMINI_") or name.startswith("BEAN_GEMINI_"):
            raise AssertionError("Provider environment must not be read in placeholder mode")
        return default

    monkeypatch.setattr(os, "getenv", guarded_getenv)
    config = provider_config_from_env()
    assert config.api_key is None
    assert config.model is None
    assert config.account_gate_passed is False
    with pytest.raises(ProviderFailure, match="provider_not_configured"):
        config.check_ready()
    assert queried == ["BEAN_AI_MODE"]


def test_present_key_and_legacy_approval_flags_cannot_enable_configuration(monkeypatch):
    # Interpose a synthetic mapping, without looking up or altering real secrets.
    values = {"GEMINI_API_KEY": "SYNTHETIC_PRESENT_KEY", "GEMINI_MODEL": "synthetic-model",
              "BEAN_GEMINI_ACCOUNT_GATE": "approved", "BEAN_GEMINI_ACCOUNT_DECISION_ID": "old-decision",
              "BEAN_GEMINI_IMAGE_TOKEN_BOUND": "100"}
    queried = []

    def fake_getenv(name, default=None):
        queried.append(name)
        return values.get(name, default)

    monkeypatch.setattr(os, "getenv", fake_getenv)
    config = provider_config_from_env()
    assert config.api_key is None and config.model is None
    assert queried == ["BEAN_AI_MODE"]


def test_http_intake_and_conversation_keep_provider_attempts_zero(tmp_path, monkeypatch):
    sockets = []

    def deny_connect(self, address):
        sockets.append(address)
        raise AssertionError("No network dispatch is permitted in placeholder tests")

    monkeypatch.setattr(socket.socket, "connect", deny_connect)
    settings = Settings(database_path=str(tmp_path / "offline.sqlite3"), blob_dir=str(tmp_path / "sources"),
                        auth_tokens={"alice": "synthetic-token-" + "a" * 32})
    with TestClient(create_app(settings, adapter=UnavailableAdapter())) as client:
        client.headers["Authorization"] = "Bearer " + settings.auth_tokens["alice"]
        capabilities = client.get(PREFIX + "/capabilities").json()
        assert capabilities["ai_mode"] == "disabled_placeholder"
        assert capabilities["gemini"]["configured"] is False
        assert capabilities["gemini"]["verified_in_environment"] is False
        workspace = client.post(PREFIX + "/workspaces", json={"name": "Offline boundary"}).json()["id"]
        stream = BytesIO()
        Image.new("RGB", (24, 30), "white").save(stream, format="PNG")
        source_response = client.post(PREFIX + f"/workspaces/{workspace}/source-assets?origin=synthetic&retention=retain",
                                      content=stream.getvalue(), headers={"Content-Type": "image/png", "Idempotency-Key": "source"})
        assert source_response.status_code == 201, source_response.text
        source = source_response.json()["id"]
        consent = {"provider": "gemini", "model": "PLACEHOLDER", "source_asset_ids": [source],
                   "include_notes": True, "include_existing_values": True, "accepted": True}
        intake = client.post(PREFIX + f"/workspaces/{workspace}/intake-proposals",
                             json={"source_id": source, "consent": consent}, headers={"Idempotency-Key": "intake"})
        assert intake.status_code == 503
        assert intake.json()["code"] in {"provider_not_configured", "provider_dispatch_disabled"}
        response = client.post(PREFIX + f"/workspaces/{workspace}/assistant-turns", json={
            "operation": "explain", "client_operation_id": "turn", "expected_conversation_revision": 0,
            "text": "Explain the currently reviewed evidence.",
            "consent": {**consent, "source_asset_ids": []}}, headers={"Idempotency-Key": "turn"})
        assert response.status_code == 201, response.text
        assert response.json()["body"]["provider_attempt_id"] is None
        assert client.get(PREFIX + f"/workspaces/{workspace}/provider-attempts").json() == []
    assert sockets == []


def test_preexisting_gemini_approval_cannot_dispatch_without_controlled_model(tmp_path, monkeypatch):
    workflow = Workflow(Store(tmp_path / "offline.sqlite3"))
    workspace = workflow.create_workspace("alice", "Old approved Gemini plan")["id"]
    _, problem, original_plan, _ = prepared((workflow, workspace))
    consent = workflow.create_provider_consent("alice", workspace, {
        "provider": "gemini", "model": "synthetic-model", "source_asset_ids": [],
        "context_fields": ["problem", "dataset"], "problem_id": problem["id"], "accepted": True}, "consent")
    body = {**original_plan["body"], "provider_disclosure": {"provider": "gemini", "model": "synthetic-model",
            "source_asset_ids": [], "context_fields": ["problem", "dataset"], "permission_id": consent["id"]}}
    plan = workflow.create_plan("alice", workspace, body, "agent-plan")
    approval = workflow.approve_plan("alice", plan["id"], problem["id"], plan["digest"], "approve")
    run = workflow.start_run("alice", plan["id"], approval["id"], "start")

    async def forbidden_dispatch(*args, **kwargs):
        raise AssertionError("A legacy approved plan must not call a live coordinator")

    monkeypatch.setattr("bean_api.worker.run_coordinator", forbidden_dispatch)
    ready_config = ProviderConfig(api_key="SYNTHETIC_NOT_A_KEY", model="synthetic-model", account_gate_passed=True,
                                  account_decision_id="synthetic-old-decision")
    result = asyncio.run(Worker(workflow, adapter=UnavailableAdapter(), provider_config=ready_config).execute(run))
    assert result["state"] == "failed"
    assert result["error_code"] == "provider_dispatch_disabled"
    assert result["provider_turns"] == 0
    assert result["scientific_reservations"] == 0
    assert result["scenarios"] == []
    with workflow.store.read() as conn:
        assert conn.execute("SELECT COUNT(*) FROM provider_attempts").fetchone()[0] == 0
    assert workflow.start_run("alice", plan["id"], approval["id"], "retry")["id"] == run["id"]
