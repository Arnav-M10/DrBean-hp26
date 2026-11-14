"""C exploration of the research coordinator's compiled inventory (run from an app checkout's root, isolated .venv).

Controlled model and inert ports only; constructs no provider client. Usage: .venv/bin/python -I <this file>
Prints the middleware/tools deepagents handed to create_agent, the compiled ToolNode inventory, the tools bound for
one model turn, model calls versus admitted turns, and the pinned SDK's default inventory for comparison.
"""
import asyncio
import sys

sys.path.insert(0, "apps/api")
import deepagents  # noqa: E402
import deepagents.graph as sdk  # noqa: E402
from langchain_core.language_models import BaseChatModel  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.outputs import ChatGeneration, ChatResult  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402

from bean_api import research_coordinator as rc  # noqa: E402


class Probe(BaseChatModel):
    model_name: str = "c-inventory-probe"
    offered: list = []
    calls: int = 0

    @property
    def _llm_type(self):
        return "c-inventory-probe"

    def bind_tools(self, tools, **kwargs):
        self.offered.append(sorted(getattr(t, "name", None) or t["name"] for t in tools))
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.calls += 1
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content="plain"))])


class Reference(Probe):
    model_name: str = "c-sdk-reference"

    @property
    def _llm_type(self):
        return "c-sdk-reference"


class Ports:
    version = rc.PORT_VERSION

    def __init__(self):
        self.log = []

    def __getattr__(self, name):
        def call(*args, **kwargs):
            self.log.append(name)
        return call


records = []
original = sdk.create_agent


def spy(model, **kwargs):
    graph = original(model, **kwargs)
    records.append({"middleware": [f"{m.name} ({type(m).__module__}.{type(m).__qualname__})" for m in kwargs["middleware"]],
                    "explicit_tools": sorted(t.name for t in kwargs["tools"]),
                    "checkpointer": type(kwargs.get("checkpointer")).__name__, "graph": graph})
    return graph


sdk.create_agent = spy
print("deepagents", deepagents.__version__ if hasattr(deepagents, "__version__") else "?")
ctx = rc.ResearchContext("c-workspace", "c-session", "c-action", "c-thread", "c-input",
                         "Do my reviewed measurements support the claimed range?", {"input_id": "c-reviewed-input"})
model, ports = Probe(), Ports()
coordinator = rc.create_research_coordinator(context=ctx, ports=ports, model_factory=lambda: model,
                                             checkpointer=InMemorySaver())
product = records[-1]
print("product middleware:")
for item in product["middleware"]:
    print("  ", item)
print("product explicit tools:", product["explicit_tools"])
print("product checkpointer passed to create_agent:", product["checkpointer"])
print("product nodes:", list(product["graph"].get_graph().nodes))
print("product tool nodes:", [(k, sorted(n.data.tools_by_name)) for k, n in product["graph"].get_graph().nodes.items()
                              if hasattr(n.data, "tools_by_name")])
print("runtime metadata:", coordinator.runtime)
try:
    asyncio.run(coordinator.start())
except Exception as error:  # noqa: BLE001
    print("start ->", type(error).__name__, error)
print("tools bound per model turn:", model.offered)
print("model calls:", model.calls, "| admitted turns:", ports.log.count("admit_model_turn"), "| port calls:", ports.log)
deepagents.create_deep_agent(model=Reference(), tools=[])
reference = records[-1]
print("SDK default middleware:", [m.split(" ")[0] for m in reference["middleware"]])
print("SDK default tool nodes:", [(k, sorted(n.data.tools_by_name)) for k, n in reference["graph"].get_graph().nodes.items()
                                  if hasattr(n.data, "tools_by_name")])
