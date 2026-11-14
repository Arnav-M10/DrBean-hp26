# Backend milestone progress

Completed: browser baseline, pushed and merged in PR #6 (`1f75bdc`).
Completed: separately approved next-measurement design from the actual baseline
pair, with browser review and independently replayable native design evidence.
Current task: GitHub integration handoff; feature implementation is complete.

Branch: `backend/browser-design`; integrated `main` at `a8dd4ed` (PR #7).
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

- 326 backend tests passed, including actual HTTP design, separate installed
  `-I` CLI replay, adversarial binding and late cancellation/expiry controls.
- 29 browser unit tests passed after integrating the latest web/release changes.
- Actual Chromium completed baseline, positive design and no-separation design,
  separate approvals, native/anchor downloads, offline replay and history checks.
- Ruff (`apps tests scripts`), schema compatibility and deterministic export pass.
- Commands: `BEAN_COUNTERDEX_PYTHON=/path/to/prepared/python BEAN_COUNTERDEX_REPLAY_PYTHON=/path/to/prepared/python .venv/bin/python -m pytest -q`;
  `node --test apps/web/*.test.mjs`; `PLAYWRIGHT_MODULE=/path/to/playwright/index.js CHROMIUM_PATH=/usr/bin/chromium BEAN_COUNTERDEX_PYTHON=/path/to/prepared/python node apps/web/check-backend.mjs`.

## Remaining / next

- No blocker remains for this design feature. Native design currently admits a
  request for checked pair separation; returned outcomes remain evidence-based.
- Next owned feature: a separately reviewed follow-up that checks the original
  selected pair. The engine currently admits one appended hypothetical reading.
  Actual-observation native review needs Owner 1 to extend that admission/mapping.
- Follow-up UI, live AI, independent evaluator expansion and hosted deployment
  were not added here. Actual Mac qualification remains not run.
