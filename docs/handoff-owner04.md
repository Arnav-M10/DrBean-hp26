# Workstream 4 operational handoff

Current handoff for the integrated tree. The pre-merge handoff (when only the web editor existed) is summarized at the end as dated history.

## Runnable commit and command

Branch `claude/dreamy-lamport-dsttgm`, merged with default branch `main` at `adac945` (includes PR #3, the backend scientific integration, and PR #4, engine discovery). After `scripts/dev/setup.sh`:

```sh
scripts/dev/start.sh
```

## Gate status

No gate fully passes. G0 holds for root only: for an ordinary user every approved run fails ([I-018](issue-ledger.md)). See [INTEGRATION_STATUS.md](INTEGRATION_STATUS.md). The one blocker for G1 and G2 is baseline discovery through the application, [issue I-013](issue-ledger.md): the engine can now discover candidates, but the backend does not call that operation yet.

## Manual demo steps that work today (placeholder AI, no science)

1. `scripts/dev/start.sh`; open `http://127.0.0.1:4173`.
2. Open **Local backend connection**, paste the token from `var/auth.json`, connect, create a workspace.
3. Click **Load synthetic example** (it is the shared five-row example), or enter it by hand: times 0.25, 0.5, 1, 2, 4 h; concentrations 4.80, 7.20, 8.00, 6.80, 5.70 mg/L; hard allowance 0.50 each.
4. Question: experiment identifier, t=0 description, origin Synthetic; A `[0.001, 30]`, ke `[0.015, 0.35]`, ka `[0.4, 8]`; target `[0.10, 0.17]`; describe the allowance origin.
5. Review, **Save inputs and prepare plan**, read the frozen plan, tick the approval box, approve.
6. Queue stays disabled in the browser (the adapter reports no qualified baseline). The same run over HTTP (see `scripts/release/stack_smoke.py`) completes with `unsupported`, reason `baseline_producer_unavailable`.
7. In Investigations, open the run id; download evidence and a report; hashes are checked.
8. `scripts/dev/stop.sh`, `scripts/dev/start.sh`, reconnect: the run and report reopen unchanged.

The domain, claim and any future times are team-selected assumptions for review, not values read from the image.

## Results by lane (Linux x86_64, this branch)

| Lane | Result |
|---|---|
| Launch path and transport boundary (stack smoke, isolated store) | 31 of 31 as root; 28 of 31 on the GitHub runner (the approved run fails, I-018) |
| Scientific boundary as an ordinary user owning 64 processes | failed: 2 of 5 tests |
| Gate G1 through the API | not passed: Counterdex adapter available, baseline discovery unavailable, outcome `unsupported` |
| Backend unit and HTTP tests (controlled AI; real engine from a seeded regression pair) | 264 passed |
| Backend lint and schema export | clean; exported schemas match committed |
| Engine tests (CPython 3.11) | 257 passed, 2 skipped |
| Engine native replay of prepared bundle | replay passed, binding matches, verification valid |
| Web unit tests | 22 passed |
| Browser to real API (`check-backend.mjs`) | passed |
| Web editor smoke | 17 of 17 passed (editor only, not science) |
| Launcher tests | 7 passed |
| Harness self-checks (Owner 5's) | 40 unit tests, manifest verifies, grader self-test passes |
| Harness product report | 34 entries unrun, recorded before the merge; retained as history |
| Owner 5 HTTP/invariant suite | not delivered |
| Provider requests, tokens, cost | 0, 0, none |
| Live Gemini | not run |
| Target Mac | not run |
| Consultation, observed task, rehearsal, recording | not done |

## Interfaces changed or proposed by this workstream

- The launcher passes the backend's own variables: `BEAN_COUNTERDEX_PYTHON` (the `.venv-engine` interpreter, never a `python3.11` from PATH), `BEAN_SCIENCE_ADAPTER`, `BEAN_ARTIFACT_DIR`. `BEAN_AI_MODE=placeholder` is informational.
- `apps/web/manual.mjs`: plans now send `scientific_profile` and a reviewed objective, required since PR #3. A blank goal still does not block: the question is then stated from the exact target interval and shown in the plan review.
- `DRBEAN_VAR_DIR` selects an isolated store for tests.
- `apps/web/check-backend.mjs`: Playwright resolution made portable; provider variables removed from the processes it starts. No behaviour change to the page.
- Release evidence now lives in `docs/release-evidence/`. `evaluation/results/` belongs to Owner 5 and was not modified.

## Future live-Gemini checks: all not run

Account, region and audience qualification; live image intake on the shared sheet; live deepagents run with real tools; live grounded explanation; real token usage, latency and cost. None may be claimed. They need a new explicit instruction from the user.

## Remaining limitations

No scientific result through the application. No source review, design or follow-up controls in the browser. No native bundle export. One platform tested. No user evidence.

## What happens next in this workstream

1. When baseline discovery lands (I-013): run `stack_smoke.py --require-science`, then connect the remaining browser controls (I-017) against real responses.
2. Mac recheck with whoever has the device (I-015).
3. Consultation and observed task: scripts are ready in `docs/human-task/`; the human team arranges the person.
4. Rehearsal and recording once there is real science to show.

## History: pre-merge handoff, 13 November (Eastern)

At commits `20dd941` to `f4786c5` the repository held only the web editor and this workstream's harness. Recorded then: 40 harness tests, 11 web tests, 14 of 14 editor smoke checks, clean-clone run passed, 34 scheduled evaluation entries unrun, 0 provider requests. Those records remain in `evaluation/results/` unchanged.
