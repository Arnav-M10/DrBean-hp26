# Automatic private browser access

Owner 1, five-owner sprint, isolated branch `codex/automatic-private-access`.
Base: current main `aa51f162422aaca000e95de86d9baf6d62ca0f03`.
Existing owner worktrees, credentials, data, provider budgets and services remain untouched.

The local launcher/proxy now uses the existing private browser-session service,
with a separate server-controlled loopback boundary and HttpOnly cookie. Public
HTTPS retains its Secure cookie and exact-origin gateway. Operator bearer access
stays on the direct API. The nonissuing current-session route confirms cookie
retention and enables bounded read-only recovery. Browser bootstrap serializes
concurrent calls, retains nonsecret continuity metadata, and never retries
issuance or scientific/model operations automatically.

Component verification on this implementation:

- 62 backend tests passed: local/shared sessions, general private sessions,
  ordinary API and existing independent-session regressions. These are Owner 1
  executions of the independent tests, not a fresh independent evaluator verdict.
- 14 local/public proxy tests and 49 launcher/sharing tests passed.
- 12 browser-session module tests passed, including quota-blocked site storage,
  lost issuance response, cookie refusal, capacity refusal and substitution.
- Actual launcher/Chromium partial acceptance passed local first visit,
  simultaneous first tabs, reload, independent HTTPS visitors and zero
  provider/science ledger changes. CPython 3.11.17 Counterdex 0.3.0 source matches
  the candidate's 24 Python files. Recovery/full-science acceptance is pending
  the agreed connection controls; this partial run is not final qualification.

Owner 3 seam proposed on PR #46: Owner 1 writes only the workflow connection
block and small connection markup; Owner 3 retains page/chrome/navigation/form
composition. Awaiting that explicit agreement before shared-file edits. Hooks:
`#connection-status`, `#connection-retry`, `#connection-start-new`; modes
`connecting`, `browser_session`, `session_error`. Owner 2's motion registration
will be reconciled once its focused PR is published. Other owners' final PRs and
the resulting combined candidate still need integration and browser retesting.

No provider calls or new public tunnel have run. Temporary fixture stores and
nonstandard ports are used for acceptance; no real owner credentials were read.

## Browser and launcher regression checkpoint

The ordinary retained manual-science and controlled Deep Agents browser runners
now use automatic local sessions and their actual cookie transport. Both passed,
including the separate declared-actual follow-up variant, real baseline,
changed inputs, positive/no-separation design, native downloads and fresh replay.
The editor smoke passed 18 checks; general UI smoke passed 23 checks. All 94 web
unit tests passed. Proxy headers are disabled explicitly at the API process.
The secret scan passed after replacing a literal dummy bearer string in a test
with its already generated dummy fixture; no credential or scanner rule changed.

The initially reused backend runtime lacked the locked PDF decoder dependency.
It was left untouched; a fresh locked backend runtime was prepared separately.
The initial full run had 1,233 passes and 23 PDF-dependent failures/errors;
a full rerun in the matching environment is in progress. Schema export produces
identical schema definitions but existing PDF example boxes vary by about 0.0003
on macOS. Generator changes were not retained; frozen examples were not edited.

Claude’s independent `tests/integration/langchain_demo_browser.mjs` still targets
old bearer onboarding and is not registered in ordinary CI. It was left unchanged
for its owner to update; the retained production-path `check-research.mjs` passes.
