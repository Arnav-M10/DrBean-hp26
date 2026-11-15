# Classic research sprint

Frontend owner only. Base main d7abf3b; branch codex/classic-research-sprint.
Codex 3 owns integration/merge/public routing. Claude alone owns live Gemini tests.

Initial audit (before minute 15): the unchanged classic interface works through
its ordinary launcher at http://127.0.0.1:4173/#investigations. Eight baseline
browser checks pass: reviewed CSV correction, private cookie session, actual
maintained plan/interrupt, separate scientific/design approval, real Counterdex
children, native downloads and fresh CPython 3.11 replay. Zero provider attempts.

Focused candidate: consume existing token/quota/accounting/recovery projections
before enabling live continuation; show plain-language provider stops with codes
in technical details; distinguish stopped assistant from scientific outcome.
No new consent, model, routing, deployment or modern study change.

Completed: candidate application 158daa2a94b01c92803acf135e6055cf53fcaa74
passes 119 web units and 10 browser checks. Reload restores the same
session/children with zero mutations. A separately labelled parent-read-response
presentation diagnostic keeps actual evidence/downloads accessible after simulated
narration failure; it is not backend failure, restart or live qualification.

Launch: scripts/dev/setup.sh, then
BEAN_AI_MODE=placeholder BEAN_RESEARCH_MODE=controlled scripts/dev/start.sh
Open http://127.0.0.1:4173/ (ordinary local application, not the Vercel landing).
Research view: /#investigations; results: /#result; design/report: /#next.

Codex 3 asset handoff: serve apps/web/index.html at the classic application's
entry, retaining relative styles.css, app.mjs and motion.mjs plus existing modules:
exact.mjs, question.mjs, api.mjs, session.mjs, general-workspace.mjs, research.mjs,
manual.mjs, source-workflow.mjs, assistant-workflow.mjs, workflow.mjs, design.mjs,
followup-workflow.mjs, design-workflow.mjs, result-view.mjs. Keep the existing
same-origin /api/bean/v1 private-session proxy, security headers and cookie
boundary. Optional example /examples/controlled-source.png is not required for
CSV/manual research. Do not copy credentials or expose the private backend directly.
The production domain's landing root is not this classic application. No public
route or asset deployment is changed by this branch; preserve hosted /study/.

90-second demonstration (science runtime may require extra waiting):
0–20s: import time,concentration,epsilon CSV, review units/origin, correct one value.
20–35s: enter the concentration claim/bounds and question; save reviewed inputs.
35–50s: open Investigate, accept input review and save question; advance the real
plan. Show public plan/tool events and that no scientific child exists yet.
50–65s: review the exact scientific scope and approve. Wait for actual completion;
show the result and its assumptions, then download native evidence/anchors.
65–80s: refresh and reopen the same retained session; no mutation or repeat run.
80–90s: request next-measurement planning; demonstrate its separate approval.
Live demonstration only by Claude: explicit provider disclosure/consent, actual
operator allocation, then scientific approval. Controlled success is not live proof.


Delivery: PR70, owned changes only research.mjs, research.test.mjs,
check-research.mjs and this handoff/evidence. No serve.mjs, share-gateway.mjs,
modern study or deployment changes. Commit identity verified as the requested eesh-verma account. No Gemini calls, keys inspected, capacity grants or service
restarts outside temporary test stores/dynamic ports. Baseline before changes:
8 browser checks passed. Candidate: 119 units, 10 browser checks, whitespace clean.
Linux locked backend CPython 3.12.14, scientific CPython 3.11.18, Node 24/Chromium.

Checks:
node --test apps/web/*.test.mjs
PLAYWRIGHT_MODULE=/absolute/path/to/pinned/playwright CHROMIUM_PATH=/path/to/chromium node apps/web/check-research.mjs

Retained receipt and labelled presentation screenshot:
../frontend/classic-sprint/. The existing runner downloads/replays both actual
native packets under ignored var/test-evidence/research-browser/.

Current task: frontend delivery complete; support Codex 3 integration only.
Remaining gates: CI, Codex 3 merge/routing choice and Claude's independent/live
qualification. This branch does not advertise live or restart qualification.
