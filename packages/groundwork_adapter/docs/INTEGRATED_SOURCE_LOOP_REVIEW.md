# Integrated source-to-science qualification

Owner 1, November 14, 2026. Exact integrated candidate:
**`5507519cb0bd12cd3b18acd3ff87ed643470d84e`**. This is the actual merge of
Owner 1's retained review with product **`31a8ed3c9b66ed721cf2f37179ab3fe62ebe0d09`**
([PR #27](https://github.com/Arnav-M10/DrBean-hp26/pull/27)), including backend
**`42f92b1b07f52f4336cc4449928bc781e30ae0fe`**
([PR #29](https://github.com/Arnav-M10/DrBean-hp26/pull/29)) and main `2d2993d`.
Both owners' authored history, recovery and ledger changes are preserved.

The normal controlled-source API and final follow-up download/replay now join
the tested scientific loop. The earlier missing-route and final-packet findings
are resolved on this integration. No scientific implementation, model family,
package version or new test is needed. Owner 1 adds only review/evidence/logs in
[PR #30](https://github.com/Arnav-M10/DrBean-hp26/pull/30).

## Exact execution scope

Counterdex **0.3.0**, qualified **CPython 3.11.17**, backend **CPython 3.13.18**,
Darwin arm64. Source and installed implementation remain
`90b42ae505c9a7c25103331f447edc2e15026d291374f6beefd0ef89c23b7bf8`.
The actual resulting merge was tested clean; prior component successes were
not relabelled as combined acceptance. Environments/stores were isolated and
application model-provider calls remained disabled. No real keys were inspected.

- **7/7 ordinary HTTP cases**, no diagnostics; 214 executed predicates passed,
  including 130 follow-up predicates, and zero guarded external model attempts.
  [Exact case/record identities](review-evidence/5507519/ordinary-http-summary.json).
- **22/22 native controls** and all required offline scientific gate predicates
  passed. [Controls](review-evidence/5507519/native-controls.json),
  [gate](review-evidence/5507519/science-gate.json).
- **Actual-origin own-time unresolved HTTP/worker/native replay** passed in
  2.92 s. Reference remains `inconclusive/insufficient_enclosure`; outside vector
  is excluded. Packet verification is valid and replay passes without upgrading
  the scientific outcome. [Exact inputs and vectors](review-evidence/5507519/unresolved-receipt.json).
- **Installed-supervisor, four-outcome bridge and authoritative DTO** checks
  separately passed on this merge under their prepared runtimes, covering the
  two conditional tests in the standard engine suite.
  [Commands and output](review-evidence/5507519/conditional-engine-checks.txt).
- **Strict fresh-clone checklist:** all 23 checks, five configured gates and 12
  configured boundaries passed. **619 backend tests**, **47 independent HTTP
  suite tests**, **31 web unit tests**, **32/32 stack launch-path checks**, full
  engine and harness suites, lint/schema export, ordinary-user process boundary,
  and both hypothetical/actual browser modes passed. The two conditional engine
  skips were separately covered above. [Unmodified JSON](review-evidence/5507519/clean-checkout.json),
  [readable output](review-evidence/5507519/clean-checkout.txt).

The fresh clone installed locked backend/engine environments with its own auth
fixture and store; pinned Playwright used its matching Chromium. The checklist's
configured release-ready label does not cover the remaining browser predicates,
independent acceptance or optional narration qualification below.

The browser tests now prepare controlled proposals through the ordinary
authenticated intake route, review/correct values, transfer them into the draft,
materialize exact inputs and require separate scientific approval. They exercise
two baseline computations, separately approved positive/no-separation designs,
hypothetical and actual-declaration follow-ups, and downloaded native bytes plus
external anchors with fresh isolated replay. Changed image bytes return empty
unavailable/manual fallback and preserve previously accepted science. No release
helper writes proposal records directly into storage.

Before this merge, the separate backend component at `42f92b1` passed **102
macOS tests**: eight new source boundaries, the 77-test source/provider slice
and 17 legacy intake cases. A `24/5 → 97/20` correction retained original `4.80`
and reached real science and fresh replay. Both workspace input heads are checked
transactionally; stale context/source changes refuse new acceptance while saved
identical retries preserve existing records. That component used a parent pytest
socket guard and sanitized children, not an independently established arbitrary
subprocess guard. [Exact component result and scope](https://github.com/Arnav-M10/DrBean-hp26/pull/29#issuecomment-6873351534).

## Scientific conclusions and remaining handoff

The [full scientific predicates](DECISION_LOOP_QUALIFICATION.md#scientific-predicates-established)
remain established: outside is strict relative to a closed claim; every included
row uses its reviewed hard allowance; search failure is inconclusive; design is
about the named fixed pair on its approved grid; numerical authority cannot
upgrade; changed assumptions require fresh approval; substitutions fail
publication; follow-up preserves original vectors/history at its own time and
allowance. Reference-only survival, outside-only survival, both excluded and
unresolved remain distinct. Candidate exclusion never eliminates all outside
models. Successful replay cannot strengthen an inconclusive scientific result.

Reproduce the retained unresolved synthetic packet without the application:

```sh
python3.11 -I -m counterdex replay-native \
  packages/groundwork_adapter/docs/review-evidence/5507519/unresolved.native.json \
  --anchors packages/groundwork_adapter/docs/review-evidence/5507519/unresolved.anchors.json
```

Remaining product findings are with **Owner 4**:

1. Source materialization still calls `planRequest(materialized.problem)` without
   the reviewed custom goal. Preserve `getDraft().question.goal` and assert exact
   `plan.body.objective.question`; current browser goal-edit coverage only checks
   preview invalidation, not the resulting question.
2. Checked `no_separation_established` parents still have no browser follow-up
   entry although the backend permits them. Support it or explicitly retain
   this browser limitation.
3. Browser feedback assertions need exact survivor semantics and unchanged
   candidate IDs/vectors/history. Current browser checks exercise automatic
   opening and final-packet replay; a separate reconnect/reopen acceptance and
   all-four-outcome browser matrix remain unqualified. Backend/engine coverage
   is stronger and must not be presented as that browser coverage.

**Owner 2:** no new scientific backend defect found. Preserve its accepted-input
and source-context safeguards. **Owner 3:** optional narration guard PR #28 remains
separate; current commentary is not qualified against the 14 reported attacks.
**Claude:** independently accept this actual combined tree, the normal-route
positive source join, no-separation-parent path and genuinely unresolved band.
Its reviewed `c8d39b5` acceptance remains distinct from Owner 1's new executions.
The [latest exact handoff](https://github.com/Arnav-M10/DrBean-hp26/pull/27#issuecomment-6873369338)
identifies the resolved and remaining joins.

The scientific side is qualified to support browser completion. This is not a
whole-product release verdict, physical measurement validation or live Gemini
qualification. Subsequent production changes need checks at their resulting
commit; evidence-only commits preserve the tested source labels.
