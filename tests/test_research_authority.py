"""B's application-authority tests. Controlled, no provider/science assertions."""
import asyncio
from dataclasses import replace
import sqlite3
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
from langgraph.types import Command, interrupt
import pytest

from bean_api.research import ResearchService
from bean_api.research_checkpoints import ResearchCheckpointer, ResearchJSON
from bean_api.research_contracts import ResearchCreate, ResearchPlanRevision
from bean_api.research_tools import ApplicationResearchPorts
from bean_api.store import Store
from bean_api.workflow import DomainError, Workflow
from test_workflow import dataset_body, create_problem


@pytest.fixture
def research(tmp_path):
    flow = Workflow(Store(tmp_path / "authority.sqlite3"))
    workspace = flow.create_workspace("alice", "Controlled authority checks")["id"]
    data = flow.create_dataset("alice", workspace, dataset_body(), "data")
    problem = create_problem(flow, workspace, data)
    service = ResearchService(flow)
    body = {"objective": "Does the reviewed range survive this bounded investigation?", "problem_id": problem["id"], "expected_problem_digest": problem["digest"]}
    session = service.create("alice", workspace, body, "session")
    return service, session, body


def run(awaitable):
    return asyncio.run(awaitable)


def acquired(research):
    service, session, _ = research
    queued = service.advance("alice", session["id"], {"expected_revision": session["revision"]}, "advance")
    context = service.acquire("alice", queued["action"]["id"], "worker-test")
    return service, context, ApplicationResearchPorts(service, context)


def approved(research):
    service, context, ports = acquired(research)
    prepared = run(ports.prepare_investigation())
    assert run(ports.require_review(prepared["review_id"], prepared["review_digest"]))["decision"] == "pending"
    service.release(context, "waiting_review")
    current = service.get("alice", context.research_session_id)
    body = {"expected_revision": current["revision"], "pending_review_id": prepared["review_id"], "expected_review_digest": prepared["review_digest"], "decision": "approve", "accepted": True}
    resumed = service.decide("alice", current["id"], body, "approve")
    next_context = service.acquire("alice", resumed["action"]["id"], "worker-next")
    return service, next_context, ApplicationResearchPorts(service, next_context), prepared, body


def code(expected, callback):
    with pytest.raises(DomainError) as caught:
        callback()
    assert caught.value.code == expected


def test_session_retry_body_binding_private_thread_and_tenant(research):
    service, session, body = research
    assert service.create("alice", session["workspace_id"], body, "session") == session
    code("idempotency_conflict", lambda: service.create("alice", session["workspace_id"], {**body, "objective": "changed"}, "session"))
    code("not_found", lambda: service.get("mallory", session["id"]))
    assert "thread_id" not in session and "actor_id" not in session
    assert session["mode"] == "controlled" and session["usage"]["physical_calls"] == 0


def test_stale_inputs_rejected_without_new_action(research):
    service, session, _ = research
    problem = service.workflow.get("alice", session["problem_id"])
    data = service.workflow.get("alice", problem["body"]["dataset_id"])
    service.workflow.create_dataset("alice", session["workspace_id"], {**data["body"], "parent_id": data["id"], "change_reason": "Changed review"}, "changed")
    code("stale_research_inputs", lambda: service.advance("alice", session["id"], {"expected_revision": session["revision"]}, "advance"))
    assert service.get("alice", session["id"])["action"] is None


def test_one_advancing_lease_and_cumulative_admission(research):
    service, context, ports = acquired(research)
    code("research_lease_unavailable", lambda: service.acquire("alice", context.action_id, "other"))
    for _ in range(4):
        run(ports.admit_model())
    code("research_budget_exhausted", lambda: run(ports.admit_model()))
    assert service.get("alice", context.research_session_id)["usage"]["logical_turns"] == 4
    code("research_authority_revoked", lambda: run(ApplicationResearchPorts(service, replace(context, lease_epoch=99)).admit_tool("read")))


def test_decision_approval_resume_atomic_and_retry_safe(research):
    service, context, ports, prepared, decision = approved(research)
    repeat = service.decide("alice", context.research_session_id, decision, "approve")
    assert repeat["action"]["id"] == context.action_id
    with service.store.read() as conn:
        assert conn.execute("SELECT count(*) FROM approvals").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM entities WHERE kind='research_decision'").fetchone()[0] == 1
    assert run(ports.require_review(prepared["review_id"], prepared["review_digest"]))["approval_id"]
    code("stale_review", lambda: run(ports.execute_child(prepared["review_id"], "0" * 64)))
    code("stale_research_revision", lambda: service.decide("alice", context.research_session_id, decision, "fresh-key"))


def test_child_created_checkpoint_absent_reuses_one_reservation(research):
    service, context, ports, prepared, _ = approved(research)
    first = run(ports.execute_child(prepared["review_id"], prepared["review_digest"]))
    service.recover(force=True)  # Previous worker is established gone in this offline test.
    code("research_authority_revoked", lambda: run(ports.execute_child(prepared["review_id"], prepared["review_digest"])))
    current = service.get("alice", context.research_session_id)
    service.reconcile("alice", current["id"], {"expected_revision": current["revision"], "acknowledged_unknown_outcome": True}, "recover")
    recovered = service.acquire("alice", context.action_id, "replacement")
    second = run(ApplicationResearchPorts(service, recovered).execute_child(prepared["review_id"], prepared["review_digest"]))
    assert first["job_id"] == second["job_id"]
    with service.store.read() as conn:
        assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1
    assert service.get("alice", current["id"])["usage"]["child_count"] == 1


def test_intent_committed_child_absent_retry_does_not_charge_again(research, monkeypatch):
    service, context, ports, prepared, _ = approved(research)
    original = service.workflow._start_in_transaction
    def crash(*args):
        raise RuntimeError("controlled crash before child reservation")
    monkeypatch.setattr(service.workflow, "_start_in_transaction", crash)
    with pytest.raises(RuntimeError):
        run(ports.execute_child(prepared["review_id"], prepared["review_digest"]))
    with service.store.read() as conn:
        assert conn.execute("SELECT count(*) FROM jobs").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM research_effects WHERE state='intent'").fetchone()[0] == 1
    monkeypatch.setattr(service.workflow, "_start_in_transaction", original)
    child = run(ports.execute_child(prepared["review_id"], prepared["review_digest"]))
    assert child["waiting"]
    assert service.get("alice", context.research_session_id)["usage"]["child_count"] == 1


def test_cancel_revokes_checkpoints_and_stops_only_owned_child(research):
    service, context, ports, prepared, _ = approved(research)
    child = run(ports.execute_child(prepared["review_id"], prepared["review_digest"]))
    service.cancel("alice", context.research_session_id, "cancel")
    code("research_authority_revoked", lambda: run(ports.check_authority()))
    assert service.workflow.get_run("alice", child["job_id"])["state"] == "cancel_requested"
    assert service.cancel("alice", context.research_session_id, "cancel")["state"] == "cancelled"


def test_plan_revisions_immutable_and_events_ordered(research):
    service, context, ports = acquired(research)
    first = run(ports.update_plan({"steps": [{"id": "investigate", "title": "Review investigation", "status": "pending"}]}))
    second = run(ports.update_plan({"steps": [{"id": "investigate", "title": "Review investigation", "status": "waiting_review"}]}))
    assert first["id"] != second["id"] and second["parent_id"] == first["id"]
    assert service.workflow.get("alice", first["id"])["body"]["steps"][0]["status"] == "pending"
    with pytest.raises(sqlite3.IntegrityError), service.store.transaction() as conn:
        conn.execute("UPDATE entities SET body='{}' WHERE id=?", (first["id"],))
    events = service.events("alice", context.research_session_id)
    assert [e["sequence"] for e in events] == list(range(len(events)))
    with pytest.raises(sqlite3.IntegrityError), service.store.transaction() as conn:
        conn.execute("DELETE FROM research_events")


def test_checkpoint_real_interrupt_reconstructed_runtime_and_fence(research):
    service, context, _ = acquired(research)
    saver = ResearchCheckpointer(service, context)
    def graph(checkpointer):
        builder = StateGraph(dict)
        builder.add_node("review", lambda state: {**state, "answer": interrupt({"review_id": "controlled-review"})})
        builder.add_edge(START, "review")
        builder.add_edge("review", END)
        return builder.compile(checkpointer=checkpointer)
    config = {"configurable": {"thread_id": context.thread_id}}
    result = graph(saver).invoke({"question": "controlled"}, config)
    assert "__interrupt__" in result
    # New objects and database connections, with no in-memory graph state.
    fresh = ResearchService(Workflow(Store(service.store.path)))
    resumed = graph(ResearchCheckpointer(fresh, context)).invoke(Command(resume="reviewed"), config)
    assert resumed["answer"] == "reviewed"
    service.cancel("alice", context.research_session_id, "cancel")
    code("research_authority_revoked", lambda: saver.get_tuple(config))
    with pytest.raises(ValueError):
        saver.get_tuple({"configurable": {"thread_id": "other-private-thread"}})


def test_checkpoint_codec_no_executable_deserialization_or_unbounded_state():
    codec = ResearchJSON()
    value = {"messages": [HumanMessage(content="source text is data"), AIMessage(content="review needed")], "tuple": (1, 2), "untrusted": {"__type__": "os.system", "lc": 2, "type": "constructor", "id": ["os", "system"]}}
    assert codec.loads(codec.dumps(value)) == value
    with pytest.raises(ValueError):
        codec.loads(b'["pickle", "arbitrary"]')
    with pytest.raises(ValueError):
        codec.dumps({"large": "x" * (1024 * 1024)})
    with pytest.raises(ValueError):
        codec.dumps(object())


def test_contract_refuses_forged_authority_and_invalid_dependencies():
    with pytest.raises(ValueError):
        ResearchCreate.model_validate({"objective": "x", "actor_id": "owner"})
    with pytest.raises(ValueError):
        ResearchCreate.model_validate({"objective": "x", "problem_id": "p"})
    with pytest.raises(ValueError):
        ResearchPlanRevision.model_validate({"steps": [{"id": "a", "title": "a", "status": "pending", "dependencies": ["b"]}, {"id": "b", "title": "b", "status": "pending", "dependencies": ["a"]}]})


def test_migration_preserves_existing_records_and_repeat_start(research):
    service, session, _ = research
    reopened = ResearchService(Workflow(Store(service.store.path)))
    assert reopened.get("alice", session["id"]) == session
    with reopened.store.read() as conn:
        assert conn.execute("PRAGMA user_version").fetchone()[0] == 2


def test_published_valid_refused_examples_and_producer_fixture():
    import json
    from bean_api.research_contracts import PUBLIC_RESEARCH_SCHEMAS, ResearchEvent
    root = Path(__file__).resolve().parents[1] / "shared/contracts/DB-RESEARCH-1"
    for name, examples in json.loads((root / "examples.json").read_text()).items():
        model = PUBLIC_RESEARCH_SCHEMAS[name]
        model.model_validate(examples["valid"])
        with pytest.raises(ValueError):
            model.model_validate(examples["refused"])
    fixture = json.loads((root / "event-plan.fixture.json").read_text())
    ResearchEvent.model_validate(fixture["event"])
    ResearchPlanRevision.model_validate(fixture["plan"])
