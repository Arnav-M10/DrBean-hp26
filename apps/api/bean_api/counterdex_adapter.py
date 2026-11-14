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
from .scientific_projection import PROJECTION_VERSION, admit_problem, project_design, project_problem
from .workflow import DomainError


@dataclass
class CounterdexAdapter:
    python_executable: str = "python3.11"

    def _run(self, payload: dict, wall_seconds: int) -> dict:
        executable = shutil.which(self.python_executable)
        if executable is None:
            return {"worker_error": "scientific_runtime_missing"}
        raw = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
        if len(raw) > 8 * 1024 * 1024:
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
        if result.returncode or len(result.stdout) > 8 * 1024 * 1024:
            return {"worker_error": "scientific_bridge_failed"}
        try:
            response = json.loads(result.stdout)
        except (ValueError, UnicodeError):
            return {"worker_error": "scientific_bridge_failed"}
        if not isinstance(response, dict):
            return {"worker_error": "scientific_bridge_failed"}
        if "engine_error" in response:
            return {"worker_error": response["engine_error"]["code"], "engine_error": response["engine_error"]}
        return response

    def capabilities(self) -> dict:
        probe = self._run({"operation": "probe"}, 5)
        available = "worker_error" not in probe
        return {"implemented": True, "configured": bool(self.python_executable), "available": available,
                "verified_in_environment": False, "adapter": "Counterdex", "adapter_version": "0.1.0",
                "projection_version": PROJECTION_VERSION, "runtime": probe.get("identity"),
                "reason": probe.get("worker_error") or "baseline_producer_unavailable",
                "baseline_discovery": False, "claim_families": [],
                "design_tiers": ["numerical_guidance", "checked_pair_separation", "no_separation_established"] if available else [],
                "native_replay": available, "browser_replay": False,
                "qualification": "Runtime availability; each result requires actual checking and fresh native replay."}

    def admit(self, problem: dict, dataset: dict) -> None:
        # Building the projection also checks bounded text/provenance without loss.
        project_problem(problem, dataset)

    def investigate(self, problem: dict, dataset: dict, limits: dict) -> dict:
        admit_problem(problem, dataset)
        probe = self._run({"operation": "probe"}, min(5, limits["scientific_wall_seconds"]))
        if "worker_error" in probe:
            return probe
        # No fixture pair, hardcoded optimizer output or local replacement theorem.
        return {"scientific_outcome": "unsupported", "verification": "unsupported",
            "expected_binding": "not_supplied", "replay": "unsupported", "reason_code": "baseline_producer_unavailable",
            "problem_id": problem["id"], "problem_digest": problem["digest"], "candidates": [], "artifacts": [],
            "projection_version": PROJECTION_VERSION,
            "scientific_problem_digest": semantic_digest("problem", project_problem(problem, dataset))}

    def design(self, request: dict, historical_evidence: dict) -> dict:
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
