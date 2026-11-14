"""Trusted same-action recovery; no hosted model or scientific-result doubles accepted as math."""
import asyncio
import json
import socket

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from bean_api.coordinator import CoordinatorFailure
from bean_api.research import ResearchService
from bean_api.research_checkpoints import ResearchCheckpointer
from bean_api.research_integration import create_application_research_coordinator
from bean_api.research_tools import ApplicationResearchPorts
from bean_api.store import Store
from bean_api.workflow import Workflow
from test_research_coordinator import Ports, ResearchModel, context, factory
from test_research_integration import PublishedBackendModel
from test_workflow import create_problem, dataset_body


@pytest.fixture(autouse=True)
def no_external_dispatch(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Pending-continuation checks cannot use network or a provider")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr("google.genai.Client", denied)


@pytest.mark.parametrize("approval_interrupt", [False, True])
def test_committed_child_lost_ack_reuses_job_without_repeating_model(approval_interrupt):
    async def exercise():
        ports, saver = Ports(), InMemorySaver()
        graph = factory(ports, saver=saver)
        if approval_interrupt:
            await graph.start()
        ports.review["decision"] = "approved"
        original = ports.execute_or_reconcile

        def lost_ack(*args):
            original(*args)
            raise RuntimeError("child committed, acknowledgement lost")

        ports.execute_or_reconcile = lost_ack
        with pytest.raises(RuntimeError, match="acknowledgement lost"):
            await (graph.resume() if approval_interrupt else graph.start())
        assert len(ports.children) == 1 and len(ports.turns) == 3
        ports.execute_or_reconcile = original
        restored = factory(ports, saver=saver)
        result = await restored.continue_pending()
        assert result["terminal"] == {"kind": "report", "record_id": "report"}
        assert len(ports.children) == 1 and len(ports.turns) == 4
        assert ports.tool_admissions.count("run_scientific_operation") == 1
        assert ports.execute_calls == [("proposal", "digest"), ("proposal", "digest")]
        before = (len(ports.turns), len(ports.tool_admissions), len(ports.execute_calls))
        assert await restored.continue_pending() == result
        assert before == (len(ports.turns), len(ports.tool_admissions), len(ports.execute_calls))

    asyncio.run(exercise())


def test_canonical_pause_is_not_bypassed_by_pending_continuation():
    async def exercise():
        ports = Ports()
        graph = factory(ports)
        await graph.start()
        with pytest.raises(CoordinatorFailure, match="research_canonical_approval_required"):
            await graph.continue_pending()
        assert not ports.children and len(ports.turns) == 3
        ports.review["decision"] = "approved"
        assert (await graph.continue_pending())["terminal"]["kind"] == "report"
    asyncio.run(exercise())


@pytest.mark.parametrize("change", ["input", "action", "revoked", "review"])
def test_recovery_rereads_authority_binding_and_exact_review(change):
    async def exercise():
        ports, saver = Ports(), InMemorySaver()
        ports.review["decision"] = "approved"
        original = ports.execute_or_reconcile

        def lost_ack(*args):
            original(*args)
            raise RuntimeError("ack lost")

        ports.execute_or_reconcile = lost_ack
        with pytest.raises(RuntimeError, match="ack lost"):
            await factory(ports, saver=saver).start()
        ports.execute_or_reconcile = original
        changes = {"input_digest": "changed"} if change == "input" else {"action_id": "other"} if change == "action" else {}
        if change == "revoked":
            ports.revoked = True
        if change == "review":
            ports.review["review_digest"] = "changed"
        before = (len(ports.turns), len(ports.execute_calls), len(ports.tool_admissions))
        with pytest.raises(CoordinatorFailure, match="research_checkpoint_incompatible|research_access_revoked|research_review_changed"):
            await factory(ports, saver=saver, ctx=context(**changes)).continue_pending()
        assert before == (len(ports.turns), len(ports.execute_calls), len(ports.tool_admissions))
    asyncio.run(exercise())


def test_pending_model_failure_is_never_retried_by_tool_continuation():
    class UnknownModelOutcome(ResearchModel):
        calls: int = 0

        def _generate(self, messages, **kwargs):
            self.calls += 1
            raise RuntimeError("unknown model outcome")

    async def exercise():
        ports, saver, model = Ports(), InMemorySaver(), UnknownModelOutcome()
        with pytest.raises(RuntimeError, match="unknown model outcome"):
            await factory(ports, model, saver).start()
        before = (len(ports.turns), model.calls)
        with pytest.raises(CoordinatorFailure, match="research_checkpoint_reconciliation_required"):
            await factory(ports, model, saver).continue_pending()
        assert before == (len(ports.turns), model.calls)
        assert not ports.children
    asyncio.run(exercise())


@pytest.mark.parametrize("changed_binding", [False, True])
def test_stale_new_action_hint_uses_effective_state_without_resetting_budget(changed_binding):
    async def exercise():
        ports, saver = Ports(), InMemorySaver()
        first = factory(ports, saver=saver)
        await first.start()
        ports.review["decision"] = "approved"
        execute = ports.execute_or_reconcile
        pending = True

        def queued(*args):
            result = execute(*args)
            if pending:
                result["state"] = "pending"
                result.pop("evidence")
            return result

        ports.execute_or_reconcile = queued
        assert (await first.resume())["awaiting_child"]
        assert ports.turns == [("action", 1), ("action", 2), ("action", 3)]
        pending = False
        restored = factory(ports, saver=saver, ctx=context(input_digest="changed") if changed_binding else context())
        if changed_binding:
            with pytest.raises(CoordinatorFailure, match="research_checkpoint_incompatible"):
                await restored.resume(new_action=True)
            assert len(ports.turns) == 3 and not ports.reports
        else:
            assert (await restored.resume(new_action=True))["terminal"]["kind"] == "report"
            assert ports.turns == [("action", 1), ("action", 2), ("action", 3), ("action", 4)]
            assert len(ports.children) == 1

    asyncio.run(exercise())


def test_actual_sqlite_child_commit_and_lost_ack_recover_one_reservation(tmp_path):
    """Real B journal/leases/checkpointer and Deep Agents; child is queued, not mathematically executed."""
    async def exercise():
        flow = Workflow(Store(tmp_path / "pending.sqlite3"))
        workspace = flow.create_workspace("alice", "Pending tool recovery")["id"]
        data = flow.create_dataset("alice", workspace, dataset_body(), "data")
        problem = create_problem(flow, workspace, data)
        service = ResearchService(flow)
        session = service.create("alice", workspace, {"objective": "Investigate the reviewed parameter range.",
            "problem_id": problem["id"], "expected_problem_digest": problem["digest"]}, "session")
        queued = service.advance("alice", session["id"], {"expected_revision": session["revision"]}, "advance")

        async def build(runtime, ports):
            snapshot = await ports.context()
            return await create_application_research_coordinator(context=runtime, ports=ports,
                checkpointer=ResearchCheckpointer(service, runtime),
                model_factory=lambda: PublishedBackendModel(reference_id=problem["id"]),
                event_sink=lambda event: service.observe(runtime, event), policy=snapshot["budget"])

        first = service.acquire("alice", queued["action"]["id"], "worker-before-review")
        graph = await build(first, ApplicationResearchPorts(service, first))
        paused = await graph.start()
        review = paused["interrupts"][0]
        service.release(first, "waiting_review")
        current = service.get("alice", session["id"])
        approved = service.decide("alice", session["id"], {"expected_revision": current["revision"],
            "pending_review_id": review["review_id"], "expected_review_digest": review["review_digest"],
            "decision": "approve", "accepted": True}, "approve")
        active = service.acquire("alice", approved["action"]["id"], "worker-before-crash")
        ports = ApplicationResearchPorts(service, active)
        execute = ports.execute_child

        async def lost_ack(review_id, expected_review_digest):
            await execute(review_id, expected_review_digest)
            raise RuntimeError("durable child commit before checkpoint acknowledgement")

        ports.execute_child = lost_ack
        graph = await build(active, ports)
        with pytest.raises(RuntimeError, match="durable child commit"):
            await graph.resume(new_action=True)
        with service.store.read() as conn:
            children = [dict(row) for row in conn.execute("SELECT * FROM research_effects WHERE kind='child'")]
            assert len(children) == 1 and children[0]["job_id"]
            old_action = dict(conn.execute("SELECT * FROM research_actions WHERE id=?", (active.action_id,)).fetchone())
            assert old_action["child_count"] == 1
        assert service.recover(force=True)["research_actions_needing_reconciliation"] == 1
        current = service.get("alice", session["id"])
        reconciled = service.reconcile("alice", session["id"], {"expected_revision": current["revision"],
            "acknowledged_unknown_outcome": True}, "reconcile")
        assert reconciled["action"]["id"] == active.action_id
        restored_context = service.acquire("alice", active.action_id, "worker-restarted")
        restored = await build(restored_context, ApplicationResearchPorts(service, restored_context))
        result = await restored.continue_pending()
        assert result["awaiting_child"]
        assert result["interrupts"][0]["job_id"] == children[0]["job_id"]
        with service.store.read() as conn:
            new_action = dict(conn.execute("SELECT * FROM research_actions WHERE id=?", (active.action_id,)).fetchone())
            assert (new_action["logical_turns"], new_action["tool_calls"], new_action["child_count"]) == (
                old_action["logical_turns"], old_action["tool_calls"], old_action["child_count"])
            assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1
            assert conn.execute("SELECT count(*) FROM provider_attempts").fetchone()[0] == 0
            assert json.loads(new_action["budget"]) == json.loads(old_action["budget"])

    asyncio.run(exercise())
