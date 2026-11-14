"""Read-only investigation comparison and immutable, unapproved setup templates."""
from __future__ import annotations

from .contracts import ExperimentTemplateRequest, MaterializedProblemInputs
from .workflow import DomainError


def differences(before, after, path=""):
    """Exact values, including presence; no rounding or scientific inference."""
    if isinstance(before, dict) and isinstance(after, dict):
        rows = []
        for key in sorted(before.keys() | after.keys()):
            escaped = str(key).replace("~", "~0").replace("/", "~1")
            child = path + "/" + escaped
            if key not in before or key not in after:
                rows.append({"path": child, "before_present": key in before, "after_present": key in after,
                             "before": before.get(key), "after": after.get(key)})
            else:
                rows.extend(differences(before[key], after[key], child))
        return rows
    return [] if before == after else [{"path": path, "before_present": True, "after_present": True,
                                        "before": before, "after": after}]


class ResearcherTools:
    def __init__(self, workflow):
        self.workflow = workflow

    def create_template(self, actor, workspace_id, body, key):
        body = ExperimentTemplateRequest.model_validate(body).model_dump(mode="json")
        def action(conn):
            problem = self.workflow._get(conn, actor, body["problem_id"], "problem")
            self.workflow._same_workspace(workspace_id, problem)
            if problem["digest"] != body["problem_digest"]:
                raise DomainError("binding_mismatch", "Save the exact selected problem setup.", 422)
            inputs = MaterializedProblemInputs.model_validate({k: v for k, v in problem["body"].items()
                if k not in {"schema_version", "dataset_id", "dataset_digest"}}).model_dump(mode="json")
            defaults = {k: body[k] for k in ("name", "description", "default_hard_allowance", "allowance_origin", "methods")}
            return self.workflow._insert(conn, actor, workspace_id, "experiment_template", {
                "format": "experiment-template.v1", **defaults, "problem_inputs": inputs,
                "source_problem_id": problem["id"], "source_problem_digest": problem["digest"],
                "requires_review": True}, problem["id"])
        return self.workflow._perform(actor, workspace_id, "create:experiment-template", key, body, action)

    def template_draft(self, actor, template_id):
        record = self.workflow.get(actor, template_id, "experiment_template")
        return {"template_id": record["id"], "template_digest": record["digest"],
                "requires_review": True, "defaults": record["body"],
                "message": "Draft defaults only. Supply the new experiment, measurements and provenance, then review and approve a new plan."}

    def _snapshot(self, conn, actor, workspace_id, run_id):
        job = self.workflow._job(conn, actor, run_id, "run")
        self.workflow._same_workspace(workspace_id, job)
        plan = self.workflow._get(conn, actor, job["plan_id"], "plan")
        scopes, results, identities = {}, {}, []
        reservations = {item["scenario_id"]: item for item in job["scenarios"]}
        for scenario in plan["body"]["scenarios"]:
            problem = self.workflow._get(conn, actor, scenario["problem_id"], "problem")
            dataset = self.workflow._get(conn, actor, problem["body"]["dataset_id"], "dataset")
            for record in (problem, dataset):
                self.workflow._same_workspace(workspace_id, record)
            data = dataset["body"]
            scopes[scenario["id"]] = {"purpose": scenario.get("purpose"), "kind": scenario["kind"],
                "eligibility": scenario.get("eligible_baseline_outcomes"),
                "dataset": {**{k: v for k, v in data.items() if k not in {"rows", "parent_id"}},
                    "rows": {row["id"]: row for row in data["rows"]}, "row_order": [row["id"] for row in data["rows"]]},
                "problem": {k: v for k, v in problem["body"].items() if k not in {"dataset_id", "dataset_digest"}}}
            reservation = reservations.get(scenario["id"], {})
            outcome = {"state": reservation.get("state", "not_started"), "reason_code": reservation.get("reason_code")}
            evidence = None
            if reservation.get("result_id"):
                evidence = self.workflow._get(conn, actor, reservation["result_id"], "evidence")
                self.workflow._same_workspace(workspace_id, evidence)
                if evidence["body"]["run_id"] != run_id or evidence["body"]["scenario_id"] != scenario["id"]:
                    raise DomainError("binding_mismatch", "Comparison evidence must belong to its selected scenario.")
                result = evidence["body"]["result"]
                outcome["result"] = {k: result[k] for k in ("scientific_outcome", "verification", "expected_binding",
                    "replay", "reason_code", "candidates", "candidate_results", "baseline_search") if k in result}
            results[scenario["id"]] = outcome
            identities.append({"scenario_id": scenario["id"], "problem_id": problem["id"], "problem_digest": problem["digest"],
                "dataset_id": dataset["id"], "dataset_digest": dataset["digest"],
                "evidence_id": evidence["id"] if evidence else None, "evidence_digest": evidence["digest"] if evidence else None})
        baseline = scopes[plan["body"]["scenarios"][0]["id"]]
        return {"run_id": run_id, "state": job["state"], "error_code": job["error_code"], "plan_id": plan["id"],
            "plan_digest": plan["digest"], "scenario_records": identities,
            "experiment_id": baseline["dataset"]["experiment_id"], "model": baseline["problem"]["model"],
            "inputs": {"scenarios": scopes, **{k: plan["body"].get(k) for k in
                ("objective", "budget", "permitted_tools", "provider_disclosure", "followup")}}, "results": results}

    def compare(self, actor, workspace_id, left_run_id, right_run_id):
        with self.workflow.store.read() as conn:
            conn.execute("BEGIN")  # One coherent read snapshot across both runs.
            self.workflow.authorize(actor, workspace_id, conn)
            left = self._snapshot(conn, actor, workspace_id, left_run_id)
            right = self._snapshot(conn, actor, workspace_id, right_run_id)
        return {"format": "investigation-comparison.v1", "left": left, "right": right,
            "same_experiment_and_model": (left["experiment_id"], left["model"]) == (right["experiment_id"], right["model"]),
            "input_changes": differences(left["inputs"], right["inputs"]),
            "result_changes": differences(left["results"], right["results"]),
            "scope": "Exact recorded differences only. Outcomes retain their original conditional scope; this comparison establishes neither causality nor a global scientific claim."}
