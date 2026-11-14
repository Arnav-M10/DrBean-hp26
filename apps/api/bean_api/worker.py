"""Durable single-worker dispatcher. Running work is never silently replayed."""

from __future__ import annotations

import argparse
import asyncio
import base64
from dataclasses import asdict
from datetime import datetime, timezone
import fcntl
import hashlib
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
from .science import run_bounded
from .artifacts import ArtifactService
from .controlled_ledger import ControlledLedger
from .store import Store
from .workflow import DomainError, Workflow


class Worker:
    def __init__(self, workflow: Workflow, *, adapter=None, provider_config=None, ledger=None, controlled_model=None, settings=None):
        self.workflow = workflow
        self.settings = settings or Settings.from_env()
        from .counterdex_adapter import create_science_adapter
        self.adapter = adapter or create_science_adapter(self.settings.counterdex_python, self.settings.science_adapter)
        self.config = provider_config
        self.ledger = ledger or ProviderLedger(workflow.store, request_cap=8 if getattr(provider_config, "mode", None) == "live" else 32)
        self.id = "worker_" + uuid.uuid4().hex
        self.controlled_model = controlled_model
        self.artifacts = ArtifactService(workflow, self.settings.artifact_dir)
        from .research_runtime import ResearchRunner
        self.research = ResearchRunner(workflow, self.settings, self.id, provider_config=provider_config, ledger=self.ledger)

    def _publish_native(self, actor, job, result, *, problem, dataset, aggregate_limit,
                        application_projection=None, scenario_id=None, design_context=None, followup_context=None):
        packets = result.pop("_native_artifacts", [])
        if not packets:
            if result.get("scientific_problem_digest") and result.get("artifacts"):
                raise DomainError("incomplete_export", "Scientific references require the matching native bytes.")
            return result
        from .canonical import semantic_digest
        from .scientific_projection import PROJECTION_VERSION, project_problem
        from .baseline_evidence import MAPPING_POLICY, expected_baseline_anchor, validate_baseline_packet
        application_native = result.get("projection_version") == MAPPING_POLICY
        native_design = application_native and "design_tier" in result
        if application_native:
            from .counterdex_adapter import CounterdexAdapter
            if type(self.adapter) is not CounterdexAdapter or scenario_id is None or len(packets) != 1:
                raise DomainError("binding_mismatch", "Native publication needs the reserved scientific scope.")
            if native_design:
                from .design_evidence import expected_design_anchor
                if design_context is None or job["kind"] != "design_job":
                    raise DomainError("binding_mismatch", "Native design needs its independently retained approved context.")
                expected_anchor = expected_design_anchor(application_projection, problem=problem, dataset=dataset,
                    job=job, request=design_context["request"], request_digest=design_context["request_digest"],
                    scientific_design_digest=result.get("scientific_design_digest"))
            else:
                expected_anchor = expected_baseline_anchor(application_projection, problem=problem, dataset=dataset,
                                                           job=job, scenario_id=scenario_id)
            scientific_digest = expected_anchor["projection_digest"]
        else:
            scientific_digest = semantic_digest("problem", project_problem(problem, dataset))
            expected_anchor = {"projection_version": PROJECTION_VERSION,
                "application_problem_id": problem["id"], "application_problem_digest": problem["digest"],
                "application_dataset_id": dataset["id"], "application_dataset_digest": dataset["digest"],
                "scientific_problem_digest": scientific_digest}
        if result.get("scientific_problem_digest") != scientific_digest:
            raise DomainError("binding_mismatch", "Native export must bind the frozen scientific projection.")
        if not application_native:
            for field in ("scientific_design_digest", "native_suggestion_digest"):
                if result.get(field):
                    expected_anchor[field] = result[field]
        references = result.get("artifacts", [])
        by_id = {reference["id"]: reference for reference in references}
        packet_ids = [packet.get("id") for packet in packets]
        if (len(by_id) != len(references) or len(set(packet_ids)) != len(packet_ids)
                or set(packet_ids) != set(by_id)):
            raise DomainError("artifact_mismatch", "Native packets and public references must match one to one.")
        items = []
        for packet in packets:
            try:
                content = base64.b64decode(packet["content_base64"], validate=True)
            except (KeyError, ValueError):
                raise DomainError("invalid_native_artifact", "Scientific output has invalid native bytes.") from None
            reference = by_id[packet["id"]]
            if (hashlib.sha256(content).hexdigest() != reference["sha256"]
                    or len(content) != reference["byte_size"]
                    or packet.get("media_type") != reference["media_type"]):
                raise DomainError("artifact_mismatch", "Native bytes do not match their public reference.")
            anchor = packet.get("anchor", {})
            if any(anchor.get(field) != value for field, value in expected_anchor.items()):
                raise DomainError("binding_mismatch", "Native anchors must match the frozen application and scientific identities.")
            item = {"content": content, "media_type": packet["media_type"],
                    "artifact_kind": packet["artifact_kind"], "anchor": anchor}
            if application_native:
                if anchor != {**expected_anchor, "artifact_sha256": reference["sha256"]}:
                    raise DomainError("binding_mismatch", "The native replay anchor must exactly identify these retained bytes.")
                if native_design:
                    from .design_evidence import validate_design_packet
                    validate_design_packet(content, anchor, projection=application_projection, job=job,
                                           result=result, **design_context)
                elif followup_context is not None:
                    from .followup_evidence import validate_followup_packet
                    validate_followup_packet(content, anchor, projection=application_projection, job=job,
                        scenario_id=scenario_id, result=result, **followup_context)
                else:
                    validate_baseline_packet(content, anchor, projection=application_projection, job=job,
                                             scenario_id=scenario_id, result=result)
                item["origin"] = {"run_id": job["id"], "scenario_id": scenario_id,
                                  "plan_id": job["plan_id"], "approval_id": job["approval_id"]}
            items.append(item)
        verification = result.get("verification_record")
        if verification and (verification["artifact_id"] not in by_id
                or verification["artifact_sha256"] != by_id[verification["artifact_id"]]["sha256"]
                or verification["expected_problem_digest"] != problem["digest"]
                or verification.get("expected_scientific_problem_digest") != scientific_digest):
            raise DomainError("binding_mismatch", "Verification must bind the frozen problem and retained native bytes.")
        if any(identity not in by_id for candidate in result.get("candidates", []) for identity in candidate.get("artifact_ids", [])):
            raise DomainError("incomplete_export", "Candidate references require included native bytes.")
        # Distinct attempts/scenarios in one job can share a problem but emit
        # different evidence. Key publication by its exact complete packet set.
        publication_digest = hashlib.sha256(json.dumps(items, default=lambda value: hashlib.sha256(value).hexdigest(),
            sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        records = self.artifacts.publish_many(actor, job["workspace_id"], items,
            key=job["id"] + ":" + publication_digest, aggregate_limit=aggregate_limit)
        replacements = {packet["id"]: record["id"] for packet, record in zip(packets, records, strict=True)}
        for artifact in result.get("artifacts", []):
            artifact["id"] = replacements.get(artifact["id"], artifact["id"])
        if result.get("verification_record"):
            record = result["verification_record"]
            record["artifact_id"] = replacements.get(record["artifact_id"], record["artifact_id"])
        for candidate in result.get("candidates", []):
            candidate["artifact_ids"] = [replacements.get(i, i) for i in candidate.get("artifact_ids", [])]
        return result

    def _checked_result_allowed(self, result):
        # A global package-presence flag is not qualification. The bridge must have
        # freshly replayed this exact result, with independently supplied anchors.
        # Do not launch another runtime probe outside the supervised job budget.
        from .counterdex_adapter import CounterdexAdapter
        if type(self.adapter) is not CounterdexAdapter:
            return False
        from .baseline_evidence import MAPPING_POLICY, baseline_result_checked
        if result.get("projection_version") == MAPPING_POLICY:
            if "design_tier" in result:
                from .design_evidence import design_result_checked
                return design_result_checked(result)
            if (result.get("native_replay") or {}).get("operation") in {"review", "recheck"}:
                from .followup_evidence import followup_result_checked
                return followup_result_checked(result)
            return baseline_result_checked(result)
        replay = result.get("native_replay") or {}
        record = result.get("verification_record") or {}
        fresh = replay.get("fresh_checked") or {}
        suggestion_digest = result.get("native_suggestion_digest")
        problem_digest = result.get("scientific_problem_digest")
        if not (
            result.get("verification") == "valid" and result.get("replay") == "passed"
            and replay.get("replay") == "passed" and replay.get("integrity") == "passed"
            and replay.get("verification") == "valid" and replay.get("expected_binding") == "matches"
            and replay.get("recorded_result_matches") is True
            and suggestion_digest and replay.get("suggestion_digest") == suggestion_digest
            and record.get("verification") == "valid" and record.get("expected_binding") == "matches"
            and problem_digest and record.get("expected_scientific_problem_digest") == problem_digest
            and record.get("observed_scientific_problem_digest") == problem_digest
            and fresh.get("verification") == "valid" and fresh.get("expected_binding") == "matches"
            and fresh.get("candidate_results") == result.get("candidate_results")
        ):
            return False
        if "design_tier" in result:
            if (fresh.get("tier") != result["design_tier"]
                    or fresh.get("selected_time") != result.get("selected_time")):
                return False
            rows = {row["time"]: row for row in fresh.get("rows", [])}
            options = result.get("options", [])
            if len(rows) != len(options) or any(
                option["time"] not in rows
                or option["state"] != rows[option["time"]]["status"]
                or option.get("exact_margin") != rows[option["time"]].get("margin")
                for option in options
            ):
                return False
        return True

    def _cancelled(self, actor, job_id):
        return self.workflow.get(actor, job_id, "run")["state"] == "cancel_requested"

    def _fact(self, evidence):
        return {"id": evidence["id"], **evidence["body"]["result"]}

    def _followup_history(self, actor, job, plan):
        """Load the exact selected design; never reconstruct it from display facts."""
        context = self.workflow.followup_context(actor, plan["body"])
        artifact_id = plan["body"]["followup"]["source_artifact_id"]
        record, content = self.artifacts.read(actor, artifact_id)
        if record["workspace_id"] != job["workspace_id"]:
            raise DomainError("not_found", "Artifact was not found.", 404)
        result = context["design_result"]["body"]
        reference = next((r for r in result["artifacts"] if r["id"] == artifact_id), None)
        if reference is None or any(record["body"][key] != reference[key]
                                    for key in ("sha256", "byte_size", "media_type")):
            raise DomainError("artifact_binding_mismatch", "Follow-up must retain the original design artifact.")
        request = context["design_plan"]["body"]["request"]
        expected = {"artifact_sha256": reference["sha256"],
            "dataset_digest": context["dataset"]["digest"], "problem_digest": context["problem"]["digest"],
            "projection_digest": result["scientific_problem_digest"],
            "app_request_digest": context["design_plan"]["body"]["request_digest"],
            "design_digest": result["scientific_design_digest"],
            "run_id": context["design_job"]["id"], "scenario_id": request["scenario_id"]}
        if record["body"].get("anchor") != expected:
            raise DomainError("binding_mismatch", "Retained design anchors must match the reviewed follow-up history.")
        return {"historical_artifact": {"id": artifact_id, "sha256": reference["sha256"],
            "bytes_base64": base64.b64encode(content).decode("ascii"), "anchors": expected},
            "design_request": request,
            "observation_proposal": {key: context["observation_proposal"][key] for key in ("id", "digest", "body")}}

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
        from .counterdex_adapter import CounterdexAdapter
        args = (problem, dataset, {**plan["body"]["budget"], "scientific_wall_seconds": wall})
        operation = "investigate"
        followup_context = None
        if type(self.adapter) is CounterdexAdapter:
            execution = {"run_id": run_id, "scenario_id": scenario_id, "workflow": {
                "plan_id": plan["id"], "approval_id": job["approval_id"],
                "operation_id": run_id, "execution_id": run_id}}
            if plan["body"].get("followup"):
                followup_context = self._followup_history(actor, job, plan)
                execution.update(followup_context)
                operation = "recheck"
            args += (execution,)
        elif plan["body"].get("followup"):
            raise DomainError("followup_unavailable", "Fixed-pair review requires the qualified native adapter.")
        task = asyncio.create_task(asyncio.to_thread(
            run_bounded, self.adapter, operation, args,
            wall_seconds=wall, cancelled=lambda: stop.is_set() or self._cancelled(actor, run_id),
            result_cap=12 * 1024 * 1024))
        try:
            result = await asyncio.shield(task)
            if "worker_error" in result:
                raise DomainError(result["worker_error"], "The scientific worker stopped without a completed result.")
            native = result.pop("_native_artifacts", [])
            application_projection = result.pop("_application_projection", None)
            result = ScientificResult.model_validate(result).model_dump(mode="json")
            if result["problem_id"] != problem["id"] or result.get("problem_digest") not in {None, problem["digest"]}:
                raise DomainError("binding_mismatch", "Adapter output does not bind the reserved problem.")
            if result["verification"] == "valid" and not self._checked_result_allowed(result):
                raise DomainError("adapter_not_qualified", "This adapter is not qualified to emit checked evidence.")
            if followup_context is not None:
                self.workflow.check_run_scope(actor, run_id)
                if result.get("projection_version") != "DB-SC-1-to-groundwork-v1":
                    raise DomainError("binding_mismatch", "Follow-up cannot fall back to another scientific mapping.")
            result["_native_artifacts"] = native
            result = self._publish_native(actor, job, result, problem=problem, dataset=dataset,
                                          aggregate_limit=4 * 1024 * 1024,
                                          application_projection=application_projection, scenario_id=scenario_id,
                                          followup_context=followup_context)
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
        if self.controlled_model is None or type(self.controlled_model).__module__.startswith(("langchain_google_genai", "langchain_openai", "langchain_anthropic")):
            raise ProviderFailure("provider_dispatch_disabled")
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
            context={"problem": problem["body"], "dataset": dataset["body"],
                     "objective": plan["body"].get("objective"), "scenarios": plan["body"]["scenarios"]},
            question=(plan["body"].get("objective") or {}).get("question", "Explain the evidence and a permitted next step."),
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

        from .agent_evidence import project_evidence_fact

        async def execute_agent_scenario(scenario_id):
            fact = await self._scenario(actor, job["id"], scenario_id)
            record = self.workflow.get(actor, fact["id"], "evidence")
            return project_evidence_fact(record)

        callbacks = ScopedCallbacks(check_authority=lambda: self.workflow.check_run_scope(actor, job["id"]),
            execute_scenario=execute_agent_scenario,
            read_evidence=lambda evidence_id: project_evidence_fact(self.workflow.read_evidence(actor, job["id"], evidence_id)),
            record_skip=lambda scenario_id, reason: self.workflow.skip_scenario(actor, job["id"], scenario_id, reason),
            record_event=event)
        context = AttemptContext(actor, job["workspace_id"], operation["id"], permission["id"])
        result = await run_coordinator(self.config, ControlledLedger(self.workflow), context, scope, callbacks, chat_model=self.controlled_model)
        summary = asdict(result)
        summary.update(execution_lane="controlled_placeholder", external_provider_calls=0, actual_model_tokens=0)
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
        problem = self.workflow.get(actor, request["problem_id"], "problem")
        dataset = self.workflow.get(actor, problem["body"]["dataset_id"], "dataset")
        native_artifacts = []
        historical_artifact = None
        native_design = evidence["body"]["result"].get("projection_version") == "DB-SC-1-to-groundwork-v1"
        historical_refs = {item["id"]: item for item in evidence["body"]["result"].get("artifacts", [])}
        if native_design:
            if request.get("source_artifact_ids"):
                raise DomainError("unsupported_artifact_reuse", "Prospective reuse must be separately admitted; baseline lineage is resolved from the selected evidence.")
            if len(historical_refs) != 1:
                raise DomainError("historical_artifact_required", "Native design requires one original baseline evidence artifact.")
        artifact_ids = list(historical_refs) if native_design else request.get("source_artifact_ids", [])
        for artifact_id in artifact_ids:
            record, content = self.artifacts.read(actor, artifact_id)
            if record["workspace_id"] != job["workspace_id"]:
                raise DomainError("not_found", "Artifact was not found.", 404)
            if native_design:
                reference = historical_refs[artifact_id]
                if any(record["body"][key] != reference[key] for key in ("sha256", "byte_size", "media_type")):
                    raise DomainError("artifact_binding_mismatch", "Retained baseline differs from the approved historical reference.")
                anchor = record["body"]["anchor"]
                if (anchor.get("run_id") != run["id"] or anchor.get("scenario_id") != request["scenario_id"]
                        or anchor.get("problem_digest") != problem["digest"] or anchor.get("dataset_digest") != dataset["digest"]
                        or anchor.get("projection_digest") != evidence["body"]["result"]["scientific_problem_digest"]
                        or anchor.get("artifact_sha256") != reference["sha256"]):
                    raise DomainError("binding_mismatch", "Stored baseline anchors differ from the selected historical scope.")
                historical_artifact = {"id": artifact_id, "sha256": record["body"]["sha256"],
                    "bytes_base64": base64.b64encode(content).decode("ascii"), "anchors": anchor}
            native_artifacts.append({"id": artifact_id, "sha256": record["body"]["sha256"], "content_base64": base64.b64encode(content).decode()})
        history = {"problem": problem, "dataset": dataset, "evidence": evidence,
                   "workflow": {"plan_id": plan["id"], "approval_id": job["approval_id"], "operation_id": job["id"], "execution_id": job["id"]},
                   "native_artifacts": native_artifacts}
        if native_design:
            history.update(run_id=job["id"], expected_request_digest=plan["body"]["request_digest"],
                           historical_artifact=historical_artifact, remaining_wall_seconds=remaining)
        task = asyncio.create_task(asyncio.to_thread(run_bounded, self.adapter, "design", (request, history),
            wall_seconds=remaining, result_cap=12 * 1024 * 1024,
            cancelled=lambda: stop.is_set() or self.workflow.get_design_job(actor, job["id"])["state"] == "cancel_requested"))
        try:
            result = await asyncio.shield(task)
        except asyncio.CancelledError:
            stop.set()
            await task
            raise
        if "worker_error" in result:
            raise DomainError(result["worker_error"], "The design worker stopped without completed evidence.")
        native = result.pop("_native_artifacts", [])
        application_projection = result.pop("_application_projection", None)
        result = DesignResult.model_validate(result).model_dump(mode="json")
        if native_design and result.get("projection_version") != "DB-SC-1-to-groundwork-v1":
            raise DomainError("binding_mismatch", "Native design cannot fall back to a different historical mapping.")
        if [option["time"] for option in result["options"]] != request["feasible_times"]:
            raise DomainError("design_grid_mismatch", "The result must preserve every approved time in order.")
        if result["verification"] == "valid" and not self._checked_result_allowed(result):
            raise DomainError("adapter_not_qualified", "Checked design requires a qualified adapter and replay.")
        if result["verification"] == "valid":
            if (result["candidate_ids"] != request["candidate_ids"] or
                result["future_hard_allowance"] != request["future_hard_allowance"] or
                result["verification_record"]["expected_problem_digest"] != request["problem_digest"]):
                raise DomainError("binding_mismatch", "Checked design must bind the exact pair, allowance and historical problem.")
        result["_native_artifacts"] = native
        design_context = {"request": request, "request_digest": plan["body"]["request_digest"],
            "historical_evidence": evidence["body"], "historical_artifact": historical_artifact} if native_design else None
        if native_design:
            # Publication is still part of the approved operation. A completed
            # child cannot restart an expired deadline or revoked job scope.
            self.workflow.check_run_scope(actor, job["id"])
        result = self._publish_native(actor, job, result, problem=problem, dataset=dataset,
                                      aggregate_limit=request["budget"]["bundle_bytes"],
                                      application_projection=application_projection, scenario_id=request["scenario_id"],
                                      design_context=design_context)
        return self.workflow.finish_run(actor, job["id"], result=result)

    def tick(self) -> int:
        from .runtime_status import write_status
        write_status(self.workflow.store.path, self.id, self.adapter)
        research_actions = self.research.tick()
        # A queued cancellation has no child to terminate; acknowledge it durably.
        with self.workflow.store.read() as conn:
            cancelled = [dict(r) for r in conn.execute("SELECT * FROM jobs WHERE state='cancel_requested' AND started_at IS NULL")]
        for job in cancelled:
            self.workflow.finish_run(job["actor_id"], job["id"], state="cancelled")
        jobs = self.workflow.queued_jobs(limit=1)
        for job in jobs:
            asyncio.run(self.execute(job))
        return len(jobs) + len(cancelled) + research_actions


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
            from .research import ResearchService
            print(json.dumps({**workflow.recover_interrupted(), **ResearchService(workflow).recover(force=True)}, sort_keys=True))
            return
        from .main import provider_config_from_env
        worker = Worker(workflow, provider_config=provider_config_from_env(), settings=settings)
        while True:
            worker.tick()
            if args.once:
                break
            time.sleep(0.5)


if __name__ == "__main__":
    main()
