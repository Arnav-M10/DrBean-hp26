"""Durable provider attempts and conservative, shared evaluation reservations.

A timeout never refunds a reservation or proves that a provider did no work.
Only bounded, sanitized metadata is stored, never raw prompts or credentials.
"""

from __future__ import annotations

import json
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
            self._begin_in_transaction(conn, context, encoded, reserved_in, reserved_out, attempt_id)
        return attempt_id

    def _begin_in_transaction(self, conn, context, encoded, reserved_in, reserved_out, attempt_id):
        """One physical reservation; research authority extends this transaction."""
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
        if operation["operation"] == "research-runtime":
            self._validate_research_attempt(conn, context, operation, encoded, reserved_in, reserved_out)
        rows = conn.execute("SELECT metadata, response_metadata FROM provider_attempts").fetchall()
        used_in, used_out, malformed = _accounting(rows)
        if malformed:
            raise LedgerBudgetExceeded("Historical provider accounting requires review before further dispatch")
        if len(rows) >= self.request_cap or used_in + reserved_in > self.input_token_cap or used_out + reserved_out > self.output_token_cap:
            raise LedgerBudgetExceeded("The shared GF-2 provider ledger cannot admit another request")
        conn.execute(
            "INSERT INTO provider_attempts(id,workspace_id,operation_id,metadata,state,created_at) VALUES (?,?,?,?,?,?)",
            (attempt_id, context["workspace_id"], context["operation_id"], encoded, "reserved", utc_now()),
        )

    def _validate_research_attempt(self, conn, context, operation, encoded, reserved_in, reserved_out):
        raise LedgerBudgetExceeded("Research requests require atomic session/action authority; omitted context cannot bypass it")

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
        reserved_in, reserved_out, malformed = _accounting(rows)
        unknown = sum(row["state"] in {"reserved", "unknown_outcome"} for row in rows)
        return {"dispatch_enabled": False, "current_mode": "disabled_placeholder",
                "accounting_policy": "conservative_no_refund.v1", "historical_attempts": len(rows),
                "unknown_outcome_reservations": unknown,
                "accounting_state": "needs_review" if malformed else "valid",
                "malformed_historical_attempts": malformed,
                "remaining": {"requests": 0 if malformed else max(0, self.request_cap-len(rows)),
                              "input_tokens": 0 if malformed else max(0, self.input_token_cap-reserved_in),
                              "output_tokens": 0 if malformed else max(0, self.output_token_cap-reserved_out)},
                "controlled_placeholder_records": "separate; zero external requests and actual model tokens"}
