# DB-RESEARCH-1 executable seam

B branch `codex/durable-research-application`, base main `299a356`. Public DTOs
and private ports: `apps/api/bean_api/research_contracts.py`. A owns graph state,
factory/model adapters and policies; B owns canonical records/ports/checkpoints,
worker, routes and UI; C independently challenges the combined candidate.

Routes under `/api/bean/v1`:
- `POST /workspaces/{wid}/research-sessions`: ResearchCreate.
- `GET /research-sessions/{sid}`: authorized snapshot, private thread hidden.
- `POST /research-sessions/{sid}/advance`: ResearchAdvance; stable Idempotency-Key.
- `POST /research-sessions/{sid}/decisions`: ResearchDecision; canonical approval
  and queued resume recorded in one transaction. No raw graph command accepted.
- `POST /research-sessions/{sid}/reconcile`: ResearchReconcile, explicit unknown
  acknowledgement; reconcile existing child/evidence before any retry.
- `POST /research-sessions/{sid}/cancel`: revoke further admission and cancel its
  owned child. `GET .../events?after=N`: bounded ordered read, no side effects.

Scientific preparation returns `{review_id,review_digest,kind,scope,approval_id}`.
`require_review` returns a validated decision or tells A to call a genuine graph
interrupt with that canonical reference. `execute_child(review_id)` resolves the
approved immutable plan and journals/reuses its one job; arguments/actor/budget
never come from the model. Child provider remains none. Human observation review
uses existing dedicated routes; continuation accepts only that reviewed receipt.

`factory(*, context, ports, checkpointer, model_factory, event_sink, policy)` is
the proposed A factory seam; A supplies the exact factory/version and graph-state
compatibility. B privately constructs ResearchRuntimeContext and provides a
tenant-scoped LangGraph saver. Graph checkpoints contain bounded state/refs;
native bytes remain in artifacts. B journals each tool effect before dispatch;
checkpoint failure does not delete a completed job/evidence or justify new work.

Each active action retains lower bounds: four model turns, six tool attempts,
two science reservations and 300 active seconds; design stays stricter. Pauses
release the lease and do not consume active time. Session cumulative proposed
ceilings are eight logical model turns, 24 tool attempts and four scientific
children. Physical calls are additionally limited by existing admitted session
allocation and server-wide ledger (no automatic 12/24 allocation or new grant).
Default live allocation is zero; one physical request is charged by A's single
dispatch adapter through B's atomic ledger, not twice by graph middleware.

Membership/current heads/digests/consent/cancel/lease fence are rechecked at each
side effect and decision. Browser-cookie rotation retains identity; expiry or
revocation refuses access. Paused records/checkpoints are retained independently
of the 24-hour cookie; no cross-device/expired-cookie account recovery is claimed.

Success: same accepted problem, canonical approved plan, reused stable action/job
after lost acknowledgement. Refusal: changed problem digest, stale review,
forged approval, cross-workspace reference, expired lease or model-supplied actor.
No claim of completed runtime until actual routes/factory/worker tests pass.
