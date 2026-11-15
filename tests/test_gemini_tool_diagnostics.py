"""Offline malformed-call diagnostics preserve one charged attempt and no payload."""
import json
import socket

import pytest
from google.genai import types
from pydantic import BaseModel, ConfigDict, field_validator

from bean_api.gemini_chat_gateway import GeminiChatGateway
from bean_api.gemini_chat_model import GeminiChatModel
from bean_api.gemini_tool_diagnostics import safe_validation_detail
from bean_api.providers import ProviderFailure
import test_gemini_chat_gateway as gateway_tests
import test_research_metered_application as metered_tests
from test_gemini_chat_model import Context, Gateway, read_tool, response, run

admitted = gateway_tests.admitted
metered_app = metered_tests.metered_app
PRIVATE = "DRBEAN-DUMMY-private-provider-content"


@pytest.fixture(autouse=True)
def no_network_or_hosted_client(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("Diagnostics regressions cannot contact a provider")
    monkeypatch.setattr(socket.socket, "connect", deny)
    monkeypatch.setattr(socket.socket, "connect_ex", deny)
    monkeypatch.setattr("google.genai.Client", deny)


def function_part(*, name="read_scoped_evidence", args=None, call_id="test-call", **kwargs):
    return types.Part(function_call=types.FunctionCall(name=name, args=args, id=call_id, **kwargs))


@pytest.mark.parametrize("parts,expected", [
    ([function_part(name=PRIVATE, args={"evidence_id": PRIVATE})], {"reason": "unknown_tool"}),
    ([function_part(args={})], {"reason": "missing_required", "tool_name": "read_scoped_evidence", "missing_fields": ["evidence_id"]}),
    ([function_part(args={"evidence_id": PRIVATE, PRIVATE: PRIVATE})], {"reason": "unknown_arguments", "tool_name": "read_scoped_evidence"}),
    ([function_part(args={"evidence_id": {PRIVATE: PRIVATE}})], {"reason": "wrong_argument_type", "tool_name": "read_scoped_evidence",
      "schema_path": "#/properties/evidence_id", "expected_type": "string", "observed_type": "object"}),
    ([function_part(args=None)], {"reason": "wrong_argument_type", "tool_name": "read_scoped_evidence",
      "schema_path": "#", "expected_type": "object", "observed_type": "null"}),
    ([function_part(args={"evidence_id": PRIVATE}, will_continue=True)], {"reason": "incremental_call", "tool_name": "read_scoped_evidence"}),
    ([function_part(args={"evidence_id": PRIVATE}, call_id=PRIVATE), function_part(args={"evidence_id": PRIVATE}, call_id=PRIVATE)],
     {"reason": "duplicate_id", "tool_name": "read_scoped_evidence"}),
    ([function_part(args={"evidence_id": PRIVATE}, call_id=PRIVATE * 20)], {"reason": "invalid_id", "tool_name": "read_scoped_evidence"}),
])
def test_malformed_calls_keep_safe_reason_and_one_accounted_attempt(admitted, parts, expected):
    config, ledger, context = admitted
    raw = response(types.Part(text=PRIVATE), *parts)
    raw.usage_metadata = types.GenerateContentResponseUsageMetadata(prompt_token_count=5, candidates_token_count=2,
                                                                   total_token_count=7)
    wire = gateway_tests.Wire(raw)
    model = GeminiChatModel(gateway=GeminiChatGateway(config, ledger, client_factory=wire.factory),
                            context=context).bind_tools([read_tool()])
    with pytest.raises(ProviderFailure) as caught:
        run(model, "Use the declared tool only.")
    failure = caught.value
    records = gateway_tests.attempts(ledger, context)
    assert failure.code == "provider_malformed_tool_call" and failure.retryable is False
    assert failure.validation_detail == expected
    assert len(records) == len(wire.calls) == wire.closed == 1
    assert failure.attempt_id == records[0]["id"]
    assert records[0]["state"] == "failed"
    outcome = records[0]["response_metadata"]
    assert outcome["validation_detail"] == expected
    assert outcome["code"] == "provider_malformed_tool_call" and outcome["usage"] is None
    assert outcome["external_provider_calls"] == 0  # Controlled SDK fixture, never actual Gemini.
    assert ledger.diagnostics()["remaining"]["requests"] == 2
    assert PRIVATE not in json.dumps(records) and PRIVATE not in str(failure)
    assert "args" not in outcome and "text" not in outcome


def test_strict_application_validator_failure_is_labelled_without_exception_text():
    class ScopedInput(BaseModel):
        model_config = ConfigDict(extra="forbid")
        evidence_id: str

        @field_validator("evidence_id")
        @classmethod
        def reject(cls, value):
            raise ValueError(PRIVATE)

    gateway = Gateway(response(function_part(name="ScopedInput", args={"evidence_id": PRIVATE})))
    model = GeminiChatModel(gateway=gateway, context=Context()).bind_tools([ScopedInput])
    with pytest.raises(ProviderFailure) as caught:
        run(model, "Review.")
    assert caught.value.validation_detail == {"reason": "strict_validation", "tool_name": "ScopedInput"}
    assert PRIVATE not in str(caught.value) and len(gateway.calls) == 1


def test_schema_constraint_failure_does_not_persist_unapproved_enum_value():
    declaration = {"name": "scope", "description": "Choose the supported scope.", "parameters": {
        "type": "object", "properties": {"kind": {"type": "string", "enum": ["investigation"]}},
        "required": ["kind"], "additionalProperties": False}}
    gateway = Gateway(response(function_part(name="scope", args={"kind": PRIVATE})))
    model = GeminiChatModel(gateway=gateway, context=Context()).bind_tools([declaration])
    with pytest.raises(ProviderFailure) as caught:
        run(model, "Review.")
    assert caught.value.validation_detail == {"reason": "schema_constraint", "tool_name": "scope"}
    assert PRIVATE not in str(caught.value)


def test_gateway_rechecks_detail_against_outbound_schema_and_never_retains_arbitrary_data(admitted):
    config, ledger, context = admitted
    wire = gateway_tests.Wire(response(types.Part(text=PRIVATE)))
    gateway = GeminiChatGateway(config, ledger, client_factory=wire.factory)
    unsafe = ProviderFailure("provider_malformed_tool_call")
    unsafe.validation_detail = {"reason": "missing_required", "tool_name": PRIVATE,
                                "missing_fields": [PRIVATE], "text": PRIVATE, "arguments": {PRIVATE: PRIVATE}}

    def reject(_):
        raise unsafe

    import asyncio
    with pytest.raises(ProviderFailure) as caught:
        asyncio.run(gateway.dispatch(operation="agent", contents=[types.Content(role="user", parts=[types.Part(text="Review")])],
                                    context=context, validator=reject))
    assert caught.value.validation_detail == {"reason": "missing_required"}
    assert PRIVATE not in json.dumps(gateway_tests.attempts(ledger, context))
    assert len(wire.calls) == 1


@pytest.mark.parametrize("reason", [PRIVATE, [], None])
def test_unrecognized_diagnostic_reason_is_discarded(reason):
    assert safe_validation_detail({"reason": reason, "tool_name": PRIVATE}, {}) is None


def test_missing_fields_are_schema_known_bounded_and_value_free():
    names = [f"field_{number:02}" for number in range(20)]
    declarations = {"known_tool": {"type": "object", "properties": {name: {"type": "string"} for name in names}}}
    detail = safe_validation_detail({"reason": "missing_required", "tool_name": "known_tool",
                                     "missing_fields": [*names, PRIVATE, {PRIVATE: PRIVATE}], "args": PRIVATE}, declarations)
    assert detail == {"reason": "missing_required", "tool_name": "known_tool", "missing_fields": names[:16]}
    assert len(json.dumps(detail)) < 512 and PRIVATE not in json.dumps(detail)


def test_substituted_sdk_failure_retains_observed_usage_and_single_session_charge(metered_app):
    client, service, worker, wire = metered_app
    session = metered_tests.create_session(client)
    metered_tests.consent(client, session)
    service.allocate_provider("alice", session["id"], {"physical_requests": 2, "input_tokens": 48_000,
                                                      "output_tokens": 1024, "accepted": True}, "offline-diagnostic-grant")

    async def malformed(**kwargs):
        attempts = client.app.state.ledger.list_attempts("alice", session["workspace_id"])
        assert len(attempts) == 1 and attempts[0]["state"] == "reserved"
        wire.requests.append(kwargs)
        return wire.response("request_clarification", {}, PRIVATE)

    wire.generate = malformed
    assert metered_tests.advance(client, session).status_code == 200
    assert worker.research.tick() == 1
    assert worker.research.tick() == 0
    snapshot = service.get("alice", session["id"])
    attempts = client.app.state.ledger.list_attempts("alice", session["workspace_id"])
    assert len(attempts) == len(wire.requests) == wire.closed == 1
    assert snapshot["state"] == "failed" and snapshot["action"]["error_code"] == "provider_malformed_tool_call"
    assert snapshot["children"] == []
    assert attempts[0]["response_metadata"]["validation_detail"] == {
        "reason": "missing_required", "tool_name": "request_clarification", "missing_fields": ["fields", "question"]}
    usage = snapshot["provider_usage"]
    assert usage["physical_requests"] == 1 and usage["remaining"]["physical_requests"] == 1
    assert usage["reported_input_tokens"] == 20 and usage["reported_output_tokens"] == 6 and usage["reported_total_tokens"] == 26
    assert usage["accounted_input_tokens"] == usage["reserved_input_tokens"] == attempts[0]["metadata"]["reserved_input_tokens"]
    assert usage["accounted_output_tokens"] == usage["reserved_output_tokens"] == 512
    assert usage["unresolved_attempts"] == 0 and usage["accounting_valid"] is True
    assert PRIVATE not in json.dumps(attempts)
