"""Authenticated immutable research state and transactional execution authority.

This module does not verify scientific propositions. Only a configured adapter
may produce evidence; stored execution state never upgrades its scientific tier.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import sqlite3
from typing import Any, Callable
from uuid import uuid4

from .store import Store, utc_now


class DomainError(Exception):
    def __init__(self, code: str, message: str, status: int = 409,
                 field_paths: list[str] | None = None,
                 current_revision_id: str | None = None, retryable: bool = False):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status
        self.field_paths = field_paths or []
        self.current_revision_id, self.retryable = current_revision_id, retryable


def _body(value: Any) -> dict:
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else dict(value)


def _json(value: Any) -> str:
    from .canonical import canonical_bytes
    return canonical_bytes(value).decode("utf-8")


def _hash(value: Any) -> str:
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _digest(kind: str, body: dict) -> str:
    from .canonical import semantic_digest
    semantic_kind = {"design_request": "design-request", "design_plan": "plan"}.get(kind, kind)
    if semantic_kind in {"dataset", "problem", "plan", "design-request", "suggestion", "report"}:
        return semantic_digest(semantic_kind, body)
    return _hash(body)


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def _record(row: sqlite3.Row) -> dict:
    result = dict(row)
    if "body" in result:
        result["body"] = json.loads(result["body"])
    if result.get("response"):
        result["response"] = json.loads(result["response"])
    return result


class Workflow:
    def __init__(self, store: Store):
        self.store = store

    def authorize(self, actor: str, workspace_id: str, conn: sqlite3.Connection | None = None) -> dict:
        if conn is None:
            with self.store.read() as active:
                return self.authorize(actor, workspace_id, active)
        row = conn.execute(
            "SELECT w.* FROM workspaces w JOIN memberships m ON m.workspace_id=w.id "
            "WHERE w.id=? AND m.actor_id=?", (workspace_id, actor)
        ).fetchone()
        if row is None:
            raise DomainError("not_found", "Workspace or record was not found.", 404)
        return dict(row)

    def workspace(self, actor: str, workspace_id: str) -> dict:
        return self.authorize(actor, workspace_id)

    def create_workspace(self, actor: str, name: str, workspace_id: str | None = None) -> dict:
        if not actor or not name.strip() or len(name) > 120:
            raise DomainError("invalid_workspace", "A workspace name is required.", 422, ["name"])
        workspace_id = workspace_id or _id("ws")
        with self.store.transaction() as conn:
            conn.execute("INSERT INTO workspaces(id,name,created_at) VALUES (?,?,?)", (workspace_id, name, utc_now()))
            conn.execute("INSERT INTO memberships VALUES (?,?)", (workspace_id, actor))
            return self.authorize(actor, workspace_id, conn)

    def list_workspaces(self, actor: str) -> list[dict]:
        with self.store.read() as conn:
            return [dict(row) for row in conn.execute(
                "SELECT w.* FROM workspaces w JOIN memberships m ON m.workspace_id=w.id "
                "WHERE m.actor_id=? ORDER BY w.created_at,w.id", (actor,))]

    def _get(self, conn: sqlite3.Connection, actor: str, record_id: str, kind: str | None = None) -> dict:
        row = conn.execute("SELECT * FROM entities WHERE id=?", (record_id,)).fetchone()
        if row is None or (kind and row["kind"] != kind):
            raise DomainError("not_found", "Workspace or record was not found.", 404)
        self.authorize(actor, row["workspace_id"], conn)
        return _record(row)

    def get(self, actor: str, record_id: str, kind: str | None = None) -> dict:
        with self.store.read() as conn:
            if kind in {"run", "design_job"}:
                return self._job(conn, actor, record_id, kind)
            return self._get(conn, actor, record_id, kind)

    def list_records(self, actor: str, workspace_id: str, kind: str, limit: int = 100) -> list[dict]:
        with self.store.read() as conn:
            self.authorize(actor, workspace_id, conn)
            return [_record(row) for row in conn.execute(
                "SELECT * FROM entities WHERE workspace_id=? AND kind=? ORDER BY created_at,id LIMIT ?",
                (workspace_id, kind, max(1, min(limit, 200))))]

    def recent_records(self, actor: str, workspace_id: str, kind: str, limit: int = 8) -> list[dict]:
        with self.store.read() as conn:
            self.authorize(actor, workspace_id, conn)
            return [_record(row) for row in conn.execute(
                "SELECT * FROM entities WHERE workspace_id=? AND kind=? ORDER BY created_at DESC,rowid DESC LIMIT ?",
                (workspace_id, kind, max(1, min(limit, 200))))]

    def _insert(self, conn: sqlite3.Connection, actor: str, workspace_id: str,
                kind: str, body: dict, parent_id: str | None = None) -> dict:
        if parent_id:
            parent = self._get(conn, actor, parent_id)
            self._same_workspace(workspace_id, parent)
        record_id = _id(kind)
        conn.execute(
            "INSERT INTO entities VALUES (?,?,?,?,?,?,?,?)",
            (record_id, workspace_id, kind, _json(body), _digest(kind, body), parent_id, actor, utc_now()))
        return self._get(conn, actor, record_id)

    @staticmethod
    def _same_workspace(workspace_id: str, record: dict) -> None:
        if record["workspace_id"] != workspace_id:
            raise DomainError("not_found", "Workspace or record was not found.", 404)

    @staticmethod
    def _key(key: str) -> None:
        if not isinstance(key, str) or not 1 <= len(key) <= 128 or not all(32 < ord(c) < 127 for c in key):
            raise DomainError("invalid_idempotency_key", "Use a nonempty printable operation key of at most 128 characters.", 422, ["idempotency_key"])

    def _operation(self, conn: sqlite3.Connection, actor: str, workspace_id: str,
                   operation: str, key: str, body: dict) -> dict | None:
        self._key(key)
        row = conn.execute(
            "SELECT * FROM operations WHERE workspace_id=? AND actor_id=? AND operation=? AND operation_key=?",
            (workspace_id, actor, operation, key)).fetchone()
        if row is None:
            return None
        if row["request_digest"] != _hash(body):
            raise DomainError("idempotency_conflict", "This operation key was already used with different content.", 409)
        return _record(row)

    def _reserve_operation(self, conn: sqlite3.Connection, actor: str, workspace_id: str,
                           operation: str, key: str, body: dict) -> dict:
        operation_id = _id("op")
        conn.execute(
            "INSERT INTO operations(id,workspace_id,actor_id,operation,operation_key,request_digest,state,created_at) "
            "VALUES (?,?,?,?,?,?,'reserved',?)", (operation_id, workspace_id, actor, operation, key, _hash(body), utc_now()))
        return _record(conn.execute("SELECT * FROM operations WHERE id=?", (operation_id,)).fetchone())

    def _perform(self, actor: str, workspace_id: str, operation: str, key: str,
                 body: dict, action: Callable[[sqlite3.Connection], dict]) -> dict:
        with self.store.transaction() as conn:
            self.authorize(actor, workspace_id, conn)
            existing = self._operation(conn, actor, workspace_id, operation, key, body)
            if existing:
                if existing["state"] == "completed":
                    return existing["response"]
                raise DomainError("operation_pending" if existing["state"] == "reserved" else "operation_interrupted",
                                  "The original operation must be reconciled; no duplicate work was started.", 409)
            reservation = self._reserve_operation(conn, actor, workspace_id, operation, key, body)
            response = action(conn)
            conn.execute("UPDATE operations SET state='completed',response=?,finished_at=? WHERE id=?",
                         (_json(response), utc_now(), reservation["id"]))
            return response

    def begin_operation(self, actor: str, workspace_id: str, operation: str, key: str, body: dict) -> dict:
        with self.store.transaction() as conn:
            self.authorize(actor, workspace_id, conn)
            existing = self._operation(conn, actor, workspace_id, operation, key, _body(body))
            if existing:
                return {**existing, "created_new": False}
            return {**self._reserve_operation(conn, actor, workspace_id, operation, key, _body(body)), "created_new": True}

    def finish_operation(self, actor: str, workspace_id: str, operation: str, key: str, response: dict) -> dict:
        with self.store.transaction() as conn:
            self.authorize(actor, workspace_id, conn)
            row = conn.execute(
                "SELECT * FROM operations WHERE workspace_id=? AND actor_id=? AND operation=? AND operation_key=?",
                (workspace_id, actor, operation, key)).fetchone()
            if row is None:
                raise DomainError("not_found", "Operation was not found.", 404)
            if row["state"] == "completed":
                return json.loads(row["response"])
            if row["state"] != "reserved":
                raise DomainError("operation_interrupted", "Interrupted work requires explicit reconciliation.")
            conn.execute("UPDATE operations SET state='completed',response=?,finished_at=? WHERE id=?", (_json(response), utc_now(), row["id"]))
            return response

    def fail_operation(self, actor: str, workspace_id: str, operation: str, key: str, code: str) -> None:
        with self.store.transaction() as conn:
            self.authorize(actor, workspace_id, conn)
            conn.execute("UPDATE operations SET state='failed',error_code=?,finished_at=? "
                         "WHERE workspace_id=? AND actor_id=? AND operation=? AND operation_key=? AND state='reserved'",
                         (code, utc_now(), workspace_id, actor, operation, key))

    def create_record(self, actor: str, workspace_id: str, kind: str, body: dict, key: str,
                      operation: str | None = None, parent_id: str | None = None) -> dict:
        body = _body(body)
        return self._perform(actor, workspace_id, operation or f"create:{kind}", key,
                             {"body": body, "parent_id": parent_id},
                             lambda conn: self._insert(conn, actor, workspace_id, kind, body, parent_id))

    def create_dataset(self, actor: str, workspace_id: str, body: dict, key: str) -> dict:
        from .contracts import DatasetBody
        body = DatasetBody.model_validate(_body(body)).model_dump(mode="json")
        def action(conn: sqlite3.Connection) -> dict:
            parent = None
            if body.get("parent_id"):
                parent = self._get(conn, actor, body["parent_id"], "dataset")
                self._same_workspace(workspace_id, parent)
                if parent["body"]["experiment_id"] != body["experiment_id"]:
                    raise DomainError("experiment_mismatch", "A revision must retain its experiment identity.", 422)
                if parent["body"]["origin"] == "hypothetical" and body["origin"] != "hypothetical":
                    raise DomainError("origin_mismatch", "A descendant containing hypothetical history must remain labeled hypothetical.", 422, ["origin"])
                if parent["body"]["origin"] == "synthetic" and body["origin"] == "actual":
                    raise DomainError("origin_mismatch", "Synthetic parent observations cannot be relabeled actual measurements.", 422, ["origin"])
            source_parent_rows = {row["id"]: row for row in parent["body"]["rows"] if row.get("source_asset_id")} if parent else {}
            for index, row in enumerate(body["rows"]):
                if row["id"] in source_parent_rows and row != source_parent_rows[row["id"]]:
                    raise DomainError("source_review_required", "A source-derived parent row cannot be changed or lose its source association without exact intake review.", 422, [f"rows.{index}"])
                if row.get("source_asset_id"):
                    self._same_workspace(workspace_id, self._get(conn, actor, row["source_asset_id"], "source_asset"))
                    if parent is None or row not in parent["body"]["rows"]:
                        raise DomainError("source_review_required", "New or corrected source-derived rows must be materialized from an exact intake review.", 422, [f"rows.{index}"])
            result = self._insert(conn, actor, workspace_id, "dataset", body, body.get("parent_id"))
            conn.execute("UPDATE workspaces SET current_dataset_id=?,current_problem_id=NULL WHERE id=?", (result["id"], workspace_id))
            return result
        return self._perform(actor, workspace_id, "create:dataset", key, body, action)

    def create_problem(self, actor: str, workspace_id: str, body: dict, key: str) -> dict:
        from .contracts import ProblemBody
        body = ProblemBody.model_validate(_body(body)).model_dump(mode="json")
        def action(conn: sqlite3.Connection) -> dict:
            dataset = self._get(conn, actor, body["dataset_id"], "dataset")
            self._same_workspace(workspace_id, dataset)
            current = self.authorize(actor, workspace_id, conn)
            if current["current_dataset_id"] != dataset["id"]:
                raise DomainError("stale_revision", "Review the current dataset before creating a problem.", current_revision_id=current["current_dataset_id"])
            if body["dataset_digest"] != dataset["digest"]:
                raise DomainError("binding_mismatch", "The dataset digest does not match the reviewed record.", 422, ["dataset_digest"])
            result = self._insert(conn, actor, workspace_id, "problem", body)
            conn.execute("UPDATE workspaces SET current_problem_id=? WHERE id=?", (result["id"], workspace_id))
            return result
        return self._perform(actor, workspace_id, "create:problem", key, body, action)

    def create_plan(self, actor: str, workspace_id: str, body: dict, key: str) -> dict:
        from .contracts import PlanBody
        body = PlanBody.model_validate(_body(body)).model_dump(mode="json")
        def action(conn: sqlite3.Connection) -> dict:
            problem = self._get(conn, actor, body["problem_id"], "problem")
            self._same_workspace(workspace_id, problem)
            current = self.authorize(actor, workspace_id, conn)
            if current["current_problem_id"] != problem["id"]:
                raise DomainError("stale_revision", "Review the current problem before making a plan.", current_revision_id=current["current_problem_id"])
            if body["problem_digest"] != problem["digest"] or body["dataset_id"] != problem["body"]["dataset_id"]:
                raise DomainError("binding_mismatch", "The plan must bind the exact reviewed problem and dataset.", 422)
            for scenario in body["scenarios"]:
                target = self._get(conn, actor, scenario["problem_id"], "problem")
                self._same_workspace(workspace_id, target)
                if target["digest"] != scenario["problem_digest"]:
                    raise DomainError("binding_mismatch", "A scenario problem digest does not match.", 422, ["scenarios"])
            if body.get("followup"):
                self._followup_context(conn, actor, body)
            disclosure = body["provider_disclosure"]
            for source_id in disclosure.get("source_asset_ids", []):
                self._same_workspace(workspace_id, self._get(conn, actor, source_id, "source_asset"))
            if disclosure["provider"] == "gemini":
                permission = self._get(conn, actor, disclosure["permission_id"], "provider_consent")
                self._same_workspace(workspace_id, permission)
                consent = permission["body"]
                if permission["created_by"] != actor or consent.get("accepted") is not True or any(
                    consent.get(field) != disclosure[field] for field in ("provider", "model", "source_asset_ids", "context_fields")
                ) or consent.get("problem_id") != body["problem_id"]:
                    raise DomainError("provider_consent_mismatch", "Provider permission must cover this exact model, problem, source and context disclosure.", 403)
            if body.get("parent_plan_id") is None and conn.execute(
                "SELECT 1 FROM entities WHERE workspace_id=? AND kind='plan' AND digest=?",
                (workspace_id, _digest("plan", body)),
            ).fetchone():
                raise DomainError("plan_ancestry_required", "An intentional rerun needs a new reviewed plan linked by parent_plan_id.", 422, ["parent_plan_id"])
            return self._insert(conn, actor, workspace_id, "plan", body, body.get("parent_plan_id"))
        return self._perform(actor, workspace_id, "create:plan", key, body, action)

    def followup_context(self, actor: str, plan_body: dict) -> dict:
        """Resolve the approved fixed-pair lineage without consulting mutable drafts."""
        from .contracts import PlanBody
        body = PlanBody.model_validate(_body(plan_body)).model_dump(mode="json")
        with self.store.read() as conn:
            return self._followup_context(conn, actor, body)

    def _followup_context(self, conn: sqlite3.Connection, actor: str, body: dict) -> dict:
        scope = body.get("followup")
        if not scope:
            raise DomainError("followup_scope_required", "The reviewed plan must name its selected design and observation.", 422)
        revised_problem = self._get(conn, actor, body["problem_id"], "problem")
        workspace_id = revised_problem["workspace_id"]
        revised_dataset = self._get(conn, actor, revised_problem["body"]["dataset_id"], "dataset")
        job = self._job(conn, actor, scope["design_job_id"], "design_job")
        self._same_workspace(workspace_id, job)
        if job["state"] != "completed" or job["result_id"] != scope["design_result_id"]:
            raise DomainError("followup_design_required", "Follow-up checking requires the selected completed design result.", 422)
        result = self._get(conn, actor, scope["design_result_id"], "suggestion")
        plan = self._get(conn, actor, job["plan_id"], "design_plan")
        request, facts = plan["body"]["request"], result["body"]
        if result["digest"] != scope["design_result_digest"]:
            raise DomainError("binding_mismatch", "The follow-up plan must bind the exact retained design result.", 422)
        if (facts.get("projection_version") != "DB-SC-1-to-groundwork-v1"
                or facts.get("design_tier") != "checked_pair_separation"
                or facts.get("verification") != "valid" or facts.get("replay") != "passed"
                or facts.get("selected_time") is None
                or facts.get("candidate_ids") != request["candidate_ids"]
                or facts.get("future_hard_allowance") != request["future_hard_allowance"]):
            raise DomainError("followup_design_required", "A checked selected time for the original pair is required.", 422)
        problem = self._get(conn, actor, request["problem_id"], "problem")
        dataset = self._get(conn, actor, problem["body"]["dataset_id"], "dataset")
        proposal = self._get(conn, actor, scope["observation_proposal_id"], "observation_proposal")
        artifact = self._get(conn, actor, scope["source_artifact_id"], "native_artifact")
        for record in (revised_dataset, result, plan, problem, dataset, proposal, artifact):
            self._same_workspace(workspace_id, record)
        if proposal["body"]["origin"] != "hypothetical":
            raise DomainError("followup_origin_unsupported", "The native follow-up checker currently admits an explicitly hypothetical reading only.", 422, ["followup.observation_proposal_id"])
        old, new, observation = dataset["body"], revised_dataset["body"], proposal["body"]
        row = observation["row"]
        def unchanged_problem(value):
            return {key: item for key, item in value.items() if key not in {"dataset_id", "dataset_digest"}}
        if (body["problem_digest"] != revised_problem["digest"] or body["dataset_id"] != revised_dataset["id"]
                or revised_problem["body"]["dataset_digest"] != revised_dataset["digest"]
                or revised_problem["id"] == problem["id"] or request["problem_digest"] != problem["digest"]
                or new.get("parent_id") != dataset["id"] or revised_dataset["parent_id"] != dataset["id"]
                or new["origin"] != "hypothetical" or new["experiment_id"] != old["experiment_id"]
                or new["time_origin"] != old["time_origin"] or new["rows"] != [*old["rows"], row]
                or unchanged_problem(revised_problem["body"]) != unchanged_problem(problem["body"])
                or observation["dataset_id"] != dataset["id"] or observation["experiment_id"] != old["experiment_id"]
                or row["time"] != facts["selected_time"] or row["hard_allowance"] != request["future_hard_allowance"]
                or row["included"] is not True or row.get("source_asset_id") is not None):
            raise DomainError("followup_lineage_mismatch", "Follow-up must preserve the original inputs and append exactly the reviewed hypothetical reading at the selected time and allowance.", 422)
        reviews = [_record(record) for record in conn.execute(
            "SELECT * FROM entities WHERE workspace_id=? AND kind='observation_review' AND parent_id=?", (workspace_id, proposal["id"]))]
        review = next((item for item in reviews if item["body"] == {
            "proposal_id": proposal["id"], "proposal_digest": proposal["digest"], "dataset_id": revised_dataset["id"],
            "dataset_digest": revised_dataset["digest"], "accepted": True}), None)
        if review is None:
            raise DomainError("observation_review_required", "A matching explicit observation review must have created this dataset revision.", 422)
        refs = facts.get("artifacts", [])
        expected_origin = {"run_id": job["id"], "scenario_id": request["scenario_id"],
                           "plan_id": plan["id"], "approval_id": job["approval_id"]}
        anchor = artifact["body"].get("anchor", {})
        if (len(refs) != 1 or refs[0]["id"] != artifact["id"]
                or any(artifact["body"].get(key) != refs[0][key] for key in ("sha256", "byte_size", "media_type"))
                or artifact["body"].get("origin") != expected_origin
                or anchor != {"artifact_sha256": refs[0]["sha256"], "dataset_digest": dataset["digest"],
                    "problem_digest": problem["digest"], "projection_digest": facts.get("scientific_problem_digest"),
                    "app_request_digest": plan["body"]["request_digest"], "design_digest": facts.get("scientific_design_digest"),
                    "run_id": job["id"], "scenario_id": request["scenario_id"]}):
            raise DomainError("artifact_binding_mismatch", "Follow-up must retain the selected design's original bytes and external replay anchors.", 422)
        return {"problem": problem, "dataset": dataset, "revised_problem": revised_problem,
                "revised_dataset": revised_dataset, "design_job": job, "design_plan": plan, "design_result": result,
                "observation_proposal": proposal, "observation_review": review, "artifact": artifact}

    def create_provider_consent(self, actor: str, workspace_id: str, body: dict, key: str) -> dict:
        from .contracts import AgentProviderConsent
        body = AgentProviderConsent.model_validate(_body(body)).model_dump(mode="json")
        def action(conn: sqlite3.Connection) -> dict:
            self._same_workspace(workspace_id, self._get(conn, actor, body["problem_id"], "problem"))
            for source_id in body["source_asset_ids"]:
                self._same_workspace(workspace_id, self._get(conn, actor, source_id, "source_asset"))
            return self._insert(conn, actor, workspace_id, "provider_consent", body)
        return self._perform(actor, workspace_id, "create:provider-consent", key, body, action)

    def _approve(self, actor: str, plan_id: str, expected_revision_id: str,
                 plan_digest: str, key: str, scope: str, expires_seconds: int = 900) -> dict:
        if not 1 <= expires_seconds <= 3600:
            raise DomainError("invalid_expiry", "Approval lifetime must be between one second and one hour.", 422)
        kind = "plan" if scope == "investigation" else "design_plan"
        plan = self.get(actor, plan_id, kind)
        request = {"plan_id": plan_id, "plan_digest": plan_digest, "expected_revision_id": expected_revision_id, "expires_seconds": expires_seconds}
        def action(conn: sqlite3.Connection) -> dict:
            frozen = self._get(conn, actor, plan_id, kind)
            if frozen["digest"] != plan_digest:
                raise DomainError("binding_mismatch", "Approval does not match the exact previewed plan.", 422, ["plan_digest"])
            expected = frozen["body"]["problem_id"] if scope == "investigation" else frozen["body"]["request"]["problem_id"]
            if expected_revision_id != expected:
                raise DomainError("stale_revision", "Approval must name the reviewed problem revision.", current_revision_id=expected)
            if scope == "investigation":
                current = self.authorize(actor, plan["workspace_id"], conn)
                if current["current_problem_id"] != expected:
                    raise DomainError("stale_revision", "Inputs changed after this preview. Create and review a new plan.", current_revision_id=current["current_problem_id"])
            existing = conn.execute("SELECT * FROM approvals WHERE plan_id=? AND actor_id=?", (plan_id, actor)).fetchone()
            if existing:
                if existing["expires_at"] <= utc_now():
                    raise DomainError("approval_expired", "Create a new reviewed plan after this approval expires.")
                return dict(existing)
            approval_id = _id("approval")
            expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_seconds)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            conn.execute("INSERT INTO approvals VALUES (?,?,?,?,?,?,?,?,?)", (approval_id, plan["workspace_id"], plan_id, plan_digest, actor, scope, expected_revision_id, utc_now(), expires_at))
            return dict(conn.execute("SELECT * FROM approvals WHERE id=?", (approval_id,)).fetchone())
        return self._perform(actor, plan["workspace_id"], f"approve:{scope}:{plan_id}", key, request, action)

    def approve_plan(self, actor: str, plan_id: str, expected_revision_id: str, plan_digest: str, key: str, expires_seconds: int = 900) -> dict:
        return self._approve(actor, plan_id, expected_revision_id, plan_digest, key, "investigation", expires_seconds)

    def approve_design_plan(self, actor: str, plan_id: str, expected_revision_id: str, plan_digest: str, key: str, expires_seconds: int = 900) -> dict:
        return self._approve(actor, plan_id, expected_revision_id, plan_digest, key, "design", expires_seconds)

    def _job(self, conn: sqlite3.Connection, actor: str, job_id: str, kind: str | None = None) -> dict:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None or (kind and row["kind"] != kind):
            raise DomainError("not_found", "Workspace or record was not found.", 404)
        self.authorize(actor, row["workspace_id"], conn)
        job = dict(row)
        job["scenarios"] = [dict(child) for child in conn.execute("SELECT * FROM scenario_reservations WHERE run_id=? ORDER BY created_at,id", (job_id,))]
        return job

    def get_run(self, actor: str, run_id: str) -> dict:
        with self.store.read() as conn:
            return self._job(conn, actor, run_id, "run")

    def get_design_job(self, actor: str, job_id: str) -> dict:
        with self.store.read() as conn:
            return self._job(conn, actor, job_id, "design_job")

    def _start(self, actor: str, plan_id: str, approval_id: str, key: str, scope: str) -> dict:
        plan_kind, job_kind = ("plan", "run") if scope == "investigation" else ("design_plan", "design_job")
        plan = self.get(actor, plan_id, plan_kind)
        request = {"plan_id": plan_id, "approval_id": approval_id}
        def action(conn: sqlite3.Connection) -> dict:
            approval = conn.execute("SELECT * FROM approvals WHERE id=? AND actor_id=? AND plan_id=? AND scope=?", (approval_id, actor, plan_id, scope)).fetchone()
            if approval is None or approval["workspace_id"] != plan["workspace_id"] or approval["plan_digest"] != plan["digest"]:
                raise DomainError("approval_required", "A matching approval by the authenticated person is required.", 403)
            existing = conn.execute("SELECT * FROM jobs WHERE plan_id=?", (plan_id,)).fetchone()
            if existing:
                if existing["approval_id"] != approval_id:
                    raise DomainError("plan_already_started", "This plan already has its one accepted run.")
                return self._job(conn, actor, existing["id"])
            if approval["expires_at"] <= utc_now():
                raise DomainError("approval_expired", "The approval expired before work was reserved.", 403)
            if scope == "investigation":
                current = self.authorize(actor, plan["workspace_id"], conn)
                if current["current_problem_id"] != approval["expected_revision_id"]:
                    raise DomainError("stale_revision", "Inputs changed before work was reserved. Review a new plan.", current_revision_id=current["current_problem_id"])
            job_id = _id(job_kind)
            conn.execute("INSERT INTO jobs(id,workspace_id,plan_id,approval_id,actor_id,kind,state,created_at) VALUES (?,?,?,?,?,?,'queued',?)",
                         (job_id, plan["workspace_id"], plan_id, approval_id, actor, job_kind, utc_now()))
            return self._job(conn, actor, job_id)
        return self._perform(actor, plan["workspace_id"], f"start:{scope}:{plan_id}", key, request, action)

    def start_run(self, actor: str, plan_id: str, approval_id: str, key: str) -> dict:
        return self._start(actor, plan_id, approval_id, key, "investigation")

    def start_design_job(self, actor: str, plan_id: str, approval_id: str, key: str) -> dict:
        return self._start(actor, plan_id, approval_id, key, "design")

    def mark_running(self, actor: str, job_id: str, worker_id: str) -> dict:
        with self.store.transaction() as conn:
            job = self._job(conn, actor, job_id)
            if job["state"] != "queued":
                raise DomainError("job_not_queued", "This durable reservation cannot be dispatched again.")
            conn.execute("UPDATE jobs SET state='running',started_at=?,worker_id=? WHERE id=?", (utc_now(), worker_id, job_id))
            return self._job(conn, actor, job_id)

    def check_run_scope(self, actor: str, run_id: str) -> dict:
        with self.store.read() as conn:
            job = self._job(conn, actor, run_id)
            plan = self._get(conn, actor, job["plan_id"])
            self._active(job, plan)
            return {"job": job, "plan": plan}

    def _active(self, job: dict, plan: dict) -> None:
        if job["state"] not in {"queued", "running"}:
            raise DomainError("job_not_active", "This job no longer permits additional work.", 409)
        with self.store.read() as conn:
            approval = conn.execute("SELECT expires_at FROM approvals WHERE id=?", (job["approval_id"],)).fetchone()
            if approval is None or approval["expires_at"] <= utc_now():
                raise DomainError("approval_expired", "The approval expired; completed evidence is preserved but no additional work is admitted.", 403)
        if job.get("started_at"):
            budget = plan["body"].get("budget") or plan["body"].get("request", {}).get("budget", {})
            deadline = datetime.fromisoformat(job["started_at"].replace("Z", "+00:00")) + timedelta(seconds=budget.get("wall_seconds", 120))
            if datetime.now(timezone.utc) >= deadline:
                raise DomainError("budget_exhausted", "The approved wall-time budget is exhausted.")

    def consume_budget(self, actor: str, run_id: str, category: str) -> dict:
        if category not in {"tool_calls", "provider_turns"}:
            raise ValueError("Unknown budget counter")
        with self.store.transaction() as conn:
            job = self._job(conn, actor, run_id)
            plan = self._get(conn, actor, job["plan_id"])
            self._active(job, plan)
            limit = plan["body"].get("budget", {}).get(category, 0)
            if job[category] >= limit:
                raise DomainError("budget_exhausted", "The approved invocation budget is exhausted.")
            conn.execute(f"UPDATE jobs SET {category}={category}+1 WHERE id=?", (run_id,))
            return self._job(conn, actor, run_id)

    def reserve_scenario(self, actor: str, run_id: str, scenario_id: str) -> dict:
        with self.store.transaction() as conn:
            job = self._job(conn, actor, run_id, "run")
            plan = self._get(conn, actor, job["plan_id"], "plan")
            self._active(job, plan)
            if "execute_approved_scenario" not in plan["body"]["permitted_tools"]:
                raise DomainError("tool_not_approved", "This plan does not allow scenario execution.", 403)
            scenario = next((item for item in plan["body"]["scenarios"] if item["id"] == scenario_id), None)
            if scenario is None:
                raise DomainError("scenario_not_approved", "This scenario was not listed in the approved plan.", 403)
            existing = conn.execute("SELECT * FROM scenario_reservations WHERE run_id=? AND scenario_id=?", (run_id, scenario_id)).fetchone()
            if existing:
                return {**dict(existing), "created_new": False}
            baseline = next(item for item in plan["body"]["scenarios"] if item["kind"] == "baseline")
            if scenario["kind"] != "baseline":
                complete = conn.execute("SELECT state,result_id FROM scenario_reservations WHERE run_id=? AND scenario_id=?", (run_id, baseline["id"])).fetchone()
                if complete is None or complete["state"] != "completed":
                    raise DomainError("baseline_required", "The mandatory baseline must return evidence before optional work.", 403)
                eligible = scenario.get("eligible_baseline_outcomes")
                if eligible:
                    baseline_evidence = self._get(conn, actor, complete["result_id"], "evidence")
                    if baseline_evidence["body"]["result"]["scientific_outcome"] not in eligible:
                        raise DomainError("scenario_condition_ineligible", "The actual baseline outcome does not satisfy this scenario's reviewed eligibility condition.", 403)
            if job["scientific_reservations"] >= plan["body"]["budget"]["scientific_reservations"]:
                raise DomainError("budget_exhausted", "No scientific reservations remain.")
            reservation_id = _id("scenario")
            conn.execute("INSERT INTO scenario_reservations(id,run_id,scenario_id,state,created_at) VALUES (?,?,?,'reserved',?)", (reservation_id, run_id, scenario_id, utc_now()))
            conn.execute("UPDATE jobs SET scientific_reservations=scientific_reservations+1 WHERE id=?", (run_id,))
            return {**dict(conn.execute("SELECT * FROM scenario_reservations WHERE id=?", (reservation_id,)).fetchone()), "created_new": True}

    def mark_scenario_running(self, actor: str, run_id: str, scenario_id: str) -> dict:
        with self.store.transaction() as conn:
            job = self._job(conn, actor, run_id, "run")
            self._active(job, self._get(conn, actor, job["plan_id"], "plan"))
            row = conn.execute("SELECT * FROM scenario_reservations WHERE run_id=? AND scenario_id=?", (run_id, scenario_id)).fetchone()
            if row is None or row["state"] != "reserved":
                raise DomainError("scenario_not_reserved", "The scenario cannot be dispatched again.")
            conn.execute("UPDATE scenario_reservations SET state='running' WHERE id=?", (row["id"],))
            return dict(conn.execute("SELECT * FROM scenario_reservations WHERE id=?", (row["id"],)).fetchone())

    def complete_scenario(self, actor: str, run_id: str, scenario_id: str, evidence: dict) -> dict:
        from .contracts import ScientificResult
        evidence = ScientificResult.model_validate(_body(evidence)).model_dump(mode="json")
        with self.store.transaction() as conn:
            job = self._job(conn, actor, run_id, "run")
            plan = self._get(conn, actor, job["plan_id"], "plan")
            scenario = next((item for item in plan["body"]["scenarios"] if item["id"] == scenario_id), None)
            row = conn.execute("SELECT * FROM scenario_reservations WHERE run_id=? AND scenario_id=?", (run_id, scenario_id)).fetchone()
            if scenario is None or row is None:
                raise DomainError("scenario_not_reserved", "Evidence must belong to a reserved scenario.", 403)
            if evidence["problem_id"] != scenario["problem_id"] or evidence["problem_digest"] not in {None, scenario["problem_digest"]}:
                raise DomainError("binding_mismatch", "Adapter evidence names a different expected scientific problem.", 422)
            if evidence["expected_binding"] == "matches" and evidence["problem_digest"] != scenario["problem_digest"]:
                raise DomainError("binding_mismatch", "Matching evidence must bind the independently supplied reviewed problem digest.", 422)
            if row["result_id"]:
                existing = self._get(conn, actor, row["result_id"], "evidence")
                if existing["body"]["result"] != _body(evidence):
                    raise DomainError("evidence_conflict", "Completed evidence is immutable.")
                return existing
            if row["state"] not in {"reserved", "running"}:
                raise DomainError("scenario_interrupted", "This scenario needs reconciliation before new evidence is attached.")
            # Exact result preserved. Backend never promotes numerical or mismatched output.
            envelope = {"run_id": run_id, "scenario_id": scenario_id, "problem_id": scenario["problem_id"],
                        "expected_problem_digest": scenario["problem_digest"], "result": _body(evidence),
                        "arrived_after_cancel": job["state"] == "cancel_requested"}
            result = self._insert(conn, actor, job["workspace_id"], "evidence", envelope)
            conn.execute("UPDATE scenario_reservations SET state='completed',result_id=?,finished_at=? WHERE id=?", (result["id"], utc_now(), row["id"]))
            return result

    def skip_scenario(self, actor: str, run_id: str, scenario_id: str, reason_code: str) -> dict:
        allowed = {"not_relevant", "sufficient_evidence", "budget_preserved", "capability_unavailable"}
        if reason_code not in allowed:
            raise DomainError("invalid_skip_reason", "Select an allowed bounded reason code.", 422)
        with self.store.transaction() as conn:
            job = self._job(conn, actor, run_id, "run")
            plan = self._get(conn, actor, job["plan_id"], "plan")
            self._active(job, plan)
            if "record_allowed_skip" not in plan["body"]["permitted_tools"]:
                raise DomainError("tool_not_approved", "This plan does not allow skipping optional work.", 403)
            scenario = next((item for item in plan["body"]["scenarios"] if item["id"] == scenario_id), None)
            if scenario is None or scenario["kind"] != "optional":
                raise DomainError("skip_not_allowed", "Only an unreserved optional scenario can be skipped.", 403)
            baseline = next(item for item in plan["body"]["scenarios"] if item["kind"] == "baseline")
            baseline_row = conn.execute("SELECT state FROM scenario_reservations WHERE run_id=? AND scenario_id=?", (run_id, baseline["id"])).fetchone()
            if baseline_row is None or baseline_row["state"] != "completed":
                raise DomainError("baseline_required", "The mandatory baseline must return evidence before an adaptive skip.", 403)
            existing = conn.execute("SELECT * FROM scenario_reservations WHERE run_id=? AND scenario_id=?", (run_id, scenario_id)).fetchone()
            if existing:
                if existing["state"] == "skipped" and existing["reason_code"] == reason_code:
                    return dict(existing)
                raise DomainError("skip_not_allowed", "Reserved or completed scientific work cannot be replaced by a skip.")
            reservation_id = _id("scenario")
            conn.execute("INSERT INTO scenario_reservations(id,run_id,scenario_id,state,created_at,finished_at,reason_code) VALUES (?,?,?,'skipped',?,?,?)", (reservation_id, run_id, scenario_id, utc_now(), utc_now(), reason_code))
            return dict(conn.execute("SELECT * FROM scenario_reservations WHERE id=?", (reservation_id,)).fetchone())

    def read_evidence(self, actor: str, run_id: str, evidence_id: str) -> dict:
        with self.store.read() as conn:
            job = self._job(conn, actor, run_id)
            plan = self._get(conn, actor, job["plan_id"])
            if "read_scoped_evidence" not in plan["body"]["permitted_tools"]:
                raise DomainError("tool_not_approved", "This plan does not allow the agent evidence-reading tool.", 403)
            evidence = self._get(conn, actor, evidence_id, "evidence")
            if evidence["body"]["run_id"] != run_id:
                raise DomainError("evidence_not_in_scope", "This evidence is not part of the accepted run.", 403)
            return evidence

    def finish_run(self, actor: str, job_id: str, state: str = "completed", result: dict | None = None,
                   error_code: str | None = None) -> dict:
        if state not in {"completed", "cancelled", "failed", "interrupted"}:
            raise ValueError("Expected terminal execution state")
        with self.store.transaction() as conn:
            job = self._job(conn, actor, job_id)
            if job["state"] in {"completed", "cancelled", "failed", "interrupted"}:
                return job
            active = conn.execute("SELECT 1 FROM scenario_reservations WHERE run_id=? AND state IN ('reserved','running')", (job_id,)).fetchone()
            if active:
                raise DomainError("worker_not_reconciled", "Child work must terminate or be reconciled before the parent finishes.")
            if job["state"] == "cancel_requested":
                # Cancellation may arrive after the worker's last state read.
                # Preserve any supplied result, but honor the durable request
                # after child computation has stopped.
                state = "cancelled"
            if state == "completed" and job["kind"] == "run":
                plan = self._get(conn, actor, job["plan_id"], "plan")
                baseline = next(item for item in plan["body"]["scenarios"] if item["kind"] == "baseline")
                baseline_row = conn.execute("SELECT state FROM scenario_reservations WHERE run_id=? AND scenario_id=?", (job_id, baseline["id"])).fetchone()
                if baseline_row is None or baseline_row["state"] != "completed":
                    raise DomainError("baseline_required", "The mandatory baseline must have evidence before completion.")
                for scenario in plan["body"]["scenarios"]:
                    status = conn.execute("SELECT state FROM scenario_reservations WHERE run_id=? AND scenario_id=?", (job_id, scenario["id"])).fetchone()
                    if status is None or status["state"] not in {"completed", "skipped"}:
                        raise DomainError("scenario_accounting_incomplete", "Successful completion must account for every reviewed scenario as executed or explicitly skipped.")
            if job["kind"] == "design_job" and result is not None:
                from .contracts import DesignResult
                result = DesignResult.model_validate(_body(result)).model_dump(mode="json")
                request = self._get(conn, actor, job["plan_id"], "design_plan")["body"]["request"]
                if [option["time"] for option in result["options"]] != request["feasible_times"]:
                    raise DomainError("design_grid_mismatch", "Every approved grid time must retain its evaluated, skipped, failed or unavailable state.", 422)
                if result["candidate_ids"] and result["candidate_ids"] != request["candidate_ids"]:
                    raise DomainError("candidate_not_in_scope", "Suggestion candidate IDs differ from the approved pair.", 422)
                if result["future_hard_allowance"] not in {None, request["future_hard_allowance"]}:
                    raise DomainError("binding_mismatch", "Suggestion future allowance differs from the approved request.", 422)
                if result["verification_record"] and result["verification_record"]["expected_problem_digest"] != request["problem_digest"]:
                    raise DomainError("binding_mismatch", "Suggestion verification does not bind the historical problem.", 422)
                if len(_json(result).encode()) > request["budget"]["bundle_bytes"]:
                    raise DomainError("artifact_size_limit", "The suggestion exceeds the approved byte budget.", 422)
            result_record = self._insert(conn, actor, job["workspace_id"], "suggestion" if job["kind"] == "design_job" else "run_summary", _body(result)) if result is not None else None
            conn.execute("UPDATE jobs SET state=?,finished_at=?,result_id=?,error_code=? WHERE id=?", (state, utc_now(), result_record["id"] if result_record else None, error_code, job_id))
            return self._job(conn, actor, job_id)

    def fail_scenario(self, actor: str, run_id: str, scenario_id: str, error_code: str) -> dict:
        with self.store.transaction() as conn:
            self._job(conn, actor, run_id, "run")
            row = conn.execute("SELECT * FROM scenario_reservations WHERE run_id=? AND scenario_id=?", (run_id, scenario_id)).fetchone()
            if row is None:
                raise DomainError("not_found", "Scenario reservation was not found.", 404)
            if row["state"] in {"reserved", "running"}:
                conn.execute("UPDATE scenario_reservations SET state='failed',reason_code=?,finished_at=? WHERE id=?", (error_code, utc_now(), row["id"]))
            return dict(conn.execute("SELECT * FROM scenario_reservations WHERE id=?", (row["id"],)).fetchone())

    def cancel_run(self, actor: str, job_id: str, key: str) -> dict:
        with self.store.read() as conn:
            job = self._job(conn, actor, job_id)
        def action(conn: sqlite3.Connection) -> dict:
            current = self._job(conn, actor, job_id)
            if current["state"] in {"queued", "running"}:
                conn.execute("UPDATE jobs SET state='cancel_requested' WHERE id=?", (job_id,))
            return self._job(conn, actor, job_id)
        return self._perform(actor, job["workspace_id"], f"cancel:{job_id}", key, {"job_id": job_id}, action)

    def recover_interrupted(self) -> dict:
        """Explicit single-worker startup recovery; never redispatch in-flight calls.

        Call only after establishing that the previous worker is gone. Queued
        reservations remain safe to dispatch; accepted running work is preserved.
        """
        with self.store.transaction() as conn:
            now = utc_now()
            # No child was ever started for these jobs. A restart must still
            # acknowledge the user's cancellation instead of inventing an
            # interrupted scientific attempt.
            cancelled = conn.execute("UPDATE jobs SET state='cancelled',finished_at=? "
                "WHERE state='cancel_requested' AND started_at IS NULL", (now,)).rowcount
            jobs = conn.execute("UPDATE jobs SET state='interrupted',finished_at=?,error_code='worker_restart' WHERE state IN ('running','cancel_requested')", (now,)).rowcount
            children = conn.execute("UPDATE scenario_reservations SET state='interrupted',finished_at=?,reason_code='worker_restart' WHERE state IN ('reserved','running') AND run_id IN (SELECT id FROM jobs WHERE state='interrupted')", (now,)).rowcount
            attempts = conn.execute("UPDATE provider_attempts SET state='unknown_outcome',finished_at=? WHERE state='reserved'", (now,)).rowcount
            operations = conn.execute("UPDATE operations SET state='interrupted',finished_at=?,error_code='worker_restart' WHERE state='reserved'", (now,)).rowcount
            return {"jobs": jobs + cancelled, "queued_cancellations": cancelled,
                    "scenarios": children, "provider_attempts": attempts, "operations": operations}

    def queued_jobs(self, limit: int = 20) -> list[dict]:
        """Internal dispatcher inventory, never expose without workspace filtering."""
        with self.store.read() as conn:
            return [dict(row) for row in conn.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY created_at,id LIMIT ?", (max(1, min(limit, 100)),))]

    def accept_turn(self, actor: str, workspace_id: str, key: str, body: dict, expected_revision: int) -> dict:
        body = _body(body)
        def action(conn: sqlite3.Connection) -> dict:
            current = self.authorize(actor, workspace_id, conn)
            if current["conversation_revision"] != expected_revision:
                raise DomainError("stale_conversation", "Open the current conversation before adding another turn.", current_revision_id=str(current["conversation_revision"]))
            turn = self._insert(conn, actor, workspace_id, "user_turn", {**body, "conversation_revision": expected_revision + 1})
            conn.execute("UPDATE workspaces SET conversation_revision=conversation_revision+1 WHERE id=?", (workspace_id,))
            return turn
        return self._perform(actor, workspace_id, "assistant-turn", key, {"body": body, "expected_revision": expected_revision}, action)

    def create_design_plan(self, actor: str, run_id: str, body: dict, key: str) -> dict:
        from .contracts import DesignPlanBody, DesignRequestBody
        request = DesignRequestBody.model_validate(_body(body)).model_dump(mode="json")
        run = self.get_run(actor, run_id)
        def action(conn: sqlite3.Connection) -> dict:
            current = self._job(conn, actor, run_id, "run")
            historical = self._get(conn, actor, current["plan_id"], "plan")
            if request["historical_run_id"] != run_id:
                raise DomainError("binding_mismatch", "The design request must name the selected historical run.", 422)
            scenario = next((item for item in historical["body"]["scenarios"] if item["id"] == request["scenario_id"]), None)
            if scenario is None or scenario["problem_id"] != request["problem_id"] or scenario["problem_digest"] != request["problem_digest"]:
                raise DomainError("binding_mismatch", "Design must bind the exact historical scenario and problem.", 422)
            child = conn.execute("SELECT * FROM scenario_reservations WHERE run_id=? AND scenario_id=?", (run_id, request["scenario_id"])).fetchone()
            if child is None or child["state"] != "completed" or not child["result_id"]:
                raise DomainError("historical_evidence_required", "The selected scenario needs usable historical evidence before design.", 422)
            evidence = self._get(conn, actor, child["result_id"], "evidence")["body"]["result"]
            native_design = evidence.get("projection_version") == "DB-SC-1-to-groundwork-v1"
            if evidence.get("expected_binding") == "mismatch":
                raise DomainError("binding_mismatch", "Mismatched evidence cannot support a design proposal.", 422)
            if native_design:
                if request.get("scientific_profile") != "counterdex.v1" or request.get("requested_tier") != "checked_pair_separation":
                    raise DomainError("unsupported_design_tier", "Native baseline design supports a reviewed request for checked pair separation.",
                                      422, ["requested_tier"])
                if (evidence.get("verification") != "valid" or evidence.get("replay") != "passed"
                        or evidence.get("expected_binding") != "matches"):
                    raise DomainError("historical_evidence_required", "Design requires matching freshly checked historical evidence.", 422)
                refs = evidence.get("artifacts", [])
                if len(refs) != 1 or request["source_artifact_ids"] != [refs[0]["id"]]:
                    raise DomainError("historical_artifact_required", "Select the original native baseline artifact for this pair.",
                                      422, ["source_artifact_ids"])
            if request.get("scientific_profile") == "counterdex.v1":
                from fractions import Fraction
                from .scientific_projection import _exact, project_design, project_problem
                problem = self._get(conn, actor, request["problem_id"], "problem")
                dataset = self._get(conn, actor, problem["body"]["dataset_id"], "dataset")
                historical_horizon = max(Fraction(row["time"]) for row in dataset["body"]["rows"] if row["included"])
                if Fraction(request["maximum_horizon"]) < historical_horizon:
                    raise DomainError("unavailable_horizon", "The reviewed horizon must cover the included historical observations.", 422, ["maximum_horizon"])
                historical_artifacts = {artifact["id"]: artifact for artifact in evidence.get("artifacts", [])}
                for artifact_id in request.get("source_artifact_ids", []):
                    if artifact_id not in historical_artifacts:
                        raise DomainError("artifact_not_in_scope", "A source artifact must belong to the selected historical scenario.", 422, ["source_artifact_ids"])
                    artifact = self._get(conn, actor, artifact_id, "native_artifact")
                    self._same_workspace(run["workspace_id"], artifact)
                    if any(artifact["body"][key] != historical_artifacts[artifact_id][key]
                           for key in ("sha256", "byte_size", "media_type")):
                        raise DomainError("artifact_binding_mismatch", "Historical native artifact bytes differ from the selected reference.", 422, ["source_artifact_ids"])
                    if native_design and artifact["body"].get("origin") != {
                            "run_id": run_id, "scenario_id": request["scenario_id"],
                            "plan_id": current["plan_id"], "approval_id": current["approval_id"]}:
                        raise DomainError("artifact_binding_mismatch", "Native baseline provenance differs from the selected approved run.", 422)
                if native_design:
                    # The new engine mapping consumes the complete native baseline;
                    # do not reinterpret it through the legacy fixed-pair projection.
                    for index, time_value in enumerate(request["feasible_times"]):
                        _exact(time_value, f"feasible_times[{index}]")
                    _exact(request["future_hard_allowance"], "future_hard_allowance")
                    _exact(request["maximum_horizon"], "maximum_horizon")
                    if request["budget"]["pair_verifications"] < 2:
                        raise DomainError("scientific_admission", "Checking and fresh replay require two approved pair verifications.",
                                          422, ["budget.pair_verifications"])
                    if request["candidate_vectors"][0] == request["candidate_vectors"][1]:
                        raise DomainError("candidate_vector_mismatch", "Select two distinct historical vectors.", 422, ["candidate_vectors"])
                else:
                    project_design(request, project_problem(problem, dataset), [None, None])
            candidates = {item.get("id"): item for item in evidence.get("candidates", []) if isinstance(item, dict)}
            for candidate_id, vector in zip(request["candidate_ids"], request["candidate_vectors"], strict=True):
                candidate = candidates.get(candidate_id)
                if candidate is None:
                    raise DomainError("candidate_not_in_scope", "Both fixed candidates must be present in the selected historical evidence.", 422, ["candidate_ids"])
                if native_design and candidate.get("verification") != "valid":
                    raise DomainError("candidate_not_compatible", "Both selected candidates need valid historical compatibility checks.", 422, ["candidate_ids"])
                candidate_vector = candidate.get("parameter_vector")
                if candidate_vector != vector:
                    raise DomainError("candidate_vector_mismatch", "The exact fixed vector differs from its historical candidate.", 422, ["candidate_vectors"])
                if candidate.get("problem_id") != request["problem_id"] or candidate.get("problem_digest") != request["problem_digest"]:
                    raise DomainError("binding_mismatch", "Candidate belongs to a different immutable problem identity.", 422)
            request_record = self._insert(conn, actor, run["workspace_id"], "design_request", request)
            plan_body = DesignPlanBody(request=request, request_digest=request_record["digest"]).model_dump(mode="json")
            result = self._insert(conn, actor, run["workspace_id"], "design_plan", plan_body, request_record["id"])
            return result
        return self._perform(actor, run["workspace_id"], f"create:design-plan:{run_id}", key, request, action)

    def create_observation_proposal(self, actor: str, workspace_id: str, body: dict, key: str) -> dict:
        from .contracts import ObservationProposalBody
        body = ObservationProposalBody.model_validate(_body(body)).model_dump(mode="json")
        def action(conn: sqlite3.Connection) -> dict:
            dataset = self._get(conn, actor, body["dataset_id"], "dataset")
            self._same_workspace(workspace_id, dataset)
            if dataset["body"]["experiment_id"] != body["experiment_id"]:
                raise DomainError("experiment_mismatch", "The observation must name its parent experiment.", 422)
            if any(row["id"] == body["row"]["id"] for row in dataset["body"]["rows"]):
                raise DomainError("duplicate_row", "An observation needs a new row identity.", 422, ["row.id"])
            source_id = body["row"].get("source_asset_id")
            if source_id:
                self._same_workspace(workspace_id, self._get(conn, actor, source_id, "source_asset"))
                raise DomainError("source_review_required", "Source-derived observations must be materialized from an exact intake review.", 422, ["row.source_asset_id"])
            return self._insert(conn, actor, workspace_id, "observation_proposal", body, dataset["id"])
        return self._perform(actor, workspace_id, "create:observation-proposal", key, body, action)

    def review_observation(self, actor: str, proposal_id: str, body: dict, key: str) -> dict:
        from .contracts import DatasetBody, ObservationReviewRequest
        review = ObservationReviewRequest.model_validate(_body(body)).model_dump(mode="json")
        proposal = self.get(actor, proposal_id, "observation_proposal")
        def action(conn: sqlite3.Connection) -> dict:
            frozen = self._get(conn, actor, proposal_id, "observation_proposal")
            if review["proposal_digest"] != frozen["digest"] or review["parent_dataset_id"] != frozen["body"]["dataset_id"]:
                raise DomainError("binding_mismatch", "Review must confirm this exact proposal and parent dataset.", 422)
            if frozen["body"]["row"].get("source_asset_id"):
                raise DomainError("source_review_required", "Source-derived observations must be materialized from an exact intake review.", 422, ["row.source_asset_id"])
            dataset = self._get(conn, actor, review["parent_dataset_id"], "dataset")
            current = self.authorize(actor, proposal["workspace_id"], conn)
            if current["current_dataset_id"] != dataset["id"]:
                raise DomainError("stale_revision", "The dataset changed while this observation was awaiting review.", current_revision_id=current["current_dataset_id"])
            # Persist source/generator provenance on the immutable proposal. The new
            # dataset links to that accepted proposal through a separate review record.
            origin = "hypothetical" if frozen["body"]["origin"] == "hypothetical" or dataset["body"]["origin"] == "hypothetical" else dataset["body"]["origin"]
            revised = DatasetBody.model_validate({**dataset["body"], "parent_id": dataset["id"],
                "rows": [*dataset["body"]["rows"], frozen["body"]["row"]], "origin": origin,
                "change_reason": frozen["body"]["change_reason"]}).model_dump(mode="json")
            result = self._insert(conn, actor, proposal["workspace_id"], "dataset", revised, dataset["id"])
            self._insert(conn, actor, proposal["workspace_id"], "observation_review", {
                "proposal_id": proposal_id, "proposal_digest": frozen["digest"], "dataset_id": result["id"],
                "dataset_digest": result["digest"], "accepted": True}, proposal_id)
            conn.execute("UPDATE workspaces SET current_dataset_id=?,current_problem_id=NULL WHERE id=?", (result["id"], proposal["workspace_id"]))
            return result
        return self._perform(actor, proposal["workspace_id"], f"review:observation:{proposal_id}", key, review, action)

    def metrics(self, actor: str, workspace_id: str) -> dict:
        """Operational analytics only; never a source of scientific input values."""
        with self.store.read() as conn:
            self.authorize(actor, workspace_id, conn)
            states = {row["state"]: row["n"] for row in conn.execute("SELECT state,count(*) n FROM jobs WHERE workspace_id=? GROUP BY state", (workspace_id,))}
            pending = conn.execute("SELECT count(*) FROM entities e WHERE e.workspace_id=? AND e.kind='design_plan' AND NOT EXISTS (SELECT 1 FROM jobs j WHERE j.plan_id=e.id)", (workspace_id,)).fetchone()[0]
            samples = [dict(row) for row in conn.execute("SELECT j.id,a.created_at AS approved_at,j.created_at AS reserved_at,j.finished_at FROM jobs j JOIN approvals a ON a.id=j.approval_id WHERE j.workspace_id=? ORDER BY j.created_at DESC LIMIT 50", (workspace_id,))]
            durations = []
            for sample in samples:
                if sample["finished_at"]:
                    start = datetime.fromisoformat(sample["approved_at"].replace("Z", "+00:00"))
                    end = datetime.fromisoformat(sample["finished_at"].replace("Z", "+00:00"))
                    durations.append({"job_id": sample["id"], "milliseconds": max(0, int((end-start).total_seconds()*1000))})
            return {"job_states": states, "pending_design_reviews": pending,
                    "approval_to_result_samples": durations, "sample_count": len(durations),
                    "purpose": "Operational timing; no scale or performance claim."}

    def create_report(self, actor: str, run_id: str, key: str) -> dict:
        run = self.get_run(actor, run_id)
        def action(conn: sqlite3.Connection) -> dict:
            current = self._job(conn, actor, run_id, "run")
            plan = self._get(conn, actor, current["plan_id"], "plan")
            problem = self._get(conn, actor, plan["body"]["problem_id"], "problem")
            dataset = self._get(conn, actor, problem["body"]["dataset_id"], "dataset")
            evidence = [self._get(conn, actor, child["result_id"], "evidence") for child in current["scenarios"] if child["result_id"]]
            scenario_inputs = []
            source_ids = set(plan["body"]["provider_disclosure"]["source_asset_ids"])
            dataset_ids, problem_ids = set(), set()
            for scenario in plan["body"]["scenarios"]:
                scenario_problem = self._get(conn, actor, scenario["problem_id"], "problem")
                scenario_dataset = self._get(conn, actor, scenario_problem["body"]["dataset_id"], "dataset")
                scenario_inputs.append({"scenario_id": scenario["id"], "problem": scenario_problem, "dataset": scenario_dataset})
                source_ids.update(row["source_asset_id"] for row in scenario_dataset["body"]["rows"] if row["source_asset_id"])
                problem_ids.add(scenario_problem["id"])
                ancestor = scenario_dataset
                while ancestor["id"] not in dataset_ids:
                    dataset_ids.add(ancestor["id"])
                    if not ancestor["parent_id"]:
                        break
                    ancestor = self._get(conn, actor, ancestor["parent_id"], "dataset")
                    self._same_workspace(run["workspace_id"], ancestor)
            materializations, reviews, proposals = [], {}, {}
            for row in conn.execute("SELECT * FROM entities WHERE workspace_id=? AND kind='intake_materialization' ORDER BY created_at,id", (run["workspace_id"],)):
                materialization = _record(row)
                association = materialization["body"]
                if association["dataset_id"] not in dataset_ids and association["problem_id"] not in problem_ids:
                    continue
                review = self._get(conn, actor, association["review_id"], "intake_review")
                proposal = self._get(conn, actor, review["body"]["proposal_id"], "intake_proposal")
                self._same_workspace(run["workspace_id"], review)
                self._same_workspace(run["workspace_id"], proposal)
                materializations.append(materialization)
                reviews[review["id"]] = review
                proposals[proposal["id"]] = proposal
                source_ids.add(association["source_asset_id"])
            sources = []
            for source_id in sorted(source_ids):
                source = self._get(conn, actor, source_id, "source_asset")
                self._same_workspace(run["workspace_id"], source)
                # Storage locators are private implementation details, never export
                # material. The original raw byte digest remains independently useful.
                metadata = {key: value for key, value in source["body"].items() if key not in {"blob_key", "storage_path", "signed_url"}}
                sources.append({"id": source_id, "metadata": metadata, "created_at": source["created_at"]})
            designs = []
            for row in conn.execute("SELECT * FROM entities WHERE workspace_id=? AND kind='design_plan' ORDER BY created_at,id", (run["workspace_id"],)):
                design = _record(row)
                if design["body"]["request"]["historical_run_id"] != run_id:
                    continue
                job_row = conn.execute("SELECT id FROM jobs WHERE plan_id=?", (design["id"],)).fetchone()
                design_job = self._job(conn, actor, job_row["id"], "design_job") if job_row else None
                suggestion = self._get(conn, actor, design_job["result_id"], "suggestion") if design_job and design_job["result_id"] else None
                designs.append({"plan": design, "job": design_job, "suggestion": suggestion})
            native_artifacts = {}
            for result in [*evidence, *(item["suggestion"] for item in designs if item["suggestion"])]:
                result_body = result["body"].get("result", result["body"])
                for reference in result_body.get("artifacts", []):
                    # Legacy results may name externally retained artifacts.
                    # Include locally persisted metadata only, never blob locators.
                    row = conn.execute("SELECT * FROM entities WHERE id=? AND kind='native_artifact'", (reference["id"],)).fetchone()
                    if row is None:
                        continue
                    artifact = _record(row)
                    self._same_workspace(run["workspace_id"], artifact)
                    metadata = {name: value for name, value in artifact["body"].items() if name not in {"blob_key", "storage_path", "signed_url", "content_base64"}}
                    native_artifacts[artifact["id"]] = {"id": artifact["id"], "metadata": metadata, "created_at": artifact["created_at"]}
            manifest = {"schema_version": "DB-SC-1", "policy_version": "GF-2", "run": current,
                        "plan": plan, "problem": problem, "dataset": dataset, "evidence": evidence,
                        "scenario_inputs": scenario_inputs, "source_assets": sources, "designs": designs,
                        "intake_materializations": materializations, "intake_reviews": list(reviews.values()),
                        "intake_proposals": list(proposals.values()), "native_artifacts": list(native_artifacts.values()),
                        "replay": "unsupported", "source_reconstruction": "Source assets remain separately authenticated; raw bytes are not embedded in this manifest."}
            if plan["body"].get("followup"):
                context = self._followup_context(conn, actor, plan["body"])
                # Export immutable lineage, never the private blob locator used by
                # the worker to load the separately authenticated native bytes.
                manifest["followup"] = {key: value for key, value in context.items() if key != "artifact"}
                artifact = context["artifact"]
                manifest["followup"]["artifact"] = {"id": artifact["id"], "metadata": {
                    key: value for key, value in artifact["body"].items()
                    if key not in {"blob_key", "storage_path", "signed_url", "content_base64"}}}
            return self._insert(conn, actor, run["workspace_id"], "report", manifest)
        return self._perform(actor, run["workspace_id"], f"report:{run_id}", key, {"run_id": run_id}, action)
