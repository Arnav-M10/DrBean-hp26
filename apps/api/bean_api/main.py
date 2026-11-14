"""Authenticated DB-SC-1/GF-2 application API. Start on loopback by default."""

from __future__ import annotations

import hashlib
import os
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Header, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError

from .auth import AuthenticationError, principal
from .canonical import canonical_bytes, parse_decimal
from .config import Settings
from .contracts import (
    AgentProviderConsent, ApprovalRequest, AssistantTurnRequest, CreatePlanRequest, DatasetBody,
    DecimalInputRequest, DesignRequestBody, IntakeRequest, IntakeReviewRequest, ObservationProposalBody,
    ObservationReviewRequest, ProblemBody, StartRunRequest, WorkspaceCreateRequest,
)
from .conversation import ConversationService
from .http import RequestBoundary, error_body
from .intake import IntakeService, SourceService
from .ledger import LedgerBudgetExceeded, ProviderLedger
from .providers import GeminiProvider, ProviderConfig, ProviderFailure
from .science import UnavailableAdapter
from .store import Store
from .workflow import DomainError, Workflow

PREFIX = "/api/bean/v1"
Actor = Annotated[str, Depends(principal)]
OperationKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]


def provider_config_from_env() -> ProviderConfig:
    return ProviderConfig(
        api_key=os.getenv("GEMINI_API_KEY"), model=os.getenv("GEMINI_MODEL"),
        account_gate_passed=os.getenv("BEAN_GEMINI_ACCOUNT_GATE") == "approved",
        account_decision_id=os.getenv("BEAN_GEMINI_ACCOUNT_DECISION_ID"),
        image_token_upper_bound=int(os.environ["BEAN_GEMINI_IMAGE_TOKEN_BOUND"]) if os.getenv("BEAN_GEMINI_IMAGE_TOKEN_BOUND") else None,
        max_input_tokens=int(os.getenv("BEAN_GEMINI_MAX_INPUT_TOKENS", "16000")),
        max_output_tokens=int(os.getenv("BEAN_GEMINI_MAX_OUTPUT_TOKENS", "2048")),
    )


def create_app(settings: Settings | None = None, *, provider=None, adapter=None) -> FastAPI:
    settings = settings or Settings.from_env()
    store = Store(settings.database_path)
    workflow = Workflow(store)
    ledger = ProviderLedger(store)
    provider = provider or GeminiProvider(provider_config_from_env(), ledger)
    adapter = adapter or UnavailableAdapter()
    sources = SourceService(workflow, settings.blob_dir)
    intake = IntakeService(workflow, sources, provider)
    conversation = ConversationService(workflow, provider, sources)
    app = FastAPI(title="Dr. Bean research API", version="DB-SC-1", description="GF-2 policy. Explicit local SQLite lane. Scientific capabilities are reported at /capabilities.")
    app.state.settings, app.state.workflow, app.state.ledger = settings, workflow, ledger
    app.state.provider, app.state.adapter = provider, adapter
    app.add_middleware(RequestBoundary, max_json_bytes=settings.max_json_bytes, max_upload_bytes=settings.max_upload_bytes)

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError):
        return JSONResponse(error_body(request.state.request_id, exc.code, exc.message, field_paths=exc.field_paths,
                                       retryable=exc.retryable, current_revision_id=exc.current_revision_id), status_code=exc.status)

    @app.exception_handler(AuthenticationError)
    async def auth_error(request: Request, exc: AuthenticationError):
        return JSONResponse(error_body(request.state.request_id, exc.code, exc.message), status_code=exc.status,
                            headers={"WWW-Authenticate": "Bearer"} if exc.status == 401 else {})

    @app.exception_handler(RequestValidationError)
    @app.exception_handler(ValidationError)
    async def validation_error(request: Request, exc):
        paths = [".".join(str(part) for part in issue["loc"] if part != "body") for issue in exc.errors()][:50]
        return JSONResponse(error_body(request.state.request_id, "field_validation_failed",
                                       "Review the indicated fields against the versioned schema.", field_paths=paths), status_code=422)

    @app.exception_handler(ProviderFailure)
    async def provider_error(request: Request, exc: ProviderFailure):
        return JSONResponse(error_body(request.state.request_id, exc.code,
                                       "The provider operation could not complete. Review configuration, retry later, or continue manually.",
                                       retryable=exc.retryable), status_code=503)

    @app.exception_handler(LedgerBudgetExceeded)
    async def budget_error(request: Request, exc: LedgerBudgetExceeded):
        return JSONResponse(error_body(request.state.request_id, "provider_budget_exhausted",
                                       "The shared provider budget cannot admit this request. Continue manually."), status_code=409)

    @app.get("/healthz")
    def health():
        return {"service": "dr-bean", "status": "ready", "contract_version": "DB-SC-1"}

    @app.get(PREFIX + "/capabilities")
    def capabilities():
        return {"contract_version": "DB-SC-1", "policy_version": "GF-2", "storage": "local_sqlite",
                "auth": "server_bearer", "manual_review": True,
                "source_intake": {"media_types": ["image/png", "image/jpeg"], "max_assets": 1,
                                  "max_bytes": 5242880, "max_pixels": 12000000, "max_fields": 50,
                                  "retention": "retain", "pdf": False},
                "model_templates": [{"id": "two_rate_concentration", "schema_implemented": True,
                                     "scientific_adapter_qualified": bool(adapter.capabilities().get("verified_in_environment")),
                                     "units": {"time": "h", "concentration": "mg/L", "rates": "1/h"},
                                     "initial_concentration": "0/1", "rate_order": "ke_lt_ka", "target_interval": "closed"}],
                "science": adapter.capabilities(), "gemini": provider.capabilities(),
                "deepagents": {"implemented": True, "configured": bool(provider.capabilities().get("configured")),
                               "reachable": None, "verified_in_environment": False},
                "transport": {"web": True, "photon": False}}

    @app.post(PREFIX + "/exact/decimal")
    def exact_decimal(body: DecimalInputRequest, actor: Actor):
        try:
            exact = parse_decimal(body.value)
        except ValueError:
            raise DomainError("invalid_decimal", "Use a bounded finite decimal string.", 422, ["value"]) from None
        return {"original": body.value, "exact": exact}

    @app.post(PREFIX + "/workspaces", status_code=201)
    def create_workspace(body: WorkspaceCreateRequest, actor: Actor):
        return workflow.create_workspace(actor, body.name)

    @app.get(PREFIX + "/workspaces")
    def workspaces(actor: Actor):
        return workflow.list_workspaces(actor)

    @app.get(PREFIX + "/workspaces/{workspace_id}")
    def workspace(workspace_id: str, actor: Actor):
        return workflow.workspace(actor, workspace_id)

    @app.post(PREFIX + "/workspaces/{workspace_id}/datasets", status_code=201)
    def create_dataset(workspace_id: str, body: DatasetBody, actor: Actor, key: OperationKey):
        return workflow.create_dataset(actor, workspace_id, body, key)

    @app.post(PREFIX + "/workspaces/{workspace_id}/problems", status_code=201)
    def create_problem(workspace_id: str, body: ProblemBody, actor: Actor, key: OperationKey):
        return workflow.create_problem(actor, workspace_id, body, key)

    @app.post(PREFIX + "/workspaces/{workspace_id}/provider-consents", status_code=201)
    def provider_consent(workspace_id: str, body: AgentProviderConsent, actor: Actor, key: OperationKey):
        return workflow.create_provider_consent(actor, workspace_id, body, key)

    @app.post(PREFIX + "/workspaces/{workspace_id}/plans", status_code=201)
    def create_plan(workspace_id: str, body: CreatePlanRequest, actor: Actor, key: OperationKey):
        if body.expected_current_revision_id != body.plan.problem_id:
            raise DomainError("stale_revision", "The preview must name the reviewed problem revision.")
        return workflow.create_plan(actor, workspace_id, body.plan, key)

    @app.post(PREFIX + "/plans/{plan_id}/approvals", status_code=201)
    def approve_plan(plan_id: str, body: ApprovalRequest, actor: Actor, key: OperationKey):
        return workflow.approve_plan(actor, plan_id, body.expected_current_revision_id, body.expected_plan_digest, key)

    @app.post(PREFIX + "/plans/{plan_id}/runs", status_code=202)
    def start_run(plan_id: str, body: StartRunRequest, actor: Actor, key: OperationKey):
        plan = workflow.get(actor, plan_id, "plan")
        if body.expected_plan_digest != plan["digest"]:
            raise DomainError("binding_mismatch", "The run request must match the exact approved plan.")
        return workflow.start_run(actor, plan_id, body.approval_id, key)

    @app.get(PREFIX + "/runs/{run_id}")
    def get_run(run_id: str, actor: Actor):
        return workflow.get_run(actor, run_id)

    @app.post(PREFIX + "/runs/{run_id}/cancel", status_code=202)
    def cancel(run_id: str, actor: Actor, key: OperationKey):
        workflow.get_run(actor, run_id)
        return workflow.cancel_run(actor, run_id, key)

    @app.post(PREFIX + "/runs/{run_id}/design-proposals", status_code=201)
    def design_proposal(run_id: str, body: DesignRequestBody, actor: Actor, key: OperationKey):
        return workflow.create_design_plan(actor, run_id, body, key)

    @app.post(PREFIX + "/design-plans/{plan_id}/approvals", status_code=201)
    def approve_design(plan_id: str, body: ApprovalRequest, actor: Actor, key: OperationKey):
        return workflow.approve_design_plan(actor, plan_id, body.expected_current_revision_id, body.expected_plan_digest, key)

    @app.post(PREFIX + "/design-plans/{plan_id}/jobs", status_code=202)
    def start_design(plan_id: str, body: StartRunRequest, actor: Actor, key: OperationKey):
        plan = workflow.get(actor, plan_id, "design_plan")
        if body.expected_plan_digest != plan["digest"]:
            raise DomainError("binding_mismatch", "The job request must match the exact approved design.")
        return workflow.start_design_job(actor, plan_id, body.approval_id, key)

    @app.get(PREFIX + "/design-jobs/{job_id}")
    def get_design(job_id: str, actor: Actor):
        return workflow.get_design_job(actor, job_id)

    @app.post(PREFIX + "/design-jobs/{job_id}/cancel", status_code=202)
    def cancel_design(job_id: str, actor: Actor, key: OperationKey):
        workflow.get_design_job(actor, job_id)
        return workflow.cancel_run(actor, job_id, key)

    @app.post(PREFIX + "/workspaces/{workspace_id}/observation-proposals", status_code=201)
    def observation(workspace_id: str, body: ObservationProposalBody, actor: Actor, key: OperationKey):
        return workflow.create_observation_proposal(actor, workspace_id, body, key)

    @app.post(PREFIX + "/observation-proposals/{proposal_id}/review", status_code=201)
    def review_observation(proposal_id: str, body: ObservationReviewRequest, actor: Actor, key: OperationKey):
        return workflow.review_observation(actor, proposal_id, body, key)

    @app.post(PREFIX + "/workspaces/{workspace_id}/source-assets", status_code=201)
    async def upload_source(workspace_id: str, request: Request, actor: Actor, key: OperationKey,
                            origin: Literal["synthetic", "public"] = Query(...), retention: Literal["retain"] = Query(...)):
        from starlette.concurrency import run_in_threadpool
        raw = await request.body()
        return await run_in_threadpool(sources.admit, actor, workspace_id, raw,
                                      request.headers.get("content-type", "").split(";")[0], origin, retention, key)

    @app.get(PREFIX + "/source-assets/{source_id}")
    def source_metadata(source_id: str, actor: Actor):
        return sources.public_record(workflow.get(actor, source_id, "source_asset"))

    @app.get(PREFIX + "/source-assets/{source_id}/content")
    def source_content(source_id: str, actor: Actor):
        record, content = sources.read(actor, source_id)
        return Response(content, media_type=record["body"]["observed_media_type"],
                        headers={"X-Artifact-SHA256": record["body"]["sha256"], "Content-Disposition": "inline"})

    @app.post(PREFIX + "/workspaces/{workspace_id}/intake-proposals", status_code=201)
    async def intake_proposal(workspace_id: str, body: IntakeRequest, actor: Actor, key: OperationKey):
        return await intake.create(actor, workspace_id, body, key)

    @app.post(PREFIX + "/workspaces/{workspace_id}/intake-proposals/{proposal_id}/review", status_code=201)
    def intake_review(workspace_id: str, proposal_id: str, body: IntakeReviewRequest, actor: Actor, key: OperationKey):
        return intake.review(actor, workspace_id, proposal_id, body, key)

    @app.post(PREFIX + "/workspaces/{workspace_id}/assistant-turns", status_code=201)
    async def assistant_turn(workspace_id: str, body: AssistantTurnRequest, actor: Actor, key: OperationKey):
        if key != body.client_operation_id:
            raise DomainError("operation_key_mismatch", "The header and client operation identity must agree.", 422)
        return await conversation.submit(actor, workspace_id, body, key)

    @app.get(PREFIX + "/workspaces/{workspace_id}/records")
    def records(workspace_id: str, actor: Actor, kind: str = Query(..., max_length=64)):
        return [sources.public_record(record) if record["kind"] == "source_asset" else record
                for record in workflow.list_records(actor, workspace_id, kind)]

    @app.get(PREFIX + "/records/{record_id}")
    def record(record_id: str, actor: Actor):
        result = workflow.get(actor, record_id)
        return sources.public_record(result) if result["kind"] == "source_asset" else result

    @app.get(PREFIX + "/workspaces/{workspace_id}/provider-attempts")
    def provider_attempts(workspace_id: str, actor: Actor):
        workflow.authorize(actor, workspace_id)
        return ledger.list_attempts(actor, workspace_id)

    @app.get(PREFIX + "/workspaces/{workspace_id}/activity")
    def activity(workspace_id: str, actor: Actor):
        return workflow.metrics(actor, workspace_id)

    @app.post(PREFIX + "/runs/{run_id}/reports", status_code=201)
    def report_create(run_id: str, actor: Actor, key: OperationKey):
        return workflow.create_report(actor, run_id, key)

    @app.get(PREFIX + "/reports/{report_id}")
    def get_report(report_id: str, actor: Actor):
        return workflow.get(actor, report_id, "report")

    @app.get(PREFIX + "/reports/{report_id}/download")
    def report_download(report_id: str, actor: Actor):
        report = workflow.get(actor, report_id, "report")
        content = canonical_bytes(report)
        return Response(content, media_type="application/json", headers={
            "Content-Disposition": f'attachment; filename="dr-bean-{report_id}.json"',
            "X-Artifact-SHA256": hashlib.sha256(content).hexdigest()})

    @app.get(PREFIX + "/artifacts/{artifact_id}")
    def artifact(artifact_id: str, actor: Actor):
        record = workflow.get(actor, artifact_id)
        if record["kind"] not in {"evidence", "suggestion", "report"}:
            raise DomainError("not_found", "Artifact was not found.", 404)
        content = canonical_bytes(record)
        return Response(content, media_type="application/json", headers={
            "Content-Disposition": f'attachment; filename="dr-bean-{artifact_id}.json"',
            "X-Artifact-SHA256": hashlib.sha256(content).hexdigest()})

    return app
