"""Explicit source review to immutable executable inputs, without approval."""

from __future__ import annotations

import hashlib
import json
import re

from .canonical import canonical_bytes
from .contracts import DatasetBody, MaterializeIntakeRequest, ProblemBody
from .intake import validate_intake_context
from .workflow import DomainError


def _canonical_path(path: str) -> str:
    if re.fullmatch(r"(?:A|ka|ke)\.(?:lower|upper)", path):
        return "domain." + path
    if re.fullmatch(r"rows\[\d+\]\.value", path):
        return path.removesuffix("value") + "concentration"
    if re.fullmatch(r"rows\[\d+\]\.(?:unit|units)", path):
        return "concentration_unit"
    if re.fullmatch(r"rows\[\d+\]\.time_unit", path):
        return "time_unit"
    return path


def reviewed_input_values(dataset: dict, problem: dict) -> dict[str, str]:
    """Public field-path mapping, also useful for deliberate assumption review."""
    result = {"experiment_id": dataset["experiment_id"], "time_origin": dataset["time_origin"]}
    for index, row in enumerate(dataset["rows"]):
        result.update({f"rows[{index}].{field}": row[field] for field in ("time", "concentration", "hard_allowance")})
        result[f"rows[{index}].included"] = "true" if row["included"] else "false"
        result[f"rows[{index}].notes"] = row["notes"]
    for field in ("model", "observable", "initial_concentration", "time_unit", "concentration_unit", "rate_unit"):
        result[field] = problem[field]
    for parameter in ("A", "ke", "ka"):
        for side in ("lower", "upper"):
            result[f"domain.{parameter}.{side}"] = problem["domain"][parameter][side]
    for field in ("lower", "upper", "parameter"):
        result[f"target.{field}"] = problem["target"][field]
    return result


class SourceMaterializationService:
    def __init__(self, workflow, sources=None):
        self.workflow, self.sources = workflow, sources

    def materialize(self, actor: str, workspace_id: str, review_id: str,
                    request: MaterializeIntakeRequest | dict, key: str) -> dict:
        request = MaterializeIntakeRequest.model_validate(request)
        submitted = request.model_dump(mode="json")
        request_digest = hashlib.sha256(canonical_bytes(submitted)).hexdigest()

        def action(conn):
            review = self.workflow._get(conn, actor, review_id, "intake_review")
            self.workflow._same_workspace(workspace_id, review)
            if review["digest"] != request.expected_review_digest:
                raise DomainError("stale_review", "Materialize the exact reviewed source revision.", 409)
            existing = conn.execute("SELECT body FROM entities WHERE kind='intake_materialization' AND parent_id=?", (review_id,)).fetchone()
            if existing:
                association = json.loads(existing["body"])
                if association["request_digest"] != request_digest:
                    raise DomainError("review_already_materialized", "This review already created different immutable inputs; prepare a new review.")
                return self._existing(conn, actor, review_id, association)
            source = self.workflow._get(conn, actor, review["body"]["source_asset_id"], "source_asset")
            self.workflow._same_workspace(workspace_id, source)
            # Retention is required for a new association; completed operation
            # retries above still return their immutable original result.
            if self.sources is not None:
                self.sources.read(actor, source["id"])
            proposal = self.workflow._get(conn, actor, review["body"]["proposal_id"], "intake_proposal")
            self.workflow._same_workspace(workspace_id, proposal)
            if proposal["digest"] != review["body"]["proposal_digest"] or proposal["body"]["source_digest"] != source["body"]["sha256"]:
                raise DomainError("source_binding_mismatch", "Source, proposal and review identities do not agree.", 422)
            current = self.workflow.authorize(actor, workspace_id, conn)
            validate_intake_context(proposal["body"], current)
            referenced = review["body"].get("current_revision_id")
            if referenced and referenced not in {current["current_dataset_id"], current["current_problem_id"]}:
                raise DomainError("stale_revision", "The selected input changed after source review.", current_revision_id=current["current_problem_id"] or current["current_dataset_id"])
            dataset = request.dataset.model_dump(mode="json")
            problem_inputs = request.problem.model_dump(mode="json")
            if source["body"]["origin"] == "synthetic" and dataset["origin"] == "actual":
                raise DomainError("origin_mismatch", "A synthetic source cannot become actual observed data.", 422, ["dataset.origin"])
            if dataset["parent_id"]:
                parent = self.workflow._get(conn, actor, dataset["parent_id"], "dataset")
                self.workflow._same_workspace(workspace_id, parent)
                if parent["id"] != current["current_dataset_id"]:
                    raise DomainError("stale_revision", "Review the current parent dataset before materializing the source.", current_revision_id=current["current_dataset_id"])
                if parent["body"]["experiment_id"] != dataset["experiment_id"]:
                    raise DomainError("experiment_mismatch", "A revision must retain its experiment identity.", 422)
                if parent["body"]["origin"] == "hypothetical" and dataset["origin"] != "hypothetical":
                    raise DomainError("origin_mismatch", "Hypothetical ancestry must remain hypothetical.", 422)
                if parent["body"]["origin"] == "synthetic" and dataset["origin"] == "actual":
                    raise DomainError("origin_mismatch", "Synthetic ancestry cannot be labeled actual.", 422)

            values = reviewed_input_values(dataset, problem_inputs)
            reviewed_paths = set()
            provenance = []
            for field in review["body"]["reviewed_fields"]:
                path = _canonical_path(field["field_path"])
                if path not in values or values[path] != field["normalized_value"]:
                    raise DomainError("review_value_mismatch", "Executed values must equal the exact source-review decision.", 422, [field["field_path"]])
                reviewed_paths.add(path)
                provenance.append({"field_path": path, "review_field_path": field["field_path"], "origin": field["origin"],
                    "review_id": review_id, "source_asset_id": source["id"],
                    "original_value": field["original_proposal"].get("original_value"),
                    "reviewed_value": field["normalized_value"], "correction_reason": field.get("correction_reason")})
            # Empty notes are metadata, not missing scientific assumptions.
            required = {p for p in values if not p.endswith(".notes")} - reviewed_paths
            assumptions = request.human_assumptions
            missing = sorted(required - assumptions.keys())
            if missing:
                raise DomainError("unreviewed_assumptions", "Explicitly describe every scientific input not supplied by this source review.", 422, missing)
            unknown = set(assumptions) - values.keys()
            if unknown:
                raise DomainError("invalid_assumption_path", "Assumptions must name an actual reviewed input field.", 422, sorted(unknown))
            for path in sorted(required):
                provenance.append({"field_path": path, "origin": "human_assumption", "description": assumptions[path], "reviewed_value": values[path], "source_asset_id": None})
            for index, row in enumerate(dataset["rows"]):
                if row["source_asset_id"] not in {None, source["id"]}:
                    raise DomainError("source_binding_mismatch", "A single-source materialization cannot cite another asset.", 422, [f"rows[{index}].source_asset_id"])
                row["source_asset_id"] = source["id"]
                originals = {}
                for field in review["body"]["reviewed_fields"]:
                    match = re.fullmatch(rf"rows\[{index}\]\.(time|concentration|value|hard_allowance)", field["field_path"])
                    if match and field["original_proposal"].get("original_value") is not None:
                        originals["concentration" if match[1] == "value" else match[1]] = field["original_proposal"]["original_value"]
                row["original_values"] = originals
            dataset = DatasetBody.model_validate(dataset).model_dump(mode="json")
            stored_dataset = self.workflow._insert(conn, actor, workspace_id, "dataset", dataset, dataset["parent_id"])
            problem = ProblemBody.model_validate({**problem_inputs, "dataset_id": stored_dataset["id"], "dataset_digest": stored_dataset["digest"]}).model_dump(mode="json")
            stored_problem = self.workflow._insert(conn, actor, workspace_id, "problem", problem)
            association = self.workflow._insert(conn, actor, workspace_id, "intake_materialization", {
                "review_id": review_id, "review_digest": review["digest"], "source_asset_id": source["id"],
                "source_sha256": source["body"]["sha256"], "dataset_id": stored_dataset["id"],
                "dataset_digest": stored_dataset["digest"], "problem_id": stored_problem["id"],
                "problem_digest": stored_problem["digest"], "field_provenance": provenance,
                "request_digest": request_digest, "execution_approved": False,
            }, review_id)
            conn.execute("UPDATE workspaces SET current_dataset_id=?,current_problem_id=? WHERE id=?", (stored_dataset["id"], stored_problem["id"], workspace_id))
            return {"dataset": stored_dataset, "problem": stored_problem, "materialization": association}

        return self.workflow._perform(actor, workspace_id, f"materialize-intake:{review_id}", key,
            {"review_id": review_id, **submitted}, action)

    def _existing(self, conn, actor, review_id, association):
        row = conn.execute("SELECT id FROM entities WHERE kind='intake_materialization' AND parent_id=?", (review_id,)).fetchone()
        return {"dataset": self.workflow._get(conn, actor, association["dataset_id"], "dataset"),
                "problem": self.workflow._get(conn, actor, association["problem_id"], "problem"),
                "materialization": self.workflow._get(conn, actor, row["id"], "intake_materialization")}
