# Private browser access and integration

## 2026-11-14 — private-session implementation

Owner: GPT1, following `docs/agent-prompts/01_Your_GPT_Shared_Access_and_Integration.md`.
Isolated branch `codex/shared-server-integration`, PR #39, started from the required
shared-access handoff and fast-forwarded to current main `296578a`. No reset,
force push, obsolete PR merge, existing credential change or owner-server restart.

Implementation candidate: `d204ce3baf35b9bb76db24d74f930f55226bee9b`.
Private browser sessions use random actors/workspaces, a bounded HttpOnly/Secure/
SameSite cookie, hash-only storage, durable expiry/revocation and atomic issuance.
Owner bearer access and all existing provider reservations remain separate.
The gateway validates the approved HTTPS host and request origins, strips client
owner credentials and supplies its independent private hop proof. An external
link may load the entry document; cross-site APIs and mutations remain refused.
Sharing no longer provisions a common actor or restarts the API. Owned-process
locking/recovery and closing public admission before core shutdown protect the
fixed upstream ports, including when another process's ownership is unproven.

The committed contract is `shared/contracts/SHARED_SESSION_INTEGRATION.md`.
UI owner #38 accepted the bootstrap module, shared connection callback and explicit
upload operation identity. Claude's registration/capability helper remains a
concrete dependency; no general route or production fallback is fabricated.

### Checks actually executed

Backend CPython 3.13.18; installed Counterdex 0.3.0 on CPython 3.11.17, source digest
`90b42ae505c9a7c25103331f447edc2e15026d291374f6beefd0ef89c23b7bf8`.

- Full backend: 760 passed, including 28 actual-app session/privacy cases.
- Existing independent HTTP/invariant suite: 47 passed under its egress guard.
  These are GPT1 executions of the retained independent tests, not a new
  Claude-authored acceptance verdict.
- Engine: 292 cases, 290 passed and two declared conditional skips. Fresh native
  bundle replay reports valid verification, matching external anchors and passed
  replay. Backend coverage exercises the installed qualified engine separately.
- Web: 54 passed. Launcher/sharing: 45 passed. The pre-existing Popen fixture emits
  a ResourceWarning before the owned test child is stopped; it is not an orphan.
- Ruff, schema export with no generated-contract drift, whitespace and tracked
  secret scan passed. Installed google-genai emits two dependency SyntaxWarnings.
- Existing actual browser/science runner passed for both hypothetical and declared
  actual follow-up origins, using synthetic data in both. Each includes real
  baseline discovery, changed measurements, positive and no-separation design,
  candidate-specific follow-up, five native replays, preserved history, and zero
  provider attempts. The declaration test is not a real measurement.
- New `node tests/integration/shared-session-browser.mjs`: 12/12 passed. Two real
  Chromium contexts use actual TLS, the actual gateway, static server and API.
  Checked cookie flags/HttpOnly, private lists/reads/mutations, owner-header
  rejection, reload/new-tab reopen, API restart and rotated-cookie replay. The
  test invokes the shipped bootstrap module explicitly; automatic application
  hook/general-file acceptance remains separate. No provider or API outbound
  attempts; a strict local CONNECT proxy rejects background browser networking.
- A separate read-only subagent reviewed session/gateway/process changes and
  independently reran four shutdown/navigation predicates. This is internal
  review, not Claude's independent product evaluation.

Useful reproduction commands after preparing `.venv` and `.venv-engine`:

```sh
BEAN_AI_MODE=placeholder BEAN_COUNTERDEX_PYTHON="$PWD/.venv-engine/bin/python" \
  PATH="$PWD/.venv-engine/bin:$PATH" .venv/bin/python -m pytest -q tests --ignore=tests/integration
DRBEAN_SCIENCE_PYTHON="$PWD/.venv-engine/bin/python" .venv/bin/python -m pytest -q tests/integration
.venv-engine/bin/python -m unittest discover -s packages/groundwork_adapter/tests
node --test apps/web/*.test.mjs
python3 -m unittest scripts/dev/test_launcher.py scripts/dev/test_share.py
node tests/integration/shared-session-browser.mjs
BEAN_TEST_PYTHON="$PWD/.venv/bin/python" BEAN_COUNTERDEX_PYTHON="$PWD/.venv-engine/bin/python" \
  PLAYWRIGHT_MODULE="$PWD/tests/integration/node_modules/playwright/index.js" node apps/web/check-backend.mjs
BEAN_TEST_PYTHON="$PWD/.venv/bin/python" BEAN_COUNTERDEX_PYTHON="$PWD/.venv-engine/bin/python" \
  PLAYWRIGHT_MODULE="$PWD/tests/integration/node_modules/playwright/index.js" \
  BEAN_TEST_FOLLOWUP_ORIGIN=actual node apps/web/check-backend.mjs
```

### Remaining integration and deployment gates

Initial CI run `43592198368` passed web, engine, harness and actual-stack jobs.
Its manual browser lane passed 16/17: the expected local shared-session 404 was
counted as a console error. The precise test correction was handed to the UI
owner, preserving failures for unrelated errors. Final candidate CI is required.

UI controller `00d7ef3` was reviewed, not merged: exact upload retry identity,
workspace restoration/pending history, returned analysis identity and inferred
MIME forwarding needed corrections. Reproductions and requested changes are in
PR #38; the owner retains implementation responsibility. Its application/session
hook and actual combined browser acceptance are still pending at this checkpoint.
Claude's current `codex/general-gemini-files` branch/PR and concrete registration
helper are not yet published. Old PRs #35/#36 do not substitute for that work.

No public tunnel, live model smoke or final combined-release qualification has
run. The existing owner's API/web processes and real store remain untouched.
A read-only aggregate ledger check confirms five attempts, 59,432 input and
11,264 output tokens reserved/observed, leaving three requests but only 4,568 input
and 4,736 output tokens under the existing live caps. This is application
accounting, not provider quota or billing verification. No credential was read.

Rollout must use the existing state directory for every launcher/share command:
set `DRBEAN_VAR_DIR` to that directory before stop/recover/start/share/status.
Keep the SQLite database/WAL, source and artifact directories, auth file and
private opt-in file together. Never combine a fresh ledger with the owner's key.
Prepare the new runtimes separately, back up the consistent stopped state, start
the reviewed new code against the same directory, then verify ledger counts and
private browser behavior before public activation. The normal launcher may read
the private opt-in file internally for the owned API/worker; the gateway/tunnel
never receives provider credentials. A temporary public hostname is not account
recovery or an uptime guarantee. No broader budget is granted by this work.
