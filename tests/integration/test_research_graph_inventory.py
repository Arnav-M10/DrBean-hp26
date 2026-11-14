"""C (independent): the research coordinator graph's actual compiled inventory (LOOP-09 and LOOP-10, graph parts).

Frozen predicates: evaluation/coordinator/predicates.v1.json. Controlled-callbacks lane only: a C-authored
controlled chat model and inert ports under the session egress guard; no provider, no key, no science. The graph
is built through the product factory and observed three ways, independently of the factory's own self-check:

* a spy on deepagents' call to langchain's ``create_agent`` records the middleware stack, the explicit tools and the
  checkpointer the SDK received, and the compiled graph it returned;
* the compiled graph's ToolNode inventories are read from that graph;
* one controlled model turn records the tools actually bound for the model and the number of model calls.

The allowlist is the inventory A declared in docs/integration/RESEARCH_GRAPH_HANDOFF.md (PR #42 051b4d6); changing
it needs a reviewed revision of this probe. The forbidden tools and middleware are derived from the pinned SDK by
building a default deep agent, so a new SDK default cannot slip in unnoticed. Reports NOT_AVAILABLE (xfail) where
the factory is absent, as on main 299a356. Whether the actual app invokes this factory, and whether B's checkpointer
is disk-backed and survives a process restart, are integration properties probed through the routes
(test_research_session_probes.py), not here.
"""
from __future__ import annotations

import asyncio
import importlib

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import Field

pytestmark = [pytest.mark.controlled_app]

ALLOWLIST = frozenset({"write_todos", "prepare_scientific_proposal", "run_scientific_operation",
                       "read_research_evidence", "request_clarification", "publish_research_report"})
SDK_PLANNING = "langchain.agents.middleware.todo.TodoListMiddleware"
# Model-backed, delegating, memory or skill middleware: absent from the product parent unless metered and qualified.
FORBIDDEN_MIDDLEWARE = frozenset({"SummarizationMiddleware", "SubAgentMiddleware", "AsyncSubAgentMiddleware",
                                  "MemoryMiddleware", "SkillsMiddleware"})
SIDE_EFFECT_PORTS = frozenset({"prepare_proposal", "execute_or_reconcile", "clarify", "publish_report", "record_plan"})


class InventoryProbeModel(BaseChatModel):
    """Answers every turn with plain prose and records the tools bound for it. Constructs no client."""

    model_name: str = "c-inventory-probe"
    bound_tools: list = Field(default_factory=list)
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "c-inventory-probe"

    def bind_tools(self, tools, **kwargs):
        self.bound_tools.append(sorted(getattr(tool, "name", None) or tool["name"] for tool in tools))
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls += 1
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="Plain prose cannot finish."))])


class SdkReferenceModel(InventoryProbeModel):
    """A different provider/model identity, so no harness profile registered by the product applies to it."""

    model_name: str = "c-sdk-reference"

    @property
    def _llm_type(self) -> str:
        return "c-sdk-reference"


class InertPorts:
    """Admits authority and admission checks, records every call and creates nothing."""

    def __init__(self, version: str):
        self.version = version
        self.calls: list[str] = []

    def __getattr__(self, name: str):
        if name.startswith("_"):
            raise AttributeError(name)

        def port(*args, **kwargs):
            self.calls.append(name)
            return None
        return port


def factory_module():
    try:
        module = importlib.import_module("bean_api.research_coordinator")
    except ImportError:
        module = None
    if module is None or not hasattr(module, "create_research_coordinator"):
        pytest.xfail("NOT_AVAILABLE: no research coordinator factory (bean_api.research_coordinator) in this build")
    return module


@pytest.fixture
def assembled(monkeypatch):
    """Every create_agent call deepagents makes during the test, in order, with what it received and returned."""
    import deepagents.graph as sdk
    records: list[dict] = []
    original = sdk.create_agent

    def spy(model, **kwargs):
        graph = original(model, **kwargs)
        records.append({"middleware": [item.name for item in kwargs["middleware"]],
                        "middleware_types": [f"{type(item).__module__}.{type(item).__qualname__}"
                                             for item in kwargs["middleware"]],
                        "tools": sorted(getattr(tool, "name", None) or tool["name"] for tool in kwargs["tools"]),
                        "checkpointer": kwargs.get("checkpointer"), "graph": graph})
        return graph
    monkeypatch.setattr(sdk, "create_agent", spy)
    return records


def context(module):
    return module.ResearchContext(workspace_id="c-workspace", research_session_id="c-session", action_id="c-action",
                                  thread_id="c-thread", input_digest="c-input",
                                  question="Do my reviewed measurements support the claimed range?",
                                  reviewed_context={"input_id": "c-reviewed-input"})


def build(module, model, saver=None):
    from langgraph.checkpoint.memory import InMemorySaver
    ports = InertPorts(module.PORT_VERSION)
    saver = saver or InMemorySaver()
    coordinator = module.create_research_coordinator(context=context(module), ports=ports,
                                                     model_factory=lambda: model, checkpointer=saver)
    return coordinator, ports, saver


def tool_inventories(graph) -> list[frozenset]:
    return [frozenset(node.data.tools_by_name) for node in graph.get_graph().nodes.values()
            if hasattr(node.data, "tools_by_name")]


def test_compiled_parent_inventory_is_the_declared_allowlist_with_sdk_planning(assembled):
    module = factory_module()
    build(module, InventoryProbeModel())
    product = assembled[-1]
    assert tool_inventories(product["graph"]) == [ALLOWLIST]  # one tool node; no delegate graph, no task tool
    # Planning is the SDK's own TodoListMiddleware, not a look-alike tool supplied by the application.
    assert "write_todos" not in product["tools"]
    assert SDK_PLANNING in product["middleware_types"]


def test_sdk_default_tools_and_model_backed_middleware_are_excluded(assembled):
    module = factory_module()
    build(module, InventoryProbeModel())
    product = assembled[-1]
    from deepagents import create_deep_agent
    create_deep_agent(model=SdkReferenceModel(), tools=[])
    reference = assembled[-1]
    defaults = set().union(*tool_inventories(reference["graph"]))
    # The reference shows what the pinned SDK adds by default, so the exclusions below are meaningful.
    assert {"ls", "read_file", "write_file", "edit_file", "execute", "task"} <= defaults
    assert {"SummarizationMiddleware", "SubAgentMiddleware"} <= set(reference["middleware"])
    compiled = set().union(*tool_inventories(product["graph"]))
    assert not (compiled & defaults) - {"write_todos"}, sorted(compiled & defaults)
    assert not FORBIDDEN_MIDDLEWARE & set(product["middleware"]), product["middleware"]


def test_factory_requires_a_checkpointer_and_passes_the_supplied_one_through(assembled):
    module = factory_module()
    _, _, saver = build(module, InventoryProbeModel())
    assert assembled[-1]["checkpointer"] is saver  # the backend's saver, not a substitute
    constructed = []

    def model_factory():
        constructed.append(True)
        return InventoryProbeModel()
    with pytest.raises(Exception):
        module.create_research_coordinator(context=context(module), ports=InertPorts(module.PORT_VERSION),
                                           model_factory=model_factory, checkpointer=None)
    assert constructed == []  # refused before any model was constructed


def test_a_model_turn_is_offered_exactly_the_allowlist_admitted_once_and_prose_cannot_finish(assembled):
    module = factory_module()
    model = InventoryProbeModel()
    coordinator, ports, _ = build(module, model)
    with pytest.raises(Exception) as failure:
        asyncio.run(coordinator.start())
    assert "research_completion_unaccepted" in str(failure.value)  # declared in A's handoff
    assert model.bound_tools == [sorted(ALLOWLIST)]
    assert model.calls == 1 == ports.calls.count("admit_model_turn")  # no hidden model request
    assert not SIDE_EFFECT_PORTS & set(ports.calls), ports.calls
