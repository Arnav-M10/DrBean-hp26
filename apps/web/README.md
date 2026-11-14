# Dr. Bean researcher and reviewer workspace

The dependency-free editor supports CSV/manual measurements, exact rational entry, question review, and tab-local draft download. It now connects to Owner 02’s real DB-SC-1 / GF-2 API for manual dataset/problem creation, immutable plan review, explicit approval, run retrieval, report snapshots and authenticated evidence/report downloads. The browser never creates authoritative identities or checks scientific certificates.

## Run locally

From the repository root run `scripts/dev/setup.sh` once, then `scripts/dev/start.sh`. That starts the API on `127.0.0.1:8000`, its durable worker and this frontend on `http://127.0.0.1:4173`, with AI in placeholder mode. To run only the editor, use `node apps/web/serve.mjs`. No frontend installation is required. Run `node --test` from `apps/web` (22 tests).

Open **Local backend connection**, enter the local researcher bearer token from the private backend auth file, and connect. Choose or create a workspace. Tokens stay only in memory; they are cleared from the password field after submission, never put in URLs, exports, browser storage or cookies. Disconnect clears the client and selected records. Reload requires reconnecting.

The frontend server proxies only `/api/bean/v1/` to the fixed loopback port 8000. It forwards bearer authorization and operation keys, rejects foreign origins/hosts, and does not forward cookies or browser origin headers. This is a loopback development lane, not hosted authentication or deployment. The backend continues to enforce authentication, ownership and all semantic validation.

For an editor exercise, load the explicitly synthetic example. Enter an experiment identifier, describe t=0, and select **Synthetic** origin. It is the project's shared five-row example (4.80, 7.20, 8.00, 6.80, 5.70 mg/L at 0.25, 0.5, 1, 2, 4 h; allowance 0.50). Use scale `[0.001,30]`, ke `[0.015,0.35]`, ka `[0.4,8]`, target `[0.10,0.17]`, and describe the team-chosen historical hard allowance of `0.50` mg/L. These bounds are assumptions for review, not values read from a source. Review the inputs and choose **Save inputs and prepare plan**. This writes an immutable dataset/problem/plan; it does not execute science or contact Gemini. Review the exact frozen dataset, problem and plan, then check the approval box and explicitly approve. Editing the draft requires a new plan. Queueing is a separate action and rechecks server capabilities.

Imported CSV spellings, duplicate times, included/excluded flags, source digest/description and pre-edit imported values are preserved in the submitted dataset. CSV file bytes are not uploaded or represented as server source assets. All manual wire fields follow the authoritative generated schemas under `shared/contracts/DB-SC-1`, derived from `apps/api/bean_api/contracts.py`; the API runtime validates them. Server errors retain field paths, current revision and request identifiers. Uncertain mutation retries reuse a tab-local operation key; they are never automatically resent.

In **Investigations**, enter a saved run identifier and refresh to retrieve authenticated history for the selected workspace. Execution state, scientific outcome, verification, expected binding and replay are separate. Evidence downloads use the actual authenticated artifact endpoint. In **Report**, create an immutable snapshot for the selected run and download the exact server JSON. Both downloads hash the received bytes against `X-Artifact-SHA256` before saving. This establishes byte integrity only. Native scientific bundles, browser replay and public reviewer sharing are unavailable.

Drafts remain tab-local. Download draft saves inputs, provenance and experiment context; JSON reopen remains unavailable. Backend records are durable. Keep a run identifier to reopen history after reconnecting.

## Current integration boundary

Latest refs were fetched before implementation; baseline `9c39080` includes Owner 02’s backend, generated schemas, Owner 01’s Counterdex package and Owner 04’s harness. The old statement that the repository/backend are missing is obsolete.

**The real scientific milestone remains blocked.** `apps/api/bean_api/main.py` and the worker still default to `UnavailableAdapter`. Counterdex’s `packages/groundwork_adapter/docs/INTEGRATION.md` explicitly leaves scientific projection/DTO mapping and backend interpreter qualification pending. Owner 02 must adopt Owner 01’s scientific fields, bind scenario/problem/artifact identities, install and select the adapter in both API and worker, and publish qualified capabilities. Owner 01 must supply the matching prepared scenario and artifact for that adopted mapping. The frontend keeps queueing unavailable until the API reports a qualified adapter for this template. It never imports package-local fixtures as live results.

Next-measurement execution stays unavailable pending that adopted design mapping and usable historical evidence; its scientific plan and approval must remain separate. Gemini source intake and follow-up remain visibly unavailable in this frontend: live account/model/network/budget qualification and exact per-payload consent are still needed from Owners 02/04 before a live claim. No provider call was made here. No conversation text grants approval.

The Windows-only `03_Researcher_Reviewer_Web.md` was not supplied in this cloud workspace. This continuation follows the user’s stated milestone and repository GF-2 / DB-SC-1 documentation; full work-order conformance remains unconfirmed until the file is supplied.

## Browser/backend verification

`check-backend.mjs` launches the actual API and worker with an isolated temporary SQLite database and synthetic in-process credentials, then drives Chromium. It requires an installed backend Python environment and Playwright, and ports 8000/4173 must be free. It removes its temporary data and stops its processes.

```sh
node apps/web/check-backend.mjs
```

It finds Playwright through Node's normal resolution (`npm install` in `tests/integration`, or `NODE_PATH`); set `PLAYWRIGHT_MODULE` to name an entry file explicitly. Set `BEAN_TEST_PYTHON` and `CHROMIUM_PATH` to override `.venv/bin/python` and Playwright's own Chromium. Provider credentials in your shell are removed from the processes it starts. Playwright is a test-only dependency, not shipped in the frontend. Observed validation: all 22 Node tests passed; the real browser/API check passed plan preparation, approval, blocked unqualified UI dispatch, explicit unsupported worker lifecycle via HTTP, persisted run retrieval, exact evidence/report download, stale-edit controls, 390px layout, memory-only credentials and proxy origin rejection. The worker check deliberately tests its honest unsupported result; it is not a real scientific scenario, fixture replay, Gemini or live-evidence success.
