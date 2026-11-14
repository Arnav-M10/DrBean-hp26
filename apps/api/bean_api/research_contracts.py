"""DB-RESEARCH-1: application authority, separate from A's graph state."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Literal, Protocol

from pydantic import Field, StringConstraints, model_validator

from .contracts import AllowanceOrigin, Digest, ExplicitTrue, Identifier, ObservationProposalBody, Rational, StrictModel

RESEARCH_VERSION = "DB-RESEARCH-1"
CHECKPOINT_VERSION = "research-checkpoint.v1"
ACTION_POLICY = "research-action.v1"
SESSION_POLICY = "research-session.v1"
ResearchMode = Literal["controlled", "live"]


class ResearchDesignConstraints(StrictModel):
    feasible_times: list[Rational] = Field(min_length=1, max_length=64)
    future_hard_allowance: Rational
    maximum_horizon: Rational
    allowance_origin: AllowanceOrigin
    requested_tier: Literal["numerical_guidance", "checked_pair_separation"]
    allow_construction: bool = False
    allow_continuation: bool = False

    @model_validator(mode="after")
    def valid_grid(self):
        from fractions import Fraction
        if Fraction(self.future_hard_allowance) <= 0 or Fraction(self.maximum_horizon) <= 0:
            raise ValueError("Future allowance and horizon must be positive")
        if len(set(self.feasible_times)) != len(self.feasible_times) or any(not 0 < Fraction(t) <= Fraction(self.maximum_horizon) for t in self.feasible_times):
            raise ValueError("Future times must be unique, positive and within the horizon")
        if self.allow_continuation and not self.allow_construction:
            raise ValueError("Continuation requires construction permission")
        return self


class ResearchBudget(StrictModel):
    """Lower limits win. No allocation or scientific approval is granted here."""
    policy_version: Literal["research-action.v1"] = ACTION_POLICY
    model_turns: int = Field(default=4, ge=1, le=4)
    tool_calls: int = Field(default=6, ge=1, le=6)
    scientific_reservations: int = Field(default=2, ge=1, le=2)
    active_seconds: int = Field(default=300, ge=1, le=300)


class ResearchCreate(StrictModel):
    schema_version: Literal["DB-RESEARCH-1"] = RESEARCH_VERSION
    objective: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    problem_id: Identifier | None = None
    expected_problem_digest: Digest | None = None
    source_ids: list[Identifier] = Field(default_factory=list, max_length=5)
    mode: ResearchMode = "controlled"
    provider_consent_id: Identifier | None = None
    design_constraints: ResearchDesignConstraints | None = None

    @model_validator(mode="after")
    def bindings(self):
        if bool(self.problem_id) != bool(self.expected_problem_digest):
            raise ValueError("problem_id and expected_problem_digest must be supplied together")
        if len(set(self.source_ids)) != len(self.source_ids):
            raise ValueError("source_ids must be unique")
        return self


class ResearchAdvance(StrictModel):
    expected_revision: int = Field(ge=0)
    budget: ResearchBudget = Field(default_factory=ResearchBudget)


class ResearchDecision(StrictModel):
    expected_revision: int = Field(ge=0)
    pending_review_id: Identifier
    expected_review_digest: Digest
    decision: Literal["approve", "reject"]
    accepted: ExplicitTrue
    # Data/observation input uses its canonical existing review route first.
    # The coordinator accepts only a reference to that immutable receipt.
    observation_review_id: Identifier | None = None


class ResearchReconcile(StrictModel):
    expected_revision: int = Field(ge=0)
    acknowledged_unknown_outcome: ExplicitTrue


class ResearchObservation(StrictModel):
    expected_revision: int = Field(ge=0)
    pending_review_id: Identifier
    expected_review_digest: Digest
    observation: ObservationProposalBody
    accepted: ExplicitTrue


class ResearchInputReview(StrictModel):
    expected_revision: int = Field(ge=0)
    pending_review_id: Identifier
    expected_review_digest: Digest
    accepted: ExplicitTrue
    problem_id: Identifier | None = None
    expected_problem_digest: Digest | None = None
    design_constraints: ResearchDesignConstraints | None = None
    answers: dict[str, Annotated[str, StringConstraints(min_length=1, max_length=2000)]] = Field(default_factory=dict, max_length=16)

    @model_validator(mode="after")
    def exact_inputs(self):
        if bool(self.problem_id) != bool(self.expected_problem_digest):
            raise ValueError("Problem identity and digest must be supplied together")
        if not self.problem_id and self.design_constraints is None and not self.answers:
            raise ValueError("Supply a reviewed input or clarification answer")
        if any(not key or len(key) > 128 for key in self.answers):
            raise ValueError("Answer field names must be bounded")
        return self


class ResearchProviderConsent(StrictModel):
    model: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    expected_context_digest: Digest
    accepted: ExplicitTrue


class ResearchProviderAllocation(StrictModel):
    policy_version: Literal["research-allocation.v1"] = "research-allocation.v1"
    physical_requests: int = Field(ge=1, le=8)
    input_tokens: int = Field(ge=1, le=64_000)
    output_tokens: int = Field(ge=1, le=16_000)
    accepted: ExplicitTrue


class ResearchPlanStep(StrictModel):
    id: Identifier
    title: Annotated[str, StringConstraints(min_length=1, max_length=300)]
    status: Literal["pending", "in_progress", "waiting_review", "waiting_observation", "completed", "failed", "unresolved", "skipped"]
    dependencies: list[Identifier] = Field(default_factory=list, max_length=16)
    reason: Annotated[str, StringConstraints(max_length=1000)] = ""
    reference_ids: list[Identifier] = Field(default_factory=list, max_length=16)


class ResearchPlanRevision(StrictModel):
    version: Literal["research-plan.v1"] = "research-plan.v1"
    steps: list[ResearchPlanStep] = Field(max_length=32)

    @model_validator(mode="after")
    def dependencies_exist(self):
        ids = {step.id for step in self.steps}
        if len(ids) != len(self.steps):
            raise ValueError("Plan step IDs must be unique")
        pending = {step.id: set(step.dependencies) for step in self.steps}
        for step, deps in pending.items():
            if not deps <= ids or step in deps:
                raise ValueError("Plan dependencies must reference other existing steps")
        resolved: set[str] = set()
        while pending:
            ready = {step for step, deps in pending.items() if deps <= resolved}
            if not ready:
                raise ValueError("Plan dependencies must be acyclic")
            resolved |= ready
            pending = {step: deps for step, deps in pending.items() if step not in ready}
        return self


class ResearchEvent(StrictModel):
    event_id: Identifier
    sequence: int = Field(ge=0)
    workspace_id: Identifier
    research_session_id: Identifier
    action_id: Identifier | None
    event_type: Literal["plan_updated", "action_started", "model_attempt_started", "model_attempt_finished",
        "tool_requested", "tool_finished", "review_required", "decision_recorded", "resumed",
        "child_linked", "evidence_observed", "waiting_observation", "cancel_requested", "reconciled", "terminal"]
    timestamp: str
    mode: ResearchMode
    summary: Annotated[str, StringConstraints(max_length=1000)] = ""
    reference_ids: list[Identifier] = Field(default_factory=list, max_length=16)


@dataclass(frozen=True)
class ResearchRuntimeContext:
    """Private server-built context. Never accepted from a browser or model."""
    actor_id: str
    workspace_id: str
    research_session_id: str
    action_id: str
    operation_id: str
    thread_id: str
    lease_owner: str
    lease_epoch: int
    mode: str
    graph_version: str
    checkpoint_version: str = CHECKPOINT_VERSION
    policy_version: str = ACTION_POLICY


class ResearchPorts(Protocol):
    """B resolves all identities, permissions and scientific arguments server-side.

    Every method is async. Non-idempotent model attempts consume admission before
    dispatch; child operations journal intent and reuse the same canonical job.
    """
    async def check_authority(self) -> None: ...
    async def context(self) -> dict[str, Any]: ...
    async def update_plan(self, plan: dict[str, Any]) -> dict[str, Any]: ...
    async def prepare_investigation(self) -> dict[str, Any]: ...
    async def prepare_design(self, constraints: dict[str, Any]) -> dict[str, Any]: ...
    async def prepare_followup(self) -> dict[str, Any]: ...
    async def require_review(self, review_id: str, review_digest: str) -> dict[str, Any]: ...
    async def execute_child(self, review_id: str, expected_review_digest: str) -> dict[str, Any]: ...
    async def read_evidence(self, evidence_id: str) -> dict[str, Any]: ...
    async def request_clarification(self, fields: list[str], reason: str) -> dict[str, Any]: ...
    async def publish_report(self) -> dict[str, Any]: ...
    async def admit_model(self) -> None: ...
    async def admit_tool(self, name: str) -> None: ...


PUBLIC_RESEARCH_SCHEMAS = {model.__name__: model for model in (
    ResearchBudget, ResearchCreate, ResearchAdvance, ResearchDecision, ResearchReconcile, ResearchDesignConstraints, ResearchObservation, ResearchInputReview,
    ResearchProviderConsent, ResearchProviderAllocation,
    ResearchPlanStep, ResearchPlanRevision, ResearchEvent,
)}
