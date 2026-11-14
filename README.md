# Dr. Bean

Dr. Bean is a research evidence assistant. Its goal is one decision loop: review measurements, find a compatible counterexample to a claimed parameter range, choose a next measurement that tells two candidate explanations apart, check which survives a new reading, and replay the exact evidence. The scientific engine is **Counterdex** (`packages/groundwork_adapter/counterdex`).

This README states what the repository does at the tested commit. Status by gate is in [docs/INTEGRATION_STATUS.md](docs/INTEGRATION_STATUS.md).

## Current state in one paragraph

The API, worker and web workspace start with one command and survive a restart. An approved baseline runs the real engine and returns scoped results with native evidence that replays in a separate process. The browser supports reviewed exact inputs, frozen plans, separate approvals, actual baseline and next-measurement design, history and native downloads. Backend follow-up checks retain the original pair and a separately reviewed reading. The browser also supports retained-source inspection, proposal correction/materialization and hypothetical follow-up revisions. Strict clean-checkout release qualification is tracked separately. The independent HTTP suite is delivered; qualification depends on its retained results for the current commit. Counterdex also works offline on CPython 3.11. **Gemini is disabled by default. An explicit private local opt-in enables bounded image proposals and selected-run commentary, each with separate consent. Live autonomous Deep Agents coordination is not integrated.**

## Run it

Requirements: [uv](https://docs.astral.sh/uv/) and Node 20 or newer. uv installs the Python runtimes: the backend on Python 3.12/3.13 from `uv.lock`, the engine on CPython 3.11 (its only qualified runtime). Do not use whichever `python3` is on your PATH for product code.

```sh
scripts/dev/setup.sh
```

Installs both runtimes, creates the private local auth file if absent, and prints the doctor report. It never deletes data in `var/`.

```sh
scripts/dev/start.sh --controlled-source-examples
```

Starts the API (`127.0.0.1:8000`), the durable worker and the web workspace (`127.0.0.1:4173`) on one SQLite store under `var/`, waits until they answer, and prints service facts. Loopback only. This option enables the packaged synthetic source examples. Without the separate live opt-in below, Gemini remains disabled; omit the option for manual-only source intake.

```sh
scripts/dev/stop.sh
```

Stops only the processes the launcher started. Data is kept.

```sh
scripts/dev/doctor.py
```

Reports, as separate facts: API ready, worker ready, scientific adapter available and qualified, native replay supported, and Gemini opt-in/server dispatch state. Configuration and readiness do not establish live qualification.

Open the web address printed by the launcher. It connects automatically to a private browser workspace; researchers do not enter an access token or provider key. Reloads and additional tabs reuse the session cookie. Saved work stays on the server; unsaved drafts stay in the current tab. Operator API documentation remains at `http://127.0.0.1:8000/docs`.

If a start fails, the launcher prints the log tail and stops what it started. Port already in use: it refuses and kills nothing. After an unclean stop, run `python3 scripts/dev/launcher.py recover` before the next start. Details: [docs/release-runbook.md](docs/release-runbook.md).

## Optional live Gemini

One backend uses one server-side Gemini key for all authorized users and workspaces. Teammates connecting to that backend do not provide their own Gemini keys. The server owner configures it once; cloning the repository does not copy the private key. The launcher discards shell provider credentials. After setup on the server, create an owner-only configuration from the disabled example:

```sh
cp scripts/dev/gemini.local.example.json var/gemini.local.json
chmod 600 var/gemini.local.json
```

Edit that private file on the server: enter the owner's `GEMINI_API_KEY`, set `mode` to `live`, set `BEAN_GEMINI_ACCOUNT_GATE` to `approved`, and record the owner's decision in `BEAN_GEMINI_ACCOUNT_DECISION_ID` using 1–128 letters, digits, dots, underscores, colons or hyphens, starting with a letter or digit. Keep `BEAN_GEMINI_FREE_TIER_ONLY` at `1`. The model is explicitly selected as `gemini-3.5-flash-lite`; `gemini-2.5-flash-lite` is also supported. No model fallback is performed. Restart the launcher after changing the file. Setting `mode` to `disabled` and restarting disables dispatch again.

This free-tier flag records your assertion about the Google project. The application does not verify its billing state or establish a dollar-denominated spending guarantee. Use a project without billing enabled when zero spend is required. API keys, bearer tokens, local stores and live-test records under `var/` are excluded from Git.

After connecting and selecting a workspace, upload one public or synthetic PNG/JPEG, review the image disclosure, and choose **Ask Gemini to read this image**. Live images are limited to 1600 × 1600 pixels and 5 MiB. Review each proposed value and complete missing assumptions before scientific approval. With a completed run open, **Ask Gemini about this investigation** sends the question and selected research context after separate consent. The app shows server-owned scientific statements separately from model commentary and withholds commentary that fails grounding checks.

**Show Gemini call budget** reads the local ledger without calling a model. The live ledger permits at most eight requests with total conservative reservations of 64,000 input and 16,000 output tokens. These limits apply across the local store, not separately to each workspace or to Google's quota. Failed/uncertain requests retain reservations, and the app makes no automatic retry. Manual discovery, measurement design, follow-up checking and native replay make no model calls. PDF intake and live autonomous coordination remain unavailable. A local smoke test does not satisfy the formal live release gate.

## One shared server for teammates

Run the app and configure Gemini once on the owner's Mac. Install Cloudflare's `cloudflared` tool (`brew install cloudflared` on macOS), then run:

```sh
python3 scripts/dev/share.py start
python3 scripts/dev/share.py status
```

The printed HTTPS link opens the running application. Each browser connects automatically to its own private workspace. Sharing the URL does not share another visitor’s research. Teammates do not enter an access token or provider key, or start a backend. All workspaces share the existing conservative provider budget, including earlier tests; connecting never resets or increases it.

The API, web server and sharing gateway remain bound to loopback. The gateway admits the exact current HTTPS tunnel origin, strips visitor-supplied owner credentials, and forwards only the private session cookie. It never reads or sends the Gemini key. This is a temporary development preview: keep the Mac on and connected; the URL changes on a new sharing session. Status/health checks make no model calls. Stop the public link separately with:

```sh
python3 scripts/dev/share.py stop
```

Cloudflare Quick Tunnel behavior and limitations are documented at <https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/>. Detailed setup and verification are in [Shared server](docs/shared-server.md).

## What works, and how it is checked

| Area | State | Check |
|---|---|---|
| One-command launch, restart, reopen evidence, credential and origin refusal | works | `python3 scripts/release/stack_smoke.py` (31 checks, isolated store) |
| Manual HTTP path: dataset, problem, plan, approval, one run, report | works with real Counterdex discovery | `stack_smoke.py --require-science`; backend and HTTP tests |
| Browser to API: plan, approval, run retrieval, downloads | works | `node apps/web/check-backend.mjs` |
| Web editor: exact entry, validation, export | works | `node --test` in `apps/web`; `tests/integration/web_manual_smoke.mjs` |
| Counterdex engine standalone: candidate discovery, exact check, fixed-pair design, native replay | works on CPython 3.11 | 257 engine tests; replay of the prepared synthetic bundle |
| Source intake and review | controlled examples plus explicitly opted-in live image proposals | backend tests; `tests/test_live_provider_opt_in.py`; web source tests |
| deepagents graph | backend-tested with **controlled placeholder** models only; live coordinator unavailable | backend tests |
| Baseline discovery through the API and browser | works with the prepared engine interpreter | `stack_smoke.py --require-science`; `node apps/web/check-backend.mjs` |
| Design, native export and replay through the API (gate G2) | real discovered pair, separate approval, native replay | backend tests |
| Browser controls for source review, design and follow-up | implemented; controlled source proposal, real science and hypothetical follow-up | `node apps/web/check-backend.mjs` |
| Live Gemini | explicit opt-in for image proposals and selected-run commentary; disabled by default; formal live qualification not run | substituted SDK transport tests and browser control tests; live qualification is separate |

```sh
python3 scripts/release/checklist.py
```

Runs every suite above and prints checks, gates and boundaries for the current commit. Exit 0 here is a status report, not a release.

```sh
python3 scripts/release/checklist.py --strict-offline
```

Exits nonzero unless every offline gate has passing evidence. It currently fails, correctly.

```sh
scripts/release/clean_checkout.sh
```

Repeats the checks in a clean clone with freshly installed runtimes.

## What a result would and would not mean

A checked candidate outside a claimed interval shows that the reviewed measurements and model do not force the parameter into that interval. It does not identify the true parameter, validate the model or support a clinical decision. A suggested measurement time concerns only the two named candidates, the reviewed feasible times and the stated future hard allowance. A later reading can exclude either candidate or both; it never proves the interval. Replay is a fresh run of the same checker, not an independent proof system. The person reviews assumptions and authorizes work; the checker decides mathematical validity; AI output, placeholder or live, can do neither.

## Scope

One model, `C(t) = A*(exp(-ke*t) - exp(-ka*t))`, hours and mg/L. One PNG or JPEG source. Local SQLite with optional temporary HTTPS sharing from the owner's Mac. No PDF intake, managed production deployment, second database, blockchain, messaging or extra model provider. All data in this repository is synthetic.

## Documents

- [Integration status by gate](docs/INTEGRATION_STATUS.md), [cross-owner issue ledger](docs/issue-ledger.md) and [workstream logs](docs/workstreams/)
- [Release runbook](docs/release-runbook.md) and [operational handoff](docs/handoff-owner04.md)
- [Ownership and layout](docs/ownership-and-layout.md)
- [Two-minute demo script](docs/demo/demo-script.md) and [submission draft](docs/submission-draft.md)
- [Consultation and observed-task protocol](docs/human-task/task-protocol.md)
- [Provenance and eligibility](docs/provenance-and-eligibility.md)
- Backend: [handoff](docs/HANDOFF.md), [validation](docs/VALIDATION.md), [shared contracts](shared/contracts/README.md)
- Engine: [integration](packages/groundwork_adapter/docs/INTEGRATION.md), [README](packages/groundwork_adapter/README.md)
- Evaluation: [protocol](docs/evaluation-protocol.md), [harness](evaluation/README.md)
- Web: [workspace notes](apps/web/README.md)
