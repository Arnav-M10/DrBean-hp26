# Backend integration verification

Priority: integration and recovery only; new features paused.
Branch: `backend/integration-verification`; replacement draft PR #21.
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

## Preserved evidence, Mac status and next trigger

- Read Claude's FINDINGS, c231be4 preview README and killpg-eperm-repro.py at
  `526f15a6f4be5aac81232badaba2893ac9fc4aa6`. His branch/tests/findings are untouched.
  Ledger attack file SHA-256: `46aa85b33990396d1d1a2ad1d2d761393e1ca922c6accd373686fddf044a920a`.
  Candidate module path was asserted before running the external test file.
- Earlier retained Mac lane at `159fd65` has identical production paths to
  fca07fe/37d8f6f and records ordinary passing scientific acceptance. It is
  baseline evidence, not Mac qualification of the new 4f6c580 correction.
- Owner 1 acknowledged the exact candidate and is executing it on Mac. Shared
  coordination/results: PR #19 conversation. Final candidate Mac result pending;
  draft #21 stays held until it is reported. No new numerical or cleanup rebuild.
- Next: preserve any newer Claude tests/findings, resolve concrete matrix failures,
  and update this record with the actual Mac SHA/runtime/results. Backend checks
  alone do not establish whole-release readiness. No automatic merge authorized here.
