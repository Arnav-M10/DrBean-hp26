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
import copy
import hashlib
import inspect
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from .contracts import GroundedExplanation
from .canonical import canonical_bytes
from .ai_prompts import COMMENTARY_POLICY_VERSION, commentary_rejection

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
    scenario_observations: list[dict[str, Any]] = field(default_factory=list)


def _safe_failure_code(exc: Exception, fallback: str) -> str:
    code = getattr(exc, "code", None)
    return code if isinstance(code, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,79}", code) else fallback


async def _await(value: Any) -> Any:
    return await value if inspect.isawaitable(value) else value


def _safe_fact(evidence: dict[str, Any]) -> dict[str, Any]:
    """Bound trusted facts, keeping replay states rather than proof transcripts."""
    encoded = json.dumps(evidence, ensure_ascii=False, allow_nan=False)
    if len(encoded.encode()) > 12_000:
        raise CoordinatorFailure("agent_evidence_limit")
    if not isinstance(evidence.get("id"), str):
        raise CoordinatorFailure("agent_evidence_identity_missing")
    # A trusted callback can retain and later mutate its own response object.
    # Keep the bounded serialized value, not that shared mutable reference.
    fact = json.loads(encoded)
    replay = fact.get("native_replay")
    if isinstance(replay, dict):
        # The authoritative top-level candidate results, vectors, artifacts and
        # verification record remain intact. Native replay can duplicate those
        # vectors with long per-observation proof rows, which are unnecessary
        # for an agent choosing a permitted action. Full bytes remain available
        # through the evidence/artifact routes, not conversational context.
        fact["native_replay"] = {key: replay[key] for key in (
            "replay", "scope", "integrity", "verification", "expected_binding",
            "recorded_result_matches", "reason_code", "dataset_origin", "operation",
            "packet_profile", "anchors", "baseline_digest", "problem_digest",
            "design_digest", "suggestion_digest", "outcome", "historical_compatibility",
            "search_replayed",
        ) if key in replay}
        # Bind the complete callback record, including omitted transcript
        # fields, so rereading one immutable ID cannot replace hidden content.
        fact["source_fact_digest"] = hashlib.sha256(canonical_bytes(evidence)).hexdigest()
        fact["fact_projection_version"] = "coordinator-facts.v1"
    return fact


def _require_controlled_model(model: Any) -> None:
    """Admit a trusted local test model without constructing a hosted client.

    Injection is a trusted application seam, not a security sandbox for arbitrary
    Python objects. Inspect the MRO so a locally declared subclass of a known
    hosted adapter cannot accidentally bypass the offline application policy.
    """
    from langchain_core.language_models import BaseChatModel

    hosted_modules = (
        "langchain_google_genai", "langchain_google_vertexai", "langchain_openai",
        "langchain_anthropic", "langchain_aws", "langchain_cohere",
        "langchain_mistralai", "langchain_together", "langchain_groq",
        "langchain_nvidia_ai_endpoints", "langchain_fireworks", "langchain_deepseek",
        "langchain_xai", "langchain_community.chat_models", "langchain.chat_models",
        "bean_api.gemini_chat_model",
    )
    if not isinstance(model, BaseChatModel) or any(
        cls.__module__ == prefix or cls.__module__.startswith(prefix + ".")
        for cls in type(model).__mro__ for prefix in hosted_modules
    ):
        raise CoordinatorFailure("provider_dispatch_disabled")


def _validate_explanation(value: GroundedExplanation, facts: dict[str, dict[str, Any]]) -> None:
    if not value.fact_ids:
        raise CoordinatorFailure("explanation_missing_facts")
    if any(ref not in facts for ref in value.fact_ids) or len(set(value.fact_ids)) != len(value.fact_ids):
        raise CoordinatorFailure("explanation_unknown_fact")
    prose = value.text.lower()
    rejection = commentary_rejection(value.text, [facts[ref] for ref in value.fact_ids])
    if rejection:
        raise CoordinatorFailure("explanation_unsupported_claim" if rejection == "unsupported_claim"
                                 else "explanation_unsupported_number")
    if any(facts[ref].get("expected_binding") == "mismatch" for ref in value.fact_ids):
        if any(word in prose for word in ("certified", "verified", "proves")):
            raise CoordinatorFailure("explanation_binding_mismatch")


class _Invocation:
    def __init__(self, config: ProviderConfig, ledger: AttemptLedger, context: AttemptContext,
                 scope: CoordinatorScope, callbacks: ScopedCallbacks):
        self.config, self.ledger, self.context, self.scope, self.callbacks = config, ledger, context, scope, callbacks
        self.started = time.monotonic()
        self.turns = self.tool_calls = self.reservations = 0
        self.executed: set[str] = set()
        self.skipped: set[str] = set()
        self.scenario_evidence_ids: dict[str, str] = {}
        self.skip_reasons: dict[str, str] = {}
        self.facts: dict[str, dict[str, Any]] = {}
        self.explanation: dict[str, Any] | None = None
        self.trace: list[dict[str, Any]] = []
        self.allowed_tools: set[str] = set()

    async def event(self, event: dict[str, Any]) -> None:
        item = {"sequence": len(self.trace), "at": utc_now(), **copy.deepcopy(event)}
        self.trace.append(item)
        if self.callbacks.record_event:
            await _await(self.callbacks.record_event(copy.deepcopy(item)))

    def scenario_observations(self, termination_reason: str | None) -> list[dict[str, Any]]:
        """Describe accepted callbacks, never infer a durable scientific state.

        An interrupted or failed callback can leave authoritative work completed,
        running or stopped elsewhere. Only its owning backend can establish that
        state; an unobserved result stays unresolved in this invocation.
        """
        observations = []
        for scenario_id in (self.scope.baseline_scenario_id, *self.scope.optional_scenario_ids):
            disposition, evidence_id, reason = "unresolved", None, termination_reason or "agent_result_not_observed"
            if scenario_id in self.scenario_evidence_ids:
                disposition, evidence_id, reason = "completed", self.scenario_evidence_ids[scenario_id], None
            elif scenario_id in self.skip_reasons:
                disposition, reason = "skipped", self.skip_reasons[scenario_id]
            observations.append({"scenario_id": scenario_id, "observation_scope": "coordinator_invocation",
                                 "disposition": disposition, "evidence_id": evidence_id, "reason_code": reason})
        return observations

    async def authority(self) -> None:
        if time.monotonic() - self.started >= self.scope.wall_seconds:
            raise CoordinatorFailure("agent_wall_budget_exhausted")
        await _await(self.callbacks.check_authority())

    def add_evidence(self, evidence: dict[str, Any]) -> dict[str, Any]:
        fact = _safe_fact(evidence)
        if fact.get("problem_id") not in {self.scope.problem_id, *self.scope.scenario_problem_ids.values()}:
            raise CoordinatorFailure("agent_evidence_problem_mismatch")
        if fact["id"] in self.facts and self.facts[fact["id"]] != fact:
            raise CoordinatorFailure("agent_evidence_changed")
        self.facts[fact["id"]] = fact
        return fact

    async def execute(self, scenario_id: str) -> dict[str, Any]:
        await self.authority()
        if scenario_id not in (self.scope.baseline_scenario_id, *self.scope.optional_scenario_ids):
            raise CoordinatorFailure("scenario_not_approved")
        if scenario_id != self.scope.baseline_scenario_id and self.scope.baseline_scenario_id not in self.executed:
            raise CoordinatorFailure("baseline_must_execute_first")
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
        self.scenario_evidence_ids[scenario_id] = fact["id"]
        return fact

    async def read(self, evidence_id: str) -> dict[str, Any]:
        await self.authority()
        if evidence_id not in self.facts:
            raise CoordinatorFailure("evidence_outside_invocation")
        evidence = await _await(self.callbacks.read_evidence(evidence_id))
        if evidence.get("id") != evidence_id:
            raise CoordinatorFailure("agent_evidence_identity_mismatch")
        return self.add_evidence(evidence)

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
        self.skip_reasons[scenario_id] = reason_code
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
        fact = self.add_evidence(result)
        self.executed.add(self.scope.baseline_scenario_id)
        self.scenario_evidence_ids[self.scope.baseline_scenario_id] = fact["id"]
        return fact

    async def explain(self, value: GroundedExplanation) -> dict[str, Any]:
        await self.authority()
        if self.scope.baseline_scenario_id not in self.executed:
            raise CoordinatorFailure("baseline_must_execute_first")
        if set(self.scope.optional_scenario_ids) - self.executed - self.skipped:
            raise CoordinatorFailure("scenario_accounting_incomplete")
        _validate_explanation(value, self.facts)
        self.explanation = {**value.model_dump(), "authorship": "controlled_commentary", "scientific_authority": False}
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
            attempt_id = inv.ledger.begin_attempt(inv.context.checked_dict(), {
                "provider": "controlled_local", "model": model_name,
                "active_mode": "controlled_offline", "external_provider_calls": 0,
                "actual_model_tokens": 0, "provider_request_id": None,
                "operation": "coordinator", "framework": "deepagents",
                "framework_version": package_version("deepagents"),
                "prompt_version": "gf2-coordinator-v1", "schema_version": "DB-SC-1",
                "commentary_policy_version": COMMENTARY_POLICY_VERSION,
                "started_at": utc_now(), "turn": inv.turns,
                "simulated_input_token_reservation": reservation,
                "simulated_output_token_reservation": inv.config.max_output_tokens,
                "prompt_sha256": hashlib.sha256(serialized.encode()).hexdigest(), "retry_policy": "none",
            })
            await inv.event({"type": "model_request", "local_attempt_id": attempt_id,
                             "active_mode": "controlled_offline", "provider_request_id": None, "turn": inv.turns})
            usage = None
            try:
                response = await handler(request)
                for message in response.result:
                    # Fixture usage metadata is not observed provider billing.
                    # The context reservation above is a simulated local bound.
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
                inv.ledger.finish_attempt(attempt_id, {"status": "validated", "finished_at": utc_now(),
                    "duration_ms": int((time.monotonic() - started) * 1000), "usage": usage,
                    "active_mode": "controlled_offline", "actual_model_tokens": 0,
                    "validation_outcome": "allowed_tool_request_or_unaccepted_text"})
                return response
            except asyncio.CancelledError:
                inv.ledger.finish_attempt(attempt_id, {"status": "unknown_outcome", "finished_at": utc_now(),
                    "code": "controlled_model_interrupted", "usage": usage,
                    "active_mode": "controlled_offline", "actual_model_tokens": 0})
                raise
            except Exception as exc:
                code, retryable = (exc.code, exc.retryable) if isinstance(exc, ProviderFailure) else classify_failure(exc)
                code = _safe_failure_code(exc, code)
                inv.ledger.finish_attempt(attempt_id, {"status": "unknown_outcome" if "unknown_outcome" in code else "failed",
                    "finished_at": utc_now(), "duration_ms": int((time.monotonic() - started) * 1000),
                    "code": code, "usage": usage, "active_mode": "controlled_offline", "actual_model_tokens": 0})
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
                             "decision_source": "model"})
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
            functions.append(execute_approved_design)
    else:
        functions += [execute_approved_scenario, record_allowed_skip]
        if inv.callbacks.prepare_design_proposal is not None:
            functions.append(prepare_design_proposal)
    if inv.scope.permitted_tools is not None:
        functions = [fn for fn in functions if fn.__name__ in inv.scope.permitted_tools]
        if set(inv.scope.permitted_tools) != {fn.__name__ for fn in functions}:
            raise CoordinatorFailure("agent_tool_not_implemented")
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
            "or skip it with an allowed reason. Account for every optional scenario before finishing. "
            "For design scope use only execute_approved_design. "
            "Issue exactly one tool per model turn. Finish using return_grounded_explanation referencing actual "
            "returned fact IDs. Do not write an unreferenced final answer. A completed job does not prove a "
            "claim. No counterexample found leaves the interval unproved. Mismatched evidence cannot certify "
            "this problem. Numerical evidence is not checked. New data/design must await separate review. "
            "Narration must use complete evidence-bound field statements or the neutral sentence "
            "'The evidence has a conditional scope.' Unrecognized free-form scientific prose is withheld."
        ), subagents=[], skills=None, memory=None, checkpointer=None, store=None, cache=None, debug=False)
    nodes = agent.get_graph().nodes
    inventories = [set(node.data.tools_by_name) for node in nodes.values() if hasattr(node.data, "tools_by_name")]
    if len(inventories) != 1 or inventories[0] != inv.allowed_tools:
        raise CoordinatorFailure("agent_unsafe_tool_inventory")
    runtime = {"framework": "deepagents", "framework_version": package_version("deepagents"),
               "provider_adapter": "controlled_local_model", "model": model_name,
               "intended_provider": "gemini", "configured_model": inv.config.model,
               "active_mode": "controlled_offline", "transport_provenance": "trusted_local_model_injection",
               "external_provider_calls": 0, "actual_model_tokens": 0,
               "live_qualification": "not_run", "tool_inventory": sorted(inv.allowed_tools),
               "commentary_policy_version": COMMENTARY_POLICY_VERSION,
               "filesystem": "disabled_by_middleware_replacement", "backend": "isolated_ephemeral_StateBackend",
               "shell": False, "subagents": False, "memory": False, "summarization": False,
               "tracing": "disabled", "observed_graph_nodes": sorted(nodes), "middleware_policy": "gf2-allowlist-v1", "live_qualified": False}
    return agent, runtime


async def run_coordinator(config: ProviderConfig, ledger: AttemptLedger, context: AttemptContext,
                          scope: CoordinatorScope, callbacks: ScopedCallbacks, *, chat_model: Any = None) -> CoordinatorResult:
    _require_controlled_model(chat_model)
    config.check_ready()
    context.checked_dict()
    # frozen=True prevents attribute replacement, not mutation of nested dicts.
    # Freeze reviewed context/mappings before callbacks or graph work can await.
    scope = copy.deepcopy(scope)
    scope.validate()
    inv = _Invocation(config, ledger, context, scope, callbacks)
    agent, runtime = _make_graph(inv, chat_model)
    runtime["execution_lane"] = "controlled_model"
    await inv.event({"type": "runtime_inventory", **runtime})
    envelope = {"plan_id": scope.plan_id, "run_id": scope.run_id, "problem_id": scope.problem_id,
                "kind": scope.kind, "baseline_scenario_id": scope.baseline_scenario_id,
                "optional_scenario_ids": list(scope.optional_scenario_ids), "question": scope.question,
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
    except asyncio.CancelledError as cancellation:
        cancellation_index = len(inv.trace)
        try:
            await inv.event({"type": "invocation_cancelled", "termination": "controlled_orchestrator_cancelled",
                             "scenario_observations": inv.scenario_observations("controlled_orchestrator_cancelled")})
        except (Exception, asyncio.CancelledError):
            # event() retains its local snapshot before calling the sink. A
            # failed acknowledgement leaves persistence unconfirmed; retrying
            # here or replacing cancellation would obscure backend recovery.
            if cancellation_index < len(inv.trace):
                inv.trace[cancellation_index].update(event_persistence="unconfirmed",
                                                     event_persistence_code="agent_event_sink_failed")
        raise cancellation from None
    except Exception as exc:
        status = "failed"
        code = _safe_failure_code(exc, "agent_wall_budget_exhausted" if isinstance(exc, TimeoutError) else "agent_execution_failed")
    observations = inv.scenario_observations(code)
    if status == "failed":
        await inv.event({"type": "invocation_failed", "code": code, "scenario_observations": observations})
    return CoordinatorResult(status, inv.explanation, list(inv.facts.values()), inv.trace, runtime,
                             inv.turns, inv.tool_calls, inv.reservations, code, observations)
