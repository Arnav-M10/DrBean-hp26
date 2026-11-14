"""Application authority for durable research; graph state grants no rights.

The journal is committed before external work. Scientific child reservation and
its journal association share one transaction. Checkpoints are a separate,
fenced projection; replaying a tool reconciles the canonical journal entry.
"""
from __future__ import annotations

import json
import time

from .research_contracts import (
    ACTION_POLICY, CHECKPOINT_VERSION, RESEARCH_VERSION, ResearchAdvance,
    ResearchBudget, ResearchCreate, ResearchDecision, ResearchEvent,
    ResearchInputReview, ResearchObservation, ResearchPlanRevision, ResearchProviderAllocation, ResearchProviderConsent,
    ResearchReconcile, ResearchRuntimeContext,
)
from .store import utc_now
from .workflow import DomainError, _hash, _id, _json

GRAPH_VERSION = "research-graph.v1"
SESSION_LIMITS = {"logical_turns": 8, "tool_calls": 24, "child_count": 4}
ENDED = {"completed", "failed", "cancelled"}


class ResearchService:
    def __init__(self, workflow, *, graph_version=GRAPH_VERSION, live_enabled=False, allocation_actor=None):
        self.workflow, self.store = workflow, workflow.store
        self.graph_version, self.live_enabled = graph_version, live_enabled
        self.allocation_actor = allocation_actor

    def _session(self, conn, actor, session_id):
        row = conn.execute("SELECT * FROM research_sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            raise DomainError("not_found", "Research session was not found.", 404)
        self.workflow.authorize(actor, row["workspace_id"], conn)
        # Workspace membership is not permission to impersonate an action owner.
        if row["actor_id"] != actor:
            raise DomainError("not_found", "Research session was not found.", 404)
        return dict(row)

    def _action(self, conn, actor, action_id):
        row = conn.execute("SELECT * FROM research_actions WHERE id=?", (action_id,)).fetchone()
        if row is None:
            raise DomainError("not_found", "Research action was not found.", 404)
        self._session(conn, actor, row["session_id"])
        return dict(row)

    def _inputs(self, conn, session):
        workspace = self.workflow.authorize(session["actor_id"], session["workspace_id"], conn)
        heads = {key: workspace[key] for key in ("current_dataset_id", "current_problem_id")}
        if heads != json.loads(session["input_heads"]):
            raise DomainError("stale_research_inputs", "Reviewed inputs changed. Rebind them explicitly before advancing.", 409,
                              current_revision_id=workspace["current_problem_id"])
        if session["problem_id"]:
            problem = self.workflow._get(conn, session["actor_id"], session["problem_id"], "problem")
            if problem["digest"] != session["problem_digest"]:
                raise DomainError("binding_mismatch", "The retained research problem digest differs.", 409)

    def _revision(self, session, expected):
        if session["revision"] != expected:
            raise DomainError("stale_research_revision", "Refresh the current research state before this action.", 409)

    def root_context(self, conn, session):
        """Immutable research origin; each scientific plan binds its own inputs."""
        creation = self.workflow._get(conn, session["actor_id"], session["id"], "research_session")
        problem_id = creation["body"]["problem_id"]
        problem = self.workflow._get(conn, session["actor_id"], problem_id, "problem") if problem_id else None
        dataset = self.workflow._get(conn, session["actor_id"], problem["body"]["dataset_id"], "dataset") if problem else None
        return {"problem": problem, "dataset": dataset, "sources": json.loads(session["source_refs"])}

    def review_view(self, conn, session, record, *, decision="pending", approval_id=None):
        effect = conn.execute("SELECT kind FROM research_effects WHERE session_id=? AND plan_id=? AND kind!='child'", (session["id"], record["id"])).fetchone()
        if effect is None:
            raise DomainError("review_not_in_scope", "The review does not belong to this research session.", 403)
        return {"review_id": record["id"], "review_digest": record["digest"], "kind": effect["kind"],
            "approval_id": approval_id, "decision": decision, "scope": {"plan_id": record["id"], "plan_digest": record["digest"],
                "input_digest": _hash(self.root_context(conn, session))}}

    def provider_scope(self, conn, session):
        input_ids = [row[0] for row in conn.execute("SELECT id FROM entities WHERE workspace_id=? AND kind IN ('research_input_review','research_observation_acceptance') AND json_extract(body,'$.research_session_id')=? ORDER BY rowid", (session["workspace_id"], session["id"]))]
        fields = ["research_objective", "reviewed_inputs", "research_plan", "retained_evidence", "source_references"]
        body = {"research_session_id": session["id"], "root_input_digest": _hash(self.root_context(conn, session)),
            "problem_id": session["problem_id"], "problem_digest": session["problem_digest"], "accepted_input_ids": input_ids,
            "source_digests": [ref["sha256"] for ref in json.loads(session["source_refs"])], "context_fields": fields}
        return {**body, "context_digest": _hash(body)}

    def _event(self, conn, session, event_type, summary="", references=(), action_id=None, observation_key=None):
        if observation_key:
            existing = conn.execute("SELECT e.body FROM research_events e JOIN research_event_observations o ON o.event_id=e.id WHERE o.session_id=? AND o.observation_key=?", (session["id"], observation_key)).fetchone()
            if existing:
                return json.loads(existing[0])
        references = list(dict.fromkeys(references))
        for reference in references:
            # Only canonical same-workspace references, never arbitrary model text.
            if conn.execute("SELECT 1 FROM jobs WHERE id=? AND workspace_id=?", (reference, session["workspace_id"])).fetchone():
                continue
            record = self.workflow._get(conn, session["actor_id"], reference)
            self.workflow._same_workspace(session["workspace_id"], record)
        sequence = conn.execute("SELECT coalesce(max(sequence),-1)+1 FROM research_events WHERE session_id=?", (session["id"],)).fetchone()[0]
        event = ResearchEvent(event_id=_id("event"), sequence=sequence,
            workspace_id=session["workspace_id"], research_session_id=session["id"],
            action_id=action_id, event_type=event_type, timestamp=utc_now(), mode=session["mode"],
            summary=summary, reference_ids=references).model_dump(mode="json")
        conn.execute("INSERT INTO research_events VALUES (?,?,?,?,?)", (event["event_id"], session["id"], action_id, sequence, _json(event)))
        if observation_key:
            conn.execute("INSERT INTO research_event_observations VALUES (?,?,?)", (session["id"], observation_key, event["event_id"]))
        return event

    def observe(self, context, event):
        if (set(event) != {"event_type", "action_id", "mode", "summary", "reference_ids", "observation_key"}
                or event["action_id"] != context.action_id or event["mode"] != context.mode
                or not isinstance(event["observation_key"], str) or len(event["observation_key"]) != 64):
            raise DomainError("invalid_research_event", "Only a bounded current-action event is accepted.", 422)
        with self.store.transaction() as conn:
            session, _ = self.assert_lease(conn, context)
            return self._event(conn, session, event["event_type"], event["summary"], event["reference_ids"],
                context.action_id, context.action_id + ":" + event["observation_key"])

    def _public(self, conn, session):
        creation = self.workflow._get(conn, session["actor_id"], session["id"], "research_session")
        plan = self.workflow._get(conn, session["actor_id"], session["plan_revision_id"], "research_plan_revision") if session["plan_revision_id"] else None
        review = self.workflow._get(conn, session["actor_id"], session["pending_review_id"]) if session["pending_review_id"] else None
        action = self._action(conn, session["actor_id"], session["active_action_id"]) if session["active_action_id"] else None
        if action:
            action = {key: action[key] for key in ("id", "state", "budget", "logical_turns", "tool_calls", "child_count", "physical_calls", "active_seconds", "waiting_job_id", "error_code")}
            action["budget"] = json.loads(action["budget"])
            action["active_seconds"] = format(action["active_seconds"], ".3f")
        children = []
        for effect in conn.execute("SELECT job_id FROM research_effects WHERE session_id=? AND job_id IS NOT NULL ORDER BY created_at,id", (session["id"],)):
            children.append(self.workflow._job(conn, session["actor_id"], effect["job_id"]))
        return {"schema_version": RESEARCH_VERSION, "id": session["id"], "workspace_id": session["workspace_id"],
            "objective": creation["body"]["objective"], "mode": session["mode"], "state": session["state"], "revision": session["revision"],
            "problem_id": session["problem_id"], "problem_digest": session["problem_digest"],
            "sources": json.loads(session["source_refs"]), "plan": plan,
            "reviewed_context": self.root_context(conn, session),
            "pending_review": review, "pending_review_digest": session["pending_review_digest"],
            "action": action, "children": children,
            "usage": {key: session[key] for key in ("logical_turns", "tool_calls", "child_count", "physical_calls")},
            "session_limits": SESSION_LIMITS, "graph_version": session["graph_version"],
            "reports": [row[0] for row in conn.execute("SELECT id FROM entities WHERE parent_id=? AND kind='report' ORDER BY created_at,id", (session["id"],))],
            "provider_disclosure": self.provider_scope(conn, session),
            "provider_allocation": {"physical_requests": session["physical_allocation"], "input_tokens": session["input_allocation"], "output_tokens": session["output_allocation"]},
            "checkpoint_version": session["checkpoint_version"], "policy_version": session["policy_version"],
            "created_at": session["created_at"], "updated_at": session["updated_at"]}

    def get(self, actor, session_id):
        with self.store.read() as conn:
            return self._public(conn, self._session(conn, actor, session_id))

    def list(self, actor, workspace_id):
        with self.store.read() as conn:
            self.workflow.authorize(actor, workspace_id, conn)
            return [self._public(conn, dict(row)) for row in conn.execute(
                "SELECT * FROM research_sessions WHERE actor_id=? AND workspace_id=? ORDER BY created_at DESC LIMIT 100", (actor, workspace_id))]

    def create(self, actor, workspace_id, request, key):
        request = ResearchCreate.model_validate(request).model_dump(mode="json")
        def create(conn):
            workspace = self.workflow.authorize(actor, workspace_id, conn)
            if request["mode"] == "live" and not self.live_enabled:
                raise DomainError("live_coordination_unavailable", "Live coordination is not enabled or allocated on this server.", 503)
            if request["problem_id"]:
                problem = self.workflow._get(conn, actor, request["problem_id"], "problem")
                self.workflow._same_workspace(workspace_id, problem)
                if problem["digest"] != request["expected_problem_digest"]:
                    raise DomainError("binding_mismatch", "Select the exact reviewed problem digest.", 422)
                if workspace["current_problem_id"] != problem["id"]:
                    raise DomainError("stale_revision", "Select the current reviewed problem.", 409)
            refs = []
            for source_id in request["source_ids"]:
                source = self.workflow._get(conn, actor, source_id)
                self.workflow._same_workspace(workspace_id, source)
                if source["kind"] not in {"source_asset", "research_asset"} or not source["body"].get("sha256"):
                    raise DomainError("unsupported_source", "This source has no admitted original-file binding. Use manual review.", 422)
                refs.append({"id": source_id, "sha256": source["body"]["sha256"]})
            if request["provider_consent_id"]:
                raise DomainError("research_consent_required", "Create the research session, then separately consent to its exact provider disclosure.", 422)
            creation = self.workflow._insert(conn, actor, workspace_id, "research_session", request)
            now = utc_now()
            conn.execute("INSERT INTO research_sessions(id,workspace_id,actor_id,mode,thread_id,graph_version,checkpoint_version,policy_version,problem_id,problem_digest,input_heads,source_refs,consent_id,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (creation["id"], workspace_id, actor, request["mode"], _id("thread"), self.graph_version, CHECKPOINT_VERSION, ACTION_POLICY,
                 request["problem_id"], request["expected_problem_digest"],
                 _json({key: workspace[key] for key in ("current_dataset_id", "current_problem_id")}), _json(refs), request["provider_consent_id"], now, now))
            return self._public(conn, self._session(conn, actor, creation["id"]))
        return self.workflow._perform(actor, workspace_id, "create:research", key, request, create)

    def consent(self, actor, session_id, request, key):
        request = ResearchProviderConsent.model_validate(request).model_dump(mode="json")
        known = self.get(actor, session_id)
        def consent(conn):
            session = self._session(conn, actor, session_id)
            scope = self.provider_scope(conn, session)
            if scope["context_digest"] != request["expected_context_digest"]:
                raise DomainError("provider_consent_mismatch", "Review the current exact source/input disclosure.", 409)
            if session["state"] in ENDED or session["state"] == "running":
                raise DomainError("research_consent_unavailable", "Consent must precede active dispatch.", 409)
            record = self.workflow._insert(conn, actor, session["workspace_id"], "research_provider_consent", {
                **scope, "input_digest": scope["root_input_digest"], "model": request["model"], "accepted": True,
                "free_tier_only": True, "billing_verified": False, "execution_approved": False}, session["id"])
            conn.execute("UPDATE research_sessions SET consent_id=? WHERE id=?", (record["id"], session_id))
            return record
        return self.workflow._perform(actor, known["workspace_id"], "consent:research:" + session_id, key, request, consent)

    def allocate_provider(self, actor, session_id, request, key):
        """Explicit operator-only grant; no browser route or automatic allocation."""
        if self.allocation_actor is None or actor != self.allocation_actor:
            raise DomainError("research_allocation_operator_required", "Provider capacity is not granted by a browser session or model.", 403)
        request = ResearchProviderAllocation.model_validate(request).model_dump(mode="json")
        known = self.get(actor, session_id)
        def allocate(conn):
            session = self._session(conn, actor, session_id)
            values = {"physical_allocation": session["physical_allocation"] + request["physical_requests"],
                "input_allocation": session["input_allocation"] + request["input_tokens"], "output_allocation": session["output_allocation"] + request["output_tokens"]}
            if session["state"] in ENDED or values["physical_allocation"] > 8 or values["input_allocation"] > 64_000 or values["output_allocation"] > 16_000:
                raise DomainError("research_allocation_exhausted", "Explicit cumulative grants must fit the versioned session ceilings.", 409)
            record = self.workflow._insert(conn, actor, session["workspace_id"], "research_provider_allocation", {**request, "research_session_id": session_id}, session_id)
            conn.execute("UPDATE research_sessions SET physical_allocation=?,input_allocation=?,output_allocation=? WHERE id=?", (*values.values(), session_id))
            return record
        return self.workflow._perform(actor, known["workspace_id"], "allocate:research:" + session_id, key, request, allocate)

    def _queue(self, conn, session, budget, *, resume_required=False):
        actor, workspace_id = session["actor_id"], session["workspace_id"]
        budget = ResearchBudget.model_validate(budget).model_dump(mode="json")
        action_record = self.workflow._insert(conn, actor, workspace_id, "research_action",
            {"session_id": session["id"], "budget": budget, "at_revision": session["revision"]}, session["id"])
        operation = self.workflow._reserve_operation(conn, actor, workspace_id, "research-runtime", action_record["id"], {"action_id": action_record["id"]})
        now = utc_now()
        conn.execute("INSERT INTO research_actions(id,session_id,operation_id,request_digest,state,budget,resume_required,created_at,updated_at) VALUES (?,?,?,?,'queued',?,?,?,?)",
            (action_record["id"], session["id"], operation["id"], action_record["digest"], _json(budget), int(resume_required), now, now))
        conn.execute("UPDATE research_sessions SET active_action_id=?,state='queued',revision=revision+1,updated_at=? WHERE id=?", (action_record["id"], now, session["id"]))
        self._event(conn, session, "resumed" if resume_required else "action_started", "A bounded research action was admitted.", [action_record["id"]], action_record["id"])

    def advance(self, actor, session_id, request, key):
        request = ResearchAdvance.model_validate(request).model_dump(mode="json")
        session = self.get(actor, session_id)
        def advance(conn):
            current = self._session(conn, actor, session_id)
            self._revision(current, request["expected_revision"])
            self._inputs(conn, current)
            if current["mode"] == "live":
                consent = self.workflow._get(conn, actor, current["consent_id"], "research_provider_consent") if current["consent_id"] else None
                if not consent or consent["body"]["context_digest"] != self.provider_scope(conn, current)["context_digest"]:
                    raise DomainError("research_provider_consent_required", "Consent to the exact current research context before live coordination.", 403)
                if current["physical_allocation"] <= current["physical_calls"]:
                    raise DomainError("research_provider_allocation_exhausted", "No explicit remaining research provider allocation is available.", 409)
            if current["state"] not in {"ready", "paused"}:
                raise DomainError("research_not_advanceable", "Use the pending review, observation or reconciliation action.", 409)
            self._queue(conn, current, request["budget"], resume_required=current["state"] == "paused")
            return self._public(conn, self._session(conn, actor, session_id))
        return self.workflow._perform(actor, session["workspace_id"], "advance:research:" + session_id, key, request, advance)

    def acquire(self, actor, action_id, owner, *, seconds=30):
        if not 1 <= seconds <= 300:
            raise ValueError("Lease lifetime must be bounded")
        with self.store.transaction() as conn:
            action = self._action(conn, actor, action_id)
            session = self._session(conn, actor, action["session_id"])
            self._inputs(conn, session)
            if action["state"] != "queued" or action["lease_owner"] or session["active_action_id"] != action_id:
                raise DomainError("research_lease_unavailable", "This action is not available for advancement.", 409)
            if session["graph_version"] != self.graph_version or session["checkpoint_version"] != CHECKPOINT_VERSION:
                raise DomainError("checkpoint_incompatible", "The retained checkpoint needs an explicit compatible runtime.", 409)
            now = time.time()
            conn.execute("UPDATE research_actions SET state='running',lease_owner=?,lease_epoch=lease_epoch+1,lease_until=?,acquired_at=?,updated_at=? WHERE id=?", (owner, now + seconds, now, utc_now(), action_id))
            conn.execute("UPDATE research_sessions SET state='running',updated_at=? WHERE id=?", (utc_now(), session["id"]))
            action = self._action(conn, actor, action_id)
            return ResearchRuntimeContext(actor, session["workspace_id"], session["id"], action_id,
                action["operation_id"], session["thread_id"], owner, action["lease_epoch"], session["mode"], session["graph_version"])

    def assert_lease(self, conn, context, *, check_inputs=True, check_deadline=True):
        session = self._session(conn, context.actor_id, context.research_session_id)
        action = self._action(conn, context.actor_id, context.action_id)
        if (session["active_action_id"] != action["id"] or session["state"] != "running" or action["state"] != "running"
                or session["thread_id"] != context.thread_id or session["graph_version"] != context.graph_version
                or session["checkpoint_version"] != context.checkpoint_version or session["policy_version"] != context.policy_version
                or action["lease_owner"] != context.lease_owner or action["lease_epoch"] != context.lease_epoch
                or action["lease_until"] is None or action["lease_until"] <= time.time()):
            raise DomainError("research_authority_revoked", "This worker no longer owns the research action.", 409)
        elapsed = action["active_seconds"] + max(0, time.time() - action["acquired_at"])
        if check_deadline and elapsed >= json.loads(action["budget"])["active_seconds"]:
            raise DomainError("research_deadline_exceeded", "The active computation deadline has expired.", 409)
        if check_inputs:
            self._inputs(conn, session)
        return session, action

    def heartbeat(self, context, seconds=30):
        with self.store.transaction() as conn:
            self.assert_lease(conn, context)
            conn.execute("UPDATE research_actions SET lease_until=? WHERE id=?", (time.time() + min(seconds, 300), context.action_id))

    def release(self, context, state, *, error_code=None, waiting_job_id=None):
        if state not in {"waiting_review", "waiting_observation", "waiting_child", "paused", "completed", "failed", "needs_reconciliation"}:
            raise ValueError("Unknown research pause/terminal state")
        with self.store.transaction() as conn:
            session, action = self.assert_lease(conn, context, check_inputs=False, check_deadline=False)
            elapsed = action["active_seconds"] + max(0, time.time() - action["acquired_at"])
            conn.execute("UPDATE research_actions SET state=?,active_seconds=?,lease_owner=NULL,lease_until=NULL,acquired_at=NULL,waiting_job_id=?,error_code=?,updated_at=? WHERE id=?",
                (state, elapsed, waiting_job_id, error_code, utc_now(), context.action_id))
            conn.execute("UPDATE research_sessions SET state=?,revision=revision+1,updated_at=? WHERE id=?", (state, utc_now(), session["id"]))
            if state in ENDED:
                conn.execute("UPDATE operations SET state=?,finished_at=?,error_code=? WHERE id=? AND state='reserved'", ("completed" if state == "completed" else "failed", utc_now(), error_code, action["operation_id"]))
                self._event(conn, session, "terminal", "Research action ended: " + state, action_id=action["id"])

    def admit(self, context, category, name=""):
        column, budget_key = {"model": ("logical_turns", "model_turns"), "tool": ("tool_calls", "tool_calls"), "child": ("child_count", "scientific_reservations")}[category]
        with self.store.transaction() as conn:
            session, action = self.assert_lease(conn, context)
            if action[column] >= json.loads(action["budget"])[budget_key] or session[column] >= SESSION_LIMITS[column]:
                raise DomainError("research_budget_exhausted", "The bounded action or cumulative session budget is exhausted.", 409)
            conn.execute(f"UPDATE research_actions SET {column}={column}+1 WHERE id=?", (action["id"],))
            conn.execute(f"UPDATE research_sessions SET {column}={column}+1 WHERE id=?", (session["id"],))
            if category == "tool":
                self._event(conn, session, "tool_requested", "Authorized scoped tool: " + name[:128], action_id=action["id"])

    def update_plan(self, context, plan):
        plan = ResearchPlanRevision.model_validate(plan).model_dump(mode="json")
        with self.store.transaction() as conn:
            session, _ = self.assert_lease(conn, context)
            for step in plan["steps"]:
                for reference in step["reference_ids"]:
                    record = self.workflow._get(conn, context.actor_id, reference)
                    self.workflow._same_workspace(context.workspace_id, record)
                if step["status"] == "completed" and any(reference.startswith(("run_", "design_job_")) for reference in step["reference_ids"]):
                    raise DomainError("invalid_plan_reference", "Use canonical evidence references to mark scientific work complete.", 422)
            previous = self.workflow._get(conn, context.actor_id, session["plan_revision_id"]) if session["plan_revision_id"] else None
            if previous and previous["body"] == plan:
                return previous
            record = self.workflow._insert(conn, context.actor_id, context.workspace_id, "research_plan_revision", plan, session["plan_revision_id"] or session["id"])
            conn.execute("UPDATE research_sessions SET plan_revision_id=?,revision=revision+1,updated_at=? WHERE id=?", (record["id"], utc_now(), session["id"]))
            self._event(conn, session, "plan_updated", "The maintained research plan was revised.", [record["id"]], context.action_id)
            return record

    def pending_review(self, context, review_id, digest, *, kind="review"):
        with self.store.transaction() as conn:
            session, _ = self.assert_lease(conn, context)
            record = self.workflow._get(conn, context.actor_id, review_id)
            self.workflow._same_workspace(context.workspace_id, record)
            if record["digest"] != digest or not conn.execute("SELECT 1 FROM research_effects WHERE session_id=? AND plan_id=?", (session["id"], review_id)).fetchone():
                raise DomainError("stale_review", "The review is not the exact prepared scope for this research session.", 409)
            decision = conn.execute("SELECT body FROM entities WHERE workspace_id=? AND kind='research_decision' AND parent_id=? ORDER BY rowid DESC", (context.workspace_id, review_id)).fetchone()
            if decision:
                body = json.loads(decision[0])
                if body["research_session_id"] == session["id"] and body["expected_review_digest"] == digest:
                    return self.review_view(conn, session, record, decision=body["decision"], approval_id=body["approval_id"])
            conn.execute("UPDATE research_sessions SET pending_review_id=?,pending_review_digest=?,revision=revision+1,updated_at=? WHERE id=?", (review_id, digest, utc_now(), session["id"]))
            self._event(conn, session, "waiting_observation" if kind == "observation" else "review_required", "Human review is required for the exact prepared scope.", [review_id], context.action_id)
            return self.review_view(conn, session, record)

    def decide(self, actor, session_id, request, key):
        request = ResearchDecision.model_validate(request).model_dump(mode="json")
        known = self.get(actor, session_id)
        def decide(conn):
            session = self._session(conn, actor, session_id)
            self._revision(session, request["expected_revision"])
            self._inputs(conn, session)
            if session["state"] not in {"waiting_review", "waiting_observation"} or session["pending_review_id"] != request["pending_review_id"] or session["pending_review_digest"] != request["expected_review_digest"]:
                raise DomainError("stale_review", "This is not the current pending review.", 409)
            review = self.workflow._get(conn, actor, request["pending_review_id"])
            if review["digest"] != request["expected_review_digest"]:
                raise DomainError("stale_review", "The review digest differs from the frozen scope.", 409)
            approval = None
            if request["decision"] == "approve":
                if review["kind"] not in {"plan", "design_plan"}:
                    raise DomainError("observation_review_required", "Supply a separately reviewed canonical observation before recheck preparation.", 409)
                scope = "design" if review["kind"] == "design_plan" else "investigation"
                problem_id = review["body"]["request"]["problem_id"] if scope == "design" else review["body"]["problem_id"]
                approval = self.workflow._approve_in_transaction(conn, actor, review["id"], problem_id, review["digest"], scope)
            decision = self.workflow._insert(conn, actor, session["workspace_id"], "research_decision",
                {**request, "research_session_id": session_id, "approval_id": approval["id"] if approval else None}, review["id"])
            old_action = self._action(conn, actor, session["active_action_id"])
            conn.execute("UPDATE research_actions SET state='completed',updated_at=? WHERE id=?", (utc_now(), old_action["id"]))
            conn.execute("UPDATE operations SET state='completed',finished_at=? WHERE id=? AND state='reserved'", (utc_now(), old_action["operation_id"]))
            conn.execute("UPDATE research_sessions SET last_decision_id=?,pending_review_id=NULL,pending_review_digest=NULL WHERE id=?", (decision["id"], session_id))
            self._event(conn, session, "decision_recorded", "The authenticated person recorded a decision.", [decision["id"]], old_action["id"])
            self._queue(conn, session, json.loads(old_action["budget"]), resume_required=True)
            return self._public(conn, self._session(conn, actor, session_id))
        return self.workflow._perform(actor, known["workspace_id"], "decide:research:" + session_id, key, request, decide)

    def events(self, actor, session_id, after=-1):
        with self.store.read() as conn:
            self._session(conn, actor, session_id)
            return [json.loads(row[0]) for row in conn.execute("SELECT body FROM research_events WHERE session_id=? AND sequence>? ORDER BY sequence LIMIT 200", (session_id, after))]

    def accept_observation(self, actor, session_id, request, key):
        request = ResearchObservation.model_validate(request).model_dump(mode="json")
        known = self.get(actor, session_id)
        def accept(conn):
            session = self._session(conn, actor, session_id)
            self._revision(session, request["expected_revision"])
            self._inputs(conn, session)
            if (session["state"] != "waiting_observation" or session["pending_review_id"] != request["pending_review_id"]
                    or session["pending_review_digest"] != request["expected_review_digest"]):
                raise DomainError("stale_review", "Review the exact pending request for a new reading.", 409)
            pending = self.workflow._get(conn, actor, request["pending_review_id"], "research_clarification")
            if pending["digest"] != request["expected_review_digest"] or "new_observation" not in pending["body"]["fields"]:
                raise DomainError("stale_review", "This is not the pending new-observation review.", 409)
            design = conn.execute("SELECT c.job_id FROM research_effects c JOIN research_effects p ON p.session_id=c.session_id AND p.plan_id=c.plan_id AND p.kind='design' WHERE c.session_id=? AND c.kind='child' ORDER BY c.rowid DESC LIMIT 1", (session_id,)).fetchone()
            if not design or not design["job_id"]:
                raise DomainError("followup_design_required", "A completed design is required before this reading handoff.", 409)
            job = self.workflow._job(conn, actor, design["job_id"], "design_job")
            if job["state"] != "completed" or not job["result_id"]:
                raise DomainError("followup_design_required", "The selected design is not complete.", 409)
            design_plan = self.workflow._get(conn, actor, job["plan_id"], "design_plan")
            historical_problem = self.workflow._get(conn, actor, design_plan["body"]["request"]["problem_id"], "problem")
            observation = request["observation"]
            if observation["dataset_id"] != historical_problem["body"]["dataset_id"] or observation["row"]["included"] is not True:
                raise DomainError("followup_lineage_mismatch", "Append one included reading to the original designed dataset.", 422)
            proposal = self.workflow._create_observation_proposal_in_transaction(conn, actor, session["workspace_id"], observation)
            dataset = self.workflow._review_observation_in_transaction(conn, actor, proposal["id"], {
                "proposal_digest": proposal["digest"], "parent_dataset_id": observation["dataset_id"], "accepted": True})
            problem = self.workflow._create_problem_in_transaction(conn, actor, session["workspace_id"], {
                **historical_problem["body"], "dataset_id": dataset["id"], "dataset_digest": dataset["digest"]})
            receipt = conn.execute("SELECT id FROM entities WHERE kind='observation_review' AND parent_id=?", (proposal["id"],)).fetchone()[0]
            accepted = self.workflow._insert(conn, actor, session["workspace_id"], "research_observation_acceptance", {
                "research_session_id": session_id, "pending_review_id": pending["id"], "pending_review_digest": pending["digest"],
                "observation_proposal_id": proposal["id"], "observation_review_id": receipt,
                "dataset_id": dataset["id"], "dataset_digest": dataset["digest"], "problem_id": problem["id"], "problem_digest": problem["digest"],
                "design_job_id": job["id"], "design_result_id": job["result_id"], "accepted": True, "execution_approved": False}, pending["id"])
            now = utc_now()
            old_action = self._action(conn, actor, session["active_action_id"])
            conn.execute("INSERT INTO research_effects(id,session_id,action_id,effect_key,kind,request_digest,plan_id,state,created_at,updated_at) VALUES (?,?,?,?,?,?,?,'accepted',?,?)",
                (_id("effect"), session_id, old_action["id"], "accepted_observation", "accepted_observation", _hash(request), accepted["id"], now, now))
            conn.execute("UPDATE research_actions SET state='completed',updated_at=? WHERE id=?", (now, old_action["id"]))
            conn.execute("UPDATE operations SET state='completed',finished_at=? WHERE id=? AND state='reserved'", (now, old_action["operation_id"]))
            conn.execute("UPDATE research_sessions SET problem_id=?,problem_digest=?,input_heads=?,pending_review_id=NULL,pending_review_digest=NULL WHERE id=?",
                (problem["id"], problem["digest"], _json({"current_dataset_id": dataset["id"], "current_problem_id": problem["id"]}), session_id))
            self._event(conn, session, "decision_recorded", "A person reviewed the new reading; computation still requires a separate approval.", [accepted["id"], receipt], old_action["id"])
            self._queue(conn, session, json.loads(old_action["budget"]), resume_required=False)
            return self._public(conn, self._session(conn, actor, session_id))
        return self.workflow._perform(actor, known["workspace_id"], "observation:research:" + session_id, key, request, accept)

    def adopt_inputs(self, actor, session_id, request, key):
        request = ResearchInputReview.model_validate(request).model_dump(mode="json")
        known = self.get(actor, session_id)
        def adopt(conn):
            session = self._session(conn, actor, session_id)
            self._revision(session, request["expected_revision"])
            if (session["state"] != "waiting_review" or session["pending_review_id"] != request["pending_review_id"]
                    or session["pending_review_digest"] != request["expected_review_digest"]):
                raise DomainError("stale_review", "Answer the current pending clarification.", 409)
            pending = self.workflow._get(conn, actor, request["pending_review_id"], "research_clarification")
            if pending["digest"] != request["expected_review_digest"] or "new_observation" in pending["body"]["fields"]:
                raise DomainError("observation_review_required", "Use the separate new-observation review.", 409)
            workspace = self.workflow.authorize(actor, session["workspace_id"], conn)
            problem_id, digest = session["problem_id"], session["problem_digest"]
            if request["problem_id"]:
                problem = self.workflow._get(conn, actor, request["problem_id"], "problem")
                self.workflow._same_workspace(session["workspace_id"], problem)
                if (problem["id"] != workspace["current_problem_id"] or problem["digest"] != request["expected_problem_digest"]
                        or problem["body"]["dataset_id"] != workspace["current_dataset_id"]):
                    raise DomainError("stale_revision", "Adopt the exact current human-reviewed problem and dataset.", 409)
                problem_id, digest = problem["id"], problem["digest"]
            else:
                self._inputs(conn, session)
            accepted = self.workflow._insert(conn, actor, session["workspace_id"], "research_input_review",
                {**request, "research_session_id": session_id, "execution_approved": False}, pending["id"])
            old = self._action(conn, actor, session["active_action_id"])
            conn.execute("UPDATE research_actions SET state='completed',updated_at=? WHERE id=?", (utc_now(), old["id"]))
            conn.execute("UPDATE operations SET state='completed',finished_at=? WHERE id=? AND state='reserved'", (utc_now(), old["operation_id"]))
            conn.execute("UPDATE research_sessions SET problem_id=?,problem_digest=?,input_heads=?,pending_review_id=NULL,pending_review_digest=NULL WHERE id=?",
                (problem_id, digest, _json({field: workspace[field] for field in ("current_dataset_id", "current_problem_id")}), session_id))
            self._event(conn, session, "decision_recorded", "Human-reviewed input was adopted; no scientific execution was approved.", [accepted["id"]], old["id"])
            self._queue(conn, session, json.loads(old["budget"]), resume_required=False)
            return self._public(conn, self._session(conn, actor, session_id))
        return self.workflow._perform(actor, known["workspace_id"], "inputs:research:" + session_id, key, request, adopt)

    def cancel(self, actor, session_id, key):
        known = self.get(actor, session_id)
        def cancel(conn):
            session = self._session(conn, actor, session_id)
            if session["state"] not in ENDED:
                conn.execute("UPDATE research_sessions SET state='cancelled',revision=revision+1,updated_at=? WHERE id=?", (utc_now(), session_id))
                conn.execute("UPDATE research_actions SET state='cancelled',lease_epoch=lease_epoch+1,lease_owner=NULL,lease_until=NULL,acquired_at=NULL,updated_at=? WHERE session_id=? AND state NOT IN ('completed','failed','cancelled')", (utc_now(), session_id))
                conn.execute("UPDATE jobs SET state='cancel_requested' WHERE id IN (SELECT job_id FROM research_effects WHERE session_id=?) AND state IN ('queued','running')", (session_id,))
                self._event(conn, session, "cancel_requested", "Further coordination is revoked; owned computation is stopping.", action_id=session["active_action_id"])
            return self._public(conn, self._session(conn, actor, session_id))
        return self.workflow._perform(actor, known["workspace_id"], "cancel:research:" + session_id, key, {}, cancel)

    def recover(self, *, force=False):
        """Expired/explicit worker-loss actions pause; consumed work is never reset."""
        with self.store.transaction() as conn:
            rows = conn.execute("SELECT * FROM research_actions WHERE state='running' AND (? OR lease_until<=?)", (int(force), time.time())).fetchall()
            for row in rows:
                active = row["active_seconds"] + max(0, time.time() - row["acquired_at"]) if row["acquired_at"] else row["active_seconds"]
                conn.execute("UPDATE research_actions SET state='needs_reconciliation',active_seconds=?,lease_owner=NULL,lease_until=NULL,acquired_at=NULL,lease_epoch=lease_epoch+1,error_code='worker_lost',updated_at=? WHERE id=?", (active, utc_now(), row["id"]))
                conn.execute("UPDATE research_sessions SET state='needs_reconciliation',revision=revision+1,updated_at=? WHERE id=? AND active_action_id=? AND state='running'", (utc_now(), row["session_id"], row["id"]))
                conn.execute("UPDATE provider_attempts SET state='unknown_outcome',finished_at=? WHERE state='reserved' AND id IN (SELECT attempt_id FROM research_attempt_bindings WHERE action_id=?)", (utc_now(), row["id"]))
            return {"research_actions_needing_reconciliation": len(rows)}

    def reconcile(self, actor, session_id, request, key):
        request = ResearchReconcile.model_validate(request).model_dump(mode="json")
        known = self.get(actor, session_id)
        def reconcile(conn):
            session = self._session(conn, actor, session_id)
            self._revision(session, request["expected_revision"])
            self._inputs(conn, session)
            if session["state"] != "needs_reconciliation":
                raise DomainError("reconciliation_not_required", "This research action is not awaiting recovery.", 409)
            action = self._action(conn, actor, session["active_action_id"])
            unknown = conn.execute("SELECT 1 FROM provider_attempts p JOIN research_attempt_bindings b ON b.attempt_id=p.id WHERE b.action_id=? AND p.state IN ('unknown_outcome','reserved')", (action["id"],)).fetchone()
            if unknown:
                raise DomainError("provider_outcome_unknown", "The provider outcome remains unknown and reserved; inference will not be automatically repeated.", 409)
            # Same action, same cumulative counters, same journal and graph thread.
            conn.execute("UPDATE research_actions SET state='queued',error_code=NULL,updated_at=? WHERE id=?", (utc_now(), action["id"]))
            conn.execute("UPDATE research_sessions SET state='queued',revision=revision+1,updated_at=? WHERE id=?", (utc_now(), session_id))
            self._event(conn, session, "reconciled", "Existing journal/checkpoint work will be reconciled without renewing its budget.", action_id=action["id"])
            return self._public(conn, self._session(conn, actor, session_id))
        return self.workflow._perform(actor, known["workspace_id"], "reconcile:research:" + session_id, key, request, reconcile)

    def queued(self):
        with self.store.read() as conn:
            return [dict(row) for row in conn.execute("SELECT a.id,s.actor_id FROM research_actions a JOIN research_sessions s ON s.id=a.session_id WHERE a.state='queued' AND s.active_action_id=a.id AND s.state='queued' ORDER BY a.created_at LIMIT 1")]

    def wake_children(self):
        with self.store.transaction() as conn:
            rows = conn.execute("SELECT a.id,a.session_id FROM research_actions a JOIN jobs j ON j.id=a.waiting_job_id JOIN research_sessions s ON s.id=a.session_id WHERE a.state='waiting_child' AND j.state IN ('completed','failed','cancelled','interrupted') AND s.active_action_id=a.id AND s.state='waiting_child'").fetchall()
            for row in rows:
                conn.execute("UPDATE research_actions SET state='queued',resume_required=1,updated_at=? WHERE id=?", (utc_now(), row["id"]))
                conn.execute("UPDATE research_sessions SET state='queued',updated_at=? WHERE id=?", (utc_now(), row["session_id"]))
            return len(rows)
