# Backend milestone progress

Completed: browser baseline milestone, pushed and merged in PR #6 at `1f75bdc`.
Current task: separately approved next-measurement design from the actual
baseline pair, including browser review and replayable native design evidence.

Base: `main` at `1f75bdc` (PR #6), branch `backend/browser-design`.
Backend: Python 3.12.14; scientific child: prepared CPython 3.11.18.
Model providers remain disabled; no model calls or credential checks are authorized.

## Works / reused

- Immutable input/plan/approval records, one-run reservations and scoped access.
- Supervised scientific process boundary, native storage/downloads, source review.
- Owner 1's real bounded discovery and application-bound replay protocol are now
  merged. The earlier missing-producer dependency is resolved.
- Reviewed HTTP inputs now produce real bounded baseline results, retained native
  packets and exact replay-anchor downloads. Separate installed-engine CLI replay
  passes, including changed-input, wrong-binding and no-witness controls.
- Actual Chromium review/approval/queue, polling, native + anchor downloads and
  separate installed-engine replay pass for two distinct reviewed datasets.
  Earlier evidence remains intact; no model-provider attempts occur.
- Resolved scientific child spawn `EAGAIN` beside Chromium: the per-user process
  guard now allows 256 processes/threads while preserving other job limits and
  stricter inherited hard limits.

## In progress

- Native design integration works through ordinary authenticated HTTP: separate
  approval, original baseline bytes/anchors, frozen request and job scope, exact
  grid results and independent nested replay. Positive and no-separation pass.
- Browser design controls and downloads are implemented; actual Chromium
  acceptance and final binding/regression checks are in progress.

## Blocked / outside this milestone

- No missing scientific producer dependency is currently identified.
- Design has no missing producer dependency. Native mapping supports requests
  for checked pair separation; other requested tiers will be rejected explicitly.
- Follow-up observation UI, controlled AI activation, independent evaluator
  expansion and hosted deployment remain outside this focused milestone.
- Actual Mac qualification is not established by Linux checks.

## Evidence

Completed baseline validation: 290 backend tests passed, including HTTP/CLI and
16 adversarial binding checks. Ruff and whitespace checks pass. Engine suite: 257
tests, 2 skipped; installed-runtime supervisor checks separately pass (13 tests),
and application-schema compatibility passes. Browser unit checks: 18 passed;
actual browser milestone passes. Contract export is deterministic (39 schemas).
Synthetic examples supply input values only; production candidate results are
always computed.

Current design checks: 290 existing backend regressions pass; 2 new real HTTP
design/replay tests pass; 38 adapter tests pass (including legacy controls).
Browser unit checks: 24 passed. Final combined counts and browser outcome pending.
