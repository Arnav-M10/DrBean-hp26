# Release runbook

Run these commands from the repository root. Executed qualification belongs to the commit and environment named in retained release evidence; the commands alone are not a passing gate. AI stays in placeholder mode, with zero model-provider calls.

## Tested versions

| Component | Version |
|---|---|
| OS and architecture | Linux CI and Darwin 25.5 arm64. Clean Mac candidate 366dfe1 passed strict offline qualification; retained report names exact environment. Presentation-device rehearsal is separate. |
| uv | 0.11.32 |
| Backend runtime `.venv` | CI uses Python 3.13; Mac qualification uses Python 3.12.13. Locked dependencies: fastapi 0.141.1, uvicorn 0.52.1, pydantic 2.13.4, deepagents 0.7.38, langchain 1.5.0, langchain-google-genai 4.5.0, google-genai 3.3.0 (from `uv.lock`) |
| Engine runtime `.venv-engine` | Qualified CPython 3.11; current Counterdex 0.3.0, no dependencies. Doctor reports the installed patch version. |
| Node | CI 22; Mac qualification 25.9.0 |
| Playwright (tests only) | 1.63.0 |

## Setup

```sh
scripts/dev/setup.sh
```

Needs uv and Node. Installs the backend from `uv.lock`, creates the CPython 3.11 engine environment and installs Counterdex into it, creates `var/auth.json` if absent, then prints the doctor report. Safe to rerun. It never deletes or resets `var/`. If a step fails it says which, changes nothing in `var/`, and exits nonzero.

## Start, check, stop

```sh
scripts/dev/start.sh --controlled-source-examples
```

```sh
scripts/dev/doctor.py
```

```sh
python3 scripts/dev/launcher.py status
```

```sh
scripts/dev/stop.sh
```

| Fact | Where |
|---|---|
| Web workspace | `http://127.0.0.1:4173` |
| API and docs | `http://127.0.0.1:8000`, `/docs`, `/api/bean/v1/capabilities` |
| Store (one, authoritative) | `var/bean.sqlite3`, sources in `var/sources/`, native artifacts in `var/artifacts/` |
| Bearer token | private file `var/auth.json`; paste it into the web connection panel or the docs page's Authorize control |
| Logs and pid records | `var/run/*.log`, `var/run/*.json` |
| Binding | loopback only; no hosted boundary exists |

The launcher starts each process in its own session and records its pid and start time. Stop signals only those process groups and only if the recorded start time still matches, so a reused pid or another project is never touched. It does not use `pkill`.

## Recovery

| Symptom | Action |
|---|---|
| "Port(s) [...] are in use by a process this launcher did not start" | Nothing was started or killed. Find the process yourself (`lsof -i :8000`), stop it, start again. |
| Start fails | The launcher prints the last log lines and stops what it started. Read `var/run/api.log` or `worker.log`. |
| Worker reports another worker holds the lock | An older worker is still running on this store. Stop it, then recover. |
| Machine or process died during a run | `scripts/dev/stop.sh`, then `python3 scripts/dev/launcher.py recover`, then start. Interrupted work is marked interrupted. Nothing is rerun, no approval is reused, completed evidence is unchanged. |
| Lost the token | It is in `var/auth.json`. Deleting that file and rerunning setup creates a new identity and orphans access to nothing but your own session; do not delete the database. |
| Want a clean trial without touching real data | `DRBEAN_VAR_DIR=/some/empty/dir scripts/dev/setup.sh`, then the same variable for start and stop. |

Backup: stop the stack and preserve `var/bean.sqlite3`, `var/sources/`, `var/artifacts/` and the private local identity together. Never point the stack at an empty store while presenting earlier approvals.

## Checks

```sh
python3 scripts/release/checklist.py --record
```

Inventory: runs backend tests, lint and schema export, engine tests and native replay, web tests, both browser checks, the stack smoke, the harness self-checks and the secret scan. Writes `docs/release-evidence/release-checklist.json`. Exit 0 means no check failed; it does not mean release-ready.

```sh
python3 scripts/release/checklist.py --strict-offline
```

The offline release gate. Nonzero unless G0 to G4 all have passing evidence. Missing evidence fails. Live Gemini checks are listed as intentionally unrun and do not block.

```sh
scripts/release/clean_checkout.sh --strict-offline
```

The same from a clean clone of committed HEAD, with freshly installed runtimes and its own empty store. Inherited Python import paths, active virtual environments and backend/science runtime overrides are cleared. The launcher explicitly resolves this checkout's application source, including when a filesystem hides editable-install `.pth` files.

The clone installs the browser test dependencies with `npm ci` from
`tests/integration/package-lock.json` (Playwright **1.63.0**) using a public
registry and isolated npm configuration/cache. It installs the matching
Playwright Chromium unless an executable browser is explicitly selected:

```sh
CHROMIUM_PATH=/absolute/path/to/chromium scripts/release/clean_checkout.sh --strict-offline
```

That browser binary is a declared external dependency; record its version with
the check results. Focused local browser checks also accept `PLAYWRIGHT_MODULE`
and `CHROMIUM_PATH`, but an independently selected Playwright version does not
qualify the locked clean-checkout environment. The clean check clears that module
override and uses its own pinned installation. Source-review and follow-up
browser controls remain explicit unrun G4 requirements; strict mode keeps failing
until their real acceptance checks exist.

```sh
python3 scripts/release/stack_smoke.py --require-science
```

The single command baseline discovery must make pass (gate G1). Without `--require-science` it qualifies only the launch path.

Add `--fast` to the checklist to skip checks that need ports 8000 and 4173. Stop a running stack before the full checklist: the smoke refuses to share ports and never stops your processes.

For browser checks in an existing checkout, run `npm ci --ignore-scripts --no-audit --no-fund` in `tests/integration`, then `node node_modules/playwright/cli.js install chromium`, or explicitly supply `CHROMIUM_PATH`. Without the package they report unrun.

## Native replay (engine CLI)

```sh
.venv-engine/bin/python -m counterdex replay packages/groundwork_adapter/fixtures/checked_success.bundle.json --anchors packages/groundwork_adapter/fixtures/checked_success.anchors.json
```

This replays the standalone prepared fixture against its separate anchors. Actual application baseline, design and follow-up downloads use `counterdex.application-bundle.v1` and their complete eight-field authenticated anchor record:

```sh
.venv-engine/bin/python -I -m counterdex replay-native downloaded.native.json --anchors downloaded.anchors.json
```

The packet and expected anchors must come from the same approved run. Fresh replay checks the recorded fixed-vector facts and lineage; it does not rerun discovery or establish physical truth. Browser replay remains unsupported.

## AI mode

Placeholder. The launcher, stack smoke, browser check, clean checkout and CI all remove provider and tracing variables from child processes and set `BEAN_AI_MODE=placeholder`. Doctor shows **Gemini live: disabled, not tested**, and raises an alert if a running API ever reports a configured provider.

Deferred until the user gives a new explicit instruction, and not to be run now: opening a provider cohort (`evaluation/cli.py budget open`), any live intake or agent lane, any account or key validation, and any Gemini-driven design invocation. The chosen design path is deterministic and separately approved. When live testing is authorized, issues I-004 and I-012 must be closed first.

## CI

`.github/workflows/ci.yml`: backend tests, lint and schema drift; engine tests and native replay on CPython 3.11; web unit tests; harness self-checks and secret scan; the provider-free stack smoke; Owner 5's suite when present. No model secrets. A green run is not a release qualification and not a live qualification.

## Not attempted

| Item | Status |
|---|---|
| Live Gemini of any kind | not run, disabled |
| Target Mac qualification | not run |
| Hosted deployment (Vultr or other) | not attempted; loopback only |
| PDF intake, Tiger Data, MongoDB, Solana, Photon, AWS | omitted |
| Browser replay | unsupported |

## Final six hours (from Sunday 02:00 Eastern)

No new features or integrations. Fix only launch failures, incorrect scientific claims, approval or binding defects, blocked user steps and submission issues. Rehearse on the presentation device with model APIs unreachable. Keep a saved real-science fallback, labelled as saved, plus the recovery commands above. Tag the last commit whose clean-checkout run passed.

## Retain clean-checkout qualification

Set an absolute evidence directory outside the disposable clone:

```sh
DRBEAN_RELEASE_EVIDENCE_DIR=/absolute/path/to/release-evidence \
  scripts/release/clean_checkout.sh --strict-offline
```

The command installs locked dependencies in a fresh clone, runs the offline gates with isolated state, and copies a timestamped report for the exact tested commit before cleanup, including on gate failure. Existing historical reports are not rewritten. Inspect `offline_release_ready`, individual checks, platform facts and tested commit together. A source fixture is controlled intake output; the science and replay checks execute the actual engine. The release verdict does not qualify live Gemini or substitute for a human consultation, observed task, or presentation rehearsal.

The source-example option configures only the packaged trusted local manifest. The web action uses the ordinary intake route; unsupported images offer manual entry. Omit the flag to keep source proposals disabled. No hosted provider is enabled.
