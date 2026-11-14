"""Actual graph, controlled model/ports; these are NOT backend durability acceptance."""
import asyncio
import copy
import json
import socket
from dataclasses import replace

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from bean_api.coordinator import CoordinatorFailure
from bean_api.research_coordinator import PORT_VERSION, TOOLS, ResearchContext, create_research_coordinator


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def denied(*args, **kwargs):
        pytest.fail("Controlled graph attempted a network connection")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


class ResearchModel(BaseChatModel):
    model_name: str = "controlled-research-parent"
    mode: str = "adapt"
    offered: list[str] = []

    @property
    def _llm_type(self):
        return "controlled-research"

    def bind_tools(self, tools, **kwargs):
        self.offered = sorted(t.name for t in tools)
        return self

    def _generate(self, messages, **kwargs):
        observed = [m for m in messages if isinstance(m, ToolMessage)]
        if self.mode == "plain":
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="I proved everything."))])
        if self.mode == "forbidden":
            name, args = "execute", {"command": "env"}
        elif self.mode == "loop":
            name, args = "write_todos", {"todos": [{"content": "Review assumptions", "status": "pending"}]}
        elif not observed:
            name, args = "write_todos", {"todos": [{"content": "Investigate reviewed measurements", "status": "in_progress"},
                                                   {"content": "Review useful next measurement", "status": "pending"}]}
            if self.mode == "forged_complete":
                args["todos"][0]["status"] = "completed"
            if self.mode == "large_plan":
                args["todos"] *= 7
        elif len(observed) == 1:
            name, args = "prepare_scientific_proposal", {"kind": "investigation", "reference_ids": ["reviewed-input"]}
            if self.mode == "extra_args":
                args["approved"] = True
            if self.mode == "remove_completed":
                name, args = "write_todos", {"todos": [{"content": "New future", "status": "pending"}]}
        elif len(observed) == 2:
            proposal = json.loads(observed[-1].content)
            name, args = "run_scientific_operation", {"proposal_id": proposal["proposal_id"],
                "proposal_digest": proposal["proposal_digest"], "review_id": proposal["review_id"],
                "review_digest": proposal["review_digest"]}
        else:
            result = json.loads(observed[-1].content)
            if result["state"] == "rejected":
                name, args = "request_clarification", {"fields": ["scope"], "question": "Which scope should be reviewed?"}
            else:
                name, args = "publish_research_report", {"evidence_ids": [result["evidence"]["id"]],
                    "text": "The evidence has a conditional scope.",
                    "next_action": "review_design" if result["evidence"]["scientific_outcome"] == "certified_counterexample"
                    else "clarify"}
                if self.mode == "bad_claim":
                    args["text"] = "This proves the interval and identifies the true model."
        message = AIMessage(content="", tool_calls=[{"name": name, "args": args,
                             "id": f"research-call-{len(observed)}", "type": "tool_call"}])
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(self, messages, **kwargs):
        return self._generate(messages, **kwargs)


class Ports:
    """In-process test authority only, deliberately no claim of disk persistence."""
    version = PORT_VERSION

    def __init__(self, outcome="certified_counterexample"):
        self.revoked = False
        self.turns = []
        self.tool_admissions = []
        self.plans = []
        self.events = []
        self.children = {}
        self.execute_calls = []
        self.reports = []
        self.review = {"proposal_id": "proposal", "proposal_digest": "digest", "review_id": "review",
                       "review_digest": "review-digest", "decision": "pending"}
        self.fact = {"id": "fact", "problem_id": "problem", "scientific_outcome": outcome,
                     "verification": "valid", "expected_binding": "matches"}

    def check_authority(self):
        if self.revoked:
            raise CoordinatorFailure("research_access_revoked")

    def admit_model_turn(self, action_id, turn):
        self.check_authority()
        if sum(a == action_id for a, _ in self.turns) >= 4:
            raise CoordinatorFailure("durable_action_budget_exhausted")
        self.turns.append((action_id, turn))

    def record_plan(self, todos, plan_digest):
        self.plans.append({"todos": todos, "digest": plan_digest})

    def admit_tool(self, name):
        self.tool_admissions.append(name)

    def prepare_proposal(self, kind, reference_ids):
        assert kind == "investigation" and reference_ids == ["reviewed-input"]
        return {"proposal_id": "proposal", "proposal_digest": "digest", "accepted": False,
                "review_id": "review", "review_digest": "review-digest"}

    def read_review(self, proposal_id):
        assert proposal_id == "proposal"
        return copy.deepcopy(self.review)

    def execute_or_reconcile(self, proposal_id, proposal_digest, review_id, review_digest, max_scientific_calls):
        self.check_authority()
        assert self.review["decision"] == "approved" and self.review["proposal_digest"] == proposal_digest
        assert self.review["review_id"] == review_id and self.review["review_digest"] == review_digest
        self.execute_calls.append((proposal_id, proposal_digest))
        self.children.setdefault(proposal_id, {"proposal_id": proposal_id, "state": "completed", "job_id": "job",
                                               "evidence": copy.deepcopy(self.fact)})
        return copy.deepcopy(self.children[proposal_id])

    def read_evidence(self, evidence_id):
        assert evidence_id == "fact" and self.children
        return copy.deepcopy(self.fact)

    def clarify(self, fields, question):
        return {"id": "clarification", "fields": fields, "question": question}

    def publish_report(self, evidence_ids, commentary):
        self.reports.append(commentary)
        return {"id": "report", "evidence_ids": evidence_ids}

    def record_event(self, event):
        self.events.append(event)


def context(**changes):
    return replace(ResearchContext("workspace", "session", "action", "private-thread", "input-digest",
                                   "Do my measurements support this range?", {"input_id": "reviewed-input"}), **changes)


def factory(ports, model=None, saver=None, ctx=None):
    return create_research_coordinator(context=ctx or context(), ports=ports,
            model_factory=lambda: model or ResearchModel(), checkpointer=saver or InMemorySaver())


@pytest.mark.parametrize("outcome,next_action", [("certified_counterexample", "review_design"),
                                                 ("no_counterexample_found", "clarify")])
def test_real_plan_interrupt_reconstructed_graph_and_evidence_dependent_decision(outcome, next_action):
    async def exercise():
        ports, saver, model = Ports(outcome), InMemorySaver(), ResearchModel()
        first = factory(ports, model, saver)
        paused = await first.start()
        assert paused["awaiting_review"] and ports.children == {}
        assert ports.plans[0]["todos"] == paused["todos"]
        assert set(model.offered) == TOOLS
        assert not set(model.offered) & {"task", "execute", "write_file", "read_file"}
        assert paused["interrupts"][0]["review_id"] == "review"
        with pytest.raises(CoordinatorFailure, match="research_canonical_approval_required"):
            await first.resume()
        assert len(ports.turns) == 3 and not ports.children
        ports.review["decision"] = "approved"
        # Rebuilding the real graph with the same saver preserves state. This is
        # not fresh-process disk persistence or B's actual application startup.
        restored = factory(ports, ResearchModel(), saver)
        done = await restored.resume()
        assert not done["awaiting_review"] and done["terminal"] == {"kind": "report", "record_id": "report"}
        assert len(ports.children) == 1 and ports.reports[0]["next_action"] == next_action
        assert len(ports.turns) == 4 and done["todos"] == paused["todos"]
        assert ports.reports[0]["scientific_authority"] is False
        before = (len(ports.turns), len(ports.children))
        assert not (await restored.snapshot())["awaiting_review"]
        assert before == (len(ports.turns), len(ports.children))
        with pytest.raises(CoordinatorFailure, match="research_action_already_started"):
            await restored.start()
        with pytest.raises(CoordinatorFailure, match="research_not_awaiting_review"):
            await restored.resume()
    asyncio.run(exercise())


@pytest.mark.parametrize("field,value", [("proposal_digest", "different"), ("review_digest", "different"),
                                         ("review_id", "different")])
def test_changed_review_refuses_resume_without_new_model_or_child(field, value):
    async def exercise():
        ports = Ports()
        graph = factory(ports)
        await graph.start()
        ports.review.update(decision="approved", **{field: value})
        with pytest.raises(CoordinatorFailure, match="research_review_changed"):
            await graph.resume()
        assert len(ports.turns) == 3 and not ports.children
    asyncio.run(exercise())


def test_raw_graph_resume_is_not_an_approval():
    async def exercise():
        ports = Ports()
        graph = factory(ports)
        await graph.start()
        with pytest.raises(CoordinatorFailure, match="research_canonical_approval_required"):
            await graph._graph.ainvoke(Command(resume={"approved": True}), config=graph._config)
        assert not ports.children
    asyncio.run(exercise())


def test_rejection_retains_plan_and_requests_clarification_without_child():
    async def exercise():
        ports = Ports()
        graph = factory(ports)
        await graph.start()
        ports.review["decision"] = "rejected"
        result = await graph.resume()
        assert result["terminal"]["kind"] == "clarification" and not ports.children
    asyncio.run(exercise())


@pytest.mark.parametrize("mode,code", [("plain", "research_completion_unaccepted"),
                                      ("forbidden", "agent_forbidden_tool"),
                                      ("large_plan", "research_plan_invalid"),
                                      ("extra_args", "agent_malformed_tool_arguments"),
                                      ("loop", "agent_model_budget_exhausted")])
def test_unaccepted_or_out_of_policy_model_outputs_fail_before_science(mode, code):
    async def exercise():
        ports = Ports()
        with pytest.raises(CoordinatorFailure, match=code):
            await factory(ports, ResearchModel(mode=mode)).start()
        assert not ports.children and len(ports.turns) <= 4
    asyncio.run(exercise())


def test_todo_completed_cannot_complete_canonical_science():
    async def exercise():
        ports = Ports()
        result = await factory(ports, ResearchModel(mode="forged_complete")).start()
        assert result["todos"][0]["status"] == "completed"
        assert result["planning_status_authority"] == "agent_proposal"
        assert result["awaiting_review"] and not ports.children and not ports.reports
    asyncio.run(exercise())


def test_lower_tool_budget_counts_planning():
    async def exercise():
        ports = Ports()
        with pytest.raises(CoordinatorFailure, match="agent_tool_budget_exhausted"):
            await factory(ports, ctx=context(max_tool_calls=1)).start()
        assert len(ports.plans) == 1 and not ports.children
    asyncio.run(exercise())


@pytest.mark.parametrize("changed", [{"input_digest": "different"}, {"question": "Different question"},
                                    {"workspace_id": "other"}, {"max_model_turns": 3}])
def test_checkpoint_binding_is_not_reusable_under_changed_context(changed):
    async def exercise():
        ports, saver = Ports(), InMemorySaver()
        await factory(ports, saver=saver).start()
        ports.review["decision"] = "approved"
        with pytest.raises(CoordinatorFailure, match="research_checkpoint_incompatible"):
            await factory(ports, saver=saver, ctx=context(**changed)).resume()
        assert len(ports.turns) == 3 and not ports.children
    asyncio.run(exercise())


def test_revocation_on_resume_does_not_read_or_execute():
    async def exercise():
        ports = Ports()
        graph = factory(ports)
        await graph.start()
        ports.revoked = True
        with pytest.raises(CoordinatorFailure, match="research_access_revoked"):
            await graph.resume()
        assert not ports.children
    asyncio.run(exercise())


def test_child_before_checkpoint_reconciles_same_proposal_and_retains_one_job():
    async def exercise():
        ports, saver = Ports(), InMemorySaver()
        graph = factory(ports, saver=saver)
        await graph.start()
        ports.review["decision"] = "approved"
        execute = ports.execute_or_reconcile
        def lost_ack(*args):
            execute(*args)
            raise RuntimeError("controlled lost acknowledgement")
        ports.execute_or_reconcile = lost_ack
        with pytest.raises(RuntimeError, match="lost acknowledgement"):
            await graph.resume()
        assert len(ports.children) == 1
        ports.execute_or_reconcile = execute
        # B's recovery worker is responsible for safe fault reconciliation; a
        # trusted raw continuation tests ONLY the port's stable operation key.
        restored = factory(ports, saver=saver)
        result = await restored._invoke(None)
        assert result["terminal"]["kind"] == "report" and len(ports.children) == 1
        assert ports.execute_calls == [("proposal", "digest"), ("proposal", "digest")]
    asyncio.run(exercise())


def test_reporting_refuses_fabricated_scientific_claim_after_real_child():
    async def exercise():
        ports = Ports()
        graph = factory(ports, ResearchModel(mode="bad_claim"))
        await graph.start()
        ports.review["decision"] = "approved"
        with pytest.raises(CoordinatorFailure, match="explanation_unsupported_claim"):
            await graph.resume()
        assert len(ports.children) == 1 and not ports.reports
    asyncio.run(exercise())


class RevisePlanModel(ResearchModel):
    """An explicitly admitted next action reads retained evidence then revises its plan."""
    def _generate(self, messages, **kwargs):
        from langchain_core.messages import HumanMessage
        start = max(i for i, m in enumerate(messages) if isinstance(m, HumanMessage))
        observed = [m for m in messages[start:] if isinstance(m, ToolMessage)]
        earlier = [m for m in messages[:start] if isinstance(m, ToolMessage) and m.name == "run_scientific_operation"]
        assert earlier and json.loads(earlier[-1].content)["evidence"]["id"] == "fact"
        if not observed:
            name, args = "write_todos", {"todos": [
                {"content": "Investigate reviewed measurements", "status": "completed"},
                {"content": "Review useful next measurement", "status": "in_progress"}]}
        else:
            name, args = "request_clarification", {"fields": ["feasible_times", "hard_allowance"],
                                                   "question": "What times and hard allowance are feasible?"}
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="", tool_calls=[{
            "id": f"next-action-{len(observed)}", "name": name, "args": args, "type": "tool_call"}]))])


def test_explicit_new_action_keeps_evidence_and_revises_plan_without_resetting_session_admission():
    async def exercise():
        ports, saver = Ports(), InMemorySaver()
        first = factory(ports, saver=saver)
        await first.start()
        with pytest.raises(CoordinatorFailure, match="research_previous_action_not_finished"):
            await factory(ports, saver=saver, ctx=context(action_id="second")).advance()
        ports.review["decision"] = "approved"
        await first.resume()
        second = factory(ports, model=RevisePlanModel(), saver=saver, ctx=context(action_id="second"))
        result = await second.advance()
        assert result["terminal"]["kind"] == "clarification"
        assert result["todos"][0]["status"] == "completed" and len(ports.children) == 1
        assert len(ports.turns) == 6 and ports.turns[-2:] == [("second", 1), ("second", 2)]
        with pytest.raises(CoordinatorFailure, match="research_previous_action_not_finished"):
            await second.advance()
        with pytest.raises(CoordinatorFailure, match="research_checkpoint_incompatible"):
            await factory(ports, saver=saver, ctx=context(action_id="third", research_session_id="other")).advance()
    asyncio.run(exercise())


def test_existing_controlled_coordinator_rejects_metered_adapter_including_local_subclasses():
    from bean_api.coordinator import _require_controlled_model
    from bean_api.gemini_chat_model import GeminiChatModel
    from test_gemini_chat_model import Context, Gateway
    class LocalAdapterSubclass(GeminiChatModel):
        pass
    for cls in (GeminiChatModel, LocalAdapterSubclass):
        with pytest.raises(CoordinatorFailure, match="provider_dispatch_disabled"):
            _require_controlled_model(cls(gateway=Gateway(), context=Context()))


def test_backend_admitted_approval_action_resumes_same_plan_with_explicit_new_counters():
    async def exercise():
        ports, saver = Ports(), InMemorySaver()
        await factory(ports, saver=saver).start()
        ports.review["decision"] = "approved"
        approved = factory(ports, saver=saver, ctx=context(action_id="approved-action"))
        result = await approved.resume(new_action=True)
        assert result["terminal"]["kind"] == "report" and len(ports.children) == 1
        assert ports.turns == [("action", 1), ("action", 2), ("action", 3), ("approved-action", 1)]
        assert len(ports.tool_admissions) == 4
    asyncio.run(exercise())


@pytest.mark.parametrize("substitute", [False, True])
def test_pending_child_pauses_without_model_or_reservation_reset_and_binds_job_identity(substitute):
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
            elif substitute:
                result["job_id"] = "wrong-job"
            return result
        ports.execute_or_reconcile = queued
        waiting = await first.resume()
        assert waiting["awaiting_child"] and not waiting["awaiting_review"]
        assert waiting["interrupts"][0]["job_id"] == "job"
        assert len(ports.turns) == 3 and len(ports.tool_admissions) == 3 and len(ports.children) == 1
        with pytest.raises(CoordinatorFailure, match="research_child_wait_cannot_renew_action"):
            await factory(ports, saver=saver, ctx=context(action_id="unwanted-new-action")).resume(new_action=True)
        pending = False
        restored = factory(ports, saver=saver)
        if substitute:
            with pytest.raises(CoordinatorFailure, match="research_child_binding_invalid"):
                await restored.resume()
            assert not ports.reports
        else:
            done = await restored.resume()
            assert done["terminal"]["kind"] == "report"
            assert len(ports.turns) == 4 and len(ports.tool_admissions) == 4 and len(ports.children) == 1
    asyncio.run(exercise())
