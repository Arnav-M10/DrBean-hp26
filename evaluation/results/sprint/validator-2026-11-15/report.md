# Validator verdict, live sprint 2026-11-15

**Tested commit:** `0cebdd41ba2b9ab357fded27daa9319bcc748388`, tree `751d453c99dec284ddfd8408252e27deddaadc7b`.
This is GitHub's CI-tested merge of PR #73 (`75f3c2c`, backend planning schema and diagnostics) into main
`ad2483b` (PR #70 classic UI, PR #71 integration handoff, PR #72). GitHub records all 8 CI jobs as passed on this exact commit. It is
preserved as branch `claude/validator-candidate-0cebdd4`, and its tree equals a local merge. Application
files matched the commit exactly. The harness overlay (`evaluation/live/live_research_browser.mjs`,
`evaluation/live/operator_grant.py`) was byte-identical to `claude/sprint-validator` at `91fe72b`.

## Verdict

- **May merge:** PR #73, as long as the resulting main tree equals `751d453c99dec284ddfd8408252e27deddaadc7b`.
  Otherwise retest. Every offline check passed on this commit, and the live workflow completed on it.
- **May be demonstrated:** the classic live flow on this commit, described as "one live run completed with
  4 Gemini requests": consent, a plan, a pause for approval, an approved Counterdex check, and a report
  with validated commentary. Fix finding 1 first, or the audience will see "The last step stopped
  unexpectedly" during every model call. The controlled mode remains the dependable demonstration.
- **Not established:** a fully qualified autonomous release. L6 did not occur live. L7 is incomplete,
  because the validator did not freshly replay this run's downloaded native file.

## Live run: one run, no retry

- **Physical requests: 4** of a single grant of 8 (receipt `validator-sprint-2026-11-15`, ceiling 36).
  The sprint ledger went from 15 to 19 actual requests and from 28 to 36 effective grants. The 4 unused
  requests cannot be reused, and no further live run is authorized.
- 06:06:13Z to 06:06:20Z: consent (06:06:13.055Z), requests 1 and 2, a pause on the plan review with no
  scientific child, browser approval, requests 3 and 4, completed.
- Tokens: 11,772 input and 408 output reported. 43,242 input and 2,048 output reserved, against an
  allocation of 64,000 and 4,096.

| # | Predicate | Result | Evidence |
|---|---|---|---|
| L1 | Real Gemini drives the Deep Agents flow | passed | 4 live `gemini-3.5-flash-lite` attempts drove `write_todos`, `prepare_scientific_proposal`, `run_scientific_operation` and `publish_research_report` |
| L2 | Consent before dispatch | passed | Consent saved at 06:06:13.055Z; zero attempts before it; first attempt at 06:06:13.758Z; every attempt carries the consent id |
| L3 | Pause for scope approval | passed | First advance ended in `waiting_review` on a plan review with no child; Approve stayed disabled until the scope box was ticked |
| L4 | Approval triggers Counterdex | passed | Approved child completed with `certified_counterexample`; native artifact `872045c1…` (57,700 bytes) is bound to `approval_2127…`; the application's native replay passed |
| L5 | Agent reads evidence and acts | passed | `evidence_observed` after the child, then a canonical report whose commentary is validated and bound to the evidence; next action `stop` |
| L6 | Results survive a commentary failure | not exercised live | Commentary was validated; offline O4 tests passed on this commit |
| L7 | Reload and fresh replay | incomplete | Reload kept the same session, state, revision and reports. The validator's fresh replay of this run's downloaded native file was not run (finding 2) |
| L8 | Accounting | passed | 4 of 8; all attempts settled `completed`; retry policy `none`; accounting valid |

## Scientific and replay results

- `certified_counterexample` against the claim ke ∈ [0.10, 0.17] h⁻¹ on the public synthetic readings.
  The witness ke = 101/1016 ≈ 0.0994 h⁻¹ fits all five readings within ±0.5 mg/L. The contrast curve
  ke = 1631/12700 ≈ 0.1284 h⁻¹, inside the claim, also fits.
- The application's native replay at evidence time reported integrity passed, replay passed, verification
  valid and binding matches.
- An independent check outside the application recomputed both curves at all five times with 60-digit
  arithmetic. Every value lies within ±0.5 of its reading and inside the checker's own rational interval.
- The validator's fresh `counterdex replay-native` of this run's downloaded file: **not run** (finding 2).

## Findings

1. **P1, classic UI, live only.** While any model request is in flight, the panel shows "Recover the
   interrupted step. The last step stopped unexpectedly…" and "The backend has not authorized
   reconciliation…", and it disables actions. `apps/api/bean_api/research_projection.py:57` sets
   `interaction.recovery.required` whenever an attempt is unresolved, which includes a request still in
   flight. `apps/web/research.mjs:351` then renders the recovery branch for a `running` session. Controlled
   mode makes no provider attempts, so the controlled browser checks cannot show this. Suggested fix: render
   that branch only outside the active states (`queued`, `running`, `waiting_child`), or exclude the running
   action's in-flight attempt in the backend. Owners: Codex 2 and Codex 3.
2. **P2, validator harness, fixed after the run.** The harness ended its wait on that panel text and captured
   the session as `running` before the report existed. It therefore skipped the report and native downloads
   and the fresh replay, and it deleted the run's blob directory when it finished. The settled state was read
   back from the retained isolated store (`live-0cebdd4/retained-store-readback.json`). Fixed in `25e7a20`:
   waits now settle on server state, and the reload check counts the report button on its hidden page. The
   fix has had a dry run only; it has not run live.
3. **P2, test flake.** `test_concurrent_additive_migration_preserves_legacy_metadata` failed once with
   `database is locked` under full-suite load on macOS, on #73's head. It passed 5 of 5 times alone and in
   this commit's full run. `store.py` is unchanged by #70 and #73.
4. **Observation.** The commentary is minimal ("The evidence has a conditional scope."). The agent stopped
   instead of proposing the next measurement the question asked for. The pair design is still available
   through "Plan next step for separate review".

## Offline checks on the exact commit (0 provider requests)

| Check | Result |
|---|---|
| O1–O4 focused tests plus #73's new tests | 129 passed |
| Full backend (`tests`, no integration) | 1649 passed in 198.8 s |
| Web, study and preview unit suites | 166 passed |
| Controlled classic browser check (`apps/web/check-research.mjs`) | passed: 2 Counterdex children, native downloads freshly replayed, no egress |
| Live harness dry run | 0 requests, passed |
| Strict offline release gate | **not run**: `scripts/release/stack_smoke.py` needs ports 8000 and 4173, which the user's running app holds |

## Remaining limitations

- The evidence is a single live run. The live commentary-failure path and the fresh replay of a live
  artifact remain unverified on this commit.
- Input headroom is limited. Four requests reserved 43,242 of the 64,000 per-session input tokens. A run
  that also asks for the pair design can reach that cap; PR #73's fixture reserves 63,875 for six requests.
- The engine version is recorded only inside the native file, which was not retained.
- The automatic Vercel deployment status was reported as failed by Codex 1 and Codex 2. The validator did
  not examine it.

## Evidence

- `checklist.md`: predicates written before any candidate was seen
- `live-0cebdd4/record.json`, `harness-console.log`: the harness record, including the premature snapshot
- `live-0cebdd4/retained-store-readback.json`, `research-report.retained.json`: the settled state
- `live-0cebdd4/independent-witness-check.txt`, `predicates.json`: the independent check and the final scoring
- `offline-0cebdd4/offline.json`, `controlled-browser-receipt.json`: the offline results
- `../live-budget.json`: the receipt, grant, actual use and run summary
