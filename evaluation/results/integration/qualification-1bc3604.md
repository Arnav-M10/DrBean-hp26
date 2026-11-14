# Independent qualification of candidate `1bc3604d04bf225ba6477b419a54ba67fb1bf9a1`

Owner 5 (independent validation). 2026-11-14, about 02:09 to 02:14 ET. This supersedes `e791e91` (see `qualification-e791e91.md`) because `main` advanced to `22c9a24` (PR #27) during that qualification. The evidence for both candidates is retained.

## What was qualified

| Item | Value |
|---|---|
| Candidate (immutable; empty `git status`) | `1bc3604d04bf225ba6477b419a54ba67fb1bf9a1` on `claude/adversarial-validation` |
| Application code | identical to `main` `22c9a24` (PR #27 merged: controlled source review, browser source workflow, launcher). Check: `git diff --quiet origin/main 1bc3604 -- apps packages scripts shared pyproject.toml uv.lock` |
| Harness and tests | this branch: `evaluation/`, `tests/integration/` |
| Not included (still open) | PR #20 (its coordinator scenario-observation change) and PR #28 (evidence-bound explanations). Both were exercised only in the labelled preview `combined-6a69a55` |

## Platform and runtimes

- macOS 26.7 (Darwin 25.6.0) arm64. Checkout under iCloud-synced `~/Documents`.
- Backend: CPython 3.13.18 (`.venv`, `uv sync --locked`, uv 0.13.8).
- Engine: CPython 3.11.17 (`.venv-engine`) with Counterdex 0.3.0, byte-identical to the repository source. Source digest `ed5a8fb2216dcf4f0113799bd3e341fc464e204492fa3bc673460dec19777750`. This is verified in the control record and, in the lane, against the application's capability manifest.
- Node v25.3.0.
- No sandbox restriction was encountered. No product guard was relaxed for acceptance; the barrier run is a labelled diagnostic.

## Results at `1bc3604`

| Check | Result |
|---|---|
| Harness unit tests, CPython 3.11 and `3.13 -W error` | 142/142 on both |
| `cli.py verify`, `selftest`, `history` | manifest v3 OK; self-test 24/62; history OK (140 main-chain attempts plus the verified fork) |
| `ruff check evaluation tests apps scripts` | clean |
| Acceptance lane, harness launch path, no diagnostics | **7/7 passed** |
| Acceptance lane, Owner 4's unmodified `launcher.py start` | 6/7 passed; cancel/restart runs only on the harness path |
| Barrier diagnostic (cancel/restart) | passed; the harness terminated nothing |
| Native engine controls | **22/22**, from a qualified record (clean, executed acceptance, CPython 3.11.17, engine imported from the repository with a matching digest) |
| `pytest tests/integration` | **73 passed, 27 xfailed, 0 failed, 0 XPASS**. Source review now passes on `main` |
| Backend suite (`BEAN_COUNTERDEX_PYTHON=.venv-engine/bin/python .venv/bin/python -m pytest -q tests --ignore=tests/integration`) | 619 passed. It also recreated `var/artifacts` (F-TEST-VAR-LEAK, P2, Owner 2) |
| Engine suite | 292 run, OK (2 skipped by design) |
| Web unit tests (`node --test`) | 31/31 |
| Release gate | `gates-latest.json` on the evidence commit |

The 27 xfails are the explanation-guard gaps on `main`'s phrase-list guard: F-EXPLANATION-QUALIFIER, NUMBER-FORMS, PARAPHRASE and CHECKED-GATES. All four are fixed in open PR #28.

### Coverage exercised

- **Real discovery:** bounded search and a certified counterexample with a strict outside witness. The application's engine runtime matches the repository source file by file.
- **Changed input:** fresh identities and a new computation.
- **Separate design authorization.**
  - Positive separation: checked at 8 h and confirmed by the decimal oracle.
  - No separation: the allowance is 0.6 mg/L. The oracle predicts the tier, the application agrees and selects nothing, and the packet replays fresh.
  - Reuse probe: a nonempty-reuse design request is refused at proposal.
- **Follow-ups:**
  - Readings of 3.4, 4.57 and 4.0.
  - An actual reading at its own time.
  - An unresolved reference: the reading is the engine-enclosure midpoint at 7.9 h. The reference is `inconclusive`/`insufficient_enclosure`, and the 80-digit value lies inside the enclosure, compared exactly.
  - The outcome follows from which candidates survive.
- **Evidence integrity:** exact native downloads with all eight external anchors and fresh replay. Altered bytes and wrong anchors are rejected.
- **Source review on `main`:**
  - Source → controlled proposal (explicit controlled authorship, zero provider attempts; a same-key retry returns the same record).
  - Human correction and review (the correction is kept beside the original).
  - Materialization (keeps source linkage and the original spelling, is idempotent and grants no approval).
  - A separately approved real run on the corrected inputs, with fresh replay and tamper controls.
- **Duplicates and staleness:** retried and concurrent starts produce one run, and stale approvals are refused.
- **Cancellation and recovery:** a real 128-row workload. A live child exists at cancel and at worker SIGKILL; none survive. Recovery marks the run interrupted and does not redispatch it.
- **Ledger accounting:** 15 attacks on isolated stores, all passing.
- **Explanations:**
  - Attacks and unsupported checked-design claims are known gaps on `main` (xfail).
  - A fully supported checked-design statement is kept.
  - Correct limiting statements are kept on `main`.
- **Zero external model dispatch:** guarded API and worker, with empty provider ledgers.

## Labelled preview (not acceptance)

Combined `6a69a55`: harness `b25c70b` + PR #20 `f3d424f` + PR #27 `6a3705a` + PR #28 `623ae19`.

- Lane: 7/7. Integration suite: 96/96.
- Backend suite: 688 passed, 1 failed. The failure is `tests/test_coordinator.py::test_separately_approved_design_has_one_completed_callback_observation`. It passes on PR #20 alone, and PR #28's guard withholds its narration (F-NARRATION-OVERSUPPRESSION, P2, Owner 3).

## Four separate claims

1. **Branch readiness (PR #22):** candidate `1bc3604` plus evidence-only commits. Harness 142/142; integration with 0 failed and 0 XPASS.
2. **Scientific acceptance:** this applies only to the application code at `main` `22c9a24`, on this Mac, as recorded in `gates-latest.json`. PRs #20 and #28 are not covered.
3. **Offline product release (Owner 4's gates G0 to G4, including the complete browser workflow):** not established here. Passing CI or this scientific gate does not show that the full browser workflow is usable.
4. **Live Gemini qualification:** NOT_RUN. Gemini stays disabled; no key was inspected and no provider was called.
