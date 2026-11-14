"""Ordinary authenticated research routes; no raw graph resume endpoint."""
from fastapi import Query

from .main import Actor, OperationKey, PREFIX
from .research import ResearchService
from .research_contracts import (
    ResearchAdvance, ResearchCancel, ResearchCreate, ResearchDecision, ResearchEventsPage,
    ResearchInputReview, ResearchObservation, ResearchProviderConsent, ResearchReconcile,
    ResearchSessionList, ResearchSnapshot,
)
from .research_runtime import research_capabilities
from .workflow import DomainError


def register_research_routes(app):
    service = ResearchService(app.state.workflow, live_enabled=app.state.settings.research_mode == "live")
    app.state.research = service

    def current(actor, accepted):
        # The journal retains the original accepted operation response. Return
        # its current authorized view, including after an older schema's cached
        # acknowledgement. This neither rewrites history nor dispatches work.
        return service.get(actor, accepted["id"])

    @app.post(PREFIX + "/workspaces/{workspace_id}/research-sessions", response_model=ResearchSnapshot)
    def create(workspace_id: str, body: ResearchCreate, actor: Actor, key: OperationKey):
        caps = research_capabilities(app.state.settings, app.state.provider.config)
        # Saving a question/context never dispatches a model or scientific job.
        # It remains useful while the graph or scientific runtime is unavailable.
        if app.state.settings.research_mode == "disabled":
            raise DomainError("research_unavailable", "research_disabled", 503)
        if body.mode != app.state.settings.research_mode:
            raise DomainError("research_mode_mismatch", "Choose the explicitly configured research mode.", 409)
        if body.mode == "live" and not caps["dispatch_enabled"]:
            raise DomainError("research_unavailable", caps["unavailable_reason"], 503)
        return current(actor, service.create(actor, workspace_id, body, key))

    @app.get(PREFIX + "/workspaces/{workspace_id}/research-sessions", response_model=ResearchSessionList)
    def listing(workspace_id: str, actor: Actor):
        return {"items": service.list(actor, workspace_id)}

    @app.get(PREFIX + "/research-sessions/{session_id}", response_model=ResearchSnapshot)
    def read(session_id: str, actor: Actor):
        return service.get(actor, session_id)

    @app.post(PREFIX + "/research-sessions/{session_id}/advance", response_model=ResearchSnapshot)
    def advance(session_id: str, body: ResearchAdvance, actor: Actor, key: OperationKey):
        service.get(actor, session_id)  # Authorize before reporting feature state.
        caps = research_capabilities(app.state.settings, app.state.provider.config)
        if not caps["dispatch_enabled"]:
            raise DomainError("research_unavailable", caps["unavailable_reason"], 503)
        return current(actor, service.advance(actor, session_id, body, key))

    @app.post(PREFIX + "/research-sessions/{session_id}/decisions", response_model=ResearchSnapshot)
    def decision(session_id: str, body: ResearchDecision, actor: Actor, key: OperationKey):
        return current(actor, service.decide(actor, session_id, body, key))

    @app.post(PREFIX + "/research-sessions/{session_id}/reconcile", response_model=ResearchSnapshot)
    def reconcile(session_id: str, body: ResearchReconcile, actor: Actor, key: OperationKey):
        return current(actor, service.reconcile(actor, session_id, body, key))

    @app.post(PREFIX + "/research-sessions/{session_id}/observations", response_model=ResearchSnapshot)
    def observation(session_id: str, body: ResearchObservation, actor: Actor, key: OperationKey):
        return current(actor, service.accept_observation(actor, session_id, body, key))

    @app.post(PREFIX + "/research-sessions/{session_id}/inputs", response_model=ResearchSnapshot)
    def inputs(session_id: str, body: ResearchInputReview, actor: Actor, key: OperationKey):
        return current(actor, service.adopt_inputs(actor, session_id, body, key))

    @app.post(PREFIX + "/research-sessions/{session_id}/provider-consents")
    def consent(session_id: str, body: ResearchProviderConsent, actor: Actor, key: OperationKey):
        if body.model != app.state.provider.config.model:
            raise DomainError("provider_model_mismatch", "Consent must name the actual configured model.", 409)
        return service.consent(actor, session_id, body, key)

    @app.post(PREFIX + "/research-sessions/{session_id}/cancel", response_model=ResearchSnapshot)
    def cancel(session_id: str, body: ResearchCancel, actor: Actor, key: OperationKey):
        return current(actor, service.cancel(actor, session_id, key))

    @app.get(PREFIX + "/research-sessions/{session_id}/events", response_model=ResearchEventsPage)
    def events(session_id: str, actor: Actor, after: int = Query(default=-1, ge=-1, le=9_007_199_254_740_991)):
        return {"items": service.events(actor, session_id, after)}
