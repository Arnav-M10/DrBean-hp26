# Narrow browser investigation — B integration

PR43, `codex/browser-agent-investigation`, starting at merged PR41/main070b697.
B is the sole application integrator; A owns coordinator/model policy; C owns
independent qualification. Existing manual scientific flow remains supported.

Current task: integrate A's `codex/controlled-research-factory` (0491939), then
exercise the actual launcher, ordinary API/worker and existing browser controls.
The first failing gate was published at101b7d4: ordinary advance503
`controlled_policy_unavailable`. No injected model or fabricated science.

Supported target: reviewed measurements/question → maintained plan → canonical
review interrupt → human approval → actual Counterdex baseline → evidence read
and accepted report → explicit next planning action → separate checked pair-design
review/approval → computed design and complete evidence/report downloads.

Explicitly deferred: observation ingestion, design amendments, larger PDFs,
general-file expansion and broad restart qualification. Retained checkpoints and
evidence do not constitute qualification of automatic restart continuation.

## Reproduce

Use prepared runtimes (`scripts/dev/setup.sh` on a new checkout). Leave any
existing server untouched. For an isolated store and ports:

```sh
export DRBEAN_VAR_DIR="$PWD/var/browser-agent-rehearsal"
export BEAN_DEV_API_PORT=28130 BEAN_DEV_WEB_PORT=28131
export BEAN_RESEARCH_MODE=controlled
BEAN_AUTH_FILE="$DRBEAN_VAR_DIR/auth.json" .venv/bin/python -m bean_api.bootstrap
scripts/dev/start.sh
# Open http://127.0.0.1:28131 ; local access token stays private/in memory.
```

Browser: connect with that store's local token; create workspace; choose a CSV or
enter measurements; review corrections, meanings, model bounds/claim, hard
allowances and question. In "Maintain a research plan", optionally enter feasible
times/future allowance/horizon and their justification. Acknowledge the exact
inputs; save; advance. Inspect maintained plan and canonical frozen scope; check
the scope box and approve only the investigation. After its report, explicitly
plan the next step, inspect the pair/design request, and separately approve it.
Download report, native packets and external replay anchors. No provider call is
needed in this explicitly controlled-policy lane; the scientific children are real.

Executable gate (currently factory integration in progress):

```sh
BEAN_AI_MODE=placeholder BEAN_COUNTERDEX_PYTHON="$PWD/.venv-engine/bin/python" \
  .venv/bin/python -m pytest -q tests/test_research_browser_milestone.py
NODE_PATH="$PWD/tests/integration/node_modules" CHROMIUM_PATH=/usr/bin/chromium \
  node apps/web/check-research.mjs
```

The browser driver uses its own private temporary store and dynamically selected
ports through the actual launcher, leaves running servers untouched and stops
only its owned processes. Synthetic input-file controls are labelled; candidates,
designs, results and native replay are computed. Receipts go to ignored
`var/test-evidence/research-browser/`. This is B author acceptance, not C signoff.

## Live gateway boundary

Same graph/authority/worker path uses the existing GeminiChatModel/Gateway and
ResearchLedger. Live mode requires server-only free-tier opt-in, exact browser
consent and an existing explicit operator allocation. Default allocation is zero;
the browser cannot grant capacity. Do not reset the ledger or retry an unknown
provider outcome. Exact operator instructions and actual qualification results
will be recorded with the integrated candidate. No live request has been made.
