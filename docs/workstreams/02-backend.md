# Current task: source handoff integration

Branch `backend/source-handoff`, base main `2d2993d`. New researcher features
are paused. Main already contains the reconciled recovery, handle cleanup,
conservative ledger and current native science routing; they are reused.

- Works on the inspected branches: PR #20 implements controlled-source intake,
  ordinary review/materialization, and truthful fixture authorship. Its intake
  commit `c20d849` and standalone metadata correction `e4c3c20` are reused here.
- Contract published: [source handoff](../../shared/contracts/SOURCE_HANDOFF.md).
  Owners 3/4 retain proposal-generation/browser ownership respectively.
- Works at `42f92b1`: ordinary controlled intake and exact materialization; eight
  new source-boundary controls pass, including three reproduced stale-context
  failures. Both workspace input heads are now frozen and checked atomically.
- Completed at `42f92b1`: Linux backend 619; ordinary HTTP 8 (diagnostic
  deselected); independent AI 38; unchanged latest Claude ledger attacks 15.
  All six CI jobs pass on tree-identical merge `128aa35`.
- Owner 1 reports exact Mac source controls 8 + source/provider cases 94 passed,
  including corrected measurement → separately approved science → fresh replay.
- Current: reviewable PR #29 and final validation handoff. Retained actual native
  bytes, anchors, replay and commands: [evidence](../evidence/source-handoff/README.md).
- Pending: requested exact Mac operational matrix and Claude's combined
  acceptance. Owner 4 has adopted the ordinary route at `31a8ed3`; browser
  custom-goal/follow-up presentation and Owner 3 narration remain separate.
  No provider calls or credential reads. No whole-release readiness claim.
- PR audit: #21's production fixes are already in main; #14 is obsolete. #20
  has unique controlled intake and separate coordinator accounting work; #22
  has evaluator work, #27 browser work, and #28 explanation work. Do not merge
  those stacks wholesale to obtain this backend seam.


## Historical integration evidence (already on main)

# Backend integration verification

Priority: integration and recovery only; new features paused.
Branch: `backend/integration-verification`; replacement PR #21, ready for integration review.
Agreed base: main `37d8f6f6010e2fe8be3e55323bd6cc18f9112760`, tree-identical
with merged PR #19 `fca07fe4f59eaf7668ea1d2dfeda21be29d6b4a4`.
Tested backend candidate: `4f6c580553b666286177de8080a5e4e5d3d4d2b9`.
Latest main `4b5f1f5` (#12) integrated as `0836eff`; only browser/release-doc
paths differ from the tested candidate, with identical backend/engine/contracts/tests.

## Corrections and PR disposition

- PR #14 must not merge unchanged. Its lifeline guard, queued-cancellation
  reconciliation and restart tests are already incorporated by PR #19. The
  integrated `_watch_parent` and `recover_interrupted` match those earlier
  implementations; newer Darwin tests and scientific recheck routing are retained.
- PR #19's `_kill_owned_session` reaps/retries Darwin zombie-only EPERM and raises
  genuine persistent/live permission failures. It is unchanged here. No blanket
  PermissionError catch was adopted; Claude's one-line patch was diagnostic only.
- One remaining handle leak reproduced on that base: a genuine cleanup denial
  closed the lifeline but skipped receiver/process cleanup. A narrow finally now
  closes transport and reaps while retaining the real permission exception. Live
  Process handles are not closed in a way that masks it with ValueError.
- PR #13 still supplies necessary ledger and bounded controlled-fact fixes.
  Those exact files were reused; only its callback hunk was reconciled onto the
  current worker, preserving v2 design/recheck/observation routing. Its narration
  test first accounts for optional work under the newer coordinator requirement;
  the unsupported narration must still fail. No evidence facts are truncated.
- Recommend superseding #13 with #21 after accepted cross-platform verification,
  and closing #14 as already incorporated/superseded by #19. Do not merge either
  old branch wholesale over the corrected scientific integration.

## Exact executed Linux evidence

Host: Linux 6.18.57 x86_64/glibc 2.41; backend CPython 3.12.14;
matching separately installed Counterdex 0.3 on CPython 3.11.18.
All candidate results below use backend code/tests at `4f6c580`:

| Check | Result |
| --- | --- |
| Full backend (`tests --ignore=tests/integration`) | 588 passed, 225.78 s |
| Ordinary HTTP (`test_http_lifecycle_and_science.py -k 'not diagnostic_barrier'`) | 8 passed, 1 deselected, 53.27 s |
| Separately labeled `science_barrier` test | 1 passed, 8 deselected, 12.15 s |
| Boundary/parent-loss/restart/handle matrix | 26 passed, 16.10 s |
| Claude ledger attacks at unchanged `526f15a`, `--runxfail` | 15 passed, 0.30 s |
| Independent AI boundary + zero-dispatch | 38 passed, 24.55 s |
| Browser units after main #12 merge (`0836eff`) | 30 passed |
| Ruff and whitespace | passed |

Ordinary HTTP observes actual workload cancellation, worker SIGKILL/recovery,
normal/changed inputs, unchanged downloads/fresh replay and no redispatch. The
separate controlled supervisor tests cover timeout, adapter failure, guard failure,
leader loss and genuine permission-error propagation/transport closure. These
controlled tests are not presented as ordinary scientific workload acceptance.
No process limits were relaxed. No model calls or credential probes were made.

The container's PID 1 does not reap orphan zombies. The initial unwrapped base
HTTP run had 8 passed plus 2 teardown errors reporting defunct entries. Final
Linux runs used a test-host child subreaper that only waits/reaps already-exited
descendants: no signals, barriers, limit changes or evaluator assertion changes.
Final evaluator teardown was clean. Ordinary and barrier evidence stay separate.
Test log prefixes in this workspace: `/tmp/integration-final-*`.

## Executed Mac and CI evidence

- Owner 1 executed clean `4f6c580` on Mac: 588 backend tests passed in 86.03 s;
  all 7 ordinary guarded HTTP lane scenarios passed, no diagnostic overrides or
  process-limit relaxation. CPython 3.13.18 backend and 3.11.17 scientific runtime.
  This includes permission-denial closure, timeout, adapter failure, cancellation,
  worker SIGKILL/lifeline cleanup, retained bytes and no redispatch.
- Exact-source report: PR #19 comment `6872682729`. An additional synthetic
  unresolved own-time recheck passed (2.52 s); it retains inconclusive candidate
  status/row identity and fresh packet replay, rather than forcing a binary verdict.
- Mac/Linux installed engine source digest agrees:
  `90b42ae505c9a7c25103331f447edc2e15026d291374f6beefd0ef89c23b7bf8`.
- GitHub CI at `c44b010` (run `43563651309`): all five jobs passed. Linux
  CPython 3.13 backend: 588 passed (107.08 s); independent HTTP/invariant suite:
  47 passed (73.02 s); ordinary-user boundary: 10 passed with 64 owned processes;
  engine: 291 tests, 2 skips; web/harness checks, lint and schema drift passed.
  The final evidence update changes this progress file only, not runtime/tests.

## Preserved evidence and next trigger

- Read Claude's FINDINGS, c231be4 preview README and killpg-eperm-repro.py at
  `526f15a6f4be5aac81232badaba2893ac9fc4aa6`. His branch/tests/findings are untouched.
  Ledger attack file SHA-256: `46aa85b33990396d1d1a2ad1d2d761393e1ca922c6accd373686fddf044a920a`.
  Candidate module path was asserted before running the external test file.
- Earlier retained Mac lane at `159fd65` has identical production paths to
  fca07fe/37d8f6f and records ordinary passing scientific acceptance. It is
  baseline evidence, not Mac qualification of the new 4f6c580 correction.
- Owner 1's actual Mac candidate execution is reported above. The requested
  supplementary run of Claude's unchanged ledger file on Mac is pending; its 15
  assertions already passed on Linux, and candidate-owned ledger regressions
  passed in both complete backend suites. Claude then pushed `896bfe0`; its
  updated EPERM/ledger findings were read and preserved. Its ledger test file
  is byte-identical to 526f15a (same SHA-256 above), so the 15/15 result applies
  to the latest assertions. No validation-owned files or markers were changed.
- Owner 1 subsequently pushed test/evidence-only PR #23 at `5d66354`, stacked
  on #21 and incorporating c44b010/main 4b5f1f5. He reports an additional exact
  clean Mac run: ordinary HTTP 7/7, controls 22/22, unresolved native recheck 1
  passed, web 30 passed, and engine 292 tests (one dependency skip, checked
  separately). Production backend/engine source remains unchanged. Preserve
  that owned regression and portable example as a separate review; do not rebuild it.
- Next: review/merge #21 and supersede obsolete #13/#14 as recommended above;
  preserve any subsequent independent findings. No new numerical or cleanup
  rebuild. Backend checks alone do not establish whole-release readiness.
