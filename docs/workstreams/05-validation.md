# Workstream 5 — validation log (owner: Claude adversarial validation)

Durable resumption record required by the master brief (DB-MASTER-1 §2.22). Raw evidence and machine-readable findings live in `evaluation/`; this log links them and is not a second status source.

## Current position

| Item | Value |
|---|---|
| Branch | `claude/adversarial-validation` (PR #22). `main` `b8c5952` (PR #32: PRs #20 + #28 + fixes) merged in as `c51bbae`, after `cbfa5ef` as `6997efb`; nothing reverted |
| Sprint brief | `05_Claude_Independent_Validation.md` (papers → Gemini → Deep Agents → Counterdex → design → follow-up → replay). Owner 5 deliverables are listed below with their state |
| Final candidate | `980a25a` (application code = `main` `b8c5952`). Record: `evaluation/results/integration/qualification-980a25a.md`; `c51bbae` and `62704be` also passed the gate on the way |
| Host | macOS 26.7 arm64; backend CPython 3.13.18 (`uv sync --locked`); engine CPython 3.11.17 (`.venv-engine`, identical to the source, which the application's child imports first anyway); checkout under iCloud-synced `~/Documents` |
| AI mode | zero external model dispatch, verified by the egress guard in every lane report; live Gemini `not_run` (no user-enabled budget, no key inspected) |
| Findings | `evaluation/findings.json` → `FINDINGS.md`. No open P0. Two open P1s, both on **unmerged** PRs: F-PAPER-CITATION-SUBSTRING (Owner 3, PR #35) and F-PAPER-RENDER-MEMORY (Owner 4, PR #36). Closed by retest on `main` `b8c5952`: F-EXPLANATION-QUALIFIER/NUMBER-FORMS/PARAPHRASE/CHECKED-GATES. Open P2: F-NARRATION-OVERSUPPRESSION (narrowed), F-PAPER-QUOTE-NORMALIZATION, F-PAPER-HARD-BOUND-CONTEXT, F-PAPER-EXPONENT-FLATTENING (PR #35), F-TEST-VAR-LEAK, F-SIBLING-FORKS; harness H-LANE-ENGINE-PRECONDITION fixed |
| Release gate | `gate --require release` exit 0 at `980a25a` (`evaluation/results/gates-latest.json`), now including the required `evidence_lanes` gate. This is scientific acceptance of `main` `b8c5952` on this Mac only. It is not the paper/Gemini/Deep Agents product (not built yet), not Owner 4's G0–G4, and not live Gemini |

## Sprint deliverables (Owner 5) and their state

| Deliverable | State | Where |
|---|---|---|
| 1. Four evidence lanes with machine-readable, identity-bound reports; gates reject dirty, incompatible or foreign-identity evidence | **done**; `controlled_callbacks`, `controlled_science` and `historical_replay` run on every candidate; `live_gemini` is `not_run` by construction | `evaluation/drbean_eval/lanes.py`, `cli.py lanes`, `evaluation/results/lanes/reports.jsonl`, gate `evidence_lanes` |
| 2. Paper corpus: at least 6 development documents plus 4 sealed held-aside variants, with gold from renderings | **holdouts sealed** (H1–H4, commitment `ad8a6913…`); development: **4 of 6** rendered by Owner 4 (PR #36), and my gold from renderings agrees with Owner 4's manifest field by field; live subset predeclared, `not_run` | `evaluation/corpus/` |
| 3. Trust-boundary attacks (10 categories) | current-route attacks pass on `main`; library-level gateway (20/20 pass) and validator attacks (4 defects) run on the PR #35 preview; paper-route, citation, statistics, authority, identity, metered-model and resume attacks are explicit `NOT_AVAILABLE` until advertised | `evaluation/attack_matrix.json`, `tests/integration/test_paper_trust_boundaries.py`, `test_gemini_gateway_attacks.py`, `test_paper_proposal_validation.py` |
| 4. Integration metrics (precision, coverage, citations, adaptivity) | scorer ready (`paper_scoring.py`); **no measurement yet**: no paper path, and live is `not_run` | `evaluation/drbean_eval/paper_scoring.py` |
| 5. Ordinary-user acceptance on the final combined commit with Owner 4's launcher | **not possible yet**: no combined paper product exists (PR #34 is interface-only; PRs #33 and #35 are unwired) | — |
| 6. Sponsor evidence matrix | **done for the current state**; truthful about what is not built or not run | `evaluation/results/sponsor-evidence.md` |
| 7. Release judgment, gate table, rehearsal script | scientific gate for `main` passes; paper product judgment pending; rehearsal script for the current loop in the qualification record | `evaluation/results/integration/qualification-980a25a.md` |

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
DRBEAN_BACKEND_PYTHON=$PWD/.venv/bin/python python3.11 evaluation/cli.py lanes run --lane controlled_callbacks   # also controlled_science, historical_replay
python3.11 evaluation/cli.py lanes report && python3.11 evaluation/cli.py lanes verify
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
| PR #36 `claude/dreamy-lamport-dsttgm` (Owner 4: PDF admission, page panel, live opt-in) on `c2803a4` plus Owner 2's **unreviewed** route patch and an unlocked pypdf/pypdfium2 resolution | `f063b10` (`081bbdc`) | Owner 4's 36 paper tests pass on macOS; **Owner 4's real-browser paper check passes 31/31 on this Mac** (headless Chromium 153: upload, pages, honest citations, SD/CI and injected-approval warnings, reopen, double clicks, narrow screen, real certified counterexample from paper-cited hand-entered inputs, zero provider attempts; `evaluation/results/previews/pr36-30ca1d7/check-paper-macos.json`, run `run_1b0fde0cf4d944ac873e473335170260`); my five paper-route attacks pass (hostile assets bounded with named refusals, inert names, workspace scope and key binding, honest citation checks, bounded page selections); development gold agrees with Owner 4's manifest 23/23, 23/23, 10/10; **F-PAPER-RENDER-MEMORY (P1)**: on macOS a 4.2 MB page inflating to 4 GiB drives the process tree to 2440 MiB |
| PR #35 `codex/gemini-metered-adapter` on `62704be` | `3a7816e` (`c952c35`) | lanes controlled_callbacks 111 passed + 10 xfail and controlled_science 17 + 7 NOT_AVAILABLE (both passed after the H-LANE-ENGINE-PRECONDITION fix); gateway attacks 20/20; paper validator: 4 defects (F-PAPER-CITATION-SUBSTRING P1 and three P2) |
| PR #33 `codex/paper-science-mapping` on `62704be` | `d0148aa` (`b397c05`) | lanes passed; engine controls 22/22 with PR #33's engine; its package packets: 21 replay, 4 older packets refused as `source_version_mismatch` (correct strictness; historical replay needs the original checker after merge) |
| PR #34 `backend/deepagents-durable` | `33dc7f4` | interface documents only (`research-agent.v1`); nothing executable |
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

1. **Owner 4 (before PR #36 merges):** F-PAPER-RENDER-MEMORY (P1). Bound page rendering by memory on macOS, which has no `RLIMIT_AS`: either pre-inflate each page's streams with a capped decoder, or have the parent sample the worker's RSS and kill it above `WORKER_MEMORY_BYTES`. Opt-in regression: `DRBEAN_HEAVY_RESOURCE_ATTACKS=1 pytest tests/integration/test_paper_trust_boundaries.py::test_maximum_size_inflate_bomb_preview_stays_within_memory`.
2. **Owner 3 (before PR #35 merges):** F-PAPER-CITATION-SUBSTRING (P1). Require whole-token boundaries in the page text, not only in the quote. Then F-PAPER-QUOTE-NORMALIZATION, F-PAPER-HARD-BOUND-CONTEXT and F-PAPER-EXPONENT-FLATTENING (P2). Each has a strict-xfail regression in `tests/integration/test_paper_proposal_validation.py`, which turns into a failure when fixed so the marker is retired by retest.
3. **Owner 4:** two more development PDFs are needed to reach the brief's six: a mixed-units document (Owner 1's minutes/ng-per-mL variant from PR #33) and a missing-raw-data or graph-only document. Gold for the four delivered papers is in `evaluation/corpus/development/`.
4. **Owner 2 (contracts, before assembly):** F-PAPER-IDENTITY-CONTRACTS. PRs #34, #35 and #36 use three different page identities and citation coordinate spaces (pixel boxes with a top-left origin versus PDF points with a bottom-left origin and rotation; `page_sha256` has no producer). Publish one mapping in `research-agent.v1`.
5. **Owner 2:** apply or review PR #36's route patch and publish the `research-agent.v1` implementation (PR #34). The paper-route, identity and resume attacks switch from NOT_AVAILABLE to HARNESS_PENDING when advertised, and Owner 5 then writes them against the published routes.
6. **Done (harness):** historical replay now replays a packet that the tested checker refuses as another source version with the engine extracted at the commit that produced it (`replayed_original_checker`). On the PR #33 preview, its three review-evidence packets replay this way, and only the 0.2.0 archive stays `incompatible_version`. Still open: Owner 4's full launcher start with a dummy live opt-in is `NOT_RUN`, because ports 8000/4173 are held by another running instance on this Mac (not touched); its doctor check passes.
7. **Freeze:** when Owners 2–4 record the frozen implementation and prompt versions, reveal H1–H4 (verify the commitment `ad8a6913…`) and run them in the controlled lanes; live only within a user-enabled budget.
8. Any later relevant code change: refresh `.venv-engine` if the engine changed, then rerun the acceptance lane, controls, the three evidence lanes and the gate on a clean candidate. Never edit the checkout during a run.

## Conditional future work (not authorized now)

Live Gemini evaluation needs a new explicit user instruction, Owner 3's operator path, one agreed dispatch ledger and independent grading of predeclared cases. Do not run it, open a cohort or use another provider.
