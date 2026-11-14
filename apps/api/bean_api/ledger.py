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


class ProviderLedger:
    def __init__(self, store: Store, *, request_cap: int = 32,
                 input_token_cap: int = 64_000, output_token_cap: int = 16_000):
        if not 1 <= request_cap <= 32 or not 1 <= input_token_cap <= 64_000 or not 1 <= output_token_cap <= 16_000:
            raise ValueError("GF-2 ledger caps can only be lowered in this release")
        self.store = store
        self.request_cap = request_cap
        self.input_token_cap = input_token_cap
        self.output_token_cap = output_token_cap

    def begin_attempt(self, context: dict[str, Any], metadata: dict[str, Any]) -> str:
        """Commit the request and token reservation before any network dispatch."""
        combined = {**metadata, "context": context}
        reserved_in = combined.get("reserved_input_tokens", combined.get("input_token_reservation"))
        reserved_out = combined.get("reserved_output_tokens", combined.get("output_token_reservation"))
        if type(reserved_in) is not int or type(reserved_out) is not int or reserved_in < 1 or reserved_out < 1:
            raise LedgerBudgetExceeded("A conservative token reservation is required before dispatch")
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
            used_in = used_out = 0
            for row in rows:
                reservation = json.loads(row["metadata"])
                usage = json.loads(row["response_metadata"] or "{}")
                actual = usage.get("usage") or {}
                actual_in = actual.get("input_tokens") or actual.get("prompt_token_count") or 0
                actual_out = (actual.get("output_tokens") or actual.get("candidates_token_count") or 0) + (actual.get("thought_tokens") or 0)
                used_in += max(reservation.get("reserved_input_tokens", 0), actual_in)
                used_out += max(reservation.get("reserved_output_tokens", 0), actual_out)
            if len(rows) >= self.request_cap or used_in + reserved_in > self.input_token_cap or used_out + reserved_out > self.output_token_cap:
                raise LedgerBudgetExceeded("The shared GF-2 provider ledger cannot admit another request")
            conn.execute(
                "INSERT INTO provider_attempts(id,workspace_id,operation_id,metadata,state,created_at) VALUES (?,?,?,?,?,?)",
                (attempt_id, context["workspace_id"], context["operation_id"], encoded, "reserved", utc_now()),
            )
        return attempt_id

    def finish_attempt(self, attempt_id: str, metadata: dict[str, Any]) -> None:
        outcome = metadata.get("outcome", metadata.get("status", "completed"))
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
        reserved_in = reserved_out = 0
        unknown = 0
        for row in rows:
            reservation = json.loads(row["metadata"])
            response = json.loads(row["response_metadata"] or "{}")
            usage = response.get("usage") or {}
            reserved_in += max(reservation.get("reserved_input_tokens", 0),
                               usage.get("input_tokens") or usage.get("prompt_token_count") or 0)
            reserved_out += max(reservation.get("reserved_output_tokens", 0),
                                (usage.get("output_tokens") or usage.get("candidates_token_count") or 0)
                                + (usage.get("thought_tokens") or 0))
            unknown += int(row["state"] in {"reserved", "unknown_outcome"})
        return {"dispatch_enabled": False, "current_mode": "disabled_placeholder",
                "accounting_policy": "conservative_no_refund.v1", "historical_attempts": len(rows),
                "unknown_outcome_reservations": unknown,
                "remaining": {"requests": max(0, self.request_cap-len(rows)),
                              "input_tokens": max(0, self.input_token_cap-reserved_in),
                              "output_tokens": max(0, self.output_token_cap-reserved_out)},
                "controlled_placeholder_records": "separate; zero external requests and actual model tokens"}
