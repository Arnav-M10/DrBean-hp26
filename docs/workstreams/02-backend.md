# Backend milestone progress

Current task: master §2.13 milestone 7 — worker-loss cleanup and restart
reconciliation implemented and verified. Integration handoff is ready; remaining
full-section acceptance depends on the workstreams listed below.

Branch: `backend/restart-recovery`; stacked on PR #13 at `731afdc`.
PR #13 remains open; `main` is `80f95a4`.
Linux, backend Python 3.12.14, scientific CPython 3.11.18.
Interfaces: DB-SC-1 / GF-2, `counterdex.bridge.v1`,
`DB-SC-1-to-groundwork-v1`, `counterdex.application-bundle.v1`.
Zero model-provider calls or credential checks; live dispatch remains disabled.

## Milestone status

| Master §2.13 | State |
| --- | --- |
| 1. Runtime and real adapter | Verified on Linux; Mac qualification not run |
| 2. Admission and actual baseline HTTP | Complete, merged PR #6 |
| 3. Native storage/download/replay | Complete for supported operations |
| 4. Source review and immutable objective/optional scope | Implemented; regression covered |
| 5. Design and follow-up | Design PR #9 and hypothetical follow-up PR #11 merged; actual readings blocked on engine |
| 6. Controlled callbacks and accounting | Backend implemented; real-science controlled acceptance passed; full independent sign-off pending |
| 7. Release stabilization and handoff | Backend restart work verified; full release qualification remains dependency-bound |

## Verified in this change

- Fixed: parent `finally` cleanup could not run after SIGKILL; a live scientific
  child survived. An independent parent-lifeline guard now stops
  the complete scientific process group without scanning unrelated processes.
- Recovery now acknowledges never-started cancelled jobs as cancelled. Started
  jobs remain interrupted; queued work is preserved. Acceptance tests kill
  an ordinary worker after actual evidence commits and independently replay the
  unchanged bytes after restart, proving no silent redispatch.
- PR #13 CI exposed Linux ESRCH during process-state reading in addition to the
  previously handled disappearing file. Both reaping errors are now covered by
  the observer regression; seven process-boundary tests pass locally.

Prior milestone 6 (PR #13), already verified:

- A valid seven-row baseline previously exceeded the coordinator's 12 KB fact
  limit. `agent-evidence.v1` now supplies exact typed facts and evidence identity
  without duplicating native replay rows; complete records/downloads stay intact.
  Oversized core facts still fail explicitly without truncating scientific facts.
- Actual restricted Deep Agents + actual Counterdex: same objective skips an
  optional comparison after an outside witness, or checks a separately reviewed
  narrower claim when no outside witness was found. Native downloads replay.
- Invalid narration/ineligible actions preserve completed scientific evidence.
  Retry, durable events/budgets, isolated controlled accounting and zero external
  connection attempts are tested. No production model activation switch added.
- Future ledger accepts only bounded integer counts, uses conservative alias and
  total accounting, retains unknown reservations, and rejects conflicting or
  unknown reconciliation. Exact retry is idempotent. Malformed historical usage
  blocks new reservations and reports `needs_review` without changing old bytes.

## Evidence

- Current full backend regression: 411 passed in 167.22s, excluding independent
  `tests/integration`. Final 16-test parent-loss/boundary suite also passes,
  including a subsequent guard-start-failure control (412 tests now collected).
- Actual restart/evidence HTTP and ordinary CLI tests: 2 passed. Queued state
  plus existing workflow tests: 31 passed. Independent code review found no
  remaining correctness blocker. Ordinary-user process-boundary check: 7 passed
  while the user owned 244 processes. Ruff and whitespace pass.
- No schema/database migration or new public route. No engine, browser,
  independent evaluator or Owner 3 source changes. The child guard adds one
  short-lived supervised process within the existing resource policy.

Prior milestone 6 evidence (PR #13):

- Full backend regression: 397 passed in 140.46s (`tests --ignore=tests/integration`).
- New actual-science controlled HTTP suite: 4 passed. Fact projection: 3 passed.
  Ledger suite: 23 passed; existing provider/coordinator/worker compatibility: 28 passed.
- Independent `tests/integration/test_ai_boundaries.py`: 28 passed, 2 existing
  expected failures (Owner 3 coordinator-only optional completion/provider label).
  Backend accounting and controlled-ledger guards pass; no oracle was weakened.
- 29 browser unit tests passed. Ruff, whitespace and independent code review pass.
  No schemas or database migrations changed. Prior milestone checks remain
  historical evidence; this change does not claim a new browser follow-up flow.
- Run: `BEAN_COUNTERDEX_PYTHON=/path/to/python3.11 BEAN_COUNTERDEX_REPLAY_PYTHON=/path/to/python3.11 .venv/bin/python -m pytest -q tests --ignore=tests/integration`.
  Independent controlled check: `.venv/bin/python -m pytest -q tests/integration/test_ai_boundaries.py`.
  See `shared/contracts/BACKEND_INTEGRATION.md` for the executable HTTP handoff.

## Remaining dependencies and estimate

- Owner 1: extend `native_packet.validate_followup` and bridge review/replay for
  truthful actual observations, changed sampling time/allowance or repeated
  readings. Current native follow-up admits one hypothetical row at the checked
  selected time/allowance; backend never relabels actual observations to fit.
- Owner 4: browser follow-up controls and prepared runtime in evaluator CI via
  `DRBEAN_SCIENCE_PYTHON`. Backend process-observer reaping race was fixed in PR #11.
- Owner 5: application-bundle classifier, `replay-native` and eight anchors;
  permission-consistent design expectations; zombie-aware orphan checks; fresh
  full HTTP/recovery qualification. Owner 3 retains the two coordinator-only
  findings above. No files owned by those workstreams were edited here.
- Next backend action: integrate admitted actual-reading changes when supplied,
  resolve any backend defects from independent acceptance, and finish release
  qualification/handoff. Merged code alone does not establish release readiness.
- Available restart slice is finished. No additional unblocked backend feature
  was identified in this audit; resume when producer changes or independent
  acceptance findings arrive. The 30–60 minute estimate covered this slice, not
  waiting on Owners 1/3/4/5. Full-section calendar sign-off remains dependency-bound.
