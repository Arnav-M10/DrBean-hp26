"""Offline schema-location diagnostics with genuine planning tools and a real ledger."""
import asyncio
from copy import deepcopy
from dataclasses import replace
import json
import socket

import pytest
from google.genai import types
from langchain.agents.middleware import TodoListMiddleware
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.utils.function_calling import convert_to_openai_tool

from bean_api.gemini_chat_gateway import GeminiChatGateway, safe_tool_validation_detail
from bean_api.gemini_chat_model import GeminiChatModel
from bean_api.providers import ProviderFailure
import test_gemini_chat_gateway as gateway_tests
from test_gemini_chat_model import response, run

admitted = gateway_tests.admitted
PRIVATE = "DRBEAN-DUMMY-private-argument-shape"
SIGNATURE = b"DRBEAN-DUMMY-opaque-signature"


@pytest.fixture(autouse=True)
def no_network_or_hosted_client(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Argument-shape regressions cannot call a provider")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr("google.genai.Client", denied)


def todo_tool():
    return next(tool for tool in TodoListMiddleware().tools if tool.name == "write_todos")


def tool_response(arguments, name="write_todos", call_id="DRBEAN-DUMMY-call"):
    raw = response(types.Part(text=PRIVATE), types.Part(function_call=types.FunctionCall(
        name=name, args=arguments, id=call_id), thought_signature=SIGNATURE))
    raw.usage_metadata = types.GenerateContentResponseUsageMetadata(
        prompt_token_count=5, candidates_token_count=2, total_token_count=7)
    return raw


def bound_model(admitted, wire, tools):
    config, ledger, context = admitted
    return GeminiChatModel(gateway=GeminiChatGateway(
        replace(config, api_key="DRBEAN-DUMMY-OFFLINE-SHAPE"), ledger, client_factory=wire.factory),
        context=context).bind_tools(tools)


def assert_failed_once(admitted, wire, failure, expected):
    _, ledger, context = admitted
    records = gateway_tests.attempts(ledger, context)
    assert len(records) == len(wire.calls) == wire.closed == 1
    record = records[0]
    assert record["id"] == failure.attempt_id and record["state"] == "failed"
    assert failure.code == "provider_malformed_tool_call" and failure.retryable is False
    assert failure.validation_detail == record["response_metadata"]["validation_detail"] == expected
    assert record["response_metadata"]["external_provider_calls"] == 0
    assert ledger.diagnostics()["remaining"]["requests"] == 2
    assert ledger.diagnostics()["remaining"]["input_tokens"] == ledger.input_token_cap - record["metadata"]["reserved_input_tokens"]
    assert ledger.diagnostics()["remaining"]["output_tokens"] == ledger.output_token_cap - record["metadata"]["reserved_output_tokens"]
    assert PRIVATE not in json.dumps(records) and PRIVATE not in str(failure)
    assert set(expected) <= {"reason", "tool_name", "schema_path", "expected_type", "observed_type"}


@pytest.mark.parametrize("arguments,path,expected_type,observed_type", [
    (None, "#", "object", "null"),
    ({"todos": PRIVATE}, "#/properties/todos", "array", "string"),
    ({"todos": {PRIVATE: PRIVATE}}, "#/properties/todos", "array", "object"),
    ({"todos": [PRIVATE]}, "#/properties/todos/items", "object", "string"),
    ({"todos": [{"content": {PRIVATE: PRIVATE}, "status": "pending"}]},
     "#/properties/todos/items/properties/content", "string", "object"),
    ({"todos": [{"content": PRIVATE, "status": 7}]},
     "#/properties/todos/items/properties/status", "string", "integer"),
])
def test_actual_todo_tool_bad_shapes_are_located_without_retaining_values(admitted, arguments, path, expected_type, observed_type):
    original = deepcopy(arguments)
    wire = gateway_tests.Wire(tool_response(arguments))
    model = bound_model(admitted, wire, [todo_tool()])
    with pytest.raises(ProviderFailure) as caught:
        run(model, "Prepare a research plan using the declared tool.")
    expected = {"reason": "wrong_argument_type", "tool_name": "write_todos", "schema_path": path,
                "expected_type": expected_type, "observed_type": observed_type}
    assert_failed_once(admitted, wire, caught.value, expected)
    assert arguments == original
    assert len(path.encode()) <= 512 and "/0" not in path


def test_valid_todo_arguments_and_signed_call_roundtrip_without_diagnostic_or_mutation(admitted):
    arguments = {"todos": [{"content": "Inspect reviewed measurements", "status": "in_progress"},
                            {"content": "Request canonical approval", "status": "pending"}]}
    original = deepcopy(arguments)
    wire = gateway_tests.Wire(tool_response(arguments), response(types.Part(text="Review is still required.")))
    model = bound_model(admitted, wire, [todo_tool()])
    first = run(model, "Prepare a plan.")
    assert first.tool_calls == [{"name": "write_todos", "args": original, "id": "DRBEAN-DUMMY-call", "type": "tool_call"}]
    restored = AIMessage.model_validate_json(first.model_dump_json())
    run(model, [HumanMessage(content="Prepare a plan."), restored,
                ToolMessage(content="Plan retained without approving science.", tool_call_id="DRBEAN-DUMMY-call", name="write_todos")])
    signed = next(part for content in wire.calls[-1]["contents"] for part in content.parts if part.function_call is not None)
    assert signed.thought_signature == SIGNATURE
    assert signed.function_call.args == original and signed.function_call.id == "DRBEAN-DUMMY-call"
    assert arguments == original
    records = gateway_tests.attempts(admitted[1], admitted[2])
    assert len(records) == len(wire.calls) == wire.closed == 2
    assert all("validation_detail" not in record["response_metadata"] for record in records)
    assert admitted[1].diagnostics()["remaining"]["requests"] == 1


@pytest.mark.parametrize("schema,arguments,path,expected_type,observed_type", [
    ({"type": "object", "properties": {"payload": {"$ref": "#/$defs/Payload"}}, "required": ["payload"],
      "$defs": {"Payload": {"type": "object", "properties": {"count": {"type": "integer"}}, "required": ["count"]}}},
     {"payload": {"count": PRIVATE}}, "#/$defs/Payload/properties/count", "integer", "string"),
    ({"type": "object", "properties": {"value": {"allOf": [{"type": "string"}, {"minLength": 1}]}}},
     {"value": {PRIVATE: PRIVATE}}, "#/properties/value/allOf/0", "string", "object"),
    ({"type": "object", "additionalProperties": {"type": "string"}},
     {PRIVATE: {PRIVATE: PRIVATE}}, "#/additionalProperties", "string", "object"),
    ({"type": "object", "properties": {"rate~/bound": {"type": "string"}}},
     {"rate~/bound": [PRIVATE]}, "#/properties/rate~0~1bound", "string", "array"),
])
def test_references_intersections_and_dynamic_keys_use_only_declared_schema_locations(
        admitted, schema, arguments, path, expected_type, observed_type):
    declaration = {"name": "inspect_scope", "description": "Inspect the reviewed scope.", "parameters": schema}
    wire = gateway_tests.Wire(tool_response(arguments, name="inspect_scope"))
    model = bound_model(admitted, wire, [declaration])
    with pytest.raises(ProviderFailure) as caught:
        run(model, "Review declared inputs.")
    assert_failed_once(admitted, wire, caught.value, {"reason": "wrong_argument_type", "tool_name": "inspect_scope",
        "schema_path": path, "expected_type": expected_type, "observed_type": observed_type})


def test_ambiguous_schema_alternatives_do_not_invent_one_expected_type(admitted):
    declaration = {"name": "inspect_scope", "description": "Inspect scope.", "parameters": {
        "type": "object", "properties": {"value": {"anyOf": [{"type": "string"}, {"type": "integer"}]}}}}
    wire = gateway_tests.Wire(tool_response({"value": {PRIVATE: PRIVATE}}, name="inspect_scope"))
    model = bound_model(admitted, wire, [declaration])
    with pytest.raises(ProviderFailure) as caught:
        run(model, "Review declared inputs.")
    assert_failed_once(admitted, wire, caught.value, {"reason": "schema_constraint", "tool_name": "inspect_scope"})


@pytest.mark.parametrize("changed", [
    {"schema_path": "#/properties/" + PRIVATE},
    {"schema_path": "#/properties/todos/items/0/properties/content"},
    {"schema_path": "#/properties/todos/items/properties/content~2"},
    {"schema_path": "#/properties/" + "a" * 513},
    {"schema_path": "#/properties/" + chr(0xD800)},
    {"schema_path": [PRIVATE]},
    {"expected_type": "integer"},
    {"expected_type": PRIVATE},
    {"observed_type": PRIVATE},
    {"observed_type": "dict"},
    {"observed_type": "string"},
    {"observed_type": {PRIVATE: PRIVATE}},
])
def test_forged_path_or_type_labels_reduce_to_generic_safe_reason(changed):
    schema = convert_to_openai_tool(todo_tool())["function"]["parameters"]
    detail = {"reason": "wrong_argument_type", "tool_name": "write_todos",
              "schema_path": "#/properties/todos/items/properties/content", "expected_type": "string", "observed_type": "object",
              "raw_arguments": PRIVATE, "provider_text": PRIVATE, **changed}
    assert safe_tool_validation_detail(detail, {"write_todos": schema}) == {
        "reason": "wrong_argument_type", "tool_name": "write_todos"}


@pytest.mark.parametrize("depth", [32, 33])
def test_schema_depth_bound_is_checked_even_for_a_known_pointer(depth):
    schema = {"type": "string"}
    for _ in range(depth):
        schema = {"type": "object", "properties": {"a": schema}}
    detail = {"reason": "wrong_argument_type", "tool_name": "inspect_scope", "schema_path": "#" + "/properties/a" * depth,
              "expected_type": "string", "observed_type": "object"}
    assert len(detail["schema_path"].encode()) < 512
    expected = detail if depth == 32 else {"reason": "wrong_argument_type", "tool_name": "inspect_scope"}
    assert safe_tool_validation_detail(detail, {"inspect_scope": schema}) == expected


@pytest.mark.parametrize("name,retained", [("a" * (512 - len("#/properties/")), True), ("é" * 256, False)])
def test_path_bound_counts_encoded_bytes_even_for_a_declared_field(name, retained):
    detail = {"reason": "wrong_argument_type", "tool_name": "inspect_scope", "schema_path": "#/properties/" + name,
              "expected_type": "string", "observed_type": "object"}
    schema = {"type": "object", "properties": {name: {"type": "string"}}}
    expected = detail if retained else {"reason": "wrong_argument_type", "tool_name": "inspect_scope"}
    assert safe_tool_validation_detail(detail, {"inspect_scope": schema}) == expected


def test_integer_is_not_reported_as_wrong_for_a_number_schema():
    detail = {"reason": "wrong_argument_type", "tool_name": "inspect_scope", "schema_path": "#/properties/value",
              "expected_type": "number", "observed_type": "integer"}
    assert safe_tool_validation_detail(detail, {"inspect_scope": {"type": "object", "properties": {"value": {"type": "number"}}}}) == {
        "reason": "wrong_argument_type", "tool_name": "inspect_scope"}


def test_malformed_unicode_diagnostic_cannot_interrupt_ledger_finalization(admitted):
    config, ledger, context = admitted
    raw = response(types.Part(text=PRIVATE))
    raw.usage_metadata = types.GenerateContentResponseUsageMetadata(prompt_token_count=5, candidates_token_count=2, total_token_count=7)
    wire = gateway_tests.Wire(raw)
    gateway = GeminiChatGateway(replace(config, api_key="DRBEAN-DUMMY-OFFLINE-SHAPE"), ledger, client_factory=wire.factory)
    schema = convert_to_openai_tool(todo_tool())["function"]["parameters"]

    def reject(_):
        failure = ProviderFailure("provider_malformed_tool_call")
        failure.validation_detail = {"reason": "wrong_argument_type", "tool_name": "write_todos",
            "schema_path": "#/properties/" + chr(0xD800), "expected_type": "string", "observed_type": "object", "text": PRIVATE}
        raise failure

    with pytest.raises(ProviderFailure) as caught:
        asyncio.run(gateway.dispatch(operation="agent", contents=[types.Content(role="user", parts=[types.Part(text="Review")])],
            context=context, validator=reject, tools=[types.Tool(function_declarations=[types.FunctionDeclaration(
                name="write_todos", parameters_json_schema=schema)])]))
    assert_failed_once(admitted, wire, caught.value, {"reason": "wrong_argument_type", "tool_name": "write_todos"})
