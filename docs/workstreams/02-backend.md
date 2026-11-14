# Browser baseline milestone

Current task: PR review handoff. Implementation, real-browser acceptance and
final regression checks are complete.

Base: `main` at `adac945` (PR #4), branch `backend/browser-baseline`.
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

## Handoff

- Review the focused `backend/browser-baseline` branch against `main`.

## Blocked / outside this milestone

- No missing scientific producer dependency is currently identified.
- New measurement design/follow-up UI, controlled AI activation, independent
  evaluator expansion and hosted deployment are outside this focused milestone.
- Actual Mac qualification is not established by Linux checks.

## Evidence

Backend regression: 290 passed, including baseline HTTP/CLI acceptance and
16 adversarial binding checks. Ruff and whitespace checks pass. Engine suite: 257
tests, 2 skipped; installed-runtime supervisor checks separately pass (13 tests),
and application-schema compatibility passes. Browser unit checks: 18 passed;
actual browser milestone passes. Contract export is deterministic (39 schemas).
Synthetic examples supply input values only; production candidate results are
always computed.
