# Preferred research workspace handoff

PR55 is merged at `a8765430c46989189b82c298c9c017dbf76dc27f`.
PR61 owns the preferred browser journey; PR60 owns backend recovery/reports.
The qualified manual UI at `/` and the numerical service implementation are unchanged.

## Exact candidates and author results

| Candidate | Exact SHA | Executed result |
| --- | --- | --- |
| Main + frontend | `c78a0094f75133e2f2a52c1c4ebbb2a4db340793` | 11 preferred-browser checks passed, including CSV corrections, real worker, independent native replay, separate design approval, different evidence-dependent next step, refresh, stale approval and expired identity. |
| Combined frontend + backend PR60 | `fcb97cf4d55a8f205122329be07ab3f58da048f0` | 12 preferred-browser checks passed, additionally requiring the new backend projection and persisted evidence-bound commentary to render. |
| Same combined candidate | `fcb97cf4d55a8f205122329be07ab3f58da048f0` | 14 preserved numerical-browser checks and 129 combined web/preview unit tests passed; Ruff/whitespace checks passed; standalone static browser passed with zero API requests. |

The combined branch is **`codex/preferred-combined-qualification`**. It contains
frontend `c78a009` and backend **`a2f568b91f493e796496d02a0e700741baf9206a`**;
the backend application implementation is `114aae410062d6abe05fb96db9bfb846ae0de8bd`
(the later backend commit changes its progress document only). No evaluator code
is merged into this candidate. Subsequent frontend commits retain evidence/docs only.
These are author checks, not Claude's independent acceptance or release approval.

The normal lane starts the actual launcher, trusted private-session proxy, API,
Deep Agents controlled factory and scientific worker on dynamic ports/temp stores.
It imports an actual browser CSV, explicitly reviews its synthetic origin, changes
`4.80` to `4.81`, and verifies science received exact `481/100` while retained source
notes still contain `4.80`. No child exists before canonical scientific approval.
The baseline returns a real checked counterexample; optional pair design requires
another review. A wider closed claim `[0.015,0.35]` yields no discovered alternative
and clarification instead of a fabricated pair-design proposal.

**Separate diagnostic:** the post-science model-failure lane uses a test-only
controlled-model subclass in `workspace-preview/tests/failure_worker.py`, under a
second isolated actual API/worker deployment. It raises after the evidence tool;
scientific computation, downloads and replay are real. It is not the ordinary
factory's success case, live Gemini behavior, a barrier test or restart qualification.
The failed agent retains its completed child, readable report and native evidence.

Both lanes use ordinary process limits. The guard and browser record zero provider
or external-request attempts. No credentials were read, model called, capacity
granted, ledger reset, automatic unknown mutation retried or scientific test weakened.

## Reproduce and use

```sh
scripts/dev/setup.sh
BEAN_AI_MODE=placeholder BEAN_RESEARCH_MODE=controlled scripts/dev/start.sh
```

Open **http://127.0.0.1:4173/workspace-preview/**, or the launcher's printed web
origin plus `/workspace-preview/`.

1. Import CSV (`time,concentration,epsilon`) or type supported concentration readings;
   review origin, hours, mg/L, time zero and hard allowances.
2. Review the research question, parameter/claim bounds and assumptions. Accept
   inputs and start; the real agent writes its maintained plan.
3. Review and approve the displayed canonical scientific scope. The real worker
   computes, read-only polling retrieves evidence, and Results opens automatically.
4. Read the finding, conditional meaning, uncertainty and next recommendation.
   Download HTML, server JSON, native packet and anchors. Exact records are secondary.
5. Request optional next-measurement planning; approve its distinct design scope.
   Unsupported/unresolved steps stay unavailable or ask for reviewed clarification.

The optional concentration example fills only input values. The preserved plasma
workflow is **`/workspace-preview/comparison.html`**, with its original real
numerical transport, reports and synthetic-only constraints. It is never labelled
an exact Counterdex certificate. Detailed researcher steps: [workspace README](../../../workspace-preview/README.md).

```sh
node --test apps/web/*.test.mjs workspace-preview/tests/*.test.mjs
PLAYWRIGHT_MODULE=/absolute/path/to/pinned/playwright \
  CHROMIUM_PATH=/path/to/chromium node workspace-preview/check-research.mjs
PLAYWRIGHT_MODULE=/absolute/path/to/pinned/playwright \
  CHROMIUM_PATH=/path/to/chromium node workspace-preview/check-connected.mjs
PLAYWRIGHT_MODULE=/absolute/path/to/pinned/playwright \
  CHROMIUM_PATH=/path/to/chromium node workspace-preview/check-static-research.mjs
```

The checked environment used launcher-installed locked backend CPython 3.12 and
scientific CPython 3.11 on Linux, Node 24 and managed Chromium. CI independently
runs the supported job runtimes; this local run is not a macOS qualification.
A generic `python3 -m http.server 4190 --bind 127.0.0.1 --directory workspace-preview`
serves visibly static drafts at `http://127.0.0.1:4190/`; it cannot execute agents.

## Evidence and remaining gates

Receipts are [combined research](combined-research-receipt.json),
[frontend-only research](frontend-research-receipt.json) and
[preserved numerical](combined-numerical-receipt.json). The numerical receipt
accurately records the managed browser's blocked `file:` navigation: the exact saved
HTML was instead rendered with networking offline. This is not a file-navigation pass.
[Readable successful report](investigation.html), [failed-agent report](model-failure-retained.html),
and screenshots are retained alongside the actual native packet/anchors.
[Artifact hashes](artifact-digests.json) identify the files. Native evidence can be
replayed under installed CPython 3.11 with
`python -m counterdex replay-native PACKET --anchors ANCHORS`.
Check integrity, binding and replay separately from the scientific outcome.

Frontend delivery is complete for this scope. Required CI and Claude's independent
combined qualification remain integration gates. Claude owns all live calls.
His `F-LIVE-COMMENTARY-NUMBER` on backend `a2f568b` remains open: science completed,
but live narration failed `explanation_unsupported_number`; the fallback evidence
is intact. This UI labels stopped narration separately from scientific outcomes.
No narration validator or authority rule was relaxed to hide that finding.
Live operation also requires explicit disclosure consent and actual operator-approved
allocation; ordinary launcher readiness is not a grant or successful live call.
No browser allocation/refill control was added.

Observation ingestion, broader arbitrary-file/model registration, new scientific
families, broad restart qualification and a redesign are outside this frontend PR.
Keep PR60 and PR61 separately reviewable; qualify the exact combined candidate.
Do not describe this as a fully qualified live release.
