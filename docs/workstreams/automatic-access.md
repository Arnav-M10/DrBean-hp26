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
