# Deep Agents completion — additive browser handoff

Backend branch: `codex/deepagents-completion`, based on main `7d40d1c`.
This is a compatibility handoff; the browser owner retains all view implementation.
No provider call is required to read a snapshot. Controlled graph execution is an
offline fixture and never qualifies Gemini. Claude owns all live qualification.

## Existing routes remain unchanged

All paths below use `/api/bean/v1`, the existing private browser cookie and trusted
same-origin proxy. Mutations retain `Idempotency-Key`; repeated uncertain requests
must retain their exact body/key rather than creating another scientific operation.

| Route | Request/use |
| --- | --- |
| GET `/capabilities` | Read `deepagents`: configured mode and server readiness. |
| POST `/workspaces/{id}/research-sessions` | Save objective, reviewed problem/digest, mode and optional design constraints; does not dispatch. |
| GET `/workspaces/{id}/research-sessions` | List private retained sessions. |
| GET `/research-sessions/{id}` | Current canonical snapshot; reading never advances. |
| POST `/research-sessions/{id}/advance` | `{expected_revision}` plus optional existing bounded budget. |
| POST `/research-sessions/{id}/decisions` | `{expected_revision,pending_review_id,expected_review_digest,decision:"approve",accepted:true}`; separate canonical science approval. |
| POST `/research-sessions/{id}/inputs` | Existing explicit reviewed problem/design constraints/clarification answers. |
| POST `/research-sessions/{id}/observations` | Existing separately reviewed reading route; no automatic inference that the operation is currently supported. |
| POST `/research-sessions/{id}/provider-consents` | `{model,expected_context_digest,accepted:true}`; does not allocate provider capacity or execute science. |
| POST `/research-sessions/{id}/reconcile` | `{expected_revision,acknowledged_unknown_outcome:true}` only when recovery permits; never a raw graph resume payload. |
| POST `/research-sessions/{id}/cancel` | `{}`; preserve historical results. |
| GET `/research-sessions/{id}/events?after=N` | Existing ordered retained events. |
| GET `/reports/{id}` and `/reports/{id}/download` | Immutable canonical report and its download. |
| GET `/artifacts/{id}` and `/artifacts/{id}/anchor` | Existing scientific native artifact and external replay anchor. |

Operator allocation remains server-side; there is no browser grant/refill endpoint.
No token-entry field, user-supplied API URL or new shared owner identity is needed.

## Additive fields in this sprint

Existing `state`, `action`, `pending_review`, `children`, `reports`, `usage`,
`provider_allocation` and `provider_disclosure` fields remain authoritative and
unchanged. Global capability additions preserve the old fields:

```json
{
  "configured_mode": "live",
  "execution_mode": "live",
  "readiness": {"state": "configured", "reason": null},
  "live_qualification": "not_run"
}
```

`configured` means the existing server admission checks pass, not that this
session has consent/allocation, that Gemini was called or that the model works.
An unready live configuration retains `configured_mode:"live"` even when legacy
`execution_mode` is `disabled`. Combine server readiness with the private session.

Session snapshots add `interaction` and `provider_usage`. Example **shape**, not
an acceptance result (identifiers/counters are illustrative):

```json
{
  "interaction": {
    "waiting_for_review": true,
    "waiting_for_observation": false,
    "quota_exhausted": false,
    "recovery": {"required": false, "code": null, "can_reconcile": false, "next_action": "none"},
    "results": {"available": true, "report_ids": ["report_example"], "latest_report_id": "report_example", "evidence_ids": ["run_example"], "download_job_ids": ["job_example"], "commentary_available": false, "deterministic_summary_available": true},
    "suggested_action": "review"
  },
  "provider_usage": {
    "physical_requests": 2,
    "reserved_input_tokens": 9000,
    "reserved_output_tokens": 1024,
    "accounted_input_tokens": 9000,
    "accounted_output_tokens": 1024,
    "reported_input_tokens": 1200,
    "reported_output_tokens": 120,
    "reported_attempts": 2,
    "unresolved_attempts": 0,
    "accounting_valid": true,
    "remaining": {"physical_requests": 6, "input_tokens": 55000, "output_tokens": 3072}
  }
}
```

These are read-only projections, never authority to bypass endpoint checks.
Physical reservations, conservative charged token capacity and provider-reported
usage are different quantities. Missing provider usage is not zero cost.
Unknown/reserved attempts keep their allocation and block unsafe resend.
Quota exhaustion means stop and inspect retained science; do not automatically
raise limits, request another allocation or replace the session identity.

A successful science child can remain available when model narration fails.
Render deterministic results/downloads independently of `action.error_code` and
model commentary. New validated recommendations create new report snapshots;
historical reports remain selectable. A passed download/replay never upgrades an
inconclusive scientific outcome or certifies narration.

The implementation and exact field examples are qualified in the focused PR.
Until that commit is supplied, consume existing fields and treat absent additive
fields as unavailable rather than assuming readiness or recovery support.
