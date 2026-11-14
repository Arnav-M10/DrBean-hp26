# General research UI handoff

UI owner branch: `codex/general-research-ui`, base main `296578a`.
Scope: general-workspace module/tests, index/styles and app/workflow hooks.
GPT1 owns transport/private sessions/proxies/startup. Claude owns general assets,
analysis schemas/providers/budgets. Prior Deep Agents work remains untouched in
its isolated worktree; this assignment replaces that implementation scope here.

## Proposed adapter agreement (confirm changes before integration)

GPT1 agreement adopted: import `bootstrapSharedSession()` from `session.mjs`.
It resolves `{api, session}` only after `/shared-session` reports
`mode=browser_session`, `authenticated=true`, `credentials=server_managed`.
Use `session.workspace_id` and fetch capabilities through that same API. A null
return means only a local-boundary 404; expired/malformed sessions stay visible.
`api` exposes authenticated `json(path, body?)`,
`uploadResearchAsset(workspaceId, file, operationId)` and
`researchAnalysis(workspaceId, frozenBody)`. The latter uses the body's
`client_operation_id` as its key. Session requests send same-origin cookies;
manual owner login stays available. No JavaScript session/bearer secret is
returned by automatic bootstrap. Please also register new static modules,
`X-Source-Name`, research-analysis timeouts, and safe filename-header forwarding
in the fixed proxies you own.

UI integration: `setupWorkflow(..., {onConnectionChange})` reports
`{api, capabilities, workspaceId, mode}` to the general workspace. Allowed modes
are `browser_session` and explicitly authenticated `local_owner`; `shared_demo`
never enables private general uploads. Session/bootstrap remains GPT1 code.

Claude: use the prompt's unchanged raw upload/analysis/GET routes. Please confirm
typed result and capability shapes early. Suggested `general_research` capability:
`available`, `media_types`, `max_assets`, `max_file_bytes`, `max_total_bytes`,
`max_pdf_pages`, `analysis:{available,model,reason}`, and
`budget:{remaining:{requests,input_tokens,output_tokens}}`.

Proposed body types: `summary` string; `extracted_tables` with `id`, `title`,
`columns` strings, `rows` arrays of strings/null, `citation_ids`; `claims` and
`suggested_next_steps` with `text`/`citation_ids`; `limitations` strings;
`clarifications` with `question`/`citation_ids`; and `citations` with `id`,
`asset_id`, `source_sha256`, zero-based `page_index`, exact `quote`, optional
normalized `bbox` and explicit `bbox_space`. `verification.status` stays
`not_mathematically_verified`; provider mode/controlled provenance is visible.
Please supply authorized preview/byte routes and real public-file provenance.

## UI invariants and current task

- Primary: add 1–5 real files → inspect retained sources → ask question → review
  exact file/question/model disclosure → explicit analysis → cited evidence.
- Enforce lower client/server limits: 5 MiB each, 10 MiB total, ten PDF pages;
  the server decides actual format/parser success. No filename-only success.
- A frozen operation survives uncertain responses and page reload without an
  automatic retry. Question/source edits require a new operation and consent.
- General outputs use text nodes and bounded tables. No raw HTML or verified AI
  badge, automatic scientific mapping, model fallback or budget reset.
- Save result references and pending operation only within the current private
  session/workspace; a new session must not inherit another session's sources.
- Browser acceptance will cover real public files with controlled model output,
  citations, malicious text, repeated/changed consent, reload/reopen, budget
  refusal, and two actual private browser contexts on the assembled backend.
- No live calls or public tunnel activation are needed for development tests.

## Delivered UI candidate

Runtime/test head: `7f523c8f0f5e6ffac006037516939917027caf45`, PR #38.
Compatible private-session dependency #39 is included by normal merge ancestry
at `d943afe`; no competing auth, parser, provider or scientific engine was added.

- Root opens the real-file research screen. The existing supported scientific
  workflow remains at `#inputs`; examples are optional there.
- Files/question/model are reviewed before explicit consent. Every disclosure
  refreshes the server's current capabilities/budget; no automatic provider retry.
- Uncertain uploads retain exact filename/bytes/media hint/operation ID in memory
  and bounded metadata for matching-file reselection after reload. Unknown
  analysis outcomes retain the original body/key across reload and workspace
  switching. A new identity clears previous private-session client state.
- Restoration immediately clears old views and locks edits. Late responses are
  generation-fenced. Reopening binds the exact result ID and source IDs/digests.
- Source/model text is inert, previews/tables are bounded, citations use human
  page numbers, and AI output cannot acquire a mathematical verification badge.
- Merely connecting or using science stores no browser credentials or data.
  General-workspace session storage holds only user drafts/references/request
  identities; never a session secret, bearer token or Gemini key.

## Rehearsal and checks

Use GPT1's documented setup and private-session gateway; local operator login
remains in Advanced server connection. Open `#research`, select admitted files,
inspect sources, enter a question, review the exact disclosure and accept it.
After analysis, inspect tables/claims/limitations and their source buttons.
Reopen a saved analysis to retrieve it; for an uncertain operation inspect its
original disclosure and deliberately retry that same operation.

**Availability gate:** current main has no general-research producer. File
admission/analysis is honestly unavailable until Claude's actual routes and
capability helper are registered by GPT1. There is no production fixture answer.
Controlled browser tests are an explicit test lane, not a substitute for this join.

Executed on the runtime candidate (Linux, Node 24.22.1; backend Python 3.12.14,
matching installed Counterdex 0.3 / Python 3.11.18):

| Command | Actual result |
| --- | --- |
| `node --test apps/web/*.test.mjs` | 71 passed; 17 new controller cases |
| `CHROMIUM_PATH=/usr/bin/chromium node tests/integration/general_workspace_smoke.mjs` | 23 controlled-HTTP/UI checks passed; real public CSV bytes, authored analysis |
| `CHROMIUM_PATH=/usr/bin/chromium node tests/integration/web_manual_smoke.mjs` | 18/18 manual scientific-editor checks passed |
| `CHROMIUM_PATH=/usr/bin/chromium node tests/integration/shared-session-browser.mjs` | 12/12 actual HTTPS gateway/API/private-session checks passed; two browser contexts |
| `CHROMIUM_PATH=/usr/bin/chromium node apps/web/check-backend.mjs` | Real baseline/design/follow-up/download/installed replay passed |
| Same scientific command with `BEAN_TEST_FOLLOWUP_ORIGIN=actual` | Declared-actual follow-up lane passed, preserving synthetic test ancestry |
| `.venv/bin/python -m pytest -q tests/test_browser_sessions.py` | 21 actual backend authority tests passed |

Supply `BEAN_TEST_PYTHON=$PWD/.venv/bin/python` and
`BEAN_COUNTERDEX_PYTHON=$PWD/.venv-engine/bin/python` for scientific commands.
Install the pinned browser dependencies with
`npm ci --prefix tests/integration --ignore-scripts`; use prepared Playwright
Chromium or set `CHROMIUM_PATH` for the local installed binary. No process
limits were relaxed, model calls made, budget history reset or public tunnel
started. The precise expected local `/shared-session` 404 is asserted in the
manual lane; all real JS and other console errors still fail.

The public Palmer Penguins excerpt, immutable digests and CC0 provenance are in
`tests/integration/fixtures/general/`. Retained results are in
`docs/evidence/general-ui/`. Earlier failing runs were not rewritten as passes;
the final scientific lane preserves and additionally asserts the exact custom
question after source materialization.

## Integration blockers and owner action

Claude must publish `codex/general-gemini-files`, the exact typed asset/result/
preview shapes and `register_general_routes(app)`/capability helper with state
dependencies. GPT1 registers those actual services. Then bind any agreed schema
amendments and rerun the combined real-parser/general-analysis browser lane,
including cross-session general asset/analysis denial and saved-result reopening.
The 23-check authored HTTP lane does not prove those missing backend predicates.
Live Gemini qualification remains not_run; the user permits free tier only, $0.
The UI component is reviewable; the full general product is not declared complete.

GitHub Actions [run 43594171124](https://github.com/Arnav-M10/DrBean-hp26/actions/runs/43594171124)
passed all six jobs on the runtime/test candidate: backend/lint/schemas,
web units, scientific/browser/native replay, ordinary stack/restart smoke,
engine/native replay and evaluator self-checks. The separately retained
23-check controlled general browser lane was also run locally; it is not yet
an independent general-backend qualification job.
