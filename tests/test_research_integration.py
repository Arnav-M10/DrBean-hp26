"""Actual A graph with controlled canonical-port producers; no B runtime claims.

The producer response shapes below are explicit adapter requirements pending B's
published implementation. Missing contracts fail closed instead of falling back.
"""
import asyncio
import copy
import socket
from types import SimpleNamespace

import pytest
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import InMemorySaver

from bean_api.coordinator import CoordinatorFailure
from bean_api.research_coordinator import GRAPH_VERSION
from bean_api.research_integration import (
    ACTION_POLICY, CHECKPOINT_VERSION, create_application_research_coordinator,
)
from test_research_coordinator import ResearchModel
from test_research_coordinator_adversarial import ToolScript


@pytest.fixture(autouse=True)
def deny_network_and_provider(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Application adapter component tests cannot contact a provider")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr("google.genai.Client", denied)


def runtime(**changes):
    fields = dict(actor_id="actor", workspace_id="workspace", research_session_id="session",
                  action_id="action", operation_id="operation", thread_id="private-thread",
                  lease_owner="worker", lease_epoch=1, mode="controlled", graph_version=GRAPH_VERSION,
                  checkpoint_version=CHECKPOINT_VERSION, policy_version=ACTION_POLICY)
    return SimpleNamespace(**{**fields, **changes})


class CanonicalBackend:
    """Controlled B-shaped authority, not a replacement backend or database."""

    def __init__(self):
        self.snapshot = {"objective": "Does this exact reviewed range survive?",
            "question": "Does this exact reviewed range survive?",
            "reviewed_context": {"input_id": "reviewed-input", "excluded_rows": ["row-excluded"]},
            "input_digest": "a" * 64, "reference_ids": ["reviewed-input"], "reviews": [],
            "design_constraints": None,
            "budget": {"policy_version": ACTION_POLICY, "model_turns": 4, "tool_calls": 6,
                       "scientific_reservations": 2, "active_seconds": 300}}
        self.review = {"review_id": "review", "review_digest": "b" * 64, "kind": "investigation",
            "approval_id": None, "decision": "pending",
            "scope": {"plan_id": "plan", "plan_digest": "c" * 64, "input_digest": "a" * 64}}
        self.fact = {"id": "evidence", "problem_id": "problem", "scientific_outcome": "certified_counterexample",
                     "verification": "valid", "expected_binding": "matches"}
        self.model_turns = 0
        self.tool_attempts = []
        self.plans, self.events, self.children, self.reports = [], [], {}, []
        self.prepared, self.design_arguments, self.child_requests = [], [], []
        self.revoked = False

    async def check_authority(self):
        if self.revoked:
            raise CoordinatorFailure("research_access_revoked")

    async def context(self):
        await self.check_authority()
        return copy.deepcopy(self.snapshot)

    async def update_plan(self, plan):
        self.plans.append(copy.deepcopy(plan))
        return copy.deepcopy(plan)

    async def _prepare(self, kind):
        self.prepared.append(kind)
        self.review["kind"] = kind
        self.snapshot["reviews"] = [copy.deepcopy(self.review)]
        return copy.deepcopy(self.review)

    async def prepare_investigation(self):
        return await self._prepare("investigation")

    async def prepare_followup(self):
        return await self._prepare("followup")

    async def prepare_design(self, constraints):
        self.design_arguments.append(copy.deepcopy(constraints))
        return await self._prepare("design")

    async def require_review(self, review_id, review_digest):
        await self.check_authority()
        if (review_id, review_digest) != (self.review["review_id"], self.review["review_digest"]):
            raise CoordinatorFailure("research_review_changed")
        return copy.deepcopy(self.review)

    async def execute_child(self, review_id, *, expected_review_digest):
        await self.check_authority()
        self.child_requests.append((review_id, expected_review_digest))
        if (review_id, expected_review_digest) != (self.review["review_id"], self.review["review_digest"]):
            raise CoordinatorFailure("research_review_changed")
        if self.review["decision"] != "approve" or self.review["approval_id"] is None:
            raise CoordinatorFailure("research_canonical_approval_required")
        self.children.setdefault(review_id, {**copy.deepcopy(self.review), "job_id": "job", "state": "completed",
            "evidence_ids": ["evidence"], "evidence": copy.deepcopy(self.fact)})
        self.snapshot["reference_ids"] = ["reviewed-input", "evidence"]
        return copy.deepcopy(self.children[review_id])

    async def read_evidence(self, evidence_id):
        await self.check_authority()
        assert evidence_id == "evidence" and self.children
        return copy.deepcopy(self.fact)

    async def request_clarification(self, fields, reason):
        return {"id": "clarification", "fields": fields, "reason": reason}

    async def publish_report(self):
        report = {"id": "report", "evidence_ids": ["evidence"]}
        self.reports.append(report)
        return copy.deepcopy(report)

    async def admit_model(self):
        await self.check_authority()
        self.model_turns += 1
        if self.model_turns > self.snapshot["budget"]["model_turns"]:
            raise CoordinatorFailure("research_model_budget_exhausted")

    async def admit_tool(self, name):
        await self.check_authority()
        self.tool_attempts.append(name)
        if len(self.tool_attempts) > self.snapshot["budget"]["tool_calls"]:
            raise CoordinatorFailure("research_tool_budget_exhausted")


async def build(backend, *, model=None, saver=None, ctx=None, policy=None):
    return await create_application_research_coordinator(context=ctx or runtime(), ports=backend,
        checkpointer=saver or InMemorySaver(), model_factory=lambda: model or ResearchModel(),
        event_sink=backend.events.append, policy=policy or copy.deepcopy(backend.snapshot["budget"]))


def test_actual_graph_uses_canonical_review_child_and_report_after_reconstruction():
    async def exercise():
        backend, saver = CanonicalBackend(), InMemorySaver()
        graph = await build(backend, saver=saver)
        paused = await graph.start()
        assert paused["awaiting_review"] and not backend.children
        state = await graph._graph.aget_state(graph._config)
        import json
        first_question = next(message for message in state.values["messages"] if isinstance(message, HumanMessage))
        assert json.loads(first_question.content) == {"question": backend.snapshot["objective"],
                                                      "reviewed_context": backend.snapshot["reviewed_context"]}
        backend.review.update(decision="approve", approval_id="approval")
        restored = await build(backend, saver=saver)
        result = await restored.resume()
        assert result["terminal"] == {"kind": "report", "record_id": "report"}
        assert backend.child_requests == [("review", "b" * 64)]
        assert len(backend.children) == len(backend.reports) == 1 and backend.model_turns == 4
        assert len(backend.tool_attempts) == 4  # Checkpoint tool replay is not another admitted model decision.
        assert result["todos"] == paused["todos"]
        record = await restored._graph.aget_state(restored._config)
        report_message = record.values["messages"][-1]
        report = json.loads(report_message.content)
        assert report["agent_commentary"]["scientific_authority"] is False
        assert report["commentary_persisted"] is False
        assert "agent_commentary" not in backend.reports[0]
        assert all("arguments" not in event and "args" not in event for event in backend.events)
        requested = [event for event in backend.events if event["summary"] == "tool_requested: run_scientific_operation"]
        assert len(requested) == 2 and requested[0]["observation_key"] == requested[1]["observation_key"]
    asyncio.run(exercise())


def test_new_review_action_and_same_action_child_wait_preserve_graph_and_one_job():
    async def exercise():
        backend, saver = CanonicalBackend(), InMemorySaver()
        first = await build(backend, saver=saver)
        reviewed = await first.start()
        backend.review.update(decision="approve", approval_id="approval")
        execute = backend.execute_child

        async def queued(review_id, *, expected_review_digest):
            result = await execute(review_id, expected_review_digest=expected_review_digest)
            result.update(state="pending", evidence_ids=[])
            result.pop("evidence")
            return result

        backend.execute_child = queued
        # This controlled producer represents B's already admitted approval
        # action; passing a fresh context is never itself backend admission.
        approved_context = runtime(action_id="approved-action", operation_id="approved-operation")
        parent = await build(backend, saver=saver, ctx=approved_context)
        waiting = await parent.resume(new_action=True)
        assert waiting["interrupts"][0]["kind"] == "canonical_scientific_child"
        assert waiting["interrupts"][0]["job_id"] == "job"
        assert waiting["todos"] == reviewed["todos"] and len(backend.children) == 1
        assert backend.model_turns == 3 and len(backend.tool_attempts) == 3
        wrong_action = await build(backend, saver=saver, ctx=runtime(action_id="another-action"))
        with pytest.raises(CoordinatorFailure, match="research_child_wait_cannot_renew_action"):
            await wrong_action.resume(new_action=True)
        backend.execute_child = execute
        restored = await build(backend, saver=saver, ctx=approved_context)
        done = await restored.resume()
        assert done["terminal"] == {"kind": "report", "record_id": "report"}
        assert len(backend.children) == 1 and len(backend.child_requests) == 2
        assert backend.child_requests[0] == backend.child_requests[1] == ("review", "b" * 64)
        assert backend.model_turns == 4 and len(backend.tool_attempts) == 4
        assert (await restored.snapshot())["model_turns"] == 1
    asyncio.run(exercise())


@pytest.mark.parametrize("missing", ["check_authority", "atomic_review_digest"])
def test_missing_authority_contract_refuses_before_model_construction(missing):
    async def exercise():
        backend = CanonicalBackend()
        if missing == "check_authority":
            backend.check_authority = None
            code = "research_backend_contract_required"
        else:
            async def legacy_execute(review_id):
                raise AssertionError("Legacy execute must never run")
            backend.execute_child = legacy_execute
            code = "research_atomic_review_binding_required"
        def forbidden_model():
            raise AssertionError("Incomplete authority must fail before constructing a model")
        with pytest.raises(CoordinatorFailure, match=code):
            await create_application_research_coordinator(context=runtime(), ports=backend,
                checkpointer=InMemorySaver(), model_factory=forbidden_model,
                event_sink=backend.events.append, policy=backend.snapshot["budget"])
        assert not backend.children
    asyncio.run(exercise())


@pytest.mark.parametrize("field", ["objective", "question", "reviewed_context", "input_digest", "budget",
                                   "reference_ids", "reviews", "design_constraints"])
def test_missing_snapshot_field_is_unavailable_not_an_invented_default(field):
    async def exercise():
        backend = CanonicalBackend()
        policy = copy.deepcopy(backend.snapshot["budget"])
        del backend.snapshot[field]
        with pytest.raises(CoordinatorFailure, match="research_backend_context_incomplete"):
            await build(backend, policy=policy)
        assert backend.model_turns == 0 and not backend.prepared
    asyncio.run(exercise())


def test_conflicting_question_and_objective_refuse_instead_of_selecting_one():
    async def exercise():
        backend = CanonicalBackend()
        backend.snapshot["question"] = "A different unreviewed research question"
        with pytest.raises(CoordinatorFailure, match="research_backend_context_incomplete"):
            await build(backend)
        assert backend.model_turns == 0
    asyncio.run(exercise())


def test_policy_and_snapshot_must_agree_and_lower_admitted_limits_are_preserved():
    async def exercise():
        backend = CanonicalBackend()
        backend.snapshot["budget"].update(model_turns=2, tool_calls=3, scientific_reservations=1, active_seconds=50)
        graph = await build(backend)
        assert (graph.context.max_model_turns, graph.context.max_tool_calls,
                graph.context.max_scientific_calls, graph.context.active_seconds) == (2, 3, 1, 50)
        enlarged = {**backend.snapshot["budget"], "model_turns": 4}
        with pytest.raises(CoordinatorFailure, match="research_backend_policy_mismatch"):
            await build(backend, policy=enlarged)
        assert backend.model_turns == 0
    asyncio.run(exercise())


def test_todo_completion_never_writes_canonical_completion_and_step_ids_are_stable():
    async def exercise():
        first, second = CanonicalBackend(), CanonicalBackend()
        await (await build(first, model=ResearchModel(mode="forged_complete"))).start()
        await (await build(second, model=ResearchModel(mode="forged_complete"))).start()
        assert first.plans[0] == second.plans[0]
        step = first.plans[0]["steps"][0]
        assert step["status"] == "pending" and "Agent-proposed completion" in step["reason"]
        assert step["dependencies"] == [] and step["reference_ids"] == []
        assert not first.children and not second.children
    asyncio.run(exercise())


def test_title_outside_canonical_bound_is_refused_without_truncation():
    async def exercise():
        backend = CanonicalBackend()
        model = ToolScript(calls=[("write_todos", {"todos": [{"content": "x" * 301, "status": "pending"}]})])
        with pytest.raises(CoordinatorFailure, match="research_plan_title_limit"):
            await (await build(backend, model=model)).start()
        assert not backend.plans
    asyncio.run(exercise())


@pytest.mark.parametrize("constraints", [None, {"feasible_times": ["1/1", "2/1"], "allowance": "1/20"}])
def test_design_uses_only_explicit_canonical_constraints_or_refuses(constraints):
    async def exercise():
        backend = CanonicalBackend()
        backend.snapshot["design_constraints"] = constraints
        model = ToolScript(calls=[("prepare_scientific_proposal", {"kind": "design", "reference_ids": ["reviewed-input"]}),
                                  ("request_clarification", {"fields": ["measurement"], "question": "Obtain the reviewed reading."})])
        graph = await build(backend, model=model)
        if constraints is None:
            with pytest.raises(CoordinatorFailure, match="research_design_constraints_unavailable"):
                await graph.start()
            assert not backend.design_arguments
        else:
            assert (await graph.start())["terminal"]["kind"] == "clarification"
            assert backend.design_arguments == [constraints]
            assert backend.snapshot["design_constraints"] == constraints
        assert not backend.children
    asyncio.run(exercise())


def test_unadmitted_reference_cannot_trigger_canonical_preparation():
    async def exercise():
        backend = CanonicalBackend()
        model = ToolScript(calls=[("prepare_scientific_proposal", {"kind": "followup", "reference_ids": ["foreign-input"]})])
        with pytest.raises(CoordinatorFailure, match="research_reference_out_of_scope"):
            await (await build(backend, model=model)).start()
        assert not backend.prepared and not backend.children
    asyncio.run(exercise())


def test_digest_is_passed_to_atomic_child_boundary_not_only_preflight():
    async def exercise():
        backend = CanonicalBackend()
        graph = await build(backend)
        await graph.start()
        backend.review.update(decision="approve", approval_id="approval")
        execute = backend.execute_child
        async def raced(review_id, *, expected_review_digest):
            backend.review["review_digest"] = "d" * 64
            return await execute(review_id, expected_review_digest=expected_review_digest)
        backend.execute_child = raced
        with pytest.raises(CoordinatorFailure, match="research_review_changed"):
            await graph.resume()
        assert backend.child_requests == [("review", "b" * 64)] and not backend.children
    asyncio.run(exercise())


def test_wrong_report_evidence_is_not_accepted_as_a_terminal_success():
    async def exercise():
        backend = CanonicalBackend()
        graph = await build(backend)
        await graph.start()
        backend.review.update(decision="approve", approval_id="approval")
        async def wrong_report():
            return {"id": "wrong-report", "evidence_ids": ["other-input-evidence"]}
        backend.publish_report = wrong_report
        with pytest.raises(CoordinatorFailure, match="research_report_binding_invalid"):
            await graph.resume()
        state = await graph._graph.aget_state(graph._config)
        assert state.values.get("research_terminal") is None and len(backend.children) == 1
    asyncio.run(exercise())
