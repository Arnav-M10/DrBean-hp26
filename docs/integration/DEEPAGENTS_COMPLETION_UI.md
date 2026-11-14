# Deep Agents completion — additive browser handoff

Backend branch: `codex/deepagents-completion`, based on main `7d40d1c`.
This is a compatibility handoff; the browser owner retains all view implementation.
No provider call is required to read a snapshot. Controlled graph execution is an
offline fixture and never qualifies Gemini. Claude owns independent live
qualification. Later explicit user authorizations allowed root-operated bounded
reproductions; those are reported separately and do not imply Claude acceptance.

## Existing routes remain unchanged

All paths below use `/api/bean/v1`, the existing private browser cookie and trusted
same-origin proxy. Mutations retain `Idempotency-Key`; repeated uncertain requests
must retain their exact body/key rather than creating another scientific operation.

| Route | Request/use |
| --- | --- |
| GET `/capabilities` | Read `deepagents`: configured mode and server readiness. |
| POST `/workspaces/{id}/research-sessions` | Save objective, reviewed problem/digest, mode and optional design constraints; does not dispatch. |
| GET `/workspaces/{id}/research-sessions` | List private retained sessions. |
| GET `/workspaces/{id}/provider-budget` | Existing shared remaining capacity; session counters below do not replace this global limit. |
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
    "provider_consent_required": false,
    "quota_exhausted": false,
    "recovery": {"required": false, "code": null, "can_reconcile": false, "next_action": "none"},
    "results": {"available": true, "report_ids": ["report_example"], "latest_report_id": "report_example", "evidence_ids": ["run_example"], "download_job_ids": ["job_example"], "commentary_available": false, "deterministic_summary_available": true},
    "suggested_action": "review"
  },
  "provider_usage": {
    "scope": "research_session",
    "physical_requests": 2,
    "reserved_input_tokens": 9000,
    "reserved_output_tokens": 1024,
    "accounted_input_tokens": 9000,
    "accounted_output_tokens": 1024,
    "reported_input_tokens": 1200,
    "reported_output_tokens": 120,
    "reported_thought_tokens": 0,
    "reported_total_tokens": 1320,
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
Reported output excludes separately reported thought tokens; conservative output
accounting includes both, and any unallocated reported total remains charged by
the existing ledger. Missing reported components are `null`, never fabricated
zeros. Reported totals sum only components actually supplied by the provider.
Unknown/reserved attempts keep their allocation and block unsafe resend.
Their recovery projection remains required even if the session state is `failed`:
`code:"provider_outcome_unknown"`, `can_reconcile:false` and
`next_action:"inspect_accounting_or_cancel"`. A lost worker with intact accounting
may offer one explicit reconciliation; a checkpoint without a safely retained
model decision exposes inspect/cancel instead of an endless retry loop.
Quota exhaustion means stop and inspect retained science; do not automatically
raise limits, request another allocation or replace the session identity.
It includes action-specific model/tool limits even when the session allocation
still has capacity.

A successful science child can remain available when model narration fails.
Render deterministic results/downloads independently of `action.error_code` and
model commentary. New validated recommendations create new report snapshots;
historical reports remain selectable. A passed download/replay never upgrades an
inconclusive scientific outcome or certifies narration.

## Immutable report additions

The report body keeps `report_profile:"research-report.v2"`. Additive fields are:

```json
{
  "report_revision": "sha256_of_snapshot_content",
  "action_id": "action_example",
  "agent_commentary": {
    "fact_ids": ["run_example"],
    "text": "Validated evidence-grounded explanation",
    "next_action": "review_design",
    "clarification_fields": [],
    "scientific_authority": false,
    "authorship": "model_commentary"
  },
  "commentary_status": "validated",
  "commentary_support": [{"evidence_id": "run_example", "evidence_digest": "sha256_of_evidence", "kind": "baseline"}],
  "deterministic_summary": {
    "authorship": "deterministic_backend",
    "scientific_authority": false,
    "text": "Deterministic summary of retained scientific outcomes",
    "results": [{"evidence_id": "run_example", "evidence_digest": "sha256_of_evidence", "kind": "baseline"}]
  },
  "model_failure": null
}
```

This is an illustrative shape. Summary result entries retain the actual outcome,
verification, expected binding and native replay fields where available. Controlled
fixtures use commentary `authorship:"controlled_commentary"`. Model failure keeps
`agent_commentary:null`, `commentary_status:"unavailable"`, the deterministic
summary, supporting evidence and native manifests, and `model_failure:{"code":...}`.
Identical retries reuse a snapshot; changed commentary or next action creates a
new immutable revision. `validated` means the existing bounded narration checks
passed, not that prose has mathematical certification.

The focused backend PR is #60. Its checked commit and commands are retained in
`docs/workstreams/deepagents-completion.md`. Treat absent additive fields as
unavailable when connecting to an older server. Browser and live qualification
remain separate. A concurrent plan/report batch captures the plan revision present
at first publication; later plan updates do not mutate that historical report.


Successful scientific proposal preparation now opens the existing canonical
`waiting_review` pause immediately. The UI uses the same pending-review body,
revision/digest checks and decision route; no new route or implicit approval is
introduced. Preparation creates no scientific child. After the human decision,
the model receives `review_decision` and `next_tool` guidance; execution remains a
separate checked tool call. Existing pending run-tool checkpoints remain supported.
This closes the observed pre-review planning loop without raising request limits.
