"""Real HTTP scenarios for the offline real-science lane.

Each scenario drives the published API as the synthetic authenticated reviewer:
workspace -> exact dataset -> problem -> plan preview -> human approval -> start ->
bounded polling -> candidates -> separately previewed/approved design -> raw
artifact download -> fresh native replay. Nothing is inserted directly into the
database and no test-only route is used.

Every check has one outcome:

* ``passed`` / ``failed`` - the predicate was evaluated on actual responses;
* ``blocked``  - a prerequisite owned by another workstream is absent (the reason
  names it); never counted as a pass;
* ``not_observed`` - the run did not reach the state the check needs (for example
  a computation finished before an interruption point); never counted as a pass.

Scientific predicates are checked, not optimizer floats. Exact comparisons use
``fractions.Fraction`` on the application's rational strings.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from fractions import Fraction

from . import kinetics, native
from .http_client import ApiClient, ApiFailure

TERMINAL = {"completed", "cancelled", "failed", "interrupted"}
REQUIRED = "required"
INFO = "informational"


def F(text) -> Fraction:
    numerator, _, denominator = str(text).partition("/")
    return Fraction(int(numerator), int(denominator or 1))


class Checks:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, check_id: str, outcome: str, detail: str = "", *, level: str = REQUIRED, finding: str | None = None):
        assert outcome in ("passed", "failed", "blocked", "not_observed", "not_applicable"), outcome
        item = {"id": check_id, "outcome": outcome, "level": level, "detail": detail[:600]}
        if finding:
            item["finding"] = finding
        self.items.append(item)
        return outcome == "passed"

    def expect(self, check_id: str, condition: bool, detail: str = "", **kwargs) -> bool:
        return self.add(check_id, "passed" if condition else "failed", detail, **kwargs)

    def status(self) -> str:
        required = [c for c in self.items if c["level"] == REQUIRED]
        if any(c["outcome"] == "failed" for c in required):
            return "failed"
        if any(c["outcome"] in ("blocked", "not_observed") for c in required):
            return "blocked"
        return "passed" if required else "blocked"


class Flow:
    """Shared context for one lane run against one launched stack."""

    def __init__(self, client: ApiClient, other: ApiClient | None, evidence_dir: str, *, science_python: str | None,
                 package_dir: str, guard_log: str | None = None, poll_timeout: float = 240.0):
        self.client, self.other = client, other
        self.evidence_dir = evidence_dir
        self.science_python, self.package_dir = science_python, package_dir
        self.guard_log = guard_log
        self.poll_timeout = poll_timeout
        self.saved: dict[str, dict] = {}
        self.cache: dict[str, dict] = {}
        self.jobs_executed: set[str] = set()
        self.workspaces: list[str] = []
        self.native_saved: list[dict] = []
        self.other_bytes: dict[str, dict] = {}
        self._openapi = None
        self.begin_entry(evidence_dir)

    def begin_entry(self, evidence_dir: str) -> None:
        """Each scheduled entry writes its own evidence directory; cached run context persists."""
        self.evidence_dir = evidence_dir
        self.saved, self.native_saved, self.other_bytes = {}, [], {}
        self.client.exchanges.clear()
        os.makedirs(os.path.join(evidence_dir, "records"), exist_ok=True)
        os.makedirs(os.path.join(evidence_dir, "artifacts"), exist_ok=True)

    def evidence_index(self) -> dict:
        index = {name: {"path": item["path"], "sha256": item["sha256"]} for name, item in self.saved.items()}
        for item in self.native_saved:
            index[f"native:{item['artifact_id']}"] = {"path": item["path"], "sha256": item["sha256"]}
        for name, item in self.other_bytes.items():
            index[name] = {"path": item["path"], "sha256": item["sha256"]}
        return index

    # -- evidence capture --------------------------------------------------
    def save_record(self, name: str, record) -> dict:
        data = json.dumps(record, sort_keys=True, ensure_ascii=False).encode("utf-8")
        rel = os.path.join("records", f"{name}.json")
        with open(os.path.join(self.evidence_dir, rel), "wb") as handle:
            handle.write(data)
        entry = {"path": rel, "sha256": hashlib.sha256(data).hexdigest(), "id": (record or {}).get("id")
                 if isinstance(record, dict) else None}
        self.saved[name] = entry
        return entry

    def save_bytes(self, name: str, data: bytes) -> dict:
        rel = os.path.join("artifacts", name)
        with open(os.path.join(self.evidence_dir, rel), "wb") as handle:
            handle.write(data)
        return {"path": rel, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}

    def openapi(self) -> dict:
        if self._openapi is None:
            response = self.client.raw("GET", "/openapi.json", api=False, authenticated=False)
            self._openapi = response.json() if response.status == 200 else {}
        return self._openapi

    def schema_properties(self, name: str) -> tuple[set[str], set[str]]:
        schema = ((self.openapi().get("components") or {}).get("schemas") or {}).get(name) or {}
        return set((schema.get("properties") or {}).keys()), set(schema.get("required") or [])

    # -- polling -----------------------------------------------------------
    def poll(self, path: str, timeout: float | None = None) -> dict:
        deadline = time.monotonic() + (timeout or self.poll_timeout)
        last = None
        while time.monotonic() < deadline:
            last = self.client.get(path)
            if last.get("state") in TERMINAL:
                return last
            time.sleep(0.4)
        return last or {}

    # -- baseline ----------------------------------------------------------
    def baseline(self, packet: dict, *, label: str, workspace_id: str | None = None,
                 dataset_override: dict | None = None) -> dict:
        """Create inputs, preview/approve/start one manual plan and wait for its result."""
        out: dict = {"label": label, "timings_ms": {}}
        t0 = time.monotonic()
        if workspace_id is None:
            workspace = self.client.post("/workspaces", {"name": f"Dr. Bean evaluation {label}"}, label="workspace")
            workspace_id = workspace["id"]
            self.workspaces.append(workspace_id)
        out["workspace_id"] = workspace_id
        dataset_body = dataset_override or packet["dataset"]
        dataset = self.client.post(f"/workspaces/{workspace_id}/datasets", dataset_body, label=f"{label}-dataset")
        problem_body = {**packet["problem"], "dataset_id": dataset["id"], "dataset_digest": dataset["digest"]}
        problem = self.client.post(f"/workspaces/{workspace_id}/problems", problem_body, label=f"{label}-problem")
        plan_body = {"schema_version": "DB-SC-1", "problem_id": problem["id"], "problem_digest": problem["digest"],
                     "dataset_id": dataset["id"],
                     "scenarios": [{"id": "baseline", "problem_id": problem["id"], "problem_digest": problem["digest"],
                                    "kind": "baseline", "label": "Reviewed baseline investigation"}]}
        props, required = self.schema_properties("PlanBody")
        unknown_required = sorted(required - set(plan_body) - {"permitted_tools", "budget", "provider_disclosure",
                                                               "parent_plan_id"})
        if unknown_required:
            out["blocked"] = f"PlanBody now requires fields this harness does not author: {unknown_required}"
            return out
        plan = self.client.post(f"/workspaces/{workspace_id}/plans",
                                {"expected_current_revision_id": problem["id"], "plan": plan_body},
                                label=f"{label}-plan")
        approval = self.client.post(f"/plans/{plan['id']}/approvals",
                                    {"expected_plan_digest": plan["digest"],
                                     "expected_current_revision_id": problem["id"], "accepted": True},
                                    label=f"{label}-approval")
        out["timings_ms"]["inputs_to_approval"] = round((time.monotonic() - t0) * 1000, 1)
        start = {"approval_id": approval["id"], "expected_plan_digest": plan["digest"]}
        run = self.client.post(f"/plans/{plan['id']}/runs", start, label=f"{label}-start")
        t1 = time.monotonic()
        finished = self.poll(f"/runs/{run['id']}")
        out["timings_ms"]["start_to_terminal"] = round((time.monotonic() - t1) * 1000, 1)
        self.jobs_executed.add(run["id"])
        evidence = []
        for child in finished.get("scenarios", []):
            if child.get("result_id"):
                record = self.client.get(f"/records/{child['result_id']}")
                evidence.append(record)
                self.save_record(f"{label}-evidence-{child['scenario_id']}", record)
        summary = self.client.get(f"/records/{finished['result_id']}") if finished.get("result_id") else None
        for name, record in (("dataset", dataset), ("problem", problem), ("plan", plan), ("approval", approval),
                             ("run", finished)):
            self.save_record(f"{label}-{name}", record)
        if summary:
            self.save_record(f"{label}-run-summary", summary)
        out.update(dataset=dataset, problem=problem, plan=plan, approval=approval, run=finished,
                   evidence=evidence, summary=summary, start_request=start)
        return out

    # -- design ------------------------------------------------------------
    def design(self, base: dict, pair: list[dict], *, feasible_times: list[str], allowance: str, label: str,
               review: dict) -> dict:
        run, problem = base["run"], base["problem"]
        request = {"schema_version": "DB-SC-1", "historical_run_id": run["id"], "scenario_id": "baseline",
                   "problem_id": problem["id"], "problem_digest": problem["digest"],
                   "candidate_ids": [c["id"] for c in pair],
                   "candidate_vectors": [c["parameter_vector"] for c in pair],
                   "observable": "concentration", "feasible_times": feasible_times,
                   "future_hard_allowance": allowance,
                   "allow_construction": bool(review.get("allow_construction")),
                   "allow_continuation": bool(review.get("allow_continuation"))}
        props, required = self.schema_properties("DesignRequestBody")
        optional_map = {"maximum_horizon": ("max_horizon", "maximum_horizon", "horizon"),
                        "allowance_origin": ("future_allowance_origin", "allowance_origin"),
                        "allowance_description": ("future_allowance_description", "allowance_description"),
                        "requested_tier": ("requested_tier", "scientific_tier")}
        for key, names in optional_map.items():
            for name in names:
                if name in props and key in review:
                    request[name] = review[key]
                    break
        if "requested_tier" in [n for n in props] and "requested_tier" not in request:
            request["requested_tier"] = "checked_pair_separation"
        missing = sorted(required - set(request) - {"budget", "schema_version", "observable"})
        if missing:
            return {"blocked": f"DesignRequestBody requires fields the reviewed packet does not define: {missing}",
                    "request": request}
        plan = self.client.post(f"/runs/{run['id']}/design-proposals", request, label=f"{label}-design-plan")
        approval = self.client.post(f"/design-plans/{plan['id']}/approvals",
                                    {"expected_plan_digest": plan["digest"],
                                     "expected_current_revision_id": problem["id"], "accepted": True},
                                    label=f"{label}-design-approval")
        job = self.client.post(f"/design-plans/{plan['id']}/jobs",
                               {"approval_id": approval["id"], "expected_plan_digest": plan["digest"]},
                               label=f"{label}-design-start")
        t0 = time.monotonic()
        finished = self.poll(f"/design-jobs/{job['id']}")
        self.jobs_executed.add(job["id"])
        suggestion = self.client.get(f"/records/{finished['result_id']}") if finished.get("result_id") else None
        for name, record in (("design-plan", plan), ("design-approval", approval), ("design-job", finished)):
            self.save_record(f"{label}-{name}", record)
        if suggestion:
            self.save_record(f"{label}-suggestion", suggestion)
        return {"request": request, "plan": plan, "approval": approval, "job": finished, "suggestion": suggestion,
                "timings_ms": {"start_to_terminal": round((time.monotonic() - t0) * 1000, 1)}}

    # -- artifacts ---------------------------------------------------------
    def download(self, reference: dict, label: str) -> dict:
        """GET the referenced bytes. Owner 2 owns the final byte route; both shapes are tried."""
        attempts = []
        for path in (f"/artifacts/{reference['id']}", f"/artifacts/{reference['id']}/content"):
            response = self.client.raw("GET", path)
            attempts.append({"route": path.replace(reference["id"], "{id}"), "status": response.status})
            if response.status == 200:
                kind = native.classify(response.data)
                saved = self.save_bytes(f"{label}-{reference['id']}.bin", response.data)
                result = {"reference": reference, "route_attempts": attempts, "classification": kind,
                          "saved": saved, "checks": native.validate_download(reference, response.data,
                                                                              response.headers)}
                if kind["class"] == "native_packet":
                    result["data"] = response.data
                    self.native_saved.append({"artifact_id": reference["id"], "path": saved["path"],
                                              "sha256": saved["sha256"], "reference": reference,
                                              "label": label, "anchor_records": []})
                    return result
                self.other_bytes[f"download:{label}:{reference['id']}"] = saved
                last = result
        else:
            last = None
        return last or {"reference": reference, "route_attempts": attempts, "classification": {"class": "unavailable"}}

    def replay_checks(self, checks: Checks, downloads: list[dict], anchors: dict, prefix: str,
                      anchor_records: list[str] | None = None) -> list[dict]:
        reports = []
        natives = [d for d in downloads if d["classification"]["class"] == "native_packet"]
        for item in self.native_saved:  # the qualifier re-extracts anchors from exactly these saved records
            if any(d["saved"]["path"] == item["path"] for d in natives):
                item["anchor_records"] = list(anchor_records or [])
        if not downloads:
            checks.add(f"{prefix}_native_bytes_downloadable", "blocked",
                       "the result references no artifacts to download", finding="F-NATIVE-BYTES")
            return reports
        if not natives:
            classes = sorted({d["classification"]["class"] for d in downloads})
            checks.add(f"{prefix}_native_bytes_downloadable", "blocked",
                       f"referenced artifacts are not downloadable as native packets ({classes}); routes tried "
                       f"{[a for d in downloads for a in d['route_attempts']]}", finding="F-NATIVE-BYTES")
            return reports
        for item in natives:
            for check in item["checks"]:
                checks.expect(f"{prefix}_{check['id']}", check["passed"], check["detail"])
        if not self.science_python:
            checks.add(f"{prefix}_fresh_native_replay", "blocked", "no CPython 3.11 replay interpreter configured")
            return reports
        if not anchors.get("problem_digest") or not anchors.get("suggestion_digest"):
            checks.add(f"{prefix}_anchor_from_authenticated_record", "blocked",
                       f"authenticated records expose anchors {sorted(anchors)}; replay needs problem and "
                       "suggestion anchors obtained from the expected-run record, not from the bundle",
                       finding="F-ANCHOR-RECORD")
            return reports
        checks.add(f"{prefix}_anchor_from_authenticated_record", "passed", f"anchors {sorted(anchors)}")
        for item in natives:
            report = native.replay(self.science_python, self.package_dir, item["data"], anchors,
                                   guard_log=self.guard_log)
            reports.append({"artifact_id": item["reference"]["id"], **report})
            body = report.get("report") or {}
            checks.expect(f"{prefix}_fresh_native_replay", report["status"] == "passed"
                          and body.get("integrity") == "passed" and body.get("expected_binding") == "matches",
                          f"status {report['status']}, integrity {body.get('integrity')}, binding "
                          f"{body.get('expected_binding')}, error {(report.get('error') or {}).get('code')}")
            tampered = native.replay(self.science_python, self.package_dir, native.flip_one_byte(item["data"]),
                                     anchors, guard_log=self.guard_log)
            checks.expect(f"{prefix}_altered_byte_rejected", tampered["status"] != "passed",
                          f"tampered replay status {tampered['status']} "
                          f"({(tampered.get('error') or {}).get('code')})")
            wrong = native.replay(self.science_python, self.package_dir, item["data"],
                                  {**anchors, "problem_digest": native.wrong_anchor(anchors["problem_digest"])},
                                  guard_log=self.guard_log)
            checks.expect(f"{prefix}_wrong_problem_anchor_rejected", wrong["status"] != "passed",
                          f"wrong-anchor replay status {wrong['status']} ({(wrong.get('error') or {}).get('code')})")
        return reports


# ---------------------------------------------------------------------------
# Scenario predicates


def result_of(evidence_record: dict) -> dict:
    return ((evidence_record or {}).get("body") or {}).get("result") or {}


def classify_candidates(result: dict, target: dict) -> tuple[list[dict], list[dict]]:
    inside, outside = [], []
    for candidate in result.get("candidates") or []:
        vector = candidate.get("parameter_vector") or {}
        try:
            out = kinetics.outside_closed_claim(F(vector["ke"]), F(target["lower"]), F(target["upper"]))
        except (KeyError, ValueError, ZeroDivisionError):
            continue
        (outside if out else inside).append(candidate)
    return inside, outside


def check_baseline(checks: Checks, base: dict, packet: dict, *, known_positive: bool) -> dict:
    """Binding and outcome predicates over one actual baseline run."""
    info: dict = {}
    if base.get("blocked"):
        checks.add("baseline_created", "blocked", base["blocked"], finding="F-SCHEMA-DRIFT")
        return info
    run = base["run"]
    checks.expect("baseline_run_terminal", run.get("state") in TERMINAL, f"state {run.get('state')}")
    checks.expect("single_baseline_reservation",
                  sum(1 for s in run.get("scenarios", []) if s.get("scenario_id") == "baseline") == 1,
                  f"{len(run.get('scenarios', []))} scenario rows")
    if run.get("state") != "completed" or not base["evidence"]:
        checks.add("baseline_completed_with_evidence", "failed",
                   f"run state {run.get('state')}, error {run.get('error_code')}; scenario reasons "
                   f"{[s.get('reason_code') for s in run.get('scenarios', [])]}", finding=_worker_finding(run))
        return info
    checks.add("baseline_completed_with_evidence", "passed", f"{len(base['evidence'])} evidence record(s)")
    evidence = base["evidence"][0]
    result = result_of(evidence)
    problem = base["problem"]
    info["result"] = result
    body = evidence.get("body") or {}
    checks.expect("evidence_binds_run_and_problem",
                  body.get("run_id") == run["id"] and body.get("problem_id") == problem["id"]
                  and body.get("expected_problem_digest") == problem["digest"]
                  and result.get("problem_id") == problem["id"]
                  and result.get("problem_digest") in (None, problem["digest"]),
                  f"evidence run {body.get('run_id')}, problem {body.get('problem_id')}")
    candidates = result.get("candidates") or []
    checks.expect("candidates_bind_reviewed_problem",
                  all(c.get("problem_id") == problem["id"] and c.get("problem_digest") == problem["digest"]
                      for c in candidates),
                  f"{len(candidates)} candidate(s)")
    ids = [c.get("id") for c in candidates]
    vectors = [json.dumps(c.get("parameter_vector"), sort_keys=True) for c in candidates]
    checks.expect("candidate_ids_and_vectors_distinct", len(set(ids)) == len(ids) and len(set(vectors)) == len(vectors),
                  f"ids {ids}")
    outcome, verification = result.get("scientific_outcome"), result.get("verification")
    info.update(outcome=outcome, verification=verification)
    if outcome == "unsupported" or (result.get("reason_code") or "").endswith("not_installed"):
        checks.add("real_scientific_adapter_selected", "failed",
                   f"ordinary startup returned scientific_outcome={outcome}, reason {result.get('reason_code')}",
                   finding="F-ADAPTER-SELECTION")
        return info
    checks.add("real_scientific_adapter_selected", "passed", f"outcome {outcome}, verification {verification}")
    if outcome == "certified_counterexample":
        checks.expect("certified_requires_valid_matching_evidence",
                      verification == "valid" and result.get("expected_binding") == "matches" and bool(candidates),
                      f"verification {verification}, binding {result.get('expected_binding')}")
    inside, outside = classify_candidates(result, packet["problem"]["target"])
    info.update(inside=inside, outside=outside)
    oracle = {c["id"]: kinetics.history_verdict(c["parameter_vector"], base["dataset"]["body"]["rows"])
              for c in candidates if c.get("parameter_vector")}
    info["independent_oracle_history"] = oracle
    valid_outside = [c for c in outside if c.get("verification") == "valid"]
    if known_positive:
        checks.expect("fresh_outside_candidate_compatible",
                      bool(valid_outside) and outcome == "certified_counterexample",
                      f"{len(outside)} outside candidate(s), {len(valid_outside)} freshly checked valid; "
                      f"outcome {outcome}", finding=None if valid_outside else "F-HERO-NO-WITNESS")
    for candidate in valid_outside:
        checks.expect(f"independent_oracle_agrees_{candidate['id']}", oracle.get(candidate["id"]) != "excluded",
                      f"independent decimal oracle says {oracle.get(candidate['id'])} for a checker-valid candidate",
                      level=INFO)
    if outcome == "no_counterexample_found":
        checks.expect("no_counterexample_is_not_proof",
                      verification != "valid" or not any("prove" in str(v).lower() for v in result.values()),
                      "a bounded search miss must not be reported as proof of the interval")
    return info


def _worker_finding(run: dict) -> str | None:
    codes = {run.get("error_code"), *[s.get("reason_code") for s in run.get("scenarios", [])]}
    if "scientific_worker_failed" in codes:
        return "F-PLATFORM-RLIMIT"
    if "worker_failed" in codes:
        return "F-WORKER"
    return None


def choose_pair(info: dict) -> list[dict] | None:
    """Reference (inside) first when one exists, then an outside witness; never invent or duplicate."""
    inside = [c for c in info.get("inside", []) if c.get("verification") == "valid"] or info.get("inside", [])
    outside = [c for c in info.get("outside", []) if c.get("verification") == "valid"] or info.get("outside", [])
    if inside and outside:
        return [inside[0], outside[0]]
    pool = outside or inside
    return pool[:2] if len(pool) >= 2 else None


def check_design(checks: Checks, design: dict, pair: list[dict], base: dict, *, prefix: str = "design") -> dict:
    if design.get("blocked"):
        checks.add(f"{prefix}_created", "blocked", design["blocked"], finding="F-SCHEMA-DRIFT")
        return {}
    request, job, suggestion = design["request"], design["job"], design.get("suggestion")
    checks.expect(f"{prefix}_plan_binds_request", design["plan"]["body"]["request"]["candidate_ids"]
                  == request["candidate_ids"] and design["plan"]["body"]["request"]["feasible_times"]
                  == request["feasible_times"], "persisted design plan matches the reviewed request")
    checks.expect(f"{prefix}_separate_approval_scope", design["approval"].get("scope") == "design"
                  and design["approval"]["id"] != base["approval"]["id"],
                  f"approval scope {design['approval'].get('scope')}")
    if job.get("state") != "completed" or not suggestion:
        checks.add(f"{prefix}_completed", "failed", f"design job {job.get('state')} error {job.get('error_code')}",
                   finding=_worker_finding(job) or "F-DESIGN-JOB")
        return {}
    checks.add(f"{prefix}_completed", "passed")
    result = suggestion.get("body") or {}
    times = [o.get("time") for o in result.get("options", [])]
    checks.expect(f"{prefix}_every_approved_grid_time_retained", times == request["feasible_times"],
                  f"options {times}, approved {request['feasible_times']}")
    checks.expect(f"{prefix}_uses_same_candidates", (result.get("candidate_ids") or request["candidate_ids"])
                  == request["candidate_ids"] and request["candidate_ids"] == [c["id"] for c in pair],
                  f"result ids {result.get('candidate_ids')}")
    tier = result.get("design_tier")
    selected = next((o for o in result.get("options", []) if o.get("time") == result.get("selected_time")), None)
    info = {"tier": tier, "selected_time": result.get("selected_time"), "result": result}
    if tier == "checked_pair_separation":
        record = result.get("verification_record") or {}
        ok = (selected is not None and selected.get("state") == "evaluated" and selected.get("exact_margin")
              and F(selected["exact_margin"]) > 0 and result.get("verification") == "valid"
              and result.get("replay") == "passed" and record.get("expected_binding") == "matches"
              and record.get("expected_problem_digest") == base["problem"]["digest"])
        checks.expect(f"{prefix}_selected_checked_margin_strictly_positive", bool(ok),
                      f"selected {result.get('selected_time')} margin {selected and selected.get('exact_margin')}",
                      finding=None if ok else "F-FALSE-CHECKED")
    elif tier == "no_separation_established":
        checks.add(f"{prefix}_selected_checked_margin_strictly_positive", "not_applicable",
                   "no separation established on the reviewed grid; nothing was selected", level=INFO)
        checks.expect(f"{prefix}_no_selection_without_separation", result.get("selected_time") is None,
                      f"selected_time {result.get('selected_time')}")
    else:
        checks.add(f"{prefix}_checked_tier", "failed" if tier not in ("numerical_guidance", "unavailable") else
                   "blocked", f"design tier {tier}, reason {result.get('reason_code')}", finding="F-DESIGN-TIER")
    return info


def check_original_unchanged(checks: Checks, flow: Flow, base: dict, check_id: str) -> None:
    """Re-fetch the original records; their bytes must be identical."""
    changed = []
    for name, record in (("run", base["run"]), ("evidence", base["evidence"][0] if base.get("evidence") else None),
                         ("dataset", base["dataset"]), ("problem", base["problem"])):
        if not record:
            continue
        path = f"/runs/{record['id']}" if name == "run" else f"/records/{record['id']}"
        again = flow.client.get(path)
        if json.dumps(again, sort_keys=True) != json.dumps(record, sort_keys=True):
            changed.append(name)
    checks.expect(check_id, not changed, f"changed after later work: {changed}" if changed else
                  "run, evidence, dataset and problem re-fetched byte-identical")


# ---------------------------------------------------------------------------
# Scenarios


def upload_source(flow: Flow, checks: Checks, workspace_id: str, path: str, expected_sha: str | None) -> str | None:
    """Admit the synthetic source image through the real decoder subprocess; return its asset id."""
    with open(path, "rb") as handle:
        raw = handle.read()
    response = flow.client.raw("POST", f"/workspaces/{workspace_id}/source-assets?origin=synthetic&retention=retain",
                               body=raw, content_type="image/png", key=flow.client.new_key("source"))
    if response.status != 201:
        code = response.json().get("code") if response.data else None
        checks.add("source_image_admitted", "failed", f"valid synthetic PNG refused: {response.status} {code}",
                   finding="F-PLATFORM-RLIMIT" if code == "malformed_image" else "F-SOURCE-ADMISSION")
        return None
    record = response.json()
    flow.save_record("hero-source-asset", record)
    body = record.get("body") or {}
    checks.expect("source_image_admitted", body.get("sha256") == (expected_sha or body.get("sha256"))
                  and "blob_key" not in body, f"{body.get('width')}x{body.get('height')} {body.get('observed_media_type')}")
    return record.get("id")


def scenario_hero(flow: Flow, packet: dict) -> dict:
    checks = Checks()
    workspace = flow.client.post("/workspaces", {"name": "Dr. Bean evaluation hero"}, label="hero-workspace")
    flow.workspaces.append(workspace["id"])
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    source_id = upload_source(flow, checks, workspace["id"], os.path.join(repo, "fixtures", "intake", "clean.png"),
                              "6363da39c1a7a86e45e5a9d5f17aa87006130cc75c61844f4902be0f118c0b06")
    dataset = packet["dataset"]
    if source_id:
        dataset = {**dataset, "rows": [{**row, "source_asset_id": source_id} for row in dataset["rows"]]}
    base = flow.baseline(packet, label="hero", workspace_id=workspace["id"], dataset_override=dataset)
    flow.cache["hero"] = base
    info = check_baseline(checks, base, packet, known_positive=packet["designation"]["known_positive"])
    flow.cache["hero_info"] = info
    observation = {"records": _ids(base), "baseline": _summary(info)}
    evidence = base.get("evidence") or []
    downloads = [flow.download(ref, "hero-baseline") for ref in (result_of(evidence[0]).get("artifacts") or [])] \
        if evidence else []
    anchors = native.anchors_from_record(*evidence)
    if info.get("result") and info.get("outcome") not in ("unsupported", None):
        observation["baseline_replay"] = flow.replay_checks(checks, downloads, anchors, "baseline",
                                                            ["hero-evidence-baseline"])
    pair = choose_pair(info)
    observation["pair"] = [{"id": c["id"], "parameter_vector": c["parameter_vector"]} for c in pair or []]
    if not pair:
        checks.add("design_pair_available", "blocked" if not info.get("result") else "failed",
                   f"{len(info.get('inside', []))} inside and {len(info.get('outside', []))} outside candidate(s); "
                   "design needs two distinct fixed candidates from this run", finding="F-HERO-NO-PAIR")
        return {"checks": checks, "observation": observation, "base": base}
    review = packet["design_review"]
    design = flow.design(base, pair, feasible_times=review["feasible_times"],
                         allowance=review["future_hard_allowance"], label="hero", review=review)
    flow.cache["hero_design"] = design
    design_info = check_design(checks, design, pair, base)
    observation["design"] = {k: design_info.get(k) for k in ("tier", "selected_time")}
    suggestion = design.get("suggestion")
    if suggestion:
        refs = (suggestion.get("body") or {}).get("artifacts") or []
        downloads = [flow.download(ref, "hero-design") for ref in refs]
        anchors = native.anchors_from_record(suggestion, design.get("plan") or {}, *evidence)
        observation["design_replay"] = flow.replay_checks(checks, downloads, anchors, "design_packet",
                                                          ["hero-suggestion", "hero-design-plan",
                                                           "hero-evidence-baseline"])
        report = flow.client.post(f"/runs/{base['run']['id']}/reports", label="hero-report")
        download = flow.client.raw("GET", f"/reports/{report['id']}/download")
        kind = native.classify(download.data)
        checks.add("report_download_is_not_a_native_packet",
                   "passed" if kind["class"] != "native_packet" else "failed",
                   f"report download classified {kind['class']}: an entity JSON with references does not "
                   "replace the native packet", level=INFO)
    return {"checks": checks, "observation": observation, "base": base}


def scenario_changed_input(flow: Flow, hero: dict, changed: dict) -> dict:
    checks = Checks()
    original = flow.cache.get("hero")
    if not original or original.get("blocked"):
        original = flow.baseline(hero, label="original")
        flow.cache["hero"] = original
    workspace = original["workspace_id"]
    revised = {**changed["dataset"], "experiment_id": original["dataset"]["body"]["experiment_id"],
               "parent_id": original["dataset"]["id"]}
    base = flow.baseline(changed, label="changed", workspace_id=workspace, dataset_override=revised)
    info = check_baseline(checks, base, changed, known_positive=False)
    if base.get("blocked"):
        return {"checks": checks, "observation": {}}
    fresh = {name: (original[name]["id"] != base[name]["id"]) for name in ("dataset", "problem", "plan", "approval")}
    fresh["run"] = original["run"]["id"] != base["run"]["id"]
    fresh["digests"] = (original["dataset"]["digest"] != base["dataset"]["digest"]
                        and original["problem"]["digest"] != base["problem"]["digest"]
                        and original["plan"]["digest"] != base["plan"]["digest"])
    checks.expect("fresh_identities_and_computation", all(fresh.values()), json.dumps(fresh))
    checks.expect("revision_records_parent", base["dataset"].get("parent_id") == original["dataset"]["id"],
                  f"parent {base['dataset'].get('parent_id')}")
    check_original_unchanged(checks, flow, original, "original_result_unchanged")
    if info.get("result") and base.get("evidence") and original.get("evidence"):
        checks.expect("changed_evidence_binds_new_problem",
                      result_of(base["evidence"][0]).get("problem_id") == base["problem"]["id"]
                      and result_of(original["evidence"][0]).get("problem_id") == original["problem"]["id"],
                      "each result binds its own reviewed problem")
    observation = {"records": _ids(base), "original_records": _ids(original), "baseline": _summary(info),
                   "fresh": fresh}
    return {"checks": checks, "observation": observation}


def scenario_retry_concurrent(flow: Flow, packet: dict, *, threads: int = 8) -> dict:
    """Concurrent and retried starts of one approved plan create exactly one run."""
    checks = Checks()
    workspace = flow.client.post("/workspaces", {"name": "Dr. Bean evaluation concurrency"}, label="ws")["id"]
    flow.workspaces.append(workspace)
    dataset = flow.client.post(f"/workspaces/{workspace}/datasets", packet["dataset"], label="c-dataset")
    problem = flow.client.post(f"/workspaces/{workspace}/problems",
                               {**packet["problem"], "dataset_id": dataset["id"], "dataset_digest": dataset["digest"]},
                               label="c-problem")
    plan = flow.client.post(f"/workspaces/{workspace}/plans", {"expected_current_revision_id": problem["id"], "plan": {
        "schema_version": "DB-SC-1", "problem_id": problem["id"], "problem_digest": problem["digest"],
        "dataset_id": dataset["id"], "scenarios": [{"id": "baseline", "problem_id": problem["id"],
                                                     "problem_digest": problem["digest"], "kind": "baseline",
                                                     "label": "Concurrency control baseline"}]}}, label="c-plan")
    approval = flow.client.post(f"/plans/{plan['id']}/approvals", {"expected_plan_digest": plan["digest"],
                                "expected_current_revision_id": problem["id"], "accepted": True}, label="c-approve")
    body = {"approval_id": approval["id"], "expected_plan_digest": plan["digest"]}
    results, barrier = [], threading.Barrier(threads)

    def start(index: int):
        client = ApiClient(flow.client.base_url, flow.client._token, key_prefix=f"{flow.client.key_prefix}-t{index}")
        barrier.wait()
        try:
            results.append(("ok", client.post(f"/plans/{plan['id']}/runs", body, key=f"concurrent-{index}")["id"]))
        except ApiFailure as error:
            results.append(("error", error.code or error.status))
        flow.client.exchanges.extend(client.exchanges)

    workers = [threading.Thread(target=start, args=(i,)) for i in range(threads)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(60)
    retry = flow.client.post(f"/plans/{plan['id']}/runs", body, key="concurrent-0")["id"]
    ids = {value for status, value in results if status == "ok"} | {retry}
    errors = [value for status, value in results if status == "error"]
    checks.expect("one_run_per_approved_plan", len(ids) == 1,
                  f"{len(ids)} distinct run id(s) from {threads} concurrent starts plus one same-key retry; "
                  f"errors {errors}")
    checks.expect("no_server_errors_under_concurrency", all(e not in (500, 502, 503) for e in errors),
                  f"errors {errors}")
    run_id = next(iter(ids))
    finished = flow.poll(f"/runs/{run_id}")
    flow.jobs_executed.add(run_id)
    reservations = [s for s in finished.get("scenarios", []) if s.get("scenario_id") == "baseline"]
    checks.expect("no_duplicate_science", len(reservations) <= 1,
                  f"{len(reservations)} baseline reservation(s); run state {finished.get('state')}")
    activity = flow.client.get(f"/workspaces/{workspace}/activity")
    total = sum((activity.get("job_states") or {}).values())
    checks.expect("workspace_has_one_job", total == 1, f"job states {activity.get('job_states')}")
    second = flow.client.post(f"/plans/{plan['id']}/approvals", {"expected_plan_digest": plan["digest"],
                              "expected_current_revision_id": problem["id"], "accepted": True}, label="c-approve-again")
    checks.expect("repeat_approval_returns_same_approval", second["id"] == approval["id"],
                  "an approval is not multiplied by repetition")
    flow.save_record("concurrency-run", finished)
    return {"checks": checks, "observation": {"run_id": run_id, "distinct_runs": len(ids), "errors": errors,
                                              "job_states": activity.get("job_states")}}


def scenario_design_authority(flow: Flow, packet: dict) -> dict:
    """Baseline approval cannot authorize design; the reviewed pair, allowance and grid are bound."""
    checks = Checks()
    base = flow.cache.get("hero")
    if not base or base.get("blocked"):
        base = flow.baseline(packet, label="authority")
        flow.cache["hero"] = base
    pair = choose_pair(flow.cache.get("hero_info") or {})
    run, problem = base["run"], base["problem"]
    # Always checkable: a design proposal needs usable historical evidence.
    review = packet["design_review"]
    if not pair:
        fake = [{"id": "candidate-not-in-evidence-1", "parameter_vector": {"A": "9/1", "ke": "1/8", "ka": "7/2"}},
                {"id": "candidate-not-in-evidence-2", "parameter_vector": {"A": "8/1", "ke": "3/40", "ka": "4/1"}}]
        try:
            flow.client.post(f"/runs/{run['id']}/design-proposals", _design_request(run, problem, fake, review),
                             label="authority-no-evidence")
            checks.add("design_requires_usable_evidence_and_listed_candidates", "failed",
                       "a design plan was created from candidates absent from the historical evidence",
                       finding="F-DESIGN-AUTHORITY")
        except ApiFailure as error:
            checks.expect("design_requires_usable_evidence_and_listed_candidates", error.status in (403, 409, 422)
                          and error.code in ("historical_evidence_required", "candidate_not_in_scope",
                                             "binding_mismatch"), f"{error.status} {error.code}")
        checks.add("baseline_approval_cannot_start_design", "blocked",
                   "needs a completed baseline with two candidates (see hero entry)", finding="F-HERO-NO-PAIR")
        return {"checks": checks, "observation": {"pair": None}}
    first = _design_request(run, problem, pair, review)
    plan = flow.client.post(f"/runs/{run['id']}/design-proposals", first, label="authority-plan-a")
    # 1. The baseline approval names the investigation plan, never this design.
    try:
        flow.client.post(f"/design-plans/{plan['id']}/jobs",
                         {"approval_id": base["approval"]["id"], "expected_plan_digest": plan["digest"]},
                         label="authority-baseline-approval")
        checks.add("baseline_approval_cannot_start_design", "failed", "design job started with the baseline approval",
                   finding="F-DESIGN-AUTHORITY")
    except ApiFailure as error:
        checks.expect("baseline_approval_cannot_start_design", error.status == 403
                      and error.code == "approval_required", f"{error.status} {error.code}")
    # 2. Approval must name this exact design digest.
    try:
        flow.client.post(f"/design-plans/{plan['id']}/approvals", {"expected_plan_digest": "0" * 64,
                         "expected_current_revision_id": problem["id"], "accepted": True}, label="authority-wrong-dig")
        checks.add("design_approval_binds_digest", "failed", "approval accepted a different plan digest",
                   finding="F-DESIGN-AUTHORITY")
    except ApiFailure as error:
        checks.expect("design_approval_binds_digest", error.code == "binding_mismatch", f"{error.status} {error.code}")
    approval_a = flow.client.post(f"/design-plans/{plan['id']}/approvals", {"expected_plan_digest": plan["digest"],
                                  "expected_current_revision_id": problem["id"], "accepted": True}, label="authority-ok")
    # 3. A different grid or allowance is a different plan; plan A's approval cannot start it.
    for label, change in (("grid", {"feasible_times": review["feasible_times"][:1]}),
                          ("allowance", {"future_hard_allowance": "3/5"})):
        other = flow.client.post(f"/runs/{run['id']}/design-proposals", {**first, **change},
                                 label=f"authority-plan-{label}")
        checks.expect(f"changed_{label}_is_new_plan", other["id"] != plan["id"] and other["digest"] != plan["digest"],
                      "a changed reviewed constraint produced a distinct design plan")
        try:
            flow.client.post(f"/design-plans/{other['id']}/jobs",
                             {"approval_id": approval_a["id"], "expected_plan_digest": other["digest"]},
                             label=f"authority-reuse-{label}")
            checks.add(f"approval_bound_to_{label}", "failed", f"approval for the reviewed {label} started another plan",
                       finding="F-DESIGN-AUTHORITY")
        except ApiFailure as error:
            checks.expect(f"approval_bound_to_{label}", error.status == 403, f"{error.status} {error.code}")
    # 4. Pair scope: unknown id, duplicated candidate and altered vector are refused.
    alter = dict(pair[1]["parameter_vector"])
    alter["ke"] = _nudge(alter["ke"])
    for label, request, codes in (
        ("unknown_candidate", {**first, "candidate_ids": [pair[0]["id"], "candidate-not-in-evidence"]},
         ("candidate_not_in_scope",)),
        ("duplicate_candidate", {**first, "candidate_ids": [pair[0]["id"], pair[0]["id"]],
                                 "candidate_vectors": [pair[0]["parameter_vector"]] * 2},
         ("field_validation_failed",)),
        ("altered_vector", {**first, "candidate_vectors": [pair[0]["parameter_vector"], alter]},
         ("candidate_vector_mismatch",))):
        try:
            flow.client.post(f"/runs/{run['id']}/design-proposals", request, label=f"authority-{label}")
            checks.add(f"refuses_{label}", "failed", "design plan created", finding="F-DESIGN-AUTHORITY")
        except ApiFailure as error:
            checks.expect(f"refuses_{label}", error.code in codes, f"{error.status} {error.code}")
    return {"checks": checks, "observation": {"design_plan_id": plan["id"], "approval_id": approval_a["id"]}}


def _design_request(run: dict, problem: dict, pair: list[dict], review: dict) -> dict:
    return {"schema_version": "DB-SC-1", "historical_run_id": run["id"], "scenario_id": "baseline",
            "problem_id": problem["id"], "problem_digest": problem["digest"],
            "candidate_ids": [c["id"] for c in pair], "candidate_vectors": [c["parameter_vector"] for c in pair],
            "observable": "concentration", "feasible_times": review["feasible_times"],
            "future_hard_allowance": review["future_hard_allowance"],
            "allow_construction": bool(review.get("allow_construction")),
            "allow_continuation": bool(review.get("allow_continuation"))}


def _nudge(rational: str) -> str:
    value = F(rational) * Fraction(1001, 1000)
    return f"{value.numerator}/{value.denominator}"


def scenario_followup(flow: Flow, packet: dict) -> dict:
    """Hypothetical readings create new lineage; per-candidate outcomes are preserved and checked."""
    checks = Checks()
    base, design = flow.cache.get("hero"), flow.cache.get("hero_design")
    if not base or base.get("blocked") or not base.get("evidence"):
        checks.add("followup_prerequisites", "blocked", "needs the hero baseline run", finding="F-HERO-NO-PAIR")
        return {"checks": checks, "observation": {}}
    pair = (design or {}).get("request", {}).get("candidate_ids")
    selected = (((design or {}).get("suggestion") or {}).get("body") or {}).get("selected_time")
    vectors = dict(zip(pair or [], (design or {}).get("request", {}).get("candidate_vectors") or []))
    branches = []
    parent = base["dataset"]
    for branch in packet["followups"]:
        time_value = selected or branch["time"]
        row = {"id": f"followup_{branch['branch'].replace('.', '_')}", "time": time_value,
               "concentration": branch["reading"], "hard_allowance": branch["allowance"], "included": True,
               "original_values": {"concentration": branch["reading_spelling"]}, "source_asset_id": None,
               "notes": "Hypothetical reading for a what-if branch; not a measurement."}
        proposal = flow.client.post(f"/workspaces/{base['workspace_id']}/observation-proposals", {
            "dataset_id": parent["id"], "experiment_id": parent["body"]["experiment_id"], "observable": "concentration",
            "origin": "hypothetical", "row": row, "source_description": "Evaluation what-if branch",
            "change_reason": f"Hypothetical {branch['reading_spelling']} mg/L at the selected time",
            "generating_choices": {"generator": "evaluation-harness", "branch": branch["branch"]}},
            label=f"fu-{branch['branch']}")
        try:
            revised = flow.client.post(f"/observation-proposals/{proposal['id']}/review",
                                       {"proposal_digest": proposal["digest"], "parent_dataset_id": parent["id"],
                                        "accepted": True}, label=f"fu-review-{branch['branch']}")
        except ApiFailure as error:
            checks.add(f"{branch['branch']}_lineage", "failed", f"review refused {error.status} {error.code}")
            continue
        checks.expect(f"{branch['branch']}_new_hypothetical_lineage",
                      revised["id"] != parent["id"] and revised.get("parent_id") == parent["id"]
                      and revised["body"]["origin"] == "hypothetical"
                      and len(revised["body"]["rows"]) == len(parent["body"]["rows"]) + 1,
                      f"origin {revised['body']['origin']}, parent {revised.get('parent_id')}")
        expected = {cid: kinetics.band_verdict(vec, time_value, branch["reading"], branch["allowance"])
                    for cid, vec in vectors.items()}
        problem = flow.client.post(f"/workspaces/{base['workspace_id']}/problems",
                                   {**packet["problem"], "dataset_id": revised["id"], "dataset_digest": revised["digest"]},
                                   label=f"fu-problem-{branch['branch']}")
        plan = flow.client.post(f"/workspaces/{base['workspace_id']}/plans", {
            "expected_current_revision_id": problem["id"], "plan": {
                "schema_version": "DB-SC-1", "problem_id": problem["id"], "problem_digest": problem["digest"],
                "dataset_id": revised["id"], "scenarios": [{"id": "baseline", "problem_id": problem["id"],
                                                             "problem_digest": problem["digest"], "kind": "baseline",
                                                             "label": "Follow-up baseline"}]}},
            label=f"fu-plan-{branch['branch']}")
        try:
            flow.client.post(f"/plans/{plan['id']}/runs", {"approval_id": base["approval"]["id"],
                             "expected_plan_digest": plan["digest"]}, label=f"fu-old-approval-{branch['branch']}")
            checks.add(f"{branch['branch']}_requires_new_approval", "failed", "old approval started new work",
                       finding="F-APPROVAL-REUSE")
        except ApiFailure as error:
            checks.expect(f"{branch['branch']}_requires_new_approval", error.status == 403,
                          f"{error.status} {error.code}")
        approval = flow.client.post(f"/plans/{plan['id']}/approvals", {"expected_plan_digest": plan["digest"],
                                    "expected_current_revision_id": problem["id"], "accepted": True},
                                    label=f"fu-approve-{branch['branch']}")
        run = flow.client.post(f"/plans/{plan['id']}/runs", {"approval_id": approval["id"],
                               "expected_plan_digest": plan["digest"]}, label=f"fu-run-{branch['branch']}")
        finished = flow.poll(f"/runs/{run['id']}")
        flow.jobs_executed.add(run["id"])
        evidence = [flow.client.get(f"/records/{c['result_id']}") for c in finished.get("scenarios", [])
                    if c.get("result_id")]
        per_candidate = _prior_candidate_results(evidence, pair or [])
        if not vectors:
            checks.add(f"{branch['branch']}_per_candidate_outcome", "blocked",
                       "no selected pair from the hero design to re-check", finding="F-HERO-NO-PAIR")
        elif per_candidate is None:
            checks.add(f"{branch['branch']}_per_candidate_outcome", "blocked",
                       f"follow-up run {finished.get('state')} exposes no candidate-specific result for the prior pair "
                       f"(independent oracle expects {expected})", finding="F-FOLLOWUP-FEEDBACK")
        else:
            agree = all(expected[c] == "indeterminate" or per_candidate.get(c) == expected[c] for c in expected)
            checks.expect(f"{branch['branch']}_per_candidate_outcome", agree,
                          f"application {per_candidate}, independent oracle {expected}")
        branches.append({"branch": branch["branch"], "time": time_value, "dataset_id": revised["id"],
                         "run_id": run["id"], "run_state": finished.get("state"), "oracle_expectation": expected,
                         "application_per_candidate": per_candidate})
    check_original_unchanged(checks, flow, base, "original_evidence_unchanged_after_followups")
    return {"checks": checks, "observation": {"branches": branches, "selected_time_used": selected}}


def _prior_candidate_results(evidence: list[dict], pair_ids: list[str]) -> dict | None:
    """Candidate-specific outcomes for the prior pair, if the application exposes them."""
    for record in evidence:
        result = result_of(record)
        for key in ("prior_candidate_results", "candidate_results", "followup_candidate_results"):
            items = result.get(key) or (record.get("body") or {}).get(key)
            if isinstance(items, list):
                found = {}
                for item in items:
                    cid = item.get("candidate_id") or item.get("id")
                    if cid in pair_ids:
                        verdict = item.get("verification") or item.get("state")
                        found[cid] = "compatible" if verdict in ("valid", "compatible") else (
                            "excluded" if verdict in ("invalid", "excluded") else str(verdict))
                if found:
                    return found
    return None


def scenario_cancel_restart(flow: Flow, packet: dict, stack) -> dict:
    """Queued cancellation, running cancellation and worker restart, with orphan checks."""
    checks = Checks()
    observation: dict = {}
    # A. Queued cancellation: stop the worker so the job stays queued.
    stack.kill("worker")
    workspace = flow.client.post("/workspaces", {"name": "Dr. Bean evaluation cancellation"}, label="cx-ws")["id"]
    flow.workspaces.append(workspace)
    queued = _approved_run(flow, packet, workspace, "cx-queued")
    cancelled = flow.client.post(f"/runs/{queued['id']}/cancel", label="cx-cancel-queued")
    checks.expect("queued_cancel_requested", cancelled.get("state") == "cancel_requested", cancelled.get("state", ""))
    stack.start_worker()
    final = flow.poll(f"/runs/{queued['id']}", timeout=30)
    checks.expect("queued_cancel_acknowledged_without_science", final.get("state") == "cancelled"
                  and not final.get("scenarios"), f"state {final.get('state')}, {len(final.get('scenarios', []))} "
                  "scenario reservation(s)")
    # B. Running cancellation through the API.
    running = _approved_run(flow, packet, workspace, "cx-running")
    observed = _wait_running(flow, running["id"])
    live_before = _live_science_children(stack, flow, running["id"]) if observed else []
    if observed:
        flow.client.post(f"/runs/{running['id']}/cancel", label="cx-cancel-running")
        done = flow.poll(f"/runs/{running['id']}", timeout=60)
        stack.snapshot_descendants()
        checks.expect("running_cancel_terminal", done.get("state") in ("cancelled", "completed", "failed"),
                      f"state {done.get('state')}")
        observation["running_cancel_state"] = done.get("state")
    else:
        checks.add("running_cancel_terminal", "not_observed",
                   "the scientific job left the running state before cancellation could be issued")
    if live_before:
        time.sleep(1.0)
        leftover = [pid for pid in live_before if _alive(pid)]
        checks.expect("no_orphan_after_cancel", not leftover,
                      f"{len(live_before)} live scientific child(ren) at cancel; still alive: {leftover}",
                      finding="F-ORPHAN" if leftover else None)
    else:
        checks.add("no_orphan_after_cancel", "not_observed",
                   "no sustained scientific computation existed at the cancellation point, so the orphan check "
                   "would be vacuous (for example the child failed immediately)")
    # C. Worker killed mid-run, explicit recovery, no silent redispatch.
    third = _approved_run(flow, packet, workspace, "cx-restart")
    restart_ids = ("no_orphan_after_worker_kill", "interrupted_not_redispatched", "interrupted_stays_interrupted")
    if _wait_running(flow, third["id"]):
        live_before = _live_science_children(stack, flow, third["id"])
        stack.kill("worker")
        after_kill = flow.client.get(f"/runs/{third['id']}")
        if after_kill.get("state") != "running":
            for check_id in restart_ids:
                checks.add(check_id, "not_observed", f"the run reached {after_kill.get('state')} before the worker "
                           "was killed, so there was no in-flight work to interrupt")
            stack.start_worker()
        else:
            time.sleep(1.0)
            survivors = [pid for pid in live_before if _alive(pid)]
            observation["children_alive_after_worker_kill"] = survivors
            if live_before:
                checks.expect("no_orphan_after_worker_kill", not survivors,
                              f"{len(live_before)} live scientific child(ren) when the worker was killed; still "
                              f"alive: {survivors}", finding="F-ORPHAN" if survivors else None)
            else:
                checks.add("no_orphan_after_worker_kill", "not_observed",
                           "no sustained scientific computation existed when the worker was killed; check would be vacuous")
            recover = stack.start_worker("--recover")
            recover.wait(timeout=60)
            stack.start_worker()
            after = flow.poll(f"/runs/{third['id']}", timeout=20)
            checks.expect("interrupted_not_redispatched", after.get("state") == "interrupted",
                          f"state after recovery {after.get('state')} (error {after.get('error_code')})")
            time.sleep(2.0)
            again = flow.client.get(f"/runs/{third['id']}")
            checks.expect("interrupted_stays_interrupted", again.get("state") == "interrupted"
                          and len(again.get("scenarios", [])) == len(after.get("scenarios", [])),
                          f"state {again.get('state')}")
    else:
        for check_id in restart_ids:
            checks.add(check_id, "not_observed", "the scientific job left the running state before the worker "
                       "could be killed")
    observation["queued_run"] = queued["id"]
    return {"checks": checks, "observation": observation}


def _approved_run(flow: Flow, packet: dict, workspace: str, label: str) -> dict:
    dataset = flow.client.post(f"/workspaces/{workspace}/datasets",
                               {**packet["dataset"], "experiment_id": f"{packet['dataset']['experiment_id']}_{label}"
                                .replace("-", "_")}, label=f"{label}-dataset")
    problem = flow.client.post(f"/workspaces/{workspace}/problems", {**packet["problem"], "dataset_id": dataset["id"],
                               "dataset_digest": dataset["digest"]}, label=f"{label}-problem")
    plan = flow.client.post(f"/workspaces/{workspace}/plans", {"expected_current_revision_id": problem["id"], "plan": {
        "schema_version": "DB-SC-1", "problem_id": problem["id"], "problem_digest": problem["digest"],
        "dataset_id": dataset["id"], "scenarios": [{"id": "baseline", "problem_id": problem["id"],
                                                     "problem_digest": problem["digest"], "kind": "baseline",
                                                     "label": label}]}}, label=f"{label}-plan")
    approval = flow.client.post(f"/plans/{plan['id']}/approvals", {"expected_plan_digest": plan["digest"],
                                "expected_current_revision_id": problem["id"], "accepted": True},
                                label=f"{label}-approval")
    run = flow.client.post(f"/plans/{plan['id']}/runs", {"approval_id": approval["id"],
                           "expected_plan_digest": plan["digest"]}, label=f"{label}-run")
    flow.jobs_executed.add(run["id"])
    return run


def _wait_running(flow: Flow, run_id: str, timeout: float = 20.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        run = flow.client.get(f"/runs/{run_id}")
        if run.get("state") == "running" and any(s.get("state") == "running" for s in run.get("scenarios", [])):
            return True
        if run.get("state") in TERMINAL:
            return False
        time.sleep(0.05)
    return False


def _live_science_children(stack, flow: Flow | None = None, run_id: str | None = None,
                           timeout: float = 5.0, sustain: float = 0.5) -> list[int]:
    """Scientific children in a *sustained* computation: alive across ``sustain`` seconds while the run is running.

    The API marks a scenario running before it spawns the child, and a child that exits on its own
    within moments (for example a failed resource setup) proves nothing about cancellation. Only a
    child observed alive twice, ``sustain`` apart, with the run still running, counts.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() <= deadline:
        stack.snapshot_descendants()
        live = [pid for pid in _science_children(stack) if _alive(pid)]
        if flow is not None and run_id and flow.client.get(f"/runs/{run_id}").get("state") in TERMINAL:
            return []
        if live:
            time.sleep(sustain)
            still = [pid for pid in live if _alive(pid)]
            running = flow is None or not run_id or flow.client.get(f"/runs/{run_id}").get("state") == "running"
            if still and running:
                return still
        time.sleep(0.05)
    return []


def _science_children(stack) -> list[int]:
    """Scientific children are multiprocessing *spawn* workers; the resource tracker is excluded."""
    return [pid for pid, row in stack.seen_descendants.items()
            if "spawn_main" in row["command"] and "resource_tracker" not in row["command"]]


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _ids(base: dict) -> dict:
    out = {"workspace_id": base.get("workspace_id")}
    for name in ("dataset", "problem", "plan", "approval"):
        record = base.get(name) or {}
        out[f"{name}_id"] = record.get("id")
        if record.get("digest"):
            out[f"{name}_digest"] = record["digest"]
    out["run_id"] = (base.get("run") or {}).get("id")
    out["run_state"] = (base.get("run") or {}).get("state")
    out["evidence_ids"] = [e.get("id") for e in base.get("evidence") or []]
    return out


def _summary(info: dict) -> dict:
    result = info.get("result") or {}
    return {"scientific_outcome": result.get("scientific_outcome"), "verification": result.get("verification"),
            "expected_binding": result.get("expected_binding"), "replay": result.get("replay"),
            "reason_code": result.get("reason_code"),
            "candidates": [{"id": c.get("id"), "parameter_vector": c.get("parameter_vector"),
                            "verification": c.get("verification")} for c in result.get("candidates") or []],
            "independent_oracle_history": info.get("independent_oracle_history")}


def scenario_zero_dispatch(flow: Flow, stack) -> dict:
    """Whole lane so far: guard active in API and worker, zero external attempts, empty provider ledgers."""
    checks = Checks()
    events = stack.guard_events()
    installed = {e["pid"] for e in events if e["kind"] == "guard_installed"}
    api_pid = stack.processes["api"].pid
    worker_pids = {p.pid for name, p in stack.processes.items() if name.startswith("worker")}
    checks.expect("guard_active_in_api", api_pid in installed, f"api pid guarded: {api_pid in installed}")
    checks.expect("guard_active_in_worker", bool(worker_pids & installed),
                  f"{len(worker_pids & installed)} of {len(worker_pids)} worker process(es) guarded")
    attempts = stack.external_attempts()
    checks.expect("zero_external_model_attempts", not attempts,
                  f"{len(attempts)} blocked attempt(s): {sorted({a.get('host') or a.get('client') for a in attempts})}",
                  finding="F-EXTERNAL-ATTEMPT" if attempts else None)
    names = sorted({n for e in events for n in e.get("credential_names_present", [])})
    checks.expect("no_provider_credentials_in_launched_environment", not names, f"names present: {names}")
    ledgers = {}
    for workspace in flow.workspaces:
        ledgers[workspace] = len(flow.client.get(f"/workspaces/{workspace}/provider-attempts"))
    checks.expect("provider_attempt_ledgers_empty", all(v == 0 for v in ledgers.values()),
                  f"{len(ledgers)} harness workspace(s); attempts {sorted(ledgers.values())}")
    capabilities = flow.client.raw("GET", "/capabilities", authenticated=False).json()
    gemini = capabilities.get("gemini") or {}
    checks.expect("capabilities_claim_no_live_qualification", gemini.get("verified_in_environment") is False
                  and (capabilities.get("deepagents") or {}).get("verified_in_environment") is False,
                  "gemini/deepagents verified_in_environment must stay false offline")
    mode = gemini.get("mode") or gemini.get("provider_mode") or gemini.get("execution_mode")
    checks.add("explicit_placeholder_mode_reported",
               "passed" if mode in ("placeholder", "disabled", "controlled_placeholder", "offline_placeholder")
               else "blocked", f"capabilities.gemini mode {mode!r}", level=INFO,
               finding=None if mode else "F-PLACEHOLDER-MODE")
    return {"checks": checks, "observation": {"guarded_processes": len(installed), "workspaces": len(ledgers),
                                              "gemini_capability": {k: gemini.get(k) for k in (
                                                  "configured", "account_gate_passed", "verified_in_environment",
                                                  "unavailable_reason", "mode")}}}
