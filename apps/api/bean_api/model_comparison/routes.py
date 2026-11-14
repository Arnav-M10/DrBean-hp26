"""Application routes for reviewed, provider-free numerical comparisons."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Header, Path
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from ..auth import principal
from .contract import ModelComparisonRequest
from .service import ModelComparisonService, comparison_capabilities

PREFIX = "/api/bean/v1"
Actor = Annotated[str, Depends(principal)]
Identifier = Annotated[str, Path(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")]
OperationKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=128)]


def register_comparison_routes(app: FastAPI) -> ModelComparisonService:
    if getattr(app.state, "model_comparison", None) is not None:
        raise RuntimeError("Model comparison routes are already registered")
    service = ModelComparisonService(app.state.workflow)
    app.state.model_comparison = service
    router = APIRouter(prefix=PREFIX, tags=["model-comparison"])

    @router.get("/model-comparison-capabilities")
    def capabilities(actor: Actor):
        return comparison_capabilities()

    @router.post("/workspaces/{workspace_id}/model-comparisons", status_code=201)
    async def compare(workspace_id: Identifier, body: ModelComparisonRequest, actor: Actor, key: OperationKey):
        return await run_in_threadpool(service.compare, actor, workspace_id, body, key)

    @router.get("/workspaces/{workspace_id}/model-comparisons")
    def list_comparisons(workspace_id: Identifier, actor: Actor):
        return service.list(actor, workspace_id)

    @router.get("/workspaces/{workspace_id}/model-comparisons/{comparison_id}")
    def get_comparison(workspace_id: Identifier, comparison_id: Identifier, actor: Actor):
        return service.get(actor, workspace_id, comparison_id)

    @router.get("/workspaces/{workspace_id}/model-comparisons/{comparison_id}/download")
    def download(workspace_id: Identifier, comparison_id: Identifier, actor: Actor):
        data, digest = service.download(actor, workspace_id, comparison_id)
        return Response(data, media_type="application/json",
                        headers={"Content-Disposition": f'attachment; filename="{comparison_id}.json"',
                                 "X-Artifact-SHA256": digest,
                                 "Content-Security-Policy": "default-src 'none'; sandbox"})

    app.include_router(router)
    return service
