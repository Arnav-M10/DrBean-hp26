"""SDK-shaped fixtures exercise opt-in policy without a hosted request."""
import asyncio
from dataclasses import replace
import hashlib
import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel
from google.genai import types

from bean_api.providers import (AttemptContext, MeteredGeminiGateway, ProviderConfig,
                                ProviderFailure, SessionCallContext)


class Answer(BaseModel):
    value: str


class AdmittedLedger:
    # An isolated stand-in for Owner 2's future durable admission, NOT a second
    # production budget. Current ProviderLedger intentionally lacks this marker.
    session_accounting_version = "research-session.v1"

    def __init__(self, allocation=0):
        self.allocation, self.attempts = allocation, []

    def begin_attempt(self, context, metadata):
        if len(self.attempts) >= self.allocation:
            raise ProviderFailure("session_budget_exhausted")
        self.attempts.append({"context": context, "metadata": metadata})
        return str(len(self.attempts))

    def finish_attempt(self, attempt_id, metadata):
        self.attempts[int(attempt_id)-1]["outcome"] = metadata


def ctx(**updates):
    return SessionCallContext("actor", "workspace", "operation", "consent", "session", "action", "model", **updates)


def cfg(mode="live", **updates):
    return ProviderConfig(api_key="synthetic-unspent-secret", model="model", account_gate_passed=True,
                          account_decision_id="reviewed-account", mode=mode, **updates)


def response(usage=True, reason="STOP", text='{"value":"reviewed"}'):
    return SimpleNamespace(text=text, candidates=[SimpleNamespace(finish_reason=reason)],
        usage_metadata={"prompt_token_count": 10, "candidates_token_count": 5,
                        "thoughts_token_count": 0, "total_token_count": 15} if usage else None,
        response_id="observed-id", model_version="model-001")


class WireFixture:
    def __init__(self, responses):
        self.responses, self.constructed, self.calls, self.closed = list(responses), [], [], 0

    def factory(self, **kwargs):
        self.constructed.append(kwargs)
        return SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=self.generate), aclose=self.close))

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        result = self.responses.pop(0)
        if isinstance(result, BaseException):
            raise result
        return result

    async def close(self):
        self.closed += 1


def generate(gateway, context=None, **kwargs):
    return asyncio.run(gateway.generate("explanation", "Review the selected evidence.", Answer,
                                       context=context or ctx(), **kwargs))


@pytest.fixture(autouse=True)
def zero_sockets(monkeypatch):
    import socket
    def denied(*a, **kw):
        pytest.fail("Offline gateway test attempted network dispatch")
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)


@pytest.mark.parametrize("mode", ["disabled", "controlled", "live"])
def test_modes_without_an_allocation_cannot_construct_a_hosted_client(mode, monkeypatch):
    from google import genai
    def deny(**kwargs):
        pytest.fail("Refusal must precede hosted constructor")
    monkeypatch.setattr(genai, "Client", deny)
    gateway = MeteredGeminiGateway(cfg(mode), AdmittedLedger())
    with pytest.raises(ProviderFailure):
        generate(gateway)
    assert gateway.ledger.attempts == []
    assert gateway.capabilities()["live_qualification"] == "not_run"


def test_main_generic_ledger_cannot_be_mistaken_for_session_admission():
    ledger = SimpleNamespace(begin_attempt=lambda *a: pytest.fail("must not reserve"))
    with pytest.raises(ProviderFailure, match="provider_session_accounting_unavailable"):
        generate(MeteredGeminiGateway(cfg(), ledger))


@pytest.mark.parametrize("context", [AttemptContext("actor", "workspace", "op", "consent"),
    replace(ctx(), model="another-model"), replace(ctx(), research_session_id=""),
    replace(ctx(), selected_page_ids=("page",)), replace(ctx(), parent_action_id="parent")])
def test_missing_or_changed_accounting_context_fails_before_reservation(context):
    wire, ledger = WireFixture([response()]), AdmittedLedger(2)
    with pytest.raises(ProviderFailure):
        generate(MeteredGeminiGateway(cfg(), ledger, client_factory=wire.factory), context)
    assert not wire.calls and not wire.constructed and not ledger.attempts


def test_direct_call_reserves_once_before_transport_and_preserves_real_metadata():
    wire, ledger = WireFixture([response()]), AdmittedLedger(1)
    original = wire.generate
    async def ordered(**kwargs):
        assert len(ledger.attempts) == 1 and "outcome" not in ledger.attempts[0]
        return await original(**kwargs)
    wire.generate = ordered
    result = generate(MeteredGeminiGateway(cfg(), ledger, client_factory=wire.factory))
    assert result.value.value == "reviewed" and result.execution_mode == "live"
    # The synthetic transport, not live Gemini, supplied these local test values.
    outcome = ledger.attempts[0]["outcome"]
    assert outcome["provider_request_id"] == "observed-id"
    assert outcome["observed_model_version"] == "model-001"
    assert outcome["usage"]["total_tokens"] == 15
    assert wire.closed == len(wire.calls) == 1
    assert wire.constructed[0]["api_key"] == "nonsecret-controlled-placeholder"
    assert wire.constructed[0]["http_options"].retry_options.attempts == 1
    sent = wire.calls[0]["config"]
    assert sent.response_mime_type == "application/json" and sent.automatic_function_calling.disable
    assert "synthetic-unspent-secret" not in json.dumps(ledger.attempts)


def test_parent_specialist_and_explicit_retry_share_admission_without_refund():
    wire = WireFixture([TimeoutError("private response detail"), response()])
    ledger = AdmittedLedger(2)
    gateway = MeteredGeminiGateway(cfg(), ledger, client_factory=wire.factory)
    with pytest.raises(ProviderFailure, match="provider_timeout_unknown_outcome"):
        generate(gateway)
    assert ledger.attempts[0]["outcome"]["status"] == "unknown_outcome"
    child = replace(ctx(), parent_action_id="action", specialist_id="evidence_reviewer")
    generate(gateway, child)
    with pytest.raises(ProviderFailure, match="session_budget_exhausted"):
        generate(gateway)
    assert len(wire.calls) == len(ledger.attempts) == 2
    assert {a["context"]["research_session_id"] for a in ledger.attempts} == {"session"}
    assert {a["context"]["action_id"] for a in ledger.attempts} == {"action"}
    assert "private response detail" not in json.dumps(ledger.attempts)


def test_missing_usage_is_unknown_never_zero_cost_success():
    wire, ledger = WireFixture([response(False)]), AdmittedLedger(1)
    result = generate(MeteredGeminiGateway(cfg(), ledger, client_factory=wire.factory))
    assert result.usage is None
    assert ledger.attempts[0]["outcome"]["status"] == "unknown_outcome"
    assert ledger.attempts[0]["metadata"]["reserved_input_tokens"] > 0


@pytest.mark.parametrize("bad", [-1, 1.5, True, "10", 2**54])
def test_malformed_usage_fails_closed(bad):
    value = response()
    value.usage_metadata["prompt_token_count"] = bad
    wire, ledger = WireFixture([value]), AdmittedLedger(1)
    with pytest.raises(ProviderFailure, match="provider_usage_invalid"):
        generate(MeteredGeminiGateway(cfg(), ledger, client_factory=wire.factory))
    assert ledger.attempts[0]["outcome"]["status"] == "unknown_outcome"
    assert wire.closed == 1


@pytest.mark.parametrize("failure", [asyncio.CancelledError(), RuntimeError("private detail"), response(reason="SAFETY"), response(text='{bad')])
def test_failures_preserve_attempts_and_close_without_retries(failure):
    wire, ledger = WireFixture([failure]), AdmittedLedger(1)
    with pytest.raises((ProviderFailure, asyncio.CancelledError)):
        generate(MeteredGeminiGateway(cfg(), ledger, client_factory=wire.factory))
    assert len(wire.calls) == len(ledger.attempts) == wire.closed == 1
    assert "private detail" not in json.dumps(ledger.attempts)


def test_pdf_requires_disclosed_subset_and_bound_media_reservation():
    raw = b"%PDF authored wire fixture, not a parser test"
    digest = hashlib.sha256(raw).hexdigest()
    wire, ledger = WireFixture([response()]), AdmittedLedger(1)
    gateway = MeteredGeminiGateway(cfg(image_token_upper_bound=100), ledger, client_factory=wire.factory)
    with pytest.raises(ProviderFailure, match="provider_page_disclosure_required"):
        generate(gateway, ctx(source_digests=(digest,)), image_bytes=raw, mime_type="application/pdf")
    assert not ledger.attempts
    disclosed = ctx(source_digests=(digest,), selected_page_manifest_digest="a"*64,
                    selected_page_ids=("page1",), selected_page_subset_digest=digest)
    generate(gateway, disclosed, image_bytes=raw, mime_type="application/pdf")
    assert len(ledger.attempts) == 1
    with pytest.raises(ProviderFailure, match="provider_source_binding_mismatch"):
        generate(gateway, disclosed, image_bytes=b"changed", mime_type="application/pdf")
    assert len(wire.calls) == 1


def test_no_remote_file_or_provider_builtin_can_bypass_auxiliary_accounting():
    gateway = MeteredGeminiGateway(cfg(), AdmittedLedger(1))
    for contents, tools in [
        ([types.Content(role="user", parts=[types.Part.from_uri(file_uri="https://example.com/paper.pdf", mime_type="application/pdf")])], None),
        ([types.Content(role="user", parts=[types.Part(text="hello")])], [types.Tool(code_execution=types.ToolCodeExecution())]),
    ]:
        with pytest.raises(ProviderFailure):
            asyncio.run(gateway.dispatch(operation="agent", contents=contents, context=ctx(), validator=lambda x:x, tools=tools))
    assert not gateway.ledger.attempts


def test_page_cited_paper_proposal_traverses_the_shared_metered_gateway():
    from test_gemini_papers import retained_context, proposal
    paper = retained_context()
    wire, ledger = WireFixture([response(text=json.dumps(proposal(paper)))]), AdmittedLedger(1)
    context = ctx(source_digests=(paper["paper_sha256"],),
                  selected_page_manifest_digest=paper["page_manifest_digest"],
                  selected_page_ids=tuple(paper["selected_page_ids"]))
    gateway = MeteredGeminiGateway(cfg(), ledger, client_factory=wire.factory)
    result = asyncio.run(gateway.understand_paper(paper, context=context))
    assert result.value.review_state == "unaccepted" and result.value.scientific_eligibility == "unassessed"
    assert result.value.findings[0].candidate_exact == "26/5"
    assert result.value.omitted_page_ids == ["page-3"]
    assert len(wire.calls) == len(ledger.attempts) == 1
    sent = wire.calls[0]
    assert sent["config"].response_mime_type == "application/json"
    assert "UNSELECTED_PAGE_TEXT_MUST_NOT_BE_SENT" not in str(sent["contents"])
    assert ledger.attempts[0]["metadata"]["operation"] == "paper_understanding"


@pytest.mark.parametrize("change", ["source", "manifest", "pages"])
def test_paper_session_disclosure_mismatch_fails_before_attempt(change):
    from test_gemini_papers import retained_context
    paper = retained_context()
    context = ctx(source_digests=(paper["paper_sha256"],),
                  selected_page_manifest_digest=paper["page_manifest_digest"],
                  selected_page_ids=tuple(paper["selected_page_ids"]))
    context = replace(context, **{"source": {"source_digests": ("c"*64,)},
        "manifest": {"selected_page_manifest_digest": "c"*64}, "pages": {"selected_page_ids": ("page-1",)}}[change])
    wire, ledger = WireFixture([]), AdmittedLedger(1)
    with pytest.raises(ProviderFailure, match="provider_source_binding_mismatch"):
        asyncio.run(MeteredGeminiGateway(cfg(), ledger, client_factory=wire.factory).understand_paper(paper, context=context))
    assert not wire.calls and not ledger.attempts


def test_gateway_refuses_model_substitution_and_preserves_billed_usage():
    answer = response()
    answer.model_version = "a-different-model"
    wire, ledger = WireFixture([answer]), AdmittedLedger(1)
    with pytest.raises(ProviderFailure, match="provider_model_version_mismatch"):
        generate(MeteredGeminiGateway(cfg(), ledger, client_factory=wire.factory))
    assert ledger.attempts[0]["outcome"]["usage"]["total_tokens"] == 15
    assert wire.closed == 1


def test_default_sdk_factory_is_reached_only_after_admission(monkeypatch):
    from google import genai
    wire, ledger = WireFixture([response()]), AdmittedLedger(1)
    def sdk_stub(**kwargs):
        assert len(ledger.attempts) == 1
        return wire.factory(**kwargs)
    monkeypatch.setattr(genai, "Client", sdk_stub)
    result = generate(MeteredGeminiGateway(cfg(), ledger))
    assert result.provider_request_id == "observed-id" and result.model_version == "model-001"
    assert wire.constructed[0]["api_key"] == "synthetic-unspent-secret"
    assert wire.constructed[0]["vertexai"] is False
    assert wire.constructed[0]["http_options"].base_url == "https://generativelanguage.googleapis.com"
    assert ledger.attempts[0]["metadata"]["transport_provenance"] == "google_genai_sdk"
    assert "synthetic-unspent-secret" not in json.dumps(ledger.attempts)


def test_operation_specific_output_reservations_preserve_lower_configured_caps():
    wire, ledger = WireFixture([response(), response()]), AdmittedLedger(2)
    gateway = MeteredGeminiGateway(cfg(), ledger, client_factory=wire.factory)
    generate(gateway)
    generate(gateway, image_bytes=None)
    assert all(a["metadata"]["reserved_output_tokens"] == 768 for a in ledger.attempts)
    assert all(a["metadata"]["output_budget_profile"] == "gemini-operation-budgets.v1" for a in ledger.attempts)
    wire2, ledger2 = WireFixture([response()]), AdmittedLedger(1)
    generate(MeteredGeminiGateway(cfg(max_output_tokens=32), ledger2, client_factory=wire2.factory))
    assert ledger2.attempts[0]["metadata"]["reserved_output_tokens"] == 32


def test_explicit_controlled_mode_needs_no_key_or_account_decision():
    config = ProviderConfig(mode="controlled", model="model")
    config.check_ready()
    wire, ledger = WireFixture([response()]), AdmittedLedger(1)
    result = generate(MeteredGeminiGateway(config, ledger, client_factory=wire.factory))
    assert result.execution_mode == "controlled" and result.usage is None
    assert result.simulated_usage["total_tokens"] == 15
    assert ledger.attempts[0]["metadata"]["external_provider_calls"] == 0


@pytest.mark.parametrize("extra", ["text", "function_call", "thought_signature"])
def test_media_cannot_hide_another_payload_or_unbounded_metadata(extra):
    raw = b"admitted-image"
    wire, ledger = WireFixture([response()]), AdmittedLedger(1)
    part = types.Part.from_bytes(data=raw, mime_type="image/png")
    if extra == "text":
        part.text = "x" * 60_000
    elif extra == "function_call":
        part.function_call = types.FunctionCall(name="tool", args={"value": "x" * 60_000})
    else:
        part.thought_signature = b"x" * 60_000
    gateway = MeteredGeminiGateway(cfg(image_token_upper_bound=100), ledger, client_factory=wire.factory)
    with pytest.raises(ProviderFailure):
        asyncio.run(gateway.dispatch(operation="agent", contents=[types.Content(role="user", parts=[part])],
            context=ctx(source_digests=(hashlib.sha256(raw).hexdigest(),)), validator=lambda x:x))
    assert not wire.calls and not ledger.attempts


def test_pdf_needs_specific_server_attested_subset_digest():
    raw = b"admitted selected-page PDF"
    digest = hashlib.sha256(raw).hexdigest()
    wire, ledger = WireFixture([response()]), AdmittedLedger(1)
    context = ctx(source_digests=(digest,), selected_page_manifest_digest="a"*64, selected_page_ids=("page1",))
    gateway = MeteredGeminiGateway(cfg(image_token_upper_bound=100), ledger, client_factory=wire.factory)
    with pytest.raises(ProviderFailure, match="provider_page_subset_binding_required"):
        generate(gateway, context, image_bytes=raw, mime_type="application/pdf")
    assert not wire.calls and not ledger.attempts


def test_narrowed_paper_cannot_send_full_original_pdf_as_subset():
    from test_gemini_papers import retained_context
    paper = retained_context()
    raw = b"full original paper PDF"
    digest = hashlib.sha256(raw).hexdigest()
    paper["paper_sha256"] = digest
    context = ctx(source_digests=(digest,), selected_page_manifest_digest=paper["page_manifest_digest"],
                  selected_page_ids=tuple(paper["selected_page_ids"]), selected_page_subset_digest=digest)
    wire, ledger = WireFixture([]), AdmittedLedger(1)
    gateway = MeteredGeminiGateway(cfg(image_token_upper_bound=100), ledger, client_factory=wire.factory)
    with pytest.raises(ProviderFailure, match="provider_page_subset_binding_required"):
        asyncio.run(gateway.understand_paper(paper, context=context, subset_bytes=raw))
    assert not wire.calls and not ledger.attempts


def test_paper_response_binding_is_frozen_before_await():
    from bean_api.ai_prompts import PaperContext
    from test_gemini_papers import retained_context, proposal
    paper = PaperContext.model_validate(retained_context())
    answer = response(text=json.dumps(proposal(paper.model_dump())))
    wire, ledger = WireFixture([answer]), AdmittedLedger(1)
    original = wire.generate
    async def mutate(**kwargs):
        paper.pages.clear()
        paper.selected_page_ids.clear()
        return await original(**kwargs)
    wire.generate = mutate
    context = ctx(source_digests=(paper.paper_sha256,), selected_page_manifest_digest=paper.page_manifest_digest,
                  selected_page_ids=tuple(paper.selected_page_ids))
    result = asyncio.run(MeteredGeminiGateway(cfg(), ledger, client_factory=wire.factory).understand_paper(paper, context=context))
    assert result.value.selected_page_ids == list(context.selected_page_ids)
    assert result.value.findings[0].candidate_exact == "26/5"


def test_prompt_fingerprint_matches_actual_tool_turn_instruction():
    wire, ledger = WireFixture([response()]), AdmittedLedger(1)
    gateway = MeteredGeminiGateway(cfg(), ledger, client_factory=wire.factory)
    asyncio.run(gateway.dispatch(operation="agent", context=ctx(),
        contents=[types.Content(role="user", parts=[types.Part(text="Choose an approved tool.")])], validator=lambda x:x))
    sent = wire.calls[0]
    fingerprint = hashlib.sha256(json.dumps({
        "contents": [c.model_dump(mode="json", exclude_none=True) for c in sent["contents"]],
        "system": sent["config"].system_instruction, "schema": None, "tools": [],
    }, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()
    assert ledger.attempts[0]["metadata"]["prompt_sha256"] == fingerprint


@pytest.mark.parametrize("cancelled", [False, True])
def test_hanging_cleanup_is_bounded_and_sync_pool_is_closed(cancelled):
    wire, ledger = WireFixture([asyncio.CancelledError() if cancelled else response()]), AdmittedLedger(1)
    sync_closed = []
    async def hanging_close():
        wire.closed += 1
        await asyncio.Event().wait()
    original_factory = wire.factory
    def factory(**kwargs):
        client = original_factory(**kwargs)
        client.close = lambda: sync_closed.append(True)
        client.aio.aclose = hanging_close
        return client
    async def scenario():
        started = asyncio.get_running_loop().time()
        try:
            result = await MeteredGeminiGateway(cfg(), ledger, client_factory=factory).generate(
                "explanation", "Explain evidence.", Answer, context=ctx())
            assert not cancelled and result.value.value == "reviewed"
        except asyncio.CancelledError:
            assert cancelled
        assert asyncio.get_running_loop().time() - started < 2.0
    asyncio.run(scenario())
    assert sync_closed == [True] and wire.closed == 1 and len(wire.calls) == 1


def test_second_cancellation_does_not_abandon_owned_cleanup():
    wire, ledger = WireFixture([asyncio.CancelledError()]), AdmittedLedger(1)
    entered, release = asyncio.Event(), asyncio.Event()
    async def close():
        entered.set()
        await release.wait()
        wire.closed += 1
    wire.close = close
    async def scenario():
        task = asyncio.create_task(MeteredGeminiGateway(cfg(), ledger, client_factory=wire.factory).generate(
            "explanation", "Explain evidence.", Answer, context=ctx()))
        await entered.wait()
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(scenario())
    assert wire.closed == len(wire.calls) == 1


def test_per_call_output_cannot_raise_operation_profile():
    wire, ledger = WireFixture([]), AdmittedLedger(1)
    with pytest.raises(ProviderFailure, match="provider_budget_invalid"):
        asyncio.run(MeteredGeminiGateway(cfg(), ledger, client_factory=wire.factory).dispatch(
            operation="agent", contents=[types.Content(role="user", parts=[types.Part(text="choose")])],
            context=ctx(), validator=lambda x:x, output_tokens=513))
    assert not wire.calls and not ledger.attempts
