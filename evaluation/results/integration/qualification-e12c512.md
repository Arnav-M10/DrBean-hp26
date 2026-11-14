# Independent qualification of candidate `e12c512cd46cd5d0a95e00350c2c9df7d8bc3bc7`

Owner 5 (independent validation), 2026-11-14, under the sprint brief *Prove the Gemini, Deep Agents and paper workflow actually works*. This record supersedes `1bc3604` (which qualified `main` `22c9a24`). The `c51bbae` and `62704be` runs on the way also passed the gate. All evidence is retained, including one controlled_science report that failed because a file was added to the checkout during its run, and two preview reports that failed on a harness precondition defect (H-LANE-ENGINE-PRECONDITION, fixed).

## What was qualified

| Item | Value |
|---|---|
| Candidate (empty `git status`) | `e12c512cd46cd5d0a95e00350c2c9df7d8bc3bc7` on `claude/adversarial-validation` |
| Application code | identical to `main` `b8c5952` (PR #32 = PR #20 coordinator observation + PR #28 evidence-bound explanations + fixes). Check: `git diff --quiet origin/main e12c512 -- apps packages scripts shared fixtures pyproject.toml uv.lock` |
| Harness | this branch: `evaluation/`, `tests/integration/` |
| Not included | sprint PRs #33 (paper mapping, Owner 1), #34 (Deep Agents interfaces, Owner 2, documents only), #35 (metered Gemini gateway and paper proposals, Owner 3). These ran only as labelled previews. **No combined paper/Gemini/Deep Agents product exists yet.** |

## Platform and runtimes

- macOS 26.7 (Darwin 25.6.0) arm64. The checkout is under iCloud-synced `~/Documents`.
- Backend: CPython 3.13.18 (`.venv`, `uv sync --locked`).
- Engine: CPython 3.11.17 (`.venv-engine`) with Counterdex 0.3.0, source digest `ed5a8fb2…7750`. The application's scientific child imports the repository source first; the installed copy is identical anyway.
- Node v25.3.0.

## Results

| Check | Result |
|---|---|
| Harness unit tests, CPython 3.11 and `3.13 -W error` | 175/175 on both |
| Acceptance lane `offline_real_science`, harness launch path, no diagnostics | **7/7** (attempts `att_74ec3a5686ce4923` hero, `att_27769189779f4492` changed input, `att_054fcee519ef49a8` retry/concurrency, `att_f00989848213452a` design authority, `att_8342c5240fa847a6` follow-up, `att_5c187b28d55a426c` cancel/restart, `att_be8a61e28b2147ab` zero dispatch) |
| Native engine controls | **22/22**, from a qualified record |
| Lane `controlled_callbacks` | **passed** `lane_c72524dd19c14f93`: 81 passed, 4 xfailed (F-NARRATION-OVERSUPPRESSION), 36 NOT_AVAILABLE (gateway and paper-validator attacks: no such modules on `main`); zero dispatch verified |
| Lane `controlled_science` | **passed** `lane_bc3d3b306bad4126`: 17 passed (9 launched stacks), 7 NOT_AVAILABLE paper-route attacks; zero dispatch verified with every stack's guard log |
| Lane `historical_replay` | **passed** `lane_cc7c7765d1e94bbd`: 120 retained packets replayed fresh against their recorded anchors; 1 archived 0.2.0 packet `incompatible_version` (another checker version, not corruption) |
| Lane `live_gemini` | **not_run**: no user-enabled budget; no key inspected; no provider called |
| `pytest tests/integration` (at `c51bbae`) | 98 passed, 11 xfailed (4 F-NARRATION-OVERSUPPRESSION, 7 NOT_AVAILABLE paper attacks); now also 36 more NOT_AVAILABLE library attacks on `main` |
| Backend / engine / web (at `c51bbae`, same application code) | 704 passed / 292 OK (2 skipped by design) / 31 passed |
| `gate --require release` | **exit 0** (`gates-latest.json`); required gates include the new `evidence_lanes` |

## Previews (labelled; never acceptance)

| Preview | Result |
|---|---|
| PR #35 `codex/gemini-metered-adapter` `c952c35` on `62704be` (`3a7816e`) | controlled_callbacks **passed** `lane_1c86a89352b248ec` (111 passed, 10 xfailed = 4 narration + 6 validator defects); controlled_science **passed** `lane_65fd953469e04b65` (17 passed, 7 NOT_AVAILABLE). Two earlier preview reports (`lane_3022c056c95f4f23`, `lane_95503c92ead24a0d`) failed only on the harness precondition defect H-LANE-ENGINE-PRECONDITION and are kept. Gateway attacks 20/20 pass: one reservation per transport call, no hidden retry, uncertain outcomes recorded as unknown, nothing dispatched when disabled or without atomic session accounting. Paper validator: 10 controls pass; 4 defects (F-PAPER-CITATION-SUBSTRING P1, F-PAPER-QUOTE-NORMALIZATION, F-PAPER-HARD-BOUND-CONTEXT, F-PAPER-EXPONENT-FLATTENING) |
| PR #33 `codex/paper-science-mapping` `b397c05` on `62704be` (`d0148aa`) | lanes controlled_callbacks **passed** `lane_14457236e1b143be`, controlled_science **passed** `lane_e403723180574529`; engine controls **22/22** against PR #33's engine (source `6467d0f7476a…`); historical replay of PR #33's package packets with its own checker `lane_094dc5aad7a441d0`: 21 replayed, 4 `incompatible_version`. These are the three earlier review-evidence packets and the 0.2.0 archive: the changed engine source refuses packets from another source version. This is correct strictness, but after PR #33 merges every packet retained by acceptance runs will need its original checker to replay (next harness step: replay with the engine at the packet's recorded commit) |
| PR #34 `backend/deepagents-durable` `33dc7f4` | documents only (`research-agent.v1` interface); nothing to execute |

## Rehearsal script for the current product (grounded in recorded runs)

This covers the manual and controlled scientific loop that exists on `main`. **It is not the paper/Gemini workflow, which is not built yet.** Each step cites the recorded acceptance attempt that exercised it on this Mac.

1. **Start.** The launched stack: API and worker, guard active in every process, zero external model dispatch verified (`RS-ZERO-DISPATCH`: `att_be8a61e28b2147ab`). These runs used the harness launch path. Owner 4's unmodified `scripts/dev/launcher.py start` was last verified at `1bc3604`: 6/7, with cancel/restart observable only on the harness path. Re-verify it on the presentation Mac before the demo.
2. **Investigate the reviewed question.** Hero dataset, then a bounded real Counterdex search. The result is a *certified counterexample* with a strict outside witness (`RS-HERO-FULL`: `att_74ec3a5686ce4923`).
3. **Design a measurement.** This needs a separate approval. The checked fixed-pair separation at 8 h is confirmed by an independent decimal oracle. Approving the baseline does not approve the design (`RS-DESIGN-AUTHORITY`: `att_f00989848213452a`).
4. **Follow up.** A reviewed reading of 3.4, 4.57 or 4.0 gives candidate-specific survival. An unresolved reference stays `inconclusive` (`RS-FOLLOWUP`: `att_8342c5240fa847a6`).
5. **Replay.** Download the native packet and replay it fresh with `counterdex replay-native` against the recorded anchor. One changed byte, or a wrong anchor, is rejected.
6. **Failure and recovery example.** Cancel a running 128-row computation and SIGKILL the worker. No child survives, and recovery marks the run interrupted without redispatching it (`RS-CANCEL-RESTART`: `att_5c187b28d55a426c`). Retried and concurrent starts create exactly one run (`RS-RETRY-CONCURRENT`: `att_054fcee519ef49a8`).

What to say: "Counterdex checked this reviewed deterministic claim under its stated assumptions and found a counterexample. The separation concerns two fixed candidates under the reviewed design. Replay re-runs the same checker; it is not an independent proof system."

## Four separate claims

1. **Branch readiness (PR #22):** this candidate plus evidence-only commits.
2. **Scientific acceptance:** the application code at `main` `b8c5952`, on this Mac.
3. **Offline product release (Owner 4's G0–G4) and the paper/Gemini/Deep Agents product:** not established. The sprint product has not been assembled; ordinary-user acceptance on a combined commit is pending.
4. **Live Gemini qualification:** `not_run`.
