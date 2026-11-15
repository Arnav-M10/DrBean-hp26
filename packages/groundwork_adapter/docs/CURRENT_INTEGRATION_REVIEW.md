# Current scientific integration review

The current review of main `2d2993d`, backend `42f92b1` and product `31a8ed3`,
tested after integration at `5507519`, is
[Integrated source-to-science qualification](INTEGRATED_SOURCE_LOOP_REVIEW.md).
The evidence below is retained as the historical backend-integration review;
its checks and browser handoffs are not silently relabelled as current results.

Owner 1, November 14, 2026. Counterdex **0.3.0**, prepared CPython **3.11.17**,
Darwin arm64; backend CPython **3.13.18**. Scientific implementation identity:
`90b42ae505c9a7c25103331f447edc2e15026d291374f6beefd0ef89c23b7bf8`.
No production scientific code, protocol, package version or archived fixture
changes are needed. Gemini remains disabled; no application provider calls.

## Candidate and ownership

The initial integrated main was `37d8f6f6010e2fe8be3e55323bd6cc18f9112760`, the
actual PR #19 merge. Its tree equals `fca07fe`; the historical head was not used
as a reset target. The newer backend integration candidate is
**`4f6c580553b666286177de8080a5e4e5d3d4d2b9`**, directly based on that main.
It retains current design/recheck routing and adds Owner 2's ledger, bounded
controlled facts and cleanup-handle corrections. Owner 1 adopted that authored
commit without duplicating its implementation. During qualification, main advanced
to **`4b5f1f5b4f3e08223422106d8c6e8c6554611d76`**, merging the reviewed product
branch. Owner 2 incorporated that merge and verification notes as
`c44b010f4697c74cf9f3f05da6122f877df79a2e`; this owner branch merged that current
candidate too. Other worktrees remain intact.

This owner branch only adds scientific regressions, this handoff and receipts,
and the Owner 1 progress entry. Its resulting commit is retested separately;
the PR records that exact SHA. Tests on the base are not silently relabelled as
tests of a later commit.

## Executed checks

| Execution | Actual source | Result |
|---|---|---|
| Owner 1 focused science/publication/recovery tests | clean main `37d8f6f` | 207 passed, 55.90 s |
| Owner 1 full backend suite, including cleanup, controlled native evidence and ledger changes | clean candidate `4f6c580` | 588 passed, 86.03 s |
| Owner 1 execution of the integrated ordinary HTTP harness | clean candidate `4f6c580` | 7/7 passed; no diagnostic overrides; guarded zero model dispatch |
| Additional Owner 1 HTTP/worker unresolved-recheck test, downloaded bytes and installed CLI replay | clean candidate `4f6c580` | 1 passed, 2.52 s |
| Owned bridge four-case regression, installed supervisor and separate-process replay | clean owner commit `1a678f6` before the product merge | 292 tests: 291 passed, one backend-dependency skip; the skipped authoritative DTO check separately passed under backend Python |
| Owner 1 ordinary lane, native controls and unresolved HTTP/replay | same clean `1a678f6` | 7/7 ordinary; 22/22 native controls; unresolved HTTP passed again in 2.45 s; all scientific gate predicates passed |

The [backend log](review-evidence/4f6c580/backend-full.txt),
[ordinary execution summary](review-evidence/4f6c580/ordinary-http-summary.json)
and [unresolved receipt](review-evidence/4f6c580/unresolved-receipt.json) retain
their actual tested commit. The original complete evaluator histories remain
unchanged. Wall times are local test times, not provider latency.

The backend matrix covers actual discovery and compatible strict outside
witnesses, exact input/projection binding, separate design approval, native
downloads, fresh replay, own-time/allowance follow-ups, numerical-only tier
preservation, prospective-reuse rejection and resealed vector/status attacks.
Recovery includes ordinary cancellation, timeout, adapter failure, worker loss,
retained evidence and no redispatch. Genuine signalling denial remains an error;
the new outer cleanup finally releases transport handles without masking it.

## Follow-up predicates and reproduction

Run the new package regression with a prepared engine interpreter:

```sh
PYTHONPATH=packages/groundwork_adapter:packages/groundwork_adapter/tests \
  python3.11 -m unittest \
  test_bridge.BridgeTests.test_proposal_bound_recheck_distinguishes_survivors_exclusions_and_unresolved -v
```

It discovers the pair from supported input, selects reference/outside by checked
candidate ID, and preserves those exact vectors. The three resolved controls use
their own **79/10 h** and **7/20 mg/L** allowance, independently of the selected
design time. Full accepted-proposal and parent-byte binding are retained. Search
is forbidden during recheck. Synthetic controls declaring an actual observation
still retain synthetic dataset ancestry.

| Reference | Outside | Permitted scientific outcome |
|---|---|---|
| compatible | excluded | inconclusive |
| excluded | compatible and strictly outside | certified counterexample |
| excluded | excluded | inconclusive |
| unresolved | excluded | inconclusive |

For the unresolved control, compute the original reference vector's supported
concentration enclosure `[lo, hi]` at 79/10 h. Use exact reading `(lo+hi)/2` and
positive allowance `(hi-lo)/4`. That band is strictly inside the retained
enclosure: this fixed proof profile can establish neither compatibility nor
disjointness. The candidate must retain `inconclusive`, `insufficient_enclosure`
and its unresolved row ID. Successful packet verification/replay does not make
that candidate compatible. A more precise independent decimal calculation may
resolve the physical band; it must not erase the native checker's uncertainty.

The HTTP control uses the existing `tests/test_native_followup_workflow.py`
computed-design and reviewed-input helpers. The receipt retains its exact
rational reading/allowance and discovered vectors. It independently accepts the
proposal, requires a new plan approval, downloads native bytes and all eight
external anchors, and checks their identities against authenticated records.
Replay the preserved **synthetic example** without the application:

```sh
python3.11 -I -m counterdex replay-native \
  packages/groundwork_adapter/docs/review-evidence/4f6c580/unresolved.native.json \
  --anchors packages/groundwork_adapter/docs/review-evidence/4f6c580/unresolved.anchors.json
```

Both files are necessary; packet-internal identities do not authenticate their
own expected anchors. Original dataset rows, parent native bytes and exact
candidate vectors remain retained. Only the revised projection's provenance
cites the new dataset digest. Candidate exclusion never eliminates every outside
model, proves a global parameter claim or triggers replacement discovery.

## Independent evidence and next owners

Claude's branch `526f15a` retains useful historical findings but has not retested
the PR #19 merge or candidate `4f6c580`. Its ordinary `d6503da` failures used the
older engine/application state; its `9a6db61` results were a six-of-seven preview
and a separately labelled worker-loss diagnostic. Those are not fresh failures
of the current candidate. Owner 1's execution of the integrated harness is
distinct from Claude's own independent retest. Claude should preserve history,
adopt current full-proposal qualification, and retest this candidate ordinarily,
including genuine unresolved recheck and unsupported nonempty reuse before
approval. The 80-digit oracle must not demand false resolution of a conservative
native enclosure. Source materialization also needs its independent positive
review → immutable values → separate approval → computation/replay check.

Owner 2 owns any further backend/recovery correction and integration of its
researcher-tools branch `8f31dda`, whose older base must not replace the current
guards. Owner 3's newer controlled-source branch `21cd940` also needs integration
onto current main before qualification. Their authored features were reviewed;
their stale branch tips were not presented as current integrated candidates.

Owner 4's product `9ba9c6a`, now merged in main `4b5f1f5`, preserves the qualified
backend, but its new follow-up
display only handles `review` while current jobs emit `recheck`. A read-only
Node reproduction with actual retained records omits the dedicated feedback
table. It also labels aggregate `dataset_origin` as observation origin: an
actual-origin declaration may have synthetic ancestry. Recognize both native
operations, retain candidate statuses/reasons, and display ancestry separately
from the accepted proposal's origin/time/allowance. The backend exposes that
proposal through the run's plan follow-up reference and record route.

These are browser integration defects, not reasons to expand the engine. G4
still needs source review/materialization and follow-up entry/review/separate
approval controls. Reopening an existing result alone does not complete them.
The scientific side is ready to support that browser work; a full product
release claim waits for its actual resulting integration and independent checks.

Coordination: [Owner 2 / Claude candidate results](https://github.com/Arnav-M10/DrBean-hp26/pull/19#issuecomment-6872682729)
and [Owner 4 concrete display defects](https://github.com/Arnav-M10/DrBean-hp26/pull/12#issuecomment-6872625724).
