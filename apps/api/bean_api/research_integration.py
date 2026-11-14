"""Consumer adapter from DB-RESEARCH-1 services to A's restricted graph.

No backend modules, routes, approval service or storage are implemented here.
The d224846 protocol needs the following producer additions before this adapter
is available: read-only ``check_authority``; atomic
``execute_child(review_id, *, expected_review_digest)``; and a context snapshot
with objective/question (identical), reviewed_context, input_digest, budget, reference_ids, reviews,
and design_constraints (a reviewed dict or explicit None).

Each canonical review has review_id/review_digest/kind/approval_id and a scope
containing immutable plan_id/plan_digest/input_digest. ``require_review`` returns
that binding plus decision pending/approve/reject. Child results retain the same
review/scope plus job_id/state. These expectations fail closed until B publishes
and implements them. They are consumer requirements, not new public DTOs.

``policy`` is the admitted ResearchBudget mapping/model, identical to the
snapshot budget. ``model_factory`` is B's trusted zero-argument bound factory.
``event_sink(dict)`` receives bounded internal observations for B to sequence,
deduplicate and project into ResearchEvent; it never receives model arguments.
"""
from __future__ import annotations

import hashlib
import inspect
from typing import Any

from .canonical import canonical_bytes
from .coordinator import CoordinatorFailure, _await
from .research_coordinator import (
    GRAPH_VERSION, PORT_VERSION, ResearchContext, _bounded, create_research_coordinator,
)

CONTRACT_VERSION = "DB-RESEARCH-1"
CHECKPOINT_VERSION = "research-checkpoint.v1"
ACTION_POLICY = "research-action.v1"
INTEGRATION_VERSION = "research-integration.v1"
_BUDGET_CAPS = {"model_turns": 4, "tool_calls": 6, "scientific_reservations": 2, "active_seconds": 300}
_KINDS = {"investigation", "design", "followup"}
_METHODS = ("context", "check_authority", "update_plan", "prepare_investigation", "prepare_design",
            "prepare_followup", "require_review", "execute_child", "read_evidence",
            "request_clarification", "publish_report", "admit_model", "admit_tool")


def _mapping(value: Any, limit: int = 24_000) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    value = _bounded(value, limit)
    if not isinstance(value, dict):
        raise CoordinatorFailure("research_backend_contract_required")
    return value


def _identity(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 256:
        raise CoordinatorFailure("research_backend_binding_invalid")
    return value


def _digest(value: Any) -> str:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise CoordinatorFailure("research_backend_binding_invalid")
    return value


def _budget(value: Any) -> dict[str, Any]:
    result = _mapping(value, 2000)
    if set(result) != {"policy_version", *_BUDGET_CAPS} or result["policy_version"] != ACTION_POLICY:
        raise CoordinatorFailure("research_backend_policy_mismatch")
    if any(type(result[k]) is not int or not 1 <= result[k] <= cap for k, cap in _BUDGET_CAPS.items()):
        raise CoordinatorFailure("research_budget_invalid")
    return result


def _canonical_review(value: Any, input_digest: str) -> dict[str, Any]:
    result = _mapping(value, 8000)
    for field in ("review_id",):
        _identity(result.get(field))
    _digest(result.get("review_digest"))
    scope = result.get("scope")
    if (result.get("kind") not in _KINDS or not isinstance(scope, dict)
            or "approval_id" not in result or scope.get("input_digest") != input_digest):
        raise CoordinatorFailure("research_backend_binding_invalid")
    _identity(scope.get("plan_id"))
    _digest(scope.get("plan_digest"))
    if result["approval_id"] is not None:
        _identity(result["approval_id"])
    return result


def _binding(review: dict[str, Any]) -> tuple[str, ...]:
    return (review["review_id"], review["review_digest"], review["kind"],
            review["scope"]["plan_id"], review["scope"]["plan_digest"], review["scope"]["input_digest"])


class _CanonicalPorts:
    version = PORT_VERSION

    def __init__(self, backend: Any, snapshot: dict[str, Any], context: ResearchContext, event_sink: Any):
        self.backend, self.snapshot, self.context, self.event_sink = backend, snapshot, context, event_sink
        self.references = set(snapshot["reference_ids"])
        self.reviews: dict[str, dict[str, Any]] = {}
        for value in snapshot["reviews"]:
            self._remember(value)

    def _remember(self, value: Any) -> dict[str, Any]:
        review = _canonical_review(value, self.context.input_digest)
        proposal_id = review["scope"]["plan_id"]
        if proposal_id in self.reviews and _binding(self.reviews[proposal_id]) != _binding(review):
            raise CoordinatorFailure("research_review_changed")
        self.reviews[proposal_id] = review
        return review

    def _scoped(self, references: list[str]) -> None:
        if any(ref not in self.references for ref in references):
            raise CoordinatorFailure("research_reference_out_of_scope")

    async def check_authority(self) -> None:
        await _await(self.backend.check_authority())

    async def admit_model_turn(self, action_id: str, turn: int) -> None:
        if action_id != self.context.action_id or not 1 <= turn <= self.context.max_model_turns:
            raise CoordinatorFailure("research_backend_binding_invalid")
        await self.check_authority()
        await _await(self.backend.admit_model())

    async def admit_tool(self, name: str) -> None:
        await self.check_authority()
        await _await(self.backend.admit_tool(name))

    async def record_plan(self, todos: list[dict[str, str]], plan_digest: str) -> Any:
        if hashlib.sha256(canonical_bytes(todos)).hexdigest() != plan_digest:
            raise CoordinatorFailure("research_plan_invalid")
        steps = []
        for todo in todos:
            title = todo["content"]
            if len(title) > 300:
                raise CoordinatorFailure("research_plan_title_limit")
            step_id = "step_" + hashlib.sha256(canonical_bytes(
                [self.context.research_session_id, title])).hexdigest()[:32]
            steps.append({"id": step_id, "title": title,
                "status": "pending" if todo["status"] == "completed" else todo["status"],
                "dependencies": [], "reference_ids": [],
                "reason": "Agent-proposed completion; canonical execution remains authoritative."
                if todo["status"] == "completed" else "Agent-proposed research step."})
        if len({step["id"] for step in steps}) != len(steps):
            raise CoordinatorFailure("research_plan_duplicate_step")
        await self.check_authority()
        return await _await(self.backend.update_plan({"version": "research-plan.v1", "steps": steps}))

    async def prepare_proposal(self, kind: str, reference_ids: list[str]) -> dict[str, Any]:
        self._scoped(reference_ids)
        await self.check_authority()
        if kind == "investigation":
            value = await _await(self.backend.prepare_investigation())
        elif kind == "followup":
            value = await _await(self.backend.prepare_followup())
        elif kind == "design":
            constraints = self.snapshot["design_constraints"]
            if constraints is None:
                raise CoordinatorFailure("research_design_constraints_unavailable")
            value = await _await(self.backend.prepare_design(_mapping(constraints, 8000)))
        else:
            raise CoordinatorFailure("research_operation_unavailable")
        review = self._remember(value)
        if review["kind"] != kind:
            raise CoordinatorFailure("research_backend_binding_invalid")
        return {"accepted": False, "proposal_id": review["scope"]["plan_id"],
                "proposal_digest": review["scope"]["plan_digest"],
                "review_id": review["review_id"], "review_digest": review["review_digest"]}

    async def read_review(self, proposal_id: str) -> dict[str, Any]:
        expected = self.reviews.get(proposal_id)
        if expected is None:
            raise CoordinatorFailure("research_review_context_missing")
        await self.check_authority()
        actual = _canonical_review(await _await(self.backend.require_review(
            expected["review_id"], expected["review_digest"])), self.context.input_digest)
        if _binding(actual) != _binding(expected):
            raise CoordinatorFailure("research_review_changed")
        decisions = {"pending": "pending", "approve": "approved", "reject": "rejected"}
        if actual.get("decision") not in decisions:
            raise CoordinatorFailure("research_review_invalid")
        if actual["decision"] == "approve" and actual["approval_id"] is None:
            raise CoordinatorFailure("research_canonical_approval_required")
        return {"proposal_id": proposal_id, "proposal_digest": actual["scope"]["plan_digest"],
                "review_id": actual["review_id"], "review_digest": actual["review_digest"],
                "decision": decisions[actual["decision"]]}

    async def execute_or_reconcile(self, proposal_id: str, proposal_digest: str, review_id: str,
                                   review_digest: str, max_scientific_calls: int) -> dict[str, Any]:
        expected = self.reviews.get(proposal_id)
        if (expected is None or (review_id, review_digest, proposal_digest) !=
                (expected["review_id"], expected["review_digest"], expected["scope"]["plan_digest"])
                or max_scientific_calls != self.context.max_scientific_calls):
            raise CoordinatorFailure("research_review_changed")
        await self.check_authority()
        result = _mapping(await _await(self.backend.execute_child(
            review_id, expected_review_digest=review_digest)), 16_000)
        returned = _canonical_review(result, self.context.input_digest)
        if _binding(returned) != _binding(expected):
            raise CoordinatorFailure("research_child_binding_invalid")
        _identity(result.get("job_id"))
        if result.get("state") not in {"pending", "running", "completed", "failed", "cancelled", "unresolved"}:
            raise CoordinatorFailure("research_child_binding_invalid")
        if "evidence_ids" not in result or not isinstance(result["evidence_ids"], list):
            raise CoordinatorFailure("research_child_binding_invalid")
        for evidence_id in result["evidence_ids"]:
            self.references.add(_identity(evidence_id))
        return {**result, "proposal_id": proposal_id}

    async def read_evidence(self, evidence_id: str) -> Any:
        self._scoped([evidence_id])
        await self.check_authority()
        # B revalidates membership and exact admitted lineage, including explicit
        # historical evidence. A's cache is an additional bound, never authority.
        return await _await(self.backend.read_evidence(evidence_id))

    async def clarify(self, fields: list[str], question: str) -> Any:
        await self.check_authority()
        return await _await(self.backend.request_clarification(fields, question))

    async def publish_report(self, evidence_ids: list[str], commentary: dict[str, Any]) -> dict[str, Any]:
        self._scoped(evidence_ids)
        await self.check_authority()
        report = _mapping(await _await(self.backend.publish_report()), 8000)
        if report.get("evidence_ids") != evidence_ids:
            raise CoordinatorFailure("research_report_binding_invalid")
        # The published port accepts no commentary. Do not claim that this
        # guarded annotation was persisted in B's immutable canonical report.
        return {**report, "agent_commentary": _mapping(commentary, 6000), "commentary_persisted": False}

    async def record_event(self, event: dict[str, Any]) -> None:
        await self.check_authority()
        event = _mapping(event, 8000)
        if event.get("action_id") != self.context.action_id:
            raise CoordinatorFailure("research_backend_binding_invalid")
        references = [event[key] for key in ("review_id", "proposal_id") if key in event]
        observation = {"event_type": event["type"], "action_id": self.context.action_id,
            "mode": "live" if self.context.mode == "live_gemini" else "controlled",
            "summary": event["type"] + (": " + event["tool"] if "tool" in event else ""),
            "reference_ids": references,
            "observation_key": hashlib.sha256(canonical_bytes(event)).hexdigest()}
        await _await(self.event_sink(observation))


async def create_application_research_coordinator(*, context: Any, ports: Any, checkpointer: Any,
                                                model_factory: Any, event_sink: Any, policy: Any):
    """Create A's actual graph using explicitly adopted B authority/services.

The returned facade exposes start, resume, snapshot and explicit new-action
advance. B selects the operation after durable authorization; construction is
read-only and cannot restart work or replenish an allocation.
"""
    if any(not callable(getattr(ports, method, None)) for method in _METHODS) or not callable(event_sink):
        raise CoordinatorFailure("research_backend_contract_required")
    parameters = inspect.signature(ports.execute_child).parameters
    if "expected_review_digest" not in parameters:
        raise CoordinatorFailure("research_atomic_review_binding_required")
    if (getattr(context, "graph_version", None) != GRAPH_VERSION
            or getattr(context, "checkpoint_version", None) != CHECKPOINT_VERSION
            or getattr(context, "policy_version", None) != ACTION_POLICY):
        raise CoordinatorFailure("research_checkpoint_incompatible")
    for name in ("actor_id", "workspace_id", "research_session_id", "action_id", "operation_id",
                 "thread_id", "lease_owner"):
        _identity(getattr(context, name, None))
    if type(getattr(context, "lease_epoch", None)) is not int or context.lease_epoch < 1:
        raise CoordinatorFailure("research_backend_binding_invalid")
    modes = {"controlled": "controlled", "live": "live_gemini"}
    if getattr(context, "mode", None) not in modes:
        raise CoordinatorFailure("research_mode_invalid")
    await _await(ports.check_authority())
    snapshot = _mapping(await _await(ports.context()), 48_000)
    required = {"objective", "question", "reviewed_context", "input_digest", "budget",
                "reference_ids", "reviews", "design_constraints"}
    if not required <= set(snapshot):
        raise CoordinatorFailure("research_backend_context_incomplete")
    if (not isinstance(snapshot["objective"], str) or not 1 <= len(snapshot["objective"]) <= 2000
            or snapshot["question"] != snapshot["objective"]
            or not isinstance(snapshot["reviewed_context"], dict)
            or not isinstance(snapshot["reference_ids"], list) or len(snapshot["reference_ids"]) > 64
            or not isinstance(snapshot["reviews"], list) or len(snapshot["reviews"]) > 16
            or snapshot["design_constraints"] is not None and not isinstance(snapshot["design_constraints"], dict)):
        raise CoordinatorFailure("research_backend_context_incomplete")
    _digest(snapshot["input_digest"])
    for reference in snapshot["reference_ids"]:
        _identity(reference)
    budget = _budget(snapshot["budget"])
    if budget != _budget(policy):
        raise CoordinatorFailure("research_backend_policy_mismatch")
    graph_context = ResearchContext(workspace_id=context.workspace_id, research_session_id=context.research_session_id,
        action_id=context.action_id, thread_id=context.thread_id, input_digest=snapshot["input_digest"],
        question=snapshot["objective"], reviewed_context=snapshot["reviewed_context"], mode=modes[context.mode],
        max_model_turns=budget["model_turns"], max_tool_calls=budget["tool_calls"],
        max_scientific_calls=budget["scientific_reservations"], active_seconds=budget["active_seconds"])
    bound_ports = _CanonicalPorts(ports, snapshot, graph_context, event_sink)
    return create_research_coordinator(context=graph_context, ports=bound_ports,
                                       model_factory=model_factory, checkpointer=checkpointer)
