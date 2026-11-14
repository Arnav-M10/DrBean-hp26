# Workstream 4 log: product, integration and release

Standing brief: master document DB-MASTER-1, section 2. This log is a navigation aid; verify the repository before relying on it. Shared index: [issue ledger](../issue-ledger.md), [integration status](../INTEGRATION_STATUS.md).

## Current state

| Item | Value |
|---|---|
| Branch | `claude/dreamy-lamport-dsttgm` |
| Integrated base | `main` at `adac945` (PR #3 backend scientific integration, PR #4 engine discovery) |
| Platform of all fresh checks below | Linux x86_64, **run as root** unless stated (root hides per-user limits; CI is the non-root lane); uv 0.11.32; backend Python 3.13.18; engine CPython 3.11.15; Node 22.23.4 |
| AI mode | controlled placeholder; live Gemini disabled and not run; provider requests made: 0 |
| Evidence | `docs/release-evidence/release-checklist.json`, `docs/release-evidence/stack-smoke.json` (each names its commit) |

## Update after merging `main` at `1f75bdc` (PR #6)

Supersedes rows 2 to 5 and 8 of the table below. Fresh, as root: stack smoke 31/31 and G1 passed (`certified_counterexample`, 2 candidates, 1 native artifact); `user_conditions_check.py` 5/5; backend 290 passed; engine 257 passed; web 23 passed; browser check with real discovery, native and anchor download and separate-process replay passed 3 of 4 runs (one unexplained failure on the first run after the merge; watch for flakiness); editor smoke 17/17. Checklist: G0 passed; G1 to G3 wait on Workstream 5's suite; G4 waits on the design, follow-up and source-review controls, which are now this workstream's next task (I-017).

## Gate table

"Fresh" means run by this workstream on this branch. Nothing here restates a teammate's report as qualified.

| # | Delivery criterion | State | Evidence or blocker |
|---|---|---|---|
| 1 | Qualified setup | passed (Linux) | `scripts/dev/setup.sh` in a clean clone via `scripts/release/clean_checkout.sh`; target Mac not run (I-015) |
| 2 | Ordinary launch | **failed for ordinary users** | as root: stack smoke 31/31. As a non-root user (GitHub runner, and `user_conditions_check.py` locally) the approved run fails: I-018, Owner 2 |
| 3 | Real baseline over HTTP | **blocked** | backend does not call the engine's discovery bridge; baseline returns `unsupported` (I-013, Owner 2) |
| 4 | Separately approved design | blocked by 3 | no discovered candidates to design on; backend tests cover it from a seeded regression pair only |
| 5 | Raw native export and replay | blocked by 3 | engine CLI replays its prepared bundle; no application run has produced native bytes |
| 6 | Follow-up lineage | blocked by 3 | backend-tested; not exercised through ordinary startup by this workstream |
| 7 | Controlled AI integration | partial | backend tests (author-run and fresh: 264 pass); zero provider attempts in the launched stack; Owner 5's dispatch guard not delivered |
| 8 | Minimal browser flow | partial | connect, save inputs, plan review, approval, run retrieval, downloads pass against the real API; source review, design, follow-up, native download not built (I-017, waits for 3) |
| 9 | Independent adverse checks | not delivered | Owner 5's `tests/integration/test_*.py` absent (I-016) |
| 10 | Reproducible release | not passed | `checklist.py --strict-offline` exits 1: gates G1 to G4 lack evidence |

## Completed criteria (this workstream)

- PROD-0: setup, start, stop, status, doctor, recover (`scripts/dev/`); two declared runtimes; owned-process tracking; port-collision refusal; partial-start cleanup; doctor reports API, worker, adapter, baseline discovery, native replay, storage, AI mode and Gemini live as separate facts.
- PROD-1: proxy shape preserved. Fresh transport checks in the stack smoke: missing and invalid credentials refused, another actor cannot read the workspace, run or report, foreign origin refused at the web proxy, duplicate start returns the same run, same key with another body conflicts, consumed approval not replayed after restart, report bytes match their declared hash and are labelled as an application report, not a native packet.
- PROD-4 (automation): `checklist.py` inventory and `--strict-offline`; evidence must match the tested commit; `clean_checkout.sh` with declared runtimes and its own store; CI workflow without model secrets (not yet observed running on GitHub).
- Web client hardening (PROD-1): responses size-bounded and strictly parsed; a lost mutation answer is reported as uncertain and a retry reuses the same operation key; refusals carry code, fields and current revision; queueing follows `science.available` and `baseline_discovery` and shows the server's reason (I-019 open for Owner 2's confirmation).
- Web editor (PROD-2 items allowed before the science gate): empty rows reported with their repair and removable; imported rows kept and excluded instead; row-count and spelling limits match the server; the built-in example is the shared five-row example; long exact values wrap; visible focus outline.
- Web maintenance after contract changes: plans send `scientific_profile` and a reviewed objective; browser check made portable and placeholder-safe.
- Documents: README, runbook, handoff, ownership, issue ledger, integration status, demo script, submission claim table, consultation protocol.

## Commands and results (fresh, this branch)

| Command | Result |
|---|---|
| `scripts/dev/setup.sh` | both runtimes installed; doctor ready |
| `python3 scripts/release/stack_smoke.py` | launch path 31/31; G1 not passed (`baseline_producer_unavailable`) |
| `.venv/bin/python -m pytest -q tests --ignore=tests/integration` | 264 passed |
| `.venv-engine/bin/python -m unittest discover -s packages/groundwork_adapter/tests` | 257 passed, 2 skipped |
| `node --test` in `apps/web` | 22 passed |
| `node apps/web/check-backend.mjs` | passed (honest unsupported lifecycle; not a science success) |
| `node tests/integration/web_manual_smoke.mjs` | 17/17 (editor only) |
| `python3 -m unittest scripts/dev/test_launcher.py` | 7 passed |
| `python3 scripts/release/checklist.py --strict-offline` | exit 1, as it should |
| `python3 scripts/release/user_conditions_check.py` | **failed**: 2 of 5 boundary tests fail as an unprivileged user owning 64 processes (passes at 30, fails at 34) |
| GitHub Actions `ci` on this branch | runs 1 and 2 green (before PR #3); runs 3 to 6 red from I-018. Run 6 (`58a2b1e`): ordinary-user check fails on the runner exactly as locally (uid 1001, 64 processes, 2 of 5); backend job with the real engine runtime: 4 failed, 247 passed, 13 skipped |

## Blockers and who holds them

0. **I-018, Owner 2: scientific jobs fail for any non-root user.** Found by reading CI, reproduced with `scripts/release/user_conditions_check.py`. Fix before anything else: it stops the demo on a laptop.
1. I-013, Owner 2: adopt the engine's discovery bridge in the worker. Interface request with reproduction and acceptance command is in the issue ledger.
2. I-016, Owner 5: HTTP/invariant suite and model-dispatch guard.
3. I-015, whoever has the target Mac: run setup and the checklist there.
4. Human team: consultation (script ready), names and Discord usernames, reuse ruling.

## Next three eligible actions

1. When I-013 closes: `python3 scripts/release/stack_smoke.py --require-science`; extend the smoke through design, native download, engine replay and a hypothetical follow-up using real returned identities.
2. Then PROD-2 browser controls against real responses, in this order: result table with separate states, design review and separate approval, follow-up with actual/hypothetical origin, native download with the replay command, source review with placeholder label.
3. Until then, independent of other owners: read each CI run (it is the only non-root lane this workstream has); keep the smoke and browser checks passing after each merge of `main`; rerun `user_conditions_check.py` as soon as Owner 2 changes the process guard.

## Deferred, not to be started without a new instruction

Live Gemini of any kind; hosted deployment; Photon; visual redesign; additional sponsor services.

## History

- 13 Nov (Eastern), `20dd941`..`f4786c5`: harness, sources, first release checks; repository held only the web editor. Evaluation ownership later moved to Workstream 5.
- `3b456b1`..`06c6518`: launcher, strict gate, stack smoke, CI, docs on the integrated tree.
- `cb8aef8`..`849f516`: merged PR #3; fixed launcher and web plan request for the new contract.
- CI review: found I-018; added the ordinary-user check to the gates and CI; test suites in the checklist no longer inherit paths to the real `var/` store.
- Earlier update: merged PR #4; transport checks; storage and AI-mode doctor facts; role log; master-document alignment.
