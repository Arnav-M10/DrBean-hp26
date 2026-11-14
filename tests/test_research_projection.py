"""Offline canonical UI projections; no model, credential or scientific inference."""
import asyncio
import json
import socket
from types import SimpleNamespace

import pytest

from bean_api.providers import ProviderFailure
from bean_api.research import ResearchService
from bean_api.research_contracts import ResearchSnapshot
from bean_api.research_runtime import research_capabilities
from bean_api.research_tools import ApplicationResearchPorts
from bean_api.store import Store
from bean_api.workflow import DomainError, Workflow
import test_research_ledger as ledger_tests

active, lane = ledger_tests.active, ledger_tests.lane


@pytest.fixture(autouse=True)
def no_network_or_provider(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("Projection tests cannot dispatch a provider or network request")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr("google.genai.Client", deny)


def test_global_capability_retains_requested_live_mode_when_unready():
    class Unready:
        mode = "live"
        def check_ready(self):
            raise ProviderFailure("provider_account_gate_unmet")
    caps = research_capabilities(SimpleNamespace(research_mode="live"), Unready())
    assert caps["configured_mode"] == "live"
    assert caps["execution_mode"] == "disabled" and caps["dispatch_enabled"] is False
    assert caps["readiness"] == {"state": "unavailable", "reason": "provider_account_gate_unmet"}
    assert caps["live_qualification"] == "not_run" and caps["verified_in_environment"] is False


@pytest.mark.parametrize("mode", ["controlled", "disabled", "live"])
def test_ready_configuration_never_claims_live_qualification(mode):
    class OfflineReadiness:
        mode = "live"
        def check_ready(self):
            pass  # Configuration-only fixture; no actual credential or SDK.
    caps = research_capabilities(SimpleNamespace(research_mode=mode), OfflineReadiness())
    assert caps["configured_mode"] == mode
    assert caps["readiness"]["state"] == ("disabled" if mode == "disabled" else "configured")
    assert caps["execution_mode"] == mode
    assert caps["live_qualification"] == "not_run"
    assert caps["checkpoint_continuation"]["uncertain_provider_requests"] == "not_replayed"
    assert "restart_continuation" not in caps["deferred_operations"]


def test_live_session_discloses_consent_and_zero_allocation_without_granting_work(tmp_path):
    workflow = Workflow(Store(tmp_path / "projection.sqlite3"))
    workspace = workflow.create_workspace("alice", "UI state")["id"]
    service = ResearchService(workflow, live_enabled=True)
    session = service.create("alice", workspace, {"objective": "Review what is required", "mode": "live"}, "create")
    ResearchSnapshot.model_validate(session)
    assert session["interaction"]["provider_consent_required"] is True
    assert session["interaction"]["quota_exhausted"] is True
    assert session["interaction"]["suggested_action"] == "review_provider_consent"
    assert session["interaction"]["results"]["available"] is False
    assert session["provider_usage"]["reported_input_tokens"] is None
    assert session["provider_usage"]["remaining"] == {"physical_requests": 0, "input_tokens": 0, "output_tokens": 0}
    with service.store.read() as conn:
        before = tuple(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                       for table in ("provider_attempts", "operations", "jobs", "research_actions"))
    assert service.get("alice", session["id"]) == session
    assert service.list("alice", workspace) == [session]
    with pytest.raises(DomainError) as denied:
        service.get("bob", session["id"])
    assert denied.value.code == "not_found"
    with service.store.read() as conn:
        after = tuple(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
                      for table in ("provider_attempts", "operations", "jobs", "research_actions"))
    assert before == after


def test_projection_separates_reservations_conservative_accounting_and_reported_usage(lane):
    service, context, identity, _, ledger = active(lane)
    asyncio.run(ApplicationResearchPorts(service, context).admit_model())
    attempt = ledger.begin_attempt(identity.checked_dict(), {"reserved_input_tokens": 1000, "reserved_output_tokens": 100})
    # Deliberate offline bookkeeping fixture: actual provider dispatch is forbidden.
    ledger.finish_attempt(attempt, {"status": "validated", "usage": {
        "input_tokens": 2000, "output_tokens": 28, "thought_tokens": 2, "total_tokens": 2030}})
    snapshot = service.get("alice", context.research_session_id)
    usage = snapshot["provider_usage"]
    assert usage["physical_requests"] == 1
    assert (usage["reserved_input_tokens"], usage["reserved_output_tokens"]) == (1000, 100)
    assert (usage["accounted_input_tokens"], usage["accounted_output_tokens"]) == (2000, 100)
    assert (usage["reported_input_tokens"], usage["reported_output_tokens"], usage["reported_thought_tokens"]) == (2000, 28, 2)
    assert usage["reported_total_tokens"] == 2030 and usage["reported_attempts"] == 1
    assert usage["remaining"] == {"physical_requests": 1, "input_tokens": 14000, "output_tokens": 924}
    assert usage["accounting_valid"] is True and usage["unresolved_attempts"] == 0
    ResearchSnapshot.model_validate(snapshot)


@pytest.mark.parametrize("field,state,hint", [("reviewed_problem", "waiting_review", "review"),
                                            ("new_observation", "waiting_observation", "review_observation")])
def test_canonical_clarification_projects_the_actual_waiting_state(lane, field, state, hint):
    service, context, _, _, _ = active(lane)
    ports = ApplicationResearchPorts(service, context)
    asyncio.run(ports.request_clarification([field], "A separately reviewed input is required."))
    service.release(context, state)
    snapshot = service.get("alice", context.research_session_id)
    assert snapshot["pending_review"]["body"]["fields"] == [field]
    assert snapshot["interaction"]["waiting_for_review"] is (state == "waiting_review")
    assert snapshot["interaction"]["waiting_for_observation"] is (state == "waiting_observation")
    assert snapshot["interaction"]["suggested_action"] == hint
    assert snapshot["children"] == [] and snapshot["provider_usage"]["physical_requests"] == 0


def test_partial_reported_usage_remains_unknown_instead_of_fabricating_components(lane):
    service, context, identity, _, ledger = active(lane)
    asyncio.run(ApplicationResearchPorts(service, context).admit_model())
    attempt = ledger.begin_attempt(identity.checked_dict(), {"reserved_input_tokens": 1000, "reserved_output_tokens": 100})
    ledger.finish_attempt(attempt, {"status": "validated", "usage": {"total_tokens": 1500}})
    usage = service.get("alice", context.research_session_id)["provider_usage"]
    assert usage["reported_input_tokens"] is None and usage["reported_output_tokens"] is None
    assert usage["reported_total_tokens"] == 1500
    assert usage["accounted_input_tokens"] == usage["accounted_output_tokens"] == 1500
    assert usage["remaining"]["output_tokens"] == 0


def test_controlled_zero_allocation_does_not_claim_exhausted_live_quota(lane):
    service, session, _ = lane
    current = service.get("alice", session["id"])
    assert current["mode"] == "controlled"
    assert current["provider_usage"]["physical_requests"] == 0
    assert current["interaction"]["quota_exhausted"] is False
    assert current["interaction"]["provider_consent_required"] is False
    assert current["interaction"]["suggested_action"] == "advance"


def test_unknown_attempt_keeps_its_reservation_and_exposes_inspect_or_cancel(lane):
    service, context, identity, _, ledger = active(lane)
    asyncio.run(ApplicationResearchPorts(service, context).admit_model())
    ledger.begin_attempt(identity.checked_dict(), {"reserved_input_tokens": 1000, "reserved_output_tokens": 100})
    service.recover(force=True)
    snapshot = service.get("alice", context.research_session_id)
    usage = snapshot["provider_usage"]
    assert usage["unresolved_attempts"] == 1 and usage["reported_attempts"] == 0
    assert usage["reported_input_tokens"] is None and usage["reported_output_tokens"] is None
    assert usage["accounted_input_tokens"] == usage["reserved_input_tokens"] == 1000
    assert snapshot["interaction"]["recovery"] == {
        "required": True, "code": "provider_outcome_unknown", "can_reconcile": False, "next_action": "inspect_accounting_or_cancel"}
    assert service.get("alice", snapshot["id"])["provider_usage"] == usage
    with pytest.raises(DomainError) as unknown:
        service.reconcile("alice", snapshot["id"], {"expected_revision": snapshot["revision"], "acknowledged_unknown_outcome": True}, "reconcile")
    assert unknown.value.code == "provider_outcome_unknown"
    assert service.get("alice", snapshot["id"])["provider_usage"] == usage


def test_failed_sdk_action_still_exposes_unknown_provider_accounting(lane):
    service, context, identity, _, ledger = active(lane)
    asyncio.run(ApplicationResearchPorts(service, context).admit_model())
    attempt = ledger.begin_attempt(identity.checked_dict(), {"reserved_input_tokens": 1000, "reserved_output_tokens": 100})
    ledger.finish_attempt(attempt, {"status": "unknown_outcome", "usage": None})
    service.release(context, "failed", error_code="provider_timeout_unknown_outcome")
    snapshot = service.get("alice", context.research_session_id)
    assert snapshot["state"] == "failed"
    assert snapshot["interaction"]["recovery"] == {
        "required": True, "code": "provider_outcome_unknown", "can_reconcile": False, "next_action": "inspect_accounting_or_cancel"}
    assert snapshot["interaction"]["suggested_action"] == "inspect_accounting_or_cancel"
    assert snapshot["provider_usage"]["accounted_input_tokens"] == 1000


@pytest.mark.parametrize("code", ["agent_model_budget_exhausted", "agent_tool_budget_exhausted", "agent_child_budget_exhausted"])
def test_action_limit_is_visible_even_with_remaining_session_capacity(lane, code):
    service, context, _, _, _ = active(lane)
    service.release(context, "failed", error_code=code)
    snapshot = service.get("alice", context.research_session_id)
    assert snapshot["usage"]["logical_turns"] < snapshot["session_limits"]["logical_turns"]
    assert snapshot["provider_usage"]["remaining"]["physical_requests"] > 0
    assert snapshot["interaction"]["quota_exhausted"] is True


@pytest.mark.parametrize("code", ["worker_lost", "research_model_outcome_unrecoverable", "research_checkpoint_reconciliation_required"])
def test_recovery_hint_distinguishes_reconcilable_worker_loss_from_unrecoverable_model(lane, code):
    service, context, _, _, _ = active(lane)
    service.release(context, "needs_reconciliation", error_code=code)
    recovery = service.get("alice", context.research_session_id)["interaction"]["recovery"]
    assert recovery["required"] and recovery["code"] == code
    assert recovery["can_reconcile"] is (code == "worker_lost")
    assert recovery["next_action"] == ("reconcile" if code == "worker_lost" else "inspect_accounting_or_cancel")


def test_malformed_accounting_never_looks_like_available_capacity(lane):
    service, context, identity, _, ledger = active(lane)
    asyncio.run(ApplicationResearchPorts(service, context).admit_model())
    attempt = ledger.begin_attempt(identity.checked_dict(), {"reserved_input_tokens": 1000, "reserved_output_tokens": 100})
    # Corrupted historical metadata is diagnostic input, not a new provider request.
    with service.store.transaction() as conn:
        conn.execute("UPDATE provider_attempts SET response_metadata=? WHERE id=?", (json.dumps({"usage": {"input_tokens": -1}}), attempt))
    snapshot = service.get("alice", context.research_session_id)
    assert snapshot["provider_usage"]["accounting_valid"] is False
    assert snapshot["provider_usage"]["remaining"] == {"physical_requests": 0, "input_tokens": 0, "output_tokens": 0}
    assert snapshot["interaction"]["quota_exhausted"] is True
