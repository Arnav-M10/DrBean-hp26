# Product candidate for independent qualification

Code/test candidate: `d55ff949b9ca95aa045f1bd2e5c9e17a5da66945` in PR #27.
Source handoff parent: Owner 2 `42f92b1b07f52f4336cc4449928bc781e30ae0fe`.
Local equivalent: `37150085df20733756714399c9a88ba0257894f8`.
Identical tree: `74c60552cfa778ed283376098fa6aeba844ca721`.
Later evidence/documentation commits do not replace this code identity.

Earlier production candidate 31a8ed3 passed all six CI jobs and strict clean-checkout qualification (5 offline gates, 12 boundaries); see [full report](offline-c4d1ad6-macos.json) and [commit/tree mapping](product-candidate.json). These are Owner 4 observations, not Claude's independent acceptance.

The later runner-only correction d55ff94 observes visible follow-up status after automatic navigation. It fixes a Playwright response-body race; no product implementation or evaluator assertion changed. Final execution results for this exact revision are recorded in the PR #27 conversation, separately from the archived earlier report.

## Prepare the exact candidate

Use a separate checkout, preserve any existing store, and run from its root:

```sh
git checkout d55ff949b9ca95aa045f1bd2e5c9e17a5da66945
scripts/dev/setup.sh
npm ci --prefix tests/integration --ignore-scripts --no-audit --no-fund
node tests/integration/node_modules/playwright/cli.js install chromium
```

Linux may require Playwright's `install --with-deps chromium`. The shipped web application has no Playwright dependency.

## Execute product and operational checks

```sh
export NODE_PATH="$PWD/tests/integration/node_modules"
export BEAN_COUNTERDEX_PYTHON="$PWD/.venv-engine/bin/python"
node apps/web/check-backend.mjs
BEAN_TEST_FOLLOWUP_ORIGIN=actual node apps/web/check-backend.mjs
python3 -m unittest scripts/dev/test_launcher.py
python3 scripts/release/stack_smoke.py --require-science
DRBEAN_RELEASE_EVIDENCE_DIR="$PWD/../claude-product-evidence" \
  scripts/release/clean_checkout.sh --strict-offline
```

The browser checks create isolated state. They exercise the normal controlled source API, source correction, explicit reviewed-row transfer, stale-preview refusal, changed-byte manual fallback, real discovery on original/changed inputs, separate design approvals, positive/no-separation results, both follow-up origins, direct result navigation, native downloads and installed-engine replay. Actual-origin tests use synthetic data and preserve that ancestry; no real acquisition is claimed.

The stack check starts/stops/restarts an isolated store using the explicit packaged-source option and checks saved evidence. Launcher tests challenge selected-checkout import and credential-value access during filtering. A missing or failing required check fails the strict gate.

Claude should also apply the latest independently owned source/revision, ledger, wrong-result, cleanup and worker-loss controls unchanged to this candidate. Verify the imported `bean_api` path belongs to this checkout. Do not substitute older green reports or edit expectations to match the implementation. Known independent findings in other workstreams retain their own disposition; this handoff does not close them.

## Ordinary user start

After setup:

```sh
scripts/dev/start.sh --controlled-source-examples
```

Open http://127.0.0.1:4173 and connect using the local credential. Choose a workspace, then Use controlled example image and Prepare controlled source proposal. Review values, copy accepted rows into the draft, complete assumptions, and separately approve the investigation. Follow-up queues directly to results. Stop with `scripts/dev/stop.sh`; saved server evidence remains.

## Limits

Only the packaged, byte-matched synthetic source examples have controlled proposals; arbitrary images use manual entry. Gemini is disabled and unqualified. Declared actual origin is not instrument authentication. The browser displays persisted verification/replay states and verifies download bytes; mathematical replay runs outside the browser. Drafts remain tab-local. Consultation, observed user task and presentation-device rehearsal have not happened.
