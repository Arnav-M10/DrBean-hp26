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
- Backend sweep: 1,451 passed (156 s); this preceded the last projection regression
  additions. The complete final-candidate rerun and CI are recorded in the PR #60 check summary.
- Exact integrated implementation candidate
  `114aae410062d6abe05fb96db9bfb846ae0de8bd` (includes main `a876543`):
  science/metered/reports/integration group **107 passed**; recovery group **30
  passed**; projection/context/HTTP group **68 passed**. Web units **108 passed**;
  preferred-preview units **15 passed**.
- Engine discovery: **292 run, 290 passed, 2 environment skips**; both skipped
  predicates passed separately under their required bridge/API runtimes. Fresh
  native replay passed integrity/binding/verification and matched its recorded
  result. All 24 installed Counterdex Python source files matched this candidate.
- Ruff and whitespace checks passed. The two changed research schemas reproduce
  exactly. Full local schema generation also changes unrelated PDF bounding-box
  examples on macOS; those changes were excluded and the existing Linux CI schema
  check remains the full-generator gate.

## Remaining scope

Claude must qualify actual Gemini tool behavior, signed-part acceptance, provider
usage and combined browser operation on one integrated commit. The 489-token
reservation headroom is small and applies only to the measured request shape;
verbose or larger inputs stop honestly with completed science preserved. No cap
increase or budget replenishment is authorized by these checks. Automatic follow-up
observation execution remains deferred in the current capability contract.

The UI route/field examples are in `docs/integration/DEEPAGENTS_COMPLETION_UI.md`.

## Reproduction

With the launcher’s locked backend environment and matching 3.11 engine:

```sh
export BEAN_AI_MODE=placeholder BEAN_RESEARCH_MODE=disabled
export BEAN_COUNTERDEX_PYTHON="$PWD/.venv-engine/bin/python"
export BEAN_COUNTERDEX_REPLAY_PYTHON="$BEAN_COUNTERDEX_PYTHON"
export PYTHONPATH="$PWD/packages/counterdex_models"
.venv/bin/python -m pytest -q tests --ignore=tests/integration
.venv/bin/ruff check apps tests scripts
```

Focused provider-failure seam (trusted test injection only, never an HTTP switch):
`tests/test_research_reports.py::test_uncertain_substituted_gemini_after_science_keeps_summary_downloads_and_reservation`.
The actual live model and graph remain in place; only the SDK response is replaced,
and network access is denied. Browser tests can inspect the resulting ordinary
session/report fields without adding a production failure-control endpoint.

## Independent validator handoff

C's probe file from `claude/deepagents-qualification` at
`2a378162db2ba8e39be0fe5a8bba3aa6839320ec` was replayed unchanged against
`114aae4` with `--runxfail` in scratch storage (only its fixture ROOT path was
redirected to the candidate). This was **our reproduction**, not independent
acceptance: three ACC-07/08 probes passed. ACC-06 passed its downloaded-commentary
and cited-evidence checks, then its broad substring assertion rejected the
existing limitation saying fresh replay is **not** an independently implemented
proof system. That overbroad predicate was reported to C on PR #60; the limitation
was preserved. C must refine/re-run its acceptance against the combined browser
candidate. No live check was performed here.

## Live findings and repair — follow-through

Claude’s first live run at `a2f568b` used five requests: canonical review, approved
real science and replay succeeded; numeric commentary was correctly rejected.
A later preferred-workspace run at `a43d5b2` used three requests and stopped on a
malformed tool call before review/science. Those are failed live acceptance cases,
not evidence of a qualified Gemini release. The reported sprint use is eight of
12 physical requests, with ten effective grants; no limit was raised here.

The report instructions now state the exact accepted neutral caption. Scientific
facts remain in the canonical report, while planning, tools and next_action remain
model decisions. The run tool explicitly asks for the four prepared identity fields
verbatim. Numeric validation, operation authority and retry policy are unchanged.
The two signed-SDK/native-science narration cases both use three calls with the
same allocation: incorrect numeric prose stays rejected and preserves science;
the instructed caption persists with an evidence-dependent review_design action.
Baseline plus design still fits six requests: 63,709 conservative input reservation
under 64,000. The reserved output remains 3,072; this is offline accounting evidence.

Malformed tool responses now retain bounded diagnostic enums, a declared tool name
and schema-known missing-field names only. Raw model arguments, unknown names,
text and IDs are never included. Request/usage accounting and main error codes stay
unchanged. The prior live malformed call was not retained before its rejection;
these diagnostics do not claim to identify or repair that historical response.

Claude explicitly authorized adopting the DEMO-09 R1 oracle from `9229150`; that
exact test update is included. The coordinator action stays failed if required
commentary fails. Completed science and commentary availability remain separate.
