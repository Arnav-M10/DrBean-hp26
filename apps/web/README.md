# Dr. Bean researcher workspace

The dependency-free browser supports reviewed CSV/manual measurements, exact rational inputs, an immutable baseline plan, explicit approval, real Counterdex investigation, result reopening, and authenticated native evidence/replay-anchor downloads. The backend owns identities, approvals, scope and scientific execution. Gemini remains disabled; this manual path makes no model-provider calls.

## Local startup

Prepare the backend and CPython 3.11 Counterdex runtime using the backend handoff. Start the API and durable worker with the same database, artifact storage and `BEAN_COUNTERDEX_PYTHON`. Then run:

```sh
node apps/web/serve.mjs
```

Open `http://127.0.0.1:4173`. The proxy targets `127.0.0.1:8000` by default. A trusted local launch can set `BEAN_WEB_API_PORT` to a different loopback API port; browser requests cannot select another destination. The proxy rejects foreign hosts/origins and forwards neither cookies nor browser origin headers. This remains a local serving lane, not hosted authentication.

Open **Local backend connection**, enter an authorized researcher bearer token, and choose or create a workspace. Credentials stay in memory and are cleared from the password field after connecting. They never enter URLs, downloads, cookies or browser storage. Reloading requires reconnecting.

## Baseline workflow

1. Enter measurements or import CSV columns `time,concentration,epsilon`. Review elapsed hours, concentrations in mg/L, positive hard allowances and included rows. CSV original spellings and source metadata are retained; original CSV file bytes remain with you.
2. Enter experiment identity, the meaning of t=0, dataset origin, parameter domain and closed `ke` claim. Explain the hard allowances. Counterdex requires 3–128 rows, three distinct included times, strict positive parameter intervals and `upper(ke) < lower(ka)`.
3. Review the draft and choose **Save inputs and prepare plan**. The immutable `counterdex.v1` plan freezes the question, success criterion, exact inputs and bounded provider-free baseline scope. An optional research goal becomes the question; otherwise the question is derived from the reviewed exact claim.
4. Review the displayed objective and exact frozen records, check the approval box, then choose **Approve reviewed plan**. Saving inputs never runs science. Editing a draft requires a new plan and approval.
5. Choose **Queue approved manual run**. The browser requires actual baseline availability; it does not use a global qualification badge. The worker searches and checks the submitted input. Pending runs update through read-only polling.
6. Inspect execution state, scientific outcome, verification, expected binding and replay separately. Exact candidate vectors remain visible. A bounded search without a counterexample does not prove the claim.
7. Download **native scientific evidence** and **replay anchors**. Native bytes are checked against both their response digest and the selected evidence reference. The application evidence-record and report downloads are separately labeled.

The explicitly synthetic example uses measurements `4.80, 7.20, 8.00, 6.80, 5.70` at `0.25, 0.5, 1, 2, 4` hours, with team-selected hard allowances `0.50 mg/L`. A corresponding reviewed example domain is `A=[0.001,30]`, `ke=[0.015,0.35]`, `ka=[0.4,8]`, with closed claim `ke=[0.10,0.17]`. These are input controls; candidate vectors and results are computed by the actual engine.

With the matching prepared Counterdex package in CPython 3.11, replay the two downloaded files outside the browser:

```sh
python3.11 -m counterdex replay-native dr-bean-ARTIFACT.native.json --anchors dr-bean-ARTIFACT.anchors.json
```

The anchors provide separately retained expected application/run identities. A matching hash establishes byte integrity, not mathematical validity. Native replay recomputes the supported predicates using the matching engine source. This is fresh checking by the same mathematical implementation, not an independently implemented checker. Browser replay remains unavailable.

Keep a run identifier to reopen authenticated history after reconnecting. A report freezes the selected run and its evidence inventory. Drafts remain tab-local; **Download draft** preserves them before closing the tab. Next-measurement, follow-up and public-sharing controls are outside this baseline milestone.

## Verification

```sh
node --test apps/web/*.test.mjs
PLAYWRIGHT_MODULE=/absolute/path/to/playwright/index.mjs \
BEAN_COUNTERDEX_PYTHON=/absolute/path/to/prepared/python3.11 \
node apps/web/check-backend.mjs
```

`check-backend.mjs` starts an isolated API, worker and proxy on unused loopback ports, drives Chromium through review/approval/queue, submits two distinct datasets to actual discovery, downloads native bytes and anchors, and runs replay in another interpreter process. It also checks preserved earlier evidence, zero provider attempts, stale draft approval, reports, narrow-screen layout, memory-only credentials and proxy origin rejection. It creates no candidate records or synthetic scientific responses. Temporary test data and processes are cleaned up.

Set `BEAN_TEST_PYTHON` or `CHROMIUM_PATH` to override `.venv/bin/python` and `/usr/bin/chromium`. Playwright is a test-only dependency and is not shipped with the browser application. A missing runtime or failed scientific run fails this milestone check instead of being counted as a successful demonstration.
