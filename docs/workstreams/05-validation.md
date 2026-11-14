# Workstream 5 — validation log (owner: Claude adversarial validation)

Durable resumption record required by the master brief (DB-MASTER-1 §2.22). Raw evidence and machine-readable findings live in `evaluation/`; this log links them and is not a second status source.

## Current position

| Item | Value |
|---|---|
| Branch | `claude/adversarial-validation` (pushed); PR #8 merged it into `main` up to `4ea7cb3`; `main` `9cc90e0` merged back as `7be805a` |
| Integration branch | `main` (GitHub default since the PR #3/#4 merges) |
| Last recorded lane run | harness `8bb1fbe` against merged `main` `9cc90e0` (acceptance: science fails on this Mac, F-MAC-NPROC; diagnostic: `evaluation/results/previews/main-8bb1fbe/`) |
| Host | macOS 26.7 arm64; backend CPython 3.13.18 (`uv sync --locked`); Counterdex/replay CPython 3.11.17 |
| AI mode | zero external model dispatch, verified by the egress guard in API, worker and pytest; live Gemini `NOT_RUN` |
| Findings | `evaluation/findings.json` → `evaluation/FINDINGS.md` (open P0: F-MAC-NPROC, F-BASELINE-DISCOVERY on main, F-NATIVE-BYTES pending retest, F-FOLLOWUP-FEEDBACK) |
| Release gate | `python3.11 evaluation/cli.py gate --require release` → failed (exit 3) |

## Gate evidence (current)

| Gate | Status | Evidence |
|---|---|---|
| G0 baseline | done | backend suite on this Mac: 265 passed / 4 failed at `adac945` (was 136/17/11 at `586fb9b`); engine 257 OK; harness 82 unit tests, manifest v2 verified, selftest 24/62 |
| G1 real manual investigation (HTTP) | **blocked on `main`** | `RS-HERO-FULL` fails: on the Mac `scientific_runtime_unavailable` (F-MAC-NPROC); on any host the baseline producer is unavailable on `main` (F-BASELINE-DISCOVERY). Image admission passes. **Preview of Owner 2's `backend/browser-baseline` cc779bf (diagnostic relax_nproc):** real discovery, certified counterexample, baseline packet download + fresh `replay-native` all pass. |
| G2 decision loop | blocked | engine-level controls 12/12. Preview: changed input, design authority, three hypothetical lineages pass; checked design blocked by F-DESIGN-SOURCE-ARTIFACTS (without source ids the same pair separates at 8 h and replays fresh); per-candidate follow-up feedback has no route (F-FOLLOWUP-FEEDBACK). |
| G3 AI-ready offline | mostly evidenced | zero-dispatch tests 7/7 incl. legacy live switch; controlled boundary 28 passed + 2 strict xfail (P2 residuals); real Worker + deepagents graph contrast and vanished-scenario refusal pass |
| G4 usable release | not started here | Owner 4 |

## Unresolved findings and owners

See `evaluation/FINDINGS.md` for input, command, expected, observed and retests.

- **Owner 2:** F-MAC-NPROC (P0, new: RLIMIT_NPROC per user on macOS blocks spawning CPython 3.11), F-BASELINE-DISCOVERY (P0, adapter wiring with Owner 1), F-NATIVE-BYTES (fixed pending HTTP retest), F-REVIEW-MATERIALIZATION (fixed pending retest), F-RESTART-UNOBSERVABLE, F-TEST-VAR-LEAK (P2).
- **Owner 1:** F-BASELINE-DISCOVERY producer side, F-FOLLOWUP-FEEDBACK (with Owner 2).
- **Owner 3:** F-COORDINATOR-OPTIONAL-STATUS, F-COORDINATOR-PROVIDER-LABEL (P2 residuals; integrated boundary passes).
- **Owner 4:** F-LINT-CHECKLIST (P2).
- Closed by retest on `main`: F-PLATFORM-RLIMIT (image part), F-ADAPTER-SELECTION, F-PLACEHOLDER-AUTO, F-PLACEHOLDER-MODE, F-OPTIONAL-VANISHES, F-CONTROLLED-PROVENANCE; harness defects H-* fixed in this workstream.

## Exposed holdouts

`evaluation/sources/h01.png`, `h04.png`: authored alongside the development sheets and visible to the merged-harness source review; not unseen. No holdout model evaluation has occurred. Future live grading needs an unexposed grader or a fresh `holdout-v2`.

## Runnable commands

```sh
python3.11 -m unittest discover -s evaluation/tests
python3.11 evaluation/cli.py verify && python3.11 evaluation/cli.py selftest
DRBEAN_BACKEND_PYTHON=$PWD/.venv/bin/python python3.11 evaluation/cli.py run --lane offline_real_science --subject http-launch
python3.11 evaluation/cli.py controls
python3.11 evaluation/cli.py gate --require release --output /tmp/drbean-gates.json   # exit 0 only when releasable
python3.11 evaluation/cli.py inventory      # same gates, informational, exit 0
.venv/bin/python -m pytest tests/integration -m "zero_dispatch or controlled_app or real_stack"
```

Expected durations on this Mac: harness unit tests ≈ 3 s; lane ≈ 10 s while science fails fast, bounded by 240 s polling per job once real computation runs (worst case ≈ 30 min across all entries); controls ≈ 2 s; pytest integration ≈ 30 s. Outputs: `evaluation/results/` (append-only). Teardown stops only processes the harness started and reports orphans.

## Requests to Owner 4 (files Owner 4 owns)

1. `docs/ownership-and-layout.md`: replace the pre-merge component table with the five-workstream allocation in master brief §1.31 (Workstream 5: `evaluation/**`, `docs/evaluation-protocol.md`, `scripts/evaluate.py`, `tests/test_evaluation.py`, new Python tests in `tests/integration/`, this log). I briefly edited that file and reverted it (`3f87487`) because it is yours.
2. `docs/issue-ledger.md`: I-001/I-002/I-005 are superseded by the merged backend and engine; current statuses are in `evaluation/FINDINGS.md`.
3. CI: run the commands above; treat `gate --require release` exit 3 as a failing release, exit 0 from `inventory` as informational only. `scripts/release/checklist.py:25` has an unused import (F-LINT-CHECKLIST).

## Previews of unmerged branches (never acceptance)

`--app-repo <worktree>` runs this branch's harness against a teammate checkout; `--diagnostic relax_nproc` lifts only the per-user process cap that blocks the Mac (F-MAC-NPROC). Both write to `evaluation/results/previews/` and never count toward gates.

| Branch | Commit | Result |
|---|---|---|
| `backend/browser-baseline` (now merged as PR #6) | `cc779bf` | plain: hero fails (F-MAC-NPROC). diagnostic: discovery + baseline replay pass; changed input, concurrency, design authority, zero dispatch pass; hero blocked by F-DESIGN-SOURCE-ARTIFACTS; follow-up per-candidate blocked (F-FOLLOWUP-FEEDBACK); cancel/restart unobservable (computation < 1 s). |

## Next exact actions

1. Preview Owner 3's `codex/gemini-offline-integration` against the zero-dispatch and controlled-boundary tests.
2. Cancellation is now observable with `--diagnostic science_barrier` (a harness-side barrier inside the scientific child): running cancellation passes; a worker SIGKILL leaves an orphan computation (P0 F-ORPHAN-WORKER-KILL, Owner 2). Ask Owner 2 for a product-side test barrier so this can become acceptance evidence.
3. Remaining master-brief gaps in my lane: stale-approval-after-revision HTTP check, extended native negative controls (truncation, missing dependency, wrong profile, duplicate member, oversized, another run's packet), endpoint-level admission goldens from `shared/contracts/DB-SC-1/fixtures/admission-golden.json`, guard coverage for the CLI process and credential-read detection, ledger corruption handling, metamorphic engine controls, and grading C08/C09 from the real graph at the controlled tier.
4. Retest F-MAC-NPROC, F-BASELINE-DISCOVERY, F-NATIVE-BYTES and F-FOLLOWUP-FEEDBACK whenever `main` moves.

## Conditional future work (not authorized now)

Live Gemini evaluation needs a new explicit user instruction, Owner 3's operator path, one agreed dispatch ledger and independent grading of predeclared cases. Do not run it, open a cohort or use another provider.
