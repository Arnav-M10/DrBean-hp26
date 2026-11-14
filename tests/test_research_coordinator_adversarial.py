"""Author-side adversarial component checks of the actual Deep Agents factory.

Models, authority ports and checkpoint storage are controlled in-process. These
checks do not qualify B's persistence, real Counterdex, or hosted model behavior.
"""
import asyncio
import copy
import socket
from dataclasses import asdict, dataclass

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langgraph.checkpoint.memory import InMemorySaver

from bean_api.coordinator import CoordinatorFailure
from bean_api.gemini_chat_gateway import GeminiChatGateway
from bean_api.gemini_chat_model import GeminiChatModel
from bean_api.providers import ProviderConfig
from bean_api.research_coordinator import create_research_coordinator
from test_research_coordinator import Ports, context, factory


@pytest.fixture(autouse=True)
def deny_provider_and_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Adversarial component tests cannot dispatch a provider or network request")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr("google.genai.Client", denied)


class ToolScript(BaseChatModel):
    """Controlled tool requests; scientific expected outcomes are not scripted here."""

    model_name: str = "controlled-adversarial-research"
    calls: list[tuple[str, dict]]

    @property
    def _llm_type(self):
        return "controlled-adversarial"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, **kwargs):
        step = sum(isinstance(message, ToolMessage) for message in messages)
        if step >= len(self.calls):
            raise AssertionError("Unexpected extra model turn")
        name, arguments = self.calls[step]
        message = AIMessage(content="", tool_calls=[{
            "name": name, "args": copy.deepcopy(arguments),
            "id": f"adversarial-call-{step}", "type": "tool_call",
        }])
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(self, messages, **kwargs):
        return self._generate(messages, **kwargs)


@pytest.mark.parametrize("changed_field", ["review_id", "review_digest", "proposal_digest"])
def test_review_replaced_between_resume_preflight_and_tool_replay_cannot_execute(changed_field):
    class RacingPorts(Ports):
        reads = 0

        def read_review(self, proposal_id):
            self.reads += 1
            if self.reads == 3:
                # First read pauses; second is resume preflight. The third is
                # the replayed preparation's fresh read, after preflight passed.
                self.review[changed_field] = "replacement-identity"
            return super().read_review(proposal_id)

    async def exercise():
        ports = RacingPorts()
        graph = factory(ports)
        assert (await graph.start())["awaiting_review"]
        ports.review["decision"] = "approved"
        with pytest.raises(CoordinatorFailure, match="research_review_changed"):
            await graph.resume()
        assert ports.reads == 3
        assert ports.execute_calls == [] and ports.children == {} and ports.reports == []
        assert len(ports.turns) == 2
    asyncio.run(exercise())


@dataclass(frozen=True)
class ModelContext:
    actor_id: str = "actor"
    workspace_id: str = "workspace"
    operation_id: str = "operation"
    consent_id: str = "consent"
    research_session_id: str = "session"
    action_id: str = "action"
    model: str = "controlled-model"

    def checked_dict(self):
        return asdict(self)


@pytest.mark.parametrize("controlled_transport", [False, True])
def test_live_context_rejects_disabled_or_controlled_gateway_before_admission(controlled_transport):
    class NoAdmission:
        calls = 0

        def begin_attempt(self, *args):
            self.calls += 1
            raise AssertionError("Mismatched model mode must not reach admission")

    def unused_transport(**kwargs):
        raise AssertionError("Mismatched model mode must not construct a transport")

    ledger = NoAdmission()
    gateway = GeminiChatGateway(ProviderConfig(model="controlled-model"), ledger,
        client_factory=unused_transport if controlled_transport else None)
    model = GeminiChatModel(gateway=gateway, context=ModelContext())
    with pytest.raises(CoordinatorFailure, match="research_live_model_unavailable"):
        create_research_coordinator(context=context(mode="live_gemini"), ports=Ports(),
                                    model_factory=lambda: model, checkpointer=InMemorySaver())
    assert ledger.calls == 0


def test_replayed_tool_events_have_identical_keys_distinct_from_other_calls():
    async def exercise():
        ports, saver = Ports(), InMemorySaver()
        graph = factory(ports, saver=saver)
        paused = await graph.start()
        assert paused["awaiting_review"] and not ports.children
        assert not any(event.get("tool") == "run_scientific_operation" for event in ports.events)
        ports.review["decision"] = "approved"
        await factory(ports, saver=saver).resume()
        requests = [event for event in ports.events if event["type"] == "tool_requested"]
        prepares = [event for event in requests if event["tool"] == "prepare_scientific_proposal"]
        runs = [event for event in requests if event["tool"] == "run_scientific_operation"]
        assert len(prepares) == 2  # The preparation tool re-enters after human review.
        assert len(runs) == 1  # Science is requested only after that review resumes.
        assert paused["interrupts"][0]["tool_call_id"] == prepares[0]["tool_call_id"]

        def observation_key(event):
            return (event["action_id"], event["type"], event["tool_call_id"], event["arguments_digest"])

        assert observation_key(prepares[0]) == observation_key(prepares[1])
        assert prepares[0]["tool_call_id"] != runs[0]["tool_call_id"]
        assert len({observation_key(event) for event in requests}) == 4
        finished = [event for event in ports.events if event["type"] == "tool_finished"]
        assert len(finished) == len({observation_key(event) for event in finished}) == 4
        for event in requests + finished:
            assert len(event["arguments_digest"]) == 64
            assert "args" not in event and "arguments" not in event
        for name, requested in (("prepare_scientific_proposal", prepares), ("run_scientific_operation", runs)):
            completed = [event for event in finished if event["tool"] == name]
            assert len(completed) == 1
            assert completed[0]["tool_call_id"] == requested[0]["tool_call_id"]
            assert completed[0]["arguments_digest"] == requested[0]["arguments_digest"]
        assert len(ports.children) == 1
    asyncio.run(exercise())


@pytest.mark.parametrize("operation", ["proposal", "evidence", "report"])
def test_authoritative_port_refuses_other_input_even_in_same_workspace(operation):
    class ScopedPorts(Ports):
        rejected = []

        def prepare_proposal(self, kind, reference_ids):
            self.rejected.append(tuple(reference_ids))
            raise CoordinatorFailure("research_reference_out_of_scope")

        def read_evidence(self, evidence_id):
            self.rejected.append(evidence_id)
            raise CoordinatorFailure("research_reference_out_of_scope")

    calls = {
        "proposal": ("prepare_scientific_proposal", {"kind": "investigation",
                                                     "reference_ids": ["same-workspace-other-input"]}),
        "evidence": ("read_research_evidence", {"evidence_id": "same-workspace-other-evidence"}),
        "report": ("publish_research_report", {"evidence_ids": ["same-workspace-other-evidence"],
                    "text": "The evidence has a conditional scope.", "next_action": "stop"}),
    }

    async def exercise():
        ports = ScopedPorts()
        ports.rejected = []
        graph = factory(ports, ToolScript(calls=[calls[operation]]))
        with pytest.raises(CoordinatorFailure, match="research_reference_out_of_scope"):
            await graph.start()
        assert len(ports.rejected) == 1
        assert not ports.children and not ports.reports
        state = await graph._graph.aget_state(graph._config)
        assert state.values.get("research_terminal") is None
        assert not any(event["type"] == "tool_finished" for event in ports.events)
    asyncio.run(exercise())


@pytest.mark.parametrize("injected", ["outer", "todo"])
def test_unknown_todo_fields_fail_before_plan_recording(injected):
    arguments = {"todos": [{"content": "Review current scope", "status": "pending"}]}
    if injected == "outer":
        arguments["approved"] = True
    else:
        arguments["todos"][0]["approval_id"] = "forged-approval"

    async def exercise():
        ports = Ports()
        with pytest.raises(CoordinatorFailure, match="research_plan_invalid"):
            await factory(ports, ToolScript(calls=[("write_todos", arguments)])).start()
        assert not ports.plans and not ports.children and not ports.reports
    asyncio.run(exercise())


def test_cancelled_child_callback_retains_existing_job_without_report_or_false_completion():
    async def exercise():
        class CancellingPorts(Ports):
            async def execute_or_reconcile(self, *args):
                super().execute_or_reconcile(*args)
                callback_started.set()
                await asyncio.Future()

        callback_started = asyncio.Event()
        ports = CancellingPorts()
        graph = factory(ports)
        await graph.start()
        ports.review["decision"] = "approved"
        resumed = asyncio.create_task(graph.resume())
        try:
            await asyncio.wait_for(callback_started.wait(), timeout=5)
            resumed.cancel()
            with pytest.raises(asyncio.CancelledError):
                await resumed
        finally:
            if not resumed.done():
                resumed.cancel()
                await asyncio.gather(resumed, return_exceptions=True)
        assert len(ports.children) == 1 and not ports.reports
        state = await graph._graph.aget_state(graph._config)
        assert state.values.get("research_terminal") is None
        assert not any(event["type"] == "tool_finished" and event["tool"] == "run_scientific_operation"
                       for event in ports.events)
    asyncio.run(exercise())
