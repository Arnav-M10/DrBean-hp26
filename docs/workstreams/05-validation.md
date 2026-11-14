# Workstream 5 — validation log (owner: Claude adversarial validation)

Durable resumption record required by the master brief (DB-MASTER-1 §2.22). Raw evidence and machine-readable findings live in `evaluation/`; this log links them and is not a second status source.

## Current position

| Item | Value |
|---|---|
| Branch | `claude/adversarial-validation` (pushed). PR #8 merged it into `main` up to `4ea7cb3`; `main` `55403ab` (PR #9 design, PR #10 offline AI, PR #11 follow-up) merged back as `98cef50`. Later harness commits (native consumer, `.venv-engine` discovery, Owner 4 launch path, design-bound follow-up, group-aware orphan cleanup, evidence-equivalent gates) reach `main` only through a new PR |
| Integration branch | `main` (GitHub default since the PR #3/#4 merges) |
| Last recorded lane run | `3b55843` (app code = `main` `9cc90e0`), on **both launch paths**: the harness's own isolated launch (`evaluation/results/`) and Owner 4's `scripts/dev/launcher.py` (`evaluation/results/owner4-launcher/`). Same verdicts: hero and changed input fail with `scientific_runtime_unavailable` (F-MAC-NPROC); retry/concurrency and zero dispatch pass. Owner 4's path with `relax_nproc`: `evaluation/results/owner4-launcher/relax_nproc/` |
| Host | macOS 26.7 arm64; backend CPython 3.13.18 (`uv sync --locked`); Counterdex/replay CPython 3.11.17 from Owner 4's `.venv-engine` (created by `launcher.py setup`); checkout under iCloud-synced `~/Documents` (see F-LAUNCHER-HIDDEN-PTH) |
| AI mode | zero external model dispatch, verified by the egress guard in API, worker and pytest; live Gemini `NOT_RUN` |
| Findings | `evaluation/findings.json` → `evaluation/FINDINGS.md`. Open P0: **F-MAC-NPROC** (the only blocker between this Mac and release acceptance of hero/design/follow-up) and **F-ORPHAN-WORKER-KILL**. Closed by retest on merged `main` this session: F-FOLLOWUP-FEEDBACK, F-DESIGN-SOURCE-ARTIFACTS, F-NATIVE-BYTES, F-BASELINE-DISCOVERY. Check-level ids are catalogued there too |
| Release gate | `python3.11 evaluation/cli.py gate --require release` → failed (exit 3) |

## Gate evidence (current)

| Gate | Status | Evidence |
|---|---|---|
| G0 baseline | done | backend suite on this Mac: 265 passed / 4 failed at `adac945` (was 136/17/11 at `586fb9b`); engine 257 OK; harness 82 unit tests, manifest v2 verified, selftest 24/62 |
| G1 real manual investigation (HTTP) | **passes on Linux CI; blocked on this Mac by F-MAC-NPROC only** | Linux CI run 43560507025 on `main` `61edad7` (PR #16): the real-science HTTP tests pass without diagnostics (43/46; failures: 2 strict XPASS fixed by `1ae19ff`, F-ORPHAN-WORKER-KILL). |
| G1 (this Mac) | blocked by F-MAC-NPROC | On merged `main` with only the process-limit guard relaxed: RS-HERO-FULL passes end to end (discovery, checked design with source ids at 8 h, both packets download and replay fresh, qualifier re-checks). Earlier notes below this row are history. |
| G1 (history) | was blocked on `main` | `RS-HERO-FULL` fails: on the Mac `scientific_runtime_unavailable` (F-MAC-NPROC); on any host the baseline producer is unavailable on `main` (F-BASELINE-DISCOVERY). Image admission passes. **Preview of Owner 2's `backend/browser-baseline` cc779bf (diagnostic relax_nproc):** real discovery, certified counterexample, baseline packet download + fresh `replay-native` all pass. |
| G2 decision loop | **blocked on this Mac by F-MAC-NPROC only** | On merged `main` (diagnostic): changed input, design authority and the design-bound follow-up pass (application, fresh replay and the decimal oracle agree per candidate). Earlier notes below this row are history. |
| G2 (history) | blocked | engine-level controls 12/12. Preview: changed input, design authority, three hypothetical lineages pass; checked design blocked by F-DESIGN-SOURCE-ARTIFACTS (without source ids the same pair separates at 8 h and replays fresh); per-candidate follow-up feedback has no route (F-FOLLOWUP-FEEDBACK). |
| G3 AI-ready offline | **evidenced on `main` `55403ab`** | AI-boundary + zero-dispatch suites 38/38 after PR #10; both coordinator residuals and F-AI-INTEGRATION-SEAM closed by retest; strict-xfail markers removed. Earlier notes below this row are history. |
| G3 (history) | mostly evidenced | zero-dispatch tests 7/7 incl. legacy live switch; controlled boundary 28 passed + 2 strict xfail (P2 residuals); real Worker + deepagents graph contrast and vanished-scenario refusal pass |
| G4 usable release | **blocked on this Mac** | Owner 4's one-command start fails here (F-LAUNCHER-HIDDEN-PTH, P1): iCloud Drive hides `.venv`, CPython skips its editable `.pth`, `bean_api` is not importable, doctor still says ready. With `apps/api` on `PYTHONPATH` the unmodified launcher passes readiness and zero dispatch and keeps provider credentials out of the API and worker |

## Unresolved findings and owners

See `evaluation/FINDINGS.md` for input, command, expected, observed and retests.

- **Owner 2 (urgent, before PR #14 merges):** F-RESTART-EPERM (P0): on macOS `run_bounded`'s owned-session cleanup raises PermissionError (Darwin EPERM for killpg on an exited, unreaped leader), so every normally finishing job fails and a cancelled job's guard can survive. One-line cause, standalone repro and a local-patch confirmation in `evaluation/results/previews/backend-restart-recovery-c231be4/`. Its lifeline guard does fix F-ORPHAN-WORKER-KILL.
- **Owner 2:** F-MAC-NPROC (P0, new: RLIMIT_NPROC per user on macOS blocks spawning CPython 3.11), F-BASELINE-DISCOVERY (P0, adapter wiring with Owner 1), F-NATIVE-BYTES (fixed pending HTTP retest), F-REVIEW-MATERIALIZATION (fixed pending retest), F-RESTART-UNOBSERVABLE, F-TEST-VAR-LEAK (P2).
- **Owner 1:** F-BASELINE-DISCOVERY producer side, F-FOLLOWUP-FEEDBACK (with Owner 2).
- **Owner 2 (ledger, 2.14):** F-LEDGER-TOTALS and F-LEDGER-MALFORMED (P2) on `main`; both fixed in PR #13 (strict xfails XPASS there; remove the markers when it merges). `tests/integration/test_ledger_attacks.py` also pins 13 safety regressions: negative/boolean/missing usage never releases a reservation, non-finite usage stays unknown, 8 concurrent reservations respect a cap of 3, replayed or unknown reconciliations never rewrite history, malformed history fails closed.
- **Owner 3:** F-EXPLANATION-QUALIFIER, F-EXPLANATION-NUMBER-FORMS, F-EXPLANATION-PARAPHRASE (P2, explanation guard gaps found by `tests/integration/test_explanation_guard.py`; P1 before any live model writes user-visible prose). F-COORDINATOR-OPTIONAL-STATUS and F-COORDINATOR-PROVIDER-LABEL closed by retest on `main` `55403ab`.
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
python3.11 evaluation/cli.py run --lane offline_real_science --subject http-owner4-launcher --results evaluation/results/owner4-launcher   # Owner 4's launcher; needs `launcher.py setup` once, ports 8000/4173 free
.venv/bin/python -m pytest tests/integration -m "zero_dispatch or controlled_app or real_stack"
```

Expected durations on this Mac: harness unit tests ≈ 3 s; lane ≈ 10 s while science fails fast, bounded by 240 s polling per job once real computation runs (worst case ≈ 30 min across all entries); controls ≈ 2 s; pytest integration ≈ 30 s. Outputs: `evaluation/results/` (append-only). Teardown stops only processes the harness started and reports orphans.

## Requests to Owner 4 (files Owner 4 owns)

1. `docs/ownership-and-layout.md`: replace the pre-merge component table with the five-workstream allocation in master brief §1.31 (Workstream 5: `evaluation/**`, `docs/evaluation-protocol.md`, `scripts/evaluate.py`, `tests/test_evaluation.py`, new Python tests in `tests/integration/`, this log). I briefly edited that file and reverted it (`3f87487`) because it is yours.
2. `docs/issue-ledger.md`: I-001/I-002/I-005 are superseded by the merged backend and engine; current statuses are in `evaluation/FINDINGS.md`.
3. CI: run the commands above; treat `gate --require release` exit 3 as a failing release, exit 0 from `inventory` as informational only. `scripts/release/checklist.py:25` has an unused import (F-LINT-CHECKLIST).
4. CI stack job (H-CI-ENGINE, reported by Owner 1 from run 43556610563): the integration suite's 7 failures are `scientific_runtime_missing` because the harness copy in `main` does not find `.venv-engine`. Fixed on this branch (`8bb1fbe`); until it merges, export `DRBEAN_SCIENCE_PYTHON="$PWD/.venv-engine/bin/python"` for that step. Either fix alone is sufficient.
5. Launcher (F-LAUNCHER-HIDDEN-PTH, P1): pass `--app-dir apps/api` to uvicorn and add `apps/api` to `PYTHONPATH` in `child_env()` (as `shared/contracts/BACKEND_INTEGRATION.md` documents), and let doctor import `bean_api` with the services' environment. Reproduction: `evaluation/results/owner4-launcher/HIDDEN-PTH-REPRO.md`.
6. Launcher (F-LAUNCHER-ENV-READ, P2): build the child environment from names only (`os.environ.items()` reads every credential value) and give doctor probes the scrubbed environment.

## Previews of unmerged branches (never acceptance)

`--app-repo <worktree>` runs this branch's harness against a teammate checkout; `--diagnostic relax_nproc` lifts only the per-user process cap that blocks the Mac (F-MAC-NPROC). Both write to `evaluation/results/previews/` and never count toward gates.

| Branch | Commit | Result |
|---|---|---|
| `codex/science-integration-fixes` (PR #15, on PR #5; Counterdex 0.3) | `9a6db61` | **NO diagnostics: 6/7 pass on this Mac** (hero, changed input, retry, design authority with v2 reuse probe, follow-up via `recheck`, zero dispatch): F-MAC-NPROC fixed there. Barrier only: worker-kill orphan still reproduces (fix is PR #14). Engine controls against its Counterdex 0.3.0: **22/22 pass** (`controls --app-repo`). |
| `backend/restart-recovery` (PR #14) | `c231be4` | with barrier: **worker-kill orphan fixed**; without: hero/changed input **fail** and a cancelled child survives (F-RESTART-EPERM, Darwin-only); local one-line patch -> 6/7 + cancel/restart pass. |
| `backend/controlled-acceptance` (PR #13) | `731afdc` | local merge with this harness: integration suite unchanged (39 passed; failures F-MAC-NPROC/orphan; no regressions). |
| merged `main` (`55403ab`, after PR #10) in this checkout | harness `1ae19ff` | diagnostic relax_nproc: **6/7 pass** again (hero, changed input, retry, design authority, follow-up, zero dispatch); plain acceptance on both launch paths: F-MAC-NPROC; gate exit 3. |
| merged `main` (`80f95a4`) in this checkout | harness `b827c61`/`f992b48` | diagnostic relax_nproc: **6/7 pass** (hero, changed input, retry, design authority, follow-up, zero dispatch); with science_barrier the worker-kill orphan reproduces (F-ORPHAN-WORKER-KILL) and is now terminated before the barrier is released. Plain acceptance on both launch paths: F-MAC-NPROC. |
| `backend/followup` (PR #11, stacked on PR #9; now merged) | `8525cab` | diagnostic relax_nproc: **6/7 entries pass incl. RS-FOLLOWUP** (design-bound `PlanBody.followup`: application, fresh replay and decimal oracle agree per candidate on all three readings; tampered/substituted/foreign scopes refused; qualifier 125/125); RS-CANCEL-RESTART unrun without the barrier. With relax_nproc + science_barrier: running cancel passes, **worker SIGKILL still orphans the child** (F-ORPHAN-WORKER-KILL). |
| `backend/browser-design` | `8451c1f` | plain: hero fails (F-MAC-NPROC). diagnostic: **RS-HERO-FULL passes** — discovery, checked design with documented source ids (8 h, positive exact margin), both native packets replay fresh, 33/33 qualifier re-checks; follow-up per-candidate still blocked. |
| `codex/ai-offline-milestones` | `c6f04c2` | worker-boundary controlled lane passes (F-AI-INTEGRATION-SEAM resolved); both coordinator P2 residuals XPASS; all 5 backend failures are F-MAC-NPROC. |
| `main` + `codex/gemini-offline-integration` (local merge) | `9cc90e0` + `c95ab28` | zero-dispatch passes; Owner 3 fixes both coordinator P2 residuals (strict xfail XPASS); the worker's controlled lane breaks with `provider_placeholder_disabled` until Owner 2 selects mode=controlled (F-AI-INTEGRATION-SEAM). |
| `backend/browser-baseline` (now merged as PR #6) | `cc779bf` | plain: hero fails (F-MAC-NPROC). diagnostic: discovery + baseline replay pass; changed input, concurrency, design authority, zero dispatch pass; hero blocked by F-DESIGN-SOURCE-ARTIFACTS; follow-up per-candidate blocked (F-FOLLOWUP-FEEDBACK); cancel/restart unobservable (computation < 1 s). |

## Next exact actions

1. Merge order (for the user / owners): PR #5 + PR #15 make real science run on this Mac with no diagnostics. PR #14 fixes the worker-kill orphan but, as is, fails every normally finishing job on macOS (F-RESTART-EPERM): fix that first. Then rerun the plain lane on both launch paths and `gate --require release`.
1b. (history) F-MAC-NPROC (P0, Owner 2) was the single blocker for release acceptance on this Mac: when Owner 2's platform-aware process guard lands, rerun the plain lane on both launch paths, then `gate --require release`.
2. F-ORPHAN-WORKER-KILL (P0, Owner 2): reproduced on merged `main`. Ask for a product-side test barrier so the retest can be acceptance evidence, not only a diagnostic.
3. Done: PR #10 merged, markers removed, AI findings closed. PR #12 (Owner 4 launcher cleanup; adds `DRBEAN_SCIENCE_PYTHON` to CI, which also resolves H-CI-ENGINE there) and PR #13 (Owner 2 controlled agents with real science) are open; PR #13 previewed locally: integration suite unchanged (no regressions).
4. A new PR from this branch to `main` would ship the native consumer, `.venv-engine` discovery (fixes H-CI-ENGINE in CI), the Owner 4 launch subject and group-aware orphan cleanup. Opening it is the user's call.
5. Owner 4: F-LAUNCHER-HIDDEN-PTH (P1) and F-LAUNCHER-ENV-READ (P2); rerun `--subject http-owner4-launcher` after a fix (it then records no workaround).

## Conditional future work (not authorized now)

Live Gemini evaluation needs a new explicit user instruction, Owner 3's operator path, one agreed dispatch ledger and independent grading of predeclared cases. Do not run it, open a cohort or use another provider.
