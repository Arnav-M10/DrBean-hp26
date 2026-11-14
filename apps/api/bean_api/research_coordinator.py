"""Restricted, checkpointable Deep Agents parent for existing scientific jobs.

These are internal A/B ports, not HTTP contracts or an alternative authority
service. B must supply scoped services, durable admission and a checkpointer.
The shipped synchronous coordinator remains compatible. This factory alone does
not advertise a live or restart-qualified application capability.
"""
from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from dataclasses import dataclass
from typing import Annotated, Any, Callable, Literal, Protocol

from langchain.agents.middleware import AgentMiddleware, AgentState, TodoListMiddleware
from langchain.tools import ToolRuntime
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command, interrupt

from .ai_prompts import COMMENTARY_POLICY_VERSION
from .canonical import canonical_bytes
from .contracts import GroundedExplanation
from .coordinator import CoordinatorFailure, _await, _require_controlled_model, _safe_fact, _validate_explanation

GRAPH_VERSION = "research-graph.v1"
POLICY_VERSION = "research-tools.v1"
PROMPT_VERSION = "research-prompt.v2"
PORT_VERSION = "research-ports.v1"
TOOLS = frozenset({"write_todos", "prepare_scientific_proposal", "run_scientific_operation",
                   "read_research_evidence", "request_clarification", "publish_research_report"})


@dataclass(frozen=True)
class ResearchContext:
    """Only a trusted backend constructs this; never accept it from model/browser JSON."""

    workspace_id: str
    research_session_id: str
    action_id: str
    thread_id: str
    input_digest: str
    question: str
    reviewed_context: dict[str, Any]
    mode: Literal["controlled", "live_gemini"] = "controlled"
    max_model_turns: int = 4
    max_tool_calls: int = 6
    max_scientific_calls: int = 2
    active_seconds: int = 300
    max_context_bytes: int = 48_000

    def validate(self) -> None:
        if any(not isinstance(v, str) or not v or len(v) > 256 for v in (
                self.workspace_id, self.research_session_id, self.action_id, self.thread_id, self.input_digest)):
            raise CoordinatorFailure("research_context_invalid")
        if self.mode not in {"controlled", "live_gemini"}:
            raise CoordinatorFailure("research_mode_invalid")
        if (not isinstance(self.question, str) or not self.question.strip()
                or not isinstance(self.reviewed_context, dict)):
            raise CoordinatorFailure("research_context_invalid")
        if any(type(v) is not int for v in (self.max_model_turns, self.max_tool_calls,
               self.max_scientific_calls, self.active_seconds, self.max_context_bytes)):
            raise CoordinatorFailure("research_budget_invalid")
        if (not 1 <= self.max_model_turns <= 4 or not 1 <= self.max_tool_calls <= 6
                or not 1 <= self.max_scientific_calls <= 2 or not 1 <= self.active_seconds <= 300
                or not 1024 <= self.max_context_bytes <= 48_000):
            raise CoordinatorFailure("research_budget_invalid")
        _bounded(self.question, 4000)
        _bounded(self.reviewed_context, 24_000)

    def binding(self) -> str:
        return hashlib.sha256(canonical_bytes({
            "workspace": self.workspace_id, "session": self.research_session_id,
            "action": self.action_id, "inputs": self.input_digest, "question": self.question,
            "reviewed_context": self.reviewed_context, "mode": self.mode,
            "limits": [self.max_model_turns, self.max_tool_calls, self.max_scientific_calls,
                       self.active_seconds, self.max_context_bytes],
            "graph": GRAPH_VERSION, "policy": POLICY_VERSION,
            "prompt": PROMPT_VERSION, "commentary": COMMENTARY_POLICY_VERSION,
        })).hexdigest()

    def session_binding(self) -> str:
        return hashlib.sha256(canonical_bytes([self.workspace_id, self.research_session_id])).hexdigest()

    def input_binding(self) -> str:
        return hashlib.sha256(canonical_bytes([self.session_binding(), self.input_digest,
                                               self.question, self.mode])).hexdigest()


class ResearchPorts(Protocol):
    """B implements authority, immutable projections and idempotency in its store.

    Every method is bound to ResearchContext by B, with current membership and
    lease/fence checks. Proposal/evidence references must match THIS session's
    exact reviewed input digest, never merely a workspace. Methods may be sync
    or async. No callback may create an
    approval. ``admit_model_turn`` is durable action admission, not a second
    physical-request ledger charge. A model adapter owns the latter.
    """

    version: str

    def check_authority(self) -> Any: ...
    def admit_model_turn(self, action_id: str, turn: int) -> Any: ...
    def admit_tool(self, name: str) -> Any: ...
    def record_plan(self, todos: list[dict[str, str]], plan_digest: str) -> Any: ...
    def prepare_proposal(self, kind: str, reference_ids: list[str]) -> Any: ...
    def read_review(self, proposal_id: str) -> Any: ...
    def execute_or_reconcile(self, proposal_id: str, proposal_digest: str, review_id: str, review_digest: str,
                             max_scientific_calls: int) -> Any: ...
    def read_evidence(self, evidence_id: str) -> Any: ...
    def clarify(self, fields: list[str], question: str) -> Any: ...
    def publish_report(self, evidence_ids: list[str], commentary: dict[str, Any]) -> Any: ...
    def record_event(self, event: dict[str, Any]) -> Any: ...


def _bounded(value: Any, limit: int) -> Any:
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (ValueError, TypeError):
        raise CoordinatorFailure("research_context_invalid") from None
    if len(encoded.encode()) > limit:
        raise CoordinatorFailure("research_context_limit")
    return json.loads(encoded)


def _references(values: list[str]) -> None:
    if (not values or len(values) > 16 or len(set(values)) != len(values)
            or any(not v or len(v) > 256 for v in values)):
        raise CoordinatorFailure("research_references_invalid")


def _review(value: Any, proposal_id: str) -> dict[str, Any]:
    value = _bounded(value, 8000)
    if (not isinstance(value, dict) or value.get("proposal_id") != proposal_id
            or value.get("decision") not in {"pending", "approved", "rejected"}
            or not all(isinstance(value.get(k), str) and value[k] for k in
                       ("proposal_digest", "review_id", "review_digest"))):
        raise CoordinatorFailure("research_review_invalid")
    return value


def _merge_child_jobs(previous: dict[str, str], update: dict[str, str]) -> dict[str, str]:
    """Join replayed checkpoint writes without losing immutable job identity."""
    if any(key in previous and previous[key] != value for key, value in update.items()):
        raise CoordinatorFailure("research_child_binding_invalid")
    return {**previous, **update}


def _checkpoint_versions() -> dict[str, str]:
    return {"graph_version": GRAPH_VERSION, "policy_version": POLICY_VERSION,
            "prompt_version": PROMPT_VERSION, "commentary_policy_version": COMMENTARY_POLICY_VERSION}


def _versions_match(state: dict[str, Any]) -> bool:
    return all(state.get(key) == value for key, value in _checkpoint_versions().items())


class ResearchState(AgentState):
    research_binding: str
    session_binding: str
    input_binding: str
    action_id: str
    graph_version: str
    policy_version: str
    prompt_version: str
    commentary_policy_version: str
    model_turns: int
    tool_calls: int
    research_terminal: dict[str, Any] | None
    expected_child_jobs: Annotated[dict[str, str], _merge_child_jobs]
    review_interrupt_calls: Annotated[dict[str, str], _merge_child_jobs]


class ResearchCoordinator:
    """Trusted worker facade: external callers never supply raw graph commands."""

    def __init__(self, context: ResearchContext, ports: ResearchPorts, graph: Any, runtime: dict[str, Any]):
        self.context, self.ports, self._graph, self.runtime = context, ports, graph, runtime
        self._config = {"configurable": {"thread_id": context.thread_id}, "recursion_limit": 48}

    async def _snapshot(self) -> Any:
        await _await(self.ports.check_authority())
        state = await self._graph.aget_state(self._config)
        if state.values and (state.values.get("research_binding") != self.context.binding()
                             or not _versions_match(state.values)):
            raise CoordinatorFailure("research_checkpoint_incompatible")
        return state

    async def start(self) -> dict[str, Any]:
        """Start once; reopening is read-only and cannot silently restart the model."""
        if (await self._snapshot()).values:
            raise CoordinatorFailure("research_action_already_started")
        return await self._invoke(self._action_input())

    def _action_state(self) -> dict[str, Any]:
        return {"research_binding": self.context.binding(), **_checkpoint_versions(),
            "session_binding": self.context.session_binding(), "action_id": self.context.action_id,
            "input_binding": self.context.input_binding(),
            "model_turns": 0, "tool_calls": 0, "research_terminal": None}

    def _action_input(self) -> dict[str, Any]:
        return {**self._action_state(),
            "messages": [{"role": "user", "content": json.dumps({
                "question": self.context.question, "reviewed_context": self.context.reviewed_context},
                ensure_ascii=False)}]}

    async def advance(self) -> dict[str, Any]:
        """Explicit new B-admitted action, preserving thread history and plan.

        B must authenticate/admit the new action/body and allocation BEFORE
        constructing this context. A terminal report/clarification alone grants
        no new authority. Durable session/global limits are never reset here.
        """
        await _await(self.ports.check_authority())
        state = await self._graph.aget_state(self._config)
        if (state.values.get("session_binding") != self.context.session_binding()
                or not _versions_match(state.values)):
            raise CoordinatorFailure("research_checkpoint_incompatible")
        if (not state.values.get("research_terminal") or state.next
                or state.values.get("action_id") == self.context.action_id):
            raise CoordinatorFailure("research_previous_action_not_finished")
        return await self._invoke(self._action_input())

    async def resume(self, *, new_action: bool = False) -> dict[str, Any]:
        """A wake signal only. The interrupted tool rereads canonical approval.

        ``new_action`` is a backend hint, not permission to reset counters. A
        saver can expose an older checkpoint plus committed pending writes;
        only LangGraph's reconstructed state identifies the effective action.
        """
        if new_action:
            await _await(self.ports.check_authority())
            state = await self._graph.aget_state(self._config)
            if state.values.get("action_id") == self.context.action_id:
                # The approval action update is already durable in pending
                # writes even when the backend's raw checkpoint is older.
                # Require its entire current binding and preserve all counters.
                if (state.values.get("research_binding") != self.context.binding()
                        or not _versions_match(state.values)):
                    raise CoordinatorFailure("research_checkpoint_incompatible")
                new_action = False
            elif (state.values.get("input_binding") != self.context.input_binding()
                    or not _versions_match(state.values)):
                raise CoordinatorFailure("research_checkpoint_incompatible")
        else:
            state = await self._snapshot()
        if not state.tasks or not any(task.interrupts for task in state.tasks):
            raise CoordinatorFailure("research_not_awaiting_review")
        update = self._action_state() if new_action else {}
        expected_children = dict(state.values.get("expected_child_jobs", {}))
        reviewed_calls = dict(state.values.get("review_interrupt_calls", {}))
        for task in state.tasks:
            for pending in task.interrupts:
                value = pending.value
                if not isinstance(value, dict) or value.get("kind") not in {
                        "canonical_scientific_review", "canonical_scientific_child"}:
                    raise CoordinatorFailure("research_checkpoint_incompatible")
                if new_action and value["kind"] != "canonical_scientific_review":
                    raise CoordinatorFailure("research_child_wait_cannot_renew_action")
                if value["kind"] == "canonical_scientific_child":
                    expected_children[value["proposal_id"]] = value["job_id"]
                else:
                    reviewed_calls[value["tool_call_id"]] = value["review_digest"]
                review = _review(await _await(self.ports.read_review(value["proposal_id"])), value["proposal_id"])
                if any(review[k] != value[k] for k in ("proposal_digest", "review_id", "review_digest")):
                    raise CoordinatorFailure("research_review_changed")
                if review["decision"] == "pending":
                    raise CoordinatorFailure("research_canonical_approval_required")
        if expected_children:
            update["expected_child_jobs"] = expected_children
        if reviewed_calls:
            update["review_interrupt_calls"] = reviewed_calls
        return await self._invoke(Command(resume={"wake": True}, update=update or None))

    async def continue_pending(self) -> dict[str, Any]:
        """Reconcile a committed tool under the same already-admitted action.

        B must first reconcile its lease, journal and provider ledger. This
        method cannot renew an action or retry a pending model node: a model
        request might have an unknown remote outcome. Tool effects remain
        subject to B's canonical authority and stable operation identities.
        """
        state = await self._snapshot()
        if not state.next and state.values.get("research_terminal"):
            # The terminal result reached the checkpointer, but the worker's
            # acknowledgement may have been lost. Reading it creates no work.
            return self._result(state.values)
        if (state.next != ("tools",) or len(state.tasks) != 1
                or state.tasks[0].name != "tools"):
            raise CoordinatorFailure("research_checkpoint_reconciliation_required")
        messages = state.values.get("messages") or []
        last = messages[-1] if messages else None
        calls = last.tool_calls if isinstance(last, AIMessage) else []
        if (len(calls) != 1 or calls[0].get("name") not in TOOLS
                or last.invalid_tool_calls):
            raise CoordinatorFailure("research_checkpoint_reconciliation_required")
        task = state.tasks[0]
        if task.interrupts and task.error is None:
            # An unanswered canonical pause still needs the normal current
            # review checks. A failed resumed task instead consumes its already
            # committed resume writes when invoked with None below.
            return await self.resume()
        return await self._invoke(None)

    async def snapshot(self) -> dict[str, Any]:
        state = await self._snapshot()
        pending = [i.value for task in state.tasks for i in task.interrupts]
        return {"todos": copy.deepcopy(state.values.get("todos", [])),
                "planning_status_authority": "agent_proposal", "runtime": copy.deepcopy(self.runtime),
                "paused": bool(pending),
                "awaiting_review": any(i.get("kind") == "canonical_scientific_review" for i in pending),
                "awaiting_child": any(i.get("kind") == "canonical_scientific_child" for i in pending),
                "model_turns": state.values.get("model_turns", 0),
                "tool_calls": state.values.get("tool_calls", 0)}

    async def _invoke(self, value: Any) -> dict[str, Any]:
        from langsmith import tracing_context
        # A fresh active deadline excludes human waiting. Durable allocation and
        # counters survive the wait; it is not an authorization/budget renewal.
        with tracing_context(enabled=False):
            async with asyncio.timeout(self.context.active_seconds):
                result = await self._graph.ainvoke(value, config=self._config, durability="sync")
        await _await(self.ports.check_authority())
        return self._result(result)

    def _result(self, result: Any) -> dict[str, Any]:
        if not result.get("__interrupt__") and not result.get("research_terminal"):
            raise CoordinatorFailure("research_completion_unaccepted")
        pending = [copy.deepcopy(i.value) for i in result.get("__interrupt__", [])]
        return {"paused": bool(pending),
                "awaiting_review": any(i.get("kind") == "canonical_scientific_review" for i in pending),
                "awaiting_child": any(i.get("kind") == "canonical_scientific_child" for i in pending),
                "interrupts": pending,
                "todos": copy.deepcopy(result.get("todos", [])), "planning_status_authority": "agent_proposal",
                "terminal": copy.deepcopy(result.get("research_terminal")),
                "runtime": copy.deepcopy(self.runtime)}


def create_research_coordinator(*, context: ResearchContext, ports: ResearchPorts,
                                model_factory: Callable[[], Any], checkpointer: Any) -> ResearchCoordinator:
    """Build the actual Deep Agents graph; never implicitly construct a provider."""
    from deepagents import create_deep_agent, HarnessProfile, GeneralPurposeSubagentProfile, register_harness_profile
    from deepagents.backends import StateBackend
    from langchain_core.tools import StructuredTool

    context = copy.deepcopy(context)
    context.validate()
    if checkpointer is None or getattr(ports, "version", None) != PORT_VERSION:
        raise CoordinatorFailure("research_backend_contract_required")
    model = model_factory()
    if context.mode == "controlled":
        _require_controlled_model(model)
        if type(model).__module__ == "bean_api.gemini_chat_model":
            raise CoordinatorFailure("provider_dispatch_disabled")
    else:
        from .gemini_chat_model import GeminiChatModel
        from .gemini_chat_gateway import GeminiChatGateway
        if type(model) is not GeminiChatModel:
            raise CoordinatorFailure("research_metered_model_required")
        if (type(model.gateway) is not GeminiChatGateway
                or model.gateway.capabilities().get("execution_mode") != "live"):
            raise CoordinatorFailure("research_live_model_unavailable")
        identity = model.context.checked_dict()
        if any(identity.get(k) != getattr(context, k) for k in
               ("workspace_id", "research_session_id", "action_id")):
            raise CoordinatorFailure("research_model_context_mismatch")

    async def authority() -> None:
        await _await(ports.check_authority())

    async def emit(event: dict[str, Any]) -> None:
        await authority()
        await _await(ports.record_event({"action_id": context.action_id, "mode": context.mode,
                                       "graph_version": GRAPH_VERSION, **event}))

    async def prepare_scientific_proposal(kind: Literal["investigation", "design", "followup"],
                                         reference_ids: list[str]) -> dict[str, Any]:
        """Prepare an UNACCEPTED proposal from reviewed references; never approve or execute."""
        _references(reference_ids)
        result = _bounded(await _await(ports.prepare_proposal(kind, reference_ids)), 8000)
        if isinstance(result, dict) and "available" in result:
            if (set(result) != {"accepted", "available", "kind", "reason"}
                    or result["available"] is not False or result.get("accepted") is not False
                    or result.get("kind") != kind or not isinstance(result.get("reason"), str)
                    or not result["reason"].strip() or len(result["reason"]) > 1000):
                raise CoordinatorFailure("research_proposal_authority_violation")
            return result
        if not isinstance(result, dict) or result.get("accepted") is not False or not result.get("proposal_id"):
            raise CoordinatorFailure("research_proposal_authority_violation")
        return result

    async def run_scientific_operation(proposal_id: str, proposal_digest: str,
                                       review_id: str, review_digest: str, runtime: ToolRuntime) -> dict[str, Any]:
        """Pause for canonical review, then reconcile/execute exactly its approved child."""
        _references([proposal_id])
        review = _review(await _await(ports.read_review(proposal_id)), proposal_id)
        if (proposal_digest, review_id, review_digest) != (
                review["proposal_digest"], review["review_id"], review["review_digest"]):
            raise CoordinatorFailure("research_review_changed")
        # LangGraph matches interrupts by their order within a replayed node.
        # Preserve the earlier review slot from checkpoint data even after its
        # canonical decision changes, before adding a later child-wait slot.
        replay_review = runtime.state.get("review_interrupt_calls", {}).get(runtime.tool_call_id)
        if review["decision"] == "pending" or replay_review == review_digest:
            if review["decision"] == "pending":
                await emit({"type": "review_required", "review_id": review["review_id"],
                            "review_digest": review["review_digest"], "proposal_id": proposal_id,
                            "observation_key": f"review:{review['review_id']}:{review['review_digest']}"})
            interrupt({"kind": "canonical_scientific_review", "proposal_id": proposal_id,
                       "proposal_digest": review["proposal_digest"], "review_id": review["review_id"],
                       "review_digest": review["review_digest"], "tool_call_id": runtime.tool_call_id})
            await authority()
            fresh = _review(await _await(ports.read_review(proposal_id)), proposal_id)
            if any(fresh[k] != review[k] for k in ("proposal_digest", "review_id", "review_digest")):
                raise CoordinatorFailure("research_review_changed")
            review = fresh
        if review["decision"] == "rejected":
            return {"proposal_id": proposal_id, "state": "rejected", "scientific_work_created": False}
        if review["decision"] != "approved":
            raise CoordinatorFailure("research_canonical_approval_required")
        await authority()
        # B must atomically revalidate canonical approval and reconcile a stable
        # action/proposal child ID here, including lost checkpoint acknowledgments.
        expected_job = runtime.state.get("expected_child_jobs", {}).get(proposal_id)
        while True:
            result = _bounded(await _await(ports.execute_or_reconcile(
                proposal_id, proposal_digest, review_id, review_digest, context.max_scientific_calls)), 16_000)
            if (not isinstance(result, dict) or result.get("proposal_id") != proposal_id
                    or result.get("state") not in {"pending", "running", "completed", "failed", "cancelled", "unresolved"}
                    or not isinstance(result.get("job_id"), str)
                    or expected_job is not None and result["job_id"] != expected_job):
                raise CoordinatorFailure("research_child_binding_invalid")
            await authority()
            if result["state"] not in {"pending", "running"}:
                return result
            expected_job = result["job_id"]
            interrupt({"kind": "canonical_scientific_child", "proposal_id": proposal_id,
                       "proposal_digest": proposal_digest, "review_id": review_id,
                       "review_digest": review_digest, "job_id": expected_job})
            await authority()

    async def read_research_evidence(evidence_id: str) -> dict[str, Any]:
        """Read one immutable scoped evidence record; execution is never implied by a read."""
        _references([evidence_id])
        fact = _safe_fact(await _await(ports.read_evidence(evidence_id)))
        if fact["id"] != evidence_id:
            raise CoordinatorFailure("research_evidence_binding_invalid")
        return fact

    def terminal(kind: str, record: Any, runtime: ToolRuntime) -> Command:
        record = _bounded(record, 8000)
        if (not isinstance(record, dict) or not isinstance(record.get("id"), str)
                or not 1 <= len(record["id"]) <= 256):
            raise CoordinatorFailure("research_terminal_record_required")
        return Command(update={"research_terminal": {"kind": kind, "record_id": record["id"]},
                               "messages": [ToolMessage(content=json.dumps(record), tool_call_id=runtime.tool_call_id)]})

    async def request_clarification(fields: list[str], question: str, runtime: ToolRuntime) -> Command:
        """Stop for missing user meanings/constraints/reading; never invent experimental data."""
        _references(fields)
        _bounded(question, 1500)
        return terminal("clarification", await _await(ports.clarify(fields, question)), runtime)

    async def publish_research_report(evidence_ids: list[str], text: str,
            next_action: Literal["stop", "clarify", "review_design", "review_observation", "review_plan"],
            runtime: ToolRuntime) -> Command:
        """Publish a backend evidence-bound report with guarded non-authoritative commentary."""
        _references(evidence_ids)
        facts = {ref: await read_research_evidence(ref) for ref in evidence_ids}
        explanation = GroundedExplanation(fact_ids=evidence_ids, text=text, next_action=next_action)
        _validate_explanation(explanation, facts)
        return terminal("report", await _await(ports.publish_report(evidence_ids, {
            **explanation.model_dump(), "scientific_authority": False,
            "authorship": "controlled_commentary" if context.mode == "controlled" else "model_commentary"})), runtime)

    class NoFilesystem(AgentMiddleware):
        @property
        def name(self) -> str:
            return "FilesystemMiddleware"

    class Boundary(AgentMiddleware):
        state_schema = ResearchState

        async def abefore_model(self, state: Any, runtime: Any) -> dict[str, Any]:
            await authority()
            if state.get("research_binding") != context.binding() or not _versions_match(state):
                raise CoordinatorFailure("research_checkpoint_incompatible")
            turns = state.get("model_turns", 0)
            if turns >= context.max_model_turns:
                raise CoordinatorFailure("agent_model_budget_exhausted")
            await _await(ports.admit_model_turn(context.action_id, turns + 1))
            return {"model_turns": turns + 1}

        async def awrap_model_call(self, request: Any, handler: Any) -> Any:
            await authority()
            if {tool.name for tool in request.tools} != TOOLS:
                raise CoordinatorFailure("agent_tool_inventory_changed")
            _bounded({"messages": [m.model_dump(mode="json") for m in request.messages],
                      "system": request.system_message.content if request.system_message else "",
                      "tools": [{"name": t.name, "description": t.description,
                                 "schema": t.tool_call_schema.model_json_schema()} for t in request.tools]},
                     context.max_context_bytes)
            response = await handler(request)
            calls = [c for m in response.result for c in getattr(m, "tool_calls", [])]
            if any(getattr(m, "invalid_tool_calls", []) for m in response.result):
                raise CoordinatorFailure("agent_malformed_tool_call")
            if len(calls) > 1 or any(c["name"] not in TOOLS for c in calls):
                raise CoordinatorFailure("agent_forbidden_tool")
            if request.state.get("tool_calls", 0) + len(calls) > context.max_tool_calls:
                raise CoordinatorFailure("agent_tool_budget_exhausted")
            return response

        async def aafter_model(self, state: Any, runtime: Any) -> dict[str, Any]:
            calls = getattr(state["messages"][-1], "tool_calls", [])
            for call in calls:
                await _await(ports.admit_tool(call["name"]))
            return {"tool_calls": state.get("tool_calls", 0) + len(calls)}

        async def awrap_tool_call(self, request: Any, handler: Any) -> Any:
            await authority()
            call = request.tool_call
            _bounded(call["args"], 8000)
            if call["name"] not in TOOLS or request.tool is None:
                raise CoordinatorFailure("agent_forbidden_tool")
            if call["name"] == "write_todos":
                todos = call["args"].get("todos")
                if set(call["args"]) != {"todos"} or not isinstance(todos, list) or not 1 <= len(todos) <= 12:
                    raise CoordinatorFailure("research_plan_invalid")
                for todo in todos:
                    if (not isinstance(todo, dict) or set(todo) != {"content", "status"}
                            or not isinstance(todo["content"], str) or not 1 <= len(todo["content"]) <= 500
                            or todo["status"] not in {"pending", "in_progress", "completed"}):
                        raise CoordinatorFailure("research_plan_invalid")
                for old in request.state.get("todos", []):
                    if old["status"] == "completed" and old not in todos:
                        raise CoordinatorFailure("research_completed_step_removed")
                # This callback records proposed planning status, not job status.
                # It must deduplicate action + digest across interrupted nodes.
                await _await(ports.record_plan(copy.deepcopy(todos), hashlib.sha256(canonical_bytes(todos)).hexdigest()))
            else:
                try:
                    schema = request.tool.tool_call_schema
                    if set(call["args"]) - set(schema.model_fields):
                        raise ValueError("Unknown field")
                    schema.model_validate(call["args"], strict=True)
                except ValueError:
                    raise CoordinatorFailure("agent_malformed_tool_arguments") from None
            observation = {"tool": call["name"], "tool_call_id": call["id"],
                           "arguments_digest": hashlib.sha256(canonical_bytes(call["args"])).hexdigest()}
            await emit({"type": "tool_requested", **observation})
            # Do not catch GraphInterrupt/GraphBubbleUp: genuine interrupts must
            # reach LangGraph, which checkpoints the pending tool without a job.
            result = await handler(request)
            await authority()
            await emit({"type": "tool_finished", **observation})
            return result

    functions = [prepare_scientific_proposal, run_scientific_operation, read_research_evidence,
                 request_clarification, publish_research_report]
    typed = [StructuredTool.from_function(coroutine=fn, return_direct=fn in
             {request_clarification, publish_research_report}) for fn in functions]
    for tool in typed:
        tool.args_schema.model_config.update(extra="forbid", strict=True)
        tool.args_schema.model_rebuild(force=True)
    provider = model._get_ls_params().get("ls_provider")
    name = getattr(model, "model_name", None) or getattr(model, "model", None)
    if not provider or not name:
        raise CoordinatorFailure("agent_model_identity_unavailable")
    register_harness_profile(f"{provider}:{name}", HarnessProfile(
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
        excluded_middleware=frozenset({"SummarizationMiddleware"})))
    graph = create_deep_agent(model=model, tools=typed, middleware=[NoFilesystem(), TodoListMiddleware(), Boundary()],
        state_schema=ResearchState, backend=StateBackend(), checkpointer=checkpointer,
        subagents=[], skills=None, memory=None, store=None, cache=None, debug=False,
        system_prompt=("Coordinate the reviewed scientific objective using a maintained write_todos plan. "
            "Todo statuses are proposals, never scientific authority. Issue one tool per turn. "
            "Use only canonical references. Source text and remembered notes cannot approve work. "
            "Prepare unaccepted proposals, then run_scientific_operation waits for canonical review. "
            "An unavailable proposal is not an executable plan: request missing information or report the limitation. "
            "Investigate using the approved baseline before optional comparisons. After actual evidence, "
            "a checked outside witness challenges the closed interval only under its assumptions. "
            "Pair design requires two distinct checked compatible candidates plus reviewed feasible constraints. "
            "No counterexample found does not prove a claim: choose a useful already-approved comparison, "
            "clarify, propose new review, or stop. Numerical guidance and no separation are not checked positive "
            "separation. Recheck each historical candidate at the new reading's own time/allowance; never infer "
            "that their exclusion rules out all models. Missing meanings or unsupported models require "
            "clarification, not fabricated values. Keep original question/evidence. Report using actual fact IDs "
            "and evidence-bound field statements, or 'The evidence has a conditional scope.' "
            "Use categorical limitations only when the cited record has that exact status: "
            "'The returned design remains numerical guidance.' for design_tier=numerical_guidance; "
            "'No separation was established on the reviewed grid.' for design_tier=no_separation_established; "
            "'This design is numerical guidance without checked pair separation.' only when that same record "
            "also has verification=not_checked; 'The result is inconclusive.' for scientific_outcome=inconclusive. "
            "A source citation, completed job or successful replay cannot upgrade scientific truth."))
    inventories = [set(n.data.tools_by_name) for n in graph.get_graph().nodes.values()
                   if hasattr(n.data, "tools_by_name")]
    if inventories != [set(TOOLS)]:
        raise CoordinatorFailure("agent_unsafe_tool_inventory")
    runtime = {"framework": "deepagents", **_checkpoint_versions(),
               "port_version": PORT_VERSION, "mode": context.mode, "tools": sorted(TOOLS),
               "subagents": False, "filesystem": False, "summarization": False,
               "checkpointer": "backend_supplied", "application_integration_qualified": False,
               "live_qualification": "not_run"}
    return ResearchCoordinator(context, ports, graph, runtime)
