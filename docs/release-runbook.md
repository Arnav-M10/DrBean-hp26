# Release runbook

Every command below was run on this branch. Run them from the repository root.

## Requirements

- Node 22 (tested with v22.23.4). `apps/web` has no dependencies.
- Python 3.11 or newer (tested with 3.13.18). The harness uses the standard library only.
- Optional: Playwright 1.63.0 for the browser smoke. Install with `npm install` inside `tests/integration`, then `npx playwright install chromium`. Without it the smoke reports unrun.

## Start and stop

```bash
node apps/web/serve.mjs
```

Serves the workspace on `http://127.0.0.1:4173` (pass another port as the first argument). Bound to loopback only. Stop with Ctrl-C. Drafts live in the browser tab; nothing is written to disk and nothing is sent anywhere. No configuration is read.

There is no backend to start. When Owner 02 adds one, its launch command, port, data location and configuration names go here, and `DRBEAN_API_BASE` enables the capabilities probe.

## Checks

```bash
python3 scripts/release/checklist.py --record
```

Runs the automated checks and writes `evaluation/results/release-checklist.json` for the tested commit.

```bash
scripts/release/clean_checkout.sh
```

Clones the current commit into a temporary directory, unsets provider key variables, and reruns the checks there.

```bash
python3 -m unittest discover -s evaluation/tests
```

Harness unit tests.

```bash
node tests/integration/web_manual_smoke.mjs
```

Browser smoke: invalid input, manual path, export, no external requests.

```bash
python3 scripts/release/secret_scan.py
```

Secret-shape scan of tracked files. To check exports, logs or storage dumps for the planted sentinels as well, pass paths with `--sentinels`.

## Evaluation

```bash
python3 evaluation/cli.py verify
```

```bash
python3 evaluation/cli.py run --lane fixture_contract --subject recorded:PATH_TO_OBSERVATIONS
```

```bash
python3 evaluation/cli.py report
```

```bash
python3 evaluation/cli.py admission-assets PATH_TO_EMPTY_DIRECTORY
```

Generates the negative admission files (oversize, over 12 megapixels, corrupt, wrong type) with their expected states.

Live lanes stay refused until a human opens a cohort:

```bash
python3 evaluation/cli.py budget open --cohort NAME --authorized-by "FULL NAME" --spending-note "ALLOWANCE AND TIER" --model MODEL_ID
```

Do this only after the checks in "Gemini readiness" below.

## Gemini readiness (not yet met)

Before any live request, a human confirms and records in the spending note: the account and its paid or unpaid treatment; region and adult-audience eligibility under the Gemini API terms; the pinned model id chosen from actual availability; the spending allowance. Only synthetic sheets from `evaluation/sources/` are sent. The key is configured on the backend through `GEMINI_API_KEY` (see `.env.example`), never in the browser, the repository or the harness. Health probes must not call the provider.

## Store lane

Proposed: one local SQLite store owned by Owner 02. Not implemented. Tiger Data PostgreSQL is omitted. Install, restart, race and backup-restore tests on the chosen lane are unrun. A failure of the store must never fall back silently to an empty one.

## Deployment gate (Vultr, not attempted)

Hosting is secondary and nothing was provisioned. Before any hosting claim, all of these must hold:

1. The local core passes the twelve boundaries.
2. Resource size and region chosen; credit expiry and cost ceiling recorded; a human authorizes the spend.
3. Pinned images, non-root services, TLS, authenticated mutations, bounded workers, backups.
4. Only the needed port is open. No arbitrary-code runner, no universal admin token, no unauthenticated mutation.
5. What data is exposed is listed; only synthetic material is hosted.
6. Rollback and teardown steps are written and tested.
7. A second authorized device completes the review task against the hosted instance.
8. The local fallback still works.

## Omitted integrations

| Integration | Status |
|---|---|
| PDF modality | omitted by decision (image chosen) |
| Checked pair separation | unshipped; numerical guidance is the advertised tier |
| Tiger Data PostgreSQL | omitted |
| MongoDB Atlas retrieval | omitted |
| Solana commitment | omitted |
| Vultr hosting | omitted |
| Photon messaging | omitted; disabled by default, never attempted |
| Hosted tracing | omitted; local sanitized traces only |
| AWS | not required by the Amazon Practical AI track; not used |

## Final six hours (from Sunday 02:00 Eastern)

Only correctness, broken integration, release verification, evidence integrity, documentation, video and submission readiness. No new modality, provider, database, channel or mathematical family. Do not delete a failing test or loosen a bound to make the release green. Keep a rollback tag of the last commit whose clean-checkout run passed.
