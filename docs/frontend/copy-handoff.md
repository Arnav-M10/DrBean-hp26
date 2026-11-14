# Copy pass: plain language and less clutter (owner 4)

Branch `owner4/plain-language`, based on main `aa51f162422aaca000e95de86d9baf6d62ca0f03`. Terms are fixed in [`copy-terminology.md`](copy-terminology.md).

## What this change is

Text-only edits to the shipped interface: string literals in `apps/web/*.mjs` and text nodes in `apps/web/index.html`. No element IDs, request bodies, guards, disabled conditions, polling, approval binding or server payloads changed. I picked a narrow string-replacement patch over a shared copy module, so owner 3's structural work can merge with no new imports or wiring.

Not reworded on purpose:
- machine codes (`error_code`, outcome tiers, `Design tier: …`), exact values, digests and file names
- text that is sent to the server and frozen into a plan, such as the follow-up `change_reason`, `success_criterion` and the planned question in `followup-workflow.mjs` and `manual.mjs`
- uploaded and quoted source text, citations and model commentary bodies
- explanation sentences in `api.mjs`, which the grounding and overclaim tests check (owner 5's lane)
- the research-plan control labels that `check-research.mjs` and owner 5 rely on: "Advance research plan", "Approve exact operation and continue", the approval checkbox wording and "Save reviewed inputs and research question"

## Renamed controls (tests updated with the same assertions)

| Before | After |
|---|---|
| Save inputs and prepare plan | Save inputs and prepare check |
| Approve reviewed plan / Plan approved | Approve check / Check approved |
| Queue approved manual run | Run approved check |
| Run identifier / Open or refresh run | Check ID / Open check |
| Download native scientific evidence (and the research panel's "Download native evidence") | Download evidence file |
| Download independent replay anchors | Download replay anchors |
| Prepare measurement design | Prepare comparison |
| Approve reviewed design / Design approved | Approve comparison / Comparison approved |
| Queue approved design | Run approved comparison |
| Open or refresh design | Open comparison |
| Download native design evidence / design replay anchors | Download comparison evidence file / comparison replay anchors |
| Prepare actual observation / Accept reviewed actual observation | Prepare actual reading / Accept actual reading |
| Prepare follow-up investigation plan | Prepare recheck |
| Approve reviewed follow-up / Queue approved follow-up | Approve recheck / Run approved recheck |
| Follow-up candidate checks (region) | Recheck of the compared candidates |
| Create report for selected run / Download exact report JSON | Create report / Download report (JSON) |

Selectors and one message regex (`/Draft changed/` to `/You edited the draft after saving it/`, same stale-approval assertion) changed in `apps/web/check-backend.mjs`, `apps/web/check-research.mjs`, `tests/integration/web_manual_smoke.mjs` and `tests/integration/langchain_demo_browser.mjs`. Each test still asserts the same behaviour. `web_manual_smoke`'s "planning honestly unavailable" check now matches the new unavailable sentence. Two unit-test predicates (`/combined limit/`, `/exact pending/`) are unchanged; the new sentences still contain those phrases.

## Before and after

| Where | Before | After |
|---|---|---|
| Result, counterexample | Your measurements do not force the claim. The checker found parameter values that fit every included reading within its allowance, yet put the elimination rate outside the claimed range. | Your readings do not force the claim. The checker found a candidate that fits every included reading within its allowance but has an elimination rate outside the claimed range. |
| Result, none found | The bounded search found no parameter values that fit the readings and fall outside the claim. / This is not proof of the claim. A search with limits can miss a counterexample. | This search found no checked candidate outside the claimed range. / This does not prove the claim. The search covers only your search limits and can miss a counterexample. |
| Result, support line | Shown as fully checked when verification was valid and replay passed, **without looking at binding** | Shown as fully checked only when verification is valid, **binding matches** and replay passed: "The checker accepted this evidence, it is tied to the inputs you saved, and it can be replayed outside the browser." Otherwise: "This result is not fully checked." followed by the three raw states |
| Evidence downloads | Together they let anyone re-run the check with the Counterdex command-line tool. | With both, anyone can recompute the recorded candidates using the Counterdex command-line tool. Replay does not repeat the search. |
| Gemini commentary withheld | Gemini commentary was withheld because it did not meet the evidence-grounding checks. The stored scientific results remain available above. | Gemini commentary was withheld because the evidence records did not support it. The checked results above are unaffected. |
| Not connected | Disconnected. Investigation planning is unavailable. | Not connected. Connect to save inputs and run checks. |
| Image reading off | Gemini is a disabled placeholder. Upload retains a source locally without extraction or scientific approval. Enter measurements manually when no reviewed proposal is available. | Image reading with Gemini is off on this server. You can still upload an image to keep it with your study, but no values are read from it. Type the readings into the table instead. |
| Version mismatch | Unsupported API contract or policy version. | This server runs a different version of Dr. Bean than this page. Reload the page. If the message stays, ask the server owner to update. |
| Check stopped | The check stopped: `E_CODE`. Any completed evidence is kept. | The check stopped before finishing (`E_CODE`). Evidence it already recorded is kept. Review the inputs and start a new check. |

The "support line" row fixes a real overclaim: the old sentence said "The evidence matches your saved inputs" without checking `expected_binding`.

## Clutter audit: requests to owner 3 (structure)

1. **Draft warning shown twice.** The top bar says "Draft in this tab only" and the footer repeats "Your draft is not saved…". Keep the footer sentence and the top-bar state; drop the footer's first bold sentence once inputs are saved.
2. **Approval scope said three times on Review.** The page lede, the button help and the "What this approval covers" list overlap. I shortened the lede. Please keep the list and the help line under each button, and remove any third restatement if one comes back.
3. **Investigate page leads with two long intro paragraphs** (check timeline and assistant). Put "How the assistant works" (`research.mjs`, intro and model line) in a closed disclosure under the research-plan heading, and keep the controlled-versus-live provenance line visible.
4. **Start page.** The "Four words you will see" glossary and the scope list both define terms. Keep the glossary and cut the scope list to Model, Units and Data you can bring; the "Who decides what" sentence fits under the lede.

## Typography and colour: requests to owner 2 (design)

1. **One family.** `h1` and `.verdict-statement` use `--serif` (Iowan/Palatino) while everything else uses `--sans`. Please use the system sans stack for all interface text and keep `--mono` for codes and exact values.
2. **Neutral navigation.** The step rail marks the current step and the done steps with the accent colour (`--act`, white numerals on filled circles). The user asked for no coloured sidebar: please use ink weight and a neutral marker for the current step, and keep colour for states that need attention.
3. **Text roles.** Settle on a few roles (page title, section title, body, help/fine print, technical) with fixed sizes, and drop per-component sizes such as `.steps-note` and `.fine` variants that differ only slightly.
4. **Line length.** Body paragraphs, ledes and help text: about 65 characters (`max-width: 65ch`). The verdict statement already uses 40rem.
5. **Semantic colour only for state.** Chips for checked, waiting, failed and unsupported states. Pair each with its text label, which the copy already provides.

## Verification

Run on commit `b8b99f6` (this branch, based on main `aa51f16`), Linux, Node 22.23.4, backend Python 3.13.18 (`.venv` from `scripts/dev/setup.sh`), engine CPython 3.11.15 / Counterdex 0.3.0, the session's preinstalled Playwright Chromium. Environment: `NODE_PATH=<playwright> BEAN_TEST_PYTHON=$PWD/.venv/bin/python BEAN_COUNTERDEX_PYTHON=$PWD/.venv-engine/bin/python`. Isolated ports and temporary stores; no provider calls.

| Command | Result |
|---|---|
| `node --test` in `apps/web` | 81 passed, 0 failed |
| `node apps/web/check-backend.mjs` | Passed (the same command also passed on unchanged main before the edits) |
| same with `BEAN_TEST_FOLLOWUP_ORIGIN=actual` | Passed |
| `node apps/web/check-research.mjs` | Passed |
| `node tests/integration/web_manual_smoke.mjs` | 18/18 |
| `node tests/integration/shared-session-browser.mjs` | Passed |
| `node tests/integration/general_workspace_smoke.mjs` | Passed |
| `.venv/bin/python -m pytest tests/test_general_research_contract.py` | 7 passed |
| `node tests/integration/langchain_demo_browser.mjs` | **Fails, and fails identically on unchanged main `aa51f16`**: both stop waiting for "Advance research plan" after "Save reviewed inputs and research question". Not caused by this change; its two renamed download labels are updated but unexercised past that point |

Screenshots of the real flow after the change (real API, worker and Counterdex; synthetic example): `docs/frontend/screenshots/copy-pass/`, covering the start page, readings, claim, review while not connected, approved review, Investigate, the result, the comparison, the report and the result at 390 px.

## Walkthrough

1. Start the stack (`scripts/dev/start.sh`), open the web app, connect and pick a workspace.
2. Measurements: **Load synthetic example**, **Use these rows**, **Next: describe the claim**.
3. Claim and assumptions: fill the dataset fields, then **Next: review inputs**.
4. Review: **Save inputs and prepare check**, read what the approval covers, tick the box, **Approve check**, **Run approved check**.
5. Result: "Your readings do not force the claim…", with the support, assumptions and uncertainty lines. Then **Download evidence file** and **Download replay anchors**.
6. Next measurement: enter `8, 6`, allowance `0.2`, latest time `8` and a reason. Tick both permissions, then **Prepare comparison**, **Approve comparison**, **Run approved comparison**.
7. Report: **Create report**, **Download report (JSON)**.

## Integration needs and limits

- Owner 3: the five structure requests above. My edits touch the same files (`workflow.mjs`, `index.html`, `app.mjs`, …) but only inside string literals, so conflicts should be line-local. If owner 3 rewrote a sentence, keep their structure and re-apply the wording from the before/after table and the terminology file.
- Owner 2: the five typography and colour requests above. I did not edit `styles.css`.
- Owner 5: please cross-check the result statements in `result-view.mjs` and the support line in `workflow.mjs` against your canonical result fixtures. The research-plan labels and the `api.mjs` explanation sentences are unchanged for you.
- Owner 1: after merging, re-run `check-backend.mjs` (both origins) and `check-research.mjs`; their selectors depend on the new button names.
- Still technical, left on purpose: the frozen plan question (`[1/10, 17/100] 1/h`) and success criterion ("No witness found does not prove the claim"). They are authored in `manual.mjs` but frozen into every plan, and a check-backend assertion matches them. Rewording them changes plan content, so it needs owner 3/5 agreement.
- The Wikipedia "Signs of AI writing" page could not be fetched from this session (network policy blocks `en.wikipedia.org`). I used the patterns quoted in the Impeccable `clarify`/`distill` references and Vercel's writing guidelines (both read from their GitHub repos) instead.
