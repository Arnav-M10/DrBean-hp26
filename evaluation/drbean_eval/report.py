"""Markdown evaluation report from the append-only attempt ledger and recorded evidence.

Counts and denominators only. No percentiles, no model ranking, no invented cost.
Every attempt is listed, including unrun and failed ones. Scientific jobs (real local
computation) and external model requests are counted separately; a placeholder or
controlled call is never a model request, and an unverified count is reported unknown.
"""
from __future__ import annotations

import json
import os
from collections import Counter, defaultdict

from . import gates as gates_mod, history, manifest as manifest_mod
from .budget import BudgetLedger
from .runner import STATUSES, git_state, read_attempts

LEGACY_NOTE = ("Records with manifest_version 1 / harness 0.1.0 are the pre-merge inventory: 34 entries recorded "
               "before the backend and science package were merged, all `unrun` with a stale reason. They are kept "
               "byte-for-byte and interpreted as written, never relabelled as current results.")


def _jsonl(path: str) -> list[dict]:
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def render(root: str, results_dir: str) -> str:
    manifest = manifest_mod.load(root)
    rules = manifest.get("lanes") or manifest_mod.LANE_RULES
    attempts = read_attempts(results_dir)
    scheduled = {"fixture_contract": len(manifest["schedule"]["fixture_contract"]),
                 "actual_full_stack": len(manifest["schedule"]["actual_full_stack"]),
                 "offline_real_science": len(manifest["schedule"].get("offline_real_science", []))}
    for entry in manifest["schedule"]["live"]:
        scheduled[entry["lane"]] = scheduled.get(entry["lane"], 0) + 1
    by_lane = defaultdict(list)
    for attempt in attempts:
        by_lane[attempt["lane"]].append(attempt)
    problems = history.verify(results_dir)
    out = ["# Dr. Bean evaluation report", "",
           "Generated from `attempts.jsonl` (append-only, hash-chained since harness 0.2.0). Feasibility evidence "
           "from a small portfolio, not a statistical benchmark. No live model request was permitted or made: "
           "live lanes are disabled (NOT_RUN) and any AI in the current lanes is absent or a labelled controlled "
           "placeholder. Fresh native replay re-runs the project's own checker; it is not an independent proof.", "",
           f"- Manifest version {manifest['manifest_version']} (ancestry: "
           f"{', '.join('v%d' % a['manifest_version'] for a in manifest.get('supersedes', [])) or 'none'}), contract "
           f"{manifest['contract']['revision']} / {manifest['contract']['wire_profile']}",
           f"- Holdouts: {manifest['holdouts']['status']}",
           f"- Attempts recorded: {len(attempts)}; history verification: "
           f"{'OK' if not problems else 'FAILED: ' + '; '.join(problems[:3])}",
           f"- Live activation: {manifest.get('live_activation', 'disabled')}", "",
           "## Lanes", "",
           "| Lane | v | Enabled | Provider | Tools | Scheduled | Attempts | " + " | ".join(STATUSES) + " |",
           "|---|---|---|---|---|---|---|" + "---|" * len(STATUSES)]
    for lane in manifest_mod.LANES:
        rule = rules.get(lane, {})
        counts = Counter(a["status"] for a in by_lane.get(lane, []))
        enabled = "yes" if rule.get("enabled") else "NOT_RUN (disabled)"
        out.append(f"| {lane} | {rule.get('version', 1)} | {enabled} | {'/'.join(rule.get('provider', []))} | "
                   f"{rule.get('tools') or 'any'} | {scheduled.get(lane, 0)} | {len(by_lane.get(lane, []))} | "
                   + " | ".join(str(counts.get(s, 0)) for s in STATUSES) + " |")
    out += ["", LEGACY_NOTE, "",
            "Evidence classes: `executed_acceptance` (the runner executed the subject against a stack it launched "
            "and re-verified the evidence), `imported_claim` (recorded observations; never qualification).", ""]
    current = [a for a in attempts if a.get("harness_version") != "0.1.0"]
    classes = Counter(a.get("evidence_class") or "none" for a in current)
    out.append("Evidence class counts (harness >= 0.2.0): "
               + (", ".join(f"{k}: {v}" for k, v in sorted(classes.items())) or "none") + ".")
    out += ["", "## Latest attempt per scheduled entry", ""]
    latest = {}
    for attempt in attempts:
        latest[(attempt["lane"], attempt["entry_id"])] = attempt
    out += ["| Lane | Entry | Status | Commit | Dirty | Reason |", "|---|---|---|---|---|---|"]
    for (lane, entry), attempt in sorted(latest.items()):
        out.append(f"| {lane} | {entry} | {attempt['status']} | {(attempt['tested_commit'] or '')[:10]} | "
                   f"{attempt['worktree_dirty']} | {(attempt['reason'] or '').replace('|', '/')[:220]} |")
    out += ["", "## Scientific jobs and external model requests (separate counts)", ""]
    jobs = set()
    for attempt in attempts:
        jobs.update(attempt.get("job_ids") or [])
    verified = [a for a in attempts if (a.get("external_model_requests") or {}).get("value") == 0]
    unknown = [a for a in attempts if a.get("lane") == "offline_real_science"
               and (a.get("external_model_requests") or {}).get("value") is None and a["status"] != "unrun"]
    legacy_requests = [a["provider_requests"] for a in attempts if a.get("harness_version") == "0.1.0"
                       and a.get("provider_requests") is not None]
    out += [f"- Distinct scientific jobs started through the real API (deduplicated by job id across attempts): "
            f"{len(jobs)}. This accumulated count spans historical attempts; see each attempt for its "
            "scientific outcome and the latest-entry table for current results.",
            f"- External model requests: verified zero by the egress guard in {len(verified)} attempt(s); "
            f"unknown in {len(unknown)} attempt(s); legacy records reporting requests: {len(legacy_requests)}. "
            "Verified zero means zero actual model requests and zero model usage in that run, not 'unknown'.",
            "- Synthetic budget-ledger reservations in unit tests use temporary stores and are not provider charges.",
            "- Durations are harness wall time on loopback; they are not provider latency."]
    ledger = BudgetLedger(os.path.join(root, "ledger", "provider_budget.jsonl")).state()
    out.append("- Harness budget ledger: " + (f"cohort `{ledger['cohort']['cohort_id']}` (unexpected; investigate)"
                                              if ledger["cohort"] else "no cohort opened; none may be opened now."))
    controls = _jsonl(os.path.join(results_dir, "controls.jsonl"))
    if controls:
        last = controls[-1]
        out += ["", "## Engine-level native controls (latest run; engine public operations, not HTTP)", "",
                f"Commit {last['tested_commit'][:10]}, interpreter {last['interpreter'].get('implementation')} "
                f"{last['interpreter'].get('version')}.", "", "| Control | Result | Observed |", "|---|---|---|"]
        for item in last["results"]:
            observed = json.dumps(item["observed"], sort_keys=True)[:160].replace("|", "/")
            out.append(f"| {item['id']} | {'passed' if item['passed'] else 'FAILED'} | {observed} |")
    state = git_state(os.path.dirname(root))
    gate = gates_mod.compute(root, results_dir, state["commit"], state["dirty"], os.path.join(root, "findings.json"))
    out += ["", f"## Release gates at {(state['commit'] or '')[:10]} (overall: {gate['overall']})", "",
            "| Gate | Status |", "|---|---|"]
    out += [f"| {g['gate']} | {g['status']} |" for g in gate["gates"]]
    findings_path = os.path.join(root, "findings.json")
    if os.path.exists(findings_path):
        with open(findings_path, encoding="utf-8") as handle:
            findings = json.load(handle)["findings"]
        out += ["", "## Findings (evaluation/findings.json)", "", "| ID | Sev | Owner | Status | Title |",
                "|---|---|---|---|---|"]
        out += [f"| {f['id']} | {f['severity']} | {f['owner']} | {f['status']} | {f['title'].replace('|', '/')} |"
                for f in findings]
    out += ["", "## Every attempt", "",
            "| # | Entry | Lane | Attempt | Status | Class | Commit | Dirty | Duration ms | Reason |",
            "|---|---|---|---|---|---|---|---|---|---|"]
    for index, a in enumerate(attempts, 1):
        out.append(f"| {index} | {a['entry_id']} | {a['lane']} | {a['attempt_number']} | {a['status']} | "
                   f"{a.get('evidence_class') or '—'} | {(a['tested_commit'] or '')[:10]} | {a['worktree_dirty']} | "
                   f"{a['duration_ms']} | {(a['reason'] or '').replace('|', '/')[:160]} |")
    return "\n".join(out) + "\n"
