"""Real deepagents graph with only approved, typed application operations.

Pinned 0.7.38 public profile/middleware API inspected from:
https://docs.langchain.com/oss/python/deepagents/customization
https://github.com/langchain-ai/deepagents/blob/main/libs/deepagents/deepagents/graph.py
https://github.com/langchain-ai/langchain-google/tree/main/libs/genai

The defaults are not safe for this task. By-name middleware replacement removes
filesystem tools; the harness profile disables subagents and summarization (which
could otherwise make uncounted provider calls). Every graph's *actual* ToolNode
inventory is checked. Neither a successful import nor a controlled test qualifies
live Gemini adaptation. Callbacks must execute scientific jobs in a killable worker
and reconcile durable reservations; cancellation here only ends orchestration.
"""
from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from .contracts import GroundedExplanation

from .providers import (
    AttemptContext, AttemptLedger, ProviderConfig, ProviderFailure, SYSTEM_INSTRUCTION,
    classify_failure, package_version, utc_now,
)


class CoordinatorFailure(ProviderFailure):
    pass


@dataclass(frozen=True)
class CoordinatorScope:
    run_id: str
    plan_id: str
    problem_id: str
    baseline_scenario_id: str
    optional_scenario_ids: tuple[str, ...] = ()
    context: dict[str, Any] = field(default_factory=dict)
    scenario_problem_ids: dict[str, str] = field(default_factory=dict)
    permitted_tools: tuple[str, ...] | None = None
    question: str = "Explain the evidence and a permitted next step."
    kind: Literal["investigation", "design"] = "investigation"
    optional_scenario_condition: Literal["baseline_inconclusive", "checked_counterexample"] | None = None
    max_model_turns: int = 4
    max_tool_calls: int = 6
    max_scientific_reservations: int = 2
    wall_seconds: int = 300

    def validate(self) -> None:
        if not all((self.run_id, self.plan_id, self.problem_id, self.baseline_scenario_id)):
            raise CoordinatorFailure("agent_scope_invalid")
        if set(self.scenario_problem_ids) - {self.baseline_scenario_id, *self.optional_scenario_ids}:
            raise CoordinatorFailure("agent_scope_invalid")
        if self.scenario_problem_ids.get(self.baseline_scenario_id, self.problem_id) != self.problem_id:
            raise CoordinatorFailure("agent_scope_invalid")
        if len(self.optional_scenario_ids) > 1 or self.baseline_scenario_id in self.optional_scenario_ids:
            raise CoordinatorFailure("agent_scope_invalid")
        if self.optional_scenario_condition not in {None, "baseline_inconclusive", "checked_counterexample"}:
            raise CoordinatorFailure("agent_scope_invalid")
        if self.kind not in {"investigation", "design"}:
            raise CoordinatorFailure("agent_scope_invalid")
        if not 1 <= self.max_model_turns <= 4 or not 1 <= self.max_tool_calls <= 6:
            raise CoordinatorFailure("agent_budget_invalid")
        if not 1 <= self.max_scientific_reservations <= 2 or not 1 <= self.wall_seconds <= 300:
            raise CoordinatorFailure("agent_budget_invalid")
        if self.kind == "design" and (self.wall_seconds > 120 or self.max_scientific_reservations != 1):
            raise CoordinatorFailure("agent_budget_invalid")
        if len(self.question.encode()) > 4000 or len(json.dumps(self.context).encode()) > 24_000:
            raise CoordinatorFailure("agent_context_limit")


@dataclass
class ScopedCallbacks:
    check_authority: Callable[[], Any]
    execute_scenario: Callable[[str], Any]
    read_evidence: Callable[[str], Any]
    record_skip: Callable[[str, str], Any]
    prepare_design_proposal: Callable[[str], Any] | None = None
    execute_design: Callable[[], Any] | None = None
    record_event: Callable[[dict[str, Any]], Any] | None = None


@dataclass
class CoordinatorResult:
    status: Literal["completed", "failed", "cancelled"]
    explanation: dict[str, Any] | None
    evidence: list[dict[str, Any]]
    trace: list[dict[str, Any]]
    runtime: dict[str, Any]
    model_turns: int
    tool_calls: int
    scientific_reservations: int
    error_code: str | None = None


def _safe_failure_code(exc: Exception, fallback: str) -> str:
    code = getattr(exc, "code", None)
    return code if isinstance(code, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,79}", code) else fallback


async def _await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


def _safe_fact(evidence: dict[str, Any]) -> dict[str, Any]:
    """Bound typed records from trusted callbacks; never pass arbitrary exception text."""
    encoded = json.dumps(evidence, ensure_ascii=False, allow_nan=False)
    if len(encoded.encode()) > 12_000:
        raise CoordinatorFailure("agent_evidence_limit")
    if not isinstance(evidence.get("id"), str):
        raise CoordinatorFailure("agent_evidence_identity_missing")
    return json.loads(encoded)


def _validate_explanation(value: GroundedExplanation, facts: dict[str, dict[str, Any]]) -> None:
    if not value.fact_ids:
        raise CoordinatorFailure("explanation_missing_facts")
    if any(ref not in facts for ref in value.fact_ids) or len(set(value.fact_ids)) != len(value.fact_ids):
        raise CoordinatorFailure("explanation_unknown_fact")
    # These explicit controls catch known bad claims; they are not a semantic
    # proof of free-form prose. The UI must separately render trusted fact cards.
    prose = value.text.lower()
    forbidden = ("proves the interval", "proves your interval", "the true parameter", "identifies the true",
                 "disproved nature", "guaranteed accurate", "proves the model is correct", "interval is proven", "interval is proved")
    if any(fragment in prose for fragment in forbidden):
        raise CoordinatorFailure("explanation_unsupported_claim")
    text_facts = json.dumps([facts[ref] for ref in value.fact_ids], ensure_ascii=False)
    number_pattern = r"(?<![\w/])-?\d+(?:\.\d+|/\d+)?(?![\w/])"
    allowed_numbers = set(re.findall(number_pattern, text_facts))
    for number in re.findall(number_pattern, value.text):
        if number not in allowed_numbers:
            raise CoordinatorFailure("explanation_unsupported_number")
    if any(facts[ref].get("expected_binding") == "mismatch" for ref in value.fact_ids):
        if any(word in prose for word in ("certified", "verified", "proves")):
            raise CoordinatorFailure("explanation_binding_mismatch")


def _condition_met(fact: dict[str, Any], condition: str) -> bool:
    if fact.get("expected_binding") != "matches":
        return False
    if condition == "checked_counterexample":
        return fact.get("scientific_outcome") == "certified_counterexample" and fact.get("verification") == "valid"
    return fact.get("scientific_outcome") in {"inconclusive", "no_counterexample_found", "numerical_candidate"}


class OfflineChatModel(BaseChatModel):
    """Explicit local-only injection boundary; subclasses must implement local computation.

    This class is for trusted in-process code, never an HTTP-selectable model.
    No generic provider model is accepted as an offline implementation.
    """


class ControlledEvidenceModel(OfflineChatModel):
    """Scripted placeholder decisions over returned facts, not Gemini reasoning.

    The same immutable reviewed objective/condition accompanies both branches.
    Science remains entirely in authenticated, approval-bound worker callbacks.
    """
    model_name: str = "dr-bean-controlled-placeholder-v1"
    offered: list[str] = []

    @property
    def _llm_type(self):
        return "dr-bean-controlled-placeholder"

    def bind_tools(self, tools, **kwargs):
        self.offered = sorted(tool.name for tool in tools)
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        envelope = json.loads(next(m.content for m in messages if isinstance(m, HumanMessage)))
        observed = [m for m in messages if isinstance(m, ToolMessage)]
        facts = [json.loads(m.content) for m in observed if m.name in {"execute_approved_scenario", "execute_approved_design"}]
        baseline = envelope["baseline_scenario_id"]
        optional = envelope.get("optional_scenario_ids", [])
        acted = {json.loads(m.content).get("scenario_id") for m in observed if m.name == "record_allowed_skip"}
        if not observed:
            name = "execute_approved_design" if envelope["kind"] == "design" else "execute_approved_scenario"
            args = {} if envelope["kind"] == "design" else {"scenario_id": baseline}
        elif optional and len(facts) == 1 and optional[0] not in acted:
            condition = envelope.get("optional_scenario_condition")
            if condition and _condition_met(facts[0], condition):
                name, args = "execute_approved_scenario", {"scenario_id": optional[0]}
            else:
                name, args = "record_allowed_skip", {"scenario_id": optional[0], "reason_code": "not_relevant"}
        elif not optional and "prepare_design_proposal" in self.offered and not any(m.name == "prepare_design_proposal" for m in observed):
            name, args = "prepare_design_proposal", {"scenario_id": baseline}
        else:
            name = "return_grounded_explanation"
            args = {"fact_ids": [f["id"] for f in facts],
                    "text": "Controlled placeholder output: the named records retain their reported scientific scope. Review the exact evidence before further work.",
                    "next_action": "review_design" if facts and facts[0].get("scientific_outcome") == "certified_counterexample" and facts[0].get("verification") == "valid" and facts[0].get("expected_binding") == "matches" else "stop"}
        message = AIMessage(content="", tool_calls=[{"id": f"controlled-call-{len(observed)}", "type": "tool_call", "name": name, "args": args}])
        return ChatResult(generations=[ChatGeneration(message=message)])

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return self._generate(messages, stop, run_manager, **kwargs)


class _Invocation:
    def __init__(self, config: ProviderConfig, ledger: AttemptLedger, context: AttemptContext,
                 scope: CoordinatorScope, callbacks: ScopedCallbacks):
        self.config, self.ledger, self.context, self.scope, self.callbacks = config, ledger, context, scope, callbacks
        self.started = time.monotonic()
        self.turns = self.tool_calls = self.reservations = self.provider_requests = 0
        self.executed: set[str] = set()
        self.skipped: set[str] = set()
        self.baseline_fact_ids: set[str] = set()
        self.facts: dict[str, dict[str, Any]] = {}
        self.explanation: dict[str, Any] | None = None
        self.trace: list[dict[str, Any]] = []
        self.allowed_tools: set[str] = set()
        self.controlled = config.mode == "controlled"

    async def event(self, event: dict[str, Any]) -> None:
        item = {"sequence": len(self.trace), "at": utc_now(), **event}
        self.trace.append(item)
        if self.callbacks.record_event:
            await _await(self.callbacks.record_event(item))

    async def authority(self) -> None:
        if time.monotonic() - self.started >= self.scope.wall_seconds:
            raise CoordinatorFailure("agent_wall_budget_exhausted")
        await _await(self.callbacks.check_authority())

    def add_evidence(self, evidence: dict[str, Any]) -> dict[str, Any]:
        fact = _safe_fact(evidence)
        if fact.get("problem_id") not in {self.scope.problem_id, *self.scope.scenario_problem_ids.values()}:
            raise CoordinatorFailure("agent_evidence_problem_mismatch")
        if fact["id"] in self.facts and self.facts[fact["id"]] != fact:
            raise CoordinatorFailure("agent_evidence_record_changed")
        self.facts[fact["id"]] = fact
        return fact

    async def execute(self, scenario_id: str) -> dict[str, Any]:
        await self.authority()
        if scenario_id not in (self.scope.baseline_scenario_id, *self.scope.optional_scenario_ids):
            raise CoordinatorFailure("scenario_not_approved")
        if scenario_id != self.scope.baseline_scenario_id and self.scope.baseline_scenario_id not in self.executed:
            raise CoordinatorFailure("baseline_must_execute_first")
        if scenario_id != self.scope.baseline_scenario_id and self.scope.optional_scenario_condition:
            baseline = next((f for f in self.facts.values() if f.get("id") in self.baseline_fact_ids), None)
            if not baseline or not _condition_met(baseline, self.scope.optional_scenario_condition):
                raise CoordinatorFailure("optional_scenario_condition_unmet")
        if scenario_id in self.skipped:
            raise CoordinatorFailure("scenario_already_skipped")
        if scenario_id not in self.executed:
            if self.reservations >= self.scope.max_scientific_reservations:
                raise CoordinatorFailure("scientific_budget_exhausted")
            self.reservations += 1
        # Callback owns the durable idempotent child reservation and actual worker.
        evidence = await _await(self.callbacks.execute_scenario(scenario_id))
        await self.authority()
        if evidence.get("problem_id") != self.scope.scenario_problem_ids.get(scenario_id, self.scope.problem_id):
            raise CoordinatorFailure("agent_evidence_problem_mismatch")
        fact = self.add_evidence(evidence)
        self.executed.add(scenario_id)
        if scenario_id == self.scope.baseline_scenario_id:
            self.baseline_fact_ids.add(fact["id"])
        return fact

    async def read(self, evidence_id: str) -> dict[str, Any]:
        await self.authority()
        if evidence_id not in self.facts:
            raise CoordinatorFailure("evidence_outside_invocation")
        original = self.facts[evidence_id]
        returned = await _await(self.callbacks.read_evidence(evidence_id))
        if returned != original:
            raise CoordinatorFailure("agent_evidence_record_changed")
        return self.add_evidence(returned)

    async def skip(self, scenario_id: str, reason_code: str) -> dict[str, Any]:
        await self.authority()
        if scenario_id not in self.scope.optional_scenario_ids:
            raise CoordinatorFailure("mandatory_scenario_cannot_be_skipped")
        if self.scope.baseline_scenario_id not in self.executed:
            raise CoordinatorFailure("baseline_must_execute_first")
        if scenario_id in self.executed:
            raise CoordinatorFailure("completed_scenario_cannot_be_skipped")
        if reason_code not in {"not_relevant", "sufficient_evidence", "budget_preserved", "capability_unavailable"}:
            raise CoordinatorFailure("skip_reason_invalid")
        result = await _await(self.callbacks.record_skip(scenario_id, reason_code))
        self.skipped.add(scenario_id)
        return {"scenario_id": scenario_id, "status": "skipped", "reason_code": reason_code,
                "reservation_id": result.get("id") if isinstance(result, dict) else None}

    async def prepare(self, scenario_id: str) -> dict[str, Any]:
        await self.authority()
        if scenario_id not in self.executed or self.callbacks.prepare_design_proposal is None:
            raise CoordinatorFailure("design_proposal_prerequisite_missing")
        result = await _await(self.callbacks.prepare_design_proposal(scenario_id))
        # The callback receives only a scoped scenario ID. It must use explicitly
        # supplied user constraints, and may create a proposal, never approval/job.
        if not isinstance(result, dict) or result.get("accepted") is not False:
            raise CoordinatorFailure("design_proposal_authority_violation")
        return result

    async def design(self) -> dict[str, Any]:
        await self.authority()
        if self.scope.kind != "design" or self.callbacks.execute_design is None:
            raise CoordinatorFailure("design_approval_required")
        if not self.executed:
            self.reservations += 1
        result = await _await(self.callbacks.execute_design())
        await self.authority()
        self.executed.add(self.scope.baseline_scenario_id)
        return self.add_evidence(result)

    async def explain(self, value: GroundedExplanation) -> dict[str, Any]:
        await self.authority()
        if self.scope.baseline_scenario_id not in self.executed:
            raise CoordinatorFailure("baseline_must_execute_first")
        if set(self.scope.optional_scenario_ids) - self.executed - self.skipped:
            raise CoordinatorFailure("optional_scenario_unresolved")
        _validate_explanation(value, self.facts)
        self.explanation = {**value.model_dump(), "authorship": "controlled_placeholder_commentary" if self.controlled else "gemini_commentary", "scientific_authority": False}
        return {"accepted": True, "fact_ids": value.fact_ids, "scientific_state_changed": False}


def _make_graph(inv: _Invocation, model: Any) -> tuple[Any, dict[str, Any]]:
    from deepagents import create_deep_agent, HarnessProfile, GeneralPurposeSubagentProfile, register_harness_profile
    from deepagents.backends import StateBackend
    from langchain.agents.middleware import AgentMiddleware
    from langchain_core.tools import StructuredTool

    class NoFilesystemMiddleware(AgentMiddleware):
        @property
        def name(self) -> str:
            return "FilesystemMiddleware"  # Documented by-name replacement, no tools/hooks/backend.

    class BudgetMiddleware(AgentMiddleware):
        async def awrap_model_call(self, request: Any, handler: Any) -> Any:
            await inv.authority()
            if inv.explanation is not None:
                raise CoordinatorFailure("agent_already_finished")
            if inv.turns >= inv.scope.max_model_turns:
                raise CoordinatorFailure("agent_model_budget_exhausted")
            request = request.override(model_settings={**request.model_settings,
                "automatic_function_calling": {"disable": True}, "max_retries": 1,
                "max_output_tokens": inv.config.max_output_tokens,
                "timeout": min(inv.config.request_timeout_seconds,
                               max(1, inv.scope.wall_seconds - (time.monotonic() - inv.started)))})
            offered = {tool.name if hasattr(tool, "name") else tool.get("name") for tool in request.tools}
            if offered != inv.allowed_tools:
                raise CoordinatorFailure("agent_tool_inventory_changed")
            serialized = json.dumps({"messages": [m.model_dump(mode="json") for m in request.messages],
                "system": request.system_message.content if request.system_message else "",
                "tools": [{"name": t.name, "description": t.description, "parameters": t.args_schema.model_json_schema()}
                          for t in request.tools]}, ensure_ascii=False, default=str)
            reservation = 1024 + len(serialized.encode())
            if reservation > inv.config.max_input_tokens:
                raise CoordinatorFailure("agent_context_budget_exhausted")
            inv.turns += 1
            started = time.monotonic()
            attempt_id = None
            if not inv.controlled:
                attempt_id = inv.ledger.begin_attempt(inv.context.checked_dict(), {
                    "provider": "gemini", "model": inv.config.model,
                    "operation": "coordinator", "framework": "deepagents",
                    "framework_version": package_version("deepagents"),
                    "sdk_version": package_version("langchain-google-genai"),
                    "prompt_version": "gf2-coordinator-v1", "schema_version": "DB-SC-1",
                    "started_at": utc_now(), "turn": inv.turns,
                    "reserved_input_tokens": reservation, "reserved_output_tokens": inv.config.max_output_tokens,
                    "prompt_sha256": hashlib.sha256(serialized.encode()).hexdigest(), "retry_policy": "none",
                })
            await inv.event({"type": "controlled_model_turn" if inv.controlled else "model_request",
                             "turn": inv.turns, "transport": "controlled" if inv.controlled else "live",
                             **({"attempt_id": attempt_id} if attempt_id else {}),
                             "provenance": "controlled placeholder output" if inv.controlled else "unqualified live model"})
            usage = None
            try:
                if not inv.controlled:
                    inv.provider_requests += 1
                response = await handler(request)
                for message in response.result:
                    raw_usage = getattr(message, "usage_metadata", None)
                    if raw_usage and not inv.controlled:
                        details = raw_usage.get("output_token_details") or {}
                        reasoning = details.get("reasoning")
                        total_out = raw_usage.get("output_tokens")
                        usage = {"input_tokens": raw_usage.get("input_tokens"),
                                 "output_tokens": (total_out - (reasoning or 0)) if type(total_out) is int else None,
                                 "thought_tokens": reasoning, "total_tokens": raw_usage.get("total_tokens")}
                    calls = getattr(message, "tool_calls", [])
                    attempted_count = len(calls) + len(getattr(message, "invalid_tool_calls", []))
                    inv.tool_calls += attempted_count
                    if attempted_count:
                        await inv.event({"type": "tool_attempt", "count": attempted_count})
                    if getattr(message, "invalid_tool_calls", []):
                        raise CoordinatorFailure("agent_malformed_tool_call")
                    if inv.tool_calls > inv.scope.max_tool_calls:
                        raise CoordinatorFailure("agent_tool_budget_exhausted")
                    if any(call.get("name") not in inv.allowed_tools for call in calls):
                        raise CoordinatorFailure("agent_forbidden_tool")
                    if len(calls) > 1:
                        raise CoordinatorFailure("agent_parallel_tools_unsupported")
                    if usage and ((usage["input_tokens"] or 0) > reservation or
                                  (usage["output_tokens"] or 0) + (usage["thought_tokens"] or 0) > inv.config.max_output_tokens):
                        raise CoordinatorFailure("provider_usage_exceeded_reservation")
                if attempt_id is not None:
                    inv.ledger.finish_attempt(attempt_id, {"status": "validated", "finished_at": utc_now(),
                        "duration_ms": int((time.monotonic() - started) * 1000), "usage": usage,
                        "validation_outcome": "allowed_tool_request_or_unaccepted_text"})
                return response
            except asyncio.CancelledError:
                if attempt_id is not None:
                    inv.ledger.finish_attempt(attempt_id, {"status": "unknown_outcome", "finished_at": utc_now(),
                        "code": "provider_cancelled_unknown_outcome", "usage": usage})
                raise
            except Exception as exc:
                code, retryable = (exc.code, exc.retryable) if isinstance(exc, ProviderFailure) else classify_failure(exc)
                code = _safe_failure_code(exc, code)
                if attempt_id is not None:
                    inv.ledger.finish_attempt(attempt_id, {"status": "unknown_outcome" if "unknown_outcome" in code else "failed",
                        "finished_at": utc_now(), "duration_ms": int((time.monotonic() - started) * 1000),
                        "code": code, "usage": usage})
                raise CoordinatorFailure(code, retryable, attempt_id) from None

        async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
            await inv.authority()
            call = request.tool_call
            try:
                request.tool.args_schema.model_validate(call["args"])
                if len(json.dumps(call["args"]).encode()) > 8000:
                    raise ValueError("arguments too large")
            except (ValueError, TypeError):
                raise CoordinatorFailure("agent_malformed_tool_arguments") from None
            safe_arguments = {key: value for key, value in call["args"].items()
                              if key in {"scenario_id", "evidence_id", "reason_code", "fact_ids", "next_action"}}
            await inv.event({"type": "tool_request", "tool": call["name"], "arguments": safe_arguments,
                             "decision_source": "controlled placeholder output" if inv.controlled else "model"})
            try:
                result = await handler(request)
                await inv.event({"type": "tool_result", "tool": call["name"], "completed": True,
                                 "evidence_ids": list(inv.facts)})
                return result
            except Exception as exc:
                code = _safe_failure_code(exc, "scoped_tool_failed")
                await inv.event({"type": "tool_result", "tool": call["name"], "completed": False, "code": code})
                raise CoordinatorFailure(code) from None

    async def execute_approved_scenario(scenario_id: str) -> dict[str, Any]:
        """Execute only the named preapproved scenario, mandatory baseline first."""
        return await inv.execute(scenario_id)

    async def read_scoped_evidence(evidence_id: str) -> dict[str, Any]:
        """Read one immutable evidence record already returned in this invocation."""
        return await inv.read(evidence_id)

    async def record_allowed_skip(scenario_id: str, reason_code: str) -> dict[str, Any]:
        """Skip an optional scenario after baseline: not_relevant, sufficient_evidence, budget_preserved, capability_unavailable."""
        return await inv.skip(scenario_id, reason_code)

    async def prepare_design_proposal(scenario_id: str) -> dict[str, Any]:
        """Prepare unaccepted design from already supplied user constraints; never execute or approve."""
        return await inv.prepare(scenario_id)

    async def execute_approved_design() -> dict[str, Any]:
        """Execute the exact separately approved design job frozen in this invocation."""
        return await inv.design()

    async def return_grounded_explanation(fact_ids: list[str], text: str,
            next_action: Literal["stop", "clarify", "review_design", "review_observation", "review_plan"],
            clarification_fields: list[str] | None = None) -> dict[str, Any]:
        """Finish with referenced model commentary; backend fact cards retain scientific authority."""
        return await inv.explain(GroundedExplanation(fact_ids=fact_ids, text=text,
                                                     next_action=next_action, clarification_fields=clarification_fields or []))

    functions = [read_scoped_evidence, return_grounded_explanation]
    if inv.scope.kind == "design":
        if inv.callbacks.execute_design is not None:
            functions += [execute_approved_design]
    else:
        functions += [execute_approved_scenario, record_allowed_skip]
        if inv.callbacks.prepare_design_proposal is not None and inv.scope.permitted_tools is not None and "prepare_design_proposal" in inv.scope.permitted_tools:
            functions.append(prepare_design_proposal)
    if inv.scope.permitted_tools is not None:
        functions = [fn for fn in functions if fn.__name__ in inv.scope.permitted_tools]
        if set(inv.scope.permitted_tools) != {fn.__name__ for fn in functions}:
            raise CoordinatorFailure("agent_tool_not_implemented")
    callback_names = {"read_scoped_evidence": inv.callbacks.read_evidence,
                      "execute_approved_scenario": inv.callbacks.execute_scenario,
                      "record_allowed_skip": inv.callbacks.record_skip,
                      "prepare_design_proposal": inv.callbacks.prepare_design_proposal,
                      "execute_approved_design": inv.callbacks.execute_design}
    if any(fn.__name__ in callback_names and not callable(callback_names[fn.__name__]) for fn in functions):
        raise CoordinatorFailure("agent_callback_unavailable")
    typed_tools = [StructuredTool.from_function(coroutine=fn, return_direct=fn is return_grounded_explanation)
                   for fn in functions]
    for tool in typed_tools:
        tool.args_schema.model_config.update(extra="forbid", strict=True)
        tool.args_schema.model_rebuild(force=True)
    inv.allowed_tools = {tool.name for tool in typed_tools}
    provider = model._get_ls_params().get("ls_provider")
    model_name = getattr(model, "model_name", None) or getattr(model, "model", None)
    if not provider or not model_name:
        raise CoordinatorFailure("agent_model_identity_unavailable")
    register_harness_profile(f"{provider}:{model_name}", HarnessProfile(
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
        excluded_middleware=frozenset({"SummarizationMiddleware"}),
    ))
    agent = create_deep_agent(model=model, tools=typed_tools,
        middleware=[NoFilesystemMiddleware(), BudgetMiddleware()], backend=StateBackend(),
        system_prompt=SYSTEM_INSTRUCTION + (
            " Execute the mandatory baseline first using execute_approved_scenario. After its actual result, "
            "choose a useful allowed action: run one explicitly approved optional scenario only if relevant, "
            "skip it with an allowed reason, or finish. For design scope use only execute_approved_design. "
            "Issue exactly one tool per model turn. Finish using return_grounded_explanation referencing actual "
            "returned fact IDs. Do not write an unreferenced final answer. A completed job does not prove a "
            "claim. No counterexample found leaves the interval unproved. Mismatched evidence cannot certify "
            "this problem. Numerical evidence is not checked. New data/design must await separate review."
        ), subagents=[], skills=None, memory=None, checkpointer=None, store=None, cache=None, debug=False)
    nodes = agent.get_graph().nodes
    inventories = [set(node.data.tools_by_name) for node in nodes.values() if hasattr(node.data, "tools_by_name")]
    if len(inventories) != 1 or inventories[0] != inv.allowed_tools:
        raise CoordinatorFailure("agent_unsafe_tool_inventory")
    runtime = {"framework": "deepagents", "framework_version": package_version("deepagents"),
               "provider_adapter": "controlled_local" if inv.controlled else "langchain-google-genai", "provider_adapter_version": package_version("langchain-google-genai"),
               "model": getattr(model, "model_name", None), "api_surface": "offline controlled model" if inv.controlled else "Gemini Developer API v1beta",
               "provenance": "controlled placeholder output" if inv.controlled else "unqualified live model",
               "provider_requests": 0 if inv.controlled else None, "provider_usage": None, "tool_inventory": sorted(inv.allowed_tools),
               "filesystem": "disabled_by_middleware_replacement", "backend": "isolated_ephemeral_StateBackend",
               "shell": False, "subagents": False, "memory": False, "summarization": False,
               "tracing": "disabled", "observed_graph_nodes": sorted(nodes), "middleware_policy": "gf2-allowlist-v1", "live_qualified": False}
    return agent, runtime


async def run_coordinator(config: ProviderConfig, ledger: AttemptLedger, context: AttemptContext,
                          scope: CoordinatorScope, callbacks: ScopedCallbacks, *, chat_model: Any = None) -> CoordinatorResult:
    if not 1 <= config.max_input_tokens <= 64_000 or not 1 <= config.max_output_tokens <= 16_000 or not 1 <= config.request_timeout_seconds <= 60:
        raise CoordinatorFailure("provider_budget_invalid")
    controlled = config.mode == "controlled"
    if controlled:
        if chat_model is None:
            chat_model = ControlledEvidenceModel()
        if not isinstance(chat_model, OfflineChatModel):
            raise CoordinatorFailure("agent_controlled_model_required")
    else:
        config.check_ready()
        if chat_model is not None:
            raise CoordinatorFailure("agent_live_model_injection_forbidden")
    context.checked_dict()
    scope.validate()
    inv = _Invocation(config, ledger, context, scope, callbacks)
    owns_model = chat_model is None
    if chat_model is None:
        from langchain_google_genai import ChatGoogleGenerativeAI
        chat_model = ChatGoogleGenerativeAI(model=config.model, api_key=config.api_key,
            vertexai=False, api_version="v1beta", base_url="https://generativelanguage.googleapis.com",
            max_retries=1, timeout=min(config.request_timeout_seconds, scope.wall_seconds),
            max_output_tokens=config.max_output_tokens, cache=False)
        if chat_model.client.vertexai:
            raise CoordinatorFailure("provider_backend_mismatch")
    agent, runtime = _make_graph(inv, chat_model)
    runtime["execution_lane"] = "controlled_model" if controlled else "live_model"
    await inv.event({"type": "runtime_inventory", **runtime})
    envelope = {"plan_id": scope.plan_id, "run_id": scope.run_id, "problem_id": scope.problem_id,
                "kind": scope.kind, "baseline_scenario_id": scope.baseline_scenario_id,
                "optional_scenario_ids": list(scope.optional_scenario_ids), "optional_scenario_condition": scope.optional_scenario_condition, "question": scope.question,
                "approved_context": scope.context,
                "budget": {"model_turns": scope.max_model_turns, "tool_calls": scope.max_tool_calls,
                           "scientific_reservations": scope.max_scientific_reservations, "wall_seconds": scope.wall_seconds}}
    status: Literal["completed", "failed", "cancelled"] = "completed"
    code = None
    try:
        # Prevent environment-enabled LangSmith tracing from exporting private inputs.
        from langsmith import tracing_context
        with tracing_context(enabled=False):
            async with asyncio.timeout(scope.wall_seconds):
                await agent.ainvoke({"messages": [{"role": "user", "content": json.dumps(envelope, ensure_ascii=False)}]},
                                    config={"recursion_limit": 32})
        if inv.explanation is None:
            status, code = "failed", "agent_grounded_explanation_missing"
    except asyncio.CancelledError:
        await inv.event({"type": "invocation_cancelled", "termination": "orchestrator_cancelled_provider_outcome_unknown"})
        raise
    except Exception as exc:
        status = "failed"
        code = _safe_failure_code(exc, "agent_wall_budget_exhausted" if isinstance(exc, TimeoutError) else "agent_execution_failed")
        await inv.event({"type": "invocation_failed", "code": code})
    finally:
        if owns_model:
            try:
                await chat_model.client.aio.aclose()
                chat_model.client.close()
            except Exception:
                pass
    if not controlled:
        runtime["provider_requests"] = inv.provider_requests
    return CoordinatorResult(status, inv.explanation, list(inv.facts.values()), inv.trace, runtime,
                             inv.turns, inv.tool_calls, inv.reservations, code)
