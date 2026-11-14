"""DB-RESEARCH-1: application authority, separate from A's graph state."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, Any, Literal, Protocol

from pydantic import Field, StringConstraints

from .contracts import Digest, ExplicitTrue, Identifier, StrictModel

RESEARCH_VERSION = "DB-RESEARCH-1"
CHECKPOINT_VERSION = "research-checkpoint.v1"
ACTION_POLICY = "research-action.v1"
SESSION_POLICY = "research-session.v1"
ResearchMode = Literal["controlled", "live"]


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
    async def context(self) -> dict[str, Any]: ...
    async def update_plan(self, plan: dict[str, Any]) -> dict[str, Any]: ...
    async def prepare_investigation(self) -> dict[str, Any]: ...
    async def prepare_design(self, constraints: dict[str, Any]) -> dict[str, Any]: ...
    async def prepare_followup(self) -> dict[str, Any]: ...
    async def require_review(self, review_id: str, review_digest: str) -> dict[str, Any]: ...
    async def execute_child(self, review_id: str) -> dict[str, Any]: ...
    async def read_evidence(self, evidence_id: str) -> dict[str, Any]: ...
    async def request_clarification(self, fields: list[str], reason: str) -> dict[str, Any]: ...
    async def publish_report(self) -> dict[str, Any]: ...
    async def admit_model(self) -> None: ...
    async def admit_tool(self, name: str) -> None: ...


PUBLIC_RESEARCH_SCHEMAS = {model.__name__: model for model in (
    ResearchBudget, ResearchCreate, ResearchAdvance, ResearchDecision, ResearchReconcile,
    ResearchPlanStep, ResearchPlanRevision, ResearchEvent,
)}
