"""Score one live harness record against the validator's pre-registered predicates L1-L8.

    python3 evaluation/live/score_live_run.py <record.json>

Reads only the retained public record (no store, provider or credential). Each
predicate is "passed", "failed" or "not_run" with the evidence it used. A run
that stops early keeps its stopping code; nothing here relabels a partial run.
"""
from __future__ import annotations

import json
import sys

TERMINAL_ATTEMPTS = {"completed", "failed"}


def score(record: dict) -> dict:
    obs = record.get("observations", {})
    attempts = obs.get("attempts") or []
    events = obs.get("events") or []
    final = obs.get("final") or obs.get("at_failure") or {}
    checks = {row["id"] for row in record.get("checks", [])}
    grant = (obs.get("grant") or {}).get("granted")
    meta = [attempt.get("metadata") or {} for attempt in attempts]
    types = [event.get("type") for event in events]
    out = {}

    def put(key, ok, detail, not_run=False):
        out[key] = {"status": "not_run" if not_run else ("passed" if ok else "failed"), "detail": detail}

    live_caps = (obs.get("capabilities") or {}).get("deepagents", {}).get("execution_mode") == "live"
    gemini_live = bool(meta) and all(m.get("provider") == "gemini" and m.get("execution_mode") == "live" for m in meta)
    answered = any(a.get("state") == "completed" for a in attempts)
    tool_flow = any(t in {"tool_requested", "plan_updated"} for t in types)
    put("L1", live_caps and gemini_live and answered and tool_flow,
        {"deepagents_live": live_caps, "attempts": len(attempts), "all_gemini_live": gemini_live,
         "completed_attempts": sum(a.get("state") == "completed" for a in attempts), "tool_or_plan_events": tool_flow},
        not_run=not attempts)

    consent_at = (obs.get("consent") or {}).get("at")
    bound = bool(meta) and all((m.get("context") or {}).get("consent_id") for m in meta)
    after = bool(consent_at) and all((a.get("created_at") or "") > consent_at for a in attempts)
    consented = bool(checks & {"consent-recorded-through-the-browser", "consent-recorded-through-the-preferred-workspace"})
    put("L2", consented and bound and after,
        {"consent_check": consented, "consent_at": consent_at,
         "every_attempt_bound_to_consent": bound, "every_attempt_after_consent": after}, not_run=not attempts)

    first = obs.get("after_first_advance") or {}
    paused = first.get("pending_review") == "plan" and bool(checks & {"live-plan-stops-for-approval-with-no-child",
                                                                      "live-plan-stops-for-approval-with-no-child-in-the-preferred-workspace"})
    put("L3", paused, {"after_first_advance": first.get("state"), "pending_review": first.get("pending_review"),
                       "error_code": first.get("error_code")}, not_run=not attempts)

    children = final.get("children") or []
    replay = obs.get("replay") or []
    report = obs.get("report") or {}
    computed = any(child.get("state") == "completed" for child in children) and (report.get("native_evidence_count") or 0) >= 1
    put("L4", computed and bool(replay), {"children": [(c.get("kind"), c.get("state")) for c in children],
        "native_evidence": report.get("native_evidence_count"), "outcomes": [r.get("outcome") for r in replay]},
        not_run=not paused)

    linked = types.index("child_linked") if "child_linked" in types else None
    later = types[linked + 1:] if linked is not None else []
    read = "evidence_observed" in later
    acted = read and any(t in {"plan_updated", "review_required", "tool_finished"} for t in later[later.index("evidence_observed") + 1:]) if read else False
    put("L5", read and acted and bool(final.get("reports") or final.get("pending_review")),
        {"evidence_observed_after_child": read, "next_step_after_reading": acted,
         "reports": final.get("reports"), "pending_review": final.get("pending_review")}, not_run=linked is None)

    commentary = report.get("commentary_status")
    downloads = bool(report.get("id")) and bool(replay)
    put("L6", downloads, {"report": report.get("id"), "commentary_status": commentary, "model_failure": report.get("model_failure"),
        "exercised_live": commentary not in (None, "accepted", "grounded", "available")}, not_run=not report)

    reload = obs.get("reload") or {}
    replays_ok = bool(replay) and all(r.get("integrity") == "passed" and r.get("replay") == "passed" for r in replay)
    put("L7", bool(reload.get("passed")) and replays_ok, {"reload": reload, "replay": replay}, not_run=not reload and not replay)

    usage = obs.get("provider_usage") or {}
    count = record.get("physical_requests")
    terminal = all(a.get("state") in TERMINAL_ATTEMPTS for a in attempts)
    no_retry = all(m.get("retry_policy") == "none" and m.get("max_requests") == 1 for m in meta)
    put("L8", type(count) is int and type(grant) is int and count <= grant <= 8 and terminal and no_retry
        and usage.get("unresolved_attempts", 0) == 0 and usage.get("accounting_valid", True) is True,
        {"physical_requests": count, "grant": grant, "all_terminal": terminal, "retry_none_single_request": no_retry,
         "unresolved_attempts": usage.get("unresolved_attempts"), "accounting_valid": usage.get("accounting_valid")})

    stopped = final.get("error_code")
    return {"tested_commit": record.get("tested_commit"), "status": record.get("status"), "final_state": final.get("state"),
            "stopping_code": stopped, "physical_requests": count, "predicates": out,
            "live_workflow_passed": all(row["status"] == "passed" for row in out.values())}


if __name__ == "__main__":
    print(json.dumps(score(json.load(open(sys.argv[1], encoding="utf-8"))), indent=2))
