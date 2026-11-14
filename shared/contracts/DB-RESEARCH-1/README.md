# DB-RESEARCH-1 executable seam

Executable examples: `examples.json` (valid/refused requests) and
`event-plan.fixture.json` (bounded producer-authored event and plan shape).
`scripts/export_contracts.py` generates the public schemas from the Python types.

Private ports include read-only `check_authority()` and
`execute_child(review_id, expected_review_digest)`; dispatch revalidates that
exact digest in the canonical reservation transaction. Preparation/review/child
responses contain `review_id`, `review_digest`, `kind`, `approval_id`, and
`scope={plan_id,plan_digest,input_digest}`. `input_digest` identifies the immutable
research origin; each scientific plan additionally binds its exact dataset/problem
revision, including a separately reviewed later observation. `context()` returns
the original objective/question and reviewed context, explicit `reference_ids`,
canonical `reviews`, current admitted `budget` and optional design constraints.

Schema2 adds research records to the same SQLite store. Journal intent is durable
before scientific reservation; canonical child creation and journal association
are atomic. A lost checkpoint/acknowledgement reconciles that child without new
science allocation. Unknown inference outcomes pause for reconciliation and stay
reserved; recovery does not automatically repeat inference. Human waiting releases
the advancing lease and retains action counters, thread and immutable reviews.

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

Each active action retains ceilings: four model turns, six tool attempts,
two science reservations and 300 active seconds; design stays stricter. Pauses
release the lease and do not consume active time. New sessions persist
`research-session-limits.v2`:16 logical model turns,24 tool attempts and4 scientific
children. The initial8-turn proposal could not fit the complete multi-review loop.
Legacy session records retain their8-turn limit; a restart does not upgrade it.
This logical limit grants no provider requests. Physical calls are separately
limited by explicitly admitted session
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
