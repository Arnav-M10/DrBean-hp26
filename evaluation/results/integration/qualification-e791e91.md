# Independent qualification of candidate `e791e91f617d82e68f8878d72c4f7e99631941ab`

Owner 5 (independent validation). 2026-11-14, about 02:02 to 02:08 ET. This supersedes the earlier candidate `5138c5f`, whose evidence stays in history, because a test file changed after it (`c79e2c6`).

## What was qualified

| Item | Value |
|---|---|
| Candidate (immutable; empty `git status`) | `e791e91f617d82e68f8878d72c4f7e99631941ab` on `claude/adversarial-validation` |
| Application code | identical to `main` `2d2993d` (PR #26): `git diff --quiet origin/main e791e91 -- apps packages scripts pyproject.toml uv.lock` |
| Harness and tests | this branch: `evaluation/`, `tests/integration/` |
| Not included | PR #20 (controlled source review), PR #27 (browser source workflow), PR #28 (evidence-bound explanations): exercised only as the labelled preview below |

## Platform and runtimes

- macOS 26.7 (Darwin 25.6.0) arm64. Checkout under iCloud-synced `~/Documents`.
- Backend: CPython 3.13.18 (`.venv`, `uv sync --locked`, uv 0.13.8).
- Engine: CPython 3.11.17 (`.venv-engine`) with Counterdex 0.3.0. The installed copy is byte-identical to the repository source. Source digest `ed5a8fb2216dcf4f0113799bd3e341fc464e204492fa3bc673460dec19777750` (24 files). This is verified in the control record and, in the lane, against the application's own capability manifest.
- Node v25.3.0.
- No sandbox restriction was encountered. No product guard was relaxed for acceptance; the barrier run is a labelled diagnostic.

## Results at `e791e91`

| Check | Result |
|---|---|
| Harness unit tests, CPython 3.11 and `3.13 -W error` | 141/142 at `e791e91` itself. The catalog test failed because the new F-NARRATION-OVERSUPPRESSION id was cited before it was recorded. **142/142 at the evidence commit**, which adds the finding to `findings.json`; code is identical |
| `cli.py verify`, `selftest`, `history` | manifest v3 OK; self-test 24/62; history OK, with the verified fork segment |
| Acceptance lane, harness launch path, no diagnostics | **7/7 passed** |
| Acceptance lane, Owner 4's unmodified `launcher.py start` | 6/7 passed; cancel/restart runs only on the harness path |
| Barrier diagnostic (cancel/restart) | passed; the harness terminated nothing |
| Native engine controls | **22/22**, from a qualified record (clean, executed acceptance, CPython 3.11.17, engine imported from the repository with a matching digest) |
| `pytest tests/integration` | **72 passed, 28 xfailed, 0 failed, 0 XPASS** |
| Backend suite (`tests --ignore=tests/integration`, with `BEAN_COUNTERDEX_PYTHON=.venv-engine/bin/python`) | 588 passed. It also recreated `var/artifacts` in the checkout (F-TEST-VAR-LEAK, P2, Owner 2) |
| Engine suite (`python3.11 -m unittest discover -s packages/groundwork_adapter/tests`) | 292 run, OK (2 skipped by design) |
| Web unit tests (`node --test`) | 30/30 |
| Release gate (`cli.py gate --require release`) | see `gates-latest.json` on the evidence commit |

The 28 integration xfails are expected:
- 27 explanation-guard gaps on `main`'s phrase-list guard: F-EXPLANATION-QUALIFIER, NUMBER-FORMS, PARAPHRASE and CHECKED-GATES, all fixed in PR #28.
- 1 source-review test, blocked because controlled source review is not on `main` (PR #20).

### What the acceptance lane exercised (harness path, no diagnostics)

- **Real discovery:** bounded search and a certified counterexample with a strict outside witness. The engine the application runs matches the repository source file by file.
- **Changed input:** fresh identities and a new computation.
- **Separate design authorization.**
  - Positive separation: checked at 8 h and confirmed by the decimal oracle.
  - No separation: the allowance is 0.6 mg/L. The oracle predicts the tier, the application agrees and selects nothing, and the packet replays fresh.
  - Reuse probe: a nonempty-reuse design request is refused at proposal.
- **Follow-ups:**
  - Readings of 3.4, 4.57 and 4.0, one per candidate-specific outcome.
  - An actual reading at its own time.
  - An unresolved reference: the reading is the engine-enclosure midpoint at 7.9 h. The reference is `inconclusive`/`insufficient_enclosure`, and the 80-digit value lies inside the enclosure, compared exactly.
  - The outcome follows from which candidates survive.
- **Evidence integrity:** exact native downloads with matching length, digest, media type and all eight external anchors. Fresh replay passes. Altered bytes and wrong anchors are rejected.
- **Duplicates and staleness:** retried and concurrent starts produce one run, and stale approvals are refused.
- **Cancellation and recovery:** a real 128-row workload. A live child exists at cancel and at worker SIGKILL; none survive. Recovery marks the run interrupted and does not redispatch it.
- **Zero external model dispatch:** the guard was active in the API and the worker, and every provider ledger was empty.
- **Ledger accounting (integration suite):** 15 attacks on isolated stores pass. These cover negative, boolean, non-finite and malformed usage, totals, concurrency, replayed or unknown reconciliation, and malformed history.
- **Explanations (integration suite):**
  - Attacks and unsupported checked-design claims: xfail on `main`'s guard, all refused under PR #28.
  - A fully supported checked-design statement is kept.
  - Correct limiting statements are kept on `main` and withheld under PR #28 (F-NARRATION-OVERSUPPRESSION).

## Labelled preview (not acceptance): combined PRs

Local merge `6a69a55`, never pushed: harness `b25c70b` + PR #20 `f3d424f` + PR #27 `6a3705a` + PR #28 `623ae19`. The docs-only conflict in `docs/workstreams/03-ai.md` was resolved to PR #28's text.

- Lane: 7/7. Evidence: `evaluation/results/previews/combined-6a69a55-pr20-pr27-pr28/plain`.
- Integration suite: 96/96, a full rerun after fixing my source-review retry key. This includes source → controlled proposal → correction and review → idempotent materialization → separately approved real science → fresh replay, and 33/33 explanation cases under the declared policy.
- Backend suite in that tree: **688 passed, 1 failed**. The failure is `tests/test_coordinator.py::test_separately_approved_design_has_one_completed_callback_observation`. It passes on PR #20 alone; PR #28's guard withholds its narration "The returned design remains numerical guidance." (F-NARRATION-OVERSUPPRESSION).

## Four separate claims

1. **Branch readiness (PR #22):** candidate `e791e91`, plus evidence-only commits. Harness 142/142 at the evidence commit; integration with 0 failed and 0 XPASS.
2. **Scientific acceptance:** this applies only to the application code at `main` `2d2993d`, on this Mac, as recorded in `gates-latest.json`. It does not cover PRs #20, #27 or #28, which are previews only. Any later relevant code change requires refreshing the affected qualification.
3. **Offline product release (Owner 4's gates G0 to G4, including the complete browser workflow):** not established here. Passing CI or this scientific gate does not show that the full browser workflow is usable.
4. **Live Gemini qualification:** NOT_RUN. Gemini stays disabled; no key was inspected and no provider was called.
