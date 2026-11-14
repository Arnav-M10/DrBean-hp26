"""Controlled SDK-shaped requests against an isolated real application ledger.

These are author/component checks, not hosted-model or durable-session acceptance.
"""
import asyncio
from dataclasses import asdict, dataclass
import json
import socket
from types import SimpleNamespace

import pytest
from google.genai import types
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, ToolMessage

from bean_api.gemini_chat_gateway import GeminiChatGateway
from bean_api.gemini_chat_model import build_gemini_chat_model
from bean_api.ledger import ProviderLedger
from bean_api.providers import AttemptContext, GeminiProvider, ProviderConfig, ProviderFailure
from bean_api.store import Store
from bean_api.workflow import Workflow
from test_gemini_chat_model import call, read_tool, response, run


@pytest.fixture(autouse=True)
def deny_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("External network/hosted SDK is forbidden in these controlled tests")
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket.socket, "connect_ex", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr("google.genai.Client", forbidden)


@dataclass(frozen=True)
class Context:
    actor_id: str
    workspace_id: str
    operation_id: str
    consent_id: str = "controlled-consent"
    research_session_id: str = "controlled-session"
    action_id: str = "controlled-action"
    model: str = "controlled-model"

    def checked_dict(self):
        return asdict(self)


class Wire:
    def __init__(self, *responses):
        self.responses, self.calls, self.constructions = list(responses), [], []
        self.closed = 0
        self.before_request = lambda: None

    def factory(self, **kwargs):
        self.constructions.append(kwargs)
        return SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=self.generate),
                                                  aclose=self.close))

    async def generate(self, **kwargs):
        self.before_request()
        self.calls.append(kwargs)
        raw = self.responses.pop(0)
        if isinstance(raw, BaseException):
            raise raw
        if callable(raw):
            return await raw()
        return raw

    async def close(self):
        self.closed += 1


@pytest.fixture
def admitted(tmp_path):
    store = Store(tmp_path / "offline-chat-attempts.sqlite3")
    flow = Workflow(store)
    workspace = flow.create_workspace("alice", "Controlled adapter test")
    operation = flow.begin_operation("alice", workspace["id"], "intake", "controlled-action", {})
    context = Context("alice", workspace["id"], operation["id"])
    config = ProviderConfig(api_key="nonsecret-controlled-placeholder", model=context.model,
                            account_gate_passed=True, account_decision_id="controlled-decision",
                            max_output_tokens=128)
    ledger = ProviderLedger(store, request_cap=3)
    return config, ledger, context


def attempts(ledger, context):
    return ledger.list_attempts(context.actor_id, context.workspace_id)


def test_direct_and_chat_share_existing_accounting_and_preserve_opaque_tool_history(admitted):
    config, ledger, context = admitted
    class Answer(BaseModel):
        text: str
    wire = Wire(response(types.Part(text='{"text":"unaccepted explanation"}')),
                response(call()), response(types.Part(text="Review remains required.")))
    direct = GeminiProvider(config, ledger, client_factory=wire.factory)
    gateway = GeminiChatGateway(config, ledger, client_factory=wire.factory)
    model = build_gemini_chat_model(gateway=gateway, context=context).bind_tools([read_tool()])
    wire.before_request = lambda: _assert_reserved_before_dispatch(ledger, context, len(wire.calls) + 1)
    direct_result = asyncio.run(direct.generate("explanation", "Explain.", Answer,
        context=AttemptContext(context.actor_id, context.workspace_id, context.operation_id, context.consent_id)))
    first = run(model, "Read.")
    final = run(model, [HumanMessage(content="Read."), first,
                        ToolMessage(content="result", tool_call_id="provider-call-7")])
    records = attempts(ledger, context)
    assert len(records) == len(wire.calls) == wire.closed == 3
    assert [item["metadata"]["operation"] for item in records] == ["explanation", "agent", "agent"]
    assert {direct_result.attempt_id, first.response_metadata["attempt_id"],
            final.response_metadata["attempt_id"]} == {item["id"] for item in records}
    assert all(item["response_metadata"]["external_provider_calls"] == 0 for item in records)
    assert first.usage_metadata is None and final.usage_metadata is None
    assert all(item["config"].automatic_function_calling.disable is True for item in wire.calls)
    assert all(item["http_options"].retry_options.attempts == 1 for item in wire.constructions)
    preserved = wire.calls[2]["contents"][1].parts[0]
    assert preserved.thought_signature == b"\xffopaque\x00"
    assert wire.calls[2]["contents"][2].parts[0].function_response.id == "provider-call-7"
    with pytest.raises(ProviderFailure, match="provider_budget_exhausted"):
        run(model, "Changing the conversation cannot renew the global allowance.")
    assert len(wire.calls) == len(attempts(ledger, context)) == 3


def _assert_reserved_before_dispatch(ledger, context, count):
    records = attempts(ledger, context)
    assert len(records) == count and records[-1]["state"] == "reserved"


@pytest.mark.parametrize("failure", [TimeoutError("private payload"), asyncio.CancelledError()])
def test_unknown_outcome_is_retained_without_retry_or_refund(admitted, failure):
    config, ledger, context = admitted
    wire = Wire(failure)
    model = build_gemini_chat_model(gateway=GeminiChatGateway(config, ledger, client_factory=wire.factory),
                                    context=context)
    error_type = asyncio.CancelledError if isinstance(failure, asyncio.CancelledError) else ProviderFailure
    with pytest.raises(error_type) as error:
        run(model, "Read.")
    assert "private payload" not in str(error.value)
    record = attempts(ledger, context)[0]
    assert record["state"] == "unknown_outcome"
    assert len(wire.calls) == wire.closed == 1
    assert ledger.diagnostics()["remaining"]["requests"] == 2


def test_invalid_tool_response_remains_accounted_and_private_thoughts_are_not_retained(admitted):
    config, ledger, context = admitted
    private = "PRIVATE-REASONING-MUST-NOT-BE-PERSISTED"
    wire = Wire(response(types.Part(text=private, thought=True), types.Part(text="Review.")))
    model = build_gemini_chat_model(gateway=GeminiChatGateway(config, ledger, client_factory=wire.factory),
                                    context=context)
    with pytest.raises(ProviderFailure, match="provider_response_modality_unsupported") as error:
        run(model, "Read.")
    assert private not in str(error.value) and private not in json.dumps(attempts(ledger, context))
    assert len(wire.calls) == len(attempts(ledger, context)) == wire.closed == 1


def test_no_factory_and_live_without_session_admission_refuse_before_sdk_or_reservation(admitted):
    config, ledger, context = admitted
    gateway = GeminiChatGateway(config, ledger)
    with pytest.raises(ProviderFailure, match="provider_dispatch_disabled"):
        run(build_gemini_chat_model(gateway=gateway, context=context), "Read.")
    live_config = ProviderConfig(mode="live", model="gemini-2.5-flash-lite")
    gateway = GeminiChatGateway(live_config, ledger)
    assert gateway.capabilities()["unavailable_reason"] == "provider_session_accounting_unavailable"
    with pytest.raises(ProviderFailure, match="provider_session_accounting_unavailable"):
        run(build_gemini_chat_model(gateway=gateway, context=context), "Read.")
    assert attempts(ledger, context) == []


def test_live_rejects_test_transport_override_before_admission(admitted):
    _, ledger, context = admitted
    wire = Wire()
    gateway = GeminiChatGateway(ProviderConfig(mode="live", model=context.model), ledger,
                                client_factory=wire.factory)
    with pytest.raises(ProviderFailure, match="provider_live_transport_override_forbidden"):
        run(build_gemini_chat_model(gateway=gateway, context=context), "Read.")
    assert attempts(ledger, context) == [] and wire.calls == []


def test_hosted_class_cannot_be_injected_into_controlled_lane(admitted):
    config, ledger, context = admitted
    class Hosted:
        __module__ = "google.genai.client"
    gateway = GeminiChatGateway(config, ledger, client_factory=Hosted)
    with pytest.raises(ProviderFailure, match="provider_dispatch_disabled"):
        run(build_gemini_chat_model(gateway=gateway, context=context), "Read.")
    assert attempts(ledger, context) == []


@pytest.mark.parametrize("mutation", [{"actor_id": "mallory"}, {"model": "different-model"},
                                    {"research_session_id": ""}])
def test_invalid_or_foreign_context_never_constructs_transport(admitted, mutation):
    config, ledger, context = admitted
    changed = Context(**{**asdict(context), **mutation})
    wire = Wire()
    gateway = GeminiChatGateway(config, ledger, client_factory=wire.factory)
    with pytest.raises(ProviderFailure):
        run(build_gemini_chat_model(gateway=gateway, context=changed), "Read.")
    assert wire.constructions == [] and attempts(ledger, context) == []


def test_mutated_context_cannot_change_a_bound_model_action(admitted):
    config, ledger, context = admitted
    identity = context.checked_dict()
    mutable_context = SimpleNamespace(checked_dict=lambda: dict(identity))
    wire = Wire()
    gateway = GeminiChatGateway(config, ledger, client_factory=wire.factory)
    model = build_gemini_chat_model(gateway=gateway, context=mutable_context)
    identity["action_id"] = "replacement-action"
    with pytest.raises(ProviderFailure, match="provider_context_changed"):
        run(model, "Read.")
    assert wire.constructions == [] and attempts(ledger, context) == []
    with pytest.raises(AttributeError):
        gateway.config = ProviderConfig(model="replacement-model")


def test_equivalent_context_key_order_keeps_the_same_bound_identity(admitted):
    config, ledger, context = admitted
    identity = context.checked_dict()
    mutable_context = SimpleNamespace(checked_dict=lambda: dict(identity))
    wire = Wire(response(types.Part(text="Review.")))
    model = build_gemini_chat_model(gateway=GeminiChatGateway(config, ledger, client_factory=wire.factory),
                                    context=mutable_context)
    identity = dict(reversed(list(identity.items())))
    assert run(model, "Read.").content == "Review."
    assert len(wire.calls) == 1


def test_full_tool_and_system_bytes_are_reserved_before_dispatch(admitted):
    config, ledger, context = admitted
    wire = Wire(response(types.Part(text="Review.")))
    gateway = GeminiChatGateway(config, ledger, client_factory=wire.factory)
    model = build_gemini_chat_model(gateway=gateway, context=context).bind_tools([read_tool()])
    run(model, "Read.")
    record = attempts(ledger, context)[0]
    wire_content = wire.calls[0]
    count = len(json.dumps([item.model_dump(mode="json", exclude_none=True)
                           for item in wire_content["contents"]]).encode())
    tools_count = len(wire_content["config"].tools[0].model_dump_json().encode())
    assert record["metadata"]["reserved_input_tokens"] > count + tools_count
    assert record["metadata"]["reserved_output_tokens"] == config.max_output_tokens


def test_explicit_non_thought_marker_survives_a_real_gateway_roundtrip(admitted):
    config, ledger, context = admitted
    initial = call().model_copy(update={"thought": False})
    wire = Wire(response(initial), response(types.Part(text="Review.")))
    model = build_gemini_chat_model(gateway=GeminiChatGateway(config, ledger, client_factory=wire.factory),
                                    context=context).bind_tools([read_tool()])
    first = run(model, "Read.")
    run(model, [HumanMessage(content="Read."), first,
                ToolMessage(content="result", tool_call_id="provider-call-7")])
    assert len(wire.calls) == 2
    assert wire.calls[1]["contents"][1].parts[0].thought is False


def test_finish_failure_is_not_retried_or_reconciled_with_a_different_outcome(admitted):
    config, ledger, context = admitted
    finishes = []
    class BrokenFinalization:
        def begin_attempt(self, *args):
            return ledger.begin_attempt(*args)
        def finish_attempt(self, *args):
            finishes.append(args)
            raise RuntimeError("write unavailable")
    wire = Wire(response(types.Part(text="Review.")))
    gateway = GeminiChatGateway(config, BrokenFinalization(), client_factory=wire.factory)
    with pytest.raises(ProviderFailure):
        run(build_gemini_chat_model(gateway=gateway, context=context), "Read.")
    assert len(finishes) == len(wire.calls) == 1
    assert attempts(ledger, context)[0]["state"] == "reserved"


def test_actual_pinned_deep_agent_executes_planning_and_scoped_tool_through_single_gateway(admitted):
    from deepagents import create_deep_agent, HarnessProfile, GeneralPurposeSubagentProfile, register_harness_profile
    from deepagents.backends import StateBackend
    from langchain.agents.middleware import AgentMiddleware, TodoListMiddleware
    from langchain.tools import ToolRuntime
    from langchain_core.tools import StructuredTool

    config, ledger, context = admitted
    todos = [{"content": "Inspect reviewed evidence before proposing science", "status": "in_progress"}]
    wire = Wire(response(call(name="write_todos", args={"todos": todos}, call_id="plan-call")),
                response(call()), response(types.Part(text="Evidence inspected; human review remains required.")))
    model = build_gemini_chat_model(gateway=GeminiChatGateway(config, ledger, client_factory=wire.factory),
                                    context=context)
    injected = []
    async def read_scoped_evidence(evidence_id: str, runtime: ToolRuntime):
        """Read scoped evidence using an injected execution runtime."""
        injected.append(runtime)
        return evidence_id
    scoped_tool = StructuredTool.from_function(coroutine=read_scoped_evidence)
    class NoFilesystem(AgentMiddleware):
        @property
        def name(self):
            return "FilesystemMiddleware"
    register_harness_profile(f"bean_gemini:{config.model}", HarnessProfile(
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
        excluded_middleware=frozenset({"SummarizationMiddleware"})))
    agent = create_deep_agent(model=model, tools=[scoped_tool],
        middleware=[NoFilesystem(), TodoListMiddleware()], backend=StateBackend(), subagents=[],
        system_prompt="Plan and inspect only authorized evidence. A todo never authorizes science.",
        checkpointer=None, store=None, cache=None)
    inventories = [set(node.data.tools_by_name) for node in agent.get_graph().nodes.values()
                   if hasattr(node.data, "tools_by_name")]
    assert inventories == [{"write_todos", "read_scoped_evidence"}]
    result = asyncio.run(agent.ainvoke({"messages": [HumanMessage(content="Review my measurements.")]},
                                      config={"recursion_limit": 32}))
    assert result["todos"] == todos
    assert result["messages"][-1].content == "Evidence inspected; human review remains required."
    assert len(wire.calls) == len(attempts(ledger, context)) == 3
    assert len(injected) == 1 and isinstance(injected[0], ToolRuntime)
    assert [item.name for item in result["messages"] if isinstance(item, ToolMessage)] == [
        "write_todos", "read_scoped_evidence"]


class InertReadyConfig(ProviderConfig):
    """Simulate local readiness only; contains no credential and cannot dispatch."""
    def check_ready(self):
        return None


class InertSessionLedger:
    """Marker fixture, never an implementation or qualification of B admission."""
    session_accounting_version = "research-session.v1"
    def begin_attempt(self, *args):
        raise AssertionError("Factory-only test must never reserve or dispatch")
    def finish_attempt(self, *args):
        raise AssertionError("Factory-only test must never finalize a request")


def inert_research_factory(model, *, mode="live_gemini"):
    from langgraph.checkpoint.memory import InMemorySaver
    from bean_api.research_coordinator import PORT_VERSION, ResearchContext, create_research_coordinator
    context = ResearchContext("workspace", "session", "action", "private-thread", "input-digest",
                              "Review measurements.", {"input_id": "reviewed-input"}, mode=mode)
    return create_research_coordinator(context=context, ports=SimpleNamespace(version=PORT_VERSION),
                                      checkpointer=InMemorySaver(), model_factory=lambda: model)


def inert_research_model(**changes):
    context = Context("actor", "workspace", "operation", research_session_id="session", action_id="action")
    context = Context(**{**asdict(context), **changes})
    gateway = GeminiChatGateway(InertReadyConfig(mode="live", model=context.model), InertSessionLedger())
    return build_gemini_chat_model(gateway=gateway, context=context)


def test_live_shaped_factory_constructs_restricted_graph_without_model_or_ledger_dispatch():
    from bean_api.research_coordinator import TOOLS
    model = inert_research_model()
    coordinator = inert_research_factory(model)
    assert coordinator.runtime["mode"] == "live_gemini"
    assert coordinator.runtime["live_qualification"] == "not_run"
    inventories = [set(node.data.tools_by_name) for node in coordinator._graph.get_graph().nodes.values()
                   if hasattr(node.data, "tools_by_name")]
    assert inventories == [set(TOOLS)]
    assert not (set(TOOLS) & {"task", "execute", "read_file", "write_file"})
    assert model.gateway.config.api_key is None


@pytest.mark.parametrize("field", ["workspace_id", "research_session_id", "action_id"])
def test_factory_refuses_mismatched_live_model_context_before_dispatch(field):
    from bean_api.coordinator import CoordinatorFailure
    with pytest.raises(CoordinatorFailure, match="research_model_context_mismatch"):
        inert_research_factory(inert_research_model(**{field: "other"}))


@pytest.mark.parametrize("controlled_transport", [False, True])
def test_live_factory_cannot_relabel_disabled_or_controlled_gateway(controlled_transport):
    from bean_api.coordinator import CoordinatorFailure
    context = Context("actor", "workspace", "operation", research_session_id="session", action_id="action")
    wire = Wire()
    gateway = GeminiChatGateway(ProviderConfig(model=context.model), InertSessionLedger(),
                                client_factory=wire.factory if controlled_transport else None)
    model = build_gemini_chat_model(gateway=gateway, context=context)
    with pytest.raises(CoordinatorFailure, match="research_live_model_unavailable"):
        inert_research_factory(model)
    assert wire.constructions == []


@pytest.mark.parametrize("wrapper", ["direct", "subclass", "bind", "with_config"])
def test_controlled_factory_rejects_metered_model_and_framework_wrappers(wrapper):
    from bean_api.coordinator import CoordinatorFailure
    from bean_api.gemini_chat_model import GeminiChatModel
    model = inert_research_model()
    if wrapper == "subclass":
        class LocalSubclass(GeminiChatModel):
            pass
        model = LocalSubclass(gateway=model.gateway, context=model.context)
    elif wrapper == "bind":
        model = model.bind()
    elif wrapper == "with_config":
        model = model.with_config(tags=["controlled"])
    with pytest.raises(CoordinatorFailure, match="provider_dispatch_disabled"):
        inert_research_factory(model, mode="controlled")
