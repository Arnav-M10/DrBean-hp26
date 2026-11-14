"""Operator-only provider allocation for C's isolated live sprint runs.

The product deliberately exposes no browser route for granting provider
capacity (`ResearchService.allocate_provider` requires an explicit operator
actor). This tool is that operator act, on an isolated temporary store only,
through the real service method, so the ledger, ceilings and records are the
product's own.

It also enforces the default sprint ceiling of 12. A separately recorded,
explicitly selected qualification extension permits one additional grant of
at most six requests. The first has an overall ceiling of 16; the separately
authorized repaired-run extension has a ceiling of 22. Grants bound the
physical requests that can be dispatched, and failed or uncertain attempts are
charged against them, so the ceiling holds for attempts too.

    python evaluation/live/operator_grant.py <db> <session_id> <physical> <input_tokens> <output_tokens> <purpose>

Prints only public counters; never reads or prints credentials.
Run serially. If persistence fails after allocation, stop and inspect the retained
allocation record; never rerun, release or reset the budget automatically.
"""
from __future__ import annotations

import datetime
import json
import os
from pathlib import Path
import sys

SPRINT_CEILING = 12
QUALIFICATION_EXTENSION_POLICY = {
    "id": "user-followthrough-2026-11-14", "previous_ceiling": 12, "ceiling": 16,
    "max_new_requests": 6, "max_runs": 1, "actor": "root",
    "authorization": "User replied 'idk do wtv is best' to the explicit additional maximum of 6 requests, ceiling 16, and caller choice.",
}
REPAIRED_QUALIFICATION_EXTENSION_POLICY = {
    "id": "user-repaired-followthrough-2026-11-14", "previous_ceiling": 16, "ceiling": 22,
    "max_new_requests": 6, "max_runs": 1, "actor": "root",
    "authorization": "User replied 'idk upto u whatevers best' to the explicit fresh run of at most 6 requests, qualification ceiling 22, and merge only if it passes.",
}
QUALIFICATION_EXTENSION_POLICIES = {
    policy["id"]: policy for policy in (QUALIFICATION_EXTENSION_POLICY, REPAIRED_QUALIFICATION_EXTENSION_POLICY)
}
# One canonical sprint ledger, wherever the harness runs (LIVE_BUDGET_FILE overrides the default).
BUDGET = Path(os.environ.get("LIVE_BUDGET_FILE") or Path(__file__).resolve().parents[1] / "results" / "sprint" / "live-budget.json")


def check_grant(budget: dict, physical: int, extension: str | None = None) -> dict:
    """Pure qualification admission; no store, provider, history mutation or refill."""
    if type(physical) is not int or not 1 <= physical <= 8:
        raise SystemExit("Refusing: a grant must contain 1..8 physical requests.")
    if type(budget) is not dict or type(budget.get("ceiling")) is not int or budget["ceiling"] != SPRINT_CEILING:
        raise SystemExit("Refusing: the historical sprint ceiling must remain 12.")
    grants, released = budget.get("grants"), budget.get("released", [])
    if type(grants) is not list or type(released) is not list or any(
            type(row) is not dict or type(row.get("physical_requests")) is not int or row["physical_requests"] <= 0
            for row in [*grants, *released]):
        raise SystemExit("Refusing: malformed qualification grant history.")
    granted = sum(row["physical_requests"] for row in grants) - sum(row["physical_requests"] for row in released)
    if granted < 0:
        raise SystemExit("Refusing: malformed qualification release history.")
    ceiling = SPRINT_CEILING
    if extension is not None:
        policy = QUALIFICATION_EXTENSION_POLICIES.get(extension) if isinstance(extension, str) else None
        receipts = budget.get("qualification_extensions")
        if policy is None or type(receipts) is not list or not receipts:
            raise SystemExit("Refusing: the exact qualification authorization receipt and opt-in are required.")
        known_receipts = set()
        for receipt in receipts:
            receipt_id = receipt.get("id") if type(receipt) is dict else None
            known_policy = QUALIFICATION_EXTENSION_POLICIES.get(receipt_id) if isinstance(receipt_id, str) else None
            if known_policy is None or receipt_id in known_receipts or any(
                    type(receipt.get(key)) is not type(value) or receipt[key] != value
                    for key, value in known_policy.items()):
                raise SystemExit("Refusing: duplicate, unknown or altered qualification authorization receipt.")
            known_receipts.add(receipt_id)
        if extension not in known_receipts:
            raise SystemExit("Refusing: the exact qualification authorization receipt and opt-in are required.")
        tagged = [grant for grant in grants if "qualification_extension" in grant]
        if any(not isinstance(grant["qualification_extension"], str)
               or grant["qualification_extension"] not in known_receipts for grant in tagged):
            raise SystemExit("Refusing: a historical qualification grant lacks its exact authorization receipt.")
        # Even a released or failed extension run consumes the one-run policy.
        if any(grant["qualification_extension"] == extension for grant in tagged):
            raise SystemExit("Refusing: the single qualification extension grant has already been used.")
        used = budget.get("physical_requests_used")
        expected_granted, expected_used = (10, 8) if extension == QUALIFICATION_EXTENSION_POLICY["id"] else (16, 10)
        if (granted != expected_granted or type(used) is not dict
                or any(type(count) is not int or count < 0 for count in used.values())
                or sum(used.values()) != expected_used or type(budget.get("sprint_physical_requests_total")) is not int
                or budget["sprint_physical_requests_total"] != expected_used):
            raise SystemExit("Refusing: retain all historical effective grants and physical attempts for this authorization.")
        if extension == QUALIFICATION_EXTENSION_POLICY["id"]:
            if tagged:
                raise SystemExit("Refusing: the first qualification extension cannot follow another extension.")
        else:
            first_id = QUALIFICATION_EXTENSION_POLICY["id"]
            prior = [grant for grant in tagged if grant["qualification_extension"] == first_id]
            if (first_id not in known_receipts or len(prior) != 1 or prior[0]["physical_requests"] != 6
                    or not isinstance(prior[0].get("research_session_id"), str)
                    or used.get(prior[0]["research_session_id"]) != 2
                    or any(row.get("research_session_id") == prior[0]["research_session_id"] for row in released)):
                raise SystemExit("Refusing: retain the unreleased first six-request grant and its two actual attempts.")
        if physical > policy["max_new_requests"]:
            raise SystemExit("Refusing: this qualification extension permits at most six new requests.")
        ceiling = policy["ceiling"]
    if granted + physical > ceiling:
        raise SystemExit(f"Refusing: {granted} already granted; {physical} more would exceed the qualification ceiling of {ceiling}.")
    return {"sprint_granted_total": granted + physical, "ceiling": ceiling,
            **({"qualification_extension": extension} if extension is not None else {})}


def main(argv: list[str]) -> int:
    db, session_id, physical, input_tokens, output_tokens, purpose = argv
    physical, input_tokens, output_tokens = int(physical), int(input_tokens), int(output_tokens)
    if "var/bean.sqlite3" in db.replace("\\", "/") and "/tmp" not in db and "/private/" not in db:
        raise SystemExit("Refusing: operator grants in this harness are for isolated temporary stores only.")
    try:
        budget = json.loads(BUDGET.read_text()) if BUDGET.exists() else {"ceiling": SPRINT_CEILING, "grants": []}
    except (OSError, ValueError):
        raise SystemExit("Refusing: the qualification budget cannot be read as JSON.") from None
    # A grant whose isolated store was deleted with zero recorded attempts can never dispatch; it is released with evidence.
    admission = check_grant(budget, physical, os.environ.get("LIVE_QUALIFICATION_EXTENSION"))
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
                             "physical_requests": physical, "input_tokens": input_tokens, "output_tokens": output_tokens,
                             **({"qualification_extension": admission["qualification_extension"]}
                                if "qualification_extension" in admission else {})})
    BUDGET.parent.mkdir(parents=True, exist_ok=True)
    BUDGET.write_text(json.dumps(budget, indent=2) + "\n")
    print(json.dumps({"granted": physical, **admission, "allocation_record": record["id"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
