# Narrow browser investigation — B integration

PR43, `codex/browser-agent-investigation`, starting at merged PR41/main070b697.
B is the sole application integrator; A owns coordinator/model policy; C owns
independent qualification. Existing manual scientific flow remains supported.

Integrated A's `codex/controlled-research-factory` (0491939) and Cdb7098b.
Current task: focused qualification and required CI, then merge.
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

Executable checks:

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

Actual assembled results before the candidate commit:54 focused backend/model/
metering/native checks passed;81 web tests passed; all7 browser checks passed.
The latter used the actual launcher, corrected the uploaded first concentration
from4.80 to4.81, approved two distinct frozen scientific scopes, computed both
children, downloaded both native packets and replayed each in installed
Counterdex/CPython3.11. Zero provider attempts and zero API/browser egress.
Earlier reports remain immutable. Report profile research-report.v2 includes
all included operation/evidence identities and each native/anchor download path.

## Live gateway boundary

Same graph/authority/worker path uses the existing GeminiChatModel/Gateway and
ResearchLedger. Live mode requires server-only free-tier opt-in, exact browser
consent and an existing explicit operator allocation. Default allocation is zero;
the browser cannot grant capacity. Do not reset the ledger or retry an unknown
provider outcome. No approved shared-server allocation is available to this
checkout; shared Mac service access is not provided here. **Live:not_run**.
No live request or credential probe has been made.

The actual Gemini adapter/gateway is exercised by
`tests/test_research_metered_application.py` with an explicitly controlled SDK
responder, actual consent/session/action/global ledgers and real scientific
children. This is adapter/accounting integration, not live Gemini qualification.
A's tiny baseline uses6 physical reservations and63,802 input-token reservations
within the existing64,000 session ceiling. Different input/context can correctly
exhaust capacity sooner. The complete controlled design path does not establish
that a live baseline plus design fits the existing8-request physical ceiling.

Exact operator action, only after an approved allocation and after checking the
existing shared global budget at the authorized workspace's `provider-budget`
endpoint: on the existing server/store, create the live research session in the
browser, review its provider disclosure and save consent. Set BEAN_RESEARCH_MODE
to live for a future authorized server startup using its existing private
var/gemini.local.json; the browser never receives that key. Then explicitly run
the following allocation against that **existing** database. This example
requests6 calls/64,000 input/3,072 output tokens; it does not increase global caps
or erase earlier attempts. Use the exact approved numbers if they differ.

```sh
BEAN_DATABASE_PATH=/absolute/path/to/existing/bean.sqlite3 \
RESEARCH_SESSION_ID=research_session_REPLACE_WITH_EXISTING_ID \
PYTHONPATH=apps/api .venv/bin/python - <<'PY'
import os
from pathlib import Path
from bean_api.store import Store
from bean_api.workflow import Workflow
from bean_api.research import ResearchService
path = Path(os.environ['BEAN_DATABASE_PATH'])
if not path.is_file():
    raise SystemExit('Refusing to create a new store or replace the shared ledger')
store = Store(path)
sid = os.environ['RESEARCH_SESSION_ID']
with store.read() as conn:
    row = conn.execute('SELECT actor_id,mode FROM research_sessions WHERE id=?', (sid,)).fetchone()
if row is None or row['mode'] != 'live':
    raise SystemExit('An existing live research session is required')
service = ResearchService(Workflow(store), live_enabled=True, allocation_actor=row['actor_id'])
receipt = service.allocate_provider(row['actor_id'], sid, {
    'physical_requests': 6, 'input_tokens': 64000, 'output_tokens': 3072,
    'accepted': True}, 'owner-approved-narrow-demo-allocation-v1')
print('Allocation recorded:', receipt['id'])
PY
```

Refresh the browser and explicitly advance. If existing global capacity is
insufficient, stop: a per-session receipt cannot replenish it. A new store,
identity or ledger reset is not an approved remedy. Do not restart an existing
backend merely to run this example; use the operator's planned startup window.
