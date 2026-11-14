"""Runs scheduled entries against a subject and appends attempt records.

Every scheduled entry yields exactly one appended record per run, whatever
happened: passed, failed, unrun, refused, timed_out, budget_stopped or error.
Records are append-only; earlier results are never rewritten.
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import time
import uuid
from datetime import datetime, timezone

from . import HARNESS_VERSION, manifest as manifest_mod, sanitize
from .assertions import grade
from .budget import BudgetLedger, BudgetStop
from .subject import SubjectRefused, SubjectTimeout, SubjectUnavailable

STATUSES = ("passed", "failed", "unrun", "refused", "timed_out", "skipped", "budget_stopped", "error")
OPERATIONS = ("intake", "agent", "design", "follow_up")


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def git_state(repo: str) -> dict:
    def run(*args):
        return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True).stdout.strip()
    # Recorded results and the budget ledger are evidence outputs, not inputs to the tested code.
    changed = [line for line in run("status", "--porcelain").splitlines()
               if not line[3:].startswith(("evaluation/results/", "evaluation/ledger/"))]
    return {"commit": run("rev-parse", "HEAD") or None, "dirty": bool(changed)}


def read_attempts(results_dir: str) -> list[dict]:
    path = os.path.join(results_dir, "attempts.jsonl")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _check_attestation(observation: dict, lane: str, operation: str, case_sha: str | None, commit: str | None):
    """A result in one lane cannot be relabelled as another."""
    if not isinstance(observation, dict):
        return "observation is not an object"
    if observation.get("schema") != "eval-observation/v1":
        return "observation does not declare schema eval-observation/v1"
    if observation.get("lane") != lane:
        return f"observation attests lane {observation.get('lane')!r}, scheduled lane is {lane!r}"
    transport = (observation.get("provider") or {}).get("transport")
    if transport not in ("controlled", "live", "none"):
        return "observation does not attest provider.transport"
    if lane == "fixture_contract" and transport == "live":
        return "a live provider was used in the fixture lane"
    if lane != "fixture_contract" and transport != "live":
        return "a controlled or absent provider cannot be recorded in a live lane"
    tools = (observation.get("tools") or {}).get("transport")
    if lane == "actual_full_stack" and tools != "real":
        return "full-stack lane requires real scientific tools, not controlled outcomes"
    if lane == "live_agent_controlled_tools" and tools != "controlled":
        return "controlled-tool lane must attest controlled tool outcomes"
    if observation.get("operation") != operation:
        return f"observation operation {observation.get('operation')!r} does not match {operation!r}"
    if case_sha and observation.get("case_sha256") != case_sha:
        return "observation was produced for a different case digest"
    if commit and observation.get("tested_commit") != commit:
        return "observation was produced at a different commit than the tested checkout"
    return None


def _reserve(ledger: BudgetLedger, entry: dict, kind: str, caps: dict) -> list[str]:
    alloc, count = caps["request_allocation"][kind], caps["invocation"][kind]["provider_requests"]
    ids = []
    try:
        for index in range(count):
            ids.append(ledger.reserve("owner04-harness", f"{entry['lane']} request slot {index + 1}/{count}",
                                      entry["entry_id"], alloc["max_input_tokens"], alloc["max_output_tokens"],
                                      "manifest request_allocation; enforceable only when the provider layer "
                                      "counts input tokens and sets max output tokens before dispatch"))
    except BudgetStop:
        for reservation_id in ids:
            ledger.release_unsent(reservation_id, "invocation not started: later slot did not fit")
        raise
    return ids


def _reconcile(ledger: BudgetLedger, ids: list[str], observation: dict | None, failure: str | None):
    """Unknown usage stays reserved; only provably unsent slots are released."""
    requests = ((observation or {}).get("usage") or {}).get("requests")
    if requests is None:
        for reservation_id in ids:
            ledger.mark_unknown(reservation_id, failure or "subject reported no usage metadata")
        return
    for reservation_id, request in zip(ids, requests):
        if request.get("acceptance") == "known" and "input_tokens" in request and "output_tokens" in request:
            ledger.reconcile(reservation_id, request["input_tokens"], request["output_tokens"],
                             request.get("outcome", "completed"), request.get("provider_request_id"),
                             request.get("network_attempts", 1))
        else:
            ledger.mark_unknown(reservation_id, request.get("outcome", "acceptance unknown"),
                                request.get("network_attempts", 1))
    for reservation_id in ids[len(requests):]:
        ledger.release_unsent(reservation_id, "subject attested this slot was never dispatched")


def run_lane(lane: str, subject, root: str, results_dir: str, repo: str, only=None,
             ledger_path: str | None = None) -> list[dict]:
    manifest = manifest_mod.load(root)
    problems = manifest_mod.verify(root)
    if problems:
        raise RuntimeError("manifest does not verify: " + "; ".join(problems))
    if lane == "fixture_contract":
        entries = [dict(e, lane=lane) for e in manifest["schedule"]["fixture_contract"]]
    elif lane == "actual_full_stack":
        entries = manifest["schedule"]["actual_full_stack"]
    else:
        entries = [e for e in manifest["schedule"]["live"] if e["lane"] == lane]
    if only:
        entries = [e for e in entries if e["entry_id"] in only or e.get("case_id") in only]
    os.makedirs(os.path.join(results_dir, "traces"), exist_ok=True)
    prior = read_attempts(results_dir)
    state = git_state(repo)
    described = sanitize.sanitize(subject.describe())
    manifest_sha = manifest_mod.sha256_file(os.path.join(root, "manifest.json"))
    ledger = BudgetLedger(ledger_path or os.path.join(root, "ledger", "provider_budget.jsonl"))
    records = []
    for entry in entries:
        case_id = entry.get("case_id")
        variant = manifest_mod.load_case(root, case_id)["variants"][entry["variant"]] if case_id else {}
        operation = variant.get("operation") or entry.get("operation")
        case_sha = manifest["cases"][case_id]["sha256"] if case_id else None
        record = {
            "attempt_id": "att_" + uuid.uuid4().hex[:16],
            "entry_id": entry["entry_id"], "case_id": case_id, "variant": entry.get("variant"),
            "lane": lane, "mode": manifest_mod.MODES[lane], "operation": operation,
            "attempt_number": 1 + sum(1 for a in prior + records
                                      if a["entry_id"] == entry["entry_id"] and a["lane"] == lane),
            "manifest_version": manifest["manifest_version"], "manifest_sha256": manifest_sha,
            "case_sha256": case_sha, "tested_commit": state["commit"], "worktree_dirty": state["dirty"],
            "harness_version": HARNESS_VERSION, "python": platform.python_version(), "subject": described,
            "started_at": _utc(), "status": "error", "reason": None, "provider_requests": None,
            "scientific_jobs": None, "versions": None, "grade": None, "trace": None,
        }
        clock = time.monotonic()
        observation, reserved, failure = None, [], None
        try:
            if lane != "fixture_contract":
                if not ledger.state()["cohort"]:
                    raise SubjectUnavailable("no human-authorized provider cohort is open in the shared budget "
                                             "ledger; live requests are not permitted")
                reserved = _reserve(ledger, entry, "intake" if operation == "intake" else "agent",
                                    manifest["caps"])
            observation = subject.run_entry(entry, variant, lane)
            problem = _check_attestation(observation, lane, operation, case_sha, state["commit"])
            if problem:
                record.update(status="error", reason="attestation rejected: " + problem)
            elif not case_id:
                record.update(status="passed" if observation.get("state") == "completed" else "failed",
                              reason="full-stack record: outcome is whatever the real run produced; see trace")
            else:
                result = grade(variant["expected"], observation)
                record.update(status="passed" if result["passed"] else "failed", grade=result,
                              reason=None if result["passed"] else "failed assertions: "
                              + ", ".join(result["failed_ids"]))
        except SubjectUnavailable as error:
            failure = str(error)
            record.update(status="unrun", reason=failure)
        except SubjectRefused as error:
            failure = str(error)
            record.update(status="refused", reason=failure)
        except SubjectTimeout as error:
            failure = str(error)
            record.update(status="timed_out", reason=failure)
        except BudgetStop as error:
            record.update(status="budget_stopped", reason=str(error))
        except Exception as error:  # a harness or subject defect is an attempt outcome, not a crash
            failure = f"{type(error).__name__}: {error}"
            record.update(status="error", reason=failure)
        if reserved:
            if record["status"] == "unrun":
                for reservation_id in reserved:
                    ledger.release_unsent(reservation_id, "subject unavailable before any dispatch")
            else:
                _reconcile(ledger, reserved, observation, failure)
        record["ended_at"] = _utc()
        record["duration_ms"] = round((time.monotonic() - clock) * 1000, 3)
        if isinstance(observation, dict):
            record["provider_requests"] = observation.get("provider_requests")
            record["scientific_jobs"] = observation.get("scientific_jobs")
            record["versions"] = sanitize.sanitize(observation.get("versions"))
            record["timings"] = observation.get("timings")
            trace = {"attempt_id": record["attempt_id"], "entry_id": entry["entry_id"], "lane": lane,
                     "input": variant.get("input"), "controlled": variant.get("controlled"),
                     "observation": sanitize.sanitize(observation)}
            text = json.dumps(trace, indent=2, sort_keys=True, ensure_ascii=False)
            leaks = sanitize.find_leaks(text)
            if leaks:  # keep the attempt, withhold the trace, and fail on privacy
                record.update(status="failed", reason=f"sanitized trace still contains {leaks}; trace withheld")
            else:
                rel = os.path.join("traces", record["attempt_id"] + ".json")
                with open(os.path.join(results_dir, rel), "w", encoding="utf-8") as handle:
                    handle.write(text + "\n")
                record["trace"] = rel
        with open(os.path.join(results_dir, "attempts.jsonl"), "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False) + "\n")
        records.append(record)
    return records
