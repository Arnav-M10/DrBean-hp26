"""Read-only private UI projections; hints never grant execution authority."""
from __future__ import annotations

import json

from .ledger import _accounting, _aliases, _reservations, _usage


UNRECOVERABLE = {"research_model_outcome_unrecoverable", "research_checkpoint_reconciliation_required"}
QUOTA_ERRORS = {"provider_budget_exhausted", "research_provider_allocation_exhausted", "research_budget_exhausted",
                "agent_model_budget_exhausted", "agent_tool_budget_exhausted", "agent_child_budget_exhausted"}


def provider_usage(conn, session):
    rows = conn.execute("SELECT p.metadata,p.response_metadata,p.state FROM provider_attempts p JOIN research_attempt_bindings b ON b.attempt_id=p.id WHERE b.session_id=?", (session["id"],)).fetchall()
    accounted_in, accounted_out, malformed = _accounting(rows)
    reserved_in = reserved_out = reported_attempts = 0
    reported = {"input": [], "output": [], "thought": [], "total": []}
    names = {"input": ("input_tokens", "prompt_token_count"), "output": ("output_tokens", "candidates_token_count"),
             "thought": ("thought_tokens", "thoughts_token_count"), "total": ("total_tokens", "total_token_count")}
    for row in rows:
        try:
            incoming, outgoing = _reservations(json.loads(row["metadata"]))
            reserved_in += incoming
            reserved_out += outgoing
            outcome = json.loads(row["response_metadata"] or "{}")
            _usage(outcome)  # Apply the ledger's existing count/consistency validation.
            usage = outcome.get("usage")
            if usage is not None:
                reported_attempts += 1
                for kind, aliases in names.items():
                    if any(usage.get(name) is not None for name in aliases):
                        reported[kind].append(_aliases(usage, *aliases))
        except (TypeError, ValueError, OverflowError):
            # The shared ledger already fails closed for these same bytes.
            continue
    valid = malformed == 0 and session["physical_calls"] == len(rows)
    return {"scope": "research_session", "physical_requests": session["physical_calls"],
        "reserved_input_tokens": reserved_in, "reserved_output_tokens": reserved_out,
        "accounted_input_tokens": accounted_in, "accounted_output_tokens": accounted_out,
        "reported_input_tokens": sum(reported["input"]) if reported["input"] else None,
        "reported_output_tokens": sum(reported["output"]) if reported["output"] else None,
        "reported_thought_tokens": sum(reported["thought"]) if reported["thought"] else None,
        "reported_total_tokens": sum(reported["total"]) if reported["total"] else None,
        "reported_attempts": reported_attempts,
        "unresolved_attempts": sum(row["state"] in {"reserved", "unknown_outcome"} for row in rows),
        "accounting_valid": valid,
        "remaining": {"physical_requests": max(0, session["physical_allocation"]-session["physical_calls"]) if valid else 0,
                      "input_tokens": max(0, session["input_allocation"]-accounted_in) if valid else 0,
                      "output_tokens": max(0, session["output_allocation"]-accounted_out) if valid else 0}}


def session_projection(conn, service, session, snapshot):
    usage = provider_usage(conn, session)
    action = snapshot["action"] or {}
    code = action.get("error_code")
    recovery_required = (session["state"] == "needs_reconciliation" or bool(usage["unresolved_attempts"])
                         or not usage["accounting_valid"])
    can_reconcile = (session["state"] == "needs_reconciliation" and not usage["unresolved_attempts"] and usage["accounting_valid"]
                     and code not in UNRECOVERABLE)
    if recovery_required:
        recovery_action = "reconcile" if can_reconcile else "inspect_accounting_or_cancel"
    else:
        recovery_action = "none"
    evidence_ids, download_jobs = [], []
    for job in snapshot["children"]:
        refs = [row["result_id"] for row in job.get("scenarios", []) if row.get("result_id")]
        if job.get("result_id"):
            refs.append(job["result_id"])
        if refs:
            download_jobs.append(job["id"])
            evidence_ids.extend(refs)
    reports = conn.execute("SELECT id,body FROM entities WHERE parent_id=? AND kind='report' ORDER BY rowid", (session["id"],)).fetchall()
    latest = json.loads(reports[-1]["body"]) if reports else {}
    consent = service.workflow._get(conn, session["actor_id"], session["consent_id"], "research_provider_consent") if session["consent_id"] else None
    consent_required = session["mode"] == "live" and (not consent or consent["body"].get("context_digest") != snapshot["provider_disclosure"]["context_digest"])
    quota_exhausted = (not usage["accounting_valid"] or code in QUOTA_ERRORS
        or any(session[key] >= limit for key, limit in snapshot["session_limits"].items())
        or (session["mode"] == "live" and any(value == 0 for value in usage["remaining"].values())))
    state = session["state"]
    if recovery_required:
        suggested = recovery_action
    elif state in {"running", "queued", "waiting_child"}:
        suggested = "wait"
    elif state == "waiting_review":
        suggested = "review"
    elif state == "waiting_observation":
        suggested = "review_observation"
    elif state in {"failed", "cancelled"}:
        suggested = "inspect_results"
    elif consent_required:
        suggested = "review_provider_consent"
    elif quota_exhausted:
        suggested = "inspect_allocation"
    elif state == "completed" and any(job["kind"] == "design_job" for job in snapshot["children"]):
        suggested = "inspect_results"
    else:
        suggested = "advance"
    return {"provider_usage": usage, "interaction": {
        "waiting_for_review": state == "waiting_review", "waiting_for_observation": state == "waiting_observation",
        "provider_consent_required": consent_required, "quota_exhausted": quota_exhausted,
        "recovery": {"required": recovery_required, "code": ("provider_outcome_unknown" if usage["unresolved_attempts"]
                     else "provider_accounting_invalid" if not usage["accounting_valid"] else code) if recovery_required else None,
                     "can_reconcile": can_reconcile, "next_action": recovery_action},
        "results": {"available": bool(reports or evidence_ids), "report_ids": snapshot["reports"],
                    "latest_report_id": reports[-1]["id"] if reports else None,
                    "evidence_ids": list(dict.fromkeys(evidence_ids)), "download_job_ids": download_jobs,
                    "commentary_available": latest.get("commentary_status") == "validated" and latest.get("agent_commentary") is not None,
                    "deterministic_summary_available": isinstance(latest.get("deterministic_summary"), dict)},
        "suggested_action": suggested}}
