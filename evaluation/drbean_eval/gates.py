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

from . import history, manifest as manifest_mod
from .runner import read_attempts

REQUIRED_SCIENCE = ("RS-HERO-FULL",)
REQUIRED_NEGATIVE = ("RS-RETRY-CONCURRENT", "RS-DESIGN-AUTHORITY", "RS-CANCEL-RESTART", "RS-CHANGED-INPUT",
                     "RS-FOLLOWUP")
REQUIRED_CONTROLS = ("fixed_pair:grid-6-8-allowance-0.2", "fixed_pair:grid-6-allowance-0.2",
                     "fixed_pair:grid-6-8-allowance-0.6", "defense:wrong_expected_identity", "defense:changed_byte",
                     "defense:mutation_rejected_by_original_anchor", "defense:mutation_rejected_by_fresh_mathematics",
                     "semantics:touching_bands_do_not_separate", "semantics:closed_endpoint_is_inside",
                     "followup:3.4", "followup:4.57", "followup:4.0")


def _latest(attempts: list[dict], commit: str, lane: str) -> dict[str, dict]:
    latest = {}
    for attempt in attempts:
        if attempt.get("lane") == lane and attempt.get("tested_commit") == commit:
            latest[attempt["entry_id"]] = attempt
    return latest


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
        if status == "passed" and (attempt.get("evidence_class") != "executed_acceptance" or attempt.get(
                "worktree_dirty")):
            status, reason = "blocked", "passed only as an imported claim or on a dirty worktree"
        else:
            reason = attempt.get("reason")
        states[entry] = {"status": {"passed": "passed", "failed": "failed", "error": "failed"}.get(status, "blocked"),
                         "reason": (reason or "")[:400], "attempt_id": attempt["attempt_id"]}
    values = {s["status"] for s in states.values()}
    status = "failed" if "failed" in values else "blocked" if "blocked" in values else "passed"
    return {"gate": name, "status": status, "description": description, "entries": states}


def compute(root: str, results_dir: str, commit: str, dirty: bool, findings_path: str | None = None) -> dict:
    manifest_problems = manifest_mod.verify(root)
    history_problems = history.verify(results_dir)
    attempts = read_attempts(results_dir)
    latest = _latest(attempts, commit, "offline_real_science")
    gates = [{"gate": "harness_integrity", "description": "frozen manifest and append-only history verify",
              "status": "passed" if not manifest_problems and not history_problems else "failed",
              "problems": (manifest_problems + history_problems)[:20]}]
    gates.append(_entry_gate("real_science_http", latest, REQUIRED_SCIENCE,
                             "actual HTTP -> science -> separate design -> raw download -> fresh native replay"))
    gates.append(_entry_gate("essential_negative_controls_http", latest, REQUIRED_NEGATIVE,
                             "duplicate starts, design authority, cancellation/restart, changed input, follow-up"))
    zero = _entry_gate("zero_external_model_dispatch", latest, ("RS-ZERO-DISPATCH",),
                       "guard active in API and worker; zero external model attempts in the lane")
    lane_attempts = [a for a in attempts if a.get("lane") == "offline_real_science" and a.get("tested_commit") == commit]
    unverified = [a["entry_id"] for a in lane_attempts if (a.get("external_model_requests") or {}).get("value") != 0
                  and a["status"] != "unrun"]
    if unverified and zero["status"] == "passed":
        zero.update(status="failed", reason=f"entries without verified zero dispatch: {unverified}")
    gates.append(zero)
    controls = [c for c in read_jsonl(os.path.join(results_dir, "controls.jsonl")) if c.get("tested_commit") == commit]
    latest_controls = {}
    for run in controls:
        for item in run.get("results", []):
            latest_controls[item["id"]] = {**item, "dirty": run.get("worktree_dirty")}
    missing = [c for c in REQUIRED_CONTROLS if c not in latest_controls]
    failed = [c for c in REQUIRED_CONTROLS if c in latest_controls and not latest_controls[c]["passed"]]
    gates.append({"gate": "native_engine_controls", "description": "fixed-pair constraint controls, three distinct "
                  "defenses, endpoint/touching-band semantics, candidate-specific follow-ups (engine, not HTTP)",
                  "status": "failed" if failed else "blocked" if missing else "passed",
                  "missing": missing, "failed": failed})
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
    findings = []
    if findings_path and os.path.exists(findings_path):
        with open(findings_path, encoding="utf-8") as handle:
            findings = json.load(handle).get("findings", [])
    open_p0 = [f["id"] for f in findings if f.get("severity") == "P0" and f.get("status") not in ("closed", "retested")]
    gates.append({"gate": "no_unresolved_p0", "status": "passed" if not open_p0 else "failed",
                  "description": "evaluation/findings.json lists no open P0", "open_p0": open_p0})
    gates.append({"gate": "live_gemini_qualification", "status": "not_run", "required": False,
                  "description": "NOT a current acceptance gate. Live lanes are disabled; activation needs a new "
                                 "explicit user instruction. Placeholder runs are not Gemini evidence."})
    required = [g for g in gates if g.get("required", True)]
    overall = ("passed" if all(g["status"] == "passed" for g in required) and not dirty else
               "failed" if any(g["status"] == "failed" for g in required) else "blocked")
    return {"schema": "drbean-release-gates/v1", "tested_commit": commit, "worktree_dirty": dirty,
            "overall": overall, "gates": gates,
            "statement": "Gates read recorded evidence only; they dispatch no provider or scientific work."}
