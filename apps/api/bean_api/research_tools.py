"""Tenant-scoped ports for A's graph; no actor/scope is taken from tool input."""
from __future__ import annotations

import json

from .contracts import PlanBody
from .research import SESSION_LIMITS
from .research_contracts import ResearchDesignConstraints
from .store import utc_now
from .workflow import DomainError, _hash, _id


class ApplicationResearchPorts:
    def __init__(self, service, context):
        self.service, self.runtime, self.workflow = service, context, service.workflow

    async def check_authority(self):
        with self.service.store.read() as conn:
            self.service.assert_lease(conn, self.runtime)

    async def context(self):
        with self.service.store.read() as conn:
            session, action = self.service.assert_lease(conn, self.runtime)
            creation = self.workflow._get(conn, self.runtime.actor_id, session["id"])
            reviewed = self.service.root_context(conn, session)
            problem, dataset = reviewed["problem"], reviewed["dataset"]
            evidence = []
            reviews = []
            for effect in conn.execute("SELECT * FROM research_effects WHERE session_id=? ORDER BY created_at,id", (session["id"],)):
                if effect["plan_id"] and effect["kind"] in {"investigation", "design", "followup"}:
                    review = self.workflow._get(conn, self.runtime.actor_id, effect["plan_id"])
                    reviews.append(self.service.review_view(conn, session, review))
                if effect["job_id"]:
                    job = self.workflow._job(conn, self.runtime.actor_id, effect["job_id"])
                    ids = [r["result_id"] for r in job["scenarios"] if r["result_id"]]
                    if job["result_id"]:
                        ids.append(job["result_id"])
                    evidence.extend({"id": ref, "job_id": job["id"], "state": job["state"]} for ref in dict.fromkeys(ids))
            return {"objective": creation["body"]["objective"], "question": creation["body"]["objective"],
                "reviewed_context": reviewed, "input_digest": _hash(reviewed),
                "reference_ids": list(dict.fromkeys([session["id"], *([problem["id"], dataset["id"]] if problem else []),
                    *(ref["id"] for ref in reviewed["sources"]), *(ref["id"] for ref in evidence)])),
                "budget": json.loads(action["budget"]), "usage": {key: action[key] for key in ("logical_turns", "tool_calls", "child_count")},
                "design_constraints": creation["body"].get("design_constraints"),
                "design_constraints_unavailable_reason": None if creation["body"].get("design_constraints") else "Researcher has not supplied feasible times, future hard allowance and horizon.",
                "reviews": reviews, "evidence": evidence, "mode": session["mode"],
                "decision": self.workflow._get(conn, self.runtime.actor_id, session["last_decision_id"])["body"] if session["last_decision_id"] else None}

    async def update_plan(self, plan):
        return self.service.update_plan(self.runtime, plan)

    def _prepared(self, conn, session, key, kind, body, prepare):
        digest = _hash(body)
        existing = conn.execute("SELECT * FROM research_effects WHERE session_id=? AND effect_key=?", (session["id"], key)).fetchone()
        if existing:
            if existing["request_digest"] != digest:
                raise DomainError("research_effect_conflict", "A stable research step cannot change its frozen scope.", 409)
            record = self.workflow._get(conn, self.runtime.actor_id, existing["plan_id"])
        else:
            record = prepare()
            now = utc_now()
            conn.execute("INSERT INTO research_effects(id,session_id,action_id,effect_key,kind,request_digest,plan_id,state,created_at,updated_at) VALUES (?,?,?,?,?,?,?,'prepared',?,?)",
                (_id("effect"), session["id"], self.runtime.action_id, key, kind, digest, record["id"], now, now))
        return self.service.review_view(conn, session, record)

    async def prepare_investigation(self):
        with self.service.store.transaction() as conn:
            session, _ = self.service.assert_lease(conn, self.runtime)
            if not session["problem_id"]:
                return {"available": False, "reason": "Reviewed supported-model inputs are required; uploaded prose alone is not a scientific problem."}
            problem = self.workflow._get(conn, self.runtime.actor_id, session["problem_id"], "problem")
            objective = self.workflow._get(conn, self.runtime.actor_id, session["id"])["body"]["objective"]
            body = PlanBody(problem_id=problem["id"], problem_digest=problem["digest"], dataset_id=problem["body"]["dataset_id"],
                scientific_profile="counterdex.v1", objective={"question": objective, "success_criterion": "Report the actual bounded search outcome, checked evidence and remaining uncertainty."},
                scenarios=[{"id": "baseline", "kind": "baseline", "label": "Reviewed concentration-model investigation", "problem_id": problem["id"], "problem_digest": problem["digest"]}],
                budget={"provider_turns": 0, "tool_calls": 6, "scientific_reservations": 1, "wall_seconds": 300, "scientific_wall_seconds": 120}).model_dump(mode="json")
            return self._prepared(conn, session, "investigation", "investigation", body,
                lambda: self.workflow._create_plan_in_transaction(conn, self.runtime.actor_id, self.runtime.workspace_id, body))

    def _baseline(self, conn, session):
        effect = conn.execute("SELECT * FROM research_effects WHERE session_id=? AND effect_key='child:investigation'", (session["id"],)).fetchone()
        if not effect or not effect["job_id"]:
            raise DomainError("historical_evidence_required", "The approved baseline has not completed.", 409)
        job = self.workflow._job(conn, self.runtime.actor_id, effect["job_id"], "run")
        child = next((r for r in job["scenarios"] if r["scenario_id"] == "baseline" and r["result_id"]), None)
        if job["state"] != "completed" or not child:
            raise DomainError("historical_evidence_required", "The approved baseline has not completed.", 409)
        evidence = self.workflow._get(conn, self.runtime.actor_id, child["result_id"], "evidence")
        return job, evidence

    async def prepare_design(self, constraints):
        with self.service.store.transaction() as conn:
            session, _ = self.service.assert_lease(conn, self.runtime)
            # These are proposal values. The concrete canonical design is still
            # reviewed/approved separately; the model never supplies history IDs.
            scope = ResearchDesignConstraints.model_validate(constraints).model_dump(mode="json")
            job, evidence = self._baseline(conn, session)
            result = evidence["body"]["result"]
            candidates = result.get("candidates", [])
            if len(candidates) != 2 or any(c.get("verification") != "valid" for c in candidates):
                return {"available": False, "reason": "The baseline did not establish the two checked historical candidates needed for pair design."}
            plan = self.workflow._get(conn, self.runtime.actor_id, job["plan_id"], "plan")
            body = {**scope, "historical_run_id": job["id"], "scenario_id": "baseline",
                "problem_id": plan["body"]["problem_id"], "problem_digest": plan["body"]["problem_digest"],
                "candidate_ids": [c["id"] for c in candidates], "candidate_vectors": [c["parameter_vector"] for c in candidates],
                "scientific_profile": "counterdex.v1", "source_artifact_ids": []}
            return self._prepared(conn, session, "design", "design", body,
                lambda: self.workflow._create_design_plan_in_transaction(conn, self.runtime.actor_id, job["id"], body))

    async def require_review(self, review_id, review_digest):
        return self.service.pending_review(self.runtime, review_id, review_digest)

    def _decision(self, conn, session, review_id, expected_digest):
        review = self.workflow._get(conn, self.runtime.actor_id, review_id)
        self.workflow._same_workspace(self.runtime.workspace_id, review)
        if review["digest"] != expected_digest:
            raise DomainError("stale_review", "The exact prepared review digest is required at dispatch.", 409)
        prepared = conn.execute("SELECT * FROM research_effects WHERE session_id=? AND plan_id=? AND kind IN ('investigation','design','followup')", (session["id"], review_id)).fetchone()
        if not prepared:
            raise DomainError("review_not_in_scope", "This plan was not prepared for this research session.", 403)
        decisions = conn.execute("SELECT * FROM entities WHERE workspace_id=? AND kind='research_decision' AND parent_id=? ORDER BY rowid DESC", (self.runtime.workspace_id, review_id))
        for record in decisions:
            decision = json.loads(record["body"])
            if (decision["research_session_id"] == session["id"] and decision["expected_review_digest"] == expected_digest
                    and decision["decision"] == "approve" and record["created_by"] == self.runtime.actor_id):
                return review, dict(prepared), decision
        raise DomainError("approval_required", "The authenticated person must approve this exact review before dispatch.", 403)

    async def execute_child(self, review_id, expected_review_digest):
        # First commit the stable intended effect and charge its logical science
        # reservation. A crash here leaves an intent with no child, never a new
        # budget on retry. The actual canonical reservation/link is atomic below.
        with self.service.store.transaction() as conn:
            session, action = self.service.assert_lease(conn, self.runtime)
            review, prepared, decision = self._decision(conn, session, review_id, expected_review_digest)
            key = "child:" + prepared["effect_key"]
            request = {"review_id": review_id, "review_digest": expected_review_digest, "approval_id": decision["approval_id"]}
            existing = conn.execute("SELECT * FROM research_effects WHERE session_id=? AND effect_key=?", (session["id"], key)).fetchone()
            if existing and existing["request_digest"] != _hash(request):
                raise DomainError("research_effect_conflict", "A scientific step cannot change after reservation.", 409)
            if not existing:
                if action["child_count"] >= json.loads(action["budget"])["scientific_reservations"] or session["child_count"] >= SESSION_LIMITS["child_count"]:
                    raise DomainError("research_budget_exhausted", "The scientific reservation budget is exhausted.", 409)
                conn.execute("UPDATE research_actions SET child_count=child_count+1 WHERE id=?", (action["id"],))
                conn.execute("UPDATE research_sessions SET child_count=child_count+1 WHERE id=?", (session["id"],))
                now = utc_now()
                conn.execute("INSERT INTO research_effects(id,session_id,action_id,effect_key,kind,request_digest,plan_id,approval_id,state,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?, 'intent',?,?)",
                    (_id("effect"), session["id"], action["id"], key, "child", _hash(request), review_id, decision["approval_id"], now, now))
        with self.service.store.transaction() as conn:
            session, _ = self.service.assert_lease(conn, self.runtime)
            review, prepared, decision = self._decision(conn, session, review_id, expected_review_digest)
            effect = conn.execute("SELECT * FROM research_effects WHERE session_id=? AND effect_key=?", (session["id"], key)).fetchone()
            scope = "design" if review["kind"] == "design_plan" else "investigation"
            job = self.workflow._start_in_transaction(conn, self.runtime.actor_id, review_id, decision["approval_id"], scope)
            if effect["job_id"] and effect["job_id"] != job["id"]:
                raise DomainError("research_effect_conflict", "The child journal differs from its canonical reservation.", 409)
            if not effect["job_id"]:
                conn.execute("UPDATE research_effects SET job_id=?,state='dispatched',updated_at=? WHERE id=?", (job["id"], utc_now(), effect["id"]))
                self.service._event(conn, session, "child_linked", "The exact approved scientific child was reserved.", [review_id, job["id"]], self.runtime.action_id)
            evidence_ids = [r["result_id"] for r in job["scenarios"] if r["result_id"]]
            if job["result_id"]:
                evidence_ids.append(job["result_id"])
            state = {"queued": "pending", "interrupted": "unresolved", "cancel_requested": "running"}.get(job["state"], job["state"])
            return {**self.service.review_view(conn, session, review, decision="approve", approval_id=decision["approval_id"]),
                "job_id": job["id"], "state": state,
                "evidence_ids": list(dict.fromkeys(evidence_ids)), "result_id": job["result_id"],
                "waiting": job["state"] in {"queued", "running", "cancel_requested"}}

    async def read_evidence(self, evidence_id):
        with self.service.store.transaction() as conn:
            session, _ = self.service.assert_lease(conn, self.runtime)
            record = self.workflow._get(conn, self.runtime.actor_id, evidence_id)
            self.workflow._same_workspace(self.runtime.workspace_id, record)
            linked = False
            for row in conn.execute("SELECT job_id FROM research_effects WHERE session_id=? AND job_id IS NOT NULL", (session["id"],)):
                job = self.workflow._job(conn, self.runtime.actor_id, row["job_id"])
                if job["result_id"] == evidence_id or any(r["result_id"] == evidence_id for r in job["scenarios"]):
                    linked = True
            if not linked or record["kind"] not in {"evidence", "suggestion"}:
                raise DomainError("evidence_not_in_scope", "This evidence is not linked to the research session.", 403)
            self.service._event(conn, session, "evidence_observed", "Actual scientific evidence was read; its verification axes remain unchanged.", [record["id"]], self.runtime.action_id)
            return record

    async def request_clarification(self, fields, reason):
        if not isinstance(fields, list) or not 1 <= len(fields) <= 16 or any(not isinstance(v, str) or not 1 <= len(v) <= 128 for v in fields) or not isinstance(reason, str) or not 1 <= len(reason) <= 1000:
            raise DomainError("invalid_clarification", "Use bounded missing fields and a short public reason.", 422)
        with self.service.store.transaction() as conn:
            session, _ = self.service.assert_lease(conn, self.runtime)
            body = {"fields": fields, "reason": reason}
            prepared = self._prepared(conn, session, "clarification:" + _hash(body), "clarification", body,
                lambda: self.workflow._insert(conn, self.runtime.actor_id, self.runtime.workspace_id, "research_clarification", body, session["id"]))
        pending = self.service.pending_review(self.runtime, prepared["review_id"], prepared["review_digest"])
        return {**pending, "id": prepared["review_id"]}

    async def prepare_followup(self):
        # A human reading is required. No tool creates or pretends to acquire it.
        with self.service.store.transaction() as conn:
            session, _ = self.service.assert_lease(conn, self.runtime)
            effect = conn.execute("SELECT job_id FROM research_effects WHERE session_id=? AND effect_key='child:design'", (session["id"],)).fetchone()
            if not effect or not effect["job_id"]:
                return {"available": False, "reason": "An approved design result is required before requesting a follow-up reading."}
            job = self.workflow._job(conn, self.runtime.actor_id, effect["job_id"], "design_job")
            if job["state"] != "completed" or not job["result_id"]:
                return {"available": False, "reason": "The design has not completed."}
            suggestion = self.workflow._get(conn, self.runtime.actor_id, job["result_id"], "suggestion")
            body = {"design_job_id": job["id"], "design_result_id": suggestion["id"], "design_result_digest": suggestion["digest"],
                "selected_time": suggestion["body"].get("selected_time"), "future_hard_allowance": suggestion["body"].get("future_hard_allowance"),
                "message": "Supply and review a new reading, its time, hard allowance and actual or hypothetical origin. Rechecking requires a separate execution approval."}
            return self._prepared(conn, session, "observation", "observation", body,
                lambda: self.workflow._insert(conn, self.runtime.actor_id, self.runtime.workspace_id, "research_observation_request", body, session["id"]))

    async def publish_report(self):
        # Existing report generation is deterministic and idempotent. Native bytes
        # remain separately retained; narration can never erase completed science.
        with self.service.store.read() as conn:
            session, _ = self.service.assert_lease(conn, self.runtime)
            job, _ = self._baseline(conn, session)
        report = self.workflow.create_report(self.runtime.actor_id, job["id"], "research-report:" + session["id"])
        with self.service.store.transaction() as conn:
            current, _ = self.service.assert_lease(conn, self.runtime)
            self.service._event(conn, current, "tool_finished", "A canonical report snapshot was assembled from retained evidence.", [report["id"]], self.runtime.action_id)
        return {"id": report["id"], "report_id": report["id"], "report_digest": report["digest"],
            "evidence_ids": [item["id"] for item in report["body"]["evidence"]],
            "scope": "Canonical evidence snapshot; verification does not apply to every narrative sentence."}

    async def admit_model(self):
        self.service.admit(self.runtime, "model")

    async def admit_tool(self, name):
        self.service.admit(self.runtime, "tool", name)
