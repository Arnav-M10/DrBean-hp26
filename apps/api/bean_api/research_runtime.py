"""Actual application worker integration of A's graph and B's authority."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import threading

from .coordinator import CoordinatorFailure
from .ledger import LedgerBudgetExceeded
from .providers import ProviderFailure
from .research import ResearchService
from .research_checkpoints import ResearchCheckpointer
from .research_integration import create_application_research_coordinator
from .research_tools import ApplicationResearchPorts
from .workflow import DomainError


def research_capabilities(settings, provider_config=None):
    factory = importlib.util.find_spec("bean_api.research_controlled") is not None
    controlled = settings.research_mode == "controlled" and factory
    live = False
    if settings.research_mode == "live" and getattr(provider_config, "mode", None) == "live":
        try:
            provider_config.check_ready()
            live = True
        except Exception as error:
            from .providers import ProviderFailure
            if not isinstance(error, ProviderFailure):
                raise
    reason = None if controlled or live else "research_disabled" if settings.research_mode == "disabled" else "live_coordination_not_configured" if settings.research_mode == "live" else "controlled_policy_unavailable"
    return {"implemented": True, "registered": True, "configured": controlled or live,
        "execution_mode": "controlled" if controlled else "live" if live else "disabled", "dispatch_enabled": controlled or live,
        "contract_version": "DB-RESEARCH-1", "graph_version": "research-graph.v1",
        "checkpoint_version": "research-checkpoint.v1", "persistence": "application_sqlite",
        "review_resume": True, "unavailable_reason": reason,
        "session_allocation_required": True, "default_live_allocation": 0,
        "live_qualification": "not_run", "live_unavailable_reason": "No live qualification requests were made; each live session needs current consent and an explicit operator allocation.",
        "verified_in_environment": False, "scientific_verification": "adapter_specific",
        "auth_retention": "Research persists until administratively removed. Browser credentials expire independently; cross-device identity recovery is not implemented."}


class ResearchRunner:
    def __init__(self, workflow, settings, worker_id, *, model_factory=None, provider_config=None, ledger=None):
        self.service = ResearchService(workflow, live_enabled=settings.research_mode == "live")
        self.settings, self.worker_id = settings, worker_id
        self.model_factory = model_factory
        self.provider_config, self.ledger = provider_config, ledger

    def _factory(self, context):
        if self.model_factory is not None:
            return self.model_factory
        if context.mode == "live" and self.settings.research_mode == "live":
            from .gemini_chat_gateway import GeminiChatGateway
            from .gemini_chat_model import build_gemini_chat_model
            from .research_ledger import ResearchLedger, ResearchModelContext
            with self.service.store.read() as conn:
                session, _ = self.service.assert_lease(conn, context)
                scope = self.service.provider_scope(conn, session)
            if self.provider_config is None or self.ledger is None or not session["consent_id"]:
                raise DomainError("research_live_unavailable", "Current consent and the shared physical ledger are required.", 503)
            ledger = ResearchLedger(self.ledger, self.service, context, model=self.provider_config.model)
            gateway = GeminiChatGateway(self.provider_config, ledger)
            model_context = ResearchModelContext(context, session["consent_id"], self.provider_config.model,
                scope["root_input_digest"], scope["context_digest"], tuple(scope["source_digests"]))
            return lambda: build_gemini_chat_model(gateway=gateway, context=model_context, output_tokens=512)
        if context.mode != "controlled" or self.settings.research_mode != "controlled":
            raise DomainError("research_unavailable", "The configured research mode is not admitted.", 503)
        from .research_controlled import build_controlled_research_model
        return build_controlled_research_model

    async def execute(self, row):
        context = self.service.acquire(row["actor_id"], row["id"], self.worker_id)
        ports = ApplicationResearchPorts(self.service, context)
        saver = ResearchCheckpointer(self.service, context)
        stop = threading.Event()
        def heartbeat():
            while not stop.wait(5):
                try:
                    self.service.heartbeat(context)
                except DomainError:
                    return
        lease_thread = threading.Thread(target=heartbeat, daemon=True, name="research-lease-heartbeat")
        lease_thread.start()
        try:
            with self.service.store.read() as conn:
                _, action = self.service.assert_lease(conn, context)
                policy = json.loads(action["budget"])
            graph = await create_application_research_coordinator(context=context, ports=ports,
                checkpointer=saver, model_factory=self._factory(context), event_sink=lambda event: self.service.observe(context, event), policy=policy)
            config = {"configurable": {"thread_id": context.thread_id}}
            previous = saver.get_tuple(config)
            if previous is None:
                result = await graph.start()
            else:
                values = previous.checkpoint.get("channel_values", {})
                if action["resume_required"]:
                    result = await graph.resume(new_action=values.get("action_id") != context.action_id)
                elif values.get("research_terminal") and values.get("action_id") != context.action_id:
                    result = await graph.advance()
                else:
                    raise DomainError("research_checkpoint_reconciliation_required", "No safe committed graph continuation is available.", 409)
            if result["awaiting_child"]:
                pending = next(i for i in result["interrupts"] if i["kind"] == "canonical_scientific_child")
                self.service.release(context, "waiting_child", waiting_job_id=pending["job_id"])
            elif result["awaiting_review"]:
                self.service.release(context, "waiting_review")
            elif (result.get("terminal") or {}).get("kind") == "clarification":
                current = self.service.get(context.actor_id, context.research_session_id)
                pending = current["pending_review"]
                reading = pending and "new_observation" in pending["body"].get("fields", [])
                self.service.release(context, "waiting_observation" if reading else "waiting_review")
            else:
                self.service.release(context, "completed")
        except (DomainError, CoordinatorFailure, ProviderFailure, LedgerBudgetExceeded, asyncio.TimeoutError, ValueError, ImportError) as error:
            code = getattr(error, "code", "research_timeout" if isinstance(error, asyncio.TimeoutError) else "research_runtime_failure")
            try:
                self.service.release(context, "needs_reconciliation" if "reconcil" in code else "failed", error_code=code)
            except DomainError:
                pass
        finally:
            stop.set()
            lease_thread.join(timeout=2)

    def tick(self):
        self.service.recover()
        self.service.wake_children()
        rows = self.service.queued()
        for row in rows:
            try:
                asyncio.run(self.execute(row))
            except DomainError as error:
                # Input/lease/version refusal before acquisition must not crash
                # the scientific worker or repeatedly retry a stale action.
                with self.service.store.transaction() as conn:
                    action = self.service._action(conn, row["actor_id"], row["id"])
                    if action["state"] == "queued" and not action["lease_owner"]:
                        from .store import utc_now
                        conn.execute("UPDATE research_actions SET state='failed',error_code=?,updated_at=? WHERE id=?", (error.code, utc_now(), action["id"]))
                        conn.execute("UPDATE research_sessions SET state='failed',revision=revision+1,updated_at=? WHERE active_action_id=? AND state='queued'", (utc_now(), action["id"]))
        return len(rows)
