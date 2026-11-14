"""Runs scheduled entries against a subject and appends attempt records.

Every scheduled entry yields exactly one appended record per run, whatever
happened: passed, failed, unrun, refused, timed_out, budget_stopped or error.
Records are append-only and hash-chained (see history.py); earlier results are
never rewritten.

Lanes follow the manifest's lane rules. Live-provider lanes are disabled: a run
records them ``unrun`` unless code passes an explicit activation object, which the
CLI never does (unit tests use a synthetic one with an isolated ledger). Entries
without frozen case assertions (``offline_real_science``, legacy
``actual_full_stack``) are qualified by ``qualify.py``; a reported
``state: completed`` alone never passes.
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import time
import uuid
from datetime import datetime, timezone

from . import HARNESS_VERSION, history, manifest as manifest_mod, qualify, sanitize
from .assertions import grade
from .budget import BudgetLedger, BudgetStop, UsageRejected
from .subject import SubjectRefused, SubjectTimeout, SubjectUnavailable

STATUSES = ("passed", "failed", "unrun", "refused", "timed_out", "skipped", "budget_stopped", "error")
OPERATIONS = ("intake", "agent", "design", "follow_up", "science")


class LiveActivation:
    """Explicit permission to dispatch a live-provider lane. The CLI never constructs one."""

    def __init__(self, instruction_reference: str, ledger_is_isolated: bool):
        if not instruction_reference.strip():
            raise ValueError("a live activation must cite the user instruction that authorized it")
        self.instruction_reference = instruction_reference
        self.ledger_is_isolated = ledger_is_isolated


class SyntheticActivation(LiveActivation):
    """For the harness's own unit tests: a stub subject and an isolated temporary ledger, no provider."""

    def __init__(self, note: str = "harness unit test: stub subject, isolated ledger, no provider"):
        super().__init__(note, ledger_is_isolated=True)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def git_state(repo: str) -> dict:
    def run(*args):
        return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True).stdout
    # Recorded results and the budget ledger are evidence outputs, not inputs to the tested code.
    # Porcelain lines are "XY path"; never strip the whole output, which would eat the first line's
    # leading status space and make that path unrecognisable (harness 0.1.0 marked every record dirty).
    changed = []
    for line in run("status", "--porcelain", "--untracked-files=all").splitlines():
        path = line[3:].split(" -> ")[-1].strip('"')
        if line.strip() and not path.startswith(("evaluation/results/", "evaluation/ledger/")):
            changed.append(path)
    return {"commit": run("rev-parse", "HEAD").strip() or None, "dirty": bool(changed), "changed": changed[:20]}


def read_attempts(results_dir: str) -> list[dict]:
    path = os.path.join(results_dir, "attempts.jsonl")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def lane_rules(manifest: dict, lane: str) -> dict:
    rules = (manifest.get("lanes") or manifest_mod.LANE_RULES).get(lane)
    if rules is None:
        raise ValueError(f"lane {lane!r} is not declared by manifest v{manifest.get('manifest_version')}")
    return rules


def _check_attestation(observation: dict, lane: str, operation: str, case_sha: str | None, commit: str | None,
                       rules: dict | None = None):
    """A result in one lane cannot be relabelled as another."""
    rules = rules or manifest_mod.LANE_RULES[lane]
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
    if rules.get("live_provider") and transport != "live":
        return "a controlled or absent provider cannot be recorded in a live lane"
    if not rules.get("live_provider") and transport not in rules.get("provider", ["controlled", "none"]):
        return f"provider transport {transport!r} is not admitted in the offline lane {lane}"
    tools = (observation.get("tools") or {}).get("transport")
    if rules.get("tools") == "real" and tools != "real":
        return ("full-stack lane requires real scientific tools, not controlled outcomes" if lane == "actual_full_stack"
                else f"{lane} requires real scientific tools, not controlled outcomes")
    if rules.get("tools") == "controlled" and tools != "controlled":
        return "controlled-tool lane must attest controlled tool outcomes"
    if rules.get("zero_dispatch_required"):
        if observation.get("provider_requests") != 0:
            return "an offline lane observation must report exactly zero provider requests"
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
            ids.append(ledger.reserve("owner05-harness", f"{entry['lane']} request slot {index + 1}/{count}",
                                      entry["entry_id"], alloc["max_input_tokens"], alloc["max_output_tokens"],
                                      "manifest request_allocation; enforceable only when the provider layer "
                                      "counts input tokens and sets max output tokens before dispatch"))
    except BudgetStop:
        for reservation_id in ids:
            ledger.release_unsent(reservation_id, "invocation not started: later slot did not fit")
        raise
    return ids


def _reconcile(ledger: BudgetLedger, ids: list[str], observation: dict | None, failure: str | None,
               trusted: bool = True) -> str | None:
    """Unknown usage stays reserved; only provably unsent slots are released.

    Returns a problem string when usage could not be trusted; the attempt then fails.
    An untrusted observation (attestation rejected) never refunds anything.
    """
    if not trusted:
        for reservation_id in ids:
            ledger.mark_unknown(reservation_id, "observation rejected; reported usage is not trusted")
        return None
    requests = ((observation or {}).get("usage") or {}).get("requests")
    if requests is None:
        for reservation_id in ids:
            ledger.mark_unknown(reservation_id, failure or "subject reported no usage metadata")
        return None
    if not isinstance(requests, list) or not all(isinstance(r, dict) for r in requests):
        for reservation_id in ids:
            ledger.mark_unknown(reservation_id, "usage_rejected: requests is not a list of objects")
        return "usage report is malformed; every slot stays reserved at its maximum"
    problem = None
    if len(requests) > len(ids):
        problem = f"subject reported {len(requests)} requests for {len(ids)} reserved slots (unreserved dispatch)"
        ledger.record_error("reconcile", problem)
    for reservation_id, request in zip(ids, requests):
        attempts = request.get("network_attempts", 1)
        try:
            if request.get("acceptance") == "known" and "input_tokens" in request and "output_tokens" in request:
                ledger.reconcile(reservation_id, request["input_tokens"], request["output_tokens"],
                                 request.get("outcome", "completed"), request.get("provider_request_id"), attempts)
            else:
                ledger.mark_unknown(reservation_id, request.get("outcome", "acceptance unknown"), attempts)
        except UsageRejected as error:
            ledger.mark_unknown(reservation_id, f"usage_rejected: {error}", attempts)
            problem = problem or f"usage rejected: {error}"
    for reservation_id in ids[len(requests):]:
        ledger.release_unsent(reservation_id, "subject attested this slot was never dispatched")
    return problem


def _entries(manifest: dict, lane: str) -> list[dict]:
    schedule = manifest["schedule"]
    if lane == "fixture_contract":
        return [dict(e, lane=lane) for e in schedule["fixture_contract"]]
    if lane == "actual_full_stack":
        return schedule["actual_full_stack"]
    if lane == "offline_real_science":
        return schedule.get("offline_real_science", [])
    return [e for e in schedule["live"] if e["lane"] == lane]


def run_lane(lane: str, subject, root: str, results_dir: str, repo: str, only=None,
             ledger_path: str | None = None, live_activation: LiveActivation | None = None) -> list[dict]:
    manifest = manifest_mod.load(root)
    problems = manifest_mod.verify(root)
    if problems:
        raise RuntimeError("manifest does not verify: " + "; ".join(problems))
    rules = lane_rules(manifest, lane)
    entries = _entries(manifest, lane)
    if only:
        entries = [e for e in entries if e["entry_id"] in only or e.get("case_id") in only]
    os.makedirs(os.path.join(results_dir, "traces"), exist_ok=True)
    prior = read_attempts(results_dir)
    state = git_state(repo)
    manifest_sha = manifest_mod.sha256_file(os.path.join(root, "manifest.json"))
    ledger = BudgetLedger(ledger_path or os.path.join(root, "ledger", "provider_budget.jsonl"))
    live_disabled = rules.get("live_provider") and live_activation is None
    lane_run_id = "lane_" + uuid.uuid4().hex[:16]
    lane_info = {"lane_run_id": lane_run_id, "lane": lane, "lane_version": rules.get("version"),
                 "started_at": _utc(), "tested_commit": state["commit"], "worktree_dirty": state["dirty"]}
    if hasattr(subject, "begin_lane") and not live_disabled:
        try:
            lane_info["subject_start"] = sanitize.sanitize(subject.begin_lane(lane, results_dir))
        except Exception as error:  # a failed launch is recorded on every entry, never a crash
            lane_info["subject_start_error"] = f"{type(error).__name__}: {error}"
    described = sanitize.sanitize(subject.describe())
    records = []
    try:
        for entry in entries:
            records.append(_run_entry(entry, lane, rules, subject, root, results_dir, manifest, manifest_sha,
                                      prior + records, state, ledger, described, lane_info, live_disabled,
                                      live_activation))
    finally:
        if hasattr(subject, "end_lane") and not live_disabled:
            try:
                lane_info["subject_end"] = sanitize.sanitize(subject.end_lane())
            except Exception as error:
                lane_info["subject_end_error"] = f"{type(error).__name__}: {error}"
        lane_info["ended_at"] = _utc()
        lane_info["attempt_ids"] = [r["attempt_id"] for r in records]
        lane_info["statuses"] = {s: sum(r["status"] == s for r in records) for s in STATUSES if any(
            r["status"] == s for r in records)}
        with open(os.path.join(results_dir, "lane-runs.jsonl"), "a", encoding="utf-8") as handle:
            handle.write(json.dumps(lane_info, sort_keys=True, ensure_ascii=False, default=str) + "\n")
    return records


def _run_entry(entry, lane, rules, subject, root, results_dir, manifest, manifest_sha, prior, state, ledger,
               described, lane_info, live_disabled, live_activation) -> dict:
    case_id = entry.get("case_id")
    variant = manifest_mod.load_case(root, case_id)["variants"][entry["variant"]] if case_id else {}
    operation = variant.get("operation") or entry.get("operation")
    packet = entry.get("packet")
    case_sha = (manifest["cases"][case_id]["sha256"] if case_id
                else (manifest.get("science_packets", {}).get(packet) or {}).get("sha256") if packet else None)
    attempt_id = "att_" + uuid.uuid4().hex[:16]
    record = {
        "attempt_id": attempt_id, "lane_run_id": lane_info["lane_run_id"],
        "entry_id": entry["entry_id"], "case_id": case_id, "variant": entry.get("variant"), "packet": packet,
        "lane": lane, "lane_version": rules.get("version"), "mode": manifest_mod.MODES[lane],
        "operation": operation,
        "attempt_number": 1 + sum(1 for a in prior if a["entry_id"] == entry["entry_id"] and a["lane"] == lane),
        "manifest_version": manifest["manifest_version"], "manifest_sha256": manifest_sha,
        "case_sha256": case_sha, "tested_commit": state["commit"], "worktree_dirty": state["dirty"],
        "harness_version": HARNESS_VERSION, "python": platform.python_version(),
        "runtime": {"system": platform.system(), "machine": platform.machine()}, "subject": described,
        "started_at": _utc(), "status": "error", "reason": None, "provider_requests": None,
        "external_model_requests": None, "scientific_jobs": None, "versions": None, "grade": None, "trace": None,
        "evidence_class": None, "qualification": None,
    }
    clock = time.monotonic()
    observation, reserved, failure, trusted = None, [], None, True
    evidence_dir = None
    try:
        if live_disabled:
            raise SubjectUnavailable("live lane disabled (NOT_RUN): " + manifest.get("live_activation",
                                                                                       manifest_mod.LIVE_ACTIVATION))
        if lane_info.get("subject_start_error"):
            raise SubjectUnavailable("local test stack did not start: " + lane_info["subject_start_error"])
        if rules.get("cohort"):
            if not ledger.state()["cohort"]:
                raise SubjectUnavailable("no human-authorized provider cohort is open in the shared budget "
                                         "ledger; live requests are not permitted")
            reserved = _reserve(ledger, entry, "intake" if operation == "intake" else "agent", manifest["caps"])
        if getattr(subject, "accepts_context", False):
            evidence_dir = os.path.join(results_dir, "traces", attempt_id)
            subject.attempt_context = {"attempt_id": attempt_id, "evidence_dir": evidence_dir,
                                       "tested_commit": state["commit"], "case_sha256": case_sha,
                                       "lane_version": rules.get("version")}
        observation = subject.run_entry(entry, variant, lane)
        problem = _check_attestation(observation, lane, operation, case_sha, state["commit"], rules)
        if problem:
            trusted = False
            record.update(status="error", reason="attestation rejected: " + problem)
        elif not case_id:
            evidence_class = ("executed_acceptance" if getattr(subject, "executes_acceptance", False)
                              and evidence_dir else "imported_claim")
            outcome = qualify.qualify(observation, evidence_dir=evidence_dir, evidence_class=evidence_class,
                                      science_python=getattr(subject, "science_python", None),
                                      package_dir=getattr(subject, "package_dir", None))
            record.update(status=outcome["status"], reason=outcome["reason"], evidence_class=evidence_class,
                          qualification={"qualifier_checks": outcome["qualifier_checks"],
                                         "executed_checks": observation.get("checks")})
        else:
            result = grade(variant["expected"], observation)
            record.update(status="passed" if result["passed"] else "failed", grade=result,
                          evidence_class="executed_acceptance" if getattr(subject, "executes_acceptance", False)
                          else "imported_claim",
                          reason=None if result["passed"] else "failed assertions: " + ", ".join(result["failed_ids"]))
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
        try:
            if record["status"] == "unrun":
                for reservation_id in reserved:
                    ledger.release_unsent(reservation_id, "subject unavailable before any dispatch")
            else:
                problem = _reconcile(ledger, reserved, observation, failure, trusted)
                if problem and record["status"] == "passed":
                    record.update(status="failed", reason=problem)
        except Exception as error:  # reconciliation failure is recorded; reservations stay open
            ledger.record_error(entry["entry_id"], f"{type(error).__name__}: {error}")
            record.update(status="error", reason=f"reconciliation failed and was recorded: {type(error).__name__}")
    record["ended_at"] = _utc()
    record["duration_ms"] = round((time.monotonic() - clock) * 1000, 3)
    if isinstance(observation, dict):
        record["provider_requests"] = observation.get("provider_requests")
        record["scientific_jobs"] = observation.get("scientific_jobs")
        record["versions"] = sanitize.sanitize(observation.get("versions"))
        record["timings"] = observation.get("timings")
        dispatch = observation.get("external_dispatch") or {}
        if rules.get("zero_dispatch_required"):
            verified, _ = qualify.zero_dispatch(observation)
            record["external_model_requests"] = {"value": 0 if verified else None,
                                                 "basis": "verified by egress guard" if verified else "unknown"}
            record["external_dispatch"] = sanitize.sanitize(dispatch)
        for key in ("records", "placeholder_identity", "job_ids", "input_digest"):
            if key in observation:
                record[key] = sanitize.sanitize(observation[key])
        trace = {"attempt_id": attempt_id, "entry_id": entry["entry_id"], "lane": lane,
                 "input": variant.get("input"), "controlled": variant.get("controlled"),
                 "observation": sanitize.sanitize(observation)}
        text = json.dumps(trace, indent=2, sort_keys=True, ensure_ascii=False, default=str)
        leaks = sanitize.find_leaks(text)
        if leaks:  # keep the attempt, withhold the trace, and fail on privacy
            record.update(status="failed", reason=f"sanitized trace still contains {leaks}; trace withheld")
        else:
            rel = os.path.join("traces", attempt_id + ".json")
            with open(os.path.join(results_dir, rel), "w", encoding="utf-8") as handle:
                handle.write(text + "\n")
            record["trace"] = rel
            record["trace_sha256"] = history.file_digest(os.path.join(results_dir, rel))
        if evidence_dir and isinstance(observation.get("evidence_index"), dict):
            index = observation["evidence_index"]
            with open(os.path.join(evidence_dir, "index.json"), "w", encoding="utf-8") as handle:
                json.dump(index, handle, sort_keys=True, indent=1)
            record["evidence_dir"] = os.path.relpath(evidence_dir, results_dir)
            record["evidence_index_sha256"] = history.index_digest(index)
    path = os.path.join(results_dir, "attempts.jsonl")
    record["prev_record_sha256"] = history.last_digest(path)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, ensure_ascii=False, default=str) + "\n")
    return record
