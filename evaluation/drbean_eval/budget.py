"""Harness-side provider-budget ledger for a future bounded live cohort (section 7).

Append-only JSONL. A request's maximum is reserved before dispatch and
reconciled afterwards. Unknown acceptance stays reserved. Nothing here calls a
provider. Caps are ceilings, not measurements.

This is NOT the backend's persistent provider ledger (``bean_api/ledger.py``),
which reconciles conservatively by ``max(reserved, actual)``. The two are not one
enforced budget. No live cohort is open and live lanes are disabled; any future
activation needs a new explicit user instruction and one agreed authoritative
dispatch ledger whose actual attempt records this harness then *observes*
instead of reserving a second budget. See docs/evaluation-protocol.md.

Revision 2 hardening (Workstream 5): reported usage is validated (no negative,
boolean, non-integer or missing counts; ``network_attempts`` >= 1), every actual
network attempt counts as a provider request, and a usage report that cannot be
trusted keeps the full maximum reserved as unknown instead of refunding it.
"""
from __future__ import annotations

import fcntl
import json
import os
import uuid
from datetime import datetime, timezone

DEFAULT_CAPS = {"provider_requests": 32, "input_tokens": 64000, "output_tokens": 16000}

# GF-2 per-invocation operational defaults. May be lowered, never raised here.
INVOCATION_LIMITS = {
    "intake": {"provider_requests": 2, "repair_requests": 1, "wall_seconds": 60, "proposed_fields": 50},
    "agent": {"provider_requests": 4, "tool_calls": 6, "wall_seconds": 300, "scientific_reservations": 2},
    "explanation": {"provider_requests": 1, "wall_seconds": 30, "displayed_characters": 2000},
    "design_job": {"wall_seconds": 120, "times": 64, "constructions": 2, "pair_verification_passes": 2},
}


class BudgetStop(Exception):
    """The next request cannot be shown to fit; do not dispatch it."""


class UsageRejected(ValueError):
    """Reported usage is malformed or inconsistent; nothing may be refunded on its basis."""


def _count(value, name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise UsageRejected(f"{name} must be an integer >= {minimum}, got {value!r}")
    return value


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class BudgetLedger:
    def __init__(self, path: str):
        self.path = path

    # -- storage ---------------------------------------------------------
    def _events(self) -> list[dict]:
        """Every event, or BudgetStop if any line is unreadable: a corrupt ledger fails closed, bytes preserved."""
        if not os.path.exists(self.path):
            return []
        events = []
        with open(self.path, encoding="utf-8", errors="strict") as handle:
            for number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    event = json.loads(line)
                except ValueError:
                    raise BudgetStop(f"ledger line {number} is not valid JSON; the file is preserved unchanged and "
                                     "needs an explicit recovery record before any reservation") from None
                if not isinstance(event, dict) or "event" not in event:
                    raise BudgetStop(f"ledger line {number} is not a ledger event; recovery required")
                events.append(event)
        return events

    def _append(self, handle, event: dict) -> dict:
        event = {"at": _now(), **event}
        handle.write(json.dumps(event, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
        return event

    def _locked(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
        handle = open(self.path, "a+", encoding="utf-8")
        fcntl.flock(handle, fcntl.LOCK_EX)
        return handle

    # -- state -----------------------------------------------------------
    def state(self, events=None) -> dict:
        events = self._events() if events is None else events
        cohort, reservations = None, {}
        for event in events:
            kind = event["event"]
            if kind == "cohort_opened":
                cohort = event
            elif kind == "reserved":
                reservations[event["reservation_id"]] = {**event, "status": "reserved"}
            elif kind in ("reconciled", "unknown_acceptance", "released_unsent"):
                reservations[event["reservation_id"]].update(
                    status=kind, **{k: v for k, v in event.items() if k not in ("event", "at")})
        used = {"provider_requests": 0, "input_tokens": 0, "output_tokens": 0}
        for item in reservations.values():
            if item["status"] == "released_unsent":
                continue  # provably never left this machine
            # Every actual network attempt is a provider request, including retries.
            attempts = item.get("network_attempts", 1)
            used["provider_requests"] += attempts if type(attempts) is int and attempts >= 1 else 1
            if item["status"] == "reconciled":
                used["input_tokens"] += item["input_tokens"]
                used["output_tokens"] += item["output_tokens"]
            else:  # still reserved, or acceptance unknown: count the maximum
                used["input_tokens"] += item["max_input_tokens"]
                used["output_tokens"] += item["max_output_tokens"]
        caps = cohort["caps"] if cohort else None
        return {
            "cohort": cohort,
            "committed": used,
            "remaining": {k: caps[k] - used[k] for k in used} if caps else None,
            "reservations": reservations,
            "unreconciled": sorted(k for k, v in reservations.items()
                                   if v["status"] in ("reserved", "unknown_acceptance")),
            "overruns": sorted(k for k, v in reservations.items() if v.get("overrun")),
            "conflicting_request_ids": sorted(
                rid for rid in {v.get("provider_request_id") for v in reservations.values()
                                if v["status"] == "reconciled" and v.get("provider_request_id")}
                if sum(1 for v in reservations.values() if v.get("provider_request_id") == rid
                       and v["status"] == "reconciled") > 1),
            "exceeded": sorted(k for k in used if caps and used[k] > caps[k]),
        }

    # -- commands --------------------------------------------------------
    def open_cohort(self, cohort_id: str, authorized_by: str, spending_note: str, caps: dict | None = None,
                    model: str | None = None) -> dict:
        """A human-authorized cohort. One per ledger file; never reopened automatically."""
        caps = {**DEFAULT_CAPS, **(caps or {})}
        for key, ceiling in DEFAULT_CAPS.items():
            if not 0 < caps[key] <= ceiling:
                raise ValueError(f"cap {key}={caps[key]} must be in 1..{ceiling}; caps can only be lowered")
        if not authorized_by.strip() or not spending_note.strip():
            raise ValueError("a named human authorizer and a spending allowance note are required")
        with self._locked() as handle:
            if self.state()["cohort"]:
                raise BudgetStop("a cohort already exists in this ledger; a second cohort needs a new ledger "
                                 "file and a new human authorization")
            return self._append(handle, {"event": "cohort_opened", "cohort_id": cohort_id, "caps": caps,
                                         "authorized_by": authorized_by, "spending_note": spending_note,
                                         "model": model})

    def reserve(self, owner: str, purpose: str, case_id: str, max_input_tokens: int, max_output_tokens: int,
                bound_basis: str) -> str:
        if max_input_tokens <= 0 or max_output_tokens <= 0:
            raise BudgetStop("a request without a positive defensible pre-request maximum cannot be reserved")
        if not bound_basis.strip():
            raise BudgetStop("state how the pre-request maximum was derived; an estimate is not a hard limit")
        with self._locked() as handle:
            state = self.state()
            if not state["cohort"]:
                raise BudgetStop("no authorized cohort is open; live provider requests are not permitted")
            need = {"provider_requests": 1, "input_tokens": max_input_tokens, "output_tokens": max_output_tokens}
            short = [k for k, v in need.items() if state["remaining"][k] < v]
            if short:
                self._append(handle, {"event": "budget_stop", "owner": owner, "purpose": purpose,
                                      "case_id": case_id, "short": short, "need": need,
                                      "remaining": state["remaining"]})
                raise BudgetStop(f"request does not fit remaining budget: {', '.join(short)}")
            reservation_id = "rsv_" + uuid.uuid4().hex[:16]
            self._append(handle, {"event": "reserved", "reservation_id": reservation_id, "owner": owner,
                                  "purpose": purpose, "case_id": case_id, "max_input_tokens": max_input_tokens,
                                  "max_output_tokens": max_output_tokens, "bound_basis": bound_basis})
            return reservation_id

    def _close(self, reservation_id: str, event: dict) -> dict:
        with self._locked() as handle:
            item = self.state()["reservations"].get(reservation_id)
            if item is None:
                raise KeyError(reservation_id)
            if item["status"] in ("reconciled", "released_unsent"):
                raise ValueError(f"reservation {reservation_id} is already {item['status']}")
            return self._append(handle, {"reservation_id": reservation_id, **event})

    def reconcile(self, reservation_id: str, input_tokens: int, output_tokens: int, outcome: str,
                  provider_request_id: str | None = None, network_attempts: int = 1) -> dict:
        """Record provider-reported usage. Overruns are kept and flagged, never hidden.

        Malformed usage raises UsageRejected and records nothing; the caller must then
        mark the reservation unknown so its full maximum stays committed.
        """
        _count(input_tokens, "input_tokens")
        _count(output_tokens, "output_tokens")
        _count(network_attempts, "network_attempts", 1)
        if not isinstance(outcome, str) or not outcome:
            raise UsageRejected("outcome must be a nonempty string")
        item = self.state()["reservations"].get(reservation_id) or {}
        overrun = (input_tokens > item.get("max_input_tokens", 0)
                   or output_tokens > item.get("max_output_tokens", 0) or network_attempts > 1)
        return self._close(reservation_id, {"event": "reconciled", "input_tokens": input_tokens,
                                            "output_tokens": output_tokens, "outcome": outcome,
                                            "provider_request_id": provider_request_id,
                                            "network_attempts": network_attempts, "overrun": overrun})

    def mark_unknown(self, reservation_id: str, reason: str, network_attempts: int = 1) -> dict:
        """Timeout, lost response or untrusted usage: acceptance unknown, so the maximum stays reserved."""
        if type(network_attempts) is not int or network_attempts < 1:
            network_attempts = 1  # never fewer than the one request a reservation stands for
        return self._close(reservation_id, {"event": "unknown_acceptance", "reason": str(reason)[:300],
                                            "network_attempts": network_attempts})

    def record_error(self, context: str, error: str) -> dict:
        """A reconciliation failure is itself evidence; reservations it touched stay open."""
        with self._locked() as handle:
            return self._append(handle, {"event": "reconcile_error", "context": context[:200], "error": error[:300]})

    def release_unsent(self, reservation_id: str, reason: str) -> dict:
        """Only for a request that provably was never dispatched."""
        item = self.state()["reservations"].get(reservation_id) or {}
        if item.get("status") == "unknown_acceptance":
            raise ValueError("a request with unknown acceptance may have been billed; reconcile it instead")
        return self._close(reservation_id, {"event": "released_unsent", "reason": reason})
