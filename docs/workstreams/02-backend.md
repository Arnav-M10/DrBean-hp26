# Backend progress

Current task: user-requested researcher tools, items 1, 2 and 5. All three are
implemented and verified; ready for integration review.
Branch: `backend/researcher-tools`, based on `main` `61edad7`.
Runtime: Linux, backend Python 3.12.14; Counterdex 0.2 / CPython 3.11.18.
Live model dispatch remains disabled. No provider calls or credential probes.

## Completed in this change

1. Reviewer ZIP: frozen report, exact measurement JSON/CSV, immutable approval
   receipts, native artifacts and separate application anchors, checksum/size
   manifest, and standalone replay instructions. Deterministic authenticated
   download capped at 12 MiB/64 files. Missing/corrupt references fail closed.
   Raw source images are excluded; retained metadata/digests remain in the report.
2. Investigation comparison: consistent read snapshot of two owned runs in the
   same workspace; exact row, provenance, allowance, domain, target, plan scope
   and result differences. Original identities and scientific states remain
   visible. Incomplete jobs are explicit. No computation or causal claims.
5. Reusable experiment templates: immutable supported model/units/domain/target
   defaults and explicit allowance/provenance. Save, list, preview and apply in
   browser. No measurements or approvals are copied. Applying keeps existing
   readings/allowances, clears experiment identity/origin and invalidates stale
   plan controls; the default allowance applies to subsequently added manual rows.
   A new experiment still needs input review, a new plan and explicit approval.

## Verification

- Full backend suite: 492 passed in 194.11s, excluding independent integration.
- Focused actual-science tools suite: 4 passed, including exported native replay,
  exact changed-input/outcome comparisons, queued-state display, access isolation,
  durable unapproved templates, corrupt/missing evidence and export size limits.
- Browser unit suite: 31 passed.
- Real Chromium: baseline plus two approved designs exported in one ZIP; all
  three native artifacts replayed in separate installed engine processes.
  Browser comparison and template save/preview/application passed, retaining
  readings and requiring fresh identity/review/approval. Zero provider attempts,
  memory-only credentials and no external browser requests.
- Ruff, whitespace, deterministic export of 40 schemas/five fixture files pass.
  One additive request schema, no database migration. Final focused suite also
  covers added approval receipts and missing/corrupt export failures.
- Commands: `BEAN_COUNTERDEX_PYTHON=/path/to/python3.11 BEAN_COUNTERDEX_REPLAY_PYTHON=/path/to/python3.11 .venv/bin/python -m pytest -q tests --ignore=tests/integration`;
  `node --test apps/web/*.test.mjs`;
  `PLAYWRIGHT_MODULE=/path/to/playwright/index.js CHROMIUM_PATH=/usr/bin/chromium BEAN_COUNTERDEX_PYTHON=/path/to/python3.11 node apps/web/check-backend.mjs`.

## Integration status and limits

- Existing baseline/design/hypothetical follow-up work is reused. Pending
  controlled-accounting PR #13 and restart PR #14 remain separate; this change
  has no dependency on them. No engine, provider, coordinator or evaluator edits.
- Scope explicitly extends minimal browser controls for these three requested
  tools. Contract/API handoff: `shared/contracts/BACKEND_INTEGRATION.md`.
- Templates cover only the currently supported two-rate model/units and list
  the latest 100 per workspace. Core scientific limits and admission still apply.
- Full release qualification remains separate. Proposed engine/recheck adoption
  (PRs #5/#15), release setup and independent evaluator changes need integrated
  acceptance; actual-reading, platform and live-AI qualification are not claimed.
- Next action: review/merge these tools and integrate teammate work using the
  ordinary public routes. Extra timeline/measurement-cost features were not added.
