# Workstream 4 log: product, integration and release

Current checkpoint: PR #27 supplies ordinary controlled source intake and direct follow-up navigation for both origins. Clean checkout c4d1ad6, tree-identical to published 31a8ed3, passed all 5 offline gates and 12 boundaries; all six CI jobs passed. The sections below preserve chronological observations; earlier unavailable states are historical. Human consultation, observed task and device rehearsal remain pending.


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

## Codex launcher recovery contribution

Base `9cc90e0`, branch `codex/product-launch-recovery`, macOS, launcher Python 3.14. Partial service spawn exceptions now trigger cleanup. Missing process start timestamps no longer establish ownership. Six focused environment, doctor and regression checks pass, and `git diff --check` passes. Full launcher suite could not qualify this environment: sandbox denies `ps`, and the repeated socket connection assertion failed. No full-stack or release qualification is claimed. Next actions: run launcher checks in an environment allowing process inspection, qualify ordinary Mac startup, then resume the existing browser integration backlog. Gemini remains disabled.


## Release-check maintenance after main `80f95a4`

Merged the current integrated backend/design browser work into the contribution branch. Preserve the separately approved design UI and native download implementation. Corrected checklist Playwright resolution and explicit evaluation science interpreter selection. Editor smoke cleanup now covers Chromium launch failure. Updated integration summary to retire the obsolete claim that the HTTP suite is undelivered.

Fresh checks on macOS with Node 25.9.0: 29 web unit tests pass, smoke JavaScript syntax passes, release environment assertions pass, and diff whitespace checks pass. Full browser and Mac stack execution remain unverified. `uv` is absent from PATH. PR #12 CI previously passed launcher tests, backend lint/tests/schemas, web, engine/replay and harness checks; corrected HTTP runtime selection reached 40 passed, 3 failed, 2 xfailed. Remaining failures concern native evidence/design tier, follow-up results/lineage and interruption observations, plus the separate descendant process-boundary check.

Next eligible tasks: implement source-review and follow-up browser controls against current contracts; qualify installed browser dependencies and target Mac setup; reconcile independent failures and rerun strict offline release. Human consultation and rehearsal remain pending.

## Follow-up result presentation

Added candidate-specific feedback when reopening a native review run through the existing run lookup. Displays recorded observation origin, compatible/excluded/unresolved status, violating observation IDs and reason. Explanation distinguishes a checked pair review from baseline discovery and preserves uncertainty when replay or binding fails. New regression plus existing web tests: 30 pass. JavaScript syntax and diff checks pass. Full browser/API exercise remains pending. Follow-up entry and source-review controls remain unfinished.

## Browser CI checkpoint

Base `4b5f1f5`. Added a dedicated browser job using the existing pinned integration lockfile, Node 22, declared backend/engine setup and Playwright Chromium. Runs both the manual editor smoke and actual browser/API/science/design/native-replay check. No new evaluator or provider integration. Acceptance requires the new job and existing CI jobs to pass on this contribution. Source-review and follow-up entry remain separate pending controls.

## Hypothetical follow-up browser checkpoint

Added a browser path from a checked design to an explicitly hypothetical observation, reviewed dataset revision, new fixed-pair plan, separate approval and queued run. Existing run lookup renders candidate feedback and downloads. Extended the real browser CI check through this path and checks preserved design identity. Thirty existing web tests pass locally; full browser qualification is delegated to the existing clean CI job. Actual acquisition and off-design readings remain unsupported by this flow.


## 2026-11-14 — source review integration

PR #27 adds retained-source inspection and explicit controlled proposal review, correction, assumption preview and accepted input materialization. Upload selections survive action rendering; changed drafts require a new source-bound preview. The real local browser/API/worker check passed on the target Mac environment with prepared interpreters and Chromium, including real discovery, separately approved positive/no-separation design, hypothetical follow-up and native replay. All 31 web unit tests passed.

Release automation now consumes that actual browser outcome for source and follow-up gates (fast mode remains unrun). Independent clean-checkout qualification is next. Declared actual acquisition controls are implemented; qualification follows. Consultation, observed task and device rehearsal are explicitly not performed; software comes first per user direction.


Clean checkout 366dfe1 passed strict offline qualification on Darwin 25.5 arm64: 5/5 gates, 12/12 boundaries, 588 backend tests, 47 HTTP tests, 31/31 launch checks and real-science counterexample with 2 candidates and native artifact. Retained immutable report: docs/release-evidence/offline-366dfe1-macos.json. All six CI jobs passed for equivalent published integration tree 6a3705a.

The next extension adds declared actual follow-up with separately entered acquisition time, hard allowance and provenance. Tests use synthetic data and do not claim real observation. Dataset origin is labeled as such and preserves synthetic ancestry. Superseded observation parents are still rejected by the server; pending proposals can be revised before acceptance.


## Ordinary source and follow-up completion

User requested a usable loop without scripts/database manipulation/hidden identifiers. Consumed Owner 2's SOURCE_HANDOFF.md and source branch through 42f92b1; controlled proposer remains Owner 3's implementation. PR #27 published code 31a8ed3 has the same tree as local c4d1ad6. Removed the release DB producer and proposal-ID input. Added visible packaged-example/request actions, controlled/unavailable labels, explicit reviewed-row transfer, and direct queued follow-up navigation with execution polling. Preserved stale preview rejection and separate approval.

Expanded browser tests exercise ordinary source POST, original/corrected values, changed-byte manual fallback, stale local preview refusal, real discovery on changed inputs, positive/no-separation designs, both follow-up origins and native downloads/fresh replay. Launcher option --controlled-source-examples explicitly configures only the packaged manifest; stack smoke exercises that start/restart path. No independent evaluator assertions were changed.

Fresh combined strict clean checkout and CI are running. Earlier reports remain named for their original commits. Next actions: retain fresh candidate results, supply exact qualification commands to Claude, and complete authorized integration once the checks pass. Human research and rehearsal remain explicitly pending.

Final combined qualification: c4d1ad6 / published 31a8ed3, all 5 gates and 12 boundaries passed. Full immutable report and code/tree mapping are in docs/release-evidence/offline-c4d1ad6-macos.json and product-candidate.json. Exact commands for Claude are in product-qualification-handoff.md. Only evidence/docs change after this code candidate; independent acceptance, consultation, observed task and device rehearsal remain pending.
