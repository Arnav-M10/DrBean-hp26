"""Qualification of real-science observations. A claim of success is never enough.

The runner calls :func:`qualify` for every entry of a lane that carries no frozen
case assertions (``offline_real_science`` and the retained ``actual_full_stack``).
``state: completed``, ``status: passed`` or a nonempty reference string cannot
qualify an entry on their own. Qualification needs, independently re-checked here:

1. evidence class ``executed_acceptance``: the observation came from a subject the
   runner executed in this process against a stack it launched. Recorded or
   imported observations are ``imported_claim`` and never qualify;
2. every evidence file listed in the observation exists and has its recorded digest;
3. the saved authenticated records link up: plan -> problem -> dataset digests,
   approval scope/digest, run plan/approval, evidence run/problem, design request
   historical run, candidate ids and exact vectors, design approval and job;
4. each saved native packet still hashes to its reference and passes a fresh
   native replay run here, with anchors re-extracted from the saved authenticated
   record files (never from the bundle);
5. external model dispatch verified zero by the guard in the API and worker;
6. no required check failed. Blocked or unobserved checks make the entry ``unrun``
   with the blocking reason, never ``passed``.
"""
from __future__ import annotations

import hashlib
import json
import os

from . import contract, kinetics, native

EVIDENCE_CLASSES = ("executed_acceptance", "preview", "diagnostic", "validated_trace", "imported_claim")
EXECUTED = ("executed_acceptance", "preview", "diagnostic")  # executed and re-checked by this runner


def _load(evidence_dir: str, rel: str):
    with open(os.path.join(evidence_dir, rel), "rb") as handle:
        data = handle.read()
    return data, json.loads(data.decode("utf-8")) if rel.endswith(".json") else None


def _file_checks(observation: dict, evidence_dir: str) -> list[dict]:
    out = []
    index = observation.get("evidence_index") or {}
    for name, item in sorted(index.items()):
        path = os.path.join(evidence_dir, item.get("path", ""))
        if not item.get("path") or not os.path.isfile(path):
            out.append({"id": f"file:{name}", "passed": False, "detail": "listed evidence file is missing"})
            continue
        with open(path, "rb") as handle:
            digest = hashlib.sha256(handle.read()).hexdigest()
        out.append({"id": f"file:{name}", "passed": digest == item.get("sha256"),
                    "detail": "digest matches" if digest == item.get("sha256") else "digest differs from record"})
    return out


def _records(observation: dict, evidence_dir: str) -> dict:
    loaded = {}
    for name, item in (observation.get("evidence_index") or {}).items():
        if item.get("path", "").startswith("records/"):
            try:
                loaded[name] = _load(evidence_dir, item["path"])[1]
            except (OSError, ValueError):
                pass
    return loaded


def _link_checks(records: dict) -> list[dict]:
    """Cross-record identity links among saved authenticated responses."""
    out = []

    def check(check_id, condition, detail=""):
        out.append({"id": check_id, "passed": bool(condition), "detail": detail})

    labels = sorted({name.rsplit("-", 1)[0] for name in records if name.endswith("-plan")
                     and not name.endswith("design-plan")})
    for label in labels:
        dataset, problem, plan = records.get(f"{label}-dataset"), records.get(f"{label}-problem"), records.get(
            f"{label}-plan")
        approval, run = records.get(f"{label}-approval"), records.get(f"{label}-run")
        if not all((dataset, problem, plan, approval, run)):
            check(f"links:{label}:complete", False, "a baseline record is missing from the saved evidence")
            continue
        workspaces = {r.get("workspace_id") for r in (dataset, problem, plan, approval, run) if isinstance(r, dict)}
        workspaces |= {records[name].get("workspace_id") for name in records if name.startswith(label + "-")
                       and isinstance(records[name], dict) and records[name].get("workspace_id")}
        check(f"links:{label}:same_workspace", len(workspaces - {None}) == 1,
              f"records span workspaces {sorted(w for w in workspaces if w)}")
        check(f"links:{label}:problem_dataset", problem["body"]["dataset_id"] == dataset["id"]
              and problem["body"]["dataset_digest"] == dataset["digest"])
        check(f"links:{label}:plan_problem", plan["body"]["problem_id"] == problem["id"]
              and plan["body"]["problem_digest"] == problem["digest"] and plan["body"]["dataset_id"] == dataset["id"])
        check(f"links:{label}:approval_plan", approval.get("plan_id") == plan["id"]
              and approval.get("plan_digest") == plan["digest"] and approval.get("scope") == "investigation"
              and approval.get("expected_revision_id") == problem["id"])
        check(f"links:{label}:run_plan_approval", run.get("plan_id") == plan["id"]
              and run.get("approval_id") == approval["id"] and run.get("kind") == "run")
        evidence = records.get(f"{label}-evidence-baseline")
        if evidence:
            body = evidence.get("body") or {}
            check(f"links:{label}:evidence_run", body.get("run_id") == run["id"]
                  and body.get("problem_id") == problem["id"] and body.get("expected_problem_digest") == problem["digest"])
            child = next((s for s in run.get("scenarios", []) if s.get("scenario_id") == "baseline"), {})
            check(f"links:{label}:run_result_is_evidence", child.get("result_id") == evidence["id"])
        design_plan = records.get(f"{label}-design-plan")
        if design_plan:
            request = design_plan["body"]["request"]
            check(f"links:{label}:design_historical_run", request["historical_run_id"] == run["id"]
                  and request["problem_id"] == problem["id"] and request["problem_digest"] == problem["digest"])
            candidates = {c["id"]: c for c in ((evidence or {}).get("body") or {}).get("result", {}).get(
                "candidates", [])}
            check(f"links:{label}:design_pair_from_evidence",
                  all(cid in candidates and candidates[cid]["parameter_vector"] == vector
                      for cid, vector in zip(request["candidate_ids"], request["candidate_vectors"])),
                  "design candidates are exactly the run's frozen candidates")
            design_approval, job = records.get(f"{label}-design-approval"), records.get(f"{label}-design-job")
            if design_approval and job:
                check(f"links:{label}:design_approval", design_approval.get("plan_id") == design_plan["id"]
                      and design_approval.get("scope") == "design"
                      and design_approval.get("plan_digest") == design_plan["digest"]
                      and design_approval.get("id") != approval.get("id"))
                check(f"links:{label}:design_job", job.get("plan_id") == design_plan["id"]
                      and job.get("approval_id") == design_approval["id"] and job.get("kind") == "design_job")
                suggestion = records.get(f"{label}-suggestion")
                if suggestion:
                    check(f"links:{label}:suggestion_is_job_result", job.get("result_id") == suggestion["id"])
        scope = (plan.get("body") or {}).get("followup")
        if scope:
            out += _followup_links(label, scope, records)
    return out


def _followup_links(label: str, scope: dict, records: dict) -> list[dict]:
    """A design-bound follow-up: re-derive its binding and per-candidate verdicts from the saved records alone."""
    out = []

    def check(check_id, condition, detail=""):
        out.append({"id": f"links:{label}:{check_id}", "passed": bool(condition), "detail": detail})

    names = ("bound-design-job", "bound-suggestion", "bound-design-plan", "proposal", "parent-dataset", "dataset",
             "evidence-baseline", "report")
    job, suggestion, design_plan, proposal, parent, revised, evidence, report = (records.get(f"{label}-{n}") for n in names)
    missing = [n for n, r in zip(names, (job, suggestion, design_plan, proposal, parent, revised, evidence, report)) if not r]
    if missing:
        check("followup_complete", False, f"follow-up records missing from the saved evidence: {missing}")
        return out
    facts, request = suggestion.get("body") or {}, (design_plan.get("body") or {}).get("request") or {}
    refs = facts.get("artifacts") or []
    check("followup_binds_its_design", job.get("id") == scope.get("design_job_id")
          and job.get("result_id") == suggestion.get("id") == scope.get("design_result_id")
          and suggestion.get("digest") == scope.get("design_result_digest") and job.get("plan_id") == design_plan["id"]
          and len(refs) == 1 and refs[0].get("id") == scope.get("source_artifact_id"),
          "plan scope names the saved design job, its result digest and its single native artifact")
    observation = proposal.get("body") or {}
    row = observation.get("row") or {}
    before, after = parent.get("body") or {}, revised.get("body") or {}
    origin = "hypothetical" if "hypothetical" in (before.get("origin"), observation.get("origin")) else before.get("origin")
    result = (evidence.get("body") or {}).get("result") or {}
    operation = (result.get("native_replay") or {}).get("operation")
    expected_dataset = {**before, "parent_id": parent["id"], "rows": [*(before.get("rows") or []), row],
                        "origin": origin, "change_reason": observation.get("change_reason")}
    legacy_scope = (operation != "review" or (observation.get("origin") == "hypothetical"
                    and row.get("time") == facts.get("selected_time")
                    and row.get("hard_allowance") == request.get("future_hard_allowance")))
    check("followup_appends_exactly_the_reviewed_row", proposal.get("id") == scope.get("observation_proposal_id")
          and revised.get("parent_id") == parent["id"]
          and after == expected_dataset and observation.get("dataset_id") == parent["id"]
          and observation.get("experiment_id") == before.get("experiment_id")
          and row.get("included") is True and row.get("source_asset_id") is None
          and operation in ("review", "recheck") and legacy_scope,
          f"{operation}: reviewed row at {row.get('time')}, allowance {row.get('hard_allowance')}, origin {observation.get('origin')}")
    lineage = (report.get("body") or {}).get("followup") or {}
    review = (lineage.get("observation_review") or {}).get("body") or {}
    check("followup_review_binds_proposal", proposal.get("digest") == hashlib.sha256(contract.canonical_json(observation)).hexdigest()
          and lineage.get("observation_proposal") == proposal and lineage.get("dataset") == parent
          and lineage.get("revised_dataset") == revised
          and review == {"proposal_id": proposal["id"], "proposal_digest": proposal.get("digest"),
                         "dataset_id": revised["id"], "dataset_digest": revised.get("digest"), "accepted": True},
          "the accepted review binds the complete proposal body and this exact materialized revision")
    vectors = dict(zip(request.get("candidate_ids") or [], request.get("candidate_vectors") or []))
    candidates = {c.get("id"): c.get("parameter_vector") for c in result.get("candidates") or []}
    check("followup_rechecks_the_design_pair", bool(vectors) and candidates == vectors
          and result.get("baseline_search") is None, "exact original vectors; no new discovery")
    # Independent decimal oracle over every included row of the revised dataset.
    expected = {cid: kinetics.history_verdict(vec, (revised.get("body") or {}).get("rows") or [])
                for cid, vec in vectors.items()}
    observed = {c.get("candidate_id"): ("compatible" if c.get("verification") == "valid" else
                                        "excluded" if c.get("verification") == "invalid" else c.get("verification"))
                for c in result.get("candidate_results") or [] if c.get("candidate_id") in vectors}
    check("followup_verdicts_match_oracle", set(observed) == set(vectors) and all(
        expected[c] == "indeterminate" or observed[c] == expected[c] for c in vectors),
        f"application {observed}, independent oracle {expected}")
    target = ((records.get(f"{label}-problem") or {}).get("body") or {}).get("target") or {}
    if target and all(v != "indeterminate" for v in expected.values()):
        outside = [c for c in vectors if expected[c] == "compatible" and kinetics.outside_closed_claim(
            vectors[c][target["parameter"]], target["lower"], target["upper"])]
        expected_outcome = "certified_counterexample" if outside else "inconclusive"
        check("followup_outcome_follows_from_survivors", result.get("scientific_outcome") == expected_outcome,
              f"outcome {result.get('scientific_outcome')}; oracle survivors outside the closed claim {outside}")
    return out


def followup_native_binding(label: str, packet: dict, records: dict) -> dict:
    """Bind replayable bytes to independently saved proposal, revision and design records."""
    passed = False
    try:
        proposal, parent, revised, problem, plan, run, design, job, suggestion = (
            records[f"{label}-{name}"] for name in ("proposal", "parent-dataset", "dataset", "problem", "plan", "run",
                                                   "bound-design-plan", "bound-design-job", "bound-suggestion"))
        scope, request, facts = plan["body"]["followup"], design["body"]["request"], suggestion["body"]
        ref = facts["artifacts"][0]
        binding = packet["binding"]
        app = binding["application"] if packet["operation"] == "recheck" else binding
        expected_proposal = {key: proposal[key] for key in ("id", "digest", "body")}
        expected_parent = {"operation": "design", "run_id": job["id"], "scenario_id": request["scenario_id"],
            "problem_id": request["problem_id"], "problem_digest": request["problem_digest"],
            "dataset_id": parent["id"], "dataset_digest": parent["digest"], "projection_digest": facts["scientific_problem_digest"]}
        expected_anchor = {"artifact_sha256": ref["sha256"], "dataset_digest": parent["digest"],
            "problem_digest": request["problem_digest"], "projection_digest": facts["scientific_problem_digest"],
            "app_request_digest": design["body"]["request_digest"], "design_digest": facts["scientific_design_digest"],
            "run_id": job["id"], "scenario_id": request["scenario_id"]}
        operation = records[f"{label}-evidence-baseline"]["body"]["result"]["native_replay"]["operation"]
        scope_matches = (binding == {"schema_version": "counterdex.followup-binding.v1", "application": app,
                                     "observation_proposal": expected_proposal, "parent": expected_parent}
                         if operation == "recheck" else operation == "review")
        passed = (packet["operation"] == operation and scope_matches and packet["run_id"] == run["id"]
            and packet["scenario_id"] == records[f"{label}-evidence-baseline"]["body"]["scenario_id"]
            and app["schema_version"] == "counterdex.application-binding.v1"
            and app["mapping_policy"] == "DB-SC-1-to-groundwork-v1"
            and app["dataset"] == {key: revised[key] for key in ("id", "digest", "body")}
            and app["problem"] == {key: problem[key] for key in ("id", "digest", "body")}
            and app["dataset_origin"] == revised["body"]["origin"]
            and packet["history"]["id"] == scope["source_artifact_id"] == ref["id"]
            and packet["history"]["sha256"] == ref["sha256"] and packet["history"]["anchors"] == expected_anchor)
    except (KeyError, IndexError, TypeError, ValueError):
        pass
    return {"id": f"links:{label}:native_followup_binding", "passed": bool(passed),
            "detail": "native operation, full proposal, materialized revision and original design scope match saved authenticated records"}


def _replay_checks(observation: dict, evidence_dir: str, records: dict, science_python: str | None,
                   package_dir: str | None) -> list[dict]:
    out = []
    for item in observation.get("native_artifacts") or []:
        try:
            data, _ = _load(evidence_dir, item["path"])
        except OSError:
            out.append({"id": f"replay:{item.get('artifact_id')}", "passed": False, "detail": "packet file missing"})
            continue
        digest = hashlib.sha256(data).hexdigest()
        reference = item.get("reference") or {}
        out.append({"id": f"bytes:{item.get('artifact_id')}", "passed": digest == reference.get("sha256")
                    and len(data) == reference.get("byte_size"), "detail": "saved packet matches its reference"})
        anchor_records = [records[name] for name in item.get("anchor_records", []) if name in records]
        anchors = native.anchors_from_record(*anchor_records)
        application = native.classify(data).get("profile") == "application_bundle"
        full = next((r.get("anchor") for r in anchor_records if isinstance(r.get("anchor"), dict)), None)
        if not science_python or not package_dir:
            out.append({"id": f"replay:{item.get('artifact_id')}", "passed": False,
                        "detail": "no replay interpreter available to the qualifier"})
            continue
        if (application and not full) or (not application and (not anchors.get("problem_digest")
                                                                or not anchors.get("suggestion_digest"))):
            out.append({"id": f"replay:{item.get('artifact_id')}", "passed": False,
                        "detail": "anchors are not present in the saved authenticated records"})
            continue
        report = native.replay(science_python, package_dir, data, anchors,
                               application_anchor=full if application else None)
        body = report.get("report") or {}
        for name, evidence in records.items():
            if not name.endswith("-evidence-baseline"):
                continue
            result = (evidence.get("body") or {}).get("result") or {}
            if not any(ref.get("id") == item.get("artifact_id") for ref in result.get("artifacts") or []):
                continue
            label = name.removesuffix("-evidence-baseline")
            if not ((records.get(f"{label}-plan") or {}).get("body") or {}).get("followup"):
                continue
            out.append(followup_native_binding(label, json.loads(data), records))
            out.append({"id": f"replay:{item.get('artifact_id')}:published_followup_matches", "passed":
                (body.get("outcome") or {}).get("scientific_outcome") == result.get("scientific_outcome")
                and {row.get("candidate_id"): row.get("parameters") for row in body.get("candidate_results") or []}
                    == {row.get("id"): row.get("parameter_vector") for row in result.get("candidates") or []},
                "detail": "fresh replay outcome and exact vectors match the published fixed-candidate result"})
        bound = body.get("integrity") == "passed" and body.get("expected_binding") == "matches"
        if item.get("expect_checked", True):
            ok, what = report["status"] == "passed" and bound, f"fresh replay {report['status']}"
        else:  # numerical-only packet: no checked evidence exists to replay; bytes must still bind
            ok, what = bound, f"integrity/binding of a numerical-only packet ({body.get('reason_code')})"
        out.append({"id": f"replay:{item.get('artifact_id')}", "passed": ok, "detail": what})
    return out


def zero_dispatch(observation: dict) -> tuple[bool, str]:
    dispatch = observation.get("external_dispatch") or {}
    if dispatch.get("verified") is not True:
        return False, "external model dispatch was not verified by the guard (unknown is not zero)"
    if dispatch.get("egress_attempts") != 0 or dispatch.get("client_constructions") != 0:
        return False, (f"external model attempt: {dispatch.get('egress_attempts')} egress, "
                       f"{dispatch.get('client_constructions')} client construction(s)")
    if observation.get("provider_requests") not in (0,):
        return False, f"provider_requests {observation.get('provider_requests')!r} is not a verified zero"
    return True, "guard active in API and worker; zero external model attempts"


def qualify(observation: dict, *, evidence_dir: str | None, evidence_class: str, science_python: str | None,
            package_dir: str | None) -> dict:
    if evidence_class not in EVIDENCE_CLASSES:
        raise ValueError(f"unknown evidence class {evidence_class!r}")
    result = {"evidence_class": evidence_class, "qualifier_checks": []}
    if evidence_class not in EXECUTED:
        return {**result, "status": "failed",
                "reason": "imported observation: claims are never qualification; rerun the lane with --subject "
                          "http-launch so the runner executes and corroborates the acceptance itself"}
    if not evidence_dir or not os.path.isdir(evidence_dir):
        return {**result, "status": "failed", "reason": "no evidence directory was produced"}
    ok, detail = zero_dispatch(observation)
    qualifier = [{"id": "zero_external_model_dispatch", "passed": ok, "detail": detail}]
    qualifier += _file_checks(observation, evidence_dir)
    records = _records(observation, evidence_dir)
    qualifier += _link_checks(records)
    qualifier += _replay_checks(observation, evidence_dir, records, science_python, package_dir)
    result["qualifier_checks"] = qualifier
    failed_q = [c for c in qualifier if not c["passed"]]
    checks = observation.get("checks")
    if not isinstance(checks, list) or not checks:
        return {**result, "status": "failed", "reason": "observation carries no executed checks"}
    required = [c for c in checks if isinstance(c, dict) and c.get("level", "required") == "required"]
    failed = [c for c in required if c.get("outcome") == "failed"]
    blocked = [c for c in required if c.get("outcome") in ("blocked", "not_observed")]
    if failed_q or failed:
        names = [c["id"] for c in failed_q] + [c["id"] for c in failed]
        return {**result, "status": "failed", "reason": "failed: " + ", ".join(names[:12])}
    if blocked:
        reasons = "; ".join(f"{c['id']} ({c.get('finding') or 'prerequisite'}): {c.get('detail', '')[:120]}"
                            for c in blocked[:4])
        return {**result, "status": "unrun", "reason": "blocked: " + reasons}
    if not required:
        return {**result, "status": "unrun", "reason": "blocked: no required check could be evaluated"}
    return {**result, "status": "passed", "reason": None}
