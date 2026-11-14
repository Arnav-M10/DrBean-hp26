"""Durable provider attempts and conservative, shared evaluation reservations.

A timeout never refunds a reservation or proves that a provider did no work.
Only bounded, sanitized metadata is stored, never raw prompts or credentials.

Budget grants (owner decisions, ``provider-budget-grants.v1``): the base caps stay
the defaults and can only be lowered in code. Extra capacity exists only as
explicit, append-only grant rows that the owner records with
``python -m bean_api.ledger grant ... --confirm-owner-decision``. Each grant names
a unique decision id, is hash-chained to the previous grant, and is immutable
(SQLite triggers refuse UPDATE and DELETE). Grants add capacity; they never erase,
refund or reset recorded attempts. A broken grant chain fails closed. The table is
created only when the first grant is recorded, so the application itself never
changes the schema. A free-tier statement is the owner's account assertion, not a
billing verification.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import uuid
from typing import Any

from .store import Store, utc_now


class LedgerBudgetExceeded(RuntimeError):
    pass


MAX_TOKEN_COUNT = 2**63 - 1


def _count(value):
    if type(value) is not int or not 0 <= value <= MAX_TOKEN_COUNT:
        raise ValueError("Token counts must be bounded nonnegative integers")
    return value


def _aliases(values, *names):
    # Providers may supply both names. Never discard the larger reported count.
    present = [values[name] for name in names if values.get(name) is not None]
    return max((_count(value) for value in present), default=0)


def _reservations(metadata):
    if type(metadata) is not dict:
        raise ValueError("Reservation metadata must be an object")
    incoming = _aliases(metadata, "reserved_input_tokens", "input_token_reservation")
    outgoing = _aliases(metadata, "reserved_output_tokens", "output_token_reservation")
    if incoming < 1 or outgoing < 1:
        raise ValueError("A positive conservative token reservation is required")
    return incoming, outgoing


def _usage(metadata):
    if type(metadata) is not dict:
        raise ValueError("Outcome metadata must be an object")
    usage = metadata.get("usage")
    if usage is None:
        return 0, 0
    if type(usage) is not dict:
        raise ValueError("Usage must be an object or null")
    incoming = _aliases(usage, "input_tokens", "prompt_token_count")
    outgoing = _aliases(usage, "output_tokens", "candidates_token_count")
    thoughts = _aliases(usage, "thought_tokens", "thoughts_token_count")
    outgoing = _count(outgoing + thoughts)
    total = _aliases(usage, "total_tokens", "total_token_count")
    known = _count(incoming + outgoing)
    if any(usage.get(key) is not None for key in ("total_tokens", "total_token_count")) and total < known:
        raise ValueError("Reported total tokens cannot be smaller than component counts")
    # Missing components cannot make an observed total disappear. Attribute any
    # unallocated tokens conservatively to each cap until exact usage is known.
    return max(incoming, total - outgoing), max(outgoing, total - incoming)


def _accounting(rows):
    incoming = outgoing = malformed = 0
    for row in rows:
        try:
            reserved_in, reserved_out = _reservations(json.loads(row["metadata"]))
            actual_in, actual_out = _usage(json.loads(row["response_metadata"] or "{}"))
            incoming += max(reserved_in, actual_in)
            outgoing += max(reserved_out, actual_out)
        except (TypeError, ValueError, OverflowError):
            # Preserve historical bytes and capacity; diagnostics remain useful
            # while further dispatch fails closed instead of guessing a refund.
            malformed += 1
    return incoming, outgoing, malformed


GRANT_POLICY = "provider-budget-grants.v1"
# Absolute ceilings on base plus granted capacity, whatever grants are recorded.
GRANT_CEILINGS = {"requests": 256, "input_tokens": 2_000_000, "output_tokens": 500_000}
GRANT_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS provider_budget_grants ("
    " id TEXT PRIMARY KEY, sequence INTEGER NOT NULL UNIQUE CHECK(sequence >= 1),"
    " decision_id TEXT NOT NULL UNIQUE, granted_by TEXT NOT NULL, reason TEXT NOT NULL,"
    " requests INTEGER NOT NULL CHECK(requests >= 0), input_tokens INTEGER NOT NULL CHECK(input_tokens >= 0),"
    " output_tokens INTEGER NOT NULL CHECK(output_tokens >= 0), account_assertion TEXT NOT NULL,"
    " previous_grant_sha256 TEXT, grant_sha256 TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL)",
    "CREATE TRIGGER IF NOT EXISTS provider_budget_grants_no_update BEFORE UPDATE ON provider_budget_grants "
    "BEGIN SELECT RAISE(ABORT, 'immutable budget grant'); END",
    "CREATE TRIGGER IF NOT EXISTS provider_budget_grants_no_delete BEFORE DELETE ON provider_budget_grants "
    "BEGIN SELECT RAISE(ABORT, 'immutable budget grant'); END",
)
_GRANT_FIELDS = ("sequence", "decision_id", "granted_by", "reason", "requests", "input_tokens", "output_tokens",
                 "account_assertion", "previous_grant_sha256", "created_at")


def _grant_digest(fields: dict) -> str:
    payload = {name: fields[name] for name in _GRANT_FIELDS}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(b"dr-bean:provider-budget-grant:v1\n" + encoded).hexdigest()


def _grant_totals(conn) -> tuple[dict, list[dict], bool]:
    """Sum the grant chain. Returns (totals, grants, chain_valid); a missing table means no grants."""
    totals = {"requests": 0, "input_tokens": 0, "output_tokens": 0}
    try:
        rows = [dict(row) for row in conn.execute("SELECT * FROM provider_budget_grants ORDER BY sequence")]
    except sqlite3.OperationalError as error:
        if "no such table" in str(error):
            return totals, [], True
        raise
    previous = None
    for expected, row in enumerate(rows, 1):
        if (row["sequence"] != expected or row["previous_grant_sha256"] != previous
                or _grant_digest(row) != row["grant_sha256"]
                or any(type(row[name]) is not int or row[name] < 0 for name in totals)):
            return totals, rows, False
        for name in totals:
            totals[name] += row[name]
        previous = row["grant_sha256"]
    return totals, rows, True


class ProviderLedger:
    def __init__(self, store: Store, *, request_cap: int = 32,
                 input_token_cap: int = 64_000, output_token_cap: int = 16_000):
        if (any(type(value) is not int for value in (request_cap, input_token_cap, output_token_cap))
                or not 1 <= request_cap <= 32 or not 1 <= input_token_cap <= 64_000
                or not 1 <= output_token_cap <= 16_000):
            raise ValueError("GF-2 ledger caps can only be lowered in this release")
        self.store = store
        self.request_cap = request_cap
        self.input_token_cap = input_token_cap
        self.output_token_cap = output_token_cap

    def _effective_caps(self, conn) -> tuple[dict, dict]:
        totals, grants, valid = _grant_totals(conn)
        if not valid:
            raise LedgerBudgetExceeded("Budget grant history requires owner review before further dispatch")
        base = {"requests": self.request_cap, "input_tokens": self.input_token_cap,
                "output_tokens": self.output_token_cap}
        caps = {name: min(base[name] + totals[name], GRANT_CEILINGS[name]) for name in base}
        return caps, {"policy": GRANT_POLICY, "count": len(grants), "granted": totals,
                      "decision_ids": [grant["decision_id"] for grant in grants][-20:], "chain_valid": True}

    def begin_attempt(self, context: dict[str, Any], metadata: dict[str, Any]) -> str:
        """Commit the request and token reservation before any network dispatch."""
        combined = {**metadata, "context": context}
        try:
            reserved_in, reserved_out = _reservations(combined)
        except ValueError as error:
            raise LedgerBudgetExceeded(str(error)) from error
        combined["reserved_input_tokens"] = reserved_in
        combined["reserved_output_tokens"] = reserved_out
        encoded = json.dumps(combined, ensure_ascii=False, allow_nan=False)
        if len(encoded.encode()) > 16_384:
            raise ValueError("Provider metadata exceeds its bound")
        attempt_id = str(uuid.uuid4())
        with self.store.transaction() as conn:
            membership = conn.execute(
                "SELECT 1 FROM memberships WHERE workspace_id=? AND actor_id=?",
                (context["workspace_id"], context["actor_id"]),
            ).fetchone()
            operation = conn.execute(
                "SELECT * FROM operations WHERE id=? AND workspace_id=? AND actor_id=? AND state='reserved'",
                (context["operation_id"], context["workspace_id"], context["actor_id"]),
            ).fetchone()
            if not membership or not operation:
                raise ValueError("Provider attempt requires an owned durable operation")
            rows = conn.execute("SELECT metadata, response_metadata FROM provider_attempts").fetchall()
            used_in, used_out, malformed = _accounting(rows)
            if malformed:
                raise LedgerBudgetExceeded("Historical provider accounting requires review before further dispatch")
            caps, _ = self._effective_caps(conn)
            if (len(rows) >= caps["requests"] or used_in + reserved_in > caps["input_tokens"]
                    or used_out + reserved_out > caps["output_tokens"]):
                raise LedgerBudgetExceeded("The shared GF-2 provider ledger cannot admit another request")
            conn.execute(
                "INSERT INTO provider_attempts(id,workspace_id,operation_id,metadata,state,created_at) VALUES (?,?,?,?,?,?)",
                (attempt_id, context["workspace_id"], context["operation_id"], encoded, "reserved", utc_now()),
            )
        return attempt_id

    def finish_attempt(self, attempt_id: str, metadata: dict[str, Any]) -> None:
        _usage(metadata)
        outcome = metadata.get("outcome", metadata.get("status", "completed"))
        if not isinstance(outcome, str) or ("outcome" in metadata and "status" in metadata
                                            and metadata["outcome"] != metadata["status"]):
            raise ValueError("Provider outcome must be an unambiguous status string")
        if outcome in {"timeout", "cancelled", "unknown_outcome", "interrupted"}:
            state = "unknown_outcome"
        elif outcome in {"completed", "success", "valid", "validated", "schema_valid"}:
            state = "completed"
        else:
            state = "failed"
        encoded = json.dumps(metadata, ensure_ascii=False, allow_nan=False)
        if len(encoded.encode()) > 16_384:
            raise ValueError("Provider outcome metadata exceeds its bound")
        with self.store.transaction() as conn:
            attempt = conn.execute("SELECT state,response_metadata FROM provider_attempts WHERE id=?", (attempt_id,)).fetchone()
            if attempt is None:
                raise ValueError("Unknown provider attempt")
            if attempt["state"] != "reserved":
                if attempt["state"] == state and json.loads(attempt["response_metadata"] or "{}") == metadata:
                    return
                raise ValueError("Provider attempt already has a different immutable outcome")
            conn.execute(
                "UPDATE provider_attempts SET state=?,response_metadata=?,finished_at=? WHERE id=? AND state='reserved'",
                (state, encoded, utc_now(), attempt_id),
            )

    def list_attempts(self, actor: str, workspace_id: str) -> list[dict[str, Any]]:
        with self.store.read() as conn:
            if not conn.execute("SELECT 1 FROM memberships WHERE workspace_id=? AND actor_id=?", (workspace_id, actor)).fetchone():
                return []
            rows = conn.execute("SELECT * FROM provider_attempts WHERE workspace_id=? ORDER BY created_at", (workspace_id,)).fetchall()
        return [{**dict(row), "metadata": json.loads(row["metadata"]),
                 "response_metadata": json.loads(row["response_metadata"]) if row["response_metadata"] else None}
                for row in rows]

    def diagnostics(self) -> dict[str, Any]:
        """Global capacity only, never disclose another workspace's attempt data."""
        with self.store.read() as conn:
            rows = conn.execute("SELECT metadata,response_metadata,state FROM provider_attempts").fetchall()
            try:
                caps, grants = self._effective_caps(conn)
            except LedgerBudgetExceeded:
                caps = {"requests": 0, "input_tokens": 0, "output_tokens": 0}
                grants = {"policy": GRANT_POLICY, "chain_valid": False}
        reserved_in, reserved_out, malformed = _accounting(rows)
        unknown = sum(row["state"] in {"reserved", "unknown_outcome"} for row in rows)
        blocked = malformed or not grants["chain_valid"]
        return {"dispatch_enabled": False, "current_mode": "disabled_placeholder",
                "accounting_policy": "conservative_no_refund.v1", "historical_attempts": len(rows),
                "unknown_outcome_reservations": unknown,
                "accounting_state": "needs_review" if blocked else "valid",
                "malformed_historical_attempts": malformed,
                "remaining": {"requests": 0 if blocked else max(0, caps["requests"]-len(rows)),
                              "input_tokens": 0 if blocked else max(0, caps["input_tokens"]-reserved_in),
                              "output_tokens": 0 if blocked else max(0, caps["output_tokens"]-reserved_out)},
                "effective_caps": caps, "budget_grants": grants,
                "controlled_placeholder_records": "separate; zero external requests and actual model tokens"}


def record_grant(store: Store, *, decision_id: str, granted_by: str, reason: str, requests: int,
                 input_tokens: int, output_tokens: int) -> dict:
    """Append one owner-approved grant. Never edits earlier grants or any attempt."""
    if not isinstance(decision_id, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{2,127}", decision_id):
        raise ValueError("A decision id of 3-128 safe characters is required")
    if not isinstance(granted_by, str) or not 1 <= len(granted_by.strip()) <= 120:
        raise ValueError("Name who made the owner decision")
    if not isinstance(reason, str) or not 10 <= len(reason.strip()) <= 1000:
        raise ValueError("Record the reason for the grant (10-1000 characters)")
    amounts = {"requests": requests, "input_tokens": input_tokens, "output_tokens": output_tokens}
    if any(type(value) is not int or value < 0 for value in amounts.values()) or not any(amounts.values()):
        raise ValueError("Grant nonnegative integers, at least one of them positive")
    with store.transaction() as conn:
        for statement in GRANT_SCHEMA:  # one statement at a time: executescript would commit early
            conn.execute(statement)
        totals, grants, valid = _grant_totals(conn)
        if not valid:
            raise ValueError("The existing grant chain is invalid; review it before recording another grant")
        if any(grant["decision_id"] == decision_id for grant in grants):
            raise ValueError("This owner decision id already has a recorded grant")
        if any(totals[name] + amounts[name] > GRANT_CEILINGS[name] for name in amounts):
            raise ValueError("The grant would exceed the absolute budget ceilings")
        fields = {"sequence": len(grants) + 1, "decision_id": decision_id, "granted_by": granted_by.strip(),
                  "reason": reason.strip(), **amounts, "account_assertion": "free_tier_user_asserted_not_billing_verified",
                  "previous_grant_sha256": grants[-1]["grant_sha256"] if grants else None, "created_at": utc_now()}
        fields["grant_sha256"] = _grant_digest(fields)
        fields["id"] = f"grant_{uuid.uuid4().hex}"
        conn.execute("INSERT INTO provider_budget_grants(id,sequence,decision_id,granted_by,reason,requests,input_tokens,"
                     "output_tokens,account_assertion,previous_grant_sha256,grant_sha256,created_at) "
                     "VALUES (:id,:sequence,:decision_id,:granted_by,:reason,:requests,:input_tokens,:output_tokens,"
                     ":account_assertion,:previous_grant_sha256,:grant_sha256,:created_at)", fields)
    return fields


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m bean_api.ledger",
                                     description="Owner-only budget grants. Nothing here contacts a provider.")
    commands = parser.add_subparsers(dest="command", required=True)
    show = commands.add_parser("status", help="Show caps, grants and remaining capacity")
    show.add_argument("--database", required=True)
    grant = commands.add_parser("grant", help="Append one explicit owner-approved grant")
    grant.add_argument("--database", required=True)
    grant.add_argument("--decision-id", required=True)
    grant.add_argument("--granted-by", required=True)
    grant.add_argument("--reason", required=True)
    grant.add_argument("--requests", type=int, default=0)
    grant.add_argument("--input-tokens", type=int, default=0)
    grant.add_argument("--output-tokens", type=int, default=0)
    grant.add_argument("--live-request-cap", type=int, default=8, help="The server's base request cap (live: 8)")
    grant.add_argument("--confirm-owner-decision", action="store_true", required=True)
    args = parser.parse_args(argv)
    store = Store(args.database)
    if args.command == "grant":
        recorded = record_grant(store, decision_id=args.decision_id, granted_by=args.granted_by, reason=args.reason,
                                requests=args.requests, input_tokens=args.input_tokens,
                                output_tokens=args.output_tokens)
        print(json.dumps({"recorded": {k: recorded[k] for k in ("sequence", "decision_id", "requests", "input_tokens",
                                                                 "output_tokens", "grant_sha256")}}, indent=2))
        ledger = ProviderLedger(store, request_cap=args.live_request_cap)
    else:
        ledger = ProviderLedger(store, request_cap=8)
    print(json.dumps({key: ledger.diagnostics()[key] for key in ("historical_attempts", "accounting_state",
                                                                 "effective_caps", "remaining", "budget_grants")},
                     indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
