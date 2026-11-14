# Frontend handoff: five-step study experience

Branch `claude/frontend-polish`, based on main `070b697`. Owner of this work: frontend (visual design, page composition, copy, responsive and accessible presentation). B remains the owner of controllers, API contracts, research state and approval behaviour.

## What changed for a person using it

The single long page is now five route-backed steps sharing one shell, one token set and one step rail:

| Step | Hash | Purpose |
|---|---|---|
| 1 Start | `#start` (default; `#research` opens the file-question path) | What Dr. Bean does, start with the example or enter data, the four terms, saved work, the separate file-question path |
| 2 Check inputs | `#inputs`, `#question`, `#review` | Measurements with an allowance plot, claim kept apart from search limits, a plain review of every assumption, then save → approve → start as three numbered actions |
| 3 Investigate | `#investigations` | The approved check's real state and timeline, reopen by run identifier, and the research-assistant plan (honest unavailable state today) |
| 4 Result | `#result` (no secrets or research content in the URL) | Plain conclusion, `ke` number line against the claim, concentration chart with allowance bars and candidate curves, support / assumptions / uncertainty, one next action, evidence downloads, technical states behind a disclosure |
| 5 Next measurement | `#next`, `#report` | Pair comparison with chart and suggested time, follow-up reading, readable report summary and report export |

Navigation only renders. Moving between steps never saves, approves, queues, retries or resets a budget. Browser Back/Forward works across steps. The draft still lives only in the tab: the footer says so, the top bar says "Draft in this tab only" until inputs are saved, and closing the tab with an unsaved draft triggers the browser's leave warning.

## Files and boundaries

Frontend-owned (presentation only):

- `apps/web/index.html`, `apps/web/styles.css` – new shell and token system.
- `apps/web/result-view.mjs` (new) – pure presentation: decimal readings of exact rationals, plain-language interpretation of recorded outcomes, SVG `ke` line and concentration chart. It never computes a verdict; every value comes from a retrieved record.
- `apps/web/app.mjs` – routing, step rail status, study context bar, Start-page wiring, review summary, input plot. Form/validation logic unchanged.

Narrow patches in files that mix presentation and behaviour. **B, please review these specifically:**

1. `apps/web/workflow.mjs`
   - `render()` is split into `renderReview / renderInvestigation / renderResults / renderNext / renderReport` targeting `#backend-review`, `#backend-investigations`, `#backend-results`, `#backend-next`, `#backend-report`; the assistant renders into `#backend-assistant`. Every request body, guard, disabled condition, polling rule and test-facing label is unchanged.
   - `refreshRun()` additionally performs three **read-only** GETs (`/records/{plan_id}`, its problem, its dataset) once per run to draw the chart; failure only hides the chart.
   - `setupWorkflow(..., { onRender })` new optional callback; the returned `render` has a read-only `render.status()` used by the step rail.
   - Errors no longer force the connection panel open unless disconnected.
2. `apps/web/research.mjs` – `ResearchController` is **untouched**. Only `setupResearch()`'s render was rewritten (new optional `onChange`). Labels changed: "Advance research plan" → "Continue research plan", "Approve exact operation and continue" → "Approve this operation", "Save reviewed inputs and research question" → "Create research plan", research anchors download → "Download research replay anchors". "Stop this research plan" now asks for confirmation. Kept: "Save selected files and research question" and the objective in `#durable-research h4`.
3. `apps/web/design-workflow.mjs`, `apps/web/followup-workflow.mjs` – copy, checkbox placement, readable values and a comparison chart. Request construction unchanged.
4. `apps/web/serve.mjs` – registers `/result-view.mjs` in the static allowlist. **If the share gateway or any other proxy keeps its own module allowlist, add `result-view.mjs` there too.**

Tests changed (navigation and display only; no scientific, approval or binding assertion removed):

- `apps/web/check-backend.mjs`: navigates by hash to `#result` / `#next` before clicking controls that now live there; reads `Outcome:` from `#backend-results`; the design grid shows readable times (`8`, `6`), with the exact plan still asserted as `['8/1', '6/1']`; the disconnected message regex.
- `tests/integration/general_workspace_smoke.mjs`: opens `#research` directly, since the measurement study is now the primary entry.
- `tests/integration/shared-session-browser.mjs`: one added hash navigation to `#investigations` before `Save selected files and research question`. **Not run here** (needs the HTTPS sharing gateway); please run it on the assembled stack.

## Integration notes for the coordinator

The Investigate page reads only `capabilities.deepagents` and the existing `DB-RESEARCH-1` snapshot/events. With `execution_mode: 'controlled'` and `dispatch_enabled: true` the "Continue research plan" action becomes available; plan steps map their real `status` to Suggested / Running / Needs your approval / Needs a reading / Done / Failed / Unresolved / Skipped; events map to plain labels with the raw list behind "All recorded events (technical)". On current main `bean_api.research_controlled` is absent, so the page shows the server's `unavailable_reason` and keeps the approved manual check usable. No fixture events are shown.

## Verification run on this branch (macOS, Node 25.3, backend Python 3.13, engine CPython 3.11.17 / Counterdex 0.3.0, Playwright 1.63 Chromium)

| Command | Result |
|---|---|
| `node --test` in `apps/web` | 79 passed, 0 failed |
| `node apps/web/check-backend.mjs` | Passed: real discovery on two inputs, checked-separation and no-separation designs, hypothetical follow-up, native + anchor downloads replayed by the installed engine, zero provider attempts, 390 px no horizontal scroll |
| same with `BEAN_TEST_FOLLOWUP_ORIGIN=actual` | Passed |
| `node tests/integration/web_manual_smoke.mjs` | 18/18 |
| `node tests/integration/general_workspace_smoke.mjs` | 23/23 (controlled HTTP fixture lane) |

Environment: `NODE_PATH=$PWD/tests/integration/node_modules BEAN_TEST_PYTHON=$PWD/.venv/bin/python BEAN_COUNTERDEX_PYTHON=$PWD/.venv-engine/bin/python`. No Gemini calls; all runs use isolated ports and temporary stores.

Manual browser rehearsal (isolated API/worker/web on 8811/4811): first visit, example study, review, approval, running and finished check, result, comparison, report, phone (390), tablet (820) and laptop (1280) widths, keyboard-only from skip link to primary action. Screenshots: `docs/frontend/screenshots/`.

## Two-minute walkthrough for a teammate

1. Start the stack (`scripts/dev/start.sh`), open the web app and expand **Connect to a Dr. Bean server** if it is not automatic; create or pick a workspace.
2. On **Start**, choose **Start with the example study**. The claim and search limits are prefilled from the synthetic example and marked as such.
3. In **Check inputs → Measurements**, choose **Use these rows**. Note the plot: each reading with its ±0.50 mg/L allowance bar. Choose **Next: describe the claim**, review the values, then **Next: review inputs**.
4. On **Review and approve**, read "What the check will assume", choose **Save inputs and prepare plan**, read what the approval covers (no AI model, limits, design not included), tick the box, **Approve reviewed plan**, then **Queue approved manual run**.
5. **Investigate** shows the real state; when it finishes choose **View results**.
6. **Result**: the claim is not forced — one checked candidate lies outside the shaded claim. Both curves pass every allowance bar. Read "Still uncertain". Download evidence if needed.
7. **Compare measurement times**: enter `8, 6`, allowance `0.2`, latest time `8`, a reason, tick both permissions, prepare, approve, queue. The chart shows where the two curves part and marks the suggested time.
8. **Report**: create and download the report JSON.

## Known limitations

- Research-assistant coordination is unavailable on current main; its view is built against the real contract but has only been exercised in the unavailable and empty states here.
- The investigation question generated by `manual.mjs` uses exact rationals (`[1/10, 17/100] 1/h`); it is frozen into the plan, so the UI shows it verbatim.
- Charts are drawn with decimal approximations and labelled as such; exact values stay in the technical disclosures.
- Draft persistence is unchanged: in-memory only, with download and leave-warning.
- Reload requires reconnecting (unchanged authentication model).

## Design skills applied

`frontend-design` (direction, token plan, generic-default review), `charles-unslop` (direction, subtraction, ordered passes), Vercel `web-design-guidelines` (fetched rules: contrast, focus, sticky-header focus, unsaved-changes warning, destructive confirmation, `tabular-nums`, `text-wrap`). Where Vercel asks for Title Case and frontend-design for sentence case, sentence case was kept for one voice.
