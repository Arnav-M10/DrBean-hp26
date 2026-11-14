# Getting started

## Install and start

Install [uv](https://docs.astral.sh/uv/) and Node.js 20 or newer, then run:

```bash
git clone https://github.com/Arnav-M10/DrBean-hp26.git
cd DrBean-hp26
scripts/dev/setup.sh
scripts/dev/start.sh
```

Setup installs locked backend dependencies, creates a CPython 3.11 environment for Counterdex, and initializes private local access if needed. It preserves existing `var/` data. The launcher starts the API, supervised worker, and web server against one local store.

Open `/study/#data` on the web origin printed by the launcher. The default is **http://127.0.0.1:4173/study/#data**. A deployment using port `28170`, for example, uses **http://127.0.0.1:28170/study/#data**. These are ports for the same interface, not separate applications.

The browser establishes private workspace access automatically. Reloads reuse the session cookie. No researcher-facing bearer-token or provider-key field is required. Existing history remains subject to that browser identity; cross-device identity recovery is not implemented.

| Entry point | Purpose |
| --- | --- |
| `/study/#data` | Main interface for files, questions, approvals, answers, and next steps. |
| `/workspace-preview/` | Connected time–concentration research interface. |
| `/workspace-preview/comparison.html` | Connected synthetic plasma-comparison interface. |
| `/` | Existing general/manual research workspace. |
| API origin `/docs` | Operator API reference; the default API port is 8000. |

The connected views require the ordinary application server. Serving `workspace-preview` with `python -m http.server` provides only its labelled static/draft mode.

## First study

1. Write a question and upload supported files, paste a table, or choose a built-in example.
2. Review the available analysis path. File interpretation, exact model checks, and numerical comparison are distinct operations.
3. Inspect the proposed inputs, assumptions, and scope. Approve the specific operation when requested.
4. Read the answer and its limitations. Download the report and supporting records.
5. Choose a follow-up action. A new scientific scope or measurement design requires its own review.

The two built-in examples exercise the two-rate concentration model and synthetic electron-current comparison. They provide input observations; they do not substitute saved candidates for new scientific computation. Input formats and effective upload limits are shown by the interface and server capabilities. Save spreadsheets as CSV; Excel workbooks are not supported.

## Configure Gemini

A fresh checkout makes no Gemini calls. The default controlled coordinator uses an offline policy through the real Deep Agents graph and scientific worker. General file interpretation requires configured Gemini, or the explicitly labelled development responder described below.

The server operator prepares the local configuration after setup:

```bash
cp scripts/dev/gemini.local.example.json var/gemini.local.json
chmod 600 var/gemini.local.json
```

Edit `var/gemini.local.json` locally:

| Field | Setting |
| --- | --- |
| `mode` | `live` to enable the explicit opt-in; `disabled` to turn it off. |
| `GEMINI_API_KEY` | The operator's server-side Gemini key. |
| `GEMINI_MODEL` | One of the model identifiers accepted by the current launcher; see the example file and `LIVE_MODELS` in `scripts/dev/launcher.py`. |
| `BEAN_GEMINI_ACCOUNT_GATE` | `approved`, after the operator has reviewed the Google project. |
| `BEAN_GEMINI_ACCOUNT_DECISION_ID` | A local decision identifier: 1–128 letters, digits, dots, underscores, colons, or hyphens; start with a letter or digit. |
| `BEAN_GEMINI_FREE_TIER_ONLY` | Keep `1` for the supported free-tier-only configuration. |

Do not commit this file. The launcher discards inherited shell provider credentials and passes the admitted configuration only to the API and worker. One backend key serves the authorized workspaces on that server; it is not copied to teammates or the browser.

Restart services after changing the file:

```bash
scripts/dev/stop.sh
scripts/dev/start.sh
scripts/dev/doctor.py
```

Uploading a file alone does not send it to a provider. General analysis first shows what will be sent and requires consent. Retained results can be reopened without another model call.

### Live research coordination

File analysis and autonomous research coordination are separate capabilities. The research runner defaults to `controlled`. With a valid live configuration, select live coordination when starting the server:

```bash
BEAN_RESEARCH_MODE=live scripts/dev/start.sh
```

A live research session additionally needs consent bound to its context and an operator allocation. Consent does not create or refill an allocation. The UI and capabilities endpoint expose readiness and remaining capacity; configuration alone is not evidence that live qualification has passed. See the [research-session integration contract](integration/DEEPAGENTS_COMPLETION_UI.md) for the operator-facing boundaries.

The shared request ledger reserves capacity before dispatch. Failed or uncertain requests retain their reservations; requests are not automatically retried or moved to another model. The free-tier flag records the operator's declaration and does not query Google's billing state. If zero spend is required, use a Google project without billing enabled and confirm current model eligibility in that account.

### Provider-free file-analysis development

When the server is not in live mode, the general research service supports a labelled local responder:

```bash
BEAN_GENERAL_ANALYSIS_MODE=controlled_demo scripts/dev/start.sh
```

This tests the file-analysis interface and record flow. It is not Gemini output and does not establish live interpretation quality. It is separate from the controlled research coordinator that drives real Counterdex operations.

## Share a development server

Configure and start the application once on the host machine. With `cloudflared` installed:

```bash
python3 scripts/dev/share.py start
python3 scripts/dev/share.py status
```

Share the printed HTTPS origin with `/study/#data` appended. Each browser gets its own private workspace. Visitors share the host's existing provider budget; connecting does not reset it. The Gemini key remains on the host.

Keep the host awake and connected. The temporary URL changes when a new tunnel is created. Stop the public link independently with:

```bash
python3 scripts/dev/share.py stop
```

See [Shared server](shared-server.md) for the gateway and origin rules.

## Service operations

```bash
scripts/dev/doctor.py
python3 scripts/dev/launcher.py status
scripts/dev/stop.sh
```

The launcher stops only its managed processes and retains saved work. It refuses an occupied port without killing another application. After an unclean stop, inspect the reported state and use:

```bash
python3 scripts/dev/launcher.py recover
```

Scientific job recovery and research-session reconciliation preserve reviewed identities and request accounting. Uncertain provider outcomes are not silently replayed. The [release runbook](release-runbook.md) contains additional operational checks; its retained release reports apply to their named commits.

## Development checks

After setup, select the prepared scientific runtime for backend tests:

```bash
export BEAN_COUNTERDEX_PYTHON="$PWD/.venv-engine/bin/python"
export BEAN_COUNTERDEX_REPLAY_PYTHON="$PWD/.venv-engine/bin/python"
export PATH="$PWD/.venv-engine/bin:$PATH"
export PYTHONPATH="$PWD/packages/counterdex_models"

uv run pytest -q tests --ignore=tests/integration
uv run ruff check apps tests scripts
.venv-engine/bin/python -m unittest discover -s packages/groundwork_adapter/tests
.venv-engine/bin/python -m unittest discover -s packages/counterdex_models/tests
node --test apps/web/*.test.mjs
node --test workspace-preview/tests/*.test.mjs
```

Browser checks use the pinned Playwright dependency in `tests/integration`:

```bash
cd tests/integration
npm ci --ignore-scripts --no-audit --no-fund
node node_modules/playwright/cli.js install chromium
cd ../..

PLAYWRIGHT_MODULE="$PWD/tests/integration/node_modules/playwright" \
  node workspace-preview/check-research.mjs
```

That browser check exercises the connected concentration workspace with isolated stores and controlled models. The full set of checks is defined in [CI](../.github/workflows/ci.yml). Live provider acceptance is recorded separately from offline checks and historical replay.
