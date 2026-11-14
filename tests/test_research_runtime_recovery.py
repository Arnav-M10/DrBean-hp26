"""Ordinary worker recovery over real SQLite/graph journals, entirely offline.

The child-commit test queues actual canonical jobs but does not claim solver
execution. The unknown-request case uses the existing substituted SDK fixture.
"""
import socket

from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
import pytest

from bean_api.config import Settings
from bean_api.research import ResearchService
from bean_api.research_runtime import ResearchRunner
from bean_api.research_tools import ApplicationResearchPorts
from bean_api.store import Store
from bean_api.workflow import DomainError, Workflow
from test_research_coordinator import ResearchModel
from test_research_integration import PublishedBackendModel
import test_research_metered_application as metered
from test_research_metered_application import create_session, consent, advance
from test_workflow import create_problem, dataset_body

metered_app = metered.metered_app


class WorkerLoss(BaseException):
    """Deliberately escapes Exception handling, like abrupt process loss."""


class CountingBackendModel(PublishedBackendModel):
    calls: int = 0

    def _generate(self, messages, **kwargs):
        self.calls += 1
        return super()._generate(messages, **kwargs)


class ClarifyingModel(ResearchModel):
    calls: int = 0

    def _generate(self, messages, **kwargs):
        self.calls += 1
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[{
            "name": "request_clarification", "id": "clarify-reviewed-data", "type": "tool_call",
            "args": {"fields": ["reviewed_problem"], "question": "Review the model and observations."},
        }]))])


@pytest.fixture
def authority(tmp_path, monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Recovery cannot make network or provider calls")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr("google.genai.Client", denied)
    flow = Workflow(Store(tmp_path / "recovery.sqlite3"))
    workspace = flow.create_workspace("alice", "Offline recovery")["id"]
    data = flow.create_dataset("alice", workspace, dataset_body(), "data")
    problem = create_problem(flow, workspace, data)
    service = ResearchService(flow)
    session = service.create("alice", workspace, {"objective": "Investigate the reviewed range.",
        "problem_id": problem["id"], "expected_problem_digest": problem["digest"]}, "session")
    settings = Settings(database_path=str(flow.store.path), research_mode="controlled", science_adapter="unavailable")
    return service, session, settings, problem


def queue(service, session):
    return service.advance("alice", session["id"], {"expected_revision": session["revision"]}, "advance")


def reconcile(service, session_id, key="reconcile"):
    current = service.get("alice", session_id)
    body = {"expected_revision": current["revision"], "acknowledged_unknown_outcome": True}
    result = service.reconcile("alice", session_id, body, key)
    return result, body


def admitted(service, action_id):
    with service.store.read() as conn:
        action = service._action(conn, "alice", action_id)
        return {key: action[key] for key in ("id", "operation_id", "budget", "logical_turns", "tool_calls", "child_count", "physical_calls")}


def test_worker_reconciles_lost_child_ack_once_without_new_model_or_science_reservation(authority, monkeypatch):
    service, session, settings, problem = authority
    model = CountingBackendModel(reference_id=problem["id"])
    runner = ResearchRunner(service.workflow, settings, "initial-worker", model_factory=lambda: model)
    queue(service, session)
    assert runner.tick() == 1
    waiting = service.get("alice", session["id"])
    assert waiting["state"] == "waiting_review" and model.calls == 3
    approved = service.decide("alice", session["id"], {"expected_revision": waiting["revision"],
        "pending_review_id": waiting["pending_review"]["id"], "expected_review_digest": waiting["pending_review_digest"],
        "decision": "approve", "accepted": True}, "approve")
    execute = ApplicationResearchPorts.execute_child

    async def lose_ack(ports, review_id, expected_review_digest):
        await execute(ports, review_id, expected_review_digest)
        raise WorkerLoss("process lost after canonical child commit")

    monkeypatch.setattr(ApplicationResearchPorts, "execute_child", lose_ack)
    release = runner.service.release
    monkeypatch.setattr(runner.service, "release", lambda *args, **kwargs: (_ for _ in ()).throw(WorkerLoss("worker lost before action acknowledgement")))
    with pytest.raises(WorkerLoss):
        runner.tick()
    action_id = approved["action"]["id"]
    before = admitted(service, action_id)
    with service.store.read() as conn:
        effect = dict(conn.execute("SELECT * FROM research_effects WHERE kind='child'").fetchone())
        assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1
        epoch = service._action(conn, "alice", action_id)["lease_epoch"]
    monkeypatch.setattr(ApplicationResearchPorts, "execute_child", execute)
    monkeypatch.setattr(runner.service, "release", release)
    assert service.recover(force=True)["research_actions_needing_reconciliation"] == 1
    queued, request = reconcile(service, session["id"])
    assert queued["action"]["id"] == action_id
    restarted = ResearchRunner(service.workflow, settings, "replacement-worker", model_factory=lambda: model)
    assert restarted.tick() == 1
    current = service.get("alice", session["id"])
    assert current["state"] == "waiting_child", current
    assert current["action"]["waiting_job_id"] == effect["job_id"]
    assert admitted(service, action_id) == before
    assert model.calls == 3
    assert service.reconcile("alice", session["id"], request, "reconcile") == queued
    assert restarted.tick() == 0  # Lost acknowledgement retry cannot requeue it.
    with service.store.read() as conn:
        assert service._action(conn, "alice", action_id)["lease_epoch"] > epoch
        assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM provider_attempts").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM research_effects WHERE kind='child'").fetchone()[0] == 1


def test_worker_reads_committed_terminal_after_lost_release_without_repeating_model(authority, monkeypatch):
    service, session, settings, _ = authority
    model = ClarifyingModel()
    runner = ResearchRunner(service.workflow, settings, "initial-worker", model_factory=lambda: model)
    action_id = queue(service, session)["action"]["id"]
    release = runner.service.release
    monkeypatch.setattr(runner.service, "release", lambda *args, **kwargs: (_ for _ in ()).throw(WorkerLoss("lost terminal acknowledgement")))
    with pytest.raises(WorkerLoss):
        runner.tick()
    before = admitted(service, action_id)
    assert model.calls == 1
    monkeypatch.setattr(runner.service, "release", release)
    service.recover(force=True)
    reconcile(service, session["id"])
    restarted = ResearchRunner(service.workflow, settings, "replacement-worker", model_factory=lambda: model)
    assert restarted.tick() == 1
    current = service.get("alice", session["id"])
    assert current["state"] == "waiting_review" and current["pending_review"]["kind"] == "research_clarification"
    assert model.calls == 1 and admitted(service, action_id) == before
    assert restarted.tick() == 0


def test_uncertain_physical_request_stays_reserved_and_cannot_be_resumed(metered_app, monkeypatch):
    client, service, worker, wire = metered_app
    session = create_session(client)
    consent(client, session)
    service.allocate_provider("alice", session["id"], {"physical_requests": 2,
        "input_tokens": 48_000, "output_tokens": 1024, "accepted": True}, "offline-allocation")
    assert advance(client, session).status_code == 200
    wire.before_request = lambda: (_ for _ in ()).throw(WorkerLoss("lost SDK response"))
    release = worker.research.service.release
    monkeypatch.setattr(worker.research.service, "release", lambda *args, **kwargs: (_ for _ in ()).throw(WorkerLoss("worker lost before action acknowledgement")))
    with pytest.raises(WorkerLoss):
        worker.research.tick()
    monkeypatch.setattr(worker.research.service, "release", release)
    current = service.get("alice", session["id"])
    before = admitted(service, current["action"]["id"])
    assert before["physical_calls"] == 1 and len(wire.constructions) == 1
    service.recover(force=True)
    current = service.get("alice", session["id"])
    with pytest.raises(DomainError) as error:
        service.reconcile("alice", session["id"], {"expected_revision": current["revision"],
            "acknowledged_unknown_outcome": True}, "recover")
    assert error.value.code == "provider_outcome_unknown"
    assert worker.research.tick() == 0 and len(wire.constructions) == 1
    assert admitted(service, current["action"]["id"]) == before
    attempts = client.app.state.ledger.list_attempts("alice", session["workspace_id"])
    assert len(attempts) == 1 and attempts[0]["state"] == "unknown_outcome"
    assert current["state"] == "needs_reconciliation"


def test_reconciled_pending_model_without_committed_output_exposes_stop_instead_of_retry(authority, monkeypatch):
    service, session, settings, _ = authority

    class LostModel(ResearchModel):
        calls: int = 0

        def _generate(self, messages, **kwargs):
            self.calls += 1
            raise WorkerLoss("model result not checkpointed")

    model = LostModel()
    runner = ResearchRunner(service.workflow, settings, "initial-worker", model_factory=lambda: model)
    action_id = queue(service, session)["action"]["id"]
    release = runner.service.release
    monkeypatch.setattr(runner.service, "release", lambda *args, **kwargs: (_ for _ in ()).throw(WorkerLoss("worker lost before action acknowledgement")))
    with pytest.raises(WorkerLoss):
        runner.tick()
    monkeypatch.setattr(runner.service, "release", release)
    before = admitted(service, action_id)
    service.recover(force=True)
    reconcile(service, session["id"])
    assert runner.tick() == 1
    current = service.get("alice", session["id"])
    assert current["state"] == "needs_reconciliation"
    assert current["action"]["error_code"] == "research_model_outcome_unrecoverable"
    assert admitted(service, action_id) == before and model.calls == 1
    with pytest.raises(DomainError) as error:
        reconcile(service, session["id"], "second-explicit-reconcile")
    assert error.value.code == "research_model_outcome_unrecoverable"
    assert runner.tick() == 0
    assert service.cancel("alice", session["id"], "cancel-retained-action")["state"] == "cancelled"


def test_completed_physical_response_without_checkpoint_is_not_requested_again(metered_app, monkeypatch):
    from bean_api.gemini_chat_model import GeminiChatModel

    client, service, worker, wire = metered_app
    session = create_session(client)
    consent(client, session)
    service.allocate_provider("alice", session["id"], {"physical_requests": 2,
        "input_tokens": 48_000, "output_tokens": 1024, "accepted": True}, "offline-allocation")
    assert advance(client, session).status_code == 200
    generate = GeminiChatModel._agenerate

    async def lose_checkpoint(model, messages, stop=None, run_manager=None, **kwargs):
        await generate(model, messages, stop=stop, run_manager=run_manager, **kwargs)
        raise WorkerLoss("physical response accounted but model checkpoint lost")

    monkeypatch.setattr(GeminiChatModel, "_agenerate", lose_checkpoint)
    release = worker.research.service.release
    monkeypatch.setattr(worker.research.service, "release", lambda *args, **kwargs: (_ for _ in ()).throw(WorkerLoss("worker lost before action acknowledgement")))
    with pytest.raises(WorkerLoss):
        worker.research.tick()
    monkeypatch.setattr(GeminiChatModel, "_agenerate", generate)
    monkeypatch.setattr(worker.research.service, "release", release)
    current = service.get("alice", session["id"])
    before = admitted(service, current["action"]["id"])
    attempts = client.app.state.ledger.list_attempts("alice", session["workspace_id"])
    assert len(attempts) == len(wire.requests) == 1 and attempts[0]["state"] == "completed"
    service.recover(force=True)
    reconcile(service, session["id"])
    assert worker.research.tick() == 1
    current = service.get("alice", session["id"])
    assert current["state"] == "needs_reconciliation"
    assert current["action"]["error_code"] == "research_model_outcome_unrecoverable"
    assert admitted(service, current["action"]["id"]) == before
    assert len(wire.requests) == len(wire.constructions) == 1
    assert client.app.state.ledger.list_attempts("alice", session["workspace_id"]) == attempts
    with pytest.raises(DomainError) as error:
        reconcile(service, session["id"], "second-explicit-reconcile")
    assert error.value.code == "research_model_outcome_unrecoverable"
    assert worker.research.tick() == 0


def test_recovery_of_safe_plan_proposal_batch_preserves_prepared_identity(authority, monkeypatch):
    service, session, settings, problem = authority

    class BatchedModel(CountingBackendModel):
        def _generate(self, messages, **kwargs):
            from langchain_core.messages import ToolMessage
            if any(isinstance(message, ToolMessage) for message in messages):
                return super()._generate(messages, **kwargs)
            self.calls += 1
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[
                {"name": "write_todos", "id": "batch-plan", "type": "tool_call", "args": {
                    "todos": [{"content": "Investigate reviewed measurements", "status": "in_progress"}]}},
                {"name": "prepare_scientific_proposal", "id": "batch-proposal", "type": "tool_call",
                 "args": {"kind": "investigation", "reference_ids": [self.reference_id]}},
            ]))])

    model = BatchedModel(reference_id=problem["id"])
    runner = ResearchRunner(service.workflow, settings, "initial-worker", model_factory=lambda: model)
    action_id = queue(service, session)["action"]["id"]
    prepare = ApplicationResearchPorts.prepare_investigation
    release = runner.service.release

    async def lose_ack(ports):
        await prepare(ports)
        raise WorkerLoss("prepared scope committed before batch acknowledgement")

    monkeypatch.setattr(ApplicationResearchPorts, "prepare_investigation", lose_ack)
    monkeypatch.setattr(runner.service, "release", lambda *args, **kwargs: (_ for _ in ()).throw(WorkerLoss("worker lost before acknowledgement")))
    with pytest.raises(WorkerLoss):
        runner.tick()
    before = admitted(service, action_id)
    assert model.calls == before["logical_turns"] == 1 and before["tool_calls"] == 2
    with service.store.read() as conn:
        prepared_id = conn.execute("SELECT plan_id FROM research_effects WHERE kind='investigation'").fetchone()[0]
        original_plan = conn.execute("SELECT plan_revision_id FROM research_sessions WHERE id=?", (session["id"],)).fetchone()[0]
    monkeypatch.setattr(ApplicationResearchPorts, "prepare_investigation", prepare)
    monkeypatch.setattr(runner.service, "release", release)
    service.recover(force=True)
    reconcile(service, session["id"])
    assert runner.tick() == 1
    current = service.get("alice", session["id"])
    assert current["state"] == "waiting_review", current["action"]
    assert current["pending_review"]["id"] == prepared_id and current["plan"]["id"] == original_plan
    assert model.calls == 2 and current["usage"]["tool_calls"] == 3
    assert current["usage"]["child_count"] == 0
    with service.store.read() as conn:
        assert conn.execute("SELECT count(*) FROM research_effects WHERE kind='investigation'").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0
    assert runner.tick() == 0
