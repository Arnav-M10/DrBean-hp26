"""Durable single-worker dispatcher. Running work is never silently replayed."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import fcntl
import json
from pathlib import Path
import threading
import time
import uuid

from .config import Settings
from .contracts import DesignResult, ScientificResult
from .coordinator import CoordinatorScope, ScopedCallbacks, run_coordinator
from .ledger import ProviderLedger
from .providers import AttemptContext, ProviderFailure
from .science import UnavailableAdapter, run_bounded
from .store import Store
from .workflow import DomainError, Workflow


class Worker:
    def __init__(self, workflow: Workflow, *, adapter=None, provider_config=None, ledger=None):
        self.workflow = workflow
        self.adapter = adapter or UnavailableAdapter()
        self.config = provider_config
        self.ledger = ledger or ProviderLedger(workflow.store)
        self.id = "worker_" + uuid.uuid4().hex

    def _cancelled(self, actor, job_id):
        return self.workflow.get(actor, job_id, "run")["state"] == "cancel_requested"

    def _fact(self, evidence):
        return {"id": evidence["id"], **evidence["body"]["result"]}

    async def _scenario(self, actor, run_id, scenario_id):
        scope = self.workflow.check_run_scope(actor, run_id)
        plan, job = scope["plan"], scope["job"]
        if "execute_approved_scenario" not in plan["body"]["permitted_tools"]:
            raise DomainError("tool_not_approved", "Scientific execution was not in the approved plan.", 403)
        reservation = self.workflow.reserve_scenario(actor, run_id, scenario_id)
        if not reservation["created_new"]:
            if reservation["result_id"]:
                return self._fact(self.workflow.read_evidence(actor, run_id, reservation["result_id"]))
            raise DomainError("scenario_pending", "Reserved work must be reconciled, never dispatched twice.")
        scenario = next(s for s in plan["body"]["scenarios"] if s["id"] == scenario_id)
        problem = self.workflow.get(actor, scenario["problem_id"], "problem")
        dataset = self.workflow.get(actor, problem["body"]["dataset_id"], "dataset")
        self.workflow.mark_scenario_running(actor, run_id, scenario_id)
        stop = threading.Event()
        started = datetime.fromisoformat(job["started_at"].replace("Z", "+00:00"))
        remaining = int(plan["body"]["budget"]["wall_seconds"] - (datetime.now(timezone.utc) - started).total_seconds())
        wall = min(remaining, plan["body"]["budget"]["scientific_wall_seconds"])
        if wall < 1:
            self.workflow.fail_scenario(actor, run_id, scenario_id, "budget_exhausted")
            raise DomainError("budget_exhausted", "No scientific wall budget remains.")
        task = asyncio.create_task(asyncio.to_thread(
            run_bounded, self.adapter, "investigate", (problem, dataset, plan["body"]["budget"]),
            wall_seconds=wall, cancelled=lambda: stop.is_set() or self._cancelled(actor, run_id),
            result_cap=2 * 1024 * 1024))
        try:
            result = await asyncio.shield(task)
            if "worker_error" in result:
                raise DomainError(result["worker_error"], "The scientific worker stopped without a completed result.")
            result = ScientificResult.model_validate(result).model_dump(mode="json")
            if result["problem_id"] != problem["id"] or result.get("problem_digest") not in {None, problem["digest"]}:
                raise DomainError("binding_mismatch", "Adapter output does not bind the reserved problem.")
            if result["verification"] == "valid" and not self.adapter.capabilities().get("verified_in_environment"):
                raise DomainError("adapter_not_qualified", "This adapter is not qualified to emit checked evidence.")
            evidence = self.workflow.complete_scenario(actor, run_id, scenario_id, result)
            return self._fact(evidence)
        except asyncio.CancelledError:
            stop.set()
            await task  # Wait for owned child termination before acknowledging cancellation.
            self.workflow.fail_scenario(actor, run_id, scenario_id, "cancelled")
            raise
        except BaseException:
            self.workflow.fail_scenario(actor, run_id, scenario_id, "scientific_attempt_failed")
            raise

    async def execute(self, queued: dict) -> dict:
        actor, job_id = queued["actor_id"], queued["id"]
        job = self.workflow.mark_running(actor, job_id, self.id)
        plan = self.workflow.get(actor, job["plan_id"])
        try:
            if job["kind"] == "design_job":
                return await self._design(actor, job, plan)
            if plan["body"]["provider_disclosure"]["provider"] == "none":
                baseline = plan["body"]["scenarios"][0]
                evidence = await self._scenario(actor, job_id, baseline["id"])
                for scenario in plan["body"]["scenarios"][1:]:
                    self.workflow.skip_scenario(actor, job_id, scenario["id"], "budget_preserved")
                return self.workflow.finish_run(actor, job_id, result={"execution_lane": "manual",
                    "evidence_ids": [evidence["id"]], "scientific_outcome": evidence["scientific_outcome"],
                    "message": "Consult the typed evidence. Completion does not establish a scientific proposition."})
            return await self._agent(actor, job, plan)
        except BaseException as exc:
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            current = self.workflow.get_run(actor, job_id) if job["kind"] == "run" else self.workflow.get_design_job(actor, job_id)
            for child in current["scenarios"]:
                if child["state"] in {"reserved", "running"}:
                    self.workflow.fail_scenario(actor, job_id, child["scenario_id"], "worker_stopped")
            state = "cancelled" if current["state"] == "cancel_requested" else "failed"
            code = getattr(exc, "code", "worker_failed")
            return self.workflow.finish_run(actor, job_id, state=state, error_code=code)

    async def _agent(self, actor, job, plan):
        disclosure = plan["body"]["provider_disclosure"]
        if not self.config or self.config.model != disclosure["model"]:
            raise ProviderFailure("approved_provider_unavailable")
        self.config.check_ready()
        permission = self.workflow.get(actor, disclosure["permission_id"], "provider_consent")
        if permission["workspace_id"] != job["workspace_id"] or permission["body"].get("problem_id") != plan["body"]["problem_id"]:
            raise DomainError("provider_consent_mismatch", "Provider disclosure needs matching durable consent.", 403)
        allowed_context = set(disclosure["context_fields"])
        if not {"problem", "dataset"}.issubset(allowed_context):
            raise DomainError("provider_context_not_disclosed", "Disclose problem and dataset before an agent invocation.", 403)
        operation = self.workflow.begin_operation(actor, job["workspace_id"], "coordinator", job["id"], {"plan_id": plan["id"], "plan_digest": plan["digest"]})
        if not operation["created_new"]:
            raise DomainError("operation_pending", "A provider invocation cannot be silently restarted.")
        problem = self.workflow.get(actor, plan["body"]["problem_id"], "problem")
        dataset = self.workflow.get(actor, problem["body"]["dataset_id"], "dataset")
        budget = plan["body"]["budget"]
        scope = CoordinatorScope(run_id=job["id"], plan_id=plan["id"], problem_id=problem["id"],
            baseline_scenario_id=plan["body"]["scenarios"][0]["id"],
            optional_scenario_ids=tuple(s["id"] for s in plan["body"]["scenarios"][1:]),
            scenario_problem_ids={s["id"]: s["problem_id"] for s in plan["body"]["scenarios"]},
            permitted_tools=tuple(plan["body"]["permitted_tools"]),
            context={"problem": problem["body"], "dataset": dataset["body"]},
            max_model_turns=budget["provider_turns"], max_tool_calls=budget["tool_calls"],
            max_scientific_reservations=budget["scientific_reservations"], wall_seconds=budget["wall_seconds"])

        def event(item):
            if item["type"] == "model_request":
                self.workflow.consume_budget(actor, job["id"], "provider_turns")
            if item["type"] == "tool_attempt":
                for _ in range(item.get("count", 1)):
                    self.workflow.consume_budget(actor, job["id"], "tool_calls")
            if item["type"] == "tool_request":
                if item["tool"] not in plan["body"]["permitted_tools"]:
                    raise DomainError("tool_not_approved", "The model requested a tool outside this plan.", 403)
            return self.workflow.create_record(actor, job["workspace_id"], "agent_event",
                {"run_id": job["id"], **item}, f"{job['id']}:{item['sequence']}", operation="agent-event")

        callbacks = ScopedCallbacks(check_authority=lambda: self.workflow.check_run_scope(actor, job["id"]),
            execute_scenario=lambda scenario_id: self._scenario(actor, job["id"], scenario_id),
            read_evidence=lambda evidence_id: self._fact(self.workflow.read_evidence(actor, job["id"], evidence_id)),
            record_skip=lambda scenario_id, reason: self.workflow.skip_scenario(actor, job["id"], scenario_id, reason),
            record_event=event)
        context = AttemptContext(actor, job["workspace_id"], operation["id"], permission["id"])
        result = await run_coordinator(self.config, self.ledger, context, scope, callbacks)
        summary = asdict(result)
        self.workflow.finish_operation(actor, job["workspace_id"], "coordinator", job["id"], summary)
        current = self.workflow.get_run(actor, job["id"])
        final_state = "cancelled" if current["state"] == "cancel_requested" else "completed" if result.status == "completed" else "failed"
        return self.workflow.finish_run(actor, job["id"], state=final_state,
                                        result=summary, error_code=result.error_code)

    async def _design(self, actor, job, plan):
        self.workflow.check_run_scope(actor, job["id"])
        if "execute_approved_design" not in plan["body"]["permitted_tools"]:
            raise DomainError("tool_not_approved", "Design execution was not in the approved plan.", 403)
        if plan["body"]["provider_disclosure"]["provider"] != "none":
            raise DomainError("design_provider_unavailable", "This worker only admits deterministic design adapter execution.")
        request = plan["body"]["request"]
        run = self.workflow.get_run(actor, request["historical_run_id"])
        child = next(s for s in run["scenarios"] if s["scenario_id"] == request["scenario_id"])
        evidence = self.workflow.get(actor, child["result_id"], "evidence")
        if evidence["body"]["run_id"] != run["id"] or evidence["body"]["scenario_id"] != request["scenario_id"]:
            raise DomainError("binding_mismatch", "Historical evidence must belong to the selected scenario.")
        started = datetime.fromisoformat(job["started_at"].replace("Z", "+00:00"))
        remaining = int(request["budget"]["wall_seconds"] - (datetime.now(timezone.utc) - started).total_seconds())
        if remaining < 1:
            raise DomainError("budget_exhausted", "No design wall budget remains.")
        stop = threading.Event()
        task = asyncio.create_task(asyncio.to_thread(run_bounded, self.adapter, "design", (request, evidence["body"]),
            wall_seconds=remaining, result_cap=request["budget"]["bundle_bytes"],
            cancelled=lambda: stop.is_set() or self.workflow.get_design_job(actor, job["id"])["state"] == "cancel_requested"))
        try:
            result = await asyncio.shield(task)
        except asyncio.CancelledError:
            stop.set()
            await task
            raise
        if "worker_error" in result:
            raise DomainError(result["worker_error"], "The design worker stopped without completed evidence.")
        result = DesignResult.model_validate(result).model_dump(mode="json")
        if [option["time"] for option in result["options"]] != request["feasible_times"]:
            raise DomainError("design_grid_mismatch", "The result must preserve every approved time in order.")
        if result["design_tier"] == "checked_pair_separation" and not self.adapter.capabilities().get("verified_in_environment"):
            raise DomainError("adapter_not_qualified", "Checked design requires a qualified adapter and replay.")
        if result["design_tier"] == "checked_pair_separation":
            if (result["candidate_ids"] != request["candidate_ids"] or
                result["future_hard_allowance"] != request["future_hard_allowance"] or
                result["verification_record"]["expected_problem_digest"] != request["problem_digest"]):
                raise DomainError("binding_mismatch", "Checked design must bind the exact pair, allowance and historical problem.")
        return self.workflow.finish_run(actor, job["id"], result=result)

    def tick(self) -> int:
        # A queued cancellation has no child to terminate; acknowledge it durably.
        with self.workflow.store.read() as conn:
            cancelled = [dict(r) for r in conn.execute("SELECT * FROM jobs WHERE state='cancel_requested' AND started_at IS NULL")]
        for job in cancelled:
            self.workflow.finish_run(job["actor_id"], job["id"], state="cancelled")
        jobs = self.workflow.queued_jobs(limit=1)
        for job in jobs:
            asyncio.run(self.execute(job))
        return len(jobs) + len(cancelled)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="Handle one queued job and exit")
    parser.add_argument("--recover", action="store_true", help="After stopping the API and old worker, mark interrupted work; do not rerun it")
    args = parser.parse_args()
    settings = Settings.from_env()
    store = Store(settings.database_path)
    lock_path = Path(store.path + ".worker.lock")
    with lock_path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("A worker already owns this SQLite lane.") from None
        workflow = Workflow(store)
        if args.recover:
            print(json.dumps(workflow.recover_interrupted(), sort_keys=True))
            return
        from .main import provider_config_from_env
        worker = Worker(workflow, provider_config=provider_config_from_env())
        while True:
            worker.tick()
            if args.once:
                break
            time.sleep(0.5)


if __name__ == "__main__":
    main()
