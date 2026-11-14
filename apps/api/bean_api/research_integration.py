"""Consumer adapter from DB-RESEARCH-1 services to A's restricted graph.

No backend modules, routes, approval service or storage are implemented here.
The 0c69912 producer exposes read-only ``check_authority``; atomic
``execute_child(review_id, *, expected_review_digest)``; and a context snapshot
with objective/question (identical), reviewed_context, input_digest, budget, reference_ids, reviews,
and design_constraints (a reviewed dict or explicit None).

Each canonical review has review_id/review_digest/kind/approval_id and a scope
containing immutable plan_id/plan_digest/input_digest. ``require_review`` returns
that binding plus decision pending/approve/reject. Child results retain the same
review/scope plus job_id/state. Unknown or malformed producer envelopes fail
closed. These are consumer requirements, not new public DTOs or production route
integration claims.

``policy`` is the admitted ResearchBudget mapping/model, identical to the
snapshot budget. ``model_factory`` is B's trusted zero-argument bound factory.
``event_sink(dict)`` receives bounded internal observations for B to sequence,
deduplicate and project into ResearchEvent; it never receives model arguments.
"""
from __future__ import annotations

import hashlib
import inspect
from typing import Any

from .agent_evidence import project_evidence_fact
from .canonical import canonical_bytes
from .contracts import DesignResult, ScientificResult
from .conversation import ConversationService
from .coordinator import CoordinatorFailure, _await
from .research_coordinator import (
    GRAPH_VERSION, PORT_VERSION, ResearchContext, _bounded, _references, create_research_coordinator,
)
from .workflow import DomainError, _digest as entity_digest

CONTRACT_VERSION = "DB-RESEARCH-1"
CHECKPOINT_VERSION = "research-checkpoint.v1"
ACTION_POLICY = "research-action.v1"
INTEGRATION_VERSION = "research-integration.v1"
_BUDGET_CAPS = {"model_turns": 4, "tool_calls": 6, "scientific_reservations": 2, "active_seconds": 300}
_KINDS = {"investigation", "design", "followup"}
_ENTITY_FIELDS = {"id", "workspace_id", "kind", "body", "digest", "parent_id", "created_by", "created_at"}
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


def _unavailable(value: Any, kind: str) -> dict[str, Any] | None:
    if not isinstance(value, dict) or "available" not in value:
        return None
    if (set(value) != {"available", "reason"} or value["available"] is not False
            or not isinstance(value["reason"], str) or not value["reason"].strip()
            or len(value["reason"]) > 1000):
        raise CoordinatorFailure("research_backend_binding_invalid")
    return {"accepted": False, "available": False, "kind": kind, "reason": value["reason"]}


def _evidence_fact(value: Any, evidence_id: str, workspace_id: str) -> dict[str, Any]:
    """Project B's immutable entity without turning replay into scientific success."""
    if (not isinstance(value, dict) or set(value) != _ENTITY_FIELDS
            or value.get("id") != evidence_id or value.get("workspace_id") != workspace_id
            or value.get("kind") not in {"evidence", "suggestion"}
            or not isinstance(value.get("body"), dict)):
        raise CoordinatorFailure("research_evidence_binding_invalid")
    _digest(value.get("digest"))
    if value["parent_id"] is not None:
        _identity(value["parent_id"])
    try:
        if entity_digest(value["kind"], value["body"]) != value["digest"]:
            raise CoordinatorFailure("research_evidence_binding_invalid")
        if value["kind"] == "evidence":
            body = value["body"]
            _identity(body.get("run_id"))
            _identity(body.get("scenario_id"))
            ScientificResult.model_validate(body.get("result"))
            fact = project_evidence_fact(value)
            normalized = ConversationService._scientific_body(value)
            for key in ("candidate_ids", "dataset_origin", "native_replay"):
                if key in normalized:
                    fact[key] = normalized[key]
        else:
            DesignResult.model_validate(value["body"])
            # Preserve all options, candidates and verification records. The
            # established projection bounds only duplicated native transcripts;
            # binding is derived solely from a present verification record.
            fact = {"id": value["id"], "evidence_digest": value["digest"],
                    "fact_projection": "agent-design-evidence.v1",
                    **ConversationService._scientific_body(value)}
        source = value["body"]["result"] if value["kind"] == "evidence" else value["body"]
        if isinstance(source.get("native_replay"), dict):
            # Match coordinator._safe_fact's independent replay axes. In
            # particular an unresolved outcome or failed historical check must
            # not disappear merely because replay's byte check passed.
            fact["native_replay"] = {key: source["native_replay"][key] for key in (
                "replay", "scope", "integrity", "verification", "expected_binding",
                "recorded_result_matches", "reason_code", "dataset_origin", "operation",
                "packet_profile", "anchors", "baseline_digest", "problem_digest",
                "design_digest", "suggestion_digest", "outcome", "historical_compatibility",
                "search_replayed",
            ) if key in source["native_replay"]}
        fact.update(kind=value["kind"], workspace_id=workspace_id, parent_id=value["parent_id"])
        return _mapping(fact, 12_000)
    except (KeyError, TypeError, ValueError) as error:
        raise CoordinatorFailure("research_evidence_binding_invalid") from error
    except DomainError as error:
        raise CoordinatorFailure(error.code) from error


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

    async def record_plan(self, todos: list[dict[str, str]], plan_digest: str,
                          evidence: dict[str, list[str]] | None = None) -> Any:
        """Project agent todos into B's plan revision.

        A completed todo becomes a completed step only when the graph read
        canonical, in-scope evidence for it; that step cites the evidence IDs.
        Any other completion stays a pending agent proposal. Planning status
        never creates, completes or verifies a scientific job.
        """
        if hashlib.sha256(canonical_bytes(todos)).hexdigest() != plan_digest:
            raise CoordinatorFailure("research_plan_invalid")
        evidence = evidence or {}
        if not isinstance(evidence, dict) or set(evidence) - {t["content"] for t in todos if t["status"] == "completed"}:
            raise CoordinatorFailure("research_plan_invalid")
        steps = []
        for todo in todos:
            title = todo["content"]
            if len(title) > 300:
                raise CoordinatorFailure("research_plan_title_limit")
            step_id = "step_" + hashlib.sha256(canonical_bytes(
                [self.context.research_session_id, title])).hexdigest()[:32]
            cited = list(evidence.get(title) or []) if todo["status"] == "completed" else []
            if cited:
                _references(cited)
                self._scoped(cited)
            status = todo["status"] if todo["status"] != "completed" or cited else "pending"
            steps.append({"id": step_id, "title": title, "status": status,
                "dependencies": [], "reference_ids": cited,
                "reason": "Completed by the assistant after it read the cited evidence; that evidence "
                          "keeps its own verification status." if cited else
                "Agent-proposed completion; canonical execution remains authoritative."
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
                return _unavailable({"available": False,
                    "reason": "Reviewed feasible times, future hard allowance and horizon are required before preparing a design."}, kind)
            value = await _await(self.backend.prepare_design(_mapping(constraints, 8000)))
        else:
            raise CoordinatorFailure("research_operation_unavailable")
        unavailable = _unavailable(value, kind)
        if unavailable is not None:
            return unavailable
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
        return _evidence_fact(await _await(self.backend.read_evidence(evidence_id)),
                              evidence_id, self.context.workspace_id)

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
