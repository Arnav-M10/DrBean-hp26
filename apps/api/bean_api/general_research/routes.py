"""HTTP routes for general research files and analyses, registered by ``register_general_routes``.

All routes live under ``/api/bean/v1``, use the application's existing principal
dependency for workspace authorization, and raise ``DomainError``/``ProviderFailure``
so the application's standard error envelopes apply. Object identifiers confer no
authority: every read re-checks workspace membership.
"""
from __future__ import annotations

import os
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, FastAPI, Header, Path, Query, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from ..auth import principal
from ..controlled_ledger import ControlledLedger
from ..providers import ProviderConfig
from . import limits as L
from .admission import DATA_ORIGINS, SUPPORTED_MEDIA_TYPES
from .sandbox import describe_guards
from .schemas import AnalysisEstimateRequest, ResearchAnalysisRequest
from .service import GeneralResearchService
from .transport import GeneralAnalysisTransport

PREFIX = "/api/bean/v1"
Actor = Annotated[str, Depends(principal)]
Identifier = Annotated[str, Path(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")]
PageIndex = Annotated[int, Path(ge=0, le=L.MAX_PDF_PAGES - 1)]
EXTENSIONS = {"text/csv": "csv", "text/tab-separated-values": "tsv", "application/json": "json", "text/plain": "txt",
              "text/markdown": "md", "image/png": "png", "image/jpeg": "jpg", "application/pdf": "pdf"}
CONTROLLED_MODEL = "controlled-general-analysis"


def default_transport(app: FastAPI, controlled_responder=None) -> GeneralAnalysisTransport:
    """Live when the server's single provider configuration is live; otherwise controlled or disabled."""
    config = getattr(app.state.provider, "config", None) or ProviderConfig()
    if controlled_responder is None and os.getenv("BEAN_GENERAL_ANALYSIS_MODE") == "controlled_demo":
        from .controlled import demo_responder
        controlled_responder = demo_responder
    if controlled_responder is not None:
        if config.mode == "live":
            raise ValueError("A controlled responder cannot be combined with live provider mode")
        controlled = ProviderConfig(model=CONTROLLED_MODEL, max_input_tokens=24_000, max_output_tokens=4_096,
                                    image_token_upper_bound=8_192, request_timeout_seconds=30)
        return GeneralAnalysisTransport(controlled, ControlledLedger(app.state.workflow), responder=controlled_responder)
    return GeneralAnalysisTransport(config, app.state.ledger)


def register_general_routes(app: FastAPI, *, transport: GeneralAnalysisTransport | None = None,
                            controlled_responder=None) -> GeneralResearchService:
    """Attach the general research routes and service to an application built by ``create_app``.

    Requires ``app.state.workflow``, ``app.state.settings.blob_dir``, ``app.state.provider`` (its
    ``ProviderConfig``) and ``app.state.ledger`` (the shared global ledger), plus the application's
    DomainError/ProviderFailure/LedgerBudgetExceeded handlers. Call once, before serving.
    """
    if getattr(app.state, "general_research", None) is not None:
        raise RuntimeError("General research routes are already registered")
    service = GeneralResearchService(app.state.workflow, app.state.settings.blob_dir,
                                     transport or default_transport(app, controlled_responder))
    app.state.general_research = service
    router = APIRouter(prefix=PREFIX, tags=["general-research"])

    @router.get("/research-capabilities")
    def capabilities(actor: Actor):
        return general_research_capabilities(app)

    @router.post("/workspaces/{workspace_id}/research-assets", status_code=201)
    async def upload(workspace_id: Identifier, request: Request, actor: Actor,
                     origin: Annotated[str, Query(max_length=40)] = "unspecified",
                     key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=128)] = None):
        raw = await request.body()
        return await run_in_threadpool(service.admit, actor, workspace_id, raw, request.headers.get("content-type"),
                                       request.headers.get("x-source-name"), origin, key)

    @router.get("/workspaces/{workspace_id}/research-assets")
    def list_assets(workspace_id: Identifier, actor: Actor):
        return service.list_assets(actor, workspace_id)

    @router.get("/research-assets/{asset_id}")
    def asset(asset_id: Identifier, actor: Actor):
        return service.asset(actor, asset_id)

    @router.get("/research-assets/{asset_id}/content")
    def content(asset_id: Identifier, actor: Actor):
        record, data = service.content(actor, asset_id)
        body = record["body"]
        inline = body["media_type"] in ("image/png", "image/jpeg")
        fallback = f"research-asset-{body['sha256'][:12]}.{EXTENSIONS[body['media_type']]}"
        disposition = "inline" if inline else "attachment"
        disposition += f'; filename="{fallback}"'
        if body["filename"]:
            disposition += f"; filename*=UTF-8''{quote(body['filename'], safe='')}"
        return Response(data, media_type=body["media_type"] if inline or body["media_type"] == "application/pdf"
                        else "application/octet-stream",
                        headers={"Content-Disposition": disposition, "X-Artifact-SHA256": body["sha256"],
                                 "Content-Security-Policy": "default-src 'none'; sandbox"})

    @router.get("/research-assets/{asset_id}/pages/{page_index}/image")
    def page_image(asset_id: Identifier, page_index: PageIndex, actor: Actor):
        data, media_type = service.page_image(actor, asset_id, page_index)
        return Response(data, media_type=media_type,
                        headers={"Content-Disposition": "inline", "Content-Security-Policy": "default-src 'none'; sandbox"})

    @router.get("/research-assets/{asset_id}/pages/{page_index}/text")
    def page_text(asset_id: Identifier, page_index: PageIndex, actor: Actor):
        return service.page_text(actor, asset_id, page_index)

    @router.post("/workspaces/{workspace_id}/research-analysis-estimates")
    async def estimate(workspace_id: Identifier, body: AnalysisEstimateRequest, actor: Actor):
        return await run_in_threadpool(service.estimate, actor, workspace_id, body)

    @router.post("/workspaces/{workspace_id}/research-analyses", status_code=201)
    async def analyze(workspace_id: Identifier, body: ResearchAnalysisRequest, actor: Actor,
                      key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]):
        return await service.analyze(actor, workspace_id, body, key)

    @router.get("/workspaces/{workspace_id}/research-analyses")
    def list_analyses(workspace_id: Identifier, actor: Actor):
        return service.list_analyses(actor, workspace_id)

    @router.get("/research-analyses/{analysis_id}")
    def analysis(analysis_id: Identifier, actor: Actor):
        return service.analysis(actor, analysis_id)

    app.include_router(router)
    return service


def general_research_capabilities(app: FastAPI) -> dict:
    """Capability block for ``/capabilities``: available only when routes and a dispatch path are reachable."""
    service: GeneralResearchService | None = getattr(app.state, "general_research", None)
    base = {"implemented": True, "contract_version": L.CONTRACT_VERSION, "media_types": SUPPORTED_MEDIA_TYPES,
            "max_assets": L.MAX_ANALYSIS_ASSETS, "max_file_bytes": L.MAX_ASSET_BYTES,
            "max_total_bytes": L.MAX_ANALYSIS_BYTES, "max_pdf_pages": L.MAX_PDF_PAGES,
            "limits": L.public_limits(), "data_origins": list(DATA_ORIGINS)}
    if service is None:
        return {**base, "routes_registered": False, "available": False,
                "unavailable_reason": "general_routes_not_registered"}
    transport = service.transport.capabilities()
    budget = service._budget()
    reasons = {"provider_dispatch_disabled": "Gemini analysis is not enabled on this server.",
               "provider_not_configured": "Gemini is not configured on this server.",
               "provider_live_model_not_allowed": "The configured model is not on the free-tier allowlist.",
               "provider_free_tier_assertion_required": "The server owner has not asserted free-tier use."}
    reason = transport["unavailable_reason"]
    return {**base, "routes_registered": True,
            "available": True,            # file admission: uploads never contact a provider
            "upload_available": True,
            "unavailable_reason": None,
            "analysis": {"available": bool(transport["dispatch_enabled"]),
                         "reason": None if reason is None else reasons.get(reason, f"Analysis is unavailable ({reason})."),
                         **{key: transport[key] for key in (
                             "model", "execution_mode", "dispatch_enabled", "unavailable_reason", "accounting",
                             "free_tier_user_asserted", "billing_verified", "live_qualification", "max_input_tokens",
                             "max_output_tokens", "retry_policy")}},
            "budget": {"accounting": budget["accounting"],
                       "remaining": {"requests": budget["remaining_requests"],
                                     "input_tokens": budget["remaining_input_tokens"],
                                     "output_tokens": budget["remaining_output_tokens"]},
                       **{key: budget[key] for key in ("remaining_requests", "remaining_input_tokens",
                                                       "remaining_output_tokens", "billing_verified")}},
            "verification": {"general_analysis": "not_mathematically_verified",
                             "checkable_adapters": ["two_rate_concentration"],
                             "rule": "AI analysis is interpretation. Only a separately approved checker run produces "
                                     "mathematical evidence, as its own record."},
            "citations": {"normalization_version": L.CITATION_NORMALIZATION_VERSION, "bbox_space": L.BBOX_SPACE,
                          "page_index_base": 0, "page_number_base": 1},
            "parsing": {"pdf": "pypdfium2 after a bounded structural pre-scan", "ocr": False,
                        "document_scripts": "never_executed", "isolation": describe_guards()}}
