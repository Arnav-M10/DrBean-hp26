# Deep Agents backend completion — 2026-11-14

Owner: backend runtime/graph/recovery/reports. PR #60. Browser integration is PR #61;
Claude owns independent qualification and every live provider request.

The audit on main `7d40d1c` still reproduced three backend gaps: unrecoverable
pending continuation, commentary acknowledged without persistence, and baseline
plus design exceeding the existing allocation under the substituted provider.
The implementation preserves the compiled Deep Agents graph and one metered SDK
boundary. No framework, model family, infrastructure, provider limit or admission
policy changed. No provider call or credential inspection was performed.

## Implemented

- Same-action recovery continues retained tool decisions, canonical interruptions
  and committed terminal guards under the existing lease/fence. Unknown provider
  attempts and lost model responses never resend; inspect/cancel is explicit.
- Canonical reports retain validated commentary, next action and exact evidence
  references separately from deterministic results. Identical action/evidence/
  commentary retries reuse a snapshot even across a concurrent plan update.
  Changed recommendations create immutable snapshots. The plan captured at first
  publication remains historical; it may precede a concurrent todo update.
- A completed science child returns its actual scoped canonical evidence to the
  live graph. Independent plan/proposal and plan/report tools may share a model
  response; dependent science/read operations may not. Every tool retains its own
  authority/admission checks. Single-tool responses remain supported.
- Model-only canonical snapshots keep reviewed inputs, candidate vectors, scope,
  checks, prior evidence and proposed next action. Prepared review identities and
  failed/rejected operations survive intervening plan calls. The latest signed
  model/tool exchange is untouched; full checkpoint/audit history is retained.
  The view omits storage labels, prior narration text and checked duplicate copies;
  publication validation still reads full canonical facts. Uncertain/mismatching
  check values are never converted into agreement.
- Additive capability/session projections expose configured mode, waiting states,
  quota/recovery and retained report/download availability. Physical requests,
  conservative reservations/accounting and nullable provider usage are separate.
  `live_qualification` remains `not_run`.

## Executed author checks

Runtime: locked backend CPython 3.13.18; launcher scientific CPython 3.11.17,
matching current Counterdex source. Offline SDK substitutions reject network access
and use deliberately invalid `DRBEAN-DUMMY` values. These are author checks, not
Claude's independent acceptance and not live Gemini understanding.

- Metered application: 7 passed, including actual Counterdex baseline/native replay,
  separately approved design, ordinary worker reconstruction and duplicate resume.
- Real baseline + design: 6 physical requests; reserved input per request
  `[6767, 8326, 10986, 10600, 12237, 14595]`, total **63,511** under the unchanged
  64,000 allocation. Output reservation 3,072. Substituted SDK reports input 120,
  output 36, total 156; these counts are fixture values, not estimated live usage.
- The 61,000-input variant stops before request six, keeps both completed jobs and
  an immutable deterministic fallback report, and refuses an unsafe repeated advance.
- Live fact projection: 37 passed, including mismatched anchors, explicit unknowns,
  numerical guidance and inconclusive results surviving successful replay unchanged.
- Recovery/authority/ledger/HTTP: 46 passed; context/continuation recovery: 30 passed.
- Report/integration: 51 passed; context snapshots: 34 passed; UI projections: 19 passed.
- Ruff and whitespace checks passed. Full backend/CI qualification is in progress;
  final candidate results will be appended before handoff.

## Remaining scope

Claude must qualify actual Gemini tool behavior, signed-part acceptance, provider
usage and combined browser operation on one integrated commit. The 489-token
reservation headroom is small and applies only to the measured request shape;
verbose or larger inputs stop honestly with completed science preserved. No cap
increase or budget replenishment is authorized by these checks. Automatic follow-up
observation execution remains deferred in the current capability contract.

The UI route/field examples are in `docs/integration/DEEPAGENTS_COMPLETION_UI.md`.
