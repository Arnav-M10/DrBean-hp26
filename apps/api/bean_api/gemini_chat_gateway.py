"""One accounted Gemini request for a research coordinator model turn.

Reuses main's provider configuration, validation and durable attempt hooks. The
PR #35 dispatch contract is retained, but its older provider configuration and
paper transport are not imported. This creates no store or independent budget.
Live dispatch requires B's atomic research-session/action admission, which the
current main ledger intentionally does not advertise. Controlled transports are
trusted in-process test seams, not a sandbox or live-provider qualification.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import json
import re
import time
from typing import Any

from google.genai import types

from .ledger import LedgerBudgetExceeded
from .providers import (
    AttemptLedger, ProviderConfig, ProviderFailure, _finish_reason, _hosted_sdk_object,
    _request_id, classify_failure, live_usage, live_wire_schema, package_version,
    sanitize_usage, utc_now,
)

SESSION_ACCOUNTING_VERSION = "research-session.v1"
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")


@dataclass(frozen=True)
class GeminiExchange:
    value: Any
    attempt_id: str
    usage: dict[str, int | None] | None
    execution_mode: str
    provider_request_id: str | None
    model_version: str | None


class GeminiChatGateway:
    """Physical dispatch only; the injected ledger owns atomic authorization.

    A live ledger advertising ``session_accounting_version`` must atomically
    enforce actor/workspace/consent/session/action/allocation and current fencing
    in ``begin_attempt``. A marker is an integration contract, not a sandbox for
    an arbitrary object. Current ProviderLedger has no marker and fails closed.
    No caller should reserve this same physical request in a second layer.
    """

    def __init__(self, config: ProviderConfig, ledger: AttemptLedger, *, client_factory: Any = None):
        self._config, self._ledger = config, ledger
        self._client_factory = client_factory

    @property
    def config(self) -> ProviderConfig:
        return self._config

    @property
    def ledger(self) -> AttemptLedger:
        return self._ledger

    def _mode(self) -> str:
        if self.config.mode == "live":
            if self._client_factory is not None:
                raise ProviderFailure("provider_live_transport_override_forbidden")
            if getattr(self.ledger, "session_accounting_version", None) != SESSION_ACCOUNTING_VERSION:
                raise ProviderFailure("provider_session_accounting_unavailable")
            self.config.check_ready()
            return "live"
        if self.config.mode != "disabled":
            raise ProviderFailure("provider_mode_invalid")
        if self._client_factory is None or _hosted_sdk_object(self._client_factory):
            raise ProviderFailure("provider_dispatch_disabled")
        if not self.config.model:
            raise ProviderFailure("provider_not_configured")
        return "controlled"

    def capabilities(self) -> dict[str, Any]:
        try:
            mode, reason = self._mode(), None
        except ProviderFailure as exc:
            mode, reason = "disabled", exc.code
        return {"implemented": True, "execution_mode": mode, "model": self.config.model,
                "dispatch_enabled": reason is None, "unavailable_reason": reason,
                "session_accounting_version": getattr(self.ledger, "session_accounting_version", None),
                "retry_policy": "none", "live_qualification": "not_run", "billing_verified": False}

    def _context(self, context: Any) -> dict[str, Any]:
        try:
            checked = context.checked_dict()
            required = ("actor_id", "workspace_id", "operation_id", "consent_id",
                        "research_session_id", "action_id", "model")
            if type(checked) is not dict or any(
                not isinstance(checked.get(name), str) or not _ID.fullmatch(checked[name]) for name in required
            ):
                raise ValueError("Invalid context")
            if checked["model"] != self.config.model:
                raise ProviderFailure("provider_model_mismatch")
            # Snapshot trusted backend references; do not keep a mutable return
            # value that can change between admission and SDK dispatch.
            encoded = json.dumps(checked, allow_nan=False, separators=(",", ":"))
            if len(encoded.encode()) > 8192:
                raise ValueError("Context too large")
            return json.loads(encoded)
        except ProviderFailure:
            raise
        except (AttributeError, TypeError, ValueError, RecursionError):
            raise ProviderFailure("provider_context_invalid") from None

    async def dispatch(self, *, operation: str, contents: list, context: Any, validator: Any,
                       tools: list | None = None, system_instruction: str | None = None,
                       response_schema: dict | None = None, text_budget_bytes: int = 0,
                       output_tokens: int | None = None) -> GeminiExchange:
        mode = self._mode()
        live = mode == "live"
        checked = self._context(context)
        if operation != "agent":
            raise ProviderFailure("provider_operation_unsupported")
        if (type(self.config.max_input_tokens) is not int or not 1 <= self.config.max_input_tokens <= 64_000
                or type(self.config.max_output_tokens) is not int or not 1 <= self.config.max_output_tokens <= 16_000
                or type(self.config.request_timeout_seconds) is not int or not 1 <= self.config.request_timeout_seconds <= 60
                or type(text_budget_bytes) is not int or not 0 <= text_budget_bytes <= 48_000):
            raise ProviderFailure("provider_budget_invalid")
        cap = min(self.config.max_output_tokens, 512) if output_tokens is None else output_tokens
        if type(cap) is not int or not 1 <= cap <= min(self.config.max_output_tokens, 512):
            raise ProviderFailure("provider_budget_invalid")
        if response_schema is not None and tools:
            raise ProviderFailure("provider_output_mode_conflict")
        try:
            if type(contents) is not list or not 1 <= len(contents) <= 64 or not callable(validator):
                raise ValueError("Invalid contents")
            bounded = [types.Content.model_validate(item) for item in contents]
            for content in bounded:
                if content.role not in {"user", "model"} or not content.parts or len(content.parts) > 32:
                    raise ValueError("Invalid content")
                for part in content.parts:
                    fields = part.model_dump(exclude_none=True)
                    if (set(fields) - {"text", "function_call", "function_response", "thought_signature", "thought"}
                            or part.thought
                            or sum(getattr(part, key) is not None for key in
                                   ("text", "function_call", "function_response")) != 1):
                        raise ValueError("Unsupported part")
            typed_tools = [types.Tool.model_validate(tool) for tool in tools or []]
            if (len(typed_tools) > 16 or sum(len(tool.function_declarations or []) for tool in typed_tools) > 16
                    or any(set(tool.model_dump(exclude_none=True)) != {"function_declarations"}
                           or not tool.function_declarations for tool in typed_tools)):
                raise ValueError("Unsupported tools")
            if system_instruction is not None and (not isinstance(system_instruction, str)
                                                   or len(system_instruction.encode()) > 8_000):
                raise ValueError("Invalid system instruction")
            wire_schema = live_wire_schema(response_schema) if live and response_schema is not None else response_schema
            wire_tools = typed_tools
            if live:
                wire_tools = [types.Tool(function_declarations=[declaration.model_copy(update={
                    "parameters_json_schema": live_wire_schema(declaration.parameters_json_schema)
                }) for declaration in tool.function_declarations]) for tool in typed_tools]
            request = {"contents": [item.model_dump(mode="json", exclude_none=True) for item in bounded],
                       "system": system_instruction,
                       "tools": [item.model_dump(mode="json", exclude_none=True) for item in wire_tools],
                       "schema": wire_schema}
            encoded = json.dumps(request, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            content_size = len(json.dumps(request["contents"], ensure_ascii=False, allow_nan=False,
                                          separators=(",", ":")).encode())
            if content_size > 48_000 or len(encoded.encode()) > 128 * 1024:
                raise ValueError("Context too large")
            reservation = 1024 + len(encoded.encode()) + max(0, text_budget_bytes - content_size)
        except (TypeError, ValueError, OverflowError, RecursionError):
            raise ProviderFailure("provider_context_invalid") from None
        if reservation > self.config.max_input_tokens:
            raise ProviderFailure("provider_input_budget_exceeded")
        metadata = {"provider": "gemini" if live else "controlled", "model": self.config.model,
                    "operation": operation, "execution_mode": mode, "sdk_version": package_version("google-genai"),
                    "adapter_version": "gemini-chat-gateway.v1", "schema_version": "gemini-chat.v1",
                    "prompt_sha256": hashlib.sha256(encoded.encode()).hexdigest(), "retry_policy": "none",
                    "max_requests": 1, "reserved_input_tokens": reservation, "reserved_output_tokens": cap,
                    "external_provider_calls": 0, "timeout_seconds": self.config.request_timeout_seconds}
        if not live:
            metadata["actual_model_tokens"] = 0
        try:
            attempt_id = self.ledger.begin_attempt(checked, metadata)
        except ProviderFailure:
            raise
        except Exception as exc:
            raise ProviderFailure("provider_budget_exhausted" if isinstance(exc, LedgerBudgetExceeded)
                                  else "provider_admission_failed") from None
        if not isinstance(attempt_id, str) or not _ID.fullmatch(attempt_id):
            raise ProviderFailure("provider_admission_failed")
        client, usage, dispatched, finalization_attempted = None, None, False, False
        started = time.monotonic()
        try:
            factory = self._client_factory
            if live:
                from google import genai
                factory = genai.Client
            client = factory(api_key=self.config.api_key if live else "nonsecret-controlled-placeholder",
                             vertexai=False, http_options=types.HttpOptions(api_version="v1beta",
                                base_url="https://generativelanguage.googleapis.com",
                                timeout=self.config.request_timeout_seconds * 1000,
                                retry_options=types.HttpRetryOptions(attempts=1)))
            if not live and _hosted_sdk_object(client):
                raise ProviderFailure("provider_dispatch_disabled")
            request_config = types.GenerateContentConfig(system_instruction=system_instruction,
                max_output_tokens=cap, candidate_count=1,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
            if wire_tools:
                request_config.tools = wire_tools
            if wire_schema is not None:
                request_config.response_mime_type = "application/json"
                request_config.response_json_schema = wire_schema
            if live:
                request_config.thinking_config = (types.ThinkingConfig(thinking_budget=0, include_thoughts=False)
                    if self.config.model == "gemini-2.5-flash-lite"
                    else types.ThinkingConfig(thinking_level="MINIMAL", include_thoughts=False))
            async with asyncio.timeout(self.config.request_timeout_seconds):
                dispatched = True
                response = await client.aio.models.generate_content(
                    model=self.config.model, contents=bounded, config=request_config)
                usage = (live_usage if live else sanitize_usage)(getattr(response, "usage_metadata", None))
                reason = _finish_reason(response)
                if reason != "STOP":
                    raise ProviderFailure("provider_output_truncated" if reason == "MAX_TOKENS" else
                                          "provider_refused" if reason in {"SAFETY", "RECITATION", "BLOCKLIST",
                                          "PROHIBITED_CONTENT", "SPII"} else "provider_finish_reason_invalid")
                version = getattr(response, "model_version", None)
                if version is not None and (not isinstance(version, str) or not _ID.fullmatch(version)
                        or not (version == self.config.model or version.startswith(self.config.model + "-"))):
                    raise ProviderFailure("provider_model_version_mismatch")
                if usage and ((usage["input_tokens"] or 0) > reservation
                        or (usage["output_tokens"] or 0) + (usage["thought_tokens"] or 0) > cap
                        or (usage["total_tokens"] or 0) > reservation + cap):
                    raise ProviderFailure("provider_usage_exceeded_reservation")
                value = validator(response)
            outcome = {"status": "unknown_outcome" if live and usage is None else "validated",
                       "usage": usage if live else None, "simulated_usage": None if live else usage,
                       "provider_request_id": _request_id(response) if live else None,
                       "observed_model_version": version if live else None,
                       "finished_at": utc_now(), "duration_ms": int((time.monotonic() - started) * 1000),
                       "external_provider_calls": 1 if live else 0}
            finalization_attempted = True
            self.ledger.finish_attempt(attempt_id, outcome)
            return GeminiExchange(value, attempt_id, usage if live else None, mode,
                                  _request_id(response) if live else None, version if live else None)
        except BaseException as exc:
            code = "provider_cancelled_unknown_outcome" if isinstance(exc, asyncio.CancelledError) else (
                exc.code if isinstance(exc, ProviderFailure) else classify_failure(exc)[0])
            if not finalization_attempted:
                try:
                    finalization_attempted = True
                    self.ledger.finish_attempt(attempt_id, {
                        "status": "unknown_outcome" if dispatched and usage is None else "failed",
                        "code": code, "usage": usage if live else None, "finished_at": utc_now(),
                        "external_provider_calls": int(live and dispatched)})
                except Exception:
                    pass  # Preserve an uncertain reservation; do not retry or refund.
            if isinstance(exc, (asyncio.CancelledError, KeyboardInterrupt, SystemExit)):
                raise
            raise ProviderFailure(code, False, attempt_id) from None
        finally:
            if client is not None:
                await _close_client(client)


async def _close_client(client: Any) -> None:
    """Bound cleanup without allowing a cleanup failure to redispatch inference."""
    try:
        close = getattr(client, "close", None)
        if close is not None:
            close()
    except Exception:
        pass
    try:
        cleanup = asyncio.create_task(client.aio.aclose())
    except Exception:
        return
    def consume(task):
        try:
            task.result()
        except (Exception, asyncio.CancelledError):
            pass
    cleanup.add_done_callback(consume)
    interrupted = False
    deadline = asyncio.get_running_loop().time() + 1
    while not cleanup.done():
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            cleanup.cancel()
            break
        try:
            await asyncio.wait({cleanup}, timeout=remaining)
        except asyncio.CancelledError:
            interrupted = True
    if interrupted:
        raise asyncio.CancelledError
