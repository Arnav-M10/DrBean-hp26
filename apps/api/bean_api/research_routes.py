"""Ordinary authenticated research routes; no raw graph resume endpoint."""
from fastapi import Query

from .main import Actor, OperationKey, PREFIX
from .research import ResearchService
from .research_contracts import ResearchAdvance, ResearchCreate, ResearchDecision, ResearchInputReview, ResearchObservation, ResearchProviderConsent, ResearchReconcile
from .research_runtime import research_capabilities
from .workflow import DomainError


def register_research_routes(app):
    service = ResearchService(app.state.workflow, live_enabled=app.state.settings.research_mode == "live")
    app.state.research = service

    @app.post(PREFIX + "/workspaces/{workspace_id}/research-sessions")
    def create(workspace_id: str, body: ResearchCreate, actor: Actor, key: OperationKey):
        caps = research_capabilities(app.state.settings, app.state.provider.config)
        if not caps["dispatch_enabled"]:
            raise DomainError("research_unavailable", caps["unavailable_reason"], 503)
        if body.mode != caps["execution_mode"]:
            raise DomainError("research_mode_mismatch", "Choose the explicitly configured research mode.", 409)
        return service.create(actor, workspace_id, body, key)

    @app.get(PREFIX + "/workspaces/{workspace_id}/research-sessions")
    def listing(workspace_id: str, actor: Actor):
        return {"items": service.list(actor, workspace_id)}

    @app.get(PREFIX + "/research-sessions/{session_id}")
    def read(session_id: str, actor: Actor):
        return service.get(actor, session_id)

    @app.post(PREFIX + "/research-sessions/{session_id}/advance")
    def advance(session_id: str, body: ResearchAdvance, actor: Actor, key: OperationKey):
        return service.advance(actor, session_id, body, key)

    @app.post(PREFIX + "/research-sessions/{session_id}/decisions")
    def decision(session_id: str, body: ResearchDecision, actor: Actor, key: OperationKey):
        return service.decide(actor, session_id, body, key)

    @app.post(PREFIX + "/research-sessions/{session_id}/reconcile")
    def reconcile(session_id: str, body: ResearchReconcile, actor: Actor, key: OperationKey):
        return service.reconcile(actor, session_id, body, key)

    @app.post(PREFIX + "/research-sessions/{session_id}/observations")
    def observation(session_id: str, body: ResearchObservation, actor: Actor, key: OperationKey):
        return service.accept_observation(actor, session_id, body, key)

    @app.post(PREFIX + "/research-sessions/{session_id}/inputs")
    def inputs(session_id: str, body: ResearchInputReview, actor: Actor, key: OperationKey):
        return service.adopt_inputs(actor, session_id, body, key)

    @app.post(PREFIX + "/research-sessions/{session_id}/provider-consents")
    def consent(session_id: str, body: ResearchProviderConsent, actor: Actor, key: OperationKey):
        if body.model != app.state.provider.config.model:
            raise DomainError("provider_model_mismatch", "Consent must name the actual configured model.", 409)
        return service.consent(actor, session_id, body, key)

    @app.post(PREFIX + "/research-sessions/{session_id}/cancel")
    def cancel(session_id: str, actor: Actor, key: OperationKey):
        return service.cancel(actor, session_id, key)

    @app.get(PREFIX + "/research-sessions/{session_id}/events")
    def events(session_id: str, actor: Actor, after: int = Query(default=-1, ge=-1)):
        return {"items": service.events(actor, session_id, after)}
