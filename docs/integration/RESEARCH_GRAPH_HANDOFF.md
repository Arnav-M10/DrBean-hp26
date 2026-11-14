# A → B/C: the actual research graph

Assignment: DB-COORDINATOR-3OWNER-1. A branch:
`codex/three-owner-agent-science`, from main `299a356`.
B's canonical application seam is **DB-RESEARCH-1**, published at `d224846`
in `apps/api/bean_api/research_contracts.py` and
`shared/contracts/DB-RESEARCH-1/README.md` on
`codex/durable-research-application` ([PR #41](https://github.com/Arnav-M10/DrBean-hp26/pull/41)).
Those files remain B-owned. This document describes A's implementation and
required adapter preconditions; it does not replace the public DTOs.

## Implemented component

`bean_api.research_coordinator.create_research_coordinator` builds the actual
pinned Deep Agents graph. `ResearchCoordinator.start`, `resume`, `advance`, and
`snapshot` are trusted worker methods, never public LangGraph command endpoints.

- `start` requires an empty backend-supplied private thread.
- `resume` wakes a genuine pending graph interrupt after rereading its canonical
  review. It never consumes approval values from a model or browser payload.
  B can explicitly use `resume(new_action=True)` after atomically admitting a
  new approval action. The same immutable session/input/question/mode and pending
  review must match. This transition cannot renew an action waiting for a child.
- `advance` starts a separately admitted bounded action only after a previous
  canonical report/clarification, retaining thread history and planning state.
  B must admit the new action/body and allocation first. Session/global counts
  remain cumulative; this method creates no allocation.
- `snapshot` is an authorized read. It never invokes a model or scientific job.

State and tool policy are `research-graph.v1` / `research-tools.v1`; internal
adapter ports are `research-ports.v1`. A's internal `ResearchContext` is built
from B's private runtime and authorized snapshot. It binds workspace/session,
action, question, exact input digest, reviewed context, mode, limits and policy.
Changed context or an incompatible graph version cannot resume an old action.

The effective compiled tool inventory is exactly:

```text
prepare_scientific_proposal
publish_research_report
read_research_evidence
request_clarification
run_scientific_operation
write_todos
```

The actual SDK `TodoListMiddleware` writes checkpoint planning state. Its bounded
projection retains completed steps and labels all todo statuses as agent
proposals. A todo completion is never a canonical job completion. Host filesystem,
shell, arbitrary network tools, generic delegation and model-backed summarization
are disabled. Named specialists stay deferred until the ordinary parent loop is
integrated and qualified.

Normal model termination without an accepted backend report or clarification is
`research_completion_unaccepted`. Arbitrary prose cannot finish an investigation.
Model-generated report commentary uses the existing narrow scientific explanation
guard; canonical facts and report manifests remain backend/Counterdex authority.

## Review and side-effect predicates

A prepared unaccepted proposal supplies immutable proposal ID/digest and canonical
review ID/digest. The run tool freezes **all four**, checks them on every tool
entry, and supplies them to the backend execution port. This includes replayed
nodes after interruption. A resume preflight alone is insufficient: approval or
review replacement can race with the later dispatch.

B's execution port must atomically enforce the same exact review digest,
current approval, actor/workspace/session/input scope, cancellation, fence and
scientific allocation at dispatch. It journals/reconciles the action + proposal
to the existing child ID before starting anything new. A graph tool-call ID is
only an observation key, not scientific idempotency or approval authority.

The design/follow-up children remain the current deterministic provider-free
operations. A parent model decision does not widen their scopes. Missing hard
allowances, units, time origins, distinct compatible candidates or reviewed
design constraints produce clarification/unavailable behavior. Numerical or
inconclusive evidence never becomes checked separation or a proved claim.

`GraphInterrupt` is allowed to bubble to LangGraph; no blanket exception handler
converts human waiting to failure. Active deadlines exclude human waiting, but
resuming does not reset the action's logical counters or durable allocation.
Cancellation preserves completed child evidence and prevents a false report.

Tool events include action ID, tool-call ID and an argument digest; review events
include the canonical review identity. B assigns durable event IDs/sequences and
deduplicates replayed observations. No hidden chain of thought is exported.

Queued/running children produce `canonical_scientific_child` interrupts carrying
the exact job ID and review binding. Ordinary resume rechecks those identities
and reconciles the same job. Outputs distinguish `paused`, `awaiting_review`
and `awaiting_child`; the UI must not ask a human to approve mere child waiting.
Logical tool admission occurs once after model output, not again when an
interrupted tool wrapper replays.

## Canonical B adapter requirements

The async `bean_api.research_integration.create_application_research_coordinator`
accepts `context`, `ports`, `checkpointer`, `model_factory`, `event_sink`, and
`policy`, mapping B's published port names to the internal factory;
the production worker must use this same factory, not a test-only graph.
Before registration, B must supply the following, with explicit unavailable
states if an operation is not implemented:

1. A validated private runtime context with current graph/checkpoint/action
   policy versions, actor/workspace/session/action/operation identity, private
   thread and lease fence.
2. `ports.context()` returning the exact `objective`, `reviewed_context`,
   `input_digest`, admitted `budget`, and `design_constraints` (or explicit
   `None`), plus explicit scoped `reference_ids` and `reviews`. Question text is
   preserved, not regenerated from a chart or model.
3. A read-only `check_authority` port for checkpoint/history reads and callbacks.
   Scope matching means the exact research inputs, not merely the same workspace.
4. Canonical preparation/review responses with immutable proposal identity.
   `execute_child(review_id, expected_review_digest=...)` must enforce that digest
   atomically, or B must publish an equally strict action-bound implementation.
   A's adapter expects canonical `scope.plan_id`, `scope.plan_digest` and
   `scope.input_digest`, plus `review_id`, `review_digest`, `kind`, `approval_id`.
   Child responses echo that binding with `job_id`, `state`, `evidence_ids`;
   report responses provide their actual `evidence_ids`. Unconfirmed producer
   shapes remain unavailable instead of being guessed from unrelated IDs.
5. `admit_model` and `admit_tool` with cumulative durable limits and current
   lease validation. Logical model-turn admission is not another physical-request
   ledger charge. Planning writes count as tools.
6. Idempotent plan projections and report/event records, plus disk-backed safe
   checkpoint serialization, version compatibility/refusal and an explicit
   journal rule for child/checkpoint/acknowledgement gaps.

The adapter fails closed for absent requirements. A supplied `InMemorySaver`
can prove graph reconstruction in tests; it cannot prove a process restart.
Production capability flags must stay unavailable until actual startup, storage,
worker and UI registration are qualified.

## Metered model boundary

`build_gemini_chat_model(gateway=..., context=..., output_tokens=...)` returns the
restricted async `GeminiChatModel`. The gateway uses existing `ProviderConfig`
and `begin_attempt` / `finish_attempt` hooks. One physical request gets one
reservation and one finalization attempt; no automatic retries, paid fallback,
new store, silent refund or SDK function execution is introduced.

Tool binding keeps the same immutable request context. Injected `ToolRuntime`
fields are excluded from model schemas; unknown tool arguments and altered
tool-result/signature histories are refused. Unknown response usage and cancelled
outcomes stay unknown/conservatively accounted. Tracing is disabled.

The live graph requires this exact admitted adapter/gateway, matching
workspace/session/action context and an actually live gateway mode. The old
controlled graph also refuses this provider-capable adapter, including local
subclasses. Controlled gateway conformance tests never claim live provenance.

Live requires B's ledger to advertise `session_accounting_version =
"research-session.v1"` **only after** its admission atomically validates the
research session/action, actor, consent, allocation and fence. Current main does
not implement this marker. A string marker alone is not evidence of correct
accounting, an allocation, external free-tier availability or billing status.
No provider calls or credential inspection are necessary for this integration.

## Runnable checks and remaining qualification

Use the prepared backend runtime and a source-matching Counterdex CPython 3.11
installation. The engine and replay interpreter must be selected explicitly.
The root workstream log retains actual results and tested commits.

```sh
BEAN_AI_MODE=placeholder \
BEAN_COUNTERDEX_PYTHON="$PWD/.venv-engine/bin/python" \
BEAN_COUNTERDEX_REPLAY_PYTHON="$PWD/.venv-engine/bin/python" \
PYTHONPATH="$PWD/evaluation/drbean_eval/guard" \
DRBEAN_EGRESS_GUARD_LOG=/tmp/drbean-coordinator-guard.jsonl \
  .venv/bin/python -m pytest -q tests/test_research_coordinator.py \
  tests/test_research_coordinator_adversarial.py tests/test_research_coordinator_native.py \
  tests/test_research_integration.py \
  tests/test_gemini_chat_model.py tests/test_gemini_chat_gateway.py
```

The native component tests prepare an actual unapproved plan through ordinary
authenticated APIs, interrupt, obtain canonical approval, run the provider-free
worker and inspect real evidence. Changing the reviewed claim changes the
computed outcome and model-selected next action. Exact questions, candidates,
native bytes and external replay anchors are retained. Parent event/admission
ports and pending-review views in those tests are explicitly local harnesses.

B still must qualify disk/process restart, concurrent leases, ordinary routes,
the complete design/new-reading loop and private browser flow on its actual
integrated commit. C independently challenges the assembled product and provides
its own held-out inputs. These A author checks do not establish live model
adaptivity, browser completion or final release readiness.

See [the scientific truth table](COORDINATOR_SCIENTIFIC_TRUTH_TABLE.md) for precise
scientific wording, outcomes, pair eligibility and replay distinctions.
