"""Async LangChain model using the application's one metered Gemini gateway.

This module creates neither an SDK client nor a ledger. Tool binding and JSON
output retain the original gateway and immutable call context. Unsupported
message modalities and invocation overrides fail before gateway admission.
Adapted from the reviewed PR #35 adapter; transport admission remains separate.
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Sequence
from uuid import uuid4

from google.genai import types
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import BaseModel, Field

from .canonical import parse_json_strict
from .gemini_chat_gateway import safe_tool_validation_detail
from .gemini_tool_diagnostics import ToolCallValidationFailure
from .providers import ProviderFailure

_BOUND = 128 * 1024
_PARTS = "gemini_content_parts"
_CALL_IDS = "gemini_local_tool_call_ids"
_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_.:-]{0,127}\Z")


class _CancelledModelCall(Exception):
    """Bridge a pinned LangChain gather bug, never a retryable provider error."""


class _SchemaValidationError(ValueError):
    def __init__(self, reason, missing_fields=(), *, schema_path=None, expected_type=None, observed_type=None):
        self.reason, self.missing_fields = reason, tuple(missing_fields)
        self.schema_path, self.expected_type, self.observed_type = schema_path, expected_type, observed_type
        super().__init__(reason)


def _json_type(value):
    return {dict: "object", list: "array", str: "string", int: "integer", float: "number",
            bool: "boolean", type(None): "null"}.get(type(value), "non_json")


def _schema_pointer(path):
    return "#" + "".join("/" + str(part).replace("~", "~0").replace("/", "~1") for part in path)


def _json(value: Any) -> str:
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":"))
        parse_json_strict(encoded, max_bytes=_BOUND)
        return encoded
    except (TypeError, ValueError, OverflowError, RecursionError):
        raise ProviderFailure("provider_message_invalid") from None


def _text(message: BaseMessage) -> str:
    if isinstance(message.content, str):
        return message.content
    if isinstance(message.content, list) and all(
        isinstance(block, dict) and set(block) <= {"type", "text", "index"}
        and block.get("type") == "text" and isinstance(block.get("text"), str)
        for block in message.content
    ):
        return "".join(block["text"] for block in message.content)
    raise ProviderFailure("provider_message_modality_unsupported")


def _validate_schema(value: Any, schema: dict[str, Any], root: dict[str, Any] | None = None,
                     depth: int = 0, schema_path: tuple = ()) -> None:
    """Bounded JSON Schema subset for tool dictionaries; never coerce arguments.

    Pydantic tool classes additionally run their original strict validator. Other
    schema keywords are rejected at binding, rather than silently ignored.
    """
    root = root or schema
    if depth > 32:
        raise ValueError("Schema nesting exceeds the supported bound")
    if "$ref" in schema:
        ref = schema["$ref"]
        if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
            raise ValueError("Only local schema references are supported")
        target = root
        target_path = tuple(component.replace("~1", "/").replace("~0", "~") for component in ref[2:].split("/"))
        for component in target_path:
            target = target[component]
        _validate_schema(value, target, root, depth + 1, target_path)
    for keyword in ("anyOf", "oneOf"):
        if keyword in schema:
            matches = 0
            for index, choice in enumerate(schema[keyword]):
                try:
                    _validate_schema(value, choice, root, depth + 1, (*schema_path, keyword, index))
                    matches += 1
                except (ValueError, TypeError, KeyError):
                    pass
            if matches < 1 or (keyword == "oneOf" and matches != 1):
                raise ValueError("Value does not match a schema alternative")
    if "allOf" in schema:
        for index, choice in enumerate(schema["allOf"]):
            _validate_schema(value, choice, root, depth + 1, (*schema_path, "allOf", index))
    kind = schema.get("type")
    kinds = {"object": lambda: type(value) is dict, "array": lambda: type(value) is list,
             "string": lambda: type(value) is str, "integer": lambda: type(value) is int,
             "number": lambda: type(value) in (int, float), "boolean": lambda: type(value) is bool,
             "null": lambda: value is None}
    if kind is not None and (kind not in kinds or not kinds[kind]()):
        raise _SchemaValidationError("wrong_argument_type", schema_path=_schema_pointer(schema_path),
                                     expected_type=kind, observed_type=_json_type(value))
    if "enum" in schema and _json(value) not in {_json(item) for item in schema["enum"]}:
        raise ValueError("Value outside the declared enumeration")
    if "const" in schema and _json(value) != _json(schema["const"]):
        raise ValueError("Incorrect constant")
    if type(value) is dict:
        properties = schema.get("properties", {})
        missing = set(schema.get("required", ())) - value.keys()
        if missing:
            raise _SchemaValidationError("missing_required", missing)
        if not schema.get("minProperties", 0) <= len(value) <= schema.get("maxProperties", _BOUND):
            raise ValueError("Incorrect object size")
        for key, item in value.items():
            child = properties.get(key, schema.get("additionalProperties", True))
            if child is False:
                raise _SchemaValidationError("unknown_arguments")
            if isinstance(child, dict):
                child_path = (*schema_path, "properties", key) if key in properties else (*schema_path, "additionalProperties")
                _validate_schema(item, child, root, depth + 1, child_path)
    if type(value) is list:
        if not schema.get("minItems", 0) <= len(value) <= schema.get("maxItems", _BOUND):
            raise ValueError("Incorrect array size")
        for item in value:
            _validate_schema(item, schema.get("items", {}), root, depth + 1, (*schema_path, "items"))
    if type(value) is str:
        if not schema.get("minLength", 0) <= len(value) <= schema.get("maxLength", _BOUND):
            raise ValueError("Incorrect string size")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            raise ValueError("Incorrect string pattern")
    if type(value) in (int, float):
        for key, comparison in (("minimum", lambda n: value >= n), ("maximum", lambda n: value <= n),
                                ("exclusiveMinimum", lambda n: value > n),
                                ("exclusiveMaximum", lambda n: value < n)):
            if key in schema and not comparison(schema[key]):
                raise ValueError("Number outside the declared bound")


def _check_schema(schema: Any, depth: int = 0) -> None:
    allowed = {"type", "title", "description", "default", "examples", "$defs", "$ref", "properties",
               "required", "additionalProperties", "items", "enum", "const", "anyOf", "oneOf", "allOf",
               "minLength", "maxLength", "pattern", "minimum", "maximum", "exclusiveMinimum",
               "exclusiveMaximum", "minItems", "maxItems", "minProperties", "maxProperties"}
    if not isinstance(schema, dict) or depth > 32 or set(schema) - allowed:
        raise ProviderFailure("provider_schema_unsupported")
    if (schema.get("type") is not None and schema["type"] not in
            ("object", "array", "string", "integer", "number", "boolean", "null")):
        raise ProviderFailure("provider_schema_unsupported")
    if any(key in schema and not isinstance(schema[key], str) for key in ("title", "description", "pattern", "$ref")):
        raise ProviderFailure("provider_schema_unsupported")
    if "required" in schema and (not isinstance(schema["required"], list)
            or any(not isinstance(name, str) for name in schema["required"])
            or len(set(schema["required"])) != len(schema["required"])):
        raise ProviderFailure("provider_schema_unsupported")
    if any(key in schema and (type(schema[key]) is not int or schema[key] < 0)
           for key in ("minLength", "maxLength", "minItems", "maxItems", "minProperties", "maxProperties")):
        raise ProviderFailure("provider_schema_unsupported")
    if any(key in schema and type(schema[key]) not in (int, float)
           for key in ("minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum")):
        raise ProviderFailure("provider_schema_unsupported")
    for key in ("properties", "$defs"):
        if key in schema and not isinstance(schema[key], dict):
            raise ProviderFailure("provider_schema_unsupported")
        for child in schema.get(key, {}).values():
            _check_schema(child, depth + 1)
    for key in ("anyOf", "oneOf", "allOf"):
        if key in schema and (not isinstance(schema[key], list) or not schema[key]):
            raise ProviderFailure("provider_schema_unsupported")
        for child in schema.get(key, []):
            _check_schema(child, depth + 1)
    if "enum" in schema and (not isinstance(schema["enum"], list) or not schema["enum"]):
        raise ProviderFailure("provider_schema_unsupported")
    for key in ("items", "additionalProperties"):
        if isinstance(schema.get(key), dict):
            _check_schema(schema[key], depth + 1)
        elif key in schema and (key != "additionalProperties" or type(schema[key]) is not bool):
            raise ProviderFailure("provider_schema_unsupported")
    _json(schema)


class GeminiChatModel(BaseChatModel):
    """A single asynchronous, metered transport for Deep Agents model decisions.

    The gateway validates session authority; constructor fields cannot be rebound
    by ``bind``/``invoke`` kwargs. Text and explicit typed tool calls are supported;
    source/PDF modalities belong to the direct gateway extraction interface.
    """

    gateway: Any = Field(frozen=True, exclude=True, repr=False)
    context: Any = Field(frozen=True, exclude=True, repr=False)
    context_identity_json: str | None = Field(default=None, frozen=True, exclude=True, repr=False)
    model_name: str = Field(frozen=True)
    output_tokens: int | None = Field(default=None, frozen=True, strict=True, ge=1, le=16_000)
    tools_json: tuple[str, ...] = Field(default=(), frozen=True, exclude=True, repr=False)
    tool_validators: tuple[tuple[str, Any], ...] = Field(default=(), frozen=True, exclude=True, repr=False)
    response_schema_json: str | None = Field(default=None, frozen=True, exclude=True, repr=False)
    schema_type: Any = Field(default=None, frozen=True, exclude=True, repr=False)

    def __init__(self, *, gateway: Any, context: Any, output_tokens: int | None = None):
        model = getattr(getattr(gateway, "config", None), "model", None)
        if context is None or not callable(getattr(gateway, "dispatch", None)) or not isinstance(model, str) or not model:
            raise ProviderFailure("provider_context_invalid")
        identity = _json(context.checked_dict()) if callable(getattr(context, "checked_dict", None)) else None
        super().__init__(gateway=gateway, context=context, context_identity_json=identity, model_name=model,
                         output_tokens=output_tokens, disable_streaming=True, cache=False)

    @property
    def _llm_type(self) -> str:
        return "bean-metered-gemini"

    @property
    def _identifying_params(self) -> dict[str, Any]:
        return {"model_name": self.model_name, "transport": "shared_metered_gateway.v1"}

    def _get_ls_params(self, stop=None, **kwargs):
        return {"ls_provider": "bean_gemini", "ls_model_name": self.model_name, "ls_model_type": "chat"}

    def bind_tools(self, tools: Sequence[Any], *, tool_choice: str | None = None, **kwargs: Any):
        if kwargs or tool_choice not in (None, "auto") or self.response_schema_json is not None:
            raise ProviderFailure("provider_invocation_override_forbidden")
        declarations, validators, names = [], [], set()
        for tool in tools:
            try:
                declaration = convert_to_openai_tool(tool)["function"]
                name = declaration["name"]
                parameters = declaration.get("parameters", {"type": "object", "properties": {}})
                if not _NAME.fullmatch(name) or name in names or parameters.get("type") != "object":
                    raise ValueError("Invalid or duplicate tool name/schema")
                if isinstance(tool, BaseTool):
                    # LangChain's injected-argument subset can drop the original
                    # Pydantic extra=forbid config. Never let hidden runtime or
                    # authority fields re-enter through undeclared arguments.
                    parameters = {**parameters, "additionalProperties": False}
                _check_schema(parameters)
                declarations.append(_json({"name": name, "description": declaration.get("description", ""),
                                           "parameters_json_schema": parameters}))
                # Injected runtime/authority arguments belong to the executor.
                # Validate only the same public schema offered to the model.
                validator = tool.tool_call_schema if isinstance(tool, BaseTool) else tool
                if isinstance(validator, type) and issubclass(validator, BaseModel):
                    validators.append((name, validator))
                names.add(name)
            except ProviderFailure:
                raise
            except (KeyError, TypeError, ValueError):
                raise ProviderFailure("provider_schema_unsupported") from None
        return self.model_copy(update={"tools_json": tuple(declarations), "tool_validators": tuple(validators)})

    def with_structured_output(self, schema: dict[str, Any] | type, *, include_raw: bool = False, **kwargs):
        if kwargs or self.tools_json or self.response_schema_json is not None:
            raise ProviderFailure("provider_invocation_override_forbidden")
        schema_type = schema if isinstance(schema, type) and issubclass(schema, BaseModel) else None
        if schema_type is not None:
            schema = schema_type.model_json_schema()
        elif isinstance(schema, dict) and schema.get("type") == "function":
            schema = schema.get("function", {}).get("parameters")
        _check_schema(schema)
        model = self.model_copy(update={"response_schema_json": _json(schema), "schema_type": schema_type})

        def parse(message: AIMessage):
            value = parse_json_strict(message.content, max_bytes=_BOUND)
            parsed = schema_type.model_validate(value, strict=True) if schema_type else value
            return {"raw": message, "parsed": parsed, "parsing_error": None} if include_raw else parsed

        return model | RunnableLambda(parse)

    def _tool_failure(self, reason, name=None, missing_fields=(), *, schema_path=None, expected_type=None, observed_type=None):
        declarations = {value["name"]: value["parameters_json_schema"] for value in map(json.loads, self.tools_json)}
        failure = ToolCallValidationFailure(reason, declarations, tool_name=name, missing_fields=missing_fields)
        failure.validation_detail = safe_tool_validation_detail(
            {**failure.validation_detail, "schema_path": schema_path, "expected_type": expected_type,
             "observed_type": observed_type}, declarations)
        return failure

    def _validate_arguments(self, name: str, arguments: Any) -> None:
        declarations = {value["name"]: value for value in map(json.loads, self.tools_json)}
        if name not in declarations:
            raise self._tool_failure("unknown_tool")
        if type(arguments) is not dict:
            raise self._tool_failure("wrong_argument_type", name, schema_path="#", expected_type="object",
                                     observed_type=_json_type(arguments))
        try:
            _json(arguments)
            _validate_schema(arguments, declarations[name]["parameters_json_schema"])
        except _SchemaValidationError as exc:
            raise self._tool_failure(exc.reason, name, exc.missing_fields, schema_path=exc.schema_path,
                                     expected_type=exc.expected_type, observed_type=exc.observed_type) from None
        except (TypeError, ValueError, KeyError):
            raise self._tool_failure("schema_constraint", name) from None
        try:
            validator = dict(self.tool_validators).get(name)
            if validator is not None:
                validator.model_validate(arguments, strict=True)
        except (TypeError, ValueError, KeyError):
            raise self._tool_failure("strict_validation", name) from None

    def _serialize(self, messages: list[BaseMessage]) -> tuple[list[types.Content], str | None]:
        contents, system, pending, seen = [], [], {}, set()
        for message in messages:
            if isinstance(message, SystemMessage):
                if contents:
                    raise ProviderFailure("provider_message_invalid")
                system.append(_text(message))
                continue
            if isinstance(message, ToolMessage):
                call = pending.pop(message.tool_call_id, None)
                if call is None or (message.name is not None and message.name != call[0]):
                    raise ProviderFailure("provider_tool_response_mismatch")
                text = _text(message)
                try:
                    value = parse_json_strict(text, max_bytes=_BOUND)
                except ValueError:
                    value = text
                response = {"error" if message.status == "error" else "output": value}
                parts = [types.Part(function_response=types.FunctionResponse(name=call[0], id=call[1],
                                                                            response=response))]
                contents.append(types.Content(role="user", parts=parts))
                continue
            if pending:
                raise ProviderFailure("provider_tool_response_mismatch")
            if isinstance(message, HumanMessage):
                contents.append(types.Content(role="user", parts=[types.Part(text=_text(message))]))
            elif isinstance(message, AIMessage):
                if message.invalid_tool_calls:
                    raise self._tool_failure("invalid_tool_call")
                text = _text(message)
                raw = message.additional_kwargs.get(_PARTS)
                if raw is not None:
                    try:
                        parts = [types.Part.model_validate(part) for part in raw]
                        restored = self._response_message(types.GenerateContentResponse(candidates=[
                            types.Candidate(content=types.Content(role="model", parts=parts))]),
                            local_ids=message.additional_kwargs.get(_CALL_IDS))
                    except (ValueError, TypeError):
                        raise ProviderFailure("provider_message_invalid") from None
                    if restored.content != text or restored.tool_calls != message.tool_calls:
                        raise ProviderFailure("provider_message_invalid")
                else:
                    parts = [types.Part(text=text)] if text else []
                    for call in message.tool_calls:
                        self._validate_arguments(call["name"], call["args"])
                        parts.append(types.Part(function_call=types.FunctionCall(name=call["name"],
                                                        args=call["args"], id=call.get("id"))))
                function_parts = [part for part in parts if part.function_call is not None]
                for call, part in zip(message.tool_calls, function_parts, strict=True):
                    call_id = call.get("id")
                    if not isinstance(call_id, str) or not call_id or len(call_id) > 256 or call_id in seen:
                        raise self._tool_failure("duplicate_id" if isinstance(call_id, str) and call_id in seen else "invalid_id", call["name"])
                    seen.add(call_id)
                    pending[call_id] = (call["name"], part.function_call.id)
                contents.append(types.Content(role="model", parts=parts))
            else:
                raise ProviderFailure("provider_message_modality_unsupported")
        if pending or not contents:
            raise ProviderFailure("provider_tool_response_mismatch" if pending else "provider_message_invalid")
        return contents, "\n".join(system) or None

    def _response_message(self, response: Any, *, local_ids: list[str] | None = None) -> AIMessage:
        candidates = getattr(response, "candidates", None) or []
        if len(candidates) != 1 or getattr(candidates[0], "content", None) is None:
            raise ProviderFailure("provider_empty_response")
        candidate = candidates[0]
        if candidate.content.role != "model":
            raise ProviderFailure("provider_response_invalid")
        reason = getattr(candidate, "finish_reason", None)
        reason = getattr(reason, "value", reason)
        if reason is not None and reason != "STOP":
            raise ProviderFailure("provider_output_truncated" if reason == "MAX_TOKENS" else
                                  "provider_refused" if reason in {"SAFETY", "RECITATION", "BLOCKLIST",
                                  "PROHIBITED_CONTENT", "SPII"} else "provider_finish_reason_invalid")
        parts = candidate.content.parts or []
        texts, calls, ids, raw = [], [], [], []
        for part in parts:
            data = part.model_dump(mode="json", exclude_none=True)
            if (set(data) - {"text", "function_call", "thought_signature", "thought"} or part.thought
                    or sum(value is not None for value in (part.text, part.function_call)) != 1):
                raise ProviderFailure("provider_response_modality_unsupported")
            if part.text is not None:
                texts.append(part.text)
            if part.function_call is not None:
                call = part.function_call
                self._validate_arguments(call.name, call.args)
                if call.partial_args is not None or call.will_continue is not None:
                    raise self._tool_failure("incremental_call", call.name)
                call_id = call.id or (local_ids[len(calls)] if local_ids and len(local_ids) > len(calls)
                                      else "gemini-local-" + uuid4().hex)
                if not isinstance(call_id, str) or not call_id or len(call_id) > 256 or call_id in ids:
                    raise self._tool_failure("duplicate_id" if call_id in ids else "invalid_id", call.name)
                calls.append({"name": call.name, "args": call.args, "id": call_id, "type": "tool_call"})
                ids.append(call_id)
            raw.append(data)
        text = "".join(texts)
        _json(raw)
        if not text and not calls:
            raise ProviderFailure("provider_empty_response")
        if self.response_schema_json is not None:
            if calls:
                raise self._tool_failure("invalid_tool_call")
            try:
                value = parse_json_strict(text, max_bytes=_BOUND)
                _validate_schema(value, json.loads(self.response_schema_json))
                if self.schema_type is not None:
                    self.schema_type.model_validate(value, strict=True)
            except (ValueError, TypeError, KeyError):
                raise ProviderFailure("provider_malformed_output") from None
        return AIMessage(content=text, tool_calls=calls,
                         additional_kwargs={_PARTS: raw, _CALL_IDS: ids},
                         response_metadata={"finish_reason": reason})

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        raise ProviderFailure("provider_async_required")

    def generate(self, *args, **kwargs):
        # Refuse before framework callbacks/tracing can observe a sync request.
        raise ProviderFailure("provider_async_required")

    async def agenerate(self, messages, stop=None, callbacks=None, *, tags=None, metadata=None,
                        run_name=None, run_id=None, **kwargs):
        if stop is not None or kwargs:
            raise ProviderFailure("provider_invocation_override_forbidden")
        from langsmith import tracing_context
        with tracing_context(enabled=False):
            try:
                return await super().agenerate(messages, stop=stop, callbacks=callbacks, tags=tags,
                    metadata=metadata, run_name=run_name, run_id=run_id)
            except _CancelledModelCall:
                raise asyncio.CancelledError from None

    async def _agenerate_with_cache(self, *args, **kwargs):
        # langchain-core 1.8.0 gathers BaseExceptions but its completion callback
        # filters only Exception. Bridge cancellation across that callback, then
        # restore cancellation in agenerate; the gateway already recorded it.
        try:
            return await super()._agenerate_with_cache(*args, **kwargs)
        except asyncio.CancelledError:
            raise _CancelledModelCall from None

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        if stop is not None or kwargs:
            raise ProviderFailure("provider_invocation_override_forbidden")
        if self.model_name != getattr(self.gateway.config, "model", None):
            raise ProviderFailure("provider_model_mismatch")
        if self.context_identity_json is not None and _json(self.context.checked_dict()) != self.context_identity_json:
            raise ProviderFailure("provider_context_changed")
        contents, system = self._serialize(messages)
        tools = [types.Tool(function_declarations=[types.FunctionDeclaration(**json.loads(value))
                                                   for value in self.tools_json])] if self.tools_json else None
        schema = json.loads(self.response_schema_json) if self.response_schema_json is not None else None
        # The gateway separately reserves system, tool and schema bytes. Count
        # contents here, including roles/signatures, without charging them twice.
        budget = len(_json([value.model_dump(mode="json", exclude_none=True)
                            for value in contents]).encode("utf-8"))
        exchange = await self.gateway.dispatch(operation="agent", contents=contents, context=self.context,
            validator=self._response_message, tools=tools, system_instruction=system,
            response_schema=schema, text_budget_bytes=budget, output_tokens=self.output_tokens)
        message = exchange.value
        if not isinstance(message, AIMessage):
            raise ProviderFailure("provider_response_invalid")
        metadata = {**message.response_metadata, "attempt_id": exchange.attempt_id,
                    "execution_mode": exchange.execution_mode, "provider_request_id": exchange.provider_request_id,
                    "model_version": exchange.model_version, "model_name": self.model_name, "usage": exchange.usage}
        # Unknown usage stays unknown. Controlled metadata is never presented as
        # actual LangChain provider billing, even if a fake exchange supplies it.
        usage = exchange.usage
        usage_metadata = None
        if exchange.execution_mode == "live" and isinstance(usage, dict) and all(
            type(usage.get(key)) is int and usage[key] >= 0
            for key in ("input_tokens", "output_tokens", "total_tokens")
        ):
            usage_metadata = {key: usage[key] for key in ("input_tokens", "output_tokens", "total_tokens")}
            thoughts = usage.get("thought_tokens")
            if type(thoughts) is int and thoughts > 0:
                usage_metadata["output_tokens"] += thoughts
                usage_metadata["output_token_details"] = {"reasoning": thoughts}
        message = message.model_copy(update={"response_metadata": metadata, "usage_metadata": usage_metadata})
        return ChatResult(generations=[ChatGeneration(message=message)],
                          llm_output={"model_name": self.model_name, "attempt_id": exchange.attempt_id})


def build_gemini_chat_model(*, gateway: Any, context: Any,
                           output_tokens: int | None = None) -> GeminiChatModel:
    """Build an explicitly injected model without loading configuration or keys.

    B constructs the private context and one admitted gateway. Construction and
    tool binding do not reserve capacity or dispatch. The gateway repeats mode,
    scope and atomic accounting admission for every actual request.
    """
    return GeminiChatModel(gateway=gateway, context=context, output_tokens=output_tokens)
