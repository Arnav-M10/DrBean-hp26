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
from langchain.agents.middleware.types import hook_config
from langchain.tools import ToolRuntime
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.types import Command, interrupt
from pydantic import Field

from .ai_prompts import COMMENTARY_POLICY_VERSION
from .canonical import canonical_bytes
from .contracts import GroundedExplanation
from .coordinator import CoordinatorFailure, _await, _require_controlled_model, _safe_fact, _validate_explanation

GRAPH_VERSION = "research-graph.v1"
POLICY_VERSION = "research-tools.v1"
# v4: bounded, deterministic model views that keep every identity and binding:
# investigation evidence (_model_fact), finished children (_child_view) and
# dataset rows (_rows_table). Checkpoints written under v3 are refused, as before.
PROMPT_VERSION = "research-prompt.v4"
PORT_VERSION = "research-ports.v1"
FACT_VIEW_VERSION = "agent-evidence-view.v1"
TOOLS = frozenset({"write_todos", "prepare_scientific_proposal", "run_scientific_operation",
                   "read_research_evidence", "request_clarification", "publish_research_report"})


def _safe_tool_batch(calls: list[dict]) -> bool:
    """Only planning plus an independent proposal/report may share one request.

    Science and evidence-dependent tools never run in parallel with their inputs.
    Every tool still consumes its own durable admission and authority checks.
    """
    names = [call.get("name") for call in calls]
    return (len(names) <= 1 and all(name in TOOLS for name in names)) or (
        len(names) == 2 and len(set(names)) == 2 and set(names) in (
            {"write_todos", "prepare_scientific_proposal"},
            {"write_todos", "publish_research_report"}))


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
    def record_plan(self, todos: list[dict[str, str]], plan_digest: str,
                    evidence: dict[str, list[str]] | None = None) -> Any: ...
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


def _rows_table(rows: Any) -> Any:
    """Lossless table layout for reviewed rows that all have the same fields.

    Every row, including excluded rows, and every value stay exact; values shared
    by all rows are stated once. Anything irregular is returned unchanged.
    """
    if (not isinstance(rows, list) or len(rows) < 2 or not all(isinstance(row, dict) for row in rows)
            or any(set(row) != set(rows[0]) for row in rows)):
        return copy.deepcopy(rows)
    def encode(value: Any) -> str:
        # JSON text equality keeps 1/true/"1" distinct, unlike Python ==.
        return json.dumps(value, sort_keys=True, ensure_ascii=False)

    try:
        keys = sorted(rows[0])
        same = {key: copy.deepcopy(rows[0][key]) for key in keys
                if all(encode(row[key]) == encode(rows[0][key]) for row in rows)}
    except (TypeError, ValueError):
        return copy.deepcopy(rows)
    columns = [key for key in keys if key not in same]
    return {"row_count": len(rows), "same_in_every_row": same, "columns": columns,
            "values": [[copy.deepcopy(row[key]) for key in columns] for row in rows]}


def _model_context(context: dict[str, Any]) -> dict[str, Any]:
    """Omit storage metadata and deduplicate identical problem envelopes only.

    Every record body, row, allowance, assumption, identity and digest remains;
    dataset rows use the lossless table layout of ``_rows_table``. The
    authority/checkpoint binding still uses the complete original context.
    This is a deterministic projection, never model-backed summarization.
    """
    def body(record: dict[str, Any]) -> Any:
        value = record["body"]
        if record.get("kind") == "dataset" and isinstance(value, dict) and "rows" in value:
            return {key: _rows_table(item) if key == "rows" else copy.deepcopy(item) for key, item in value.items()}
        return copy.deepcopy(value)

    def project(value: Any) -> Any:
        if isinstance(value, list):
            return [project(item) for item in value]
        if not isinstance(value, dict):
            return value
        storage_record = all(key in value for key in ("id", "digest", "kind", "body"))
        return {key: body(value) if storage_record and key == "body" else project(item)
                for key, item in value.items()
                if not storage_record or key not in {"created_at", "created_by", "workspace_id"}}

    result = project(context)
    if result.get("problem") and result.get("current_problem") == result["problem"]:
        result["current_problem"] = {"id": result["problem"]["id"], "digest": result["problem"]["digest"],
                                     "same_as": "problem"}
    return result


_FACT_DUPLICATES = {"candidate_ids", "candidate_results", "workspace_id"}
_RECORD_DUPLICATES = {"artifact_id", "artifact_sha256", "verification", "expected_binding", "expected_problem_digest",
                      "observed_problem_digest", "expected_scientific_problem_digest",
                      "observed_scientific_problem_digest"}
_ANCHOR_DUPLICATES = {"artifact_sha256", "problem_digest", "projection_digest", "run_id", "scenario_id"}


def _model_fact(fact: dict[str, Any]) -> dict[str, Any]:
    """Bounded model view of one validated investigation fact; never an authority.

    The complete fact remains the report validator's input, and native bytes stay
    behind authenticated downloads bound by the artifact digest. The view keeps
    every identity, binding digest, outcome and replay axis, candidate vector,
    per-candidate result, search scope and checker proposition. It removes only
    repeated copies of the same IDs/digests inside candidate, verification and
    replay records after checking that each copy is identical. Any disagreement,
    or a fact that is not the expected investigation shape, returns the complete
    fact unchanged, so a discrepancy is never hidden from the model.
    """
    try:
        if fact.get("fact_projection") != "agent-evidence.v1" or fact.get("kind") != "evidence":
            return fact
        candidates, artifacts, record = fact["candidates"], fact["artifacts"], fact["verification_record"]
        results = {item["candidate_id"]: item for item in fact["candidate_results"]}
        ids = [candidate["id"] for candidate in candidates]
        artifact_ids = [artifact["id"] for artifact in artifacts]
        replay = fact.get("native_replay")
        anchors = replay.get("anchors") if isinstance(replay, dict) else None
        consistent = (
            len(artifacts) == 1 and len(ids) == len(set(ids)) == len(results) == len(fact["candidate_results"])
            and set(results) == set(ids) and fact.get("candidate_ids", ids) == ids
            and all(c.get("problem_id") == fact["problem_id"] and c.get("problem_digest") == fact["problem_digest"]
                    and c.get("artifact_ids") == artifact_ids and results[c["id"]].get("verification") == c["verification"]
                    and not (set(c) & set(results[c["id"]])) - {"verification"} for c in candidates)
            and record["artifact_id"] == artifacts[0]["id"] and record["artifact_sha256"] == artifacts[0]["sha256"]
            and record["verification"] == fact["verification"] and record["expected_binding"] == fact["expected_binding"]
            and record["expected_problem_digest"] == record["observed_problem_digest"] == fact["problem_digest"]
            and (record["expected_scientific_problem_digest"] == record["observed_scientific_problem_digest"]
                 == fact["scientific_problem_digest"])
            and (replay is None or (isinstance(replay, dict) and isinstance(anchors, dict)
                 and replay.get("dataset_origin") == fact.get("dataset_origin")
                 and all(anchors.get(key) == expected for key, expected in (
                     ("artifact_sha256", artifacts[0]["sha256"]), ("problem_digest", fact["problem_digest"]),
                     ("projection_digest", fact["scientific_problem_digest"]), ("run_id", fact["run_id"]),
                     ("scenario_id", fact["scenario_id"]))))))
        if not consistent:
            return fact
        view = {key: copy.deepcopy(value) for key, value in fact.items() if key not in _FACT_DUPLICATES
                and key not in {"candidates", "verification_record", "native_replay"}}
        view["fact_view"] = FACT_VIEW_VERSION
        view["candidates"] = [{**{key: copy.deepcopy(value) for key, value in c.items()
                                  if key not in {"problem_id", "problem_digest", "artifact_ids"}},
                               **{key: copy.deepcopy(value) for key, value in results[c["id"]].items()
                                  if key not in {"candidate_id", "verification"}}} for c in candidates]
        view["verification_record"] = {key: value for key, value in record.items() if key not in _RECORD_DUPLICATES}
        if replay is not None:
            view["native_replay"] = {key: copy.deepcopy(value) for key, value in replay.items()
                                     if key not in {"anchors", "dataset_origin"}}
            view["native_replay"]["anchors"] = {key: value for key, value in anchors.items()
                                                if key not in _ANCHOR_DUPLICATES}
        return view
    except (KeyError, TypeError, AttributeError):
        return fact


def _child_view(result: dict[str, Any], *, proposal_id: str, proposal_digest: str, review_digest: str,
                input_digest: str) -> dict[str, Any]:
    """Model view of a finished child result without verified repeated bindings.

    Removes only copies the model already holds or the session already binds:
    the review scope when it is exactly this proposal/digest/input, the review
    digest it sent, and a ``waiting`` flag that is false for every finished
    state. Every other field, including any unexpected one, stays unchanged.
    """
    view = copy.deepcopy(result)
    if view.get("scope") == {"plan_id": proposal_id, "plan_digest": proposal_digest, "input_digest": input_digest}:
        del view["scope"]
    if view.get("review_digest") == review_digest:
        del view["review_digest"]
    if view.get("waiting") is False:
        del view["waiting"]
    return view


def _plan_evidence(messages: list[Any]) -> dict[str, list[str]]:
    """Bind todos the agent marks completed to canonical evidence it actually read.

    A deterministic replay of the retained thread, so interrupted or reconstructed
    nodes reach the same answer. Evidence IDs come only from successful
    read_research_evidence results whose returned id equals the requested id. A todo
    that first becomes completed after such reads is bound to the evidence read since
    the previous plan update that no earlier step already cites. Completion without a
    read stays unbound and therefore remains an agent proposal.
    """
    calls: dict[str, dict[str, Any]] = {}
    bound: dict[str, list[str]] = {}
    unbound: list[str] = []
    for message in messages:
        if isinstance(message, AIMessage):
            for call in message.tool_calls:
                calls[call["id"]] = call
                todos = call["args"].get("todos") if call["name"] == "write_todos" else None
                if not isinstance(todos, list):
                    continue
                newly = [todo["content"] for todo in todos if isinstance(todo, dict) and todo.get("status") == "completed"
                         and isinstance(todo.get("content"), str) and todo["content"] not in bound]
                for content in newly:
                    bound[content] = list(unbound)
                if newly:
                    unbound.clear()
        elif isinstance(message, ToolMessage) and message.status != "error":
            call = calls.get(message.tool_call_id)
            if call is None or call["name"] not in {"read_research_evidence", "run_scientific_operation"}:
                continue
            try:
                value = json.loads(message.content)
            except (TypeError, ValueError):
                continue
            if call["name"] == "read_research_evidence":
                observed = [(call["args"].get("evidence_id"), value)]
            elif isinstance(value, dict) and value.get("state") == "completed":
                observed = [(fact.get("id"), fact) for fact in value.get("canonical_evidence", [])
                            if isinstance(fact, dict) and fact.get("id") in value.get("evidence_ids", [])]
            else:
                observed = []
            for reference, fact in observed:
                if (isinstance(fact, dict) and isinstance(reference, str) and fact.get("id") == reference
                        and reference not in unbound and not any(reference in refs for refs in bound.values())):
                    unbound.append(reference)
    return bound


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
            "model_turns": 0, "tool_calls": 0, "research_terminal": None, "jump_to": None}

    def _action_input(self) -> dict[str, Any]:
        return {**self._action_state(),
            "messages": [{"role": "user", "content": json.dumps({
                "question": self.context.question, "reviewed_context": _model_context(self.context.reviewed_context)},
                ensure_ascii=False, separators=(",", ":"))}]}

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
        if (state.values.get("research_terminal") and state.next == ("Boundary.before_model",)
                and state.tasks and all(task.name == "Boundary.before_model" for task in state.tasks)):
            # A mixed planning/report batch has completed both tools. The
            # boundary's terminal guard writes END without admitting/calling a
            # model. Complete that guard so a later explicit action can advance.
            return await self._invoke(None)
        if (state.next != ("tools",) or not 1 <= len(state.tasks) <= 2
                or any(task.name != "tools" for task in state.tasks)):
            # Without a committed tool decision the model output is not
            # reconstructible here. A completed physical request may have lost
            # its checkpoint acknowledgement, even when it is not marked
            # unknown by the provider ledger. Never infer permission to resend.
            raise CoordinatorFailure("research_model_outcome_unrecoverable")
        messages = state.values.get("messages") or []
        index = next((i for i in range(len(messages) - 1, -1, -1) if isinstance(messages[i], AIMessage)), None)
        decision = messages[index] if index is not None else None
        calls = decision.tool_calls if decision is not None else []
        # A safe two-tool batch can have one already committed ToolMessage and
        # one pending task. Preserve that response and continue only the graph's
        # pending writes; never substitute a new decision or replay the model.
        responses = messages[index + 1:] if index is not None else []
        call_ids = {call.get("id") for call in calls}
        if (not calls or not _safe_tool_batch(calls) or decision.invalid_tool_calls
                or len(state.tasks) > len(calls) or len(call_ids) != len(calls)
                or any(not isinstance(message, ToolMessage) or message.tool_call_id not in call_ids for message in responses)
                or len({message.tool_call_id for message in responses}) != len(responses)):
            raise CoordinatorFailure("research_checkpoint_reconciliation_required")
        if any(task.interrupts and task.error is None for task in state.tasks):
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
                                         reference_ids: Annotated[list[str], Field(min_length=1, max_length=16)]) -> dict[str, Any]:
        """Prepare only. Investigation: [reviewed_context.dataset.id]. Design: [evidence ID]. Never empty."""
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
        """Copy all four prepared fields verbatim; pause for approval; execute/reconcile that child."""
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
                view = _child_view(result, proposal_id=proposal_id, proposal_digest=proposal_digest,
                                   review_digest=review_digest, input_digest=context.input_digest)
                if context.mode == "live_gemini" and result["state"] == "completed" and result.get("evidence_ids"):
                    _references(result["evidence_ids"])
                    # Read the actual immutable records once the child finishes.
                    # Returning them saves a model turn; it does not synthesize
                    # science, bypass validation or replace the explicit read tool.
                    from .research_fact_view import live_fact
                    view["canonical_evidence"] = [live_fact(_model_fact(await complete_fact(ref))) for ref in result["evidence_ids"]]
                return view
            expected_job = result["job_id"]
            interrupt({"kind": "canonical_scientific_child", "proposal_id": proposal_id,
                       "proposal_digest": proposal_digest, "review_id": review_id,
                       "review_digest": review_digest, "job_id": expected_job})
            await authority()

    async def complete_fact(evidence_id: str) -> dict[str, Any]:
        _references([evidence_id])
        fact = _safe_fact(await _await(ports.read_evidence(evidence_id)))
        if fact["id"] != evidence_id:
            raise CoordinatorFailure("research_evidence_binding_invalid")
        return fact

    async def read_research_evidence(evidence_id: str) -> dict[str, Any]:
        """Read scoped immutable evidence without scientific execution."""
        fact = _model_fact(await complete_fact(evidence_id))
        if context.mode == "live_gemini":
            from .research_fact_view import live_fact
            return live_fact(fact)
        return fact

    def terminal(kind: str, record: Any, runtime: ToolRuntime) -> Command:
        record = _bounded(record, 8000)
        if (not isinstance(record, dict) or not isinstance(record.get("id"), str)
                or not 1 <= len(record["id"]) <= 256):
            raise CoordinatorFailure("research_terminal_record_required")
        return Command(update={"research_terminal": {"kind": kind, "record_id": record["id"]}, "jump_to": "end",
                               "messages": [ToolMessage(content=json.dumps(record), tool_call_id=runtime.tool_call_id)]})

    async def request_clarification(fields: list[str], question: str, runtime: ToolRuntime) -> Command:
        """Pause for missing meanings, constraints or a new reading."""
        _references(fields)
        _bounded(question, 1500)
        return terminal("clarification", await _await(ports.clarify(fields, question)), runtime)

    async def publish_research_report(evidence_ids: list[str], text: str,
            next_action: Literal["stop", "clarify", "review_design", "review_observation", "review_plan"],
            runtime: ToolRuntime) -> Command:
        """Report evidence/next_action; text exactly 'The evidence has a conditional scope.'."""
        _references(evidence_ids)
        # Validate commentary against the complete bounded facts, not the view.
        facts = {ref: await complete_fact(ref) for ref in evidence_ids}
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

        @hook_config(can_jump_to=["end"])
        async def abefore_model(self, state: Any, runtime: Any) -> dict[str, Any]:
            await authority()
            if state.get("research_binding") != context.binding() or not _versions_match(state):
                raise CoordinatorFailure("research_checkpoint_incompatible")
            if state.get("research_terminal"):
                # A plan/report batch finishes both tools; the SDK routes mixed
                # return_direct tools here. Do not spend another model request.
                return {"jump_to": "end"}
            turns = state.get("model_turns", 0)
            if turns >= context.max_model_turns:
                raise CoordinatorFailure("agent_model_budget_exhausted")
            await _await(ports.admit_model_turn(context.action_id, turns + 1))
            return {"model_turns": turns + 1}

        async def awrap_model_call(self, request: Any, handler: Any) -> Any:
            await authority()
            if {tool.name for tool in request.tools} != TOOLS:
                raise CoordinatorFailure("agent_tool_inventory_changed")
            if context.mode == "live_gemini":
                from .research_context import model_messages
                request = request.override(messages=model_messages(request.messages, request.state,
                    question=context.question, reviewed_context=_model_context(context.reviewed_context)))
            _bounded({"messages": [m.model_dump(mode="json") for m in request.messages],
                      "system": request.system_message.content if request.system_message else "",
                      "tools": [{"name": t.name, "description": t.description,
                                 "schema": t.tool_call_schema.model_json_schema()} for t in request.tools]},
                     context.max_context_bytes)
            response = await handler(request)
            calls = [c for m in response.result for c in getattr(m, "tool_calls", [])]
            if any(getattr(m, "invalid_tool_calls", []) for m in response.result):
                raise CoordinatorFailure("agent_malformed_tool_call")
            if not _safe_tool_batch(calls):
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
                # Completion counts only with evidence this thread actually read.
                evidence = _plan_evidence(request.state.get("messages") or [])
                await _await(ports.record_plan(copy.deepcopy(todos), hashlib.sha256(canonical_bytes(todos)).hexdigest(),
                                               {todo["content"]: evidence.get(todo["content"], []) for todo in todos
                                                if todo["status"] == "completed"}))
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
    # The SDK defaults repeat several pages of general planning instructions on
    # every physical request. Keep the actual SDK planning middleware and its
    # tool/schema while supplying the research-specific instruction once. This
    # reduces charged context without dropping any reviewed input or evidence.
    planning = TodoListMiddleware(
        system_prompt="Plan from evidence; preserve completed steps; no authority.",
        tool_description="Plan only; preserve completed steps.")
    graph = create_deep_agent(model=model, tools=typed, middleware=[NoFilesystem(), planning, Boundary()],
        state_schema=ResearchState, backend=StateBackend(), checkpointer=checkpointer,
        subagents=[], skills=None, memory=None, store=None, cache=None, debug=False,
        system_prompt=("Use canonical IDs/evidence. Plan; prepare; human approve; run; report/clarify. "
            "Batch only independent todos+prepare/report. Clarify missing assumptions; invent nothing. "
            "A counterexample is compatible and strictly outside the CLOSED claim. Bounded misses prove nothing. "
            "Design: distinct checked candidates, reviewed times/allowance, separate approval, positive checked margin. "
            "Keep history and readings' time/allowance/origin. Exclusions aren't global. Execution/binding/verification/replay differ. "
            "Report text exactly 'The evidence has a conditional scope.'"))
    inventories = [set(n.data.tools_by_name) for n in graph.get_graph().nodes.values()
                   if hasattr(n.data, "tools_by_name")]
    if inventories != [set(TOOLS)]:
        raise CoordinatorFailure("agent_unsafe_tool_inventory")
    runtime = {"framework": "deepagents", **_checkpoint_versions(),
               "port_version": PORT_VERSION, "mode": context.mode, "tools": sorted(TOOLS),
               "subagents": False, "filesystem": False, "summarization": False,
               "checkpointer": "backend_supplied", "application_integration_qualified": False,
               "model_context_version": "research-canonical-context.v1",
               "live_qualification": "not_run"}
    return ResearchCoordinator(context, ports, graph, runtime)
