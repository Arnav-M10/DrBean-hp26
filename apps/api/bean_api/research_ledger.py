"""Atomic research admission into the existing physical provider ledger.

The model gateway reserves once through this wrapper. Logical graph admission
is separate. There is no SDK, additional store, automatic grant or refund here.
"""
from __future__ import annotations

from dataclasses import dataclass
import json

from .ledger import LedgerBudgetExceeded, ProviderLedger, _accounting
from .research_contracts import SESSION_POLICY, ResearchRuntimeContext
from .workflow import DomainError, _hash


@dataclass(frozen=True)
class ResearchModelContext:
    runtime: ResearchRuntimeContext
    consent_id: str
    model: str
    input_digest: str
    context_digest: str
    source_digests: tuple[str, ...] = ()

    def checked_dict(self):
        return {"actor_id": self.runtime.actor_id, "workspace_id": self.runtime.workspace_id,
            "operation_id": self.runtime.operation_id, "research_session_id": self.runtime.research_session_id,
            "action_id": self.runtime.action_id, "consent_id": self.consent_id, "model": self.model,
            "input_digest": self.input_digest, "context_digest": self.context_digest, "source_digests": list(self.source_digests)}


class ResearchLedger(ProviderLedger):
    session_accounting_version = SESSION_POLICY

    def __init__(self, base, service, runtime, *, model, controlled_transport=False):
        # Retain exactly the same store/global ceilings and all historical rows.
        super().__init__(base.store, request_cap=base.request_cap,
            input_token_cap=base.input_token_cap, output_token_cap=base.output_token_cap)
        self.service, self.runtime, self.model = service, runtime, model
        self.controlled_transport = controlled_transport

    def _validate_research_attempt(self, conn, context, operation, encoded, reserved_in, reserved_out):
        try:
            session, action = self.service.assert_lease(conn, self.runtime)
        except DomainError as exc:
            raise LedgerBudgetExceeded(exc.code) from exc
        required = {"actor_id": self.runtime.actor_id, "workspace_id": self.runtime.workspace_id,
            "operation_id": self.runtime.operation_id, "research_session_id": session["id"],
            "action_id": action["id"], "consent_id": session["consent_id"], "model": self.model,
            "input_digest": _hash(self.service.root_context(conn, session)),
            "context_digest": self.service.provider_scope(conn, session)["context_digest"],
            "source_digests": [ref["sha256"] for ref in json.loads(session["source_refs"])]}
        if context != required or not session["consent_id"] or operation["id"] != action["operation_id"]:
            raise LedgerBudgetExceeded("research_provider_context_mismatch")
        if session["mode"] != "live" and not self.controlled_transport:
            raise LedgerBudgetExceeded("research_provider_mode_mismatch")
        consent = self.service.workflow._get(conn, self.runtime.actor_id, session["consent_id"], "research_provider_consent")
        body = consent["body"]
        if (consent["created_by"] != self.runtime.actor_id or body.get("accepted") is not True
                or body.get("research_session_id") != session["id"] or body.get("model") != self.model
                or body.get("input_digest") != required["input_digest"] or body.get("context_digest") != required["context_digest"]
                or body.get("source_digests") != required["source_digests"]):
            raise LedgerBudgetExceeded("research_provider_consent_mismatch")
        rows = conn.execute("SELECT p.metadata,p.response_metadata FROM provider_attempts p JOIN research_attempt_bindings b ON b.attempt_id=p.id WHERE b.session_id=?", (session["id"],)).fetchall()
        incoming, outgoing, malformed = _accounting(rows)
        if (malformed or session["physical_calls"] >= session["physical_allocation"]
                or incoming + reserved_in > session["input_allocation"] or outgoing + reserved_out > session["output_allocation"]
                or action["physical_calls"] >= action["logical_turns"]
                or action["physical_calls"] >= json.loads(action["budget"])["model_turns"]):
            raise LedgerBudgetExceeded("research_provider_allocation_exhausted")

    def _begin_in_transaction(self, conn, context, encoded, reserved_in, reserved_out, attempt_id):
        # Validate before invoking the shared reservation implementation. Plain
        # operations or an omitted research context cannot enter through here.
        if context.get("operation_id") != self.runtime.operation_id:
            raise LedgerBudgetExceeded("research_provider_context_mismatch")
        super()._begin_in_transaction(conn, context, encoded, reserved_in, reserved_out, attempt_id)
        conn.execute("INSERT INTO research_attempt_bindings VALUES (?,?,?,?)", (attempt_id, self.runtime.research_session_id, self.runtime.action_id, self.runtime.lease_epoch))
        conn.execute("UPDATE research_sessions SET physical_calls=physical_calls+1 WHERE id=?", (self.runtime.research_session_id,))
        conn.execute("UPDATE research_actions SET physical_calls=physical_calls+1 WHERE id=?", (self.runtime.action_id,))
