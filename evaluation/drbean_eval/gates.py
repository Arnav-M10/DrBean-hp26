"""Machine-readable release gates for Owner 4. Computed only from recorded evidence.

Gate statuses: ``passed``, ``failed`` (required evidence failed), ``blocked``
(required evidence absent or blocked by another workstream's prerequisite) and
``not_run`` (never required now, e.g. live Gemini). A requested release gate
exits nonzero unless every required gate passed at the tested commit. Inventory
mode reports the same statuses and exits zero unless the harness itself is broken.

Evidence must be at the tested commit, from an executed acceptance (never an
imported claim), on a clean worktree, with a verified append-only history.
"""
from __future__ import annotations

import json
import os
import subprocess

from . import engine_controls, history, lanes, manifest as manifest_mod
from .runner import read_attempts

REQUIRED_SCIENCE = ("RS-HERO-FULL",)
REQUIRED_NEGATIVE = ("RS-RETRY-CONCURRENT", "RS-DESIGN-AUTHORITY", "RS-CANCEL-RESTART", "RS-CHANGED-INPUT",
                     "RS-FOLLOWUP")
REQUIRED_CONTROLS = ("fixed_pair:grid-6-8-allowance-0.2", "fixed_pair:grid-6-allowance-0.2",
                     "fixed_pair:grid-6-8-allowance-0.6", "defense:wrong_expected_identity", "defense:changed_byte",
                     "defense:mutation_rejected_by_original_anchor", "defense:mutation_rejected_by_fresh_mathematics",
                     "semantics:touching_bands_do_not_separate", "semantics:closed_endpoint_is_inside",
                     "followup:3.4", "followup:4.57", "followup:4.0",
                     "defense:truncated_packet", "defense:oversized_packet", "defense:another_runs_valid_packet",
                     "defense:drop_artifacts", "defense:duplicate_artifact", "defense:unknown_profile",
                     "metamorphic:tightened_row_allowance", "metamorphic:widened_allowances_keep_compatibility",
                     "metamorphic:excluded_row_is_not_a_constraint", "metamorphic:swapped_pair_order")


# Changes here cannot alter the application or the harness's behaviour: recorded evidence and its written
# summaries. Evidence recorded at an ancestor counts for the tested commit only if every later change is here.
EVIDENCE_ONLY_PATHS = lanes.EVIDENCE_ONLY_PATHS


def equivalent_commits(repo: str, head: str, candidates: set[str]) -> set[str]:
    """``head`` plus each ancestor whose difference from ``head`` touches only evidence and documentation paths."""
    same = {head}
    for commit in sorted(c for c in candidates if c and c != head):
        if not head or subprocess.run(["git", "-C", repo, "merge-base", "--is-ancestor", commit, head],
                                      capture_output=True).returncode != 0:
            continue
        diff = subprocess.run(["git", "-C", repo, "diff", "--name-only", commit, head], capture_output=True, text=True)
        changed = [path for path in diff.stdout.splitlines() if path.strip()]
        if diff.returncode == 0 and all(path.startswith(EVIDENCE_ONLY_PATHS) for path in changed):
            same.add(commit)
    return same


def _latest(attempts: list[dict], commits, lane: str) -> dict[str, dict]:
    commits = {commits} if isinstance(commits, str) else set(commits)
    latest = {}
    for attempt in attempts:
        if attempt.get("lane") == lane and attempt.get("tested_commit") in commits:
            latest[attempt["entry_id"]] = attempt
    return latest


def control_record_problems(run: dict, expected_source: str | None) -> list[str]:
    """Why a control run cannot count as acceptance evidence; empty when it is fully qualified."""
    problems = []
    if run.get("worktree_dirty") is not False:
        problems.append("worktree dirty or not recorded")
    if run.get("evidence_class") != "executed_acceptance" or run.get("app_under_test"):
        problems.append(f"not executed acceptance of this checkout ({run.get('evidence_class') or 'unclassified'})")
    interpreter = run.get("interpreter") or {}
    if interpreter.get("implementation") != "CPython" or not str(interpreter.get("version", "")).startswith("3.11."):
        problems.append("engine interpreter is not the qualified CPython 3.11")
    engine = run.get("engine") or {}
    if not engine.get("source_sha256"):
        problems.append("engine identity not recorded")
    elif engine.get("imported_from") != "repository":
        problems.append("engine was not imported from the repository source")
    elif expected_source is None or engine["source_sha256"] != expected_source:
        problems.append("engine source differs from the tested code")
    return problems


def native_controls_gate(runs: list[dict], expected_source: str | None) -> dict:
    """Each required control is decided by its newest relevant run (file order = time order).

    An unqualified newest run (dirty, preview, wrong interpreter or engine) blocks that control: older passing
    evidence never overrides newer invalid evidence. A qualified newest run counts only with ``passed is True``.
    """
    newest: dict[str, tuple[dict, dict]] = {}
    for run in runs:
        for item in run.get("results") or []:
            if isinstance(item, dict) and item.get("id"):
                newest[item["id"]] = (run, item)
    missing, failed, unqualified, used = [], [], {}, {}
    for control in REQUIRED_CONTROLS:
        if control not in newest:
            missing.append(control)
            continue
        run, item = newest[control]
        used[run.get("at") or "?"] = run.get("tested_commit")
        problems = control_record_problems(run, expected_source)
        if problems:
            unqualified[control] = problems
        elif item.get("passed") is not True:
            failed.append(control)
    return {"gate": "native_engine_controls", "description": "fixed-pair constraint controls, three distinct "
            "defenses, endpoint/touching-band semantics, candidate-specific follow-ups (engine, not HTTP); each "
            "decided by its newest clean, executed, CPython 3.11 run of the tested engine source",
            "status": "failed" if failed else "blocked" if missing or unqualified else "passed",
            "missing": missing, "failed": failed, "unqualified": unqualified,
            "expected_engine_source_sha256": expected_source, "runs_used": used}


def read_jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _entry_gate(name: str, latest: dict, entries: tuple[str, ...], description: str) -> dict:
    states = {}
    for entry in entries:
        attempt = latest.get(entry)
        if attempt is None:
            states[entry] = {"status": "blocked", "reason": "no attempt at the tested commit"}
            continue
        status = attempt["status"]
        app = attempt.get("app_under_test") or {}
        foreign_app = bool(app) and (app.get("commit") != attempt.get("tested_commit") or app.get("dirty"))
        if status == "passed" and (attempt.get("evidence_class") != "executed_acceptance" or attempt.get(
                "worktree_dirty") or foreign_app):
            status, reason = "blocked", ("passed only as an imported claim, preview, diagnostic, foreign application "
                                         "commit or dirty worktree; not release acceptance")
        else:
            reason = attempt.get("reason")
        states[entry] = {"status": {"passed": "passed", "failed": "failed", "error": "failed"}.get(status, "blocked"),
                         "reason": (reason or "")[:400], "attempt_id": attempt["attempt_id"]}
    values = {s["status"] for s in states.values()}
    status = "failed" if "failed" in values else "blocked" if "blocked" in values else "passed"
    return {"gate": name, "status": status, "description": description, "entries": states}


def compute(root: str, results_dir: str, commit: str, dirty: bool, findings_path: str | None = None,
            repo: str | None = None) -> dict:
    manifest_problems = manifest_mod.verify(root)
    history_problems = history.verify(results_dir)
    attempts = read_attempts(results_dir)
    all_controls = read_jsonl(os.path.join(results_dir, "controls.jsonl"))
    same = equivalent_commits(repo or os.path.dirname(os.path.abspath(root)), commit,
                              {a.get("tested_commit") for a in attempts} | {c.get("tested_commit") for c in all_controls})
    latest = _latest(attempts, same, "offline_real_science")
    gates = [{"gate": "harness_integrity", "description": "frozen manifest and append-only history verify",
              "status": "passed" if not manifest_problems and not history_problems else "failed",
              "problems": (manifest_problems + history_problems)[:20]}]
    gates.append(_entry_gate("real_science_http", latest, REQUIRED_SCIENCE,
                             "actual HTTP -> science -> separate design -> raw download -> fresh native replay"))
    gates.append(_entry_gate("essential_negative_controls_http", latest, REQUIRED_NEGATIVE,
                             "duplicate starts, design authority, cancellation/restart, changed input, follow-up"))
    zero = _entry_gate("zero_external_model_dispatch", latest, ("RS-ZERO-DISPATCH",),
                       "guard active in API and worker; zero external model attempts in the lane")
    lane_attempts = [a for a in attempts if a.get("lane") == "offline_real_science" and a.get("tested_commit") in same]
    unverified = [a["entry_id"] for a in lane_attempts if (a.get("external_model_requests") or {}).get("value") != 0
                  and a["status"] != "unrun"]
    if unverified and zero["status"] == "passed":
        zero.update(status="failed", reason=f"entries without verified zero dispatch: {unverified}")
    gates.append(zero)
    gates.append(native_controls_gate([c for c in all_controls if c.get("tested_commit") in same],
                                      engine_controls.engine_source_identity(
                                          os.path.join(repo or os.path.dirname(os.path.abspath(root)), "packages",
                                                       "groundwork_adapter"))["source_sha256"]))
    platform_entry = latest.get("RS-HERO-FULL")
    platform_checks = {c["id"]: c for c in ((platform_entry or {}).get("qualification") or {}).get(
        "executed_checks") or []}
    source = platform_checks.get("source_image_admitted", {}).get("outcome")
    worker = platform_checks.get("baseline_completed_with_evidence", {}).get("outcome")
    gates.append({"gate": "supported_machine_subprocesses", "description": "image decoder and scientific worker "
                  "subprocesses work on this host through the real stack",
                  "status": "passed" if source == "passed" and worker == "passed" else
                  "failed" if "failed" in (source, worker) else "blocked",
                  "observed": {"source_image_admitted": source, "baseline_completed_with_evidence": worker,
                               "runtime": (platform_entry or {}).get("runtime")}})
    gates.append(lanes.lanes_gate(results_dir, repo or os.path.dirname(os.path.abspath(root))))
    findings = []
    if findings_path and os.path.exists(findings_path):
        with open(findings_path, encoding="utf-8") as handle:
            findings = json.load(handle).get("findings", [])
    open_p0 = [f["id"] for f in findings if f.get("severity") == "P0" and f.get("status") not in ("closed", "retested")]
    gates.append({"gate": "no_unresolved_p0", "status": "passed" if not open_p0 else "failed",
                  "description": "evaluation/findings.json lists no open P0", "open_p0": open_p0})
    gates.append({"gate": "live_gemini_qualification", "status": "not_run", "required": False,
                  "description": "NOT a current acceptance gate. Live requests need the user to enable provider "
                                 "consent and one bounded shared qualification budget; none exists. Controlled "
                                 "placeholder runs are never Gemini evidence."})
    required = [g for g in gates if g.get("required", True)]
    overall = ("passed" if all(g["status"] == "passed" for g in required) and not dirty else
               "failed" if any(g["status"] == "failed" for g in required) else "blocked")
    return {"schema": "drbean-release-gates/v1", "tested_commit": commit, "worktree_dirty": dirty,
            "evidence_commits": sorted(same), "evidence_only_paths": list(EVIDENCE_ONLY_PATHS),
            "overall": overall, "gates": gates,
            "statement": "Gates read recorded evidence only; they dispatch no provider or scientific work."}
