"""One accounted Gemini request for a general analysis, or a controlled substitute.

Live mode reuses the server's single ``ProviderConfig`` (explicit live opt-in, the
selected-model allowlist, the free-tier user assertion, input/output/timeout caps)
and the shared global ``ProviderLedger``. Exactly one reservation precedes exactly
one SDK request: no automatic retries, no fallback provider, bounded output and
minimal thinking. A timeout, cancellation or server error is an unknown outcome
and is never refunded. Controlled mode substitutes an in-process responder or a
test client; it never constructs the hosted SDK and records zero external calls.
No key, prompt, source bytes, raw exception or model reasoning is logged.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import hashlib
import json
import re
import time
from types import SimpleNamespace
from typing import Any, Callable

from pydantic import BaseModel

from ..providers import (
    LIVE_MODELS, AttemptContext, ProviderConfig, ProviderFailure, _finish_reason, _hosted_sdk_object,
    _parse_response, _request_id, classify_failure, live_usage, live_wire_schema, package_version,
    sanitize_usage, utc_now,
)
from . import limits as L
from .prompt import OUTPUT_SCHEMA_VERSION, PROMPT_VERSION


@dataclass(frozen=True)
class AnalysisEnvelope:
    prompt: str
    system_instruction: str
    schema: type[BaseModel]
    images: tuple[tuple[bytes, str], ...] = ()
    source_digests: tuple[str, ...] = ()
    sources: tuple[dict, ...] = ()   # structured view for controlled responders only


@dataclass
class AttemptTracker:
    attempt_id: str | None = None


@dataclass(frozen=True)
class TransportResult:
    value: BaseModel
    attempt_id: str
    execution_mode: str
    model: str
    usage: dict | None
    model_version: str | None = None
    provider_request_id: str | None = None
    finish_reason: str | None = None
    details: dict = field(default_factory=dict)


class _ResponderClient:
    """Minimal client used in controlled mode; it only calls the trusted local responder."""

    def __init__(self, responder: Callable[[AnalysisEnvelope], str], envelope: AnalysisEnvelope):
        self._responder, self._envelope = responder, envelope
        self.aio = SimpleNamespace(models=SimpleNamespace(generate_content=self._generate), aclose=self._close)

    async def _generate(self, **_: Any):
        text = self._responder(self._envelope)
        return SimpleNamespace(text=text, candidates=[SimpleNamespace(finish_reason="STOP")], usage_metadata=None,
                               response_id=None, model_version=None)

    async def _close(self):
        return None


class GeneralAnalysisTransport:
    adapter_version = "general-analysis-transport.v1"

    def __init__(self, config: ProviderConfig, ledger: Any, *, client_factory: Any = None,
                 responder: Callable[[AnalysisEnvelope], str] | None = None, accounting: str | None = None):
        if client_factory is not None and responder is not None:
            raise ValueError("Use either a test client factory or a controlled responder")
        self.config, self.ledger = config, ledger
        self._client_factory, self._responder = client_factory, responder  # trusted in-process seams only
        self.accounting = accounting or ("controlled_zero_spend" if responder is not None else "shared_global_ledger")

    # ------------------------------------------------------------------ status
    @property
    def mode(self) -> str:
        if self.config.mode == "live" and self._client_factory is None and self._responder is None:
            return "live"
        seam = self._client_factory or self._responder
        if self.config.mode != "live" and seam is not None and not _hosted_sdk_object(seam):
            return "controlled"
        return "disabled"

    @property
    def model(self) -> str | None:
        return self.config.model

    def capabilities(self) -> dict:
        mode, reason = self.mode, None
        if mode == "live":
            try:
                self.config.check_ready()
            except ProviderFailure as exc:
                reason = exc.code
        elif mode == "disabled":
            reason = "provider_dispatch_disabled"
        if mode != "disabled" and not self.config.model:
            reason = "provider_not_configured"
        return {"provider": "gemini" if mode == "live" else "controlled" if mode == "controlled" else "gemini",
                "execution_mode": mode, "model": self.config.model, "dispatch_enabled": reason is None,
                "unavailable_reason": reason, "accounting": self.accounting,
                "free_tier_user_asserted": bool(self.config.free_tier_user_asserted) if mode == "live" else False,
                "billing_verified": False, "live_qualification": "not_run",
                "max_input_tokens": self.config.max_input_tokens,
                "max_output_tokens": min(self.config.max_output_tokens, L.ANALYSIS_OUTPUT_TOKENS),
                "retry_policy": "none", "sdk_version": package_version("google-genai")}

    # ------------------------------------------------------------------ estimates
    def request_schema(self, schema: type[BaseModel]) -> tuple[dict, dict, str]:
        validation = schema.model_json_schema()
        wire = live_wire_schema(validation) if self.mode == "live" else validation
        return validation, wire, json.dumps(wire, separators=(",", ":"))

    def estimate(self, prompt: str, system_instruction: str, schema: type[BaseModel], image_count: int) -> tuple[int, int]:
        """Conservative reservation: one token per UTF-8 byte plus a fixed bound per image."""
        _, _, schema_json = self.request_schema(schema)
        image_bound = self.config.image_token_upper_bound or 8192
        incoming = (L.ANALYSIS_FIXED_INPUT_OVERHEAD + len((prompt + system_instruction + schema_json).encode("utf-8"))
                    + image_count * image_bound)
        return incoming, min(self.config.max_output_tokens, L.ANALYSIS_OUTPUT_TOKENS)

    # ------------------------------------------------------------------ dispatch
    async def generate(self, envelope: AnalysisEnvelope, context: AttemptContext,
                       tracker: AttemptTracker | None = None) -> TransportResult:
        mode = self.mode
        if mode == "disabled":
            raise ProviderFailure("provider_dispatch_disabled")
        live = mode == "live"
        if live:
            self.config.check_ready()
            if self.config.model not in LIVE_MODELS:
                raise ProviderFailure("provider_live_model_not_allowed")
        elif not self.config.model:
            raise ProviderFailure("provider_not_configured")
        checked = context.checked_dict()
        prompt = envelope.prompt
        if not isinstance(prompt, str) or not prompt or len(prompt.encode("utf-8")) > 192_000:
            raise ProviderFailure("provider_context_limit")
        if len(envelope.images) > L.MAX_ANALYSIS_ASSETS * L.MAX_PDF_PAGES:
            raise ProviderFailure("provider_context_limit")
        for content, mime in envelope.images:
            if mime not in ("image/png", "image/jpeg") or not content or len(content) > L.MAX_ASSET_BYTES:
                raise ProviderFailure("provider_modality_unsupported")
            if hashlib.sha256(content).hexdigest() not in context.source_digests:
                raise ProviderFailure("provider_source_binding_mismatch")
        if envelope.images and live:
            if self.config.image_token_upper_bound is None:
                raise ProviderFailure("provider_image_token_bound_required")
            _check_live_images(envelope.images)
        validation, wire, schema_json = self.request_schema(envelope.schema)
        input_reservation, output_cap = self.estimate(prompt, envelope.system_instruction, envelope.schema,
                                                      len(envelope.images))
        if input_reservation > self.config.max_input_tokens:
            raise ProviderFailure("provider_input_budget_exceeded")
        wall_cap = min(self.config.request_timeout_seconds, 60)
        metadata = {"provider": "gemini" if live else "controlled", "intended_provider": "gemini",
                    "model": self.config.model, "sdk_version": package_version("google-genai"),
                    "adapter_version": self.adapter_version, "prompt_version": PROMPT_VERSION,
                    "schema_version": OUTPUT_SCHEMA_VERSION, "operation": "general_analysis",
                    "modality": "text+image" if envelope.images else "text", "image_count": len(envelope.images),
                    "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                    "account_decision_id": self.config.account_decision_id if live else None,
                    "started_at": utc_now(), "reserved_input_tokens": input_reservation,
                    "reserved_output_tokens": output_cap, "max_requests": 1, "timeout_seconds": wall_cap,
                    "retry_policy": "none", "request_schema": "Gemini Developer API v1beta",
                    "test_transport": not live, "execution_mode": mode,
                    "usage_provenance": "provider_reported" if live else "controlled_simulation",
                    "estimate_method": "utf8_bytes_plus_fixed_image_bound.v1"}
        if live:
            metadata.update(free_tier_user_asserted=True, billing_verified=False,
                            thinking_policy="budget_zero" if self.config.model == "gemini-2.5-flash-lite" else "minimal",
                            wire_schema_policy="local_bounds.v1",
                            wire_schema_sha256=hashlib.sha256(schema_json.encode()).hexdigest(),
                            validation_schema_sha256=hashlib.sha256(
                                json.dumps(validation, separators=(",", ":")).encode()).hexdigest())
        else:
            metadata.update(external_provider_calls=0, actual_model_tokens=0)
        attempt_id = self.ledger.begin_attempt(checked, metadata)
        if tracker is not None:
            tracker.attempt_id = attempt_id
        started, client, usage, dispatched = time.monotonic(), None, None, False
        try:
            from google.genai import types
            kwargs = {"api_key": self.config.api_key if live else "nonsecret-controlled-placeholder", "vertexai": False,
                      "http_options": types.HttpOptions(api_version="v1beta",
                                                         base_url="https://generativelanguage.googleapis.com",
                                                         timeout=wall_cap * 1000,
                                                         retry_options=types.HttpRetryOptions(attempts=1))}
            if live:
                from google import genai
                client = genai.Client(**kwargs)
            elif self._responder is not None:
                client = _ResponderClient(self._responder, envelope)
            else:
                client = self._client_factory(**kwargs)
                if _hosted_sdk_object(client):
                    raise ProviderFailure("provider_dispatch_disabled")
            parts = [types.Part.from_text(text=prompt)]
            parts.extend(types.Part.from_bytes(data=content, mime_type=mime) for content, mime in envelope.images)
            request_config = types.GenerateContentConfig(
                system_instruction=envelope.system_instruction, response_mime_type="application/json",
                response_json_schema=wire, max_output_tokens=output_cap, candidate_count=1,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True))
            if live:
                request_config.thinking_config = (
                    types.ThinkingConfig(thinking_budget=0, include_thoughts=False)
                    if self.config.model == "gemini-2.5-flash-lite"
                    else types.ThinkingConfig(thinking_level="MINIMAL", include_thoughts=False))
            async with asyncio.timeout(wall_cap):
                dispatched = True
                response = await client.aio.models.generate_content(
                    model=self.config.model, contents=[types.Content(role="user", parts=parts)],
                    config=request_config)
            finish_reason = _finish_reason(response)
            usage = (live_usage if live else sanitize_usage)(getattr(response, "usage_metadata", None))
            model_version = getattr(response, "model_version", None)
            if live and model_version is not None and (
                    not isinstance(model_version, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", model_version)
                    or not (model_version == self.config.model or model_version.startswith(self.config.model + "-"))):
                raise ProviderFailure("provider_model_version_mismatch")
            if finish_reason in {"SAFETY", "RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT", "SPII"}:
                raise ProviderFailure("provider_refused")
            if finish_reason == "MAX_TOKENS":
                raise ProviderFailure("provider_output_truncated")
            if live and finish_reason != "STOP":
                raise ProviderFailure("provider_finish_reason_invalid")
            text = getattr(response, "text", None)
            if not isinstance(text, str) or not text:
                raise ProviderFailure("provider_empty_response")
            value = _parse_response(text, envelope.schema)
            if usage:
                input_used = usage["input_tokens"]
                output_used = (usage["output_tokens"] or 0) + (usage["thought_tokens"] or 0)
                if ((input_used is not None and input_used > input_reservation) or output_used > output_cap
                        or (live and (usage["total_tokens"] or 0) > input_reservation + output_cap)):
                    raise ProviderFailure("provider_usage_exceeded_reservation")
            request_id = _request_id(response)
            self.ledger.finish_attempt(attempt_id, {
                "status": "unknown_outcome" if live and usage is None else "validated", "finished_at": utc_now(),
                "duration_ms": int((time.monotonic() - started) * 1000), "usage": usage,
                "provider_request_id": request_id if live else None,
                "simulated_provider_request_id": None if live else request_id,
                "external_provider_calls": 1 if live else 0,
                "observed_model_version": model_version if live else None, "finish_reason": finish_reason,
                "validation_outcome": "schema_valid_unreviewed"})
            return TransportResult(value, attempt_id, mode, self.config.model or "", usage if live else None,
                                   model_version if live else None, request_id if live else None, finish_reason)
        except asyncio.CancelledError:
            self.ledger.finish_attempt(attempt_id, {
                "status": "unknown_outcome", "code": "provider_cancelled_unknown_outcome", "finished_at": utc_now(),
                "duration_ms": int((time.monotonic() - started) * 1000), "usage": usage,
                "external_provider_calls": int(live and dispatched)})
            raise
        except Exception as exc:
            code, retryable = (exc.code, exc.retryable) if isinstance(exc, ProviderFailure) else classify_failure(exc)
            self.ledger.finish_attempt(attempt_id, {
                "status": "unknown_outcome" if "unknown_outcome" in code else "failed", "code": code,
                "finished_at": utc_now(), "duration_ms": int((time.monotonic() - started) * 1000), "usage": usage,
                "external_provider_calls": int(live and dispatched)})
            raise ProviderFailure(code, retryable, attempt_id) from None
        finally:
            if client is not None:
                try:
                    async with asyncio.timeout(1):
                        await client.aio.aclose()
                except Exception:
                    pass  # cleanup cannot cause a hidden retry or change the recorded outcome


def _check_live_images(images: tuple[tuple[bytes, str], ...]) -> None:
    from io import BytesIO
    from PIL import Image
    for content, _ in images:
        try:
            with Image.open(BytesIO(content)) as image:
                if not (0 < image.width <= L.RENDER_MAX_SIDE_PX and 0 < image.height <= L.RENDER_MAX_SIDE_PX):
                    raise ProviderFailure("provider_image_dimensions_exceeded")
        except ProviderFailure:
            raise
        except Exception:
            raise ProviderFailure("provider_image_invalid") from None
