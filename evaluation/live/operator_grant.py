"""Operator-only provider allocation for C's isolated live sprint runs.

The product deliberately exposes no browser route for granting provider
capacity (`ResearchService.allocate_provider` requires an explicit operator
actor). This tool is that operator act, on an isolated temporary store only,
through the real service method, so the ledger, ceilings and records are the
product's own.

It also enforces the sprint ceiling: the cumulative physical requests granted
across every live session in this sprint never exceed 12. Grants bound the
physical requests that can be dispatched, and failed or uncertain attempts are
charged against them, so the ceiling holds for attempts too.

    python evaluation/live/operator_grant.py <db> <session_id> <physical> <input_tokens> <output_tokens> <purpose>

Prints only public counters; never reads or prints credentials.
"""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
import sys

SPRINT_CEILING = 12
# One canonical sprint ledger, wherever the harness runs (LIVE_BUDGET_FILE overrides the default).
BUDGET = Path(os.environ.get("LIVE_BUDGET_FILE") or Path(__file__).resolve().parents[1] / "results" / "sprint" / "live-budget.json")


def main(argv: list[str]) -> int:
    db, session_id, physical, input_tokens, output_tokens, purpose = argv
    physical, input_tokens, output_tokens = int(physical), int(input_tokens), int(output_tokens)
    if "var/bean.sqlite3" in db.replace("\\", "/") and "/tmp" not in db and "/private/" not in db:
        raise SystemExit("Refusing: operator grants in this harness are for isolated temporary stores only.")
    budget = json.loads(BUDGET.read_text()) if BUDGET.exists() else {"ceiling": SPRINT_CEILING, "grants": []}
    # A grant whose isolated store was deleted with zero recorded attempts can never dispatch; it is released with evidence.
    granted = sum(g["physical_requests"] for g in budget["grants"]) - sum(r["physical_requests"] for r in budget.get("released", []))
    if granted + physical > SPRINT_CEILING:
        raise SystemExit(f"Refusing: {granted} already granted; {physical} more would exceed the sprint ceiling of {SPRINT_CEILING}.")
    from bean_api.research import ResearchService
    from bean_api.store import Store
    from bean_api.workflow import Workflow
    workflow = Workflow(Store(db))
    with workflow.store.read() as conn:
        row = conn.execute("SELECT actor_id, mode FROM research_sessions WHERE id=?", (session_id,)).fetchone()
    if row is None or row["mode"] != "live":
        raise SystemExit("Refusing: no live research session with that id.")
    service = ResearchService(workflow, live_enabled=True, allocation_actor=row["actor_id"])
    record = service.allocate_provider(row["actor_id"], session_id, {"physical_requests": physical,
        "input_tokens": input_tokens, "output_tokens": output_tokens, "accepted": True}, f"c-sprint-{purpose}")
    budget["grants"].append({"at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                             "purpose": purpose, "research_session_id": session_id, "allocation_record": record["id"],
                             "physical_requests": physical, "input_tokens": input_tokens, "output_tokens": output_tokens})
    BUDGET.parent.mkdir(parents=True, exist_ok=True)
    BUDGET.write_text(json.dumps(budget, indent=2) + "\n")
    print(json.dumps({"granted": physical, "sprint_granted_total": granted + physical, "ceiling": SPRINT_CEILING,
                      "allocation_record": record["id"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
