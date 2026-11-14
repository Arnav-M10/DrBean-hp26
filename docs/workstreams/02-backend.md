# Backend milestone progress

Completed: browser baseline, pushed and merged in PR #6 (`1f75bdc`).
Completed: separately approved next-measurement design from the actual baseline
pair, with browser review and independently replayable native design evidence.
Current task: push final design fixes in PR #9; merge is held for release CI.

Branch: `backend/browser-design`; integrated `main` at `9cc90e0` (PRs #7–8).
Verified on Linux, backend Python 3.12.14, scientific CPython 3.11.18.
Interfaces: DB-SC-1 / GF-2, `counterdex.bridge.v1`,
`DB-SC-1-to-groundwork-v1`, `counterdex.application-bundle.v1`.
Model providers remain disabled; no calls or credential checks were performed.

## Works / verified now

- Reviewed measurements → explicit baseline approval → actual bounded discovery.
  No fixture candidates; native downloads and separate replay anchors work.
- Two compatible discovered candidates → reviewed grid, precision, horizon and
  permissions → separate design approval → one durable design job.
- Checked separation, checked no-separation and honest numerical fallback retain
  all approved grid rows. A selected measurement is conditional on this pair.
- Native design packets retain original baseline bytes/anchors unchanged. Fresh
  replay checks supported facts; it never reruns numerical discovery.
- Changed design inputs require new approval. Wrong scope/anchors, corrupt bytes,
  cancelled or expired authority cannot publish a new checked design result.
- Browser history reopening shows the original design scope; changing baselines
  clears the previous design display. Earlier evidence stays available.

## Evidence

- 335 backend tests passed (excluding the independent `tests/integration` suite),
  including actual HTTP design, separate installed
  `-I` CLI replay, adversarial binding and late cancellation/expiry controls.
- Reversed candidate order preserves ID/vector binding. Numerical-only evidence
  publishes and replays its integrity/binding without claiming checked facts.
- 29 browser unit tests passed after integrating the latest web/release changes.
- Actual Chromium completed baseline, positive design and no-separation design,
  separate approvals, native/anchor downloads, offline replay and history checks.
- Ruff (`apps tests scripts`), schema compatibility and deterministic export pass.
- Commands: `BEAN_COUNTERDEX_PYTHON=/path/to/prepared/python BEAN_COUNTERDEX_REPLAY_PYTHON=/path/to/prepared/python .venv/bin/python -m pytest -q tests --ignore=tests/integration`;
  `node --test apps/web/*.test.mjs`; `PLAYWRIGHT_MODULE=/path/to/playwright/index.js CHROMIUM_PATH=/usr/bin/chromium BEAN_COUNTERDEX_PYTHON=/path/to/prepared/python node apps/web/check-backend.mjs`.

## Blocked / next

- Release CI is not green. On the first PR #9 run, backend, engine, browser unit
  and evaluator self-check jobs passed; the stack job failed. Owner 4 must pass
  the prepared CPython 3.11 via `DRBEAN_SCIENCE_PYTHON` to the evaluator step in
  `.github/workflows/ci.yml`; otherwise admission reports `scientific_runtime_missing`.
- With that runtime supplied locally, Owner 5's evaluator still needs support for
  `counterdex.application-bundle.v1`, `replay-native` and the eight retained anchor
  fields in `evaluation/drbean_eval/native.py`. Its hero expectation also requires
  checked extension while `allow_continuation` is false; that input correctly
  produces numerical guidance. Independent tests were not weakened here.
- Owner 2/4 must resolve the CI-only descendant-process boundary failure (the
  ordinary-user check passed all five locally). Owner 5's orphan/teardown probe
  must distinguish exited zombies from live computation. Recovery and follow-up
  failures in the broader evaluator remain separate from this design milestone.
- Native design currently admits requests for checked pair separation; returned
  outcomes remain evidence-based. PR #9 stays open pending the release checks.
- Next owned feature: a separately reviewed follow-up that checks the original
  selected pair. The engine currently admits one appended hypothetical reading.
  Actual-observation native review needs Owner 1 to extend that admission/mapping.
- Follow-up UI, live AI, independent evaluator expansion and hosted deployment
  were not added here. Actual Mac qualification remains not run.
