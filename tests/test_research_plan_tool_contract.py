"""The real SDK planning tool advertises the canonical application's accepted shape."""
from copy import deepcopy
import json
from types import SimpleNamespace

from google.genai import _common, models, types
from langchain.agents.middleware import TodoListMiddleware
from langchain.tools import ToolRuntime
from langchain_core.messages import HumanMessage, ToolMessage
from pydantic import ValidationError
import pytest

from bean_api.gemini_chat_model import GeminiChatModel
from bean_api.providers import ProviderFailure, live_wire_schema
from bean_api.research_contracts import ResearchPlanStep
from test_gemini_chat_model import Context, Gateway
from test_research_coordinator import Ports, factory
from test_research_metered_application import metered_app, create_session, consent, advance

__all__ = ["metered_app"]
INVALID_PLANS = [
    {"todos": []},
    {"todos": [{"content": str(index), "status": "pending"} for index in range(13)]},
    {"todos": [{"content": "", "status": "pending"}]},
    # The canonical plan adapter and stored ResearchPlanStep cap titles at 300,
    # even though the generic coordinator's defense-in-depth check allows 500.
    {"todos": [{"content": "x" * 301, "status": "pending"}]},
    {"todos": [{"content": "x" * 501, "status": "pending"}]},
    {"todos": [{"content": "Review", "status": "pending", "approved": True}]},
    {"todos": [{"content": "Review", "status": "pending"}], "approved": True},
]


def planning_tool():
    graph = factory(Ports())
    return next(node.data.tools_by_name["write_todos"] for node in graph._graph.get_graph().nodes.values()
                if hasattr(node.data, "tools_by_name"))


def injected_runtime():
    return ToolRuntime(state={}, context=None, config={}, stream_writer=lambda value: None,
                       tool_call_id="DRBEAN-DUMMY-plan", store=None)


@pytest.mark.parametrize("arguments", INVALID_PLANS)
def test_actual_planning_schema_refuses_shapes_the_application_cannot_record(arguments):
    tool = planning_tool()
    model = GeminiChatModel(gateway=Gateway(), context=Context()).bind_tools([tool])
    with pytest.raises(ProviderFailure, match="provider_malformed_tool_call"):
        model._validate_arguments("write_todos", arguments)
    with pytest.raises(ValidationError):
        tool.args_schema.model_validate({**arguments, "runtime": injected_runtime()}, strict=True)


@pytest.mark.parametrize("count,length", [(1, 1), (12, 300)])
def test_real_sdk_function_and_runtime_injection_survive_bounded_schema(count, length):
    tool, sdk_tool = planning_tool(), TodoListMiddleware().tools[0]
    assert tool.func is sdk_tool.func and tool.coroutine is sdk_tool.coroutine
    assert "runtime" in tool._injected_args_keys
    assert set(tool.args_schema.model_fields) == {"todos", "runtime"}
    assert set(tool.tool_call_schema.model_fields) == {"todos"}
    arguments = {"todos": [{"content": str(index).ljust(length, "x"), "status": "pending"}
                           for index in range(count)]}
    original = deepcopy(arguments)
    model = GeminiChatModel(gateway=Gateway(), context=Context()).bind_tools([tool])
    model._validate_arguments("write_todos", arguments)
    runtime = injected_runtime()
    parsed = tool._parse_input({**arguments, "runtime": runtime}, runtime.tool_call_id)
    assert parsed["runtime"] is runtime
    assert parsed["todos"] == original["todos"] == arguments["todos"]
    assert all(type(todo) is dict for todo in parsed["todos"])
    schema = json.loads(model.tools_json[0])["parameters_json_schema"]
    assert schema["additionalProperties"] is False
    assert schema["properties"]["todos"]["items"]["additionalProperties"] is False
    assert schema["properties"]["todos"]["items"]["properties"]["content"]["maxLength"] == ResearchPlanStep.model_json_schema()["properties"]["title"]["maxLength"]
    declaration = json.loads(model.tools_json[0])
    wire_schema = live_wire_schema(schema)
    params = types._GenerateContentParameters(model="DRBEAN-DUMMY-model", contents=[
        types.Content(role="user", parts=[types.Part(text="Review the inputs.")])],
        config=types.GenerateContentConfig(tools=[types.Tool(function_declarations=[types.FunctionDeclaration(
            **{**declaration, "parameters_json_schema": wire_schema})])]))
    request = models._GenerateContentParameters_to_mldev(SimpleNamespace(vertexai=False), params, None, params)
    request = _common.encode_unserializable_types(_common.convert_to_dict(request))
    emitted = request["tools"][0]["functionDeclarations"][0]["parameters_json_schema"]
    assert emitted == wire_schema and "runtime" not in emitted["properties"]
    assert all(bound in emitted["properties"]["todos"]["description"] for bound in ("minItems=1", "maxItems=12"))
    raw = {"candidates": [{"finishReason": "STOP", "content": {"role": "model", "parts": [{
        "functionCall": {"name": "write_todos", "args": arguments, "id": "DRBEAN-DUMMY-plan"},
        "thoughtSignature": "RFJCRUFOLURVTU1Z"}]}}]}
    message = model._response_message(types.GenerateContentResponse.model_validate(models._GenerateContentResponse_from_mldev(raw)))
    contents, _ = model._serialize([HumanMessage(content="Review."), message,
        ToolMessage(content="Retained plan.", tool_call_id="DRBEAN-DUMMY-plan")])
    assert message.tool_calls[0]["args"] == contents[1].parts[0].function_call.args == original
    assert contents[1].parts[0].thought_signature == b"DRBEAN-DUMMY"


@pytest.mark.parametrize("arguments", INVALID_PLANS)
def test_invalid_plan_is_one_accounted_request_and_never_admitted_as_a_tool(metered_app, monkeypatch, arguments):
    client, service, worker, wire = metered_app
    session = create_session(client)
    consent(client, session)
    service.allocate_provider("alice", session["id"], {"physical_requests": 1,
        "input_tokens": 24_000, "output_tokens": 512, "accepted": True}, "offline-plan-schema-allocation")

    async def invalid_plan(**kwargs):
        wire.requests.append(kwargs)
        return wire.response("write_todos", deepcopy(arguments), "DRBEAN-DUMMY-invalid-plan")

    monkeypatch.setattr(wire, "generate", invalid_plan)
    assert advance(client, session).status_code == 200
    assert worker.tick() == 1
    current = service.get("alice", session["id"])
    assert current["state"] == "failed" and current["action"]["error_code"] == "provider_malformed_tool_call"
    assert current["plan"] is None and current["children"] == [] and current["reports"] == []
    assert current["usage"]["physical_calls"] == len(wire.requests) == wire.closed == 1
    assert current["usage"]["tool_calls"] == 0
    attempts = deepcopy(client.app.state.ledger.list_attempts("alice", session["workspace_id"]))
    assert len(attempts) == 1 and attempts[0]["state"] == "failed"
    assert worker.tick() == 0 and len(wire.requests) == 1
    assert client.app.state.ledger.list_attempts("alice", session["workspace_id"]) == attempts


def test_canonical_plan_accepts_twelve_300_character_titles_with_sdk_runtime(metered_app, monkeypatch):
    client, service, worker, wire = metered_app
    session = create_session(client)
    consent(client, session)
    service.allocate_provider("alice", session["id"], {"physical_requests": 2,
        "input_tokens": 48_000, "output_tokens": 1024, "accepted": True}, "offline-valid-plan-allocation")
    todos = [{"content": str(index).ljust(300, "x"), "status": "pending"} for index in range(12)]
    generate = wire.generate

    async def valid_plan(**kwargs):
        if not wire.requests:
            wire.requests.append(kwargs)
            return wire.response("write_todos", {"todos": deepcopy(todos)}, "DRBEAN-DUMMY-valid-plan")
        return await generate(**kwargs)

    monkeypatch.setattr(wire, "generate", valid_plan)
    assert advance(client, session).status_code == 200
    assert worker.tick() == 1
    current = service.get("alice", session["id"])
    assert current["state"] == "waiting_review" and current["pending_review"]["kind"] == "research_clarification"
    assert [step["title"] for step in current["plan"]["body"]["steps"]] == [todo["content"] for todo in todos]
    assert current["usage"]["physical_calls"] == len(wire.requests) == 2
    assert current["children"] == [] and current["reports"] == []
    assert worker.tick() == 0 and len(wire.requests) == 2
