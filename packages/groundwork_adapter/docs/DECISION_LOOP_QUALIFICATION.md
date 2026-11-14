# Scientific decision-loop qualification

Owner 1, November 14, 2026. Reviewed candidate:
**`f71363589ad5370cabbf99bfaf96c8a2d11e57db`**, [product PR #27](https://github.com/Arnav-M10/DrBean-hp26/pull/27),
including main **`2d2993d1a264d0128a0ea4af8f02010b263016ad`**.

The scientific engine and backend boundaries pass the checks below. No new
scientific implementation, model family, package version or test is warranted.
This review retains acceptance evidence and hands the remaining browser and
independent-evaluation work to its owners. Passing science tests alone is not a
whole-product release decision.

## Candidate, environment and scope

The separate `codex/science-loop-qualification` worktree followed the actual
product branch from `6a3705a` to `f713635`; no historical reference was used as a
reset target. The original worktree and teammate changes remain intact. PR #14
was not merged. Recovery, ledger, design/recheck routing and publication guards
remain present. Production engine, backend and contracts are unchanged from
qualified owner commit `5d66354`; the new integration is browser/release work.

Source and installed **Counterdex 0.3.0** identities independently match
`90b42ae505c9a7c25103331f447edc2e15026d291374f6beefd0ef89c23b7bf8`.
Engine/replay use **CPython 3.11.17**; backend uses locked **CPython 3.13.18** on
Darwin arm64. Tests use sanitized environments and isolated stores. Application
model-provider calls remain disabled. No credentials were inspected and no
provider tokens were consumed. A declared actual observation in these tests is
synthetic test input, not an independently verified physical acquisition.

The retained receipts name the actual clean source commit. This documentation
commit does not relabel those executions as checks of a later integrated tree.

## Executed checks on `f713635`

| Owner 1 execution | Result | Retained evidence |
|---|---|---|
| Full engine/bridge suite, including installed supervisor and four-case proposal-bound recheck | 292 tests: 291 passed, one missing-backend-dependency skip; skipped authoritative DTO test separately passed with backend Python | [engine log](review-evidence/f713635/engine-tests.txt) |
| Focused scientific backend, publication, native design/follow-up, projection, tier and reuse tests | 152 passed, no skips, 34.98 s | [backend log](review-evidence/f713635/backend-focused.txt) |
| Ordinary guarded HTTP lane | 7/7 passed, `executed_acceptance`, no diagnostic overrides, zero external model requests | [per-predicate summary](review-evidence/f713635/ordinary-http-summary.json) |
| Native controls | 22/22 passed | [native results](review-evidence/f713635/native-controls.json) |
| Integrated scientific gate | All required offline predicates passed; live Gemini intentionally not run | [gate receipt](review-evidence/f713635/science-gate.json) |
| Additional actual-origin, own-time unresolved HTTP/worker test and fresh installed CLI replay | 1 passed, 2.40 s; scientific outcome remains inconclusive | [receipt](review-evidence/f713635/unresolved-receipt.json) |
| Strict offline release checklist in a fresh clone with locked dependencies and pinned Playwright/Chromium | 5/5 configured gates, 12/12 configured boundaries; 588 backend, 47 HTTP, 31 web unit tests; 31/31 stack launch-path checks; hypothetical and actual browser modes passed | [complete checklist receipt](review-evidence/f713635/clean-checkout.json), [readable summary](review-evidence/f713635/clean-checkout.txt) |

The fresh clone was clean at the exact tested commit and used its own installed
backend/engine, store and auth fixture. The lock/setup select Playwright 1.63 and
its matching Chromium 153; no operator-selected browser substituted for the
pinned build. Browser versions are derived from that lock/setup and the earlier
cache-populating download log, not a version probe retained by the checklist. Shared
download caches do not supply application state. The release checklist's
`OFFLINE RELEASE-READY` label is its configured-gate result, not acceptance of
uncovered predicates: the concrete browser gaps, normal intake-route integration,
independent retest and optional narration guard below remain separate.

An initial invocation of the HTTP harness omitted its `DRBEAN_BACKEND_PYTHON`
selection and recorded seven unrun cases before starting a stack. The retained
successful run explicitly selects both prepared interpreters. Those unrun
attempts are not counted as acceptance.

## Scientific predicates established

The synthetic baseline discovers its actual pair from reviewed inputs; the
outside candidate is checked against every included row's hard allowance and is
strictly outside the **closed** claim interval. Endpoint equality is inside.
Changed measurements produce fresh dataset/problem/plan identities, new approval
and changed computation while preserving the original history. A bounded search
that finds no counterexample never establishes the claim.

Design binds the two named candidate IDs and exact vectors to the approved
feasible-time grid, future allowance, horizon and budget. Its approval is separate
from baseline approval. Positive separation and no-separation outcomes are both
checked and freshly replayed. Touching bands do not separate. Numerical-only
approval cannot yield a checked-separation claim. A changed allowance invalidates
the old design approval. Neither design outcome says that all outside models
have been eliminated or that the finite grid is globally optimal.

Publication tests reject candidate/vector substitutions, changed row summaries,
projection/anchor substitution, unsupported prospective artifact reuse and tier
upgrades. Mandatory historical parent evidence is distinct from permission to
reuse prospective artifacts. The allowed native reuse path performs zero new
constructions under its adopted contract. A checked no-separation parent can
support recheck; a numerical-only parent is refused before dispatch.

Follow-up separately reviews an observation, materializes a new revision and
requires a fresh investigation plan and approval. Recheck uses each observation's
own declared time and allowance; the supported HTTP cases include `79/10 h` and
`7/20 mg/L` for actual, transcription and hypothetical declarations. It preserves
the original candidate IDs/vectors, raw historical rows and parent evidence.
Candidate exclusion is specific to that vector:

| Original reference | Original outside candidate | Result |
|---|---|---|
| Compatible | Excluded | Inconclusive |
| Excluded | Compatible and strictly outside | Certified counterexample |
| Excluded | Excluded | Inconclusive |
| Unresolved at the checker precision | Excluded | Inconclusive |

For the unresolved control, evaluate the discovered reference vector's enclosure
`[lo, hi]` at `79/10 h`. Submit exact reading `(lo + hi)/2` with positive allowance
`(hi - lo)/4`, explicitly review it, and approve a new recheck plan. The reference
must retain `insufficient_enclosure` and its unresolved row; the outside candidate
is excluded. The packet is valid and replay succeeds, while the scientific
result remains inconclusive. The [receipt](review-evidence/f713635/unresolved-receipt.json)
contains the exact rational values and vectors.

Downloaded native bytes are checked against authenticated metadata and **all
eight external anchors**. Replay uses a new isolated process, not a cached
application verdict. Wrong anchors, changed bytes, resealed false mathematics,
another run's packet and malformed artifact inventories fail. Successful replay
validates what the packet actually establishes; it cannot strengthen an
inconclusive result. It is a fresh execution of the same checker, not a second
independent mathematical implementation.

Replay the retained synthetic unresolved artifact with the matching installed
engine, without the application:

```sh
python3.11 -I -m counterdex replay-native \
  packages/groundwork_adapter/docs/review-evidence/f713635/unresolved.native.json \
  --anchors packages/groundwork_adapter/docs/review-evidence/f713635/unresolved.anchors.json
```

The existing meaningful four-case regression is
`test_bridge.BridgeTests.test_proposal_bound_recheck_distinguishes_survivors_exclusions_and_unresolved`.
The backend parent-tier contract is
`tests/test_native_followup_workflow.py::test_followup_accepts_checked_no_separation_parent_and_rejects_numerical_parent`.
No duplicate implementation or manufactured test was added.

## Browser review and remaining owner handoffs

PR #27 connects retained-source inspection, a controlled intake proposal,
review/correction, assumption preview and exact materialization to a separately
approved scientific plan. Its browser regression computes two baselines,
positive and no-separation designs, downloads their native bytes and anchors,
and replays them. The new actual-origin path uses its own time and allowance and
correctly labels aggregate provenance **Dataset origin**. Controlled proposals
are not live extraction evidence.

Exact findings are handed to Owner 4 in
[PR #27 comment](https://github.com/Arnav-M10/DrBean-hp26/pull/27#issuecomment-6873227653):

1. `apps/web/workflow.mjs` drops the custom research goal when preparing a plan
   from materialized source inputs. `planRequest(materialized.problem)` uses a
   generic fallback; ordinary manual preparation supplies `draft.question.goal`.
   Reproduce with a nonempty custom goal, finish reviewed-source materialization,
   and inspect `plan.body.objective.question`. Preserve the reviewed goal and add
   the browser regression. Plan approval is still explicit; this is not an
   authority bypass.
2. Browser follow-up checks need assertions on the actual candidate outcomes,
   unchanged IDs/vectors/history and native **follow-up** download/replay after
   reopening. Existing assertions on row count, operation and provenance do not
   establish those predicates. Baseline/design replay is not final-packet replay.
3. Browser entry still hides checked `no_separation_established` parents. The
   backend already supports them. Support that contract or explicitly retain it
   as a browser limitation; no additional engine family is needed.

Owner 2 has no new scientific backend correction from this review. Preserve the
checked-parent admission, candidate-specific feedback, immutable revision,
eight-anchor export, recovery and ledger behavior. Any subsequent backend change
requires rerunning the recorded focused cases on its actual resulting commit.
Owner 2's new `backend/source-handoff` branch, published as `6f0a42a`, adopts
Owner 3's controlled proposal generation through the normal intake API. Its
[source handoff contract](https://github.com/Arnav-M10/DrBean-hp26/blob/6f0a42a/shared/contracts/SOURCE_HANDOFF.md)
requires explicit controlled mode, server-selected source/manifest, immutable
review and materialization, and separate execution approval. That integration
is pending on this tested product candidate. The release-only fixture producer
currently used by PR #27 does not qualify the normal proposal-generation route.
The [cross-owner handoff](https://github.com/Arnav-M10/DrBean-hp26/pull/27#issuecomment-6873268762)
supplies the exact scientific predicates to preserve and retest.

Owner 3 owns the separate optional scientific-commentary problem in draft
[PR #28](https://github.com/Arnav-M10/DrBean-hp26/pull/28). Owner 1 reproduced the
14 reported attacks against current main's unchanged guard without a provider
call. Unsupported numerical or global claims can survive that guard. This does
not invalidate the manual approval/native-evidence loop, but prevents claiming
qualified grounded AI narration. The draft's reported conservative fix still
has an independent positive-fixture disagreement; its qualification is not
silently included here.

## Independent evaluation versus these executions

Claude's latest reviewed acceptance is clean combined candidate
**`c8d39b56be1e8692b8608cea687b2b1c6983ef45`**: 7/7 ordinary HTTP cases and
22/22 controls, zero external dispatch. Gate execution was recorded at `58e968f`
and published by `896bfe0`. Its engine source matches this candidate, but its
application/browser tree differs. It is not independent acceptance of `f713635`.

That independent follow-up case already exercises all three resolved survivor
outcomes, own-time actual declaration, synthetic ancestry, native downloads and
fresh replay. It does not exercise the genuinely unresolved band above or the
positive reviewed-source materialization/browser join. Its no-separation controls
are fixed-pair engine checks rather than the application no-separation-parent
workflow. The latest independent records retain the source-materialization P1
pending retest and do not report an open scientific P0.

Claude's precise next acceptance is the actual integrated commit after Owner 4's
corrections: controlled source review/correction/materialization with the custom
goal retained; fresh baseline/design approvals; checked positive and no-separation
parents; all four candidate outcomes with original vectors/history; declared
actual own-time/allowance; final native bytes plus eight external anchors; fresh
replay that leaves an unresolved result inconclusive. Use the matching 0.3.0
source identity and qualified 3.11 runtime. Keep narration attacks and pending
human consultation/device rehearsal separate from scientific acceptance.

The scientific side is ready to support these remaining browser integration
corrections. Final combined-release qualification must name and retest the
actual resulting commit; it cannot inherit this verdict by branch name alone.
