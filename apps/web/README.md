# Dr. Bean researcher workspace

The dependency-free browser supports reviewed CSV/manual measurements, exact rational inputs, an immutable baseline plan, explicit approval, real Counterdex investigation, separately approved next-measurement design, result reopening, and authenticated native evidence/replay-anchor downloads. The backend owns identities, approvals, scope and scientific execution. Gemini is disabled by default; optional live image proposals and selected-run commentary require private deployment opt-in and separate operation consent. The manual scientific path makes no model-provider calls.

## Local startup

From the repository root, `scripts/dev/setup.sh` once and then `scripts/dev/start.sh` prepare both runtimes and start the API, durable worker and this workspace together on one store, with `BEAN_COUNTERDEX_PYTHON` pointing at the prepared CPython 3.11 engine. AI stays in placeholder mode unless the private live configuration is explicitly enabled; see [Optional live Gemini](../../README.md#optional-live-gemini). To run only this web server against an API you started yourself:

```sh
node apps/web/serve.mjs
```

Open `http://127.0.0.1:4173`. The proxy targets `127.0.0.1:8000` by default. A trusted local launch can set `BEAN_WEB_API_PORT` to a different loopback API port; browser requests cannot select another destination. The proxy rejects foreign hosts/origins and forwards neither cookies nor browser origin headers. This remains a local serving lane, not hosted authentication.

Open **Server connection**, enter an authorized researcher access token, and choose or create a workspace. Credentials stay in memory and are cleared from the password field after connecting. They never enter URLs, downloads, cookies or browser storage. Reloading requires reconnecting. For teammates using the owner's one server and Gemini key, open its shared HTTPS link instead; see [Shared server](../../docs/shared-server.md). No per-person Gemini key is required.

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

Keep a run identifier to reopen authenticated history after reconnecting. A report freezes the selected run and its evidence inventory. Measurement/question drafts remain tab-local; **Download draft** preserves them before closing the tab. Design drafts remain in memory until prepared as an immutable server plan. Hypothetical follow-up observations are supported below. Public sharing remains unavailable.

## Next-measurement design

1. Open a completed baseline with two freshly checked compatible candidates. The two candidate selectors use its actual retained vectors. A single counterexample does not unlock pair design.
2. Enter the feasible elapsed times, a positive future hard allowance, its origin/explanation and the maximum approved horizon. The grid keeps its reviewed order. Explicitly choose whether fixed-candidate certificates may be constructed and extended through that horizon.
3. Choose **Prepare measurement design** and inspect the exact frozen pair, assumptions and limits. The requested tier is checked pair separation; numerical guidance, no separation or unavailable results remain possible. This preview does not execute science.
4. Check the separate design-approval box, choose **Approve reviewed design**, then **Queue approved design**. Editing the design invalidates the current browser approval. Pending jobs poll read-only, and the same accepted plan cannot spend its approval twice.
5. Inspect the selected time and every grid row, including unavailable/skipped rows. Exact margins and checked prediction bands remain available. Checked separation applies only to this pair, grid and allowance; no separating time does not prove the candidates identical or exclude useful times elsewhere.
6. Download the native design evidence and its separate replay anchors. The native packet includes baseline history and is replayable with the same CLI command shown above. Keep the design job identifier to reopen its result; the browser displays that job’s historical run, scenario and pair. Opening a different baseline clears the previous design display.

The synthetic browser control uses feasible times `8, 6` hours and a reviewed allowance of `0.2 mg/L` for checked separation, then a separately approved coarse allowance of `10 mg/L` for checked no-separation. These are requested inputs, never precomputed candidate or result fixtures.

## Verification

```sh
node --test apps/web/*.test.mjs
PLAYWRIGHT_MODULE=/absolute/path/to/playwright/index.js \
BEAN_COUNTERDEX_PYTHON=/absolute/path/to/prepared/python3.11 \
node apps/web/check-backend.mjs
```

`check-backend.mjs` starts an isolated API, worker and proxy on unused loopback ports, drives Chromium through review/approval/queue, submits two distinct datasets to actual discovery, and separately approves positive/no-separation designs from the first actual pair. Native baseline and design bytes plus anchors are downloaded through the browser and replayed in a separate installed `-I` interpreter. The check also covers preserved earlier evidence, zero provider attempts, stale draft/design approval, design history reopening and context clearing, reports, narrow-screen layout, memory-only credentials and proxy origin rejection. It creates no candidate records or synthetic scientific responses. Temporary test data and processes are cleaned up.

Playwright is found through Node's normal resolution or `NODE_PATH`; `PLAYWRIGHT_MODULE` can name its `index.js` entry file. After `npm install` in `tests/integration`, set `NODE_PATH` to that directory's absolute `node_modules` path when running this browser check. Set `BEAN_TEST_PYTHON` or `CHROMIUM_PATH` to override `.venv/bin/python` and Playwright's own Chromium. Playwright is a test-only dependency and is not shipped with the browser application. A missing runtime or failed scientific run fails this milestone check instead of being counted as a successful demonstration.

## Follow-up observations

Open a completed checked-separation design, enter a hypothetical concentration and explain its choice. Prepare and inspect the observation, explicitly accept it as a new dataset revision, then prepare and separately approve the follow-up plan before queueing. The flow retains the selected design time and allowance and rechecks the original pair. Queueing opens the follow-up run directly; execution status updates until the candidate-specific results and native downloads are available. To enter a declared actual observation, choose actual origin and supply its elapsed acquisition time, hard allowance, and acquisition/source justification. Changing origin clears the entered values; it cannot relabel a generated reading. Actual origin is a user declaration, not instrument authentication. A reviewed observation advances the workspace revision. Follow-ups based on older dataset revisions are refused; prepare a new investigation from the current inputs to continue. Before acceptance, Revise observation draft clears the pending proposal for a new review. The original evidence remains immutable.

## Retained source review

Start with `scripts/dev/start.sh --controlled-source-examples` to enable the packaged controlled source manifest. Ordinary startup without this option leaves controlled intake disabled. Neither startup option enables live Gemini; that requires the separate private configuration described in the root README.

Upload a public or synthetic PNG/JPEG and choose its origin explicitly, or choose **Use controlled example image** for the supported synthetic lab sheet. The retained image is displayed for inspection; upload neither extracts values nor approves science.

Choose **Prepare controlled source proposal**. This uses the ordinary authenticated intake API and displays **Controlled example; not Gemini transcription.** Only frozen synthetic image bytes in the packaged manifest are supported. Unknown, altered/reencoded, unreadable or unsupported images return no accepted values and a visible **Continue with manual measurements** link. Existing accepted work is preserved.

Compare every original/proposed value and locator against the image, record corrections and reasons, and resolve blocking diagnostics. Accept the source review, then choose **Use reviewed values in measurement draft** to replace the draft rows with those explicit accepted values. Complete missing measurements and the question separately. Explain the remaining assumptions and inspect the exact source-bound preview before accepting it. Changing the draft requires a new preview. The resulting plan still requires separate scientific approval.

The browser regression uses these same visible controls, including changed-byte refusal and manual fallback. Source review, input materialization, discovery, design, follow-up and native replay use the real application and engine; controlled source values do not supply scientific results. No database helper or copied proposal identifier is needed.

## Optional live image and explanation controls

Live controls appear only when the connected server reports live Gemini dispatch and a selected model. Upload one public or synthetic PNG/JPEG (at most 1600 × 1600 pixels and 5 MiB for live extraction), inspect it, check its separate consent box, then choose **Ask Gemini to read this image**. Upload itself stays local. Review every extracted value and source locator, resolve missing assumptions and use the ordinary source-review/materialization flow before approving scientific work. CSV import belongs in Measurements; PDF upload is unsupported.

Open a run with retained evidence to use **Ask Gemini about this investigation**. Enter a question and accept the disclosure of that run's inputs/evidence and bounded prior question context. No source images are sent in this operation. **Ask Gemini for an explanation** makes one bounded request without automatic retry; an uncertain response retains the same operation identity for explicit retrieval. Scientific statements remain server-owned. Model commentary is labeled unverified or withheld when it fails grounding checks. A message cannot authorize an investigation or a new reading.

**Show Gemini call budget** reads remaining conservative reservations without a model call. These are application limits across the local store, not Google's quota or a billing verification. Live configuration and local smoke testing do not establish formal release qualification. Autonomous live Deep Agents coordination remains unavailable.
