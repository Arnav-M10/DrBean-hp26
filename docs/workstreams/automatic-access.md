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
the full rerun in the matching environment passed all 1,256 tests with no skips. Schema export produces
identical schema definitions but existing PDF example boxes vary by about 0.0003
on macOS. Generator changes were not retained; frozen examples were not edited.

Claude’s independent `tests/integration/langchain_demo_browser.mjs` still targets
old bearer onboarding and is not registered in ordinary CI. It was left unchanged
for its owner to update; the retained production-path `check-research.mjs` passes.

## Failure-injection review

A separate read-only implementation review found two integration defects.
Interrupted HTTP 200 response bodies now keep the pending-session marker, so
an explicit retry first checks identity and never silently issues again.
A 408 response is also treated as uncertain. Real failing-stream regressions
and an independent reproduction each confirm one issuance across retries.

Public sharing children now strip the local gateway configuration added by
the launcher. A regression uses the real launcher environment with a temporary
fixture directory and mocked process creation; no tunnel is opened. The
launcher/sharing suite now passes 50 tests. Reviewer found no further session
authorization defect; this does not substitute for the outstanding UI recovery
and final combined-browser acceptance.

Backend full-run evidence: 1,256 passed, no skips, Ruff passed, zero
egress/provider-client attempts and no inherited credentials. One existing
opt-in test read its own synthetic fixture, not an owner credential.
`1649820e70fd8169ce2ac20a5a432e10ef6a88b1` identifies the reviewed backend;
backend files were unchanged throughout that run.

## Owner 3 connection handoff

The user confirmed their teammate is actively implementing
`03_Researcher_Guided_Journey.md`. Their workflow/index/app files remain untouched
on this branch. Integrate these small hooks in that owner's connection block:

- Remove the token form from the initial HTML, including obsolete form listeners.
  Initial status is Connecting; successful automatic connection closes the
  troubleshooting disclosure. Ready requires valid capabilities and membership
  in the returned workspace.
- Initial entry and explicit `#connection-retry` call
  `bootstrapSharedSession()`. It uses current-session reads before issuance;
  no caller should add a retry loop around it.
- When the caught error has `mayStartNew === true`, expose
  `#connection-start-new` labelled Start a new private workspace. Only that
  explicit click passes `{startNew:true}` as the second argument. Explain that
  this does not recover or transfer expired/cleared-session research.
- `#connection-status` carries Connecting, Ready or the specific recovery error.
  Preserve the existing onConnectionChange callback's private workspace identity,
  same-identity API instance and frozen operation IDs. Read failures never resubmit
  science/consent/model requests or discard pending-operation reconciliation.
- Owner 3 retains app chrome, navigation and remaining structure; Owner 4 may
  refine labels without changing these semantics.

The new `tests/integration/automatic-access-browser.mjs` is the runnable combined
acceptance test. It currently fails at missing `#connection-retry`, after four
passed groups in the retained initial run. Later recovery/privacy/science cases
are implemented but not claimed as executed. It is not registered as a passing
CI gate until the controls land.

Reproduction with the repository's locked backend runtime, source-matching
CPython 3.11 engine, and pinned Playwright:

```sh
node --test apps/web/*.test.mjs
.venv/bin/python -m unittest scripts/dev/test_launcher.py scripts/dev/test_share.py
BEAN_AI_MODE=placeholder BEAN_COUNTERDEX_PYTHON="$PWD/.venv-engine/bin/python" \
  PATH="$PWD/.venv-engine/bin:$PATH" .venv/bin/python -m pytest -q tests --ignore=tests/integration
PLAYWRIGHT_MODULE="$PWD/tests/integration/node_modules/playwright" \
  BEAN_AUTOMATIC_ACCESS_EVIDENCE_DIR=/tmp/drbean-access-acceptance \
  node tests/integration/automatic-access-browser.mjs
```

The browser runner supplies a temporary store, private fixture configuration,
nonstandard ports, restricted HTTPS harness and egress guard. It verifies engine
source equality before dispatch. Existing ordinary science runners remain
`apps/web/check-backend.mjs` (also with `BEAN_TEST_FOLLOWUP_ORIGIN=actual`) and
`apps/web/check-research.mjs`; editor/general smoke remain in ordinary CI.
No external HTTPS tunnel or live provider qualification is claimed.

## CI navigation synchronization

At `6dee207`, CI passed the real HTTPS private-session checks, maintained-plan/
separate-design investigation, and ordinary manual science loop. The declared-
actual repeat failed before science: it filled the source-assumption textarea
while hash navigation to Review was still rebuilding that panel and moving focus.

The retained browser runner now waits for the actual Question/Review view and
focused heading, then asserts the exact explanation value before preview. No
sleep, retry of a scientific action, assertion removal or production change was
introduced. The full declared-actual workflow passed again on the pinned local
runtime, including its own 7-hour time and 0.3 allowance, both design outcomes,
native downloads/fresh replay, private session revocation and zero providers.

Teammate review handoffs are posted on PR48 (neutral result wording and connection
ownership), PR49 (closed disclosure keyboard focus during animation), and PR50
(two scientific wording corrections and six UI merge conflicts). Those are
owner-specific corrections, not duplicated implementations or combined acceptance.
