"""Shared DB-SC-1 application schemas with GF-2 operational bounds.

JSON Schemas generated from these models are the browser integration contract.
Scientific validation/verification belongs to the separately qualified adapter.
"""

from __future__ import annotations

from fractions import Fraction
from typing import Annotated, Literal

from pydantic import AfterValidator, BeforeValidator, BaseModel, ConfigDict, Field, StringConstraints, model_validator

from .canonical import validate_rational

CONTRACT_VERSION = "DB-SC-1"
POLICY_VERSION = "GF-2"
Rational = Annotated[str, StringConstraints(max_length=514, pattern=r"^(?:0|-[1-9][0-9]*|[1-9][0-9]*)/[1-9][0-9]*$"), AfterValidator(validate_rational)]
Identifier = Annotated[str, StringConstraints(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")]
Digest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
ShortText = Annotated[str, StringConstraints(max_length=2000)]
ExactVector = dict[Literal["A", "ke", "ka"], Rational]


def _explicit_true(value: object) -> object:
    if type(value) is not bool or value is not True:
        raise ValueError("An explicit JSON true is required")
    return value


def _page_one(value: object) -> object:
    if type(value) is not int or value != 1:
        raise ValueError("The admitted image has exactly one page, numbered 1")
    return value


ExplicitTrue = Annotated[Literal[True], BeforeValidator(_explicit_true)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, validate_default=True)


class FieldDiagnostic(StrictModel):
    code: Identifier
    field_path: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    message: ShortText
    blocking: bool = True


class ApiError(StrictModel):
    code: Identifier
    message: ShortText
    field_paths: list[str] = Field(default_factory=list, max_length=50)
    retryable: bool = False
    current_revision_id: Identifier | None = None
    request_id: Identifier


class WorkspaceCreateRequest(StrictModel):
    name: Annotated[str, StringConstraints(min_length=1, max_length=120)]


class CancelRequest(StrictModel):
    pass


class DecimalInputRequest(StrictModel):
    value: Annotated[str, StringConstraints(min_length=1, max_length=256)]


class ReportRequest(StrictModel):
    run_id: Identifier


class ObservationRow(StrictModel):
    id: Identifier
    time: Rational
    concentration: Rational
    hard_allowance: Rational
    included: bool
    original_values: dict[str, str] = Field(default_factory=dict, max_length=12)
    source_asset_id: Identifier | None = None
    notes: ShortText = ""

    @model_validator(mode="after")
    def physical_bounds(self) -> "ObservationRow":
        if Fraction(self.time) < 0 or Fraction(self.concentration) < 0:
            raise ValueError("Time and concentration must be nonnegative, including excluded rows")
        if Fraction(self.hard_allowance) <= 0:
            raise ValueError("Each historical hard allowance must be positive")
        if any(len(key) > 128 or len(value) > 256 for key, value in self.original_values.items()):
            raise ValueError("Original value spellings exceed the field limit")
        return self


class DatasetBody(StrictModel):
    schema_version: Literal["DB-SC-1"] = CONTRACT_VERSION
    experiment_id: Identifier
    time_origin: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    rows: list[ObservationRow] = Field(min_length=1, max_length=500)
    parent_id: Identifier | None = None
    change_reason: ShortText
    origin: Literal["actual", "hypothetical", "synthetic"]

    @model_validator(mode="after")
    def unique_rows(self) -> "DatasetBody":
        if len({row.id for row in self.rows}) != len(self.rows):
            raise ValueError("Observation row IDs must be unique")
        if not any(row.included for row in self.rows):
            raise ValueError("At least one observation must be explicitly included")
        return self


class ParameterBounds(StrictModel):
    lower: Rational
    upper: Rational

    @model_validator(mode="after")
    def ordered_positive(self) -> "ParameterBounds":
        if not 0 < Fraction(self.lower) <= Fraction(self.upper):
            raise ValueError("Parameter domain must have positive ordered finite bounds")
        return self


class ParameterDomain(StrictModel):
    A: ParameterBounds
    ke: ParameterBounds
    ka: ParameterBounds
    rate_order: Literal["ke_lt_ka"] = "ke_lt_ka"

    @model_validator(mode="after")
    def feasible_order(self) -> "ParameterDomain":
        if Fraction(self.ke.lower) >= Fraction(self.ka.upper):
            raise ValueError("Domain cannot contain the required ke < ka ordering")
        return self


class TargetInterval(StrictModel):
    parameter: Literal["ke"] = "ke"
    lower: Rational
    upper: Rational
    closed: ExplicitTrue = True

    @model_validator(mode="after")
    def ordered(self) -> "TargetInterval":
        if Fraction(self.lower) > Fraction(self.upper):
            raise ValueError("Closed target interval lower bound exceeds upper bound")
        return self


class ProblemBody(StrictModel):
    schema_version: Literal["DB-SC-1"] = CONTRACT_VERSION
    dataset_id: Identifier
    dataset_digest: Digest
    model: Literal["two_rate_concentration"] = "two_rate_concentration"
    domain: ParameterDomain
    initial_concentration: Literal["0/1"] = "0/1"
    observable: Literal["concentration"] = "concentration"
    time_unit: Literal["h"] = "h"
    concentration_unit: Literal["mg/L"] = "mg/L"
    rate_unit: Literal["1/h"] = "1/h"
    target: TargetInterval


ToolName = Literal["read_scoped_evidence", "execute_approved_scenario", "record_allowed_skip", "prepare_design_proposal", "execute_approved_design", "return_grounded_explanation"]


class Scenario(StrictModel):
    id: Identifier
    problem_id: Identifier
    problem_digest: Digest
    kind: Literal["baseline", "optional"]
    label: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class InvestigationBudget(StrictModel):
    provider_turns: int = Field(default=4, ge=0, le=4)
    tool_calls: int = Field(default=6, ge=1, le=6)
    scientific_reservations: int = Field(default=2, ge=1, le=2)
    wall_seconds: int = Field(default=300, ge=1, le=300)
    scientific_wall_seconds: int = Field(default=120, ge=1, le=120)

    @model_validator(mode="after")
    def fits_parent(self) -> "InvestigationBudget":
        if self.scientific_wall_seconds > self.wall_seconds:
            raise ValueError("Scientific job wall limit exceeds the whole invocation limit")
        return self


class ProviderDisclosure(StrictModel):
    provider: Literal["gemini", "none"] = "none"
    model: Annotated[str, StringConstraints(min_length=1, max_length=128)] | None = None
    source_asset_ids: list[Identifier] = Field(default_factory=list, max_length=1)
    context_fields: list[Annotated[str, StringConstraints(max_length=128)]] = Field(default_factory=list, max_length=32)
    permission_id: Identifier | None = None

    @model_validator(mode="after")
    def consistent(self) -> "ProviderDisclosure":
        if self.provider == "gemini" and (not self.model or not self.permission_id):
            raise ValueError("Gemini disclosure requires the selected model and separate permission record")
        if self.provider == "none" and (self.model or self.source_asset_ids or self.permission_id):
            raise ValueError("A manual plan cannot silently disclose data to a provider")
        return self


class AgentProviderConsent(StrictModel):
    provider: Literal["gemini"] = "gemini"
    model: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    source_asset_ids: list[Identifier] = Field(default_factory=list, max_length=1)
    context_fields: list[Annotated[str, StringConstraints(min_length=1, max_length=128)]] = Field(default_factory=list, max_length=32)
    problem_id: Identifier
    accepted: ExplicitTrue


class PlanBody(StrictModel):
    schema_version: Literal["DB-SC-1"] = CONTRACT_VERSION
    problem_id: Identifier
    problem_digest: Digest
    dataset_id: Identifier
    scenarios: list[Scenario] = Field(min_length=1, max_length=2)
    permitted_tools: list[ToolName] = Field(default_factory=lambda: ["read_scoped_evidence", "execute_approved_scenario", "record_allowed_skip", "return_grounded_explanation"], max_length=6)
    budget: InvestigationBudget = Field(default_factory=InvestigationBudget)
    provider_disclosure: ProviderDisclosure = Field(default_factory=ProviderDisclosure)
    parent_plan_id: Identifier | None = None

    @model_validator(mode="after")
    def bounded_scenarios(self) -> "PlanBody":
        if self.scenarios[0].kind != "baseline" or sum(s.kind == "baseline" for s in self.scenarios) != 1:
            raise ValueError("A plan requires exactly one mandatory baseline as its first scenario")
        if len({s.id for s in self.scenarios}) != len(self.scenarios):
            raise ValueError("Scenario IDs must be unique")
        baseline = self.scenarios[0]
        if baseline.problem_id != self.problem_id or baseline.problem_digest != self.problem_digest:
            raise ValueError("The baseline must bind the exact reviewed problem")
        if len(self.scenarios) > self.budget.scientific_reservations:
            raise ValueError("Listed scientific scenarios exceed the reservation budget")
        if "execute_approved_design" in self.permitted_tools:
            raise ValueError("Design execution requires a separate DesignPlanRevision")
        if len(set(self.permitted_tools)) != len(self.permitted_tools):
            raise ValueError("Permitted tools must be unique")
        return self


class CreatePlanRequest(StrictModel):
    expected_current_revision_id: Identifier
    plan: PlanBody


class ApprovalRequest(StrictModel):
    expected_plan_digest: Digest
    expected_current_revision_id: Identifier
    accepted: ExplicitTrue


class StartRunRequest(StrictModel):
    approval_id: Identifier
    expected_plan_digest: Digest


class DesignBudget(StrictModel):
    wall_seconds: int = Field(default=120, ge=1, le=120)
    fixed_vector_constructions: int = Field(default=2, ge=0, le=2)
    pair_verifications: int = Field(default=2, ge=0, le=2)
    bundle_bytes: int = Field(default=4194304, ge=1, le=4194304)


class CandidateVector(StrictModel):
    A: Rational
    ke: Rational
    ka: Rational

    @model_validator(mode="after")
    def supported_vector(self) -> "CandidateVector":
        if not (Fraction(self.A) > 0 and 0 < Fraction(self.ke) < Fraction(self.ka)):
            raise ValueError("A candidate requires A > 0 and 0 < ke < ka")
        return self


class DesignRequestBody(StrictModel):
    schema_version: Literal["DB-SC-1"] = CONTRACT_VERSION
    historical_run_id: Identifier
    scenario_id: Identifier
    problem_id: Identifier
    problem_digest: Digest
    candidate_ids: list[Identifier] = Field(min_length=2, max_length=2)
    candidate_vectors: list[CandidateVector] = Field(min_length=2, max_length=2)
    observable: Literal["concentration"] = "concentration"
    feasible_times: list[Rational] = Field(min_length=1, max_length=64)
    future_hard_allowance: Rational
    allow_construction: bool = False
    allow_continuation: bool = False
    budget: DesignBudget = Field(default_factory=DesignBudget)

    @model_validator(mode="after")
    def reviewed_pair(self) -> "DesignRequestBody":
        if self.candidate_ids[0] == self.candidate_ids[1]:
            raise ValueError("Design requires two distinct fixed candidates")
        if Fraction(self.future_hard_allowance) <= 0:
            raise ValueError("Future hard allowance must be explicitly positive")
        if any(Fraction(time) <= 0 for time in self.feasible_times):
            raise ValueError("Future elapsed times must be positive")
        if len(set(self.feasible_times)) != len(self.feasible_times):
            raise ValueError("Reviewed feasible times must be unique")
        return self


class DesignPlanBody(StrictModel):
    schema_version: Literal["DB-SC-1"] = CONTRACT_VERSION
    request: DesignRequestBody
    request_digest: Digest
    provider_disclosure: ProviderDisclosure = Field(default_factory=ProviderDisclosure)
    permitted_tools: list[ToolName] = Field(default_factory=lambda: ["read_scoped_evidence", "execute_approved_design", "return_grounded_explanation"], max_length=3)

    @model_validator(mode="after")
    def design_tools(self) -> "DesignPlanBody":
        if set(self.permitted_tools) - {"read_scoped_evidence", "execute_approved_design", "return_grounded_explanation"}:
            raise ValueError("Design plans cannot authorize investigation or new proposal tools")
        return self


class ObservationProposalBody(StrictModel):
    dataset_id: Identifier
    experiment_id: Identifier
    observable: Literal["concentration"] = "concentration"
    origin: Literal["actual", "transcription", "hypothetical"]
    row: ObservationRow
    source_description: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    change_reason: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    generating_choices: dict[str, str] = Field(default_factory=dict, max_length=16)
    time_unit: Literal["h"] = "h"
    concentration_unit: Literal["mg/L"] = "mg/L"

    @model_validator(mode="after")
    def hypothetical_origin(self) -> "ObservationProposalBody":
        if self.origin == "hypothetical" and not self.generating_choices:
            raise ValueError("A hypothetical reading must retain its generating choices")
        if self.origin != "hypothetical" and self.generating_choices:
            raise ValueError("Generated values cannot be labeled actual observations")
        return self


class ObservationReviewRequest(StrictModel):
    proposal_digest: Digest
    parent_dataset_id: Identifier
    accepted: ExplicitTrue


class SourceAssetMetadata(StrictModel):
    sha256: Digest
    declared_media_type: Literal["image/png", "image/jpeg"]
    observed_media_type: Literal["image/png", "image/jpeg"]
    byte_size: int = Field(ge=1, le=5242880)
    width: int = Field(ge=1, le=12000000)
    height: int = Field(ge=1, le=12000000)
    origin: Literal["synthetic", "public"]
    retention: Literal["retain", "digest_only"]
    upload_actor_id: Identifier

    @model_validator(mode="after")
    def admitted_image(self) -> "SourceAssetMetadata":
        if self.width * self.height > 12000000:
            raise ValueError("Decoded source exceeds twelve megapixels")
        if self.declared_media_type != self.observed_media_type:
            raise ValueError("Declared MIME does not match the observed image format")
        return self


class SourceLocator(StrictModel):
    page: Annotated[Literal[1], BeforeValidator(_page_one)] = 1
    label: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    excerpt: Annotated[str, StringConstraints(max_length=1000)]
    bbox: list[Annotated[int, Field(ge=0, le=12000000)]] | None = Field(default=None, min_length=4, max_length=4)

    @model_validator(mode="after")
    def valid_rectangle(self) -> "SourceLocator":
        if self.bbox is not None and (self.bbox[0] >= self.bbox[2] or self.bbox[1] >= self.bbox[3]):
            raise ValueError("Source rectangle must be [left, top, right, bottom] with positive area")
        return self


class IntakeField(StrictModel):
    field_path: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    original_value: Annotated[str, StringConstraints(max_length=256)] | None
    candidate_exact: Rational | None = None
    unit: Annotated[str, StringConstraints(max_length=64)] | None = None
    source_asset_id: Identifier
    locator: SourceLocator
    method: Literal["gemini_vision", "manual"] = "gemini_vision"
    grounding: Literal["unreviewed_visual", "human_reviewed", "human_entered"] = "unreviewed_visual"
    ambiguity: ShortText | None = None


class IntakeProposalBody(StrictModel):
    source_asset_id: Identifier
    source_digest: Digest
    current_revision_id: Identifier | None = None
    fields: list[IntakeField] = Field(max_length=50)
    diagnostics: list[FieldDiagnostic] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def source_and_field_scope(self) -> "IntakeProposalBody":
        if any(field.source_asset_id != self.source_asset_id for field in self.fields):
            raise ValueError("Every proposed field must refer to the admitted source")
        if len({field.field_path for field in self.fields}) != len(self.fields):
            raise ValueError("A proposal cannot silently overwrite duplicate field paths")
        return self


class IntakeProposalRecordBody(IntakeProposalBody):
    """Server-persisted intake proposal; metadata is never provider output."""
    provider_attempt_id: Identifier
    review_state: Literal["unaccepted"] = "unaccepted"


class ProviderConsent(StrictModel):
    provider: Literal["gemini"] = "gemini"
    model: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    source_asset_ids: list[Identifier] = Field(default_factory=list, max_length=1)
    include_notes: bool
    include_existing_values: bool
    accepted: ExplicitTrue


class IntakeRequest(StrictModel):
    source_id: Identifier
    current_revision_id: Identifier | None = None
    existing_values: dict[str, str] = Field(default_factory=dict, max_length=50)
    notes: Annotated[str, StringConstraints(max_length=4000)] = ""
    consent: ProviderConsent

    @model_validator(mode="after")
    def disclosed_payload(self) -> "IntakeRequest":
        if self.consent.source_asset_ids != [self.source_id]:
            raise ValueError("Consent must disclose the exact selected source")
        if self.notes and not self.consent.include_notes:
            raise ValueError("Typed notes are not included in the provider consent")
        if self.existing_values and not self.consent.include_existing_values:
            raise ValueError("Existing values are not included in the provider consent")
        if any(len(key) > 256 or len(value) > 1000 for key, value in self.existing_values.items()):
            raise ValueError("Existing field context exceeds the admitted limit")
        return self


class ReviewedField(StrictModel):
    field_path: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    value: Annotated[str, StringConstraints(min_length=1, max_length=256)]
    correction_reason: ShortText | None = None
    origin: Literal["confirmed_transcription", "corrected_transcription", "human_assumption"]

    @model_validator(mode="after")
    def correction_provenance(self) -> "ReviewedField":
        if self.origin != "confirmed_transcription" and not self.correction_reason:
            raise ValueError("A correction or human assumption must include its reason")
        return self


class IntakeReviewRequest(StrictModel):
    expected_proposal_digest: Digest
    reviewed_fields: list[ReviewedField] = Field(min_length=1, max_length=50)
    resolved_diagnostics: list[Annotated[str, StringConstraints(min_length=1, max_length=384)]] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def unique_reviewed_fields(self) -> "IntakeReviewRequest":
        if len({field.field_path for field in self.reviewed_fields}) != len(self.reviewed_fields):
            raise ValueError("Each field may be reviewed only once per revision")
        return self


class AssistantTurnRequest(StrictModel):
    operation: Literal["interpret_design", "interpret_observation", "explain"]
    client_operation_id: Identifier
    expected_conversation_revision: int = Field(ge=0, le=9007199254740991)
    problem_id: Identifier | None = None
    run_id: Identifier | None = None
    suggestion_id: Identifier | None = None
    text: Annotated[str, StringConstraints(min_length=1, max_length=4000)]
    source_asset_ids: list[Identifier] = Field(default_factory=list, max_length=1)
    consent: ProviderConsent | None = None
    context: dict[str, str] = Field(default_factory=dict, max_length=32)

    @model_validator(mode="after")
    def bounded_context(self) -> "AssistantTurnRequest":
        if sum(len(key) + len(value) for key, value in self.context.items()) > 16000:
            raise ValueError("Assistant context exceeds 16000 characters")
        if self.consent is not None and self.source_asset_ids != self.consent.source_asset_ids:
            raise ValueError("Assistant sources must match the disclosed consent scope")
        return self


class GroundedExplanation(StrictModel):
    fact_ids: list[Identifier] = Field(max_length=32)
    text: ShortText
    next_action: Literal["stop", "clarify", "review_design", "review_observation", "review_plan"]
    clarification_fields: list[Annotated[str, StringConstraints(max_length=256)]] = Field(default_factory=list, max_length=16)


VerificationState = Literal["not_checked", "valid", "invalid", "inconclusive", "unsupported", "failed"]
BindingState = Literal["matches", "mismatch", "not_supplied"]
ReplayState = Literal["not_run", "running", "passed", "failed", "unsupported"]
ScientificOutcome = Literal["certified_counterexample", "numerical_candidate", "no_counterexample_found", "inconclusive", "unsupported", "failed"]


class ArtifactReference(StrictModel):
    id: Identifier
    sha256: Digest
    byte_size: int = Field(ge=1, le=4194304)
    media_type: Annotated[str, StringConstraints(min_length=1, max_length=128)]


class CandidateReference(StrictModel):
    id: Identifier
    parameter_vector: CandidateVector
    problem_id: Identifier
    problem_digest: Digest
    observable: Literal["concentration"] = "concentration"
    checked_horizon: Rational | None = None
    verification: VerificationState = "not_checked"
    artifact_ids: list[Identifier] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def candidate_evidence(self) -> "CandidateReference":
        if self.checked_horizon is not None and Fraction(self.checked_horizon) < 0:
            raise ValueError("Checked horizon cannot be negative")
        if self.verification == "valid" and (self.checked_horizon is None or not self.artifact_ids):
            raise ValueError("A checked candidate requires its horizon and evidence artifacts")
        return self


class VerificationRecord(StrictModel):
    checker_name: Identifier
    checker_version: Annotated[str, StringConstraints(min_length=1, max_length=128)]
    artifact_id: Identifier
    artifact_sha256: Digest
    proposition: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    verification: VerificationState
    expected_binding: BindingState
    expected_problem_digest: Digest
    observed_problem_digest: Digest | None = None

    @model_validator(mode="after")
    def binding_is_consistent(self) -> "VerificationRecord":
        if self.expected_binding == "matches" and self.observed_problem_digest != self.expected_problem_digest:
            raise ValueError("A matching binding requires equal observed and externally expected identities")
        if self.expected_binding == "mismatch" and (self.observed_problem_digest is None or self.observed_problem_digest == self.expected_problem_digest):
            raise ValueError("A mismatch requires a distinct observed problem identity")
        return self


class ScientificResult(StrictModel):
    scientific_outcome: ScientificOutcome
    verification: VerificationState
    expected_binding: BindingState
    replay: ReplayState
    reason_code: Identifier
    problem_id: Identifier
    problem_digest: Digest | None = None
    candidates: list[CandidateReference] = Field(default_factory=list, max_length=16)
    artifacts: list[ArtifactReference] = Field(default_factory=list, max_length=16)
    verification_record: VerificationRecord | None = None

    @model_validator(mode="after")
    def evidence_axes(self) -> "ScientificResult":
        record = self.verification_record
        if self.verification == "valid" and record is None:
            raise ValueError("A valid result requires a named verification record")
        if record is not None:
            if record.verification != self.verification or record.expected_binding != self.expected_binding:
                raise ValueError("Result axes must agree with the verification record")
            if self.problem_digest != record.expected_problem_digest:
                raise ValueError("The verification record must bind this result's expected problem")
            if not any(item.id == record.artifact_id and item.sha256 == record.artifact_sha256 for item in self.artifacts):
                raise ValueError("The verification record must reference an included artifact with matching bytes")
        if self.scientific_outcome == "certified_counterexample" and not (self.verification == "valid" and self.expected_binding == "matches" and self.candidates):
            raise ValueError("A certified counterexample requires matched valid evidence and a named candidate")
        if any(candidate.problem_id != self.problem_id or (self.problem_digest is not None and candidate.problem_digest != self.problem_digest) for candidate in self.candidates):
            raise ValueError("Candidate references must belong to the same reviewed problem")
        return self


class DesignOption(StrictModel):
    time: Rational
    state: Literal["evaluated", "skipped", "failed", "unavailable"]
    reason_code: Identifier
    exact_margin: Rational | None = None


class DesignResult(StrictModel):
    design_tier: Literal["numerical_guidance", "checked_pair_separation", "no_separation_established", "unavailable"]
    verification: VerificationState
    replay: ReplayState
    reason_code: Identifier
    selected_time: Rational | None = None
    options: list[DesignOption] = Field(min_length=1, max_length=64)
    algorithm: Annotated[str, StringConstraints(min_length=1, max_length=128)] | None = None
    candidate_ids: list[Identifier] = Field(default_factory=list, max_length=2)
    future_hard_allowance: Rational | None = None
    artifacts: list[ArtifactReference] = Field(default_factory=list, max_length=16)
    verification_record: VerificationRecord | None = None

    @model_validator(mode="after")
    def checked_scope(self) -> "DesignResult":
        if len({option.time for option in self.options}) != len(self.options):
            raise ValueError("Each reviewed time appears once in a suggestion")
        selected = next((option for option in self.options if option.time == self.selected_time), None)
        if self.selected_time is not None and (selected is None or selected.state != "evaluated"):
            raise ValueError("Only an actually evaluated option may be selected")
        if self.verification == "valid" and self.verification_record is None:
            raise ValueError("A valid suggestion requires a named verification record")
        if self.design_tier == "checked_pair_separation":
            record = self.verification_record
            if (self.verification != "valid" or self.replay != "passed" or record is None
                    or record.verification != "valid" or record.expected_binding != "matches"
                    or selected is None or selected.exact_margin is None or Fraction(selected.exact_margin) <= 0
                    or len(set(self.candidate_ids)) != 2 or self.future_hard_allowance is None
                    or Fraction(self.future_hard_allowance) <= 0 or not self.algorithm):
                raise ValueError("Checked pair separation requires positive exact margin, named pair/allowance, matching check and fresh replay")
            if not any(item.id == record.artifact_id and item.sha256 == record.artifact_sha256 for item in self.artifacts):
                raise ValueError("Checked suggestion must retain the verified artifact")
        return self


PUBLIC_SCHEMAS = {
    cls.__name__: cls
    for cls in (
        ApiError, WorkspaceCreateRequest, CancelRequest, DecimalInputRequest, ReportRequest,
        DatasetBody, ProblemBody, PlanBody, CreatePlanRequest, ApprovalRequest, AgentProviderConsent,
        StartRunRequest, DesignRequestBody, DesignPlanBody, ObservationProposalBody,
        ObservationReviewRequest, SourceAssetMetadata, IntakeProposalBody, IntakeProposalRecordBody, IntakeRequest,
        IntakeReviewRequest, AssistantTurnRequest, GroundedExplanation, ScientificResult,
        VerificationRecord, DesignResult,
    )
}
