"""Supervised prepared Counterdex runtime, with separate application/native identities."""
from __future__ import annotations

import base64
from dataclasses import dataclass
from fractions import Fraction
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from .canonical import semantic_digest
from .scientific_projection import (PROJECTION_VERSION, native_design_mapping_policy,
                                    project_design, project_native_design, project_problem)
from .workflow import DomainError

APPLICATION_MAPPING = "DB-SC-1-to-groundwork-v1"
NATIVE_PROTOCOL = "counterdex.bridge.v1"
NATIVE_MEDIA_TYPE = "application/vnd.counterdex.native+json"
TRANSPORT_CAP = 12 * 1024 * 1024


@dataclass
class CounterdexAdapter:
    python_executable: str = "python3.11"

    def _run(self, payload: dict, wall_seconds: int) -> dict:
        executable = shutil.which(self.python_executable)
        if executable is None:
            return {"worker_error": "scientific_runtime_missing"}
        raw = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
        if len(raw) > TRANSPORT_CAP:
            return {"worker_error": "scientific_bridge_input_limit"}
        try:
            # Inherit the owning scientific process group/resource limits. The outer
            # supervisor kills/reaps that complete group on expiry or cancellation.
            result = subprocess.run([executable, "-I", str(Path(__file__).with_name("counterdex_child.py"))],
                input=raw, capture_output=True, timeout=wall_seconds, check=False,
                env={"PATH": os.defpath, "LANG": "C.UTF-8"})
        except subprocess.TimeoutExpired:
            return {"worker_error": "scientific_wall_limit"}
        except OSError:
            return {"worker_error": "scientific_runtime_unavailable"}
        if result.returncode or len(result.stdout) > TRANSPORT_CAP:
            return {"worker_error": "scientific_bridge_failed"}
        try:
            response = json.loads(result.stdout)
        except (ValueError, UnicodeError):
            return {"worker_error": "scientific_bridge_failed"}
        if not isinstance(response, dict):
            return {"worker_error": "scientific_bridge_failed"}
        if "engine_error" in response:
            return {"worker_error": response["engine_error"]["code"], "engine_error": response["engine_error"]}
        if response.get("ok") is False and "error" in response:
            return {"worker_error": response["error"]["code"], "engine_error": response["error"]}
        return response

    def capabilities(self) -> dict:
        probe = self._run({"operation": "probe"}, 5)
        available = "worker_error" not in probe
        recheck = available and probe.get("capabilities", {}).get("capabilities", {}).get(
            "observation_revision_recheck", {}).get("supported") is True
        native_design = available and probe.get("capabilities", {}).get("scientific_profiles", {}).get(
            "explicit_design_mapping") == "DB-SC-1-design-to-groundwork-v2"
        return {"implemented": True, "configured": bool(self.python_executable), "available": available,
                "verified_in_environment": False, "adapter": "Counterdex",
                "adapter_version": (probe.get("identity") or {}).get("adapter_version"),
                "projection_version": APPLICATION_MAPPING, "runtime": probe.get("identity"),
                "reason": probe.get("worker_error"),
                "baseline_discovery": available and probe.get("baseline_discovery") is True,
                "native_design": native_design,
                "native_followup": {"available": recheck, "operation": "recheck",
                    "hypothetical_only": False, "selected_time_and_allowance_only": False,
                    "requires_checked_separation": False, "requires_fresh_checked_design": True},
                "native_recheck": recheck,
                "native_design_requested_tiers": ["numerical_guidance", "checked_pair_separation"] if native_design else [],
                "claim_families": ["closed_ke_interval_counterexample"] if available else [],
                "design_tiers": ["numerical_guidance", "checked_pair_separation", "no_separation_established"] if available else [],
                "native_replay": available, "browser_replay": False,
                "qualification": "Runtime availability; each result requires actual checking and fresh native replay."}

    @staticmethod
    def _projection(response: dict, problem: dict, dataset: dict) -> dict:
        projection = response.get("result", {})
        binding = projection.get("binding", {})
        if (response.get("protocol") != NATIVE_PROTOCOL or response.get("ok") is not True
                or binding.get("mapping_policy") != APPLICATION_MAPPING
                or binding.get("problem") != {key: problem[key] for key in ("id", "digest", "body")}
                or binding.get("dataset") != {key: dataset[key] for key in ("id", "digest", "body")}
                or semantic_digest("problem", projection.get("problem")) != projection.get("projection_digest")
                or binding.get("projection_digest") != projection.get("projection_digest")):
            raise DomainError("scientific_projection_mismatch", "Scientific admission must bind the complete frozen application inputs.", 422)
        return projection

    def admission_projection(self, problem: dict, dataset: dict) -> dict:
        response = self._run({"protocol": NATIVE_PROTOCOL, "operation": "admission", "problem": problem, "dataset": dataset}, 5)
        if "worker_error" in response:
            code = response["worker_error"]
            infrastructure = code.startswith("scientific_") or code in {"unsupported_runtime", "bridge_failure"}
            detail = response.get("engine_error", {})
            raise DomainError(code if infrastructure else "scientific_admission",
                detail.get("message", "The prepared scientific runtime is unavailable."),
                503 if infrastructure else 422, detail.get("field_paths", []))
        return self._projection(response, problem, dataset)

    def admit(self, problem: dict, dataset: dict) -> None:
        self.admission_projection(problem, dataset)

    def investigate(self, problem: dict, dataset: dict, limits: dict, scope: dict | None = None) -> dict:
        # Admission derives the expected projection from reviewed inputs before
        # looking at any result or packet asserted by the producer.
        admitted = self._run({"protocol": NATIVE_PROTOCOL, "operation": "admission",
                              "problem": problem, "dataset": dataset}, min(5, limits["scientific_wall_seconds"]))
        if "worker_error" in admitted:
            return admitted
        projection = self._projection(admitted, problem, dataset)
        if scope is None:
            return {"worker_error": "scientific_scope_required"}
        response = self._run({"protocol": NATIVE_PROTOCOL, "operation": "investigate",
            "problem": problem, "dataset": dataset, "run_id": scope["run_id"], "scenario_id": scope["scenario_id"],
            "workflow": scope["workflow"], "limits": {"wall_seconds": limits["scientific_wall_seconds"],
                "max_bundle_bytes": 4 * 1024 * 1024}, "search_settings": None}, limits["scientific_wall_seconds"])
        if "worker_error" in response:
            return response
        return self._baseline_output(response, problem, dataset, projection, scope)

    @staticmethod
    def _baseline_output(response: dict, problem: dict, dataset: dict, projection: dict, scope: dict) -> dict:
        if (response.get("protocol") != NATIVE_PROTOCOL or response.get("ok") is not True
                or len(response.get("native_artifacts", [])) != 1):
            return {"worker_error": "incomplete_export"}
        artifact = response["native_artifacts"][0]
        try:
            content = base64.b64decode(artifact["bytes_base64"], validate=True)
            packet = json.loads(content)
            native = base64.b64decode(packet["scientific"]["bytes_base64"], validate=True)
            scientific = json.loads(native)
        except (KeyError, TypeError, ValueError):
            return {"worker_error": "invalid_native_artifact"}
        if (not content or len(content) > 4 * 1024 * 1024 or len(content) != artifact["byte_size"]
                or hashlib.sha256(content).hexdigest() != artifact["sha256"]
                or artifact["media_type"] != NATIVE_MEDIA_TYPE
                or hashlib.sha256(native).hexdigest() != packet["scientific"]["sha256"]):
            return {"worker_error": "artifact_mismatch"}
        expected = {"artifact_sha256": artifact["sha256"], "dataset_digest": dataset["digest"],
            "problem_digest": problem["digest"], "projection_digest": projection["projection_digest"],
            "app_request_digest": None, "design_digest": None, "scenario_id": scope["scenario_id"], "run_id": scope["run_id"]}
        if (response.get("anchors") != expected or packet.get("schema_version") != "counterdex.application-bundle.v1"
                or packet.get("operation") != "investigate" or packet.get("history") is not None
                or packet.get("binding") != projection["binding"] or packet.get("run_id") != scope["run_id"]
                or packet.get("scenario_id") != scope["scenario_id"] or scientific.get("problem") != projection["problem"]
                or scientific.get("operation") != "bounded_discovery" or scientific.get("workflow") != scope["workflow"]
                or scientific.get("scenario_id") != scope["scenario_id"]):
            return {"worker_error": "binding_mismatch"}
        baseline_digest = semantic_digest("report", {key: value for key, value in scientific.items() if key != "baseline_digest"})
        details = response.get("details", {})
        fresh = details.get("fresh_replay", {})
        if (scientific.get("baseline_digest") != baseline_digest or fresh.get("baseline_digest") != baseline_digest
                or fresh.get("anchors") != expected or details.get("scientific_report") != scientific["report"]
                or details.get("search") != scientific["search"] or details.get("exact_trials") != scientific["exact_trials"]):
            return {"worker_error": "artifact_mismatch"}
        result = response["result"]
        reference = {key: artifact[key] for key in ("id", "sha256", "byte_size", "media_type")}
        checked = fresh["candidate_results"]
        expected_candidates = [{"id": candidate["candidate_id"], "parameter_vector": candidate["parameters"],
            "problem_id": problem["id"], "problem_digest": problem["digest"], "observable": "concentration",
            "checked_horizon": scientific["report"]["checked"]["historical_horizon"],
            "verification": candidate["verification"], "artifact_ids": [reference["id"]]} for candidate in checked]
        if (result.get("artifacts") != [reference] or result.get("problem_id") != problem["id"]
                or result.get("problem_digest") != problem["digest"] or result.get("scientific_outcome") != fresh["outcome"]["scientific_outcome"]
                or result.get("reason_code") != fresh["outcome"]["reason_code"] or result.get("replay") != fresh["replay"]
                or result.get("expected_binding") != fresh["expected_binding"] or result.get("verification") != fresh["verification"]
                or result.get("candidates") != expected_candidates):
            return {"worker_error": "binding_mismatch"}
        result = {**result, "projection_version": APPLICATION_MAPPING,
            "scientific_problem_digest": projection["projection_digest"], "native_replay": fresh,
            "candidate_results": [{key: value for key, value in candidate.items() if key not in {"parameters", "rows"}}
                                  for candidate in fresh["candidate_results"]]}
        if result.get("verification_record"):
            result["verification_record"] = {**result["verification_record"],
                "expected_scientific_problem_digest": projection["projection_digest"],
                "observed_scientific_problem_digest": projection["projection_digest"]}
        search = scientific["search"]
        result["baseline_search"] = {key: search[key] for key in ("policy", "execution", "reason_code", "partial",
            "attempted_count", "evaluated_count", "possible_count", "feasible_count", "retained_count", "settings")}
        result["baseline_search"]["exact_attempts"] = len(scientific["exact_trials"])
        result["_native_artifacts"] = [{**reference, "content_base64": artifact["bytes_base64"],
            "artifact_kind": "bundle", "anchor": expected}]
        result["_application_projection"] = projection
        return result

    def review(self, problem: dict, dataset: dict, limits: dict, context: dict) -> dict:
        """Review the immutable selected pair against one approved hypothetical row."""
        return self._review_candidates(problem, dataset, limits, context, operation="review")

    def recheck(self, problem: dict, dataset: dict, limits: dict, context: dict) -> dict:
        """Check the original vectors against one independently reviewed reading."""
        return self._review_candidates(problem, dataset, limits, context, operation="recheck")

    def _review_candidates(self, problem: dict, dataset: dict, limits: dict, context: dict, *, operation: str) -> dict:
        from .followup_evidence import validate_followup_packet
        required = ("run_id", "scenario_id", "workflow", "historical_artifact", "design_request")
        if any(key not in context for key in required) or (operation == "recheck" and "observation_proposal" not in context):
            return {"worker_error": "incomplete_historical_projection"}
        wall = limits["scientific_wall_seconds"]
        admitted = self._run({"protocol": NATIVE_PROTOCOL, "operation": "admission",
                             "problem": problem, "dataset": dataset}, min(5, wall))
        if "worker_error" in admitted:
            return admitted
        projection = self._projection(admitted, problem, dataset)
        payload = {"protocol": NATIVE_PROTOCOL, "operation": operation, "problem": problem,
            "dataset": dataset, "run_id": context["run_id"], "scenario_id": context["scenario_id"],
            "workflow": context["workflow"], "limits": {"wall_seconds": wall, "max_bundle_bytes": 4 * 1024 * 1024},
            "historical_artifact": context["historical_artifact"]}
        if operation == "recheck":
            payload["observation_proposal"] = context["observation_proposal"]
        response = self._run(payload, wall)
        if "worker_error" in response:
            return response
        try:
            if response.get("protocol") != NATIVE_PROTOCOL or response.get("ok") is not True or len(response["native_artifacts"]) != 1:
                return {"worker_error": "incomplete_export"}
            artifact = response["native_artifacts"][0]
            content = base64.b64decode(artifact["bytes_base64"], validate=True)
            packet = json.loads(content)
            science = json.loads(base64.b64decode(packet["scientific"]["bytes_base64"], validate=True))
            reference = {key: artifact[key] for key in ("id", "sha256", "byte_size", "media_type")}
            if (not content or len(content) != artifact["byte_size"] or len(content) > 4 * 1024 * 1024
                    or hashlib.sha256(content).hexdigest() != artifact["sha256"]
                    or artifact["media_type"] != NATIVE_MEDIA_TYPE
                    or science["limits"] != {"wall_seconds": wall, "max_bundle_bytes": 4 * 1024 * 1024}):
                return {"worker_error": "artifact_mismatch"}
            details = response["details"]
            fresh = details["fresh_replay"]
            if (details["scientific_report"] != science["report"] or details["search"] is not None
                    or details["exact_trials"] != [] or response["result"]["artifacts"] != [reference]):
                return {"worker_error": "binding_mismatch"}
            result = {**response["result"], "projection_version": APPLICATION_MAPPING,
                "scientific_problem_digest": projection["projection_digest"], "native_replay": fresh,
                "candidate_results": [{key: value for key, value in item.items() if key not in {"parameters", "rows"}}
                                      for item in fresh["candidate_results"]]}
            result["verification_record"] = {**result["verification_record"],
                "expected_scientific_problem_digest": projection["projection_digest"],
                "observed_scientific_problem_digest": projection["projection_digest"]}
            job = {"id": context["run_id"], "plan_id": context["workflow"]["plan_id"],
                   "approval_id": context["workflow"]["approval_id"]}
            validate_followup_packet(content, response["anchors"], projection=projection, job=job,
                scenario_id=context["scenario_id"], result=result, historical_artifact=context["historical_artifact"],
                design_request=context["design_request"],
                **({"observation_proposal": context["observation_proposal"]} if operation == "recheck" else {}))
            result["_native_artifacts"] = [{**reference, "content_base64": artifact["bytes_base64"],
                "artifact_kind": "bundle", "anchor": response["anchors"]}]
            result["_application_projection"] = projection
            return result
        except DomainError as error:
            return {"worker_error": error.code}
        except (KeyError, ValueError, TypeError):
            return {"worker_error": "invalid_native_artifact"}

    def replay_native(self, content: bytes, *, expected: dict, wall_seconds: int = 120) -> dict:
        response = self._run({"protocol": NATIVE_PROTOCOL, "operation": "replay",
            "native_artifact_base64": base64.b64encode(content).decode("ascii"), "expected": expected}, wall_seconds)
        return response if "worker_error" in response else response["result"]

    def design(self, request: dict, historical_evidence: dict) -> dict:
        if historical_evidence.get("evidence", {}).get("body", {}).get("result", {}).get("projection_version") == APPLICATION_MAPPING:
            return self._native_design(request, historical_evidence)
        for name in ("problem", "dataset", "workflow"):
            if name not in historical_evidence:
                return {"worker_error": "incomplete_historical_projection"}
        problem, dataset = historical_evidence["problem"], historical_evidence["dataset"]
        if request["problem_id"] != problem["id"] or request["problem_digest"] != problem["digest"]:
            return {"worker_error": "binding_mismatch"}
        projection = project_problem(problem, dataset)
        native = historical_evidence.get("native_artifacts", [])
        lookup = {item["id"]: item for item in native}
        source_ids = request.get("source_artifact_ids", [])
        if not source_ids:
            source_digests = [None, None]
        elif len(source_ids) == 1 and source_ids[0] in lookup:
            source_digests = [lookup[source_ids[0]]["sha256"]] * 2
        elif len(source_ids) == 2 and all(identity in lookup for identity in source_ids):
            source_digests = [lookup[identity]["sha256"] for identity in source_ids]
        else:
            return {"worker_error": "incomplete_export"}
        science_request = project_design(request, projection, source_digests)
        # Counterdex's only design normalization is exact chronological grid
        # ordering. Compute this identity independently from approved input, not
        # from a digest or payload asserted by the child result.
        normalized_design = {**science_request, "grid": sorted(science_request["grid"], key=lambda row: Fraction(row["time"]))}
        expected_problem_digest = semantic_digest("problem", projection)
        expected_design_digest = semantic_digest("design-request", normalized_design)
        supplied = list({lookup[identity]["sha256"]: lookup[identity] for identity in source_ids}.values())
        result = self._run({"operation": "design", "problem": projection, "design": science_request,
                            "expected_problem_digest": expected_problem_digest, "expected_design_digest": expected_design_digest,
                            "workflow": historical_evidence["workflow"], "artifacts": supplied}, request["budget"]["wall_seconds"])
        if "worker_error" in result:
            return result
        if result["problem_digest"] != expected_problem_digest or result["design_digest"] != expected_design_digest:
            return {"worker_error": "scientific_projection_mismatch"}
        content = base64.b64decode(result["content_base64"], validate=True)
        if len(content) != result["byte_size"] or hashlib.sha256(content).hexdigest() != result["sha256"]:
            return {"worker_error": "artifact_mismatch"}
        bundle = json.loads(content)
        if (bundle["problem"] != projection or bundle["design"] != normalized_design
            or bundle["workflow"] != historical_evidence["workflow"] or bundle["report"] != result["report"]
            or bundle["implementation"] != result["identity"]):
            return {"worker_error": "scientific_projection_mismatch"}
        suggestion_digest = semantic_digest("suggestion", {key: value for key, value in bundle.items() if key != "suggestion_digest"})
        if result["suggestion_digest"] != suggestion_digest or bundle["suggestion_digest"] != suggestion_digest:
            return {"worker_error": "artifact_mismatch"}
        report, replay = result["report"], result["native_replay"]
        checked = report["checked"]
        tier = report["tier"]
        checked_rows = {row["time"]: row for row in checked.get("rows", [])}
        numeric_rows = {row["time"]: row for row in report["numerical"].get("rows", [])}
        options = []
        for time in request["feasible_times"]:
            row = checked_rows.get(time) if tier in {"checked_pair_separation", "no_separation_established"} else numeric_rows.get(time)
            row = row or {"status": "unavailable", "reason_code": "incomplete_result"}
            options.append({"time": time, "state": row["status"], "reason_code": row.get("reason_code") or "evaluated",
                            "exact_margin": row.get("margin") if time in checked_rows and tier != "numerical_guidance" else None})
        alias = "native_" + result["sha256"]
        reference = {"id": alias, "sha256": result["sha256"], "byte_size": result["byte_size"], "media_type": "application/json"}
        anchor = {"projection_version": PROJECTION_VERSION, "application_problem_id": problem["id"],
            "application_problem_digest": problem["digest"], "application_dataset_id": dataset["id"],
            "application_dataset_digest": dataset["digest"], "scientific_problem_digest": result["problem_digest"],
            "scientific_design_digest": result["design_digest"], "native_suggestion_digest": result["suggestion_digest"]}
        verification = checked.get("verification", "not_checked")
        verification_record = None
        if checked.get("pair_digest"):
            verification_record = {"checker_name": "counterdex", "checker_version": result["identity"]["adapter_version"],
                "artifact_id": alias, "artifact_sha256": result["sha256"],
                "proposition": "Fresh fixed-pair compatibility, candidate-specific exclusion and finite-grid separation under the reviewed model and allowances.",
                "verification": verification, "expected_binding": replay["expected_binding"],
                "expected_problem_digest": problem["digest"], "observed_problem_digest": problem["digest"],
                "expected_scientific_problem_digest": result["problem_digest"], "observed_scientific_problem_digest": result["problem_digest"]}
        return {"design_tier": tier, "verification": verification, "replay": replay["replay"],
            "reason_code": checked.get("reason_code") or "checked_pair_separation",
            "selected_time": checked.get("selected_time") if tier in {"checked_pair_separation", "no_separation_established"} else report["numerical"].get("selected_time"),
            "options": options, "algorithm": science_request["checked_policy"] if tier != "numerical_guidance" else science_request["numerical_policy"],
            "candidate_ids": request["candidate_ids"], "future_hard_allowance": request["future_hard_allowance"],
            "artifacts": [reference], "verification_record": verification_record,
            "projection_version": PROJECTION_VERSION, "scientific_problem_digest": result["problem_digest"],
            "scientific_design_digest": result["design_digest"], "native_suggestion_digest": result["suggestion_digest"],
            "candidate_results": checked.get("candidate_results", []), "native_replay": replay,
            "_native_artifacts": [{**reference, "content_base64": result["content_base64"], "artifact_kind": "bundle", "kind": "bundle", "anchor": anchor}]}

    @staticmethod
    def _native_design_projection(request: dict, projection: dict, request_digest: str) -> dict:
        """Reconstruct reviewed scope without trusting a child's projection."""
        return project_native_design(request, projection["problem"], request_digest)

    def _native_design(self, request: dict, history: dict) -> dict:
        required = ("problem", "dataset", "workflow", "run_id", "expected_request_digest",
                    "historical_artifact", "remaining_wall_seconds")
        if any(name not in history for name in required):
            return {"worker_error": "incomplete_historical_projection"}
        if request.get("source_artifact_ids", []):
            return {"worker_error": "unsupported_artifact_reuse"}
        problem, dataset = history["problem"], history["dataset"]
        if (request["problem_id"] != problem["id"] or request["problem_digest"] != problem["digest"]
                or semantic_digest("design-request", request) != history["expected_request_digest"]
                or history["workflow"].get("operation_id") != history["run_id"]
                or history["workflow"].get("execution_id") != history["run_id"]):
            return {"worker_error": "binding_mismatch"}
        wall = min(request["budget"]["wall_seconds"], history["remaining_wall_seconds"])
        if wall < 1:
            return {"worker_error": "budget_exhausted"}
        admitted = self._run({"protocol": NATIVE_PROTOCOL, "operation": "admission",
                             "problem": problem, "dataset": dataset}, min(5, wall))
        if "worker_error" in admitted:
            return admitted
        projection = self._projection(admitted, problem, dataset)
        try:
            design = self._native_design_projection(request, projection, history["expected_request_digest"])
        except DomainError as error:
            return {"worker_error": error.code}
        response = self._run({"protocol": NATIVE_PROTOCOL, "operation": "design", "problem": problem,
            "dataset": dataset, "run_id": history["run_id"], "workflow": history["workflow"], "request": request,
            "expected_request_digest": history["expected_request_digest"],
            "historical_evidence": history["evidence"]["body"], "historical_artifact": history["historical_artifact"]}, wall)
        if "worker_error" in response:
            return response
        return self._native_design_output(response, request, history, projection, design)

    @staticmethod
    def _native_design_output(response: dict, request: dict, history: dict, projection: dict, design: dict) -> dict:
        if (response.get("protocol") != NATIVE_PROTOCOL or response.get("ok") is not True
                or len(response.get("native_artifacts", [])) != 1):
            return {"worker_error": "incomplete_export"}
        artifact = response["native_artifacts"][0]
        try:
            content = base64.b64decode(artifact["bytes_base64"], validate=True)
            packet = json.loads(content)
            native = base64.b64decode(packet["scientific"]["bytes_base64"], validate=True)
            scientific = json.loads(native)
        except (KeyError, TypeError, ValueError):
            return {"worker_error": "invalid_native_artifact"}
        if (not content or len(content) > request["budget"]["bundle_bytes"] or len(content) != artifact["byte_size"]
                or hashlib.sha256(content).hexdigest() != artifact["sha256"] or artifact["media_type"] != NATIVE_MEDIA_TYPE
                or hashlib.sha256(native).hexdigest() != packet["scientific"]["sha256"]):
            return {"worker_error": "artifact_mismatch"}
        design_digest = semantic_digest("design-request", design)
        expected = {"artifact_sha256": artifact["sha256"], "dataset_digest": history["dataset"]["digest"],
            "problem_digest": history["problem"]["digest"], "projection_digest": projection["projection_digest"],
            "app_request_digest": history["expected_request_digest"], "design_digest": design_digest,
            "scenario_id": request["scenario_id"], "run_id": history["run_id"]}
        binding = {"schema_version": "counterdex.application-design-binding.v1", "mapping_policy": native_design_mapping_policy(request),
            "application": projection["binding"], "request": request, "request_digest": history["expected_request_digest"],
            "historical_evidence": history["evidence"]["body"], "design_digest": design_digest,
            "approved_grid_order": request["feasible_times"]}
        if (response.get("anchors") != expected or packet.get("schema_version") != "counterdex.application-bundle.v1"
                or packet.get("operation") != "design" or packet.get("binding") != binding
                or packet.get("run_id") != history["run_id"] or packet.get("scenario_id") != request["scenario_id"]
                or packet.get("history") != history["historical_artifact"] or scientific.get("problem") != projection["problem"]
                or scientific.get("design") != design or scientific.get("workflow") != history["workflow"]):
            return {"worker_error": "binding_mismatch"}
        suggestion_digest = semantic_digest("suggestion", {key: value for key, value in scientific.items() if key != "suggestion_digest"})
        details = response.get("details", {})
        fresh = details.get("fresh_replay", {})
        if (scientific.get("suggestion_digest") != suggestion_digest or fresh.get("suggestion_digest") != suggestion_digest
                or details.get("scientific_report") != scientific.get("report") or fresh.get("anchors") != expected
                or fresh.get("packet_profile") != "counterdex.application-bundle.v1" or fresh.get("operation") != "design"
                or fresh.get("integrity") != "passed" or fresh.get("expected_binding") != "matches"
                or fresh.get("dataset_origin") != projection["binding"]["dataset_origin"]):
            return {"worker_error": "artifact_mismatch"}
        result, report = response["result"], scientific["report"]
        checked = fresh.get("fresh_checked", {})
        valid = checked.get("verification") == "valid" and fresh["replay"] == "passed"
        if design["requested_tier"] == "numerical_guidance" and (
                valid or report.get("tier") not in {"numerical_guidance", "unavailable"}
                or fresh.get("verification") != "not_checked" or fresh.get("replay") != "unsupported"
                or report["checked"].get("verification") != "not_checked"
                or report["checked"].get("construction_attempts") != 0
                or report["checked"].get("pair_verification_passes") != 0
                or scientific.get("artifacts") != []):
            return {"worker_error": "binding_mismatch"}
        rows = checked["rows"] if valid else report["numerical"]["rows"]
        options = {row["time"]: {"time": row["time"], "state": row["status"],
            "reason_code": row["reason_code"] or ("exact_margin_checked" if valid else "numerical_only"),
            "exact_margin": row.get("margin") if valid else None} for row in rows}
        reference = {key: artifact[key] for key in ("id", "sha256", "byte_size", "media_type")}
        facts = {"design_tier": checked["tier"] if valid else report["tier"], "verification": fresh["verification"],
            "replay": fresh["replay"], "reason_code": (checked.get("reason_code") or "strict_positive_margin") if valid else fresh["reason_code"],
            "selected_time": checked["selected_time"] if valid else report["numerical"]["selected_time"],
            "algorithm": design["checked_policy"] if valid else design["numerical_policy"],
            "candidate_ids": request["candidate_ids"], "future_hard_allowance": request["future_hard_allowance"], "artifacts": [reference]}
        verification = result.get("verification_record") or {}
        if (set(options) != set(request["feasible_times"]) or len(rows) != len(options)
                or result.get("options") != [options[time] for time in request["feasible_times"]]
                or any(result.get(key) != value for key, value in facts.items())
                or (valid and fresh.get("recorded_result_matches") is not True)
                or (valid and checked != {key: value for key, value in report["checked"].items()
                                           if key not in {"construction_attempts", "pair_verification_passes"}})
                or verification.get("verification") != fresh["verification"] or verification.get("expected_binding") != "matches"
                or verification.get("artifact_id") != reference["id"] or verification.get("artifact_sha256") != reference["sha256"]
                or verification.get("expected_problem_digest") != history["problem"]["digest"]
                or verification.get("observed_problem_digest") != history["problem"]["digest"]
                or verification.get("checker_name") != "counterdex"
                or verification.get("checker_version") != scientific["implementation"]["adapter_version"]):
            return {"worker_error": "binding_mismatch"}
        return {**result, "projection_version": APPLICATION_MAPPING,
            "scientific_problem_digest": projection["projection_digest"], "scientific_design_digest": design_digest,
            "native_suggestion_digest": suggestion_digest, "native_replay": fresh,
            "candidate_results": fresh.get("candidate_results", []), "verification_record": {**verification,
                "expected_scientific_problem_digest": projection["projection_digest"],
                "observed_scientific_problem_digest": projection["projection_digest"]},
            "_application_projection": projection, "_native_artifacts": [{**reference,
                "content_base64": artifact["bytes_base64"], "artifact_kind": "bundle", "anchor": expected}]}

    def replay(self, content: bytes, *, expected_problem_digest: str, expected_suggestion_digest: str, wall_seconds: int = 120) -> dict:
        return self._run({"operation": "replay", "content_base64": base64.b64encode(content).decode("ascii"),
            "expected_problem_digest": expected_problem_digest, "expected_suggestion_digest": expected_suggestion_digest}, wall_seconds)


def create_science_adapter(python_executable: str = "python3.11", selection: str = "counterdex"):
    if selection == "counterdex":
        return CounterdexAdapter(python_executable)
    if selection == "unavailable":
        from .science import UnavailableAdapter
        return UnavailableAdapter()
    raise DomainError("scientific_adapter_configuration", "Select counterdex or the explicit unavailable lane.", 503)
