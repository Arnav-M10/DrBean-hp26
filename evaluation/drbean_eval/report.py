"""Markdown evaluation report from the append-only attempt ledger.

Counts and denominators only. No percentiles, no model ranking, no invented
cost. Every attempt is listed, including unrun and failed ones.
"""
from __future__ import annotations

import os
from collections import Counter, defaultdict

from . import manifest as manifest_mod
from .budget import BudgetLedger
from .runner import STATUSES, read_attempts


def render(root: str, results_dir: str) -> str:
    manifest = manifest_mod.load(root)
    attempts = read_attempts(results_dir)
    scheduled = {"fixture_contract": len(manifest["schedule"]["fixture_contract"]),
                 "actual_full_stack": len(manifest["schedule"]["actual_full_stack"])}
    for entry in manifest["schedule"]["live"]:
        scheduled[entry["lane"]] = scheduled.get(entry["lane"], 0) + 1
    by_lane = defaultdict(list)
    for attempt in attempts:
        by_lane[attempt["lane"]].append(attempt)
    out = ["# Dr. Bean evaluation report", "",
           "Generated from `attempts.jsonl` (append-only). This is feasibility evidence from a small "
           "portfolio, not a statistical benchmark. Proposed caps are ceilings, not measurements.", "",
           f"- Manifest version {manifest['manifest_version']}, contract {manifest['contract']['revision']} / "
           f"{manifest['contract']['wire_profile']}, modality {manifest['modality']['chosen']}",
           f"- Holdouts: {manifest['holdouts']['status']}",
           f"- Attempts recorded: {len(attempts)}", "", "## Counts by evidence lane", "",
           "| Lane | Mode | Scheduled entries | Attempts | " + " | ".join(STATUSES) + " |",
           "|---|---|---|---|" + "---|" * len(STATUSES)]
    for lane in manifest_mod.LANES:
        counts = Counter(a["status"] for a in by_lane.get(lane, []))
        out.append(f"| {lane} | {manifest_mod.MODES[lane]} | {scheduled.get(lane, 0)} | "
                   f"{len(by_lane.get(lane, []))} | " + " | ".join(str(counts.get(s, 0)) for s in STATUSES) + " |")
    out += ["", "A scheduled entry with no attempt has not been run. `unrun` attempts record why. "
            "Lanes are never merged: a fixture pass is not live evidence.", "",
            "## Latest attempt per scheduled entry", ""]
    latest = {}
    for attempt in attempts:
        latest[(attempt["lane"], attempt["entry_id"])] = attempt
    counts = Counter(a["status"] for a in latest.values())
    out.append("Latest status over " + str(len(latest)) + " attempted entries: "
               + (", ".join(f"{counts[s]} {s}" for s in STATUSES if counts.get(s)) or "none") + ".")
    axis = defaultdict(lambda: Counter())
    for attempt in latest.values():
        for name, tally in ((attempt.get("grade") or {}).get("by_axis") or {}).items():
            axis[name]["passed"] += tally["passed"]
            axis[name]["failed"] += tally["failed"]
    if axis:
        out += ["", "Assertion outcomes by axis (decision quality and enforcement are reported separately):", "",
                "| Axis | Passed | Failed |", "|---|---|---|"]
        out += [f"| {name} | {tally['passed']} | {tally['failed']} |" for name, tally in sorted(axis.items())]
    reasons = Counter((a["status"], a["reason"]) for a in attempts if a["status"] != "passed")
    out += ["", "## Failure and unrun categories (all attempts)", ""]
    out += [f"- {count} × `{status}`: {reason}" for (status, reason), count in reasons.most_common()] or ["- none"]
    requests = [a["provider_requests"] for a in attempts if a.get("provider_requests") is not None]
    jobs = [a["scientific_jobs"] for a in attempts if a.get("scientific_jobs") is not None]
    out += ["", "## Provider requests, scientific jobs and durations", "",
            f"- Provider requests reported by subjects: {sum(requests)} across {len(requests)} attempts "
            f"(case attempts and provider requests are counted separately).",
            f"- Scientific jobs reported: {sum(jobs)} across {len(jobs)} attempts.",
            "- Durations below are harness wall time per attempt (monotonic). They include no human review "
            "time and are not provider latency unless a trace's `timings` says so."]
    ledger = BudgetLedger(os.path.join(root, "ledger", "provider_budget.jsonl")).state()
    if ledger["cohort"]:
        out.append(f"- Shared budget ledger: cohort `{ledger['cohort']['cohort_id']}`, committed "
                   f"{ledger['committed']}, remaining {ledger['remaining']}, "
                   f"{len(ledger['unreconciled'])} unreconciled reservation(s).")
    else:
        out.append("- Shared budget ledger: no cohort opened; zero live provider requests were permitted. "
                   "Cost is therefore not estimated.")
    out += ["", "## Every attempt", "",
            "| # | Entry | Lane | Attempt | Status | Commit | Dirty | Duration ms | Requests | Reason / failed ids |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for index, a in enumerate(attempts, 1):
        out.append(f"| {index} | {a['entry_id']} | {a['lane']} | {a['attempt_number']} | {a['status']} | "
                   f"{(a['tested_commit'] or '')[:10]} | {a['worktree_dirty']} | {a['duration_ms']} | "
                   f"{a['provider_requests'] if a['provider_requests'] is not None else '—'} | "
                   f"{(a['reason'] or '').replace('|', '/')} |")
    return "\n".join(out) + "\n"
